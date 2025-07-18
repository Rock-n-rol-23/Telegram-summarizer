"""
Модуль для работы с базой данных SQLite
Хранение пользовательских запросов, настроек и статистики
"""

import sqlite3
import logging
from datetime import datetime
from typing import Dict, Optional, List
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Менеджер базы данных для Telegram бота"""
    
    def __init__(self, database_url: str):
        if database_url.startswith('sqlite:///'):
            self.db_path = database_url[10:]  # Убираем 'sqlite:///'
        else:
            self.db_path = database_url
        
        self._local = threading.local()
        logger.info(f"Инициализирован DatabaseManager с БД: {self.db_path}")
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для получения подключения к БД"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                self.db_path, 
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
        
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
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id INTEGER PRIMARY KEY,
                        summary_ratio REAL DEFAULT 0.3,
                        language_preference TEXT DEFAULT 'auto',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Таблица статистики системы
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
                
                # Индексы для оптимизации
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_requests_user_id ON user_requests(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_requests_timestamp ON user_requests(timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_stats_date ON system_stats(stat_date)")
                
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
    
    def _ensure_user_settings(self, user_id: int, cursor: sqlite3.Cursor):
        """Убеждаемся, что у пользователя есть настройки"""
        cursor.execute("SELECT 1 FROM user_settings WHERE user_id = ?", (user_id,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO user_settings (user_id, summary_ratio, language_preference)
                VALUES (?, 0.3, 'auto')
            """, (user_id,))
    
    def get_user_settings(self, user_id: int) -> Dict:
        """Получение настроек пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT summary_ratio, language_preference, created_at, updated_at
                    FROM user_settings WHERE user_id = ?
                """, (user_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'summary_ratio': row['summary_ratio'],
                        'language_preference': row['language_preference'],
                        'created_at': row['created_at'],
                        'updated_at': row['updated_at']
                    }
                else:
                    # Создаем настройки по умолчанию
                    self._ensure_user_settings(user_id, cursor)
                    return {
                        'summary_ratio': 0.3,
                        'language_preference': 'auto',
                        'created_at': datetime.now().isoformat(),
                        'updated_at': datetime.now().isoformat()
                    }
                    
        except Exception as e:
            logger.error(f"Ошибка получения настроек пользователя {user_id}: {e}")
            return {
                'summary_ratio': 0.3,
                'language_preference': 'auto',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
    
    def update_user_settings(self, user_id: int, summary_ratio: float = None, 
                           language_preference: str = None):
        """Обновление настроек пользователя"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Проверяем, есть ли настройки
                self._ensure_user_settings(user_id, cursor)
                
                update_fields = []
                params = []
                
                if summary_ratio is not None:
                    update_fields.append("summary_ratio = ?")
                    params.append(summary_ratio)
                
                if language_preference is not None:
                    update_fields.append("language_preference = ?")
                    params.append(language_preference)
                
                if update_fields:
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
            with self.get_connection() as conn:
                backup_conn = sqlite3.connect(backup_path)
                conn.backup(backup_conn)
                backup_conn.close()
                
                logger.info(f"Резервная копия создана: {backup_path}")
                return True
                
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            return False
    
    def close_connections(self):
        """Закрытие всех подключений к БД"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')
        
        logger.info("Подключения к БД закрыты")
