# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

企业级 AI 智能问答与知识管理系统，三个独立服务协同工作：

| 服务 | 技术栈 | 端口 | 职责 |
|------|--------|------|------|
| Backend | Django 6 + DRF + MySQL | 8000 | 用户认证(JWT)、数据持久化、文件管理(MinIO)、权限隔离 |
| AI Service | FastAPI + LangGraph + Qwen3.5-9B | 7729 | Agent 推理、SSE 流式对话、知识库索引、文档处理(Celery) |
| Frontend | React 19 + TypeScript + Ant Design | 5173 | 单页应用，Zustand 状态管理，SSE 流式渲染 |

基础设施：Redis(Celery Broker) + Elasticsearch(知识检索) + MinIO(对象存储，4 桶: knowledge-base/avatar/generated-files/chat-uploads)，通过 `docker-compose.yml` 启动。

## 常用命令

```bash
# Docker 基础设施
docker-compose up -d                    # 启动 Redis + ES + MinIO

# Backend (Django)
cd backend
uv run python manage.py runserver 8000
uv run python manage.py migrate
uv run python manage.py createsuperuser

# AI Service (FastAPI)
cd ai-service
uv run python main.py                   # 启动 API 服务
uv run python worker.py                 # 启动 Celery Worker（文档处理）

# Frontend (React)
cd frontend
npm run dev                             # 开发服务器
npm run build                           # 生产构建
npx tsc --noEmit                        # TypeScript 类型检查

# AI Service 代码质量
cd ai-service
uv run ruff check .                     # 静态检查
uv run pytest                           # 测试
uv run pytest tests/test_foo.py -k "test_name"  # 运行单个测试
```

## 架构

### 请求流转

```
用户 → Frontend(React) → Backend(Django) → AI Service(FastAPI) → vLLM(Qwen3.5-9B)
                                ↓                    ↓
                             MySQL              Elasticsearch
                             MinIO                 Redis
```

**对话流程**：Frontend 通过 SSE(`streamChat()`) 直接连接 AI Service 的 `/agent/api/chat`。认证 JWT 通过 URL 参数传递。知识库访问权限（`kb_ids`）由 Django `ChatSendView` 通过 `AIServiceClient.get_allowed_kb_ids(user)` 解析（仅 `UserKBPermission` 显式授权，`sys_admin` 返回 `None` 不做过滤），通过请求体传递给 AI Service，AI Service 将其注入 `AgentState`，ES 检索按 `metadata.kb_id` 过滤。

**知识库流程**：Frontend → Django(上传 MinIO + 写 DB) → AI Service(触发 Celery 文档处理) → ES 索引。

**文档处理回调**：Celery 任务完成后通过 HTTP POST 回调 Django `/api/knowledge/documents/{doc_id}/status-callback/` 更新状态，该接口无认证（内部服务间通信）。

### Django Backend 结构

```
backend/
├── mybackend/settings.py      # Django 配置（MySQL、JWT[Access 2h + Refresh 30天 Cookie+黑名单]、CORS、MinIO[4桶]）
├── mybackend/urls.py          # 路由汇总 → 各 app urls
├── users/                     # 用户、部门、知识库权限模型
├── chat/                      # 对话、消息、记忆、附件、反馈详情、AI文件下载、Prompt 模板
├── knowledge/                 # 文档 CRUD + MinIO 上传 + 代理 AI Service
├── tags/                      # 二级标签体系（标签树CRUD + 关联文档查询 + 内部注册表接口供 AI Service 拉取，`authentication_classes = []` 跳过 JWT）
├── dashboard/                 # 统计看板
└── org/                       # 组织管理（用户CRUD/部门CRUD/权限分配/批量导入/用户头像代理）
```

**核心模型关系**：
- `User`(角色: user/dept_admin/sys_admin) → `Department` → `KnowledgeBase`(kb_id 对应 ES 索引)
- `Document`(minio_path, status: pending/processing/completed/failed) → `Tag`(category_l1, category_l2)
- `Conversation` → `Message`(含 feedback 点赞/点踩 + feedback_detail 反馈详情JSON) + `MessageAttachment`
- `GeneratedFile`(file_name, minio_path, file_type, slide_count, theme) — AI 生成文件（PPT 等），归属校验 `user=request.user`
- `UserMemory` — 用户长期记忆（偏好/知识/目标/上下文，由 AI Service 异步抽取）

**权限隔离**：`IsSysAdmin`、`IsDeptAdmin`、`IsSameDepartmentOrSysAdmin` 三级权限。部门管理员只能操作本部门数据。

### AI Service Harness/App 分层

```
ai-service/
├── src/
│   ├── harness/               # 纯 Agent 框架层（禁止导入 FastAPI/HTTP）
│   │   ├── factory.py         # RuntimeFeatures → 中间件链 → LangGraph 编译图
│   │   ├── state.py           # AgentState TypedDict
│   │   ├── llm.py             # LLM 客户端（流式 Tool Calling 解析状态机）
│   │   ├── prompts.py         # 系统提示词动态构建
│   │   ├── tools/             # BaseTool 子类 → ToolRegistry 单例注册
│   │   ├── subgraphs/         # 复杂工具的 LangGraph 子图实现
│   │   ├── middlewares/       # 横切中间件（进度/死循环检测/Token/记忆）
│   │   ├── memory/            # 异步记忆（DjangoMemoryStorage + LLM 事实抽取）
│   │   └── nodes/             # 图节点：rewrite → agent ⇄ tools → maybe
│   └── app/                   # API 网关层
│       └── routers/chat.py    # SSE 流式对话、文件上传、日志 API
├── kb_service/                # 知识库索引服务（独立于 Agent 框架）
│   ├── es_store.py            # ES 索引管理（映射修复、Python 层 reindex）
│   ├── tasks.py               # Celery 文档处理任务（回调 Django 更新状态）
│   └── processing/            # DocumentOrchestrator 五层流水线
└── core/config.py             # pydantic-settings 配置（绝对路径 .env + load_dotenv，从任意目录启动均能加载）
```

**核心规则**：`src/harness/` 禁止导入 `src/app/`。Harness 是可复用框架，App 是 HTTP 适配。

**Agent 图流转**：`START → rewrite(查询改写) → agent(LLM 推理) ⇄ tools(工具执行) → maybe(标题+推荐) → END`

**中间件链**（固定顺序）：ProgressMiddleware → LoopDetectionMiddleware → TokenTrackerMiddleware → MemoryMiddleware。每个中间件有 before_node / after_node / on_tool_call / on_tool_result 四个钩子。

**内置工具**：
- `es_search` — 知识库检索（LangGraph 子图：分类→检索→评估反思循环，按 `kb_ids` 过滤 `metadata.kb_id` 实现权限隔离；分类体系从 Django API 动态拉取 `GET /api/tags/internal/registry/`，5 分钟缓存，本地 `categories.json` 作为 fallback；ES 存储 tag ID（integer），Agent 分类输出 `{"category_l1": int, "category_l2": [int]}`）
- `file_parse` — 文件解析（MinIO 下载 → 格式提取器）
- `calculate` — 合金材料计算（LangGraph 子图：解析→查询→计算→回答）
- `ppt_generate` — PPT 演示文稿生成（LLM 规划内容 → python-pptx 渲染 5 种主题 → 上传 `generated-files` 桶 → Django Service Token 回调创建 GeneratedFile 记录 → 返回 `<!--PPT_FILE:json-->` 标记 → 前端解析渲染下载卡片）

**SSE 事件契约**：`workflow_id → progress → think → output → title → maybe → token_usage → final → error`

**Token 追踪**：vLLM 流式返回 usage 信息（`stream_options: {"include_usage": true}`），agent 节点累加到 `state.token_usage`，经 SSE `token_usage` 事件传递给 Django 代理层，最终写入 `Message.tokens_used` 字段。

### 文档处理流水线（DocumentOrchestrator）

```
Parser(PDF/DOCX → Markdown)
  → Chunker(Parent-Child 分块，保留层级)
    → Enhancer(注入部门/分类元数据)
      → Vectorizer(Ollama Embedding)
        → Storage(Elasticsearch 索引)
```

**ES 映射要点**：`metadata` 内的 `kb_id`、`doc_id`、`chunk_id` 等字段必须为 `keyword` 类型（支持 term 精确查询），`category_l1` 和 `category_l2` 为 `integer` 类型（存储标签 ID，而非标签名），`content` 用 IK 分词器（如果可用）。`es_store.py` 启动时自动检测并修复映射错误（Python 层 reindex，非 ES reindex API）。

### Frontend 结构

```
frontend/src/
├── pages/                     # 页面组件
│   ├── Chat.tsx               # 主聊天界面
│   ├── Knowledge.tsx          # 知识库管理（主从分栏：左侧知识库列表+右侧文档列表）
│   ├── ChunkDetail.tsx        # 文档分块详情（面包屑+沉浸式编辑器）
│   ├── Users.tsx              # 用户管理（左侧部门导航+右侧数据网格+抽屉详情/编辑/对话历史）
│   ├── Tags.tsx               # 标签管理（主从分栏：左侧标签树+右侧详情面板）
│   ├── Feedback.tsx           # 反馈管理（卡片信息流+点击打开会话查看器）
│   ├── Dashboard.tsx          # 统计看板
│   ├── Settings.tsx           # 设置（含AI记忆导航卡片）
│   ├── AIMemory.tsx           # AI记忆管理（添加记忆+分类Tab筛选+卡片网格+删除）
│   └── Login.tsx              # 登录
├── components/
│   ├── Layout/                # AppLayout + Sidebar(永久折叠56px+底部头像Popover，无Header)
│   ├── Chat/                  # ChatSidebar(统一单容器+CSS宽度过渡动画+48px居中图标区+sidebar-text淡出+sidebar-tooltip折叠提示+搜索区域+时间分组+conv-item浅灰hover) + ChatHeader(h-11毛玻璃+居中标题+更多菜单+导出子菜单PDF/Word/TXT) + ChatMessages + ChatInput(拖拽上传覆盖层+蓝色虚线边框+链接图标提示+AI免责声明+语音输入Web Speech API[三态按钮:话筒/发送/停止]) + ChatSessionViewerDrawer(560px只读回放)
│   ├── FilterSelect.tsx       # 通用筛选下拉组件（自定义面板+阴影+圆角，替代原生select，用于Knowledge/Feedback/Dashboard）
│   └── GlobalDialogs.tsx      # Toast 通知 + 确认弹窗 + 输入弹窗（替代浏览器原生弹窗）
├── stores/                    # Zustand stores
│   ├── authStore.ts           # JWT 认证（Access Token 内存存储 + Cookie 自动续期）
│   ├── chatStore.ts           # 对话/消息/流式状态(phases: idle/rewrite/thinking/tool/answering)
│   ├── themeStore.ts          # 主题切换(亮/暗/跟随系统)
│   ├── layoutStore.ts         # ChatSidebar 折叠状态(localStorage 持久化)
│   └── uiStore.ts             # Toast 通知 + 确认弹窗 + 输入弹窗状态
├── api/                       # Axios HTTP + SSE 流式
│   ├── client.ts              # 基础 Axios 实例(JWT 拦截器 + Cookie 自动续期)
│   ├── chat.ts                # chatApi + streamChat(SSE) + getConversationsForUser(管理员) + memoryApi(用户长期记忆CRUD)
│   ├── knowledge.ts           # 知识库 API
│   └── org.ts                 # 组织管理 API（用户CRUD/部门CRUD/权限分配）
└── hooks/
    └── useChatStream.ts       # SSE 流式聊天 Hook(阶段状态机 + AbortController)
├── utils/
│   ├── markdown.ts           # marked 渲染配置（GFM + 知识库图片代理 + KaTeX 数学公式扩展）
│   └── relativeTime.ts       # 中文相对时间格式化（刚刚/X分钟前/昨天/X天前）
```

**SSE 流式模式**：`useChatStream.ts` 管理流式阶段状态，`streamChat()` 通过 `fetch + ReadableStream` 解析 SSE 事件。流式消息先用 `Date.now()` 作为临时 ID，完成后从 API 重新加载获取真实数据库 ID（用于点赞/点踩等操作）。

**反馈系统**：点击点赞/点踩按钮发送基础反馈（`like`/`dislike`），弹出 `FeedbackDetailPanel` 选择原因标签和可选文本输入。再次点击同一按钮取消反馈（后端清除 `feedback` + `feedback_detail`）。PPT 生成工具返回的 `<!--PPT_FILE:{json}-->` HTML 注释标记由 `parsePPTFileMarkers()` 解析，渲染为 `PPTDownloadCard` 下载卡片。下载通过 `downloadGeneratedFile(fileId, fileName)` GET 请求 Django `FileDownloadView`（归属校验），Settings 页面提供"我的生成文件"管理列表。

**消息重新生成与编辑**：重新生成按钮仅显示在最后一条 AI 回复上，点击后通过 `MessageTruncateView`（`DELETE /api/chat/conversations/<conv_id>/messages/`）删除最后的用户消息+AI回复，再重新发送。用户消息 hover 显示复制按钮，最新一条用户消息额外显示编辑按钮，编辑后截断该消息及后续所有消息并重新发送。前端 `Chat.tsx` 的 `handleResend` 统一处理截断+重发流程。

**会话管理员访问**：`ConversationListView` 支持 `?user_id=` 参数，管理员（dept_admin/sys_admin）可查看指定用户的会话列表。`ConversationDetailView.get()` 允许管理员只读访问任意会话（PATCH/DELETE 仍限制仅所有者操作）。反馈管理 `FeedbackListView` 响应中包含 `conversation_id` 字段，支持前端跳转到具体对话。`ConversationListView` 的 `?search=` 参数支持按标题和消息内容模糊搜索（Django `Q(title__icontains | messages__content__icontains)` + `.distinct()`）。

**表格分页**：列表表格统一使用服务端分页（`page`/`page_size`，每页 20 条），涉及文档列表(`knowledge/views.py`)、用户列表(`org/views.py`)、员工统计(`dashboard/views.py`)、反馈管理四个接口。返回格式 `{ data/documents: [...], total: N }`。前端分页栏样式统一（首页/上一页/下一页/末页 + 页码信息），表格行 hover 高亮，表头 sticky 固定（`text-sm` + `--text-secondary`）。文档启用/禁用使用滑动开关（绿色启用/红色禁用），操作列仅保留编辑和删除。

**知识库图片代理**：AI 回答中引用知识库文档图片时，前端 `markdown.ts` 自定义 `marked` image renderer 将 MinIO 路径（`knowledge-base/{kb_id}/{doc_id}/images/{filename}`）重写为 Django 代理 URL（`/api/knowledge/images/{object_path}?token={jwt}`）。后端 `KnowledgeBaseImageView` 支持 `?token=` query 参数认证，从 MinIO `knowledge-base` 桶取图返回。图片上传路径统一为 `{kb_id}/{doc_id}/images/{filename}`（不含 `source-documents/` 前缀）。

**数学公式渲染**：AI 回答中的 LaTeX 数学公式通过 KaTeX 渲染。`markdown.ts` 注册了两个 `marked` 扩展：`blockMath`（匹配 `$$...$$` 块级公式，渲染为居中 `<div class="math-block">`）和 `inlineMath`（匹配 `$...$` 行内公式）。KaTeX CSS（`katex/dist/katex.min.css`）在 `main.tsx` 全局导入。渲染失败时 fallback 为 `<code>` 显示原始 LaTeX 文本。

## 配置管理

所有配置通过环境变量或 `.env` 文件管理，关键配置项在 `ai-service/core/config.py` 和 `backend/mybackend/settings.py`：

| 配置 | 位置 | 说明 |
|------|------|------|
| `VLLM_BASE_URL` | ai-service | vLLM 推理服务地址 |
| `DJANGO_API_BASE_URL` | ai-service | Django 后端地址（记忆系统、状态回调） |
| `AI_SERVICE_BASE_URL` | backend | AI Service 地址 |
| `ES_HOST`/`ES_PORT` | ai-service | Elasticsearch |
| `MINIO_ENDPOINT` | backend + ai-service | MinIO 对象存储 |
| `MINIO_GENERATED_BUCKET` | backend + ai-service | AI 生成文件桶（默认 `generated-files`） |
| `MINIO_CHAT_UPLOAD_BUCKET` | backend + ai-service | 聊天上传文件桶（默认 `chat-uploads`） |
| `CELERY_BROKER` | ai-service | Redis Broker URL |

## 代码规范

### 通用

- 注释和文档使用中文，代码标识符（变量/函数/类名）使用英文
- 行宽上限 100 字符（AI Service 已通过 Black/Ruff 配置强制）
- 使用 UTF-8 编码，文件末尾保留一个换行符
- 禁止提交 `.env`、密钥、凭证文件

### Python（AI Service + Backend）

**格式化与检查**：AI Service 配置了 Black（格式化）+ Ruff（静态检查）+ MyPy（类型检查），行宽 100。Backend 暂无强制工具配置，但应遵循相同标准。

**类型注解**：
- 函数签名必须标注参数和返回类型
- 使用 Python 3.12+ 语法（`list[str]` 而非 `List[str]`，`str | None` 而非 `Optional[str]`）
- 复杂状态使用 `TypedDict` 或 `dataclass`（参考 `src/harness/state.py` 的 `AgentState`）

**导入顺序**（标准库 → 第三方库 → 本地模块）：
```python
import os
from typing import Any

from fastapi import APIRouter
from langgraph.graph import StateGraph

from core.config import settings
from harness.tools.base import BaseTool
```

**异步规范**：
- IO 操作（HTTP 请求、DB 查询、文件读写）使用 `async/await`
- LangGraph 节点和工具执行方法使用 `async def`
- Celery 任务（`kb_service/tasks.py`）使用同步代码，因为 Celery worker 本身是同步运行

**错误处理**：
- API 端点：捕获异常并返回合适的 HTTP 状态码
- Celery 任务：捕获异常后 `self.retry()`，最多重试 3 次
- Agent 工具：在 `execute()` 中捕获异常，返回错误信息给 LLM 而非抛出

**架构边界**：
- `src/harness/` 禁止导入 `src/app/`、FastAPI、requests 等 HTTP 层依赖
- `src/app/` 可以导入 `src/harness/`
- 工具和中间件通过基类（`BaseTool`、`AgentMiddleware`）和注册机制解耦

**Django 特有**：
- View 使用 DRF 的 `APIView` + `Serializer`
- 权限通过 `permission_classes` 声明，使用项目定义的 `IsSysAdmin` / `IsDeptAdmin`
- 代理 AI Service 的请求统一走 `_proxy()` 助手函数（`knowledge/views.py`），AI Service 返回错误时抛出 `APIException` 并转发状态码和错误信息
- 反馈 toggle 逻辑：`MessageFeedbackView` 检测重复反馈且无 `feedback_detail` 时清除记录；携带 `feedback_detail` 时视为更新详情，不触发 toggle 取消
- AI 文件管理：`GeneratedFile` 模型 + 三层接口（创建: Service Token 认证、下载: GET + 归属校验、列表/删除: JWT 认证），`FileDownloadView` 代理 MinIO 下载
- 文件清理：`python manage.py cleanup_generated_files --days=30` 管理命令
- 桶迁移：`python manage.py migrate_minio_buckets [--dry-run]` 将旧桶数据迁移到新桶

### TypeScript/React（Frontend）

**TypeScript 严格模式**：`tsconfig.json` 启用了 `strict: true`、`noUnusedLocals`、`noUnusedParameters`。所有代码必须通过 `tsc --noEmit` 检查。

**组件规范**：
- 使用函数组件 + Hooks，禁止 class 组件
- 组件 Props 使用 `interface` 定义，导出时命名如 `ChatMessagesProps`
- 事件处理函数使用 `useCallback` 包裹（避免不必要的重渲染）

**状态管理**：
- 全局状态使用 Zustand store（`stores/` 目录），每个 store 独立文件
- 服务端数据通过 API 调用获取，不缓存到 store（对话列表、消息等）
- 流式状态（SSE 阶段）由 `useChatStream` hook 管理，不放入全局 store

**API 层**：
- 所有 HTTP 请求通过 `api/client.ts` 的 Axios 实例（Access Token 存 Zustand 内存，Refresh Token 存 HttpOnly Cookie，401 自动续期）
- SSE 流式请求使用原生 `fetch + ReadableStream`（`api/chat.ts` 的 `streamChat()`）
- API 函数按领域分文件：`chat.ts`、`knowledge.ts`、`org.ts`

**样式**：
- 使用 CSS 变量（`src/index.css` 中 `:root` 定义设计令牌，含 `--divider-subtle` 极淡分割线变量）
- 支持深色模式（`[data-theme="dark"]` 变量覆盖）
- **统一顶部栏**：所有页面使用全宽顶部栏（`h-12`，`var(--surface)` 白底 + 底部边框），包含图标 + 标题 + 统计/状态文本。左右分栏页面采用 `flex-col` 外层 + 顶部栏 + `flex flex-1 overflow-hidden` 内层包裹左右分栏
- **主从布局背景规范**：所有左右分栏页面统一左侧面板 `var(--bg)`（灰底）+ 右侧内容区 `var(--surface)`（白底），涉及 Chat、Users、Tags、Knowledge
- Ant Design 组件优先，自定义样式用 CSS 变量保持一致性
- 详细设计规格见 `frontend/DESIGN.md`（字号、图标、间距、组件参数等）

**排版体系（Typography）**：
- **全局字体**：`--font-base` 定义为 `'Inter', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif`（英文在前，中文在后），通过 Google Fonts 加载 Inter（400/500/600/700）
- **字体渲染**：body 开启 `-webkit-font-smoothing: antialiased` + `-moz-osx-font-smoothing: grayscale`
- **状态标签/徽章**：使用 `.badge` 类（11px + font-weight 500 + letter-spacing 0.02em）
- **悬浮气泡/Popover**：12px 字号 + line-height 1.5 + letter-spacing 0.02em
- **统计看板大数字**：使用 Tailwind `tabular-nums` 类实现等宽数字对齐 + font-weight 700
- **聊天区域**：AI 回答 line-height 1.75，用户气泡 line-height 1.7

## 测试规范

### 现状

项目目前尚未建立完善的测试体系。AI Service 的 `pyproject.toml` 声明了 `pytest` 依赖，但暂无测试文件。

### 编写测试的要求

**新增工具（Tool）**：
- 在 `ai-service/tests/` 下创建 `test_<tool_name>.py`
- 测试 `get_schema()` 返回合法的 OpenAI Function Calling 格式
- 测试 `execute()` 的正常路径和异常路径
- Mock 外部依赖（ES、MinIO、LLM）

**新增中间件（Middleware）**：
- 测试四个钩子（`before_node`、`after_node`、`on_tool_call`、`on_tool_result`）的行为
- 验证中间件不修改 AgentState 的非法字段

**Django API 端点**：
- 使用 Django `TestCase` + DRF 的 `APIClient`
- 测试权限隔离：sys_admin 可访问所有、dept_admin 仅本部门、普通用户被拒绝
- 测试代理 AI Service 的端点（Mock `_proxy` 函数）

**前端组件**：
- 使用 Vitest + React Testing Library
- 测试用户交互（点击、输入）和渲染输出
- Mock SSE 流式响应和 API 调用

### 测试运行

```bash
# AI Service
cd ai-service && uv run pytest
cd ai-service && uv run pytest tests/test_es_search.py -k "test_schema"   # 单个测试

# Backend
cd backend && uv run python manage.py test
cd backend && uv run python manage.py test knowledge.tests -k "test_upload"

# Frontend（待配置 Vitest）
cd frontend && npx vitest run
```

## Git 规范

- 提交信息使用中文
- `.gitignore` 已排除 `.venv`、`.env`、`__pycache__`、`node_modules`、`media/` 等
- **每次功能修改后必须同步更新相关文档**：检查根目录及各子目录（backend/、frontend/、ai-service/）下的 CLAUDE.md、DESIGN.md 等文档，确保与代码逻辑一致
