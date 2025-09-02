"""
APScheduler-based digest scheduling system
"""

import logging
import os
from typing import Dict, List, Optional
from datetime import datetime, time
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .db import get_digest_db
from .dedup import deduplicate_messages
from .cluster import MessageClusterer
from .trends import analyze_trends_for_period
from .renderer import render_digest

logger = logging.getLogger(__name__)

# Environment configuration
TIMEZONE = os.getenv('DIGEST_TIMEZONE', 'Europe/Amsterdam')
DEFAULT_DAILY_TIME = os.getenv('DIGEST_DEFAULT_DAILY_TIME', '09:00')
DEFAULT_HOURLY_MINUTE = int(os.getenv('DIGEST_DEFAULT_HOURLY_MINUTE', '5'))
HOURLY_WINDOW_MIN = int(os.getenv('DIGEST_HOURLY_WINDOW_MIN', '65'))
QUIET_HOURS = os.getenv('DIGEST_QUIET_HOURS', '')  # e.g., "23-07"

class DigestScheduler:
    def __init__(self, bot_instance):
        self.scheduler = BackgroundScheduler(timezone=pytz.timezone(TIMEZONE))
        self.bot_instance = bot_instance
        self.db = get_digest_db()
        self.clusterer = MessageClusterer()
        self._quiet_hours_range = self._parse_quiet_hours()
        
    def start(self):
        """Start the scheduler and load existing schedules"""
        try:
            self.scheduler.start()
            logger.info("Digest scheduler started")
            
            # Load existing user schedules
            self._load_existing_schedules()
            
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
    
    def stop(self):
        """Stop the scheduler"""
        try:
            self.scheduler.shutdown()
            logger.info("Digest scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    def _parse_quiet_hours(self) -> Optional[tuple]:
        """Parse quiet hours range from environment"""
        try:
            if not QUIET_HOURS:
                return None
            
            # Parse format like "23-07"
            start_str, end_str = QUIET_HOURS.split('-')
            start_hour = int(start_str)
            end_hour = int(end_str)
            
            return (start_hour, end_hour)
        except:
            logger.warning(f"Invalid QUIET_HOURS format: {QUIET_HOURS}")
            return None
    
    def _is_quiet_time(self, dt: datetime) -> bool:
        """Check if current time is in quiet hours"""
        if not self._quiet_hours_range:
            return False
        
        start_hour, end_hour = self._quiet_hours_range
        current_hour = dt.hour
        
        if start_hour <= end_hour:
            # Same day range (e.g., 14-18)
            return start_hour <= current_hour <= end_hour
        else:
            # Overnight range (e.g., 23-07)
            return current_hour >= start_hour or current_hour <= end_hour
    
    def _load_existing_schedules(self):
        """Load all existing user schedules and register them"""
        try:
            schedules = self.db.get_all_active_schedules()
            
            for schedule in schedules:
                user_id = schedule['user_id']
                cron = schedule['cron']
                period = schedule['period']
                
                job_id = f"digest_{user_id}_{period}"
                
                # Create cron trigger
                trigger = CronTrigger.from_crontab(cron, timezone=pytz.timezone(TIMEZONE))
                
                # Add job
                self.scheduler.add_job(
                    func=self._run_digest_job,
                    trigger=trigger,
                    args=[user_id, period],
                    id=job_id,
                    replace_existing=True
                )
            
            logger.info(f"Loaded {len(schedules)} existing schedules")
            
        except Exception as e:
            logger.error(f"Error loading existing schedules: {e}")
    
    def register_or_update_schedule(self, user_id: int, cron: str, period: str) -> bool:
        """Register or update user schedule"""
        try:
            # Validate cron expression
            try:
                CronTrigger.from_crontab(cron, timezone=pytz.timezone(TIMEZONE))
            except Exception as e:
                logger.error(f"Invalid cron expression '{cron}': {e}")
                return False
            
            # Save to database
            schedule_id = self.db.save_schedule(user_id, cron, period)
            
            if not schedule_id:
                logger.error(f"Failed to save schedule for user {user_id}")
                return False
            
            # Remove existing job for this period
            job_id = f"digest_{user_id}_{period}"
            
            try:
                self.scheduler.remove_job(job_id)
            except:
                pass  # Job might not exist
            
            # Add new job
            trigger = CronTrigger.from_crontab(cron, timezone=pytz.timezone(TIMEZONE))
            
            self.scheduler.add_job(
                func=self._run_digest_job,
                trigger=trigger,
                args=[user_id, period],
                id=job_id,
                replace_existing=True
            )
            
            logger.info(f"Registered {period} schedule for user {user_id}: {cron}")
            return True
            
        except Exception as e:
            logger.error(f"Error registering schedule: {e}")
            return False
    
    def remove_user_schedules(self, user_id: int, period: str = None) -> bool:
        """Remove user schedules"""
        try:
            # Remove from database
            success = self.db.remove_user_schedules(user_id, period)
            
            if success:
                # Remove scheduler jobs
                if period:
                    job_id = f"digest_{user_id}_{period}"
                    try:
                        self.scheduler.remove_job(job_id)
                    except:
                        pass
                else:
                    # Remove all jobs for user
                    for p in ['hourly', 'daily', 'weekly', 'monthly']:
                        job_id = f"digest_{user_id}_{p}"
                        try:
                            self.scheduler.remove_job(job_id)
                        except:
                            pass
                
                logger.info(f"Removed schedules for user {user_id}, period: {period}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error removing schedules: {e}")
            return False
    
    async def _run_digest_job(self, user_id: int, period: str):
        """Run digest generation job"""
        try:
            current_time = datetime.now(pytz.timezone(TIMEZONE))
            
            # Check quiet hours for hourly digests
            if period == 'hourly' and self._is_quiet_time(current_time):
                logger.info(f"Skipping hourly digest for user {user_id} - quiet hours")
                return
            
            logger.info(f"Running {period} digest job for user {user_id}")
            
            # Calculate time window
            to_ts = int(current_time.timestamp())
            
            if period == 'hourly':
                # Use configurable window for hourly (default 65 minutes)
                from_ts = to_ts - (HOURLY_WINDOW_MIN * 60)
            elif period == 'daily':
                # Last 24 hours
                from_ts = to_ts - (24 * 3600)
            elif period == 'weekly':
                # Last 7 days
                from_ts = to_ts - (7 * 24 * 3600)
            elif period == 'monthly':
                # Last 30 days
                from_ts = to_ts - (30 * 24 * 3600)
            else:
                # Default to daily
                from_ts = to_ts - (24 * 3600)
            
            # Generate digest
            await self.generate_and_send_digest(user_id, period, from_ts, to_ts)
            
        except Exception as e:
            logger.error(f"Error running digest job for user {user_id}: {e}")
    
    async def generate_and_send_digest(self, user_id: int, period: str, from_ts: int, to_ts: int):
        """Generate digest and send to user"""
        try:
            # Get messages from user's channels
            messages = self.db.get_messages_in_period(user_id, from_ts, to_ts)
            
            if not messages:
                logger.info(f"No messages for user {user_id} in period {from_ts}-{to_ts}")
                return
            
            logger.info(f"Processing {len(messages)} messages for user {user_id}")
            
            # Deduplicate messages
            unique_messages, merged_groups = deduplicate_messages(messages)
            
            # Cluster messages
            clusters = self.clusterer.cluster_and_summarize(unique_messages)
            
            # Analyze trends (skip for hourly)
            trends = None
            if period != 'hourly' and len(unique_messages) > 3:
                trends = analyze_trends_for_period(unique_messages, period)
            
            # Render digest
            rendered_text, has_more = render_digest(
                clusters, trends, period, from_ts, to_ts
            )
            
            # Save digest to database
            digest_id = self.db.save_digest(user_id, period, from_ts, to_ts, rendered_text)
            
            # Send to user
            await self._send_digest_to_user(user_id, rendered_text, has_more)
            
            logger.info(f"Sent {period} digest to user {user_id}, digest_id: {digest_id}")
            
        except Exception as e:
            logger.error(f"Error generating digest for user {user_id}: {e}")
    
    async def _send_digest_to_user(self, user_id: int, digest_text: str, has_more: bool):
        """Send digest message to user"""
        try:
            # Get user info
            user = self.db.get_user(user_id)
            
            if not user:
                logger.error(f"User {user_id} not found")
                return
            
            chat_id = user['chat_id']
            
            # Send digest
            await self.bot_instance.send_message(
                chat_id, 
                digest_text, 
                parse_mode='HTML'
            )
            
            # If there are more items, could add pagination buttons here
            
        except Exception as e:
            logger.error(f"Error sending digest to user {user_id}: {e}")
    
    def get_user_schedules_info(self, user_id: int) -> List[Dict]:
        """Get formatted info about user's schedules"""
        try:
            schedules = self.db.get_user_schedules(user_id)
            
            formatted_schedules = []
            for schedule in schedules:
                period = schedule['period']
                cron = schedule['cron']
                
                # Convert cron to human readable
                readable = self._cron_to_readable(cron, period)
                
                formatted_schedules.append({
                    'period': period,
                    'cron': cron,
                    'readable': readable,
                    'next_run': self._get_next_run_time(cron)
                })
            
            return formatted_schedules
            
        except Exception as e:
            logger.error(f"Error getting user schedules info: {e}")
            return []
    
    def _cron_to_readable(self, cron: str, period: str) -> str:
        """Convert cron expression to human readable format"""
        try:
            parts = cron.split()
            
            if period == 'hourly':
                minute = parts[0]
                return f"Every hour at :{minute}"
            elif period == 'daily':
                minute, hour = parts[0], parts[1]
                return f"Daily at {hour}:{minute}"
            elif period == 'weekly':
                minute, hour, day_of_month, month, day_of_week = parts
                days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                day_name = days[int(day_of_week)]
                return f"Weekly on {day_name} at {hour}:{minute}"
            elif period == 'monthly':
                minute, hour, day_of_month = parts[0], parts[1], parts[2]
                return f"Monthly on day {day_of_month} at {hour}:{minute}"
            else:
                return cron
                
        except:
            return cron
    
    def _get_next_run_time(self, cron: str) -> Optional[str]:
        """Get next run time for cron expression"""
        try:
            trigger = CronTrigger.from_crontab(cron, timezone=pytz.timezone(TIMEZONE))
            next_run = trigger.get_next_fire_time(None, datetime.now(pytz.timezone(TIMEZONE)))
            
            if next_run:
                return next_run.strftime('%Y-%m-%d %H:%M %Z')
            
            return None
            
        except:
            return None

# Global scheduler instance
_digest_scheduler = None

def get_digest_scheduler():
    """Get global digest scheduler instance"""
    global _digest_scheduler
    return _digest_scheduler

def start_scheduler(bot_instance):
    """Start digest scheduler"""
    global _digest_scheduler
    
    try:
        if _digest_scheduler is None:
            _digest_scheduler = DigestScheduler(bot_instance)
        
        _digest_scheduler.start()
        logger.info("Digest scheduler started successfully")
        
    except Exception as e:
        logger.error(f"Error starting digest scheduler: {e}")

def stop_scheduler():
    """Stop digest scheduler"""
    global _digest_scheduler
    
    if _digest_scheduler:
        _digest_scheduler.stop()
        _digest_scheduler = None

def register_or_update_schedule(user_id: int, cron: str, period: str) -> bool:
    """Register or update schedule"""
    scheduler = get_digest_scheduler()
    if scheduler:
        return scheduler.register_or_update_schedule(user_id, cron, period)
    return False

def remove_user_schedules(user_id: int, period: str = None) -> bool:
    """Remove user schedules"""
    scheduler = get_digest_scheduler()
    if scheduler:
        return scheduler.remove_user_schedules(user_id, period)
    return False