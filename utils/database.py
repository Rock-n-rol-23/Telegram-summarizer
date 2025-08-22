#!/usr/bin/env python3
"""
Database utilities with PostgreSQL pool and SQLite WAL mode
"""

import logging
import os
import sqlite3
import asyncio
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from typing import Optional, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Enhanced database manager with connection pooling"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.is_postgresql = database_url.startswith('postgresql://')
        self.pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
        self.sqlite_path: Optional[str] = None
        
        if self.is_postgresql:
            self._init_postgresql_pool()
        else:
            self._init_sqlite()
    
    def _init_postgresql_pool(self):
        """Initialize PostgreSQL connection pool"""
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=10,
                dsn=self.database_url,
                cursor_factory=psycopg2.extras.RealDictCursor
            )
            logger.info("PostgreSQL connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise
    
    def _init_sqlite(self):
        """Initialize SQLite with WAL mode"""
        try:
            # Extract path from sqlite URL
            if self.database_url.startswith('sqlite:///'):
                self.sqlite_path = self.database_url[10:]  # Remove 'sqlite:///'
            else:
                self.sqlite_path = 'bot_database.db'
            
            # Enable WAL mode for better concurrency
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')
                conn.execute('PRAGMA cache_size=10000')
                conn.execute('PRAGMA temp_store=MEMORY')
                conn.commit()
            
            logger.info(f"SQLite initialized with WAL mode: {self.sqlite_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup"""
        if self.is_postgresql:
            conn = None
            try:
                conn = self.pool.getconn()
                yield conn
            finally:
                if conn:
                    self.pool.putconn(conn)
        else:
            conn = None
            try:
                conn = sqlite3.connect(
                    self.sqlite_path,
                    timeout=30.0,
                    isolation_level=None  # Autocommit mode
                )
                conn.row_factory = sqlite3.Row
                yield conn
            finally:
                if conn:
                    conn.close()
    
    def health_check(self) -> Dict[str, Any]:
        """Check database health and return status"""
        try:
            with self.get_connection() as conn:
                if self.is_postgresql:
                    with conn.cursor() as cur:
                        cur.execute('SELECT version()')
                        version = cur.fetchone()[0]
                        cur.execute('SELECT current_database()')
                        database = cur.fetchone()[0]
                else:
                    cur = conn.cursor()
                    cur.execute('SELECT sqlite_version()')
                    version = cur.fetchone()[0]
                    database = self.sqlite_path
                
                return {
                    'status': 'healthy',
                    'type': 'postgresql' if self.is_postgresql else 'sqlite',
                    'version': version,
                    'database': database,
                    'pool_status': self._get_pool_status()
                }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'type': 'postgresql' if self.is_postgresql else 'sqlite'
            }
    
    def _get_pool_status(self) -> Dict[str, int]:
        """Get connection pool status"""
        if self.is_postgresql and self.pool:
            return {
                'min_conn': self.pool.minconn,
                'max_conn': self.pool.maxconn,
                'available': len(self.pool._pool),
                'used': len(self.pool._used)
            }
        return {}
    
    def create_tables(self):
        """Create necessary database tables"""
        try:
            with self.get_connection() as conn:
                if self.is_postgresql:
                    with conn.cursor() as cur:
                        self._create_postgresql_tables(cur)
                        conn.commit()
                else:
                    cur = conn.cursor()
                    self._create_sqlite_tables(cur)
                    
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise
    
    def _create_postgresql_tables(self, cur):
        """Create PostgreSQL tables"""
        # User requests table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                request_type VARCHAR(50) NOT NULL,
                content_hash VARCHAR(64),
                processing_time REAL,
                compression_ratio REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indices separately
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_user_requests_user_id ON user_requests(user_id)''')
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_user_requests_created_at ON user_requests(created_at)''')
        
        # User settings table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id BIGINT PRIMARY KEY,
                audio_format VARCHAR(20) DEFAULT 'structured',
                audio_verbosity VARCHAR(20) DEFAULT 'normal',
                preferred_compression REAL DEFAULT 0.3,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Web cache table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS web_cache (
                url_hash VARCHAR(64) PRIMARY KEY,
                url TEXT NOT NULL,
                content TEXT,
                title TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for web cache
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_web_cache_cached_at ON web_cache(cached_at)''')
    
    def _create_sqlite_tables(self, cur):
        """Create SQLite tables"""
        # User requests table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                request_type TEXT NOT NULL,
                content_hash TEXT,
                processing_time REAL,
                compression_ratio REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_user_requests_user_id ON user_requests(user_id)''')
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_user_requests_created_at ON user_requests(created_at)''')
        
        # User settings table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                audio_format TEXT DEFAULT 'structured',
                audio_verbosity TEXT DEFAULT 'normal',
                preferred_compression REAL DEFAULT 0.3,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Web cache table
        cur.execute('''
            CREATE TABLE IF NOT EXISTS web_cache (
                url_hash TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                content TEXT,
                title TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_web_cache_cached_at ON web_cache(cached_at)''')
    
    def cleanup_old_data(self, days: int = 7):
        """Clean up old data to prevent database bloat"""
        try:
            with self.get_connection() as conn:
                if self.is_postgresql:
                    with conn.cursor() as cur:
                        # Clean old requests
                        cur.execute('''
                            DELETE FROM user_requests 
                            WHERE created_at < NOW() - INTERVAL %s DAY
                        ''', (days,))
                        
                        # Clean old cache
                        cur.execute('''
                            DELETE FROM web_cache 
                            WHERE cached_at < NOW() - INTERVAL '3 days'
                        ''')
                        conn.commit()
                else:
                    cur = conn.cursor()
                    # Clean old requests
                    cur.execute('''
                        DELETE FROM user_requests 
                        WHERE created_at < datetime('now', '-' || ? || ' days')
                    ''', (days,))
                    
                    # Clean old cache
                    cur.execute('''
                        DELETE FROM web_cache 
                        WHERE cached_at < datetime('now', '-3 days')
                    ''')
                    
            logger.info(f"Cleaned up data older than {days} days")
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
    
    def close(self):
        """Close database connections"""
        try:
            if self.is_postgresql and self.pool:
                self.pool.closeall()
                logger.info("PostgreSQL connection pool closed")
            # SQLite connections are closed automatically
        except Exception as e:
            logger.error(f"Error closing database: {e}")

# Global database instance
_global_db: Optional[DatabaseManager] = None

def get_database_manager(database_url: str = None) -> DatabaseManager:
    """Get global database manager instance"""
    global _global_db
    
    if _global_db is None:
        if database_url is None:
            database_url = os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')
        _global_db = DatabaseManager(database_url)
    
    return _global_db

def close_database():
    """Close global database manager"""
    global _global_db
    if _global_db:
        _global_db.close()
        _global_db = None