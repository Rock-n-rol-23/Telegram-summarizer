PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
  user_id INTEGER PRIMARY KEY,
  chat_id INTEGER NOT NULL,
  locale TEXT DEFAULT 'ru'
);

CREATE TABLE IF NOT EXISTS channels (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT,
  tg_chat_id INTEGER,
  title TEXT,
  added_by_user_id INTEGER,
  is_active INTEGER DEFAULT 1,
  UNIQUE(username, tg_chat_id)
);

CREATE TABLE IF NOT EXISTS user_channels (
  user_id INTEGER,
  channel_id INTEGER,
  is_active INTEGER DEFAULT 1,
  PRIMARY KEY (user_id, channel_id)
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id INTEGER,
  tg_message_id INTEGER,
  message_url TEXT,
  posted_at INTEGER,
  text TEXT,
  raw_json TEXT,
  UNIQUE(channel_id, tg_message_id)
);

CREATE TABLE IF NOT EXISTS keywords (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  pattern TEXT,
  is_regex INTEGER DEFAULT 0,
  is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS alerts_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  keyword_id INTEGER,
  message_id INTEGER,
  alerted_at INTEGER
);

CREATE TABLE IF NOT EXISTS digests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  period TEXT,             -- 'hourly'|'daily'|'weekly'|'monthly'|'custom'
  from_ts INTEGER,
  to_ts INTEGER,
  rendered TEXT,
  created_at INTEGER
);

CREATE TABLE IF NOT EXISTS schedules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  cron TEXT,               -- например: "5 * * * *" для hourly @05
  period TEXT,             -- hourly/daily/weekly/monthly
  is_active INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_messages_channel_time ON messages(channel_id, posted_at);
CREATE INDEX IF NOT EXISTS idx_messages_text ON messages(id);