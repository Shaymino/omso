"""
omso 粘贴文件解析器。
负责读取粘贴文件、剥离元数据标头、提取正文、装配模型对象。
"""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .model import Conversation, Message
from .store import get_conversation, save_conversation, save_message


MAX_HEADER_LINES = 10
HEADER_KEYS = {"source", "title", "captured"}


def split_header(text: str) -> tuple[dict[str, str], str]:
    """
    从文本开头解析 YAML 风格的元数据标头。

    返回两样东西：标头字典，和切完之后的正文。
    认不出标头时返回 ({}, text)——原封不动。

    规则：
    - 从第一行开始往下扫，最多看十行
    - 遇到 ---：前面的就是标头，后面整段是正文
    - 遇到不像标头的行：立刻放弃，整个文件当正文
    - 十行还没见到 ---：一样放弃
    - "像标头"的判定用白名单——只有 source、title、captured 这三个词才算
    - 用 partition(":") 切分，别用 split(":")
      （partition 只按第一个冒号切，切不动返回空串；
       中文全角冒号 ：撞不上半角 :，是白名单之外的第二道保险）
    """
    lines = text.splitlines(keepends=True)

    header: dict[str, str] = {}

    for i, line in enumerate(lines[:MAX_HEADER_LINES]):
        # 遇到 --- 分隔符：标头结束，正文开始
        if line.strip() == "---":
            # 正文从 --- 行之后的所有行拼接
            body = "".join(lines[i + 1 :])
            return header, body

        # 1. 严格格式检查：用 partition 切分，并检查冒号是否存在
        key, sep, value = line.partition(":")
        
        # 【修改点】：如果 sep 为空，说明这行没有冒号，不是合法标头
        # 按照你的设计：立刻放弃整个标头，返回空字典和原文本
        if not sep:
            return {}, text
            
        key = key.strip()

        # 2. 白名单检查：不是已知标头键 → 立刻放弃
        if key not in HEADER_KEYS:
            return {}, text

        # 记录标头值（strip 去掉冒号后的前导空格）
        header[key] = value.strip()

    # 十行扫描完没见到 --- → 放弃
    return {}, text

def read_paste(path: Path) -> tuple[dict[str, str], str]:
    """
    读取粘贴文件并解析标头。

    使用 utf-8-sig 编码读取：
    - 如果文件有 UTF-8 BOM（记事本保存时会偷偷塞三个字节），
      utf-8-sig 会自动吃掉，避免第一行出现 \ufeff 导致白名单匹配失败。
    - 如果文件没有 BOM，行为跟 utf-8 完全一样。
    """
    text = path.read_text(encoding="utf-8-sig")
    return split_header(text)


def normalize_body(body: str) -> str:
    """
    规范化正文，用于内容哈希计算。

    规则：
    1. \r\n 和 \r 统一成 \n

    2. 每行去掉行尾空白（保留行首空格）

    3. 去掉开头和结尾的空行

    禁令：不许动行首空格——那是原文的一部分。

    返回规范化后的字符串。
    """
    # 1. 统一换行符：\r\n -> \n，然后剩余的 \r -> \n
    text = body.replace('\r\n', '\n').replace('\r', '\n')

    # 2. 每行去掉行尾空白（rstrip 只删右边，不动左边）
    lines = text.split('\n')
    lines = [line.rstrip() for line in lines]

    # 3. 去掉开头和结尾的空行
    while lines and lines[0].strip() == '':
        lines.pop(0)
    while lines and lines[-1].strip() == '':
        lines.pop()

    return '\n'.join(lines)


def compute_content_hash(normalized: str) -> str:
    """
    对规范化后的正文计算 SHA-256 哈希。

    返回 64 个十六进制字符的哈希字符串，可直接存 TEXT 列。
    """
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def parse_paste(text: str, source_hint: str = "unknown") -> tuple[Conversation, list[Message]]:
    """
    解析粘贴文本，装配为 Conversation + Message 模型对象。

    这是 ingest 流水线的最后一道工序：把散装字符串装配成模型对象。
    不写新逻辑，只做组装和决策。

    参数：
    - text: 粘贴文件的原始文本内容
    - source_hint: 从文件名推测的来源标识，标头中没有 source 时使用

    返回：
    - (Conversation, list[Message])：一条对话 + 其消息列表
      （当前只有一条 seq=0 的 unknown 角色消息）

    异常：
    - ValueError: 正文内容为空时抛出（空文件没有存储价值）
    """
    # 第1步：拆标头和正文
    header, body = split_header(text)

    # 第2步：只剥换行，不 strip 空格——行首空格是正文
    content = body.strip("\n")

    # 第3步：content 为空 → 抛 ValueError
    if not content:
        raise ValueError("paste content is empty")

    # 第4步：算内容哈希（喂 body 不是 content，normalize_body 会剥首尾空行，两者哈希一致）
    content_hash = compute_content_hash(normalize_body(body))

    # 第5步：source —— 标头里有 source 就用；没有就用 source_hint；都没有就是 "unknown"
    source = header.get("source") or source_hint or "unknown"

    # 第6步：captured_at —— 标头有 captured 就解析；解析失败或没有 → 用当前 UTC 时间
    # 模型要求时区感知（tz-aware），naive datetime 需要缝上 UTC
    captured_at_str = header.get("captured")
    if captured_at_str:
        try:
            captured_at = datetime.fromisoformat(captured_at_str)
            # naive（没写时区）→ aware（带时区）：把 UTC 缝上去
            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            captured_at = datetime.now(timezone.utc)
    else:
        captured_at = datetime.now(timezone.utc)

    # 第7步：构造 Conversation
    # title 只在标头里有才填，没有就 None
    # started_at/ended_at 填 None —— 文本里没有可靠时间，不编
    # id 由 content_hash 算出，见下
    conv_id = hashlib.sha256(f"conversation|{content_hash}".encode("utf-8")).hexdigest()
    
    conv = Conversation(
        id=conv_id,
        source=source,
        title=header.get("title"),
        started_at=None,
        ended_at=None,
        captured_at=captured_at,
        content_hash=content_hash,
    )

    # 第8步：构造 Message（seq=0, role="unknown", ts=None, content=正文）
    # Message.id 必须由调用方算好传进来，save_message 不算任何东西
    # id 基于 content_hash + seq + role 的哈希，满足"跨对话唯一且可携带"
    msg_id = hashlib.sha256(f"{content_hash}|0|unknown".encode("utf-8")).hexdigest()
    msg = Message(
        id=msg_id,
        conversation_id=conv.id,
        seq=0,
        role="unknown",
        content=content,
        ts=None,
    )

    # 第9步：返回装配好的对象
    return conv, [msg]


def ingest_file(conn, path: Path) -> tuple[Conversation, bool]:
    """
    解析单个文件并存储到数据库。

    返回: (Conversation 对象, 是否为新插入)
    - True = 新插入（Saved）
    - False = 已存在，跳过（Skipped）
    """
    # 1. 读取文件原始内容（用 utf-8-sig 处理 BOM）
    text = path.read_text(encoding="utf-8-sig")

    # 2. 解析文本，获取对话和消息
    # source_hint: 从文件名 stem 获取（如 deepseek.txt -> "deepseek"）
    conv, messages = parse_paste(text, source_hint=path.stem)

    # 3. 判重：按 content_hash 查询（conversation 表上 UNIQUE 约束的也是 content_hash）
    # 如果已存在，直接返回 False（不是新插入）
    if get_conversation(conn, conv.content_hash) is not None:
        return conv, False

    # 4. 存入数据库（先存对话，再存消息——外键要求父行先存在）
    save_conversation(conn, conv)
    for msg in messages:
        save_message(conn, msg)

    # 5. 返回 True，表示成功新插入了一条对话
    return conv, True