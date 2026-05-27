# 架构概览

AI Service 采用**双层 Agent 框架**设计，将纯推理逻辑与 HTTP 传输层完全分离。

## 系统定位

```
React 前端 (:5173)  ←→  Django 后端 (:8000)  ←→  AI Service (:7729)  ←→  vLLM (Qwen3.5-9B)
                           │                        │
                           ├─ 用户认证/权限           ├─ Agent 推理
                           ├─ 会话/消息存储           ├─ 工具调用
                           └─ 记忆存储（MySQL）       └─ SSE 流式响应
```

## 双层架构：Harness + App

```
src/
├── harness/              # 纯 Agent 框架层（零 HTTP 依赖）
│   ├── factory.py        #   Agent 工厂：功能开关 → 中间件链 → 编译 LangGraph 图
│   ├── state.py          #   AgentState TypedDict（全局状态定义）
│   ├── llm.py            #   LLM 客户端（流式 Tool Calling、查询改写、推荐问题）
│   ├── prompts.py        #   系统提示词动态构建
│   ├── log_writer.py     #   对话日志记录（JSONL 格式）
│   │
│   ├── nodes/            #   LangGraph 图节点
│   │   ├── rewrite.py    #     查询改写（no_think，消解指代、补全上下文）
│   │   ├── agent.py      #     核心 LLM 推理（流式处理 think/output/tool_call）
│   │   ├── tools.py      #     工具执行节点（通过 ToolRegistry 查找并执行）
│   │   └── maybe.py      #     标题 + 推荐问题生成（no_think）
│   │
│   ├── tools/            #   动态工具注册系统
│   │   ├── base.py       #     BaseTool 抽象基类
│   │   ├── registry.py   #     ToolRegistry 全局注册表
│   │   ├── es_search.py  #     ESSearchTool → subgraphs/es_search/
│   │   ├── file_parse.py #     FileParseTool → subgraphs/file_parse/
│   │   ├── calculate.py  #     CalculateTool → subgraphs/calculate/
│   │   ├── ppt_generate.py #   PPTGenerateTool → ppt_renderer.py + ppt_themes.py
│   │   ├── ppt_renderer.py #  PPT 渲染引擎（python-pptx）
│   │   └── ppt_themes.py   #  5 种主题配色定义
│   │
│   ├── subgraphs/        #   子图实现（LangGraph StateGraph）
│   │   ├── es_search/    #     分类 → 检索 → 评估反思循环
│   │   ├── file_parse/   #     MinIO 下载 → 格式提取器
│   │   └── calculate/    #     解析 → 查询 → 计算 → 回答
│   │
│   ├── middlewares/      #   横切关注点中间件
│   │   ├── progress.py   #     SSE 进度事件推送 + 工具结果截断
│   │   ├── loop_detection.py  死循环检测（总调用≥10 或连续重复≥2）
│   │   ├── token_tracker.py   Token 消耗统计（占位）
│   │   └── memory.py     #     记忆注入 + 异步事实抽取
│   │
│   └── memory/           #   异步记忆系统
│       ├── storage.py    #     DjangoMemoryStorage（httpx 调用 Django API）
│       ├── updater.py    #     MemoryUpdater（LLM 抽取事实）
│       └── prompt.py     #     事实抽取 Prompt
│
└── app/                  # API 网关层（FastAPI）
    ├── routers/chat.py   #   SSE 流式对话、文件上传、日志 API
    └── pages/            #   测试页面（HTML）
```

**核心规则**：`src/harness/` 禁止导入 `src/app/` 或任何 FastAPI/HTTP 模块。Harness 是可复用的框架层，App 是 HTTP 适配层。

## Agent 图流转

```
START → rewrite → agent ⇄ tools → maybe → END
                      │
                      └─ 条件路由：有 tool_calls → tools 节点
                                   无 tool_calls → maybe 节点
```

### 各节点职责

| 节点 | 模式 | 职责 |
|------|------|------|
| **rewrite** | no_think | 查询改写：消解代词、补全上下文、保留意图动词 |
| **agent** | thinking | 核心 LLM 推理：流式处理三种输出（thinking/output/tool_call） |
| **tools** | — | 通过 ToolRegistry 查找工具并执行，经过中间件钩子 |
| **maybe** | no_think | 生成对话标题和 2-3 个推荐问题 |

### 条件路由

`_should_continue(state)` 判断：
- 无 `tool_calls` → 进入 `maybe` 节点
- 有 `tool_calls` 且 `tool_calls_count < 10` → 进入 `tools` 节点
- `tool_calls_count >= 10` → 强制结束（死循环防护）

## 中间件链

中间件由 `factory.py` 根据 `RuntimeFeatures` 功能开关组装，固定执行顺序：

```
ProgressMiddleware → LoopDetectionMiddleware → TokenTrackerMiddleware → MemoryMiddleware
```

每个中间件有 4 个钩子：
- `before_node(node_name, state, config)` — 节点执行前
- `after_node(node_name, state, config)` — 节点执行后
- `on_tool_call(tool_name, args, state, config)` — 工具调用前（可拦截）
- `on_tool_result(tool_name, result, state, config)` — 工具返回后（可修改结果）

通过 `config["configurable"]["_middlewares"]` 注入到各节点。

## 动态工具系统

工具继承 `BaseTool`，实现 `get_schema()`、`execute()`，可选 `should_activate(context)`。

```python
class BaseTool(ABC):
    name: str          # 工具名（如 "es_search"）
    description: str   # 工具描述（给 LLM 看）
    group: str         # 分组（search / parse / calculate）

    def get_schema(self) -> dict: ...       # OpenAI Function Calling 格式
    async def execute(self, **kwargs) -> str: ...  # 异步执行
    def should_activate(self, context) -> bool: ...  # 条件激活
```

启动时 `register_all_tools()` 注册所有工具到全局 `ToolRegistry`。

### 内置工具

| 工具 | 分组 | 激活条件 | 子图/流程 |
|------|------|----------|-----------|
| `es_search` | search | 始终激活 | 分类 → BM25+KNN 检索 → RRF 融合 → Reranker → 评估反思循环 |
| `file_parse` | parse | `minio_paths` 非空 | MinIO 下载 → 格式提取器（PDF/DOCX/XLSX/TXT/PPT） |
| `calculate` | calculate | 始终激活 | LLM 解析 → MySQL 查询 → 计算引擎 → LLM 回答 |
| `ppt_generate` | generate | 始终激活 | LLM 规划内容 → python-pptx 渲染（5种主题） → MinIO 上传 → Django 回调创建记录 → 返回 `<!--PPT_FILE:json-->` 标记 |

## SSE 流式事件契约

`/agent/api/chat` 返回 `text/event-stream`，事件类型顺序（不可变更）：

```
workflow_id → progress → think → output → title → maybe → final → error
```

| 事件 | 方向 | 说明 |
|------|------|------|
| `workflow_id` | 服务端 → 客户端 | 工作流 ID（首个事件） |
| `progress` | 双向 | 进度更新（如 "正在检索..."） |
| `think` | 服务端 → 客户端 | 思考过程（逐 Token） |
| `output` | 服务端 → 客户端 | 流式回答内容（逐 Token） |
| `title` | 服务端 → 客户端 | 对话标题 |
| `maybe` | 服务端 → 客户端 | 推荐问题列表 |
| `final` | 服务端 → 客户端 | 最终结果（含完整输出） |
| `error` | 服务端 → 客户端 | 错误信息 |

## 独立模块

### kb_service/ — 知识库管理服务

独立于 Agent 框架的文档处理流水线，通过 Celery Worker 异步执行：

```
上传文件 → MinIO → Parser → Chunker → Enhancer → Vectorizer → ES 写入
```

- `api.py` — FastAPI 路由（`/api/kb/*`）
- `tasks.py` — Celery 任务定义
- `processing/` — 处理流水线（Parser → Chunker → Enhancer → Vectorizer → Storage）

### core/ — 基础设施

- `config.py` — pydantic-settings 配置管理（支持 `.env` 和环境变量覆盖）
- `object_store.py` — MinIO 对象存储封装（`put_object()` 支持多桶参数，默认 `knowledge-base`）
- `database.py` — 数据库连接

## 配置管理

所有配置项在 `core/config.py` 中定义，支持 `.env` 文件或环境变量覆盖：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `VLLM_BASE_URL` | vLLM 服务地址 | `http://10.199.194.246:3001` |
| `VLLM_MODEL_NAME` | 模型名称 | `/models/Qwen3.5-9B` |
| `DJANGO_API_BASE_URL` | Django 后端地址 | `http://localhost:8000` |
| `ES_HOST` / `ES_PORT` | Elasticsearch | `localhost:9200` |
| `MINIO_ENDPOINT` | MinIO 对象存储 | `localhost:9000` |
| `MINIO_GENERATED_BUCKET` | AI 生成文件桶 | `generated-files` |
| `MINIO_CHAT_UPLOAD_BUCKET` | 聊天上传文件桶 | `chat-uploads` |
| `REDIS_HOST` / `REDIS_PORT` | Redis（Celery Broker） | `localhost:6379` |
| `CALC_DB_*` | 合金计算 MySQL 配置 | `localhost:3306/hejinshuju` |
