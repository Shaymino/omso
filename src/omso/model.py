from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field


class FactStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"
    superseded = "superseded"
    conflict = "conflict"


class Message(BaseModel):
    # 1. 修正哈希范围：确保跨对话消息 ID 唯一且可携带
    id: str = Field(
        description="基于 conversation_content_hash、seq、role、content 的哈希，确保同一对话内序号与内容的唯一性"
    )
    conversation_id: str
    seq: int = Field(description="在对话中的顺序，从 0 开始，仅用于排序")
    role: Literal["user", "assistant", "system","unknown"] = Field(
        description="消息角色，限制为这三种，防止拼写错误"
    )
    content: str
    # 2. 外部传入时间，使用 AwareDatetime 进行校验前置
    ts: AwareDatetime | None = Field(
        default=None, description="消息发生时间"
    )


class Conversation(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="对话唯一标识，生成后不变",
    )
    source: str
    title: str | None = None
    # 2. 外部传入时间，使用 AwareDatetime 进行校验前置
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="导入时间，UTC标准时间",
    )
    content_hash: str = Field(description="用于判断是否已导入过")


class Fact(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="事实唯一标识",
    )
    # 拆成三格，支持去重、冲突检测和精确检索
    subject: str
    predicate: str
    value: str
    # 降级的原文摘要
    text: str = Field(description="原文出处的一句话摘要")
    
    status: FactStatus = FactStatus.pending
    # 去掉置信度默认值，强制调用方显式赋值
    confidence: float = Field(ge=0.0, le=1.0)
    # 双时间维度
    # 2. 外部传入时间，使用 AwareDatetime 进行校验前置
    valid_from: AwareDatetime = Field(description="事实生效时间")
    valid_to: AwareDatetime | None = Field(default=None, description="事实失效时间，为空表示至今有效")
    
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    layer: Literal["stable", "recent"] = Field(
        description="事实层级：stable(长期画像) / recent(近期动态)"
    )


class Evidence(BaseModel):
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="证据唯一标识",
    )
    fact_id: str
    message_id: str
    # 增加原文片段，确保证据的可溯源性和UI展示能力
    quote: str = Field(description="支撑该事实的原文片段")