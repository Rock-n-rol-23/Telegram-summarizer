"""
Channel sources handling - Bot API and Telethon integration
"""

import logging
import json
from typing import Dict, Optional, List
from datetime import datetime
from .db import get_digest_db
from .keywords import check_keywords_and_alert

logger = logging.getLogger(__name__)

class ChannelSourcesHandler:
    def __init__(self):
        self.db = get_digest_db()
    
    async def handle_channel_post(self, update: Dict, bot_instance) -> bool:
        """
        Handle channel_post update from Bot API
        Bot must be admin in the channel to receive these updates
        """
        try:
            if 'channel_post' not in update:
                return False
            
            post = update['channel_post']
            chat = post.get('chat', {})
            
            # Extract channel info
            chat_id = chat.get('id')
            username = chat.get('username', '').lstrip('@')
            title = chat.get('title', '')
            
            if not chat_id:
                logger.warning("Channel post without chat_id")
                return False
            
            # Save or update channel info
            channel_id = self.db.save_channel(
                username=username,
                tg_chat_id=chat_id,
                title=title,
                added_by_user_id=0  # System added
            )
            
            if not channel_id:
                logger.error(f"Failed to save channel {username}")
                return False
            
            # Extract message info
            message_id = post.get('message_id')
            date = post.get('date', 0)
            text = post.get('text', '')
            
            # Create message URL
            if username:
                message_url = f"https://t.me/{username}/{message_id}"
            else:
                message_url = f"https://t.me/c/{str(chat_id)[4:]}/{message_id}"
            
            # Save message
            success = self.db.save_message(
                channel_id=channel_id,
                tg_message_id=message_id,
                message_url=message_url,
                posted_at=date,
                text=text,
                raw_json=json.dumps(post)
            )
            
            if success:
                logger.info(f"Saved channel message: {username or title}/{message_id}")
                
                # Check for keyword alerts
                await self._check_keyword_alerts(post, bot_instance)
                
                return True
            else:
                logger.error(f"Failed to save message {username}/{message_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error handling channel post: {e}")
            return False
    
    async def handle_edited_channel_post(self, update: Dict, bot_instance) -> bool:
        """Handle edited channel post"""
        try:
            if 'edited_channel_post' not in update:
                return False
            
            # Treat edited posts same as new posts for now
            # Could implement update logic later
            modified_update = {'channel_post': update['edited_channel_post']}
            return await self.handle_channel_post(modified_update, bot_instance)
            
        except Exception as e:
            logger.error(f"Error handling edited channel post: {e}")
            return False
    
    async def _check_keyword_alerts(self, post: Dict, bot_instance):
        """Check message against user keywords and send alerts"""
        try:
            text = post.get('text', '')
            if not text:
                return
            
            # Get message info for alert
            message_info = {
                'text': text,
                'chat': post.get('chat', {}),
                'message_id': post.get('message_id'),
                'date': post.get('date', 0)
            }
            
            # Check keywords for all users (this is a broadcast check)
            await check_keywords_and_alert(message_info, bot_instance)
            
        except Exception as e:
            logger.error(f"Error checking keyword alerts: {e}")
    
    def add_channel_to_user(self, user_id: int, channel_identifier: str) -> Optional[Dict]:
        """
        Add channel to user's subscription list
        channel_identifier can be username (@channel) or chat_id
        """
        try:
            # Find channel in database
            channel = self.db.find_channel(channel_identifier)
            
            if not channel:
                logger.warning(f"Channel not found: {channel_identifier}")
                return None
            
            # Add to user's channels
            success = self.db.add_user_channel(user_id, channel['id'])
            
            if success:
                logger.info(f"Added channel {channel_identifier} to user {user_id}")
                return channel
            else:
                logger.error(f"Failed to add channel {channel_identifier} to user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error adding channel to user: {e}")
            return None
    
    def remove_channel_from_user(self, user_id: int, channel_identifier: str) -> bool:
        """Remove channel from user's subscription"""
        try:
            channel = self.db.find_channel(channel_identifier)
            
            if not channel:
                logger.warning(f"Channel not found: {channel_identifier}")
                return False
            
            success = self.db.remove_user_channel(user_id, channel['id'])
            
            if success:
                logger.info(f"Removed channel {channel_identifier} from user {user_id}")
                return True
            else:
                logger.error(f"Failed to remove channel {channel_identifier} from user {user_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing channel from user: {e}")
            return False
    
    def get_user_channels_list(self, user_id: int) -> List[Dict]:
        """Get formatted list of user's channels"""
        try:
            channels = self.db.get_user_channels(user_id)
            return channels
        except Exception as e:
            logger.error(f"Error getting user channels: {e}")
            return []
    
    def add_channel_from_forward(self, user_id: int, forwarded_message: Dict) -> Optional[Dict]:
        """
        Add channel from forwarded message
        Extract channel info from forward_from_chat
        """
        try:
            forward_info = (
                forwarded_message.get('forward_from_chat') or
                forwarded_message.get('forward_origin', {}).get('chat', {})
            )
            
            if not forward_info:
                return None
            
            chat_id = forward_info.get('id')
            username = forward_info.get('username', '').lstrip('@')
            title = forward_info.get('title', '')
            
            if not chat_id:
                return None
            
            # Save channel info
            channel_id = self.db.save_channel(
                username=username,
                tg_chat_id=chat_id,
                title=title,
                added_by_user_id=user_id
            )
            
            if channel_id:
                # Add to user's channels
                self.db.add_user_channel(user_id, channel_id)
                
                # Return channel info
                return {
                    'id': channel_id,
                    'username': username,
                    'tg_chat_id': chat_id,
                    'title': title
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error adding channel from forward: {e}")
            return None

# Global instance
_sources_handler = None

def get_sources_handler() -> ChannelSourcesHandler:
    """Get global sources handler instance"""
    global _sources_handler
    if _sources_handler is None:
        _sources_handler = ChannelSourcesHandler()
    return _sources_handler

async def handle_channel_update(update: Dict, bot_instance) -> bool:
    """
    Main handler for channel updates
    Call this from bot's update handler
    """
    handler = get_sources_handler()
    
    if 'channel_post' in update:
        return await handler.handle_channel_post(update, bot_instance)
    elif 'edited_channel_post' in update:
        return await handler.handle_edited_channel_post(update, bot_instance)
    
    return False