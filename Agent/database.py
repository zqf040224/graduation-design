import psycopg2
import sqlite3
from contextlib import contextmanager
from config import DATABASE_CONFIG

class DatabaseManager:
    def __init__(self, db_type='sqlite', db_path='./data/agent_memory.db'):
        self.db_type = db_type
        self.db_path = db_path
        self.postgres_config = DATABASE_CONFIG['postgresql']
        
    @contextmanager
    def get_connection(self):
        if self.db_type == 'postgresql':
            conn = psycopg2.connect(
                host=self.postgres_config['host'],
                port=self.postgres_config['port'],
                user=self.postgres_config['user'],
                password=self.postgres_config['password'],
                database=self.postgres_config['database']
            )
        else:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        if self.db_type == 'postgresql':
            self._init_postgresql()
        else:
            self._init_sqlite()
    
    def _init_postgresql(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建用户表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    department TEXT DEFAULT '',
                    preferred_font TEXT DEFAULT '仿宋_GB2312',
                    preferred_size TEXT DEFAULT '三号',
                    common_doc_types TEXT DEFAULT '[]',
                    writing_style TEXT DEFAULT '简洁正式',
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # 创建会话表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT DEFAULT '',
                    doc_type TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT,
                    message_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # 创建消息表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp REAL,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            ''')
            
            # 创建会话上下文表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_context (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT,
                    context_key TEXT,
                    context_value TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                    UNIQUE(session_id, context_key)
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_context_session ON session_context(session_id)')
            
            conn.commit()
    
    def _init_sqlite(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 创建用户表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    department TEXT DEFAULT '',
                    preferred_font TEXT DEFAULT '仿宋_GB2312',
                    preferred_size TEXT DEFAULT '三号',
                    common_doc_types TEXT DEFAULT '[]',
                    writing_style TEXT DEFAULT '简洁正式',
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # 创建会话表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT DEFAULT '',
                    doc_type TEXT DEFAULT '',
                    created_at TEXT,
                    updated_at TEXT,
                    message_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # 创建消息表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp REAL,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            ''')
            
            # 创建会话上下文表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS session_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    context_key TEXT,
                    context_value TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id),
                    UNIQUE(session_id, context_key)
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(is_active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_context_session ON session_context(session_id)')
            
            conn.commit()
