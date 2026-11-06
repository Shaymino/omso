"""
omso 数据存储层：基于 SQL 的事实库。
负责数据库连接管理、初始化、以及核心 CRUD 操作。
"""

import os
import sqlite3
from pathlib import Path

from .model import Conversation

# 默认数据库路径：~/.omso/omso.db
DEFAULT_DB_PATH = Path.home() / ".omso" / "omso.db"


def get_db_path() -> Path:
    """获取数据库文件路径，支持通过环境变量 OMSO_DB 覆盖默认路径。"""
    return Path(os.environ.get("OMSO_DB", DEFAULT_DB_PATH))


def connect(path: Path | None = None) -> sqlite3.Connection:
    """
    打开一个数据库连接，按固定顺序完成五件事：
    1. 确定路径（默认 ~/.omso/omso.db，可被 OMSO_DB 覆盖）。
    2. 确保目录存在。
    3. 建立 sqlite3 连接。
    4. 设置 row_factory = sqlite3.Row（查询结果可按列名取值）。
    5. 开启外键检查（PRAGMA foreign_keys = ON，per-connection）。
    """
    db_path = path or get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """在已有连接上执行建表 DDL，不建目录、不开连接、不碰 PRAGMA。"""
    conn.executescript(_DDL_STATEMENTS)
    conn.commit()


def save_conversation(conn: sqlite3.Connection, conv: Conversation) -> None:
    """
    将 Conversation 模型写入数据库。

    关键设计：
    - 使用 model_dump(mode="json") 把 datetime → ISO 字符串、枚举 → 原值，
      得到的字典可直接作为 sqlite3 命名参数，避免 3.12+ 的 datetime 适配器废弃警告。
    - 使用 INSERT 而非 INSERT OR IGNORE：UNIQUE(content_hash) 被触发时抛 IntegrityError，
      暴露"导入流程忘记查重"的 bug，而不是静默吞掉。
    """
    row = conv.model_dump(mode="json")
    conn.execute(
        "INSERT INTO conversation "
        "(id, source, title, started_at, ended_at, captured_at, content_hash) "
        "VALUES (:id, :source, :title, :started_at, :ended_at, :captured_at, :content_hash)",
        row,
    )
    conn.commit()


def get_conversation(conn: sqlite3.Connection, content_hash: str) -> Conversation | None:
    """
    按 content_hash 查询对话。
    列名与 Pydantic 字段名一致，dict(row) 后直接 ** 解包即可，
    ISO 字符串会被 Pydantic 自动解析回 datetime。
    """
    row = conn.execute(
        "SELECT * FROM conversation WHERE content_hash = ?",
        (content_hash,),
    ).fetchone()
    return Conversation(**dict(row)) if row else None


# 通用 SQL DDL（SQLite 亲和性类型：TEXT / REAL / INTEGER）
_DDL_STATEMENTS = """
CREATE TABLE IF NOT EXISTS conversation (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT,
    started_at TEXT,
    ended_at TEXT,
    captured_at TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS message (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ts TEXT,
    CONSTRAINT fk_message_conversation
        FOREIGN KEY (conversation_id) REFERENCES conversation(id)
        ON DELETE CASCADE,
    CONSTRAINT uq_message_conv_seq
        UNIQUE (conversation_id, seq)
);

CREATE TABLE IF NOT EXISTS fact (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    confidence REAL NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    layer TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    fact_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    quote TEXT NOT NULL,
    CONSTRAINT fk_evidence_fact
        FOREIGN KEY (fact_id) REFERENCES fact(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_evidence_message
        FOREIGN KEY (message_id) REFERENCES message(id)
        ON DELETE CASCADE,
    CONSTRAINT uq_evidence_fact_message
        UNIQUE (fact_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_evidence_message_id
    ON evidence(message_id);

CREATE INDEX IF NOT EXISTS idx_fact_subject_predicate
    ON fact(subject, predicate);

CREATE INDEX IF NOT EXISTS idx_evidence_fact_id
    ON evidence(fact_id);
"""