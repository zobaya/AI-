# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指引。

## 项目概述

AI Service — 基于 FastAPI 的智能问答服务，使用 LangGraph ReAct Agent + Qwen3.5-9B（vLLM）实现知识库检索、文件解析和合金材料计算。属于更大系统的一部分：Django 后端（:8000）+ React 前端（:5173）+ 本服务（:7729）。

## 常用命令

```bash
# 启动 AI 服务
uv run python main.py

# 启动 Celery Worker（知识库文档处理）
uv run python worker.py

# 格式化与检查
uv run black .                       # 代码格式化（行宽 100）
uv run ruff check .                  # 静态检查（行宽 100）
uv run mypy .                        # 类型检查

# 测试
uv run pytest
uv run pytest tests/test_foo.py -k "test_name"   # 运行单个测试
```

Django 后端和前端在同级目录：
```bash
cd E:\AI_Project\backend && .venv/Scripts/python manage.py runserver 8000
cd E:\AI_Project\frontend && npm run dev
```

## 架构

### 双层 Agent 框架：Harness + App

```
src/
├── harness/          # 纯 Agent 框架层（禁止导入 FastAPI/HTTP 相关内容）
│   ├── factory.py    # Agent 工厂：RuntimeFeatures → 中间件链 → 编译图
│   ├── state.py      # AgentState TypedDict（所有节点共享的状态定义）
│   ├── llm.py        # LLM 客户端（流式 Tool Calling、查询改写、推荐问题）
│   ├── prompts.py    # 系统提示词动态构建
│   ├── log_writer.py # Agent 对话日志记录（JSONL 格式）
│   ├── tools/        # 动态工具注册表（BaseTool 子类：es_search、file_parse、calculate、ppt_generate）
│   ├── subgraphs/    # 子图实现（es_search、file_parse、calculate）
│   ├── middlewares/  # 横切关注点中间件（进度、死循环检测、记忆等）
│   ├── memory/       # 异步记忆系统（存储层、更新器、抽取 Prompt）
│   └── nodes/        # LangGraph 图节点（rewrite、agent、tools、maybe）
│
└── app/              # API 网关层（FastAPI 路由）
    ├── routers/chat.py   # SSE 流式对话端点、文件上传、日志 API
    └── pages/            # 测试页面（HTML）
```

**核心规则**：`src/harness/` 禁止导入 `src/app/`。Harness 是可复用的框架层，App 是 HTTP 适配层。

### Agent 图流转

```
START → rewrite → agent ⇄ tools → maybe → END
```

- **rewrite**：查询改写（no_think 模式，消解指代、补全上下文）
- **agent**：核心 LLM 推理节点，流式处理 think/output/tool_call 三种输出（状态机解析）
- **tools**：通过 ToolRegistry 查找工具并执行，经过中间件钩子（on_tool_call → execute → on_tool_result）
- **maybe**：生成对话标题和推荐问题（no_think 模式）

### 中间件链

中间件由 `factory.py` 根据 `RuntimeFeatures` 功能开关组装，执行顺序固定：

1. **ProgressMiddleware** — SSE 进度事件推送 + 工具结果截断（16K 字符）
2. **LoopDetectionMiddleware** — 总调用 ≥10 次或连续重复 ≥2 次时拦截
3. **TokenTrackerMiddleware** — Token 消耗统计（占位）
4. **MemoryMiddleware** — 对话前注入用户记忆事实，对话后异步抽取新事实（30 秒防抖）

每个中间件有 4 个钩子：`before_node`、`after_node`、`on_tool_call`、`on_tool_result`。通过 `config["configurable"]["_middlewares"]` 注入到各节点。

### 动态工具系统

工具继承 `src/harness/tools/base.py` 的 `BaseTool`，实现 `get_schema()`（返回 OpenAI Function Calling 格式）、`execute()`（异步执行）和可选的 `should_activate(context)`（条件激活）。启动时通过 `register_all_tools()` 注册到 `ToolRegistry`。三个内置工具：

| 工具 | 分组 | 子图实现 |
|------|------|----------|
| `es_search` | search | `src/harness/subgraphs/es_search/`（LangGraph 分类→检索→评估反思循环，分类体系从 Django API 拉取含 ID 的标签树，5 分钟缓存（含 ID→名称映射供进度消息显示），Django 标签 CUD 后推送清缓存；ES 存储 tag ID（integer），Agent 分类输出 `{"category_l1": int, "category_l2": [int]}`） |
| `file_parse` | parse | `src/harness/subgraphs/file_parse/`（MinIO 下载 → 格式提取器） |
| `calculate` | calculate | `src/harness/subgraphs/calculate/`（LangGraph 解析→查询→计算→回答） |
| `ppt_generate` | generate | `src/harness/tools/ppt_generate.py` + `ppt_renderer.py` + `ppt_themes.py`（LLM 规划内容 → python-pptx 渲染 5 种主题 → 上传 `generated-files` 桶 → Django Service Token 回调创建 GeneratedFile 记录 → 返回 `<!--PPT_FILE:json-->` 标记） |

### SSE 流式事件契约

`/agent/api/chat` 返回 `text/event-stream`。事件类型顺序（不可变更）：
`workflow_id` → `progress` → `think` → `output` → `title` → `maybe` → `final` → `error`

### 记忆系统

- **Django 端**：`UserMemory` 模型存储在 `chat_memory` 表，API 端点 `/api/chat/memory/`
- **ai-service 端**：`DjangoMemoryStorage` 通过 httpx 调用 Django API；`MemoryUpdater` 用 no_think 模式 LLM 从对话中抽取事实；`MemoryMiddleware` 在对话前注入记忆、对话后异步抽取
- 记忆事实通过 `build_system_prompt(memory_facts=...)` 注入到系统 Prompt 的「关于用户的长期记忆」段落

### 配置管理

所有配置项在 `core/config.py` 中通过 pydantic-settings 定义，支持 `.env` 文件或环境变量覆盖。`core/config.py` 使用基于文件位置的绝对路径加载 `.env`（`load_dotenv()` + pydantic-settings `env_file`），从任意工作目录启动均能正确读取。关键配置：

- `VLLM_BASE_URL` / `VLLM_MODEL_NAME` — LLM 服务地址和模型名
- `DJANGO_API_BASE_URL` — Django 后端地址（记忆系统调用）
- `ES_HOST` / `ES_PORT` — Elasticsearch
- `MINIO_ENDPOINT` — MinIO 对象存储
- `MINIO_GENERATED_BUCKET` — AI 生成文件桶（默认 `generated-files`）
- `MINIO_CHAT_UPLOAD_BUCKET` — 聊天上传文件桶（默认 `chat-uploads`）
- `REDIS_HOST` / `REDIS_PORT` — Redis（Celery Broker）

### 其他模块

- **`kb_service/`**：知识库管理服务（ES 索引、文档处理 Celery 任务，独立于 Agent 框架）。ES 映射中 `metadata.category_l1` 和 `metadata.category_l2` 为 `integer` 类型（存储标签 ID）。`api.py` 包含缓存失效（`POST /api/kb/internal/cache/invalidate`）和标签删除清洗（`POST /api/kb/internal/tags/cleanup`）内部端点。`migration/` 目录存放一次性数据迁移脚本。
- **`core/`**：基础设施——配置、数据库、MinIO 对象存储（`put_object()` 支持多桶：默认 `knowledge-base`，PPT 用 `generated-files`，聊天上传用 `chat-uploads`）

## Git 规范

- 提交信息使用中文
