"""
Database operations for digest system
"""

import sqlite3
import logging
import os
from typing import List, Dict, Optional, Tuple
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class DigestDB:
    def __init__(self, db_path: str = "digest.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Initialize database with schema"""
        try:
            # Read and execute SQL schema
            schema_path = os.path.join(os.path.dirname(__file__), "models.sql")
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
            
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript(schema_sql)
            
            logger.info(f"Database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise
    
    def get_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # User operations
    def save_user(self, user_id: int, chat_id: int, locale: str = 'ru') -> bool:
        """Save user to database"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO users (user_id, chat_id, locale) VALUES (?, ?, ?)",
                    (user_id, chat_id, locale)
                )
                return True
        except Exception as e:
            logger.error(f"Error saving user {user_id}: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                ).fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None
    
    # Channel operations
    def save_channel(self, username: str, tg_chat_id: int, title: str, added_by_user_id: int) -> Optional[int]:
        """Save channel and return channel ID"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO channels 
                       (username, tg_chat_id, title, added_by_user_id) 
                       VALUES (?, ?, ?, ?)""",
                    (username, tg_chat_id, title, added_by_user_id)
                )
                
                if cursor.rowcount == 0:
                    # Channel already exists, get its ID
                    row = conn.execute(
                        "SELECT id FROM channels WHERE username = ? OR tg_chat_id = ?",
                        (username, tg_chat_id)
                    ).fetchone()
                    return row[0] if row else None
                
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error saving channel {username}: {e}")
            return None
    
    def get_user_channels(self, user_id: int) -> List[Dict]:
        """Get all active channels for user"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """SELECT c.*, uc.is_active as user_active 
                       FROM channels c 
                       JOIN user_channels uc ON c.id = uc.channel_id 
                       WHERE uc.user_id = ? AND uc.is_active = 1 AND c.is_active = 1""",
                    (user_id,)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting user channels {user_id}: {e}")
            return []
    
    def add_user_channel(self, user_id: int, channel_id: int) -> bool:
        """Add channel to user's subscription"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO user_channels (user_id, channel_id, is_active) VALUES (?, ?, 1)",
                    (user_id, channel_id)
                )
                return True
        except Exception as e:
            logger.error(f"Error adding user channel {user_id}->{channel_id}: {e}")
            return False
    
    def remove_user_channel(self, user_id: int, channel_id: int) -> bool:
        """Remove channel from user's subscription"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE user_channels SET is_active = 0 WHERE user_id = ? AND channel_id = ?",
                    (user_id, channel_id)
                )
                return True
        except Exception as e:
            logger.error(f"Error removing user channel {user_id}->{channel_id}: {e}")
            return False
    
    def find_channel(self, identifier: str) -> Optional[Dict]:
        """Find channel by username or chat_id"""
        try:
            with self.get_connection() as conn:
                # Try as username first
                row = conn.execute(
                    "SELECT * FROM channels WHERE username = ? AND is_active = 1",
                    (identifier.lstrip('@'),)
                ).fetchone()
                
                if not row:
                    # Try as chat_id if it's numeric
                    try:
                        chat_id = int(identifier)
                        row = conn.execute(
                            "SELECT * FROM channels WHERE tg_chat_id = ? AND is_active = 1",
                            (chat_id,)
                        ).fetchone()
                    except ValueError:
                        pass
                
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error finding channel {identifier}: {e}")
            return None
    
    # Message operations
    def save_message(self, channel_id: int, tg_message_id: int, message_url: str, 
                    posted_at: int, text: str, raw_json: str) -> bool:
        """Save channel message"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO messages 
                       (channel_id, tg_message_id, message_url, posted_at, text, raw_json) 
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (channel_id, tg_message_id, message_url, posted_at, text, raw_json)
                )
                return True
        except Exception as e:
            logger.error(f"Error saving message {channel_id}/{tg_message_id}: {e}")
            return False
    
    def get_messages_in_period(self, user_id: int, from_ts: int, to_ts: int) -> List[Dict]:
        """Get all messages from user's channels in time period"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    """SELECT m.*, c.username, c.title, c.tg_chat_id 
                       FROM messages m 
                       JOIN channels c ON m.channel_id = c.id 
                       JOIN user_channels uc ON c.id = uc.channel_id 
                       WHERE uc.user_id = ? AND uc.is_active = 1 AND c.is_active = 1 
                       AND m.posted_at >= ? AND m.posted_at < ? 
                       ORDER BY m.posted_at DESC""",
                    (user_id, from_ts, to_ts)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting messages for period {user_id}: {e}")
            return []
    
    # Keyword operations
    def save_keyword(self, user_id: int, pattern: str, is_regex: bool = False) -> Optional[int]:
        """Save keyword pattern"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO keywords (user_id, pattern, is_regex, is_active) VALUES (?, ?, ?, 1)",
                    (user_id, pattern, int(is_regex))
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error saving keyword {pattern}: {e}")
            return None
    
    def get_user_keywords(self, user_id: int) -> List[Dict]:
        """Get active keywords for user"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM keywords WHERE user_id = ? AND is_active = 1",
                    (user_id,)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting keywords for {user_id}: {e}")
            return []
    
    def remove_keyword(self, user_id: int, keyword_id: int) -> bool:
        """Remove keyword"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE keywords SET is_active = 0 WHERE id = ? AND user_id = ?",
                    (keyword_id, user_id)
                )
                return True
        except Exception as e:
            logger.error(f"Error removing keyword {keyword_id}: {e}")
            return False
    
    # Alert operations
    def log_alert(self, keyword_id: int, message_id: int) -> bool:
        """Log keyword alert"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "INSERT INTO alerts_log (keyword_id, message_id, alerted_at) VALUES (?, ?, ?)",
                    (keyword_id, message_id, int(datetime.now().timestamp()))
                )
                return True
        except Exception as e:
            logger.error(f"Error logging alert {keyword_id}->{message_id}: {e}")
            return False
    
    def was_alerted(self, keyword_id: int, message_id: int) -> bool:
        """Check if alert was already sent"""
        try:
            with self.get_connection() as conn:
                row = conn.execute(
                    "SELECT 1 FROM alerts_log WHERE keyword_id = ? AND message_id = ?",
                    (keyword_id, message_id)
                ).fetchone()
                return row is not None
        except Exception as e:
            logger.error(f"Error checking alert {keyword_id}->{message_id}: {e}")
            return False
    
    # Schedule operations
    def save_schedule(self, user_id: int, cron: str, period: str) -> Optional[int]:
        """Save user schedule"""
        try:
            with self.get_connection() as conn:
                # First deactivate existing schedules for this period
                conn.execute(
                    "UPDATE schedules SET is_active = 0 WHERE user_id = ? AND period = ?",
                    (user_id, period)
                )
                
                # Add new schedule
                cursor = conn.execute(
                    "INSERT INTO schedules (user_id, cron, period, is_active) VALUES (?, ?, ?, 1)",
                    (user_id, cron, period)
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error saving schedule {user_id}/{period}: {e}")
            return None
    
    def get_user_schedules(self, user_id: int) -> List[Dict]:
        """Get active schedules for user"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM schedules WHERE user_id = ? AND is_active = 1",
                    (user_id,)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting schedules for {user_id}: {e}")
            return []
    
    def get_all_active_schedules(self) -> List[Dict]:
        """Get all active schedules"""
        try:
            with self.get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM schedules WHERE is_active = 1"
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting all schedules: {e}")
            return []
    
    def remove_user_schedules(self, user_id: int, period: str = None) -> bool:
        """Remove user schedules"""
        try:
            with self.get_connection() as conn:
                if period:
                    conn.execute(
                        "UPDATE schedules SET is_active = 0 WHERE user_id = ? AND period = ?",
                        (user_id, period)
                    )
                else:
                    conn.execute(
                        "UPDATE schedules SET is_active = 0 WHERE user_id = ?",
                        (user_id,)
                    )
                return True
        except Exception as e:
            logger.error(f"Error removing schedules {user_id}/{period}: {e}")
            return False
    
    # Digest operations
    def save_digest(self, user_id: int, period: str, from_ts: int, to_ts: int, rendered: str) -> Optional[int]:
        """Save generated digest"""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    """INSERT INTO digests (user_id, period, from_ts, to_ts, rendered, created_at) 
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, period, from_ts, to_ts, rendered, int(datetime.now().timestamp()))
                )
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error saving digest {user_id}/{period}: {e}")
            return None

# Global instance
_digest_db = None

def get_digest_db() -> DigestDB:
    """Get global digest database instance"""
    global _digest_db
    if _digest_db is None:
        _digest_db = DigestDB()
    return _digest_db

def init_digest_db(db_path: str = "digest.db"):
    """Initialize digest database"""
    global _digest_db
    _digest_db = DigestDB(db_path)
    return _digest_db