"""
Модуль для работы с базой данных PostgreSQL/SQLite
Хранение пользовательских запросов, настроек и статистики
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional, List
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Менеджер базы данных для Telegram бота (PostgreSQL/SQLite)"""
    
    def __init__(self, database_url: str = None):
        # Приоритет Railway PostgreSQL
        self.database_url = database_url or os.getenv('RAILWAY_DATABASE_URL') or os.getenv('DATABASE_URL', 'sqlite:///bot_database.db')
        self.is_postgres = self.database_url.startswith('postgresql://') or self.database_url.startswith('postgres://')
        
        if self.is_postgres:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            self.psycopg2 = psycopg2
            self.RealDictCursor = RealDictCursor
            logger.info(f"Используется PostgreSQL: {database_url[:20]}...")
        else:
            import sqlite3
            self.sqlite3 = sqlite3
            if database_url.startswith('sqlite:///'):
                self.db_path = database_url[10:]  # Убираем 'sqlite:///'
            else:
                self.db_path = database_url
            logger.info(f"Используется SQLite: {self.db_path}")
        
        self._local = threading.local()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения подключения к БД"""
        if not hasattr(self._local, 'connection'):
            if self.is_postgres:
                self._local.connection = self.psycopg2.connect(
                    self.database_url,
                    cursor_factory=self.RealDictCursor
                )
            else:
                self._local.connection = self.sqlite3.connect(
                    self.db_path, 
                    check_same_thread=False,
                    timeout=30.0
                )
                self._local.connection.row_factory = self.sqlite3.Row
        
        try:
            yield self._local.connection
        except Exception as e:
            self._local.connection.rollback()
            logger.error(f"Ошибка работы с БД: {e}")
            raise
        finally:
            self._local.connection.commit()
    
    def init_database(self):
        """Инициализация таблиц базы данных"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Таблица запросов пользователей
                if self.is_postgres:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS user_requests (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT NOT NULL,
                            username TEXT,
                            original_text_length INTEGER NOT NULL,
                            summary_length INTEGER NOT NULL,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            processing_time REAL DEFAULT 0.0,
                            method_used TEXT DEFAULT 'unknown'
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS user_requests (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            username TEXT,
                            original_text_length INTEGER NOT NULL,
                            summary_length INTEGER NOT NULL,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            processing_time REAL DEFAULT 0.0,
                            method_used TEXT DEFAULT 'unknown'
                        )
                    """)
                
                # Таблица настроек пользователей
                if self.is_postgres:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS user_settings (
                            user_id BIGINT PRIMARY KEY,
                            summary_ratio REAL DEFAULT 0.3,
                            compression_level INTEGER DEFAULT 30,
                            language_preference TEXT DEFAULT 'auto',
                            content_mode TEXT DEFAULT 'ask',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS user_settings (
                            user_id INTEGER PRIMARY KEY,
                            summary_ratio REAL DEFAULT 0.3,
                            compression_level INTEGER DEFAULT 30,
                            language_preference TEXT DEFAULT 'auto',
                            content_mode TEXT DEFAULT 'ask',
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                # Миграция: добавляем content_mode если не существует
                if self.is_postgres:
                    # В PostgreSQL используем IF NOT EXISTS (безопасно для существующих столбцов)
                    cursor.execute("""
                        ALTER TABLE user_settings
                        ADD COLUMN IF NOT EXISTS content_mode TEXT DEFAULT 'ask'
                    """)
                else:
                    # В SQLite проверяем через pragma
                    cursor.execute("PRAGMA table_info(user_settings)")
                    columns = [col[1] for col in cursor.fetchall()]
                    if 'content_mode' not in columns:
                        cursor.execute("""
                            ALTER TABLE user_settings
                            ADD COLUMN content_mode TEXT DEFAULT 'ask'
                        """)
                        logger.info("Добавлено поле content_mode в user_settings")
                
                # Таблица статистики системы
                if self.is_postgres:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS system_stats (
                            id SERIAL PRIMARY KEY,
                            stat_date DATE DEFAULT CURRENT_DATE,
                            total_requests INTEGER DEFAULT 0,
                            total_users INTEGER DEFAULT 0,
                            total_chars_processed INTEGER DEFAULT 0,
                            avg_processing_time REAL DEFAULT 0.0,
                            groq_requests INTEGER DEFAULT 0,
                            local_requests INTEGER DEFAULT 0,
                            failed_requests INTEGER DEFAULT 0
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS system_stats (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            stat_date DATE DEFAULT CURRENT_DATE,
                            total_requests INTEGER DEFAULT 0,
                            total_users INTEGER DEFAULT 0,
                            total_chars_processed INTEGER DEFAULT 0,
                            avg_processing_time REAL DEFAULT 0.0,
                            groq_requests INTEGER DEFAULT 0,
                            local_requests INTEGER DEFAULT 0,
                            failed_requests INTEGER DEFAULT 0
                        )
                    """)
                
                # Создаем таблицу для логирования изменений пользователей (только для PostgreSQL)
                if self.is_postgres:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS user_changes_log (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT NOT NULL,
                            username TEXT,
                            change_type TEXT NOT NULL,
                            old_value TEXT,
                            new_value TEXT,
                            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                
                # Индексы для оптимизации
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_requests_user_id ON user_requests(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_requests_timestamp ON user_requests(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_stats_date ON system_stats(stat_date)")
                
                if self.is_postgres:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_changes_log_user_id ON user_changes_log(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_changes_log_timestamp ON user_changes_log(timestamp)")
                
                logger.info("База данных инициализирована успешно")
                
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
            raise
    
    def save_user_request(self, user_id: int, username: str, original_length: int, 
                         summary_length: int, processing_time: float = 0.0, 
                         method_used: str = 'unknown'):
        """Сохранение запроса пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        INSERT INTO user_requests 
                        (user_id, username, original_text_length, summary_length, 
                         processing_time, method_used, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, username, original_length, summary_length, 
                          processing_time, method_used, datetime.now()))
                else:
                    cursor.execute("""
                        INSERT INTO user_requests 
                        (user_id, username, original_text_length, summary_length, 
                         processing_time, method_used, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, username, original_length, summary_length, 
                          processing_time, method_used, datetime.now()))
                
                logger.debug(f"Сохранен запрос пользователя {user_id}: {original_length} -> {summary_length} символов")
                
                # Обновляем или создаем настройки пользователя, если их нет
                self._ensure_user_settings(user_id, cursor)
                
        except Exception as e:
            logger.error(f"Ошибка сохранения запроса пользователя {user_id}: {e}")
    
    def _ensure_user_settings(self, user_id: int, cursor):
        """Убеждаемся, что у пользователя есть настройки"""
        if self.is_postgres:
            cursor.execute("SELECT 1 FROM user_settings WHERE user_id = %s", (user_id,))
        else:
            cursor.execute("SELECT 1 FROM user_settings WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            if self.is_postgres:
                cursor.execute("""
                    INSERT INTO user_settings (user_id, summary_ratio, compression_level, language_preference, content_mode)
                    VALUES (%s, 0.3, 30, 'auto', 'ask')
                """, (user_id,))
            else:
                cursor.execute("""
                    INSERT INTO user_settings (user_id, summary_ratio, compression_level, language_preference, content_mode)
                    VALUES (?, 0.3, 30, 'auto', 'ask')
                """, (user_id,))
    
    def get_user_settings(self, user_id: int) -> Dict:
        """Получение настроек пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                if self.is_postgres:
                    cursor.execute("""
                        SELECT summary_ratio, compression_level, language_preference, content_mode, created_at, updated_at
                        FROM user_settings WHERE user_id = %s
                    """, (user_id,))
                else:
                    cursor.execute("""
                        SELECT summary_ratio, compression_level, language_preference, content_mode, created_at, updated_at
                        FROM user_settings WHERE user_id = ?
                    """, (user_id,))

                row = cursor.fetchone()
                if row:
                    return {
                        'summary_ratio': row['summary_ratio'],
                        'compression_level': row['compression_level'],
                        'language_preference': row['language_preference'],
                        'content_mode': row.get('content_mode', 'ask'),
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                else:
                    # Создаем настройки по умолчанию
                    self._ensure_user_settings(user_id, cursor)
                    return {
                        'summary_ratio': 0.3,
                        'compression_level': 30,
                        'language_preference': 'auto',
                        'content_mode': 'ask',
                        'created_at': datetime.now().isoformat(),
                        'updated_at': datetime.now().isoformat()
                    }
                    
        except Exception as e:
            logger.error(f"Ошибка получения настроек пользователя {user_id}: {e}")
            return {
                'summary_ratio': 0.3,
                'compression_level': 30,
                'language_preference': 'auto',
                'content_mode': 'ask',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }

    def update_user_settings(self, user_id: int, summary_ratio: float = None,
                           compression_level: int = None, language_preference: str = None,
                           content_mode: str = None):
        """Обновление настроек пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем, есть ли настройки
                self._ensure_user_settings(user_id, cursor)
                
                update_fields = []
                params = []
                
                if summary_ratio is not None:
                    if self.is_postgres:
                        update_fields.append("summary_ratio = %s")
                    else:
                        update_fields.append("summary_ratio = ?")
                    params.append(summary_ratio)
                
                if compression_level is not None:
                    if self.is_postgres:
                        update_fields.append("compression_level = %s")
                    else:
                        update_fields.append("compression_level = ?")
                    params.append(compression_level)
                
                if language_preference is not None:
                    if self.is_postgres:
                        update_fields.append("language_preference = %s")
                    else:
                        update_fields.append("language_preference = ?")
                    params.append(language_preference)

                if content_mode is not None:
                    if self.is_postgres:
                        update_fields.append("content_mode = %s")
                    else:
                        update_fields.append("content_mode = ?")
                    params.append(content_mode)

                if update_fields:
                    if self.is_postgres:
                        update_fields.append("updated_at = %s")
                        params.append(datetime.now())
                        params.append(user_id)
                        
                        query = f"""
                            UPDATE user_settings 
                            SET {', '.join(update_fields)}
                            WHERE user_id = %s
                        """
                    else:
                        update_fields.append("updated_at = ?")
                        params.append(datetime.now())
                        params.append(user_id)
                        
                        query = f"""
                            UPDATE user_settings 
                            SET {', '.join(update_fields)}
                            WHERE user_id = ?
                        """
                    
                    cursor.execute(query, params)
                    logger.info(f"Обновлены настройки пользователя {user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка обновления настроек пользователя {user_id}: {e}")
    
    def get_user_stats(self, user_id: int) -> Dict:
        """Получение статистики пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_requests,
                            SUM(original_text_length) as total_chars,
                            SUM(summary_length) as total_summary_chars,
                            AVG(processing_time) as avg_processing_time,
                            MIN(timestamp) as first_request,
                            MAX(timestamp) as last_request
                        FROM user_requests 
                        WHERE user_id = %s
                    """, (user_id,))
                else:
                    cursor.execute("""
                        SELECT 
                            COUNT(*) as total_requests,
                            SUM(original_text_length) as total_chars,
                            SUM(summary_length) as total_summary_chars,
                            AVG(processing_time) as avg_processing_time,
                            MIN(timestamp) as first_request,
                            MAX(timestamp) as last_request
                        FROM user_requests 
                        WHERE user_id = ?
                    """, (user_id,))
                
                row = cursor.fetchone()
                if row and row['total_requests'] > 0:
                    total_chars = row['total_chars'] or 0
                    total_summary_chars = row['total_summary_chars'] or 0
                    avg_compression = (total_summary_chars / total_chars) if total_chars > 0 else 0
                    
                    return {
                        'total_requests': row['total_requests'],
                        'total_chars': total_chars,
                        'total_summary_chars': total_summary_chars,
                        'avg_compression': avg_compression,
                        'avg_processing_time': row['avg_processing_time'] or 0,
                        'first_request': row['first_request'],
                        'last_request': row['last_request']
                    }
                else:
                    return {
                        'total_requests': 0,
                        'total_chars': 0,
                        'total_summary_chars': 0,
                        'avg_compression': 0,
                        'avg_processing_time': 0,
                        'first_request': None,
                        'last_request': None
                    }
                    
        except Exception as e:
            logger.error(f"Ошибка получения статистики пользователя {user_id}: {e}")
            return {
                'total_requests': 0,
                'total_chars': 0,
                'total_summary_chars': 0,
                'avg_compression': 0,
                'avg_processing_time': 0,
                'first_request': None,
                'last_request': None
            }
    
    def get_total_stats(self) -> Dict:
        """Получение общей статистики системы"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Общая статистика
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_requests,
                        COUNT(DISTINCT user_id) as total_users,
                        SUM(original_text_length) as total_chars,
                        SUM(summary_length) as total_summary_chars,
                        AVG(processing_time) as avg_processing_time
                    FROM user_requests
                """)
                
                row = cursor.fetchone()
                
                # Статистика по методам
                cursor.execute("""
                    SELECT 
                        method_used,
                        COUNT(*) as count
                    FROM user_requests
                    GROUP BY method_used
                """)
                
                methods = dict(cursor.fetchall())
                
                return {
                    'total_requests': row['total_requests'] or 0,
                    'total_users': row['total_users'] or 0,
                    'total_chars': row['total_chars'] or 0,
                    'total_summary_chars': row['total_summary_chars'] or 0,
                    'avg_processing_time': row['avg_processing_time'] or 0,
                    'methods_used': methods
                }
                
        except Exception as e:
            logger.error(f"Ошибка получения общей статистики: {e}")
            return {
                'total_requests': 0,
                'total_users': 0,
                'total_chars': 0,
                'total_summary_chars': 0,
                'avg_processing_time': 0,
                'methods_used': {}
            }
    
    def cleanup_old_requests(self, days_to_keep: int = 90):
        """Очистка старых запросов для экономии места"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        DELETE FROM user_requests 
                        WHERE timestamp < CURRENT_TIMESTAMP - INTERVAL '%s days'
                    """, (days_to_keep,))
                else:
                    cursor.execute("""
                        DELETE FROM user_requests 
                        WHERE timestamp < datetime('now', '-{} days')
                    """.format(days_to_keep))
                
                deleted_count = cursor.rowcount
                logger.info(f"Удалено {deleted_count} старых записей (старше {days_to_keep} дней)")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых запросов: {e}")
            return 0
    
    def get_top_users(self, limit: int = 10) -> List[Dict]:
        """Получение топ пользователей по количеству запросов"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.is_postgres:
                    cursor.execute("""
                        SELECT 
                            user_id,
                            username,
                            COUNT(*) as requests_count,
                            SUM(original_text_length) as total_chars_processed,
                            AVG(processing_time) as avg_processing_time,
                            MAX(timestamp) as last_activity
                        FROM user_requests
                        GROUP BY user_id, username
                        ORDER BY requests_count DESC
                        LIMIT %s
                    """, (limit,))
                else:
                    cursor.execute("""
                        SELECT 
                            user_id,
                            username,
                            COUNT(*) as requests_count,
                            SUM(original_text_length) as total_chars_processed,
                            AVG(processing_time) as avg_processing_time,
                            MAX(timestamp) as last_activity
                        FROM user_requests
                        GROUP BY user_id, username
                        ORDER BY requests_count DESC
                        LIMIT ?
                    """, (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Ошибка получения топ пользователей: {e}")
            return []
    
    def backup_database(self, backup_path: str):
        """Создание резервной копии базы данных"""
        try:
            if not self.is_postgres:
                with self.get_connection() as conn:
                    backup_conn = self.sqlite3.connect(backup_path)
                    conn.backup(backup_conn)
                    backup_conn.close()
                    
                    logger.info(f"Резервная копия создана: {backup_path}")
                    return True
            else:
                logger.warning("Резервные копии PostgreSQL не поддерживаются этим методом")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            return False
    
    def log_user_change(self, user_id: int, username: str, change_type: str, old_value: str, new_value: str):
        """Логирование изменений пользователя (только для PostgreSQL)"""
        if not self.is_postgres:
            return
            
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_changes_log 
                    (user_id, username, change_type, old_value, new_value, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, username, change_type, old_value, new_value, datetime.now()))
                
                logger.info(f"Записано изменение для пользователя {user_id}: {change_type} {old_value} -> {new_value}")
                
        except Exception as e:
            logger.error(f"Ошибка записи изменения пользователя {user_id}: {e}")

    def update_compression_level(self, user_id: int, compression_level: int, username: str = None):
        """Обновление уровня сжатия для пользователя с логированием"""
        try:
            # Получаем старое значение для логирования
            old_settings = self.get_user_settings(user_id)
            old_compression = old_settings.get('compression_level', 30)
            
            logger.info(f"Начинаю обновление уровня сжатия для пользователя {user_id}: {old_compression}% -> {compression_level}%")
            
            # Конвертируем уровень сжатия в ratio
            summary_ratio = compression_level / 100.0
            self.update_user_settings(user_id, summary_ratio=summary_ratio, compression_level=compression_level)
            
            # Логируем изменение в Railway PostgreSQL
            if username and old_compression != compression_level:
                self.log_user_change(user_id, username, 'compression_level', str(old_compression), str(compression_level))
            
            logger.info(f"Уровень сжатия успешно обновлен для пользователя {user_id}: {compression_level}%")
            
        except Exception as e:
            logger.error(f"Ошибка обновления уровня сжатия для пользователя {user_id}: {e}")
            raise

    def close_connections(self):
        """Закрытие всех подключений к БД"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')

        logger.info("Подключения к БД закрыты")


# Алиас для обратной совместимости
Database = DatabaseManager
