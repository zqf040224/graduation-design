"""
团队级记忆系统 - SQLite + 内存缓存

适用场景：20人以内小团队
特性：
1. SQLite 持久化存储，无需额外部署
2. 分层记忆：用户画像 + 会话历史 + 当前上下文
3. 自动会话恢复
4. 定期清理过期数据
5. 支持并发访问
"""

import os
import json
import re
import threading
import time
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from contextlib import contextmanager
import hashlib
from database import DatabaseManager
from cache import CacheManager


@dataclass
class Message:
    """对话消息"""
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp,
            'metadata': json.dumps(self.metadata, ensure_ascii=False)
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Message':
        return cls(
            role=data['role'],
            content=data['content'],
            timestamp=data['timestamp'],
            metadata=json.loads(data.get('metadata', '{}'))
        )


@dataclass
class UserProfile:
    """用户画像（长期记忆）"""
    user_id: str
    name: str = ""
    department: str = ""  # 所在部门
    preferred_font: str = "仿宋_GB2312"  # 偏好字体
    preferred_size: str = "三号"  # 偏好字号
    common_doc_types: List[str] = field(default_factory=list)  # 常用公文类型
    writing_style: str = "简洁正式"  # 写作风格偏好
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            'user_id': self.user_id,
            'name': self.name,
            'department': self.department,
            'preferred_font': self.preferred_font,
            'preferred_size': self.preferred_size,
            'common_doc_types': json.dumps(self.common_doc_types, ensure_ascii=False),
            'writing_style': self.writing_style,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class TeamMemory:
    """
    团队级记忆系统

    存储结构：
    - users: 用户基本信息和画像
    - sessions: 会话元数据
    - messages: 消息历史
    - documents: 生成的公文草稿（可选）
    """

    def __init__(self, db_path: str = "./data/agent_memory.db", db_type: str = "sqlite"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_type = db_type

        # 初始化数据库管理器
        self.db_manager = DatabaseManager(db_type=db_type, db_path=str(db_path))
        
        # 初始化缓存管理器
        self.cache_manager = CacheManager()

        # 内存缓存（当前活跃会话）
        self._cache: Dict[str, List[Message]] = {}  # session_id -> messages
        self._user_sessions: Dict[str, str] = {}    # user_id -> active_session_id
        self._lock = threading.RLock()

        # 初始化数据库
        self.db_manager.init_database()

        # 加载活跃会话到缓存
        self._load_active_sessions()



    @contextmanager
    def _get_conn(self):
        """获取数据库连接（线程安全）"""
        with self.db_manager.get_connection() as conn:
            yield conn

    def _load_active_sessions(self):
        """加载最近的活跃会话到内存缓存"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            # 加载最近24小时内的活跃会话
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            cursor.execute('''
                SELECT session_id, user_id
                FROM sessions
                WHERE updated_at > ? AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT 50
            ''', (yesterday,))

            for row in cursor.fetchall():
                session_id = row['session_id']
                user_id = row['user_id']
                self._user_sessions[user_id] = session_id

                # 加载最近10条消息到缓存
                cursor.execute('''
                    SELECT * FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT 10
                ''', (session_id,))

                messages = []
                for msg_row in cursor.fetchall():
                    messages.append(Message.from_dict({
                        'role': msg_row['role'],
                        'content': msg_row['content'],
                        'timestamp': msg_row['timestamp'],
                        'metadata': msg_row['metadata']
                    }))

                messages.reverse()  # 按时间正序
                self._cache[session_id] = messages

    # ========== 用户管理 ==========

    def get_or_create_user(self, user_id: str, name: str = "",
                           department: str = "") -> UserProfile:
        """获取或创建用户"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if row:
                # 用户存在，返回现有数据
                return UserProfile(
                    user_id=row['user_id'],
                    name=row['name'],
                    department=row['department'],
                    preferred_font=row['preferred_font'],
                    preferred_size=row['preferred_size'],
                    common_doc_types=json.loads(row['common_doc_types']),
                    writing_style=row['writing_style'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
            else:
                # 创建新用户
                profile = UserProfile(
                    user_id=user_id,
                    name=name,
                    department=department
                )
                cursor.execute('''
                    INSERT INTO users
                    (user_id, name, department, preferred_font, preferred_size,
                     common_doc_types, writing_style, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    profile.user_id, profile.name, profile.department,
                    profile.preferred_font, profile.preferred_size,
                    json.dumps(profile.common_doc_types),
                    profile.writing_style, profile.created_at, profile.updated_at
                ))
                conn.commit()
                return profile

    def update_user_profile(self, user_id: str, updates: Dict):
        """更新用户画像"""
        allowed_fields = ['name', 'department', 'preferred_font',
                         'preferred_size', 'common_doc_types', 'writing_style']

        # 过滤字段
        updates = {k: v for k, v in updates.items() if k in allowed_fields}
        if not updates:
            return False

        # 处理列表类型字段
        if 'common_doc_types' in updates:
            updates['common_doc_types'] = json.dumps(updates['common_doc_types'], ensure_ascii=False)

        updates['updated_at'] = datetime.now().isoformat()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values()) + [user_id]

            cursor.execute(f'''
                UPDATE users SET {set_clause} WHERE user_id = ?
            ''', values)
            conn.commit()
            
            if cursor.rowcount > 0:
                # 清除缓存
                self.cache_manager.clear_user_cache(user_id)
                return True
            return False

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """获取用户画像"""
        # 先从缓存获取
        cache_key = self.cache_manager.get_user_cache_key(user_id)
        cached_profile = self.cache_manager.get(cache_key)
        if cached_profile:
            return UserProfile(**cached_profile)
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if row:
                profile = UserProfile(
                    user_id=row['user_id'],
                    name=row['name'],
                    department=row['department'],
                    preferred_font=row['preferred_font'],
                    preferred_size=row['preferred_size'],
                    common_doc_types=json.loads(row['common_doc_types']),
                    writing_style=row['writing_style'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                # 缓存用户画像
                self.cache_manager.set(cache_key, profile.to_dict())
                return profile
            return None

    # ========== 会话管理 ==========

    def create_session(self, user_id: str, title: str = "",
                       doc_type: str = "") -> str:
        """创建新会话"""
        session_id = f"{user_id}_{int(time.time())}_{hashlib.md5(os.urandom(8)).hexdigest()[:6]}"
        now = datetime.now().isoformat()

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sessions
                (session_id, user_id, title, doc_type, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            ''', (session_id, user_id, title, doc_type, now, now))
            conn.commit()

        # 更新缓存
        with self._lock:
            self._cache[session_id] = []
            self._user_sessions[user_id] = session_id

        return session_id

    def get_or_create_session(self, user_id: str, session_id: str = None) -> str:
        """获取或创建会话"""
        if session_id:
            # 验证会话是否存在且属于该用户
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT session_id FROM sessions
                    WHERE session_id = ? AND user_id = ? AND is_active = 1
                ''', (session_id, user_id))
                if cursor.fetchone():
                    with self._lock:
                        self._user_sessions[user_id] = session_id
                    return session_id

        # 检查用户是否有活跃会话
        with self._lock:
            if user_id in self._user_sessions:
                active_session = self._user_sessions[user_id]
                # 验证是否仍在数据库中
                with self._get_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT session_id FROM sessions
                        WHERE session_id = ? AND is_active = 1
                    ''', (active_session,))
                    if cursor.fetchone():
                        return active_session

        # 创建新会话
        return self.create_session(user_id)

    def get_owned_session(self, user_id: str, session_id: str) -> Optional[str]:
        """纯校验：只返回属于用户的活跃会话，不创建或切换会话。"""
        if not session_id:
            return None
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT session_id FROM sessions
                WHERE session_id = ? AND user_id = ? AND is_active = 1
            ''', (session_id, user_id))
            row = cursor.fetchone()
            return row['session_id'] if row else None

    def get_session_history(self, session_id: str, limit: int = 100) -> List[Message]:
        """获取会话历史"""
        # 先检查内存缓存
        with self._lock:
            if session_id in self._cache:
                return self._cache[session_id][-limit:]

        # 检查Redis缓存
        cache_key = self.cache_manager.get_session_cache_key(session_id)
        cached_messages = self.cache_manager.get(cache_key)
        if cached_messages:
            messages = [Message(**msg) for msg in cached_messages]
            # 更新内存缓存
            with self._lock:
                self._cache[session_id] = messages
            return messages[-limit:]

        # 从数据库加载
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (session_id, limit))

            messages = []
            for row in cursor.fetchall():
                messages.append(Message.from_dict({
                    'role': row['role'],
                    'content': row['content'],
                    'timestamp': row['timestamp'],
                    'metadata': row['metadata']
                }))

            messages.reverse()
            
            # 缓存到Redis
            if messages:
                messages_dict = [msg.to_dict() for msg in messages]
                self.cache_manager.set(cache_key, messages_dict, ttl=1800)  # 缓存30分钟
                
                # 更新内存缓存
                with self._lock:
                    self._cache[session_id] = messages
            
            return messages

    def list_user_sessions(self, user_id: str, limit: int = 10) -> List[Dict]:
        """列出用户的会话历史"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT session_id, title, doc_type, created_at, updated_at, message_count
                FROM sessions
                WHERE user_id = ? AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT ?
            ''', (user_id, limit))

            return [dict(row) for row in cursor.fetchall()]

    # ========== 消息管理 ==========

    def add_message(self, session_id: str, role: str, content: str,
                    metadata: Dict = None) -> bool:
        """添加消息"""
        message = Message(role=role, content=content, metadata=metadata or {})

        # 保存到数据库
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO messages (session_id, role, content, timestamp, metadata)
                VALUES (?, ?, ?, ?, ?)
            ''', (session_id, message.role, message.content,
                  message.timestamp, json.dumps(message.metadata)))

            # 更新会话时间，首条用户消息自动命名
            now = datetime.now().isoformat()
            if role == 'user':
                # 如果会话标题为空，用首条用户消息的前30字作为标题
                cursor.execute('''
                    UPDATE sessions
                    SET updated_at = ?, message_count = message_count + 1,
                        title = CASE WHEN title = '' OR title IS NULL
                                     THEN ? ELSE title END
                    WHERE session_id = ?
                ''', (now, content[:30], session_id))
            else:
                cursor.execute('''
                    UPDATE sessions
                    SET updated_at = ?, message_count = message_count + 1
                    WHERE session_id = ?
                ''', (now, session_id))

            conn.commit()

        # 清除缓存
        cache_key = self.cache_manager.get_session_cache_key(session_id)
        self.cache_manager.delete(cache_key)

        # 更新内存缓存
        with self._lock:
            if session_id not in self._cache:
                self._cache[session_id] = []
            self._cache[session_id].append(message)

            # 只保留最近 20 条在内存中
            if len(self._cache[session_id]) > 20:
                self._cache[session_id] = self._cache[session_id][-20:]

        return True

    def get_context_for_prompt(self, session_id: str, max_messages: int = 10) -> str:
        """获取格式化的上下文用于 Prompt"""
        messages = self.get_session_history(session_id, limit=max_messages)

        context_parts = []
        rolling_summary = self.get_context(session_id, "rolling_summary", "")
        task_state = self.get_context(session_id, "task_state", {})

        if rolling_summary:
            context_parts.append(f"【会话摘要】\n{rolling_summary}")

        if task_state:
            context_parts.append(
                "【当前任务状态】\n" +
                json.dumps(task_state, ensure_ascii=False, indent=2)[:1500]
            )

        if messages:
            context_parts.append("【最近对话】")
        for msg in messages:
            if msg.role == 'user':
                context_parts.append(f"用户：{msg.content}")
            elif msg.role == 'assistant':
                context_parts.append(f"助手：{msg.content}")

        return "\n\n".join(context_parts)

    def get_conversation_context(self, session_id: str, max_messages: int = 10) -> str:
        """获取对话上下文（用于 Agent）"""
        return self.get_context_for_prompt(session_id, max_messages)

    def update_rolling_summary(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        plan: Dict = None,
        source_filenames: List[str] = None,
    ):
        """用轻量规则维护会话摘要，保证长多轮对话不只依赖最近消息。"""
        previous = self.get_context(session_id, "rolling_summary", "") or ""
        plan = plan or {}
        source_filenames = [
            str(source).strip()
            for source in (source_filenames or [])
            if str(source).strip()
        ]

        turn_summary = {
            "user": self._compact_text(user_message, 220),
            "assistant": self._compact_text(assistant_message, 320),
            "task_type": plan.get("task_type", ""),
            "document_type": plan.get("document_type", ""),
            "sources": source_filenames[:8],
        }

        parts = []
        if previous:
            parts.append(previous)
        parts.append(
            f"- 用户需求：{turn_summary['user']}\n"
            f"  回复要点：{turn_summary['assistant']}\n"
            f"  任务：{turn_summary['task_type'] or '未标注'} / {turn_summary['document_type'] or '未标注'}"
        )
        if turn_summary["sources"]:
            parts.append(f"  来源：{'；'.join(turn_summary['sources'])}")

        summary = "\n".join(parts)
        if len(summary) > 2400:
            summary = summary[-2400:]
            first_line = summary.find("\n- 用户需求：")
            if first_line > 0:
                summary = summary[first_line + 1:]

        self.set_context(session_id, "rolling_summary", summary)
        self.set_context(session_id, "task_state", {
            "last_user_request": turn_summary["user"],
            "last_document_excerpt": self._compact_text(assistant_message, 900),
            "last_plan": plan,
            "source_filenames": source_filenames[:8],
            "updated_at": datetime.now().isoformat(),
        })

    def _compact_text(self, text: str, limit: int) -> str:
        text = re.sub(r'\s+', ' ', text or '').strip()
        return text[:limit] + ("..." if len(text) > limit else "")

    def set_context(self, session_id: str, key: str, value: Any):
        """设置会话上下文数据"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO session_context (session_id, context_key, context_value, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, context_key) DO UPDATE SET
                    context_value = excluded.context_value,
                    updated_at = excluded.updated_at
            ''', (session_id, key, json.dumps(value), datetime.now().isoformat()))
            conn.commit()

    def get_context(self, session_id: str, key: str, default=None):
        """获取会话上下文数据"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT context_value FROM session_context
                WHERE session_id = ? AND context_key = ?
            ''', (session_id, key))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return default

    def set_agent_state(self, session_id: str, agent_name: str, state: Dict):
        """保存 Agent 状态"""
        self.set_context(session_id, f"agent_state_{agent_name}", state)

    def get_agent_state(self, session_id: str, agent_name: str) -> Optional[Dict]:
        """获取 Agent 状态"""
        return self.get_context(session_id, f"agent_state_{agent_name}")

    def get_formatted_messages(self, session_id: str,
                               max_messages: int = 10) -> List[Dict]:
        """获取格式化的消息列表（用于 LLM API）"""
        messages = self.get_session_history(session_id, limit=max_messages)
        return [{"role": m.role, "content": m.content} for m in messages]

    # ========== 系统功能 ==========

    def close_session(self, session_id: str):
        """关闭会话（标记为非活跃）"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE sessions SET is_active = 0 WHERE session_id = ?
            ''', (session_id,))
            conn.commit()

        # 清理缓存
        with self._lock:
            if session_id in self._cache:
                del self._cache[session_id]
            for user_id, active_session in list(self._user_sessions.items()):
                if active_session == session_id:
                    del self._user_sessions[user_id]

    def cleanup_expired_sessions(self, days: int = 7):
        """清理过期会话（默认7天未更新）"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 标记过期会话为非活跃
            cursor.execute('''
                UPDATE sessions
                SET is_active = 0
                WHERE updated_at < ? AND is_active = 1
            ''', (cutoff,))

            expired_count = cursor.rowcount

            # 可选：真正删除旧数据（保留3个月）
            three_months_ago = (datetime.now() - timedelta(days=90)).isoformat()
            cursor.execute('''
                DELETE FROM messages
                WHERE session_id IN (
                    SELECT session_id FROM sessions
                    WHERE updated_at < ?
                )
            ''', (three_months_ago,))
            deleted_messages = cursor.rowcount

            cursor.execute('''
                DELETE FROM sessions
                WHERE updated_at < ?
            ''', (three_months_ago,))
            deleted_sessions = cursor.rowcount

            conn.commit()

            return {
                'expired_sessions': expired_count,
                'deleted_messages': deleted_messages,
                'deleted_sessions': deleted_sessions
            }

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 用户数
            cursor.execute('SELECT COUNT(*) FROM users')
            user_count = cursor.fetchone()[0]

            # 总会话数
            cursor.execute('SELECT COUNT(*) FROM sessions')
            session_count = cursor.fetchone()[0]

            # 活跃会话数
            cursor.execute('SELECT COUNT(*) FROM sessions WHERE is_active = 1')
            active_sessions = cursor.fetchone()[0]

            # 总消息数
            cursor.execute('SELECT COUNT(*) FROM messages')
            message_count = cursor.fetchone()[0]

            # 今日消息数
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute('''
                SELECT COUNT(*) FROM messages
                WHERE datetime(timestamp, 'unixepoch') LIKE ?
            ''', (f'{today}%',))
            today_messages = cursor.fetchone()[0]

            return {
                'users': user_count,
                'total_sessions': session_count,
                'active_sessions': active_sessions,
                'total_messages': message_count,
                'today_messages': today_messages,
                'cached_sessions': len(self._cache)
            }

    def export_user_data(self, user_id: str) -> Dict:
        """导出用户数据（用于备份或迁移）"""
        profile = self.get_user_profile(user_id)
        sessions = self.list_user_sessions(user_id, limit=100)

        # 获取所有会话的消息
        for session in sessions:
            session['messages'] = [
                asdict(m) for m in
                self.get_session_history(session['session_id'])
            ]

        return {
            'profile': asdict(profile) if profile else None,
            'sessions': sessions,
            'exported_at': datetime.now().isoformat()
        }


# ========== 便捷函数 ==========

# 全局实例
_memory_instance: Optional[TeamMemory] = None


def get_memory(db_path: str = "./data/agent_memory.db", db_type: str = "sqlite") -> TeamMemory:
    """获取全局记忆实例（单例模式）"""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = TeamMemory(db_path, db_type=db_type)
    return _memory_instance


# ========== 测试代码 ==========

if __name__ == "__main__":
    print("=" * 60)
    print("团队记忆系统测试")
    print("=" * 60)

    # 初始化
    memory = TeamMemory("./test_memory.db")

    # 测试用户
    user_id = "user_001"
    profile = memory.get_or_create_user(
        user_id=user_id,
        name="张三",
        department="项目管理部"
    )
    print(f"\n✓ 用户创建: {profile.name} ({profile.department})")

    # 更新用户偏好
    memory.update_user_profile(user_id, {
        'preferred_font': '黑体',
        'common_doc_types': ['会议通知', '对策建议']
    })
    print("✓ 更新用户偏好")

    # 创建会话
    session_id = memory.create_session(
        user_id=user_id,
        title="AI发展研讨会通知",
        doc_type="会议通知"
    )
    print(f"✓ 创建会话: {session_id}")

    # 添加消息
    memory.add_message(session_id, "user", "帮我写一份会议通知")
    memory.add_message(session_id, "assistant", "好的，请告诉我会议主题")
    memory.add_message(session_id, "user", "关于AI发展研讨会")
    print("✓ 添加 3 条消息")

    # 获取上下文
    context = memory.get_context_for_prompt(session_id)
    print(f"\n📋 会话上下文:")
    print(context)

    # 获取格式化消息
    messages = memory.get_formatted_messages(session_id)
    print(f"\n📨 格式化消息 ({len(messages)} 条):")
    for m in messages:
        print(f"  [{m['role']}] {m['content'][:30]}...")

    # 统计
    stats = memory.get_stats()
    print(f"\n📊 系统统计:")
    print(f"  用户数: {stats['users']}")
    print(f"  总会话: {stats['total_sessions']}")
    print(f"  活跃会话: {stats['active_sessions']}")
    print(f"  总消息: {stats['total_messages']}")

    # 清理测试数据
    print("\n🧹 清理测试数据...")
    os.remove("./test_memory.db")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
