# omso

> 你的 AI 记忆，一个文件夹，任何工具都能读。

本地优先（Local-First）的个人 AI 记忆层：把散落在 ChatGPT、通义千问、豆包、DeepSeek 等平台的对话，抽取成**人类可读、可版本管理、可被任何 AI 工具调用**的记忆。

![status](https://img.shields.io/badge/status-alpha-orange)
![python](https://img.shields.io/badge/python-3.12%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

> ⚠️ 项目处于 Alpha 阶段（v0.1.0）。目前只完成了数据模型与本地存储的地基，命令与接口都可能变化。
>
> 早期文档中曾使用「OmniMemory」作为项目名，现统一为 `omso`。

---

## 为什么需要它

- **记忆孤岛**：你在千问、豆包、DeepSeek、ChatGPT 里的对话各自封闭，换一个平台就得重新自我介绍。
- **上下文丢失**：每次开新会话都要重复交代身份、技术栈、沟通偏好。
- **知识沉淀难**：真正有价值的结论埋在几十轮试错里，聊天记录本身不是知识。

厂商不会主动帮你把记忆带走，因为这等于帮用户流失。omso 只做这一件事：**让记忆归你所有。**

## 设计原则

1. **本地优先**：默认不依赖任何云服务，数据保存在你自己的磁盘上。
2. **可携带**：记忆是 Markdown 文件和一份 SQLite 数据库，随时能打开、diff、备份、搬走。
3. **可溯源**：每条记忆都能回到支撑它的原始对话片段，而不是 LLM 的一句"我觉得你是"。
4. **双时间维度**：长期画像（`stable`）与近期动态（`recent`）分层，事实带 `valid_from` / `valid_to`，支持"我以前用 Rust，现在用 Go"。
5. **能被用回去**：通过 MCP / 本地 HTTP 被 Cursor、Claude Code 等工具直接查询，而不是复制粘贴一段 System Prompt。

## 现在有什么

| 模块 | 状态 | 说明 |
|---|---|---|
| 数据模型 | ✅ 已完成 | `Conversation` / `Message` / `Fact` / `Evidence`，含时间、枚举、置信度校验 |
| SQLite 存储 | ✅ 已完成 | 四张表、外键级联、唯一约束与索引 |
| CLI | ✅ 基础可用 | `omso init` 初始化数据库 |
| 对话导入 | 🚧 进行中 | 目前只有底层 `save_conversation` / `get_conversation` |
| LLM 记忆抽取 | ⏳ 计划中 | 导入 → 抽取 → 渲染 `USER.md` / `MEMORY.md` |
| 语义检索 | ⏳ 计划中 | SQLite + sqlite-vec |
| MCP Server | ⏳ 计划中 | `search_memory` / `get_profile` / `remember` |

## 快速开始

要求：Python 3.12+，推荐使用 [uv](https://docs.astral.sh/uv/)。

```bash
# 在仓库根目录
uv sync

# 初始化本地数据库
uv run omso init
```

输出示例：

```text
数据库路径: C:\Users\<你>\.omso\omso.db
初始化完成
```

默认数据库路径为 `~/.omso/omso.db`，可通过环境变量 `OMSO_DB` 覆盖：

```powershell
$env:OMSO_DB = ".\local.db"; uv run omso init
```

```bash
OMSO_DB=./local.db uv run omso init
```

查看其他命令：

```bash
uv run omso --help
```

## 数据模型

原始层只追加、不修改；记忆层可演化、可合并、可失效。这样改了抽取 prompt 之后可以随时重跑并对比结果。

| 表 | 作用 | 关键约束 |
|---|---|---|
| `conversation` | 一次导入的对话 | `content_hash` 唯一，重复导入会显式报错而不是静默吞掉 |
| `message` | 对话中的单条消息 | `(conversation_id, seq)` 唯一；随对话级联删除 |
| `fact` | 抽取出的记忆事实 | `subject / predicate / value` 三元组、`confidence (0..1)`、`layer`、`status`、双时间字段 |
| `evidence` | 事实到原文的溯源 | `(fact_id, message_id)` 唯一，`quote` 保存原文片段；**一条事实至少有一条证据** |

几条硬性约束：

- 所有时间必须带时区（`AwareDatetime`），避免跨设备、跨时区的时间线错乱。
- `confidence` 必须显式赋值，没有"默认可信"。
- `layer` 只有两层：`stable`（长期画像）与 `recent`（近期动态，计划按 10–15 天窗口滚动过期）。
- `status` 流转：`pending` → `confirmed` / `rejected` / `superseded` / `conflict`。

计划中的数据目录：

```text
~/.omso/
├── omso.db        # 结构化数据（当前已有）
├── vault/         # 渲染出的 Markdown 记忆，人类可读（计划）
├── raw/           # 原始导入文件（计划）
└── config.toml    # 配置（计划）
```

## 架构

当前是一个纯 Python 进程，未来所有入口共用同一套核心逻辑：

```text
        CLI (omso ...)      MCP Server      HTTP API (:8765)
                \               |               /
                 \              |              /
                  +-------- Core (Python) --------+
                  |  ingest → extract → merge →   |
                  |  render → serve               |
                  +--------------+----------------+
                                 |
                        ~/.omso/ (SQLite + Markdown)
```

不采用「Tauri + Python sidecar」的桌面应用路线：打包体积大、工具链多、而且会让核心能力封闭在一个盒子里。先做好本地服务，桌面壳是以后的体验糖。

## Roadmap

- [x] **Phase 0 · 地基（部分）**：数据模型、SQLite schema、`omso init`
- [ ] **Phase 0 · 评测**：20–30 份真实对话 + 手写期望画像，用于衡量抽取质量
- [ ] **Phase 1 · 最小闭环**：`omso ingest`（ChatGPT 导出 / Markdown / 纯文本）→ 抽取 → `USER.md` + `MEMORY.md`；`omso diff` 查看本次记忆变更；本地模型（Ollama）与云端模型双档
- [ ] **Phase 2 · 接入**：MCP Server；`omso export --target cursor|claude|agents`
- [ ] **Phase 3 · 检索与演化**：sqlite-vec 语义检索、去重合并、冲突消解、衰减与 supersede、最简审核页面
- [ ] **Phase 4 · 采集扩展**：更多平台导出解析器；浏览器插件（只读当前页面已渲染的对话，一键保存）
- [ ] **Phase 5 · 壳与生态**：桌面薄壳、adapter 协议

## 隐私与数据流向

**omso 不收集你的账号密码，也不做自动登录或批量爬取。** 数据来源只有三种：平台官方导出文件、浏览器页面上你主动保存的内容、手动粘贴。

摘要能力分两档，由你选择，并明确标注数据流向：

| 模式 | 数据流向 | 说明 |
|---|---|---|
| **L0 · 完全离线**（默认） | 全部在本机 | 使用 Ollama / llama.cpp 本地模型，真正零上传 |
| **L1 · 混合** | 本地存储 + 你选择的模型提供商 | 仅上传待摘要的对话片段，omso 自身不经手任何数据 |

首次启用 L1 需要显式确认，并明确展示哪些内容会被发送给哪个提供商。

安全上还有两条底线：

- 导入的对话是**不可信输入**，抽取只接受结构化 schema 结果，避免对话中的指令劫持画像（记忆投毒）。
- 记忆文件会被注入到其他 AI 工具的上下文中，因此渲染时始终标注为**数据而非指令**，并支持逐条审核。

## 明确不做的事

- ❌ 账号密码托管、模拟登录、批量抓取平台数据（违反平台条款，也有安全与法律风险）
- ❌ 任务 / 日程管理（最多从记忆中抽取只读的待办视图）
- ❌ 早期做知识图谱可视化（先保证搜得准）
- ❌ 云端同步服务（L2 若要做，会是另一个产品）

## 项目结构

```text
src/omso/
├── __init__.py
├── model.py     # Pydantic 数据模型与校验
├── store.py     # SQLite 连接、DDL、对话读写
└── cli.py       # Typer 命令行入口
```


## 许可证

MIT
