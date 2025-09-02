"""
Bot commands for digest system
"""

import logging
import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from .db import get_digest_db
from .sources import get_sources_handler
from .keywords import get_keyword_matcher, add_keywords_from_text
from .scheduler import get_digest_scheduler
from .trends import get_trends_analyzer

logger = logging.getLogger(__name__)

class DigestCommands:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.db = get_digest_db()
        self.sources_handler = get_sources_handler()
        self.keyword_matcher = get_keyword_matcher()
        
    async def handle_digest_command(self, update: Dict, command: str, args: str = ""):
        """Main handler for digest commands"""
        try:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            
            # Save user info
            self.db.save_user(user_id, chat_id)
            
            if command == "digest_help":
                await self._handle_digest_help(chat_id)
            elif command == "digest_add_channel":
                await self._handle_add_channel(chat_id, user_id, args, message)
            elif command == "digest_list":
                await self._handle_list_channels(chat_id, user_id)
            elif command == "digest_remove_channel":
                await self._handle_remove_channel(chat_id, user_id, args)
            elif command == "digest_schedule":
                await self._handle_schedule(chat_id, user_id, args)
            elif command == "digest_now":
                await self._handle_digest_now(chat_id, user_id, args)
            elif command == "keywords_add":
                await self._handle_keywords_add(chat_id, user_id, args)
            elif command == "keywords_list":
                await self._handle_keywords_list(chat_id, user_id)
            elif command == "keywords_remove":
                await self._handle_keywords_remove(chat_id, user_id, args)
            elif command == "alerts":
                await self._handle_alerts_toggle(chat_id, user_id, args)
            elif command == "trends":
                await self._handle_trends(chat_id, user_id, args)
            else:
                await self.bot.send_message(
                    chat_id,
                    "❓ Unknown digest command. Use /digest_help for help."
                )
                
        except Exception as e:
            logger.error(f"Error handling digest command {command}: {e}")
            await self.bot.send_message(
                chat_id,
                f"❌ Error processing command: {e}"
            )
    
    async def _handle_digest_help(self, chat_id: int):
        """Show digest help"""
        help_text = """
🔄 <b>Digest System Help</b>

<b>📢 Channel Management:</b>
/digest_add_channel @username — Add channel to your digest
/digest_list — Show your channels
/digest_remove_channel @username — Remove channel

<b>⏰ Scheduling:</b>
/digest_schedule hourly [mm] — Every hour at :mm (e.g., :05)
/digest_schedule daily HH:MM — Daily at time (e.g., 09:00)
/digest_schedule weekly Mon 09:00 — Weekly on day at time
/digest_schedule monthly 15 09:00 — Monthly on day 15 at 09:00
/digest_schedule off — Turn off all schedules

<b>📋 Instant Digests:</b>
/digest_now [1h|24h|7d|30d] — Generate digest for period
Examples: /digest_now 1h, /digest_now 24h, /digest_now 7d

<b>🔍 Keywords & Alerts:</b>
/keywords_add keyword1; keyword2; keyword3 — Add keywords
/keywords_list — Show your keywords
/keywords_remove [id] — Remove keyword by ID
/alerts on|off — Enable/disable alerts

<b>📈 Trends:</b>
/trends weekly — Weekly trends analysis
/trends monthly — Monthly trends analysis

<b>💡 Tips:</b>
• Add channels by forwarding a post from them
• Hourly digests are compact (max 8 items)
• Keywords trigger instant alerts with mini-summaries
• Bot needs admin rights in public channels
        """
        
        await self.bot.send_message(chat_id, help_text, parse_mode='HTML')
    
    async def _handle_add_channel(self, chat_id: int, user_id: int, args: str, message: Dict):
        """Handle adding channel"""
        try:
            # Check if message is forwarded from a channel
            if 'forward_from_chat' in message or 'forward_origin' in message:
                channel = self.sources_handler.add_channel_from_forward(user_id, message)
                
                if channel:
                    channel_name = channel.get('username') or channel.get('title', 'Unknown')
                    await self.bot.send_message(
                        chat_id,
                        f"✅ Added channel: {channel_name}\n\n"
                        f"You'll receive digests from this channel according to your schedule."
                    )
                else:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Could not add channel from forwarded message.\n\n"
                        "Make sure you forward a post from a public channel."
                    )
                return
            
            # Handle username argument
            if not args:
                await self.bot.send_message(
                    chat_id,
                    "📝 Please provide channel username or forward a post from the channel.\n\n"
                    "Example: /digest_add_channel @channelname"
                )
                return
            
            channel_identifier = args.strip()
            
            # Add channel
            channel = self.sources_handler.add_channel_to_user(user_id, channel_identifier)
            
            if channel:
                channel_name = channel.get('username') or channel.get('title', 'Unknown')
                await self.bot.send_message(
                    chat_id,
                    f"✅ Added channel: {channel_name}\n\n"
                    f"You'll receive digests from this channel according to your schedule.\n\n"
                    f"⚠️ Note: Bot needs admin rights in public channels to receive updates."
                )
            else:
                await self.bot.send_message(
                    chat_id,
                    f"❌ Could not add channel '{channel_identifier}'.\n\n"
                    f"Possible reasons:\n"
                    f"• Channel doesn't exist or is private\n"
                    f"• Bot is not admin in the channel\n"
                    f"• Channel hasn't posted any messages yet\n\n"
                    f"For public channels, make the bot admin first."
                )
                
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            await self.bot.send_message(
                chat_id,
                f"❌ Error adding channel: {e}"
            )
    
    async def _handle_list_channels(self, chat_id: int, user_id: int):
        """List user's channels"""
        try:
            channels = self.sources_handler.get_user_channels_list(user_id)
            
            if not channels:
                await self.bot.send_message(
                    chat_id,
                    "📭 You haven't added any channels yet.\n\n"
                    "Use /digest_add_channel @username to add a channel."
                )
                return
            
            lines = ["📢 <b>Your Digest Channels:</b>\n"]
            
            for i, channel in enumerate(channels, 1):
                name = channel.get('username') or channel.get('title', 'Unknown')
                if channel.get('username'):
                    name = f"@{name}"
                
                lines.append(f"{i}. {name}")
            
            # Add schedule info
            scheduler = get_digest_scheduler()
            if scheduler:
                schedules = scheduler.get_user_schedules_info(user_id)
                
                if schedules:
                    lines.append("\n⏰ <b>Active Schedules:</b>")
                    for schedule in schedules:
                        lines.append(f"• {schedule['readable']}")
                else:
                    lines.append("\n⏰ No active schedules. Use /digest_schedule to set up.")
            
            await self.bot.send_message(chat_id, '\n'.join(lines), parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error listing channels: {e}")
            await self.bot.send_message(chat_id, f"❌ Error listing channels: {e}")
    
    async def _handle_remove_channel(self, chat_id: int, user_id: int, args: str):
        """Remove channel"""
        try:
            if not args:
                await self.bot.send_message(
                    chat_id,
                    "📝 Please provide channel username.\n\n"
                    "Example: /digest_remove_channel @channelname"
                )
                return
            
            channel_identifier = args.strip()
            
            success = self.sources_handler.remove_channel_from_user(user_id, channel_identifier)
            
            if success:
                await self.bot.send_message(
                    chat_id,
                    f"✅ Removed channel: {channel_identifier}"
                )
            else:
                await self.bot.send_message(
                    chat_id,
                    f"❌ Could not remove channel '{channel_identifier}'.\n\n"
                    f"Channel might not be in your list. Use /digest_list to see your channels."
                )
                
        except Exception as e:
            logger.error(f"Error removing channel: {e}")
            await self.bot.send_message(chat_id, f"❌ Error removing channel: {e}")
    
    async def _handle_schedule(self, chat_id: int, user_id: int, args: str):
        """Handle schedule commands"""
        try:
            if not args or args.strip() == "":
                # Show current schedules
                scheduler = get_digest_scheduler()
                if scheduler:
                    schedules = scheduler.get_user_schedules_info(user_id)
                    
                    if schedules:
                        lines = ["⏰ <b>Your Active Schedules:</b>\n"]
                        for schedule in schedules:
                            lines.append(f"• {schedule['readable']}")
                            if schedule.get('next_run'):
                                lines.append(f"  Next: {schedule['next_run']}")
                        
                        lines.append("\nUse /digest_schedule off to disable all schedules.")
                        await self.bot.send_message(chat_id, '\n'.join(lines), parse_mode='HTML')
                    else:
                        await self.bot.send_message(
                            chat_id,
                            "⏰ No active schedules.\n\n"
                            "Examples:\n"
                            "/digest_schedule hourly 05\n"
                            "/digest_schedule daily 09:00\n"
                            "/digest_schedule weekly Mon 09:00"
                        )
                return
            
            args_parts = args.strip().split()
            
            if args_parts[0] == "off":
                # Remove all schedules
                scheduler = get_digest_scheduler()
                if scheduler and scheduler.remove_user_schedules(user_id):
                    await self.bot.send_message(
                        chat_id,
                        "✅ All schedules disabled."
                    )
                else:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Error disabling schedules."
                    )
                return
            
            # Parse schedule parameters
            period = args_parts[0].lower()
            
            if period == "hourly":
                minute = int(args_parts[1]) if len(args_parts) > 1 else 5
                
                if not 0 <= minute <= 59:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Minute must be between 0-59.\n\n"
                        "Example: /digest_schedule hourly 05"
                    )
                    return
                
                cron = f"{minute} * * * *"
                
            elif period == "daily":
                if len(args_parts) < 2:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Please specify time.\n\n"
                        "Example: /digest_schedule daily 09:00"
                    )
                    return
                
                time_str = args_parts[1]
                hour, minute = self._parse_time(time_str)
                
                if hour is None:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Invalid time format. Use HH:MM (24-hour).\n\n"
                        "Example: /digest_schedule daily 09:00"
                    )
                    return
                
                cron = f"{minute} {hour} * * *"
                
            elif period == "weekly":
                if len(args_parts) < 3:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Please specify day and time.\n\n"
                        "Example: /digest_schedule weekly Mon 09:00"
                    )
                    return
                
                day_str = args_parts[1]
                time_str = args_parts[2]
                
                day_of_week = self._parse_day_of_week(day_str)
                hour, minute = self._parse_time(time_str)
                
                if day_of_week is None or hour is None:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Invalid day or time format.\n\n"
                        "Example: /digest_schedule weekly Mon 09:00\n"
                        "Days: Mon, Tue, Wed, Thu, Fri, Sat, Sun"
                    )
                    return
                
                cron = f"{minute} {hour} * * {day_of_week}"
                
            elif period == "monthly":
                if len(args_parts) < 3:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Please specify day and time.\n\n"
                        "Example: /digest_schedule monthly 15 09:00"
                    )
                    return
                
                day_of_month = int(args_parts[1])
                time_str = args_parts[2]
                
                if not 1 <= day_of_month <= 31:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Day of month must be between 1-31.\n\n"
                        "Example: /digest_schedule monthly 15 09:00"
                    )
                    return
                
                hour, minute = self._parse_time(time_str)
                
                if hour is None:
                    await self.bot.send_message(
                        chat_id,
                        "❌ Invalid time format. Use HH:MM (24-hour).\n\n"
                        "Example: /digest_schedule monthly 15 09:00"
                    )
                    return
                
                cron = f"{minute} {hour} {day_of_month} * *"
                
            else:
                await self.bot.send_message(
                    chat_id,
                    "❌ Invalid period. Use: hourly, daily, weekly, or monthly.\n\n"
                    "Examples:\n"
                    "/digest_schedule hourly 05\n"
                    "/digest_schedule daily 09:00\n"
                    "/digest_schedule weekly Mon 09:00\n"
                    "/digest_schedule monthly 15 09:00"
                )
                return
            
            # Register schedule
            scheduler = get_digest_scheduler()
            if scheduler and scheduler.register_or_update_schedule(user_id, cron, period):
                # Show confirmation
                schedules = scheduler.get_user_schedules_info(user_id)
                current_schedule = next((s for s in schedules if s['period'] == period), None)
                
                if current_schedule:
                    await self.bot.send_message(
                        chat_id,
                        f"✅ {period.title()} digest scheduled!\n\n"
                        f"📅 {current_schedule['readable']}\n"
                        f"🕐 Next run: {current_schedule.get('next_run', 'Soon')}"
                    )
                else:
                    await self.bot.send_message(
                        chat_id,
                        f"✅ {period.title()} digest scheduled!"
                    )
            else:
                await self.bot.send_message(
                    chat_id,
                    "❌ Error setting up schedule. Please try again."
                )
                
        except ValueError as e:
            await self.bot.send_message(
                chat_id,
                f"❌ Invalid format: {e}\n\n"
                "Use /digest_help for examples."
            )
        except Exception as e:
            logger.error(f"Error handling schedule: {e}")
            await self.bot.send_message(chat_id, f"❌ Error setting schedule: {e}")
    
    def _parse_time(self, time_str: str) -> tuple:
        """Parse time string HH:MM"""
        try:
            hour, minute = map(int, time_str.split(':'))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
            return None, None
        except:
            return None, None
    
    def _parse_day_of_week(self, day_str: str) -> Optional[int]:
        """Parse day of week string to cron format (0=Sunday)"""
        days = {
            'sun': 0, 'sunday': 0,
            'mon': 1, 'monday': 1,
            'tue': 2, 'tuesday': 2,
            'wed': 3, 'wednesday': 3,
            'thu': 4, 'thursday': 4,
            'fri': 5, 'friday': 5,
            'sat': 6, 'saturday': 6
        }
        return days.get(day_str.lower())
    
    async def _handle_digest_now(self, chat_id: int, user_id: int, args: str):
        """Generate instant digest"""
        try:
            # Parse period argument
            period_arg = args.strip() if args else "24h"
            
            # Calculate time range
            current_time = datetime.now()
            to_ts = int(current_time.timestamp())
            
            if period_arg == "1h":
                from_ts = to_ts - 3600
                period_name = "Last Hour"
            elif period_arg == "24h":
                from_ts = to_ts - (24 * 3600)
                period_name = "Last 24 Hours"
            elif period_arg == "7d":
                from_ts = to_ts - (7 * 24 * 3600)
                period_name = "Last 7 Days"
            elif period_arg == "30d":
                from_ts = to_ts - (30 * 24 * 3600)
                period_name = "Last 30 Days"
            else:
                await self.bot.send_message(
                    chat_id,
                    "❌ Invalid period. Use: 1h, 24h, 7d, or 30d.\n\n"
                    "Examples:\n"
                    "/digest_now 1h\n"
                    "/digest_now 24h\n"
                    "/digest_now 7d"
                )
                return
            
            # Show processing message
            processing_msg = await self.bot.send_message(
                chat_id,
                f"⏳ Generating {period_name} digest..."
            )
            
            # Generate digest
            scheduler = get_digest_scheduler()
            if scheduler:
                await scheduler.generate_and_send_digest(user_id, 'custom', from_ts, to_ts)
                
                # Delete processing message
                if processing_msg:
                    await self.bot.delete_message(chat_id, processing_msg.get('message_id'))
            else:
                await self.bot.send_message(
                    chat_id,
                    "❌ Digest system not available. Please try again later."
                )
                
        except Exception as e:
            logger.error(f"Error generating instant digest: {e}")
            await self.bot.send_message(chat_id, f"❌ Error generating digest: {e}")
    
    async def _handle_keywords_add(self, chat_id: int, user_id: int, args: str):
        """Add keywords"""
        try:
            if not args.strip():
                await self.bot.send_message(
                    chat_id,
                    "📝 Please provide keywords to add.\n\n"
                    "Example: /keywords_add Bitcoin; ставка ЦБ; IPO\n\n"
                    "Separate multiple keywords with semicolons (;) or commas (,)."
                )
                return
            
            added_keywords = add_keywords_from_text(user_id, args)
            
            if added_keywords:
                keywords_list = '\n'.join([f"• {kw}" for kw in added_keywords])
                await self.bot.send_message(
                    chat_id,
                    f"✅ Added {len(added_keywords)} keywords:\n\n{keywords_list}\n\n"
                    f"You'll receive instant alerts when these keywords appear in your channels."
                )
            else:
                await self.bot.send_message(
                    chat_id,
                    "❌ No valid keywords added. Make sure keywords are at least 2 characters long."
                )
                
        except Exception as e:
            logger.error(f"Error adding keywords: {e}")
            await self.bot.send_message(chat_id, f"❌ Error adding keywords: {e}")
    
    async def _handle_keywords_list(self, chat_id: int, user_id: int):
        """List user keywords"""
        try:
            keywords = self.keyword_matcher.get_user_keywords(user_id)
            
            if not keywords:
                await self.bot.send_message(
                    chat_id,
                    "📭 You haven't added any keywords yet.\n\n"
                    "Use /keywords_add to add keywords for instant alerts."
                )
                return
            
            lines = ["🔍 <b>Your Keywords:</b>\n"]
            
            for kw in keywords:
                kw_id = kw['id']
                pattern = kw['pattern']
                is_regex = kw.get('is_regex', False)
                
                regex_indicator = " (regex)" if is_regex else ""
                lines.append(f"{kw_id}. {pattern}{regex_indicator}")
            
            lines.append(f"\nTotal: {len(keywords)} keywords")
            lines.append("Use /keywords_remove [id] to remove a keyword.")
            
            await self.bot.send_message(chat_id, '\n'.join(lines), parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error listing keywords: {e}")
            await self.bot.send_message(chat_id, f"❌ Error listing keywords: {e}")
    
    async def _handle_keywords_remove(self, chat_id: int, user_id: int, args: str):
        """Remove keyword by ID"""
        try:
            if not args.strip():
                await self.bot.send_message(
                    chat_id,
                    "📝 Please provide keyword ID to remove.\n\n"
                    "Use /keywords_list to see your keywords with IDs.\n"
                    "Example: /keywords_remove 5"
                )
                return
            
            try:
                keyword_id = int(args.strip())
            except ValueError:
                await self.bot.send_message(
                    chat_id,
                    "❌ Invalid keyword ID. Must be a number.\n\n"
                    "Use /keywords_list to see your keywords with IDs."
                )
                return
            
            success = self.keyword_matcher.remove_keyword(user_id, keyword_id)
            
            if success:
                await self.bot.send_message(
                    chat_id,
                    f"✅ Removed keyword #{keyword_id}"
                )
            else:
                await self.bot.send_message(
                    chat_id,
                    f"❌ Could not remove keyword #{keyword_id}.\n\n"
                    f"Make sure the ID is correct and the keyword belongs to you."
                )
                
        except Exception as e:
            logger.error(f"Error removing keyword: {e}")
            await self.bot.send_message(chat_id, f"❌ Error removing keyword: {e}")
    
    async def _handle_alerts_toggle(self, chat_id: int, user_id: int, args: str):
        """Toggle alerts (placeholder)"""
        try:
            # This is a placeholder - in full implementation, 
            # you'd store user alert preferences in the database
            
            if args.strip().lower() == "off":
                await self.bot.send_message(
                    chat_id,
                    "🔕 Keyword alerts disabled.\n\n"
                    "Note: This is a placeholder. Full implementation would store this preference."
                )
            else:
                await self.bot.send_message(
                    chat_id,
                    "🔔 Keyword alerts enabled.\n\n"
                    "You'll receive instant notifications when your keywords are mentioned."
                )
                
        except Exception as e:
            logger.error(f"Error toggling alerts: {e}")
            await self.bot.send_message(chat_id, f"❌ Error toggling alerts: {e}")
    
    async def _handle_trends(self, chat_id: int, user_id: int, args: str):
        """Show trends analysis"""
        try:
            period = args.strip().lower() if args else "weekly"
            
            if period not in ["weekly", "monthly"]:
                await self.bot.send_message(
                    chat_id,
                    "❌ Invalid period. Use 'weekly' or 'monthly'.\n\n"
                    "Examples:\n"
                    "/trends weekly\n"
                    "/trends monthly"
                )
                return
            
            # Show processing message
            processing_msg = await self.bot.send_message(
                chat_id,
                f"📊 Analyzing {period} trends..."
            )
            
            # Get trends
            analyzer = get_trends_analyzer()
            
            if period == "weekly":
                trends = analyzer.get_weekly_trends(user_id)
            else:
                trends = analyzer.get_monthly_trends(user_id)
            
            # Format trends
            if not trends or trends.get('total_messages', 0) == 0:
                await self.bot.edit_message(
                    chat_id,
                    processing_msg.get('message_id'),
                    f"📊 No data for {period} trends analysis.\n\n"
                    f"Add some channels and wait for messages to get trend analysis."
                )
                return
            
            # Build trends message
            lines = [f"📈 <b>{period.title()} Trends Analysis</b>"]
            lines.append(f"📊 {trends['total_messages']} messages analyzed")
            
            # Top keywords
            keywords = trends.get('top_keywords', [])
            if keywords:
                lines.append("\n🔥 <b>Trending Keywords:</b>")
                for kw in keywords[:5]:
                    relevance_stars = '⭐' * min(3, int(kw.get('relevance', 0) * 3))
                    lines.append(f"• {kw['keyword']} {relevance_stars}")
            
            # Channel activity
            channel_stats = trends.get('channel_stats', [])
            if channel_stats:
                lines.append("\n📢 <b>Most Active Channels:</b>")
                for ch in channel_stats[:3]:
                    channel_name = ch['username'] or ch['title'] or ch['channel']
                    lines.append(f"• {channel_name} — {ch['message_count']} messages")
            
            # Time range
            time_range = trends.get('time_range', {})
            if time_range:
                duration = time_range.get('duration_hours', 0)
                lines.append(f"\n⏱️ <b>Period:</b> {duration:.0f} hours")
            
            await self.bot.edit_message(
                chat_id,
                processing_msg.get('message_id'),
                '\n'.join(lines),
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Error showing trends: {e}")
            await self.bot.send_message(chat_id, f"❌ Error analyzing trends: {e}")

# Global instance
_digest_commands = None

def get_digest_commands(bot_instance):
    """Get digest commands handler"""
    global _digest_commands
    if _digest_commands is None:
        _digest_commands = DigestCommands(bot_instance)
    return _digest_commands

async def handle_digest_command(update: Dict, bot_instance):
    """Handle digest commands from bot"""
    try:
        message = update.get("message", {})
        text = message.get("text", "")
        
        if not text.startswith("/"):
            return False
        
        # Parse command
        parts = text.split(None, 1)
        command = parts[0][1:]  # Remove /
        args = parts[1] if len(parts) > 1 else ""
        
        # Check if it's a digest command
        digest_commands = [
            "digest_help", "digest_add_channel", "digest_list", "digest_remove_channel",
            "digest_schedule", "digest_now", "keywords_add", "keywords_list", 
            "keywords_remove", "alerts", "trends"
        ]
        
        if command in digest_commands:
            handler = get_digest_commands(bot_instance)
            await handler.handle_digest_command(update, command, args)
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error in digest command handler: {e}")
        return False