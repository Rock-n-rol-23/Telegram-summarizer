"""
Keywords tracking and alert system
"""

import re
import logging
from typing import List, Dict, Set, Optional
from datetime import datetime
from .db import get_digest_db

logger = logging.getLogger(__name__)

class KeywordMatcher:
    def __init__(self):
        self.db = get_digest_db()
    
    def add_keyword(self, user_id: int, pattern: str, is_regex: bool = False) -> Optional[int]:
        """Add keyword pattern for user"""
        try:
            # Validate regex if specified
            if is_regex:
                try:
                    re.compile(pattern)
                except re.error as e:
                    logger.error(f"Invalid regex pattern '{pattern}': {e}")
                    return None
            
            keyword_id = self.db.save_keyword(user_id, pattern, is_regex)
            
            if keyword_id:
                logger.info(f"Added keyword '{pattern}' for user {user_id}")
                return keyword_id
            else:
                logger.error(f"Failed to save keyword '{pattern}' for user {user_id}")
                return None
                
        except Exception as e:
            logger.error(f"Error adding keyword: {e}")
            return None
    
    def remove_keyword(self, user_id: int, keyword_id: int) -> bool:
        """Remove keyword by ID"""
        try:
            success = self.db.remove_keyword(user_id, keyword_id)
            if success:
                logger.info(f"Removed keyword {keyword_id} for user {user_id}")
            return success
        except Exception as e:
            logger.error(f"Error removing keyword: {e}")
            return False
    
    def get_user_keywords(self, user_id: int) -> List[Dict]:
        """Get all keywords for user"""
        try:
            return self.db.get_user_keywords(user_id)
        except Exception as e:
            logger.error(f"Error getting keywords for user {user_id}: {e}")
            return []
    
    def match_keywords(self, text: str, keywords: List[Dict]) -> List[Dict]:
        """
        Check text against list of keyword patterns
        Returns list of matched keywords
        """
        if not text or not keywords:
            return []
        
        text_lower = text.lower()
        matched = []
        
        for keyword in keywords:
            pattern = keyword.get('pattern', '')
            is_regex = keyword.get('is_regex', False)
            
            try:
                if is_regex:
                    # Regex matching
                    if re.search(pattern, text, re.IGNORECASE):
                        matched.append(keyword)
                else:
                    # Simple substring matching
                    if pattern.lower() in text_lower:
                        matched.append(keyword)
                        
            except Exception as e:
                logger.warning(f"Error matching keyword '{pattern}': {e}")
                continue
        
        return matched
    
    def check_all_users_keywords(self, text: str) -> Dict[int, List[Dict]]:
        """
        Check text against all users' keywords
        Returns dict: user_id -> list of matched keywords
        """
        # This is not efficient for large user bases
        # In production, consider using a keyword index or search engine
        try:
            user_matches = {}
            
            # Get all users with keywords (would need additional DB method)
            # For now, we'll implement a simpler approach
            
            return user_matches
            
        except Exception as e:
            logger.error(f"Error checking all keywords: {e}")
            return {}

async def check_keywords_and_alert(message_info: Dict, bot_instance):
    """
    Check message against all user keywords and send alerts
    """
    try:
        text = message_info.get('text', '')
        if not text:
            return
        
        matcher = KeywordMatcher()
        db = get_digest_db()
        
        # Get message metadata
        chat_info = message_info.get('chat', {})
        channel_title = chat_info.get('title', '')
        channel_username = chat_info.get('username', '')
        message_id = message_info.get('message_id', 0)
        posted_date = message_info.get('date', 0)
        
        # Create message URL
        if channel_username:
            message_url = f"https://t.me/{channel_username}/{message_id}"
        else:
            chat_id = chat_info.get('id', 0)
            message_url = f"https://t.me/c/{str(chat_id)[4:]}/{message_id}"
        
        # For efficiency, we need to check keywords per user
        # This is a simplified implementation
        # In production, consider using a keyword search index
        
        # Get all active schedules to find active users
        schedules = db.get_all_active_schedules()
        active_users = set(schedule['user_id'] for schedule in schedules)
        
        # Check keywords for each active user
        for user_id in active_users:
            try:
                user_keywords = matcher.get_user_keywords(user_id)
                
                if not user_keywords:
                    continue
                
                matched_keywords = matcher.match_keywords(text, user_keywords)
                
                if matched_keywords:
                    # Check if we already alerted for this message
                    message_db_id = _get_message_db_id(message_info)
                    
                    already_alerted = False
                    for kw in matched_keywords:
                        if message_db_id and db.was_alerted(kw['id'], message_db_id):
                            already_alerted = True
                            break
                    
                    if not already_alerted:
                        await _send_keyword_alert(
                            user_id, matched_keywords, message_info, 
                            message_url, bot_instance
                        )
                        
                        # Log alerts
                        if message_db_id:
                            for kw in matched_keywords:
                                db.log_alert(kw['id'], message_db_id)
                
            except Exception as e:
                logger.error(f"Error checking keywords for user {user_id}: {e}")
                continue
        
    except Exception as e:
        logger.error(f"Error in keyword alert check: {e}")

def _get_message_db_id(message_info: Dict) -> Optional[int]:
    """Get database message ID (simplified for now)"""
    # In a full implementation, we'd query the database
    # For now, return None to disable duplicate checking
    return None

async def _send_keyword_alert(user_id: int, matched_keywords: List[Dict], 
                             message_info: Dict, message_url: str, bot_instance):
    """Send keyword alert to user"""
    try:
        chat_info = message_info.get('chat', {})
        channel_name = chat_info.get('title') or chat_info.get('username', 'Unknown Channel')
        text = message_info.get('text', '')
        
        # Create alert message
        keyword_list = ', '.join([f"'{kw['pattern']}'" for kw in matched_keywords])
        
        # Create summary using existing summarization
        summary = await _create_mini_summary(text, bot_instance)
        
        alert_text = f"🔍 <b>Keyword Alert</b>\n\n"
        alert_text += f"📢 <b>Channel:</b> {channel_name}\n"
        alert_text += f"🎯 <b>Keywords:</b> {keyword_list}\n\n"
        
        if summary:
            alert_text += f"📝 <b>Summary:</b>\n{summary}\n\n"
        
        alert_text += f"🔗 <a href='{message_url}'>Read full message</a>"
        
        # Get user info to send to correct chat
        db = get_digest_db()
        user = db.get_user(user_id)
        
        if user:
            chat_id = user['chat_id']
            await bot_instance.send_message(chat_id, alert_text, parse_mode='HTML')
            logger.info(f"Sent keyword alert to user {user_id}")
        else:
            logger.warning(f"User {user_id} not found for alert")
            
    except Exception as e:
        logger.error(f"Error sending keyword alert: {e}")

async def _create_mini_summary(text: str, bot_instance) -> str:
    """Create mini summary using existing summarization"""
    try:
        # Use existing summarization functionality
        # This is a simplified version - integrate with actual summarizer
        
        if len(text) < 200:
            return text
        
        # Try to get first few sentences
        sentences = text.split('.')
        if len(sentences) > 1:
            return '. '.join(sentences[:2]) + '.'
        
        # Fallback to first 150 characters
        return text[:150] + '...' if len(text) > 150 else text
        
    except Exception as e:
        logger.error(f"Error creating mini summary: {e}")
        return text[:100] + '...' if len(text) > 100 else text

def add_keywords_from_text(user_id: int, keywords_text: str) -> List[str]:
    """
    Add multiple keywords from text (semicolon or comma separated)
    Returns list of added keywords
    """
    try:
        matcher = KeywordMatcher()
        
        # Split by semicolon or comma
        keywords = [kw.strip() for kw in re.split(r'[;,]', keywords_text) if kw.strip()]
        
        added_keywords = []
        for keyword in keywords:
            if len(keyword) >= 2:  # Minimum length
                keyword_id = matcher.add_keyword(user_id, keyword, is_regex=False)
                if keyword_id:
                    added_keywords.append(keyword)
        
        return added_keywords
        
    except Exception as e:
        logger.error(f"Error adding keywords from text: {e}")
        return []

# Global instance
_keyword_matcher = None

def get_keyword_matcher() -> KeywordMatcher:
    """Get global keyword matcher instance"""
    global _keyword_matcher
    if _keyword_matcher is None:
        _keyword_matcher = KeywordMatcher()
    return _keyword_matcher