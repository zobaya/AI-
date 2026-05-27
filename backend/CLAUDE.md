# Backend CLAUDE.md

本文件为 Claude Code 在 Django Backend (`backend/`) 下工作时提供指引。

## 技术栈

| 依赖 | 版本 | 用途 |
|------|------|------|
| Django | 6.x | Web 框架 |
| Django REST Framework | 3.x | RESTful API |
| SimpleJWT | 5.x | JWT 认证（Access Token + Refresh Token + 黑名单） |
| django-cors-headers | 4.x | CORS 跨域 |
| mysqlclient | 2.x | MySQL 数据库驱动 |
| MinIO | 7.x | 对象存储客户端 |
| openpyxl | 3.x | Excel 导出 |
| reportlab | 4.x | PDF 生成（会话导出） |
| python-docx | 1.x | Word 文档生成（会话导出） |
| python-dotenv | 1.x | 环境变量管理 |

## 常用命令

```bash
uv run python manage.py runserver 8000           # 启动开发服务器
uv run python manage.py migrate                   # 执行数据库迁移
uv run python manage.py makemigrations            # 生成迁移文件
uv run python manage.py createsuperuser           # 创建超级用户
uv run python manage.py test                      # 运行测试
uv run python manage.py test chat.tests -k "test" # 运行单个测试模块
```

## 目录结构

```
backend/
├── mybackend/             # Django 项目配置
│   ├── settings.py        # 核心配置（MySQL/JWT/CORS/MinIO[4桶]/INSTALLED_APPS）
│   ├── urls.py            # 主路由汇总 → 各 app urls
│   └── wsgi.py
├── users/                 # 用户、部门、知识库权限模型
│   ├── models.py          # User + Department + KnowledgeBase + UserKBPermission + UserAgentPermission
│   ├── views.py           # 登录/登出/Token刷新/个人信息/头像
│   ├── serializers.py     # UserSerializer/LoginSerializer/ChangePasswordSerializer
│   ├── permissions.py     # IsSysAdmin/IsDeptAdmin/IsSameDepartmentOrSysAdmin
│   └── urls.py
├── chat/                  # 对话、消息、记忆、附件、提示词、AI生成文件
│   ├── models.py          # Conversation + Message + MessageAttachment + PromptLibrary + UserMemory + GeneratedFile
│   ├── views.py           # 会话CRUD/SSE聊天代理/反馈(toggle)/文件上传下载/记忆管理/AI文件管理/会话导出(PDF/DOCX/TXT)（会话列表支持?user_id=管理员筛选，会话详情允许管理员只读访问）
│   ├── export.py          # 会话导出生成器（reportlab PDF + python-docx DOCX + TXT 纯文本）
│   ├── auth.py            # ServiceTokenAuthentication（ai-service内部调用认证）
│   ├── serializers.py     # 各模型序列化器 + ChatSendSerializer
│   ├── urls.py
│   ├── management/commands/cleanup_generated_files.py  # 过期AI文件清理命令
│   ├── management/commands/migrate_minio_buckets.py    # MinIO 桶迁移命令
│   └── migrations/
├── knowledge/             # 知识库管理（文档/分块/标签）
│   ├── views.py           # 知识库CRUD/文档上传/分块管理/状态回调/重新处理（所有视图通过 `_check_kb_permission`/`_check_doc_permission` 校验 `UserKBPermission` 显式授权）
│   ├── urls.py
│   └── minio_client.py    # MinIO 工具类（多桶支持: knowledge-base/avatar/generated-files/chat-uploads）
├── org/                   # 组织管理（用户CRUD/部门/权限分配/批量导入/用户头像代理）
│   ├── views.py           # UserAvatarView 支持 ?token= query 认证（img src 场景）
│   │                      # KBPermissionView：dept_admin 只能分配本部门知识库权限
│   │                      # 部门删除：自动将该部门用户 department 置空（归入未分配）
│   │                      # 用户删除：DELETE /api/org/users/{id}/，校验不能删自己
│   └── urls.py
├── dashboard/             # 统计看板（概览/趋势/反馈管理/用户统计/Excel导出）
│   ├── views.py           # 反馈列表响应包含 conversation_id 字段
│   └── urls.py
├── tags/                  # 二级标签体系
│   ├── models.py          # Tag（self-referencing，max 2 levels）
│   ├── views.py           # 标签树/创建/更新删除/关联文档列表（TagDocumentsView）+ 内部注册表接口（TagRegistryInternalView，含 id 字段，`authentication_classes = []` 跳过 DRF 默认 JWT 认证，手动校验 Service Token）+ 标签 CUD 后清 AI Service 缓存 + 标签删除后 ES 清洗
│   └── urls.py
└── docs/
    └── API.md             # 完整数据表与接口文档
```

## 核心模型关系

```
Department ──1:N── User ──1:N── Conversation ──1:N── Message
     │                │                              │
     ├──1:N── KnowledgeBase          MessageAttachment
     │           │
     │           └── UserKBPermission
     └── UserAgentPermission

User ──1:N── UserMemory（长期记忆）
User ──1:N── PromptLibrary（快捷提示词）
User ──1:N── GeneratedFile ──N:1── Conversation（AI生成文件，归属校验）
Tag（二级自引用树）
```

## 认证机制

- **Access Token**：JWT，2小时有效，前端存 Zustand 内存
- **Refresh Token**：JWT，30天有效，HttpOnly Cookie（`path=/api/auth`）
- **续期**：前端 401 → 自动调用 `/api/auth/token/refresh/` → 新 Access Token
- **登出**：Refresh Token 黑名单 + 清除 Cookie
- **头像认证**：`/api/auth/avatar/` GET 通过 `?token=xxx` Query 参数认证
- **知识库图片代理**：`/api/knowledge/images/<path>` GET 通过 `?token=xxx` Query 参数认证，从 MinIO `knowledge-base` 桶取图返回
- **内部服务**：AI Service 回调用 `Service-Token` Header 或无认证接口（`status-callback/`）

## 权限隔离

| 角色 | 权限 |
|------|------|
| user | 操作自己的会话/消息/记忆 + 访问显式授权的知识库 |
| dept_admin | user + 管理本部门用户/知识库/看板 + 分配本部门 KB 权限 |
| sys_admin | 全部 + 部门/标签/用户调动 |

**知识库权限模型（仅显式授权）**：用户只能访问通过 `UserKBPermission` 表显式授权的知识库。部门成员身份不再自动授予 KB 访问权。创建知识库时自动为创建者分配权限。`dept_admin` 分配 KB 权限时只能选择本部门的知识库。`sys_admin` 不受限制。

自定义权限类在 `users/permissions.py`：`IsSysAdmin`、`IsDeptAdmin`、`IsSameDepartmentOrSysAdmin`。

## 关键业务逻辑

### SSE 聊天代理（ChatSendView）

1. 验证请求 → 获取或创建会话 → 保存用户消息
2. 根据用户 Agent 权限确定 `allowed_tools`
3. 通过 `AIServiceClient.get_allowed_kb_ids(user)` 解析知识库访问权限（仅 `UserKBPermission` 显式授权，`sys_admin` 返回 `None` 不做过滤，其他用户返回显式授权的知识库 ID 列表，无权限返回空列表），注入 `kb_ids` 到 AI Service 请求体
4. 代理到 AI Service `/agent/api/chat`（JWT 通过 URL 参数传递，`kb_ids` 通过请求体传递）
5. SSE 流式转发 AI 响应 → 解析 `token_usage` 事件 → 保存 AI 消息（含 tokens_used）

### 列表分页

以下 API 支持服务端分页（`page`/`page_size` 参数，默认 20 条/页）：
- `GET /api/knowledge/documents/` — 支持 `search`（按文件名）、`status`（completed/other）筛选
- `GET /api/org/users/` — 支持 `search`（按用户名/手机号）筛选
- `GET /api/dashboard/user-stats/` — 支持 `search`、`department_id` 筛选
- `GET /api/dashboard/feedback/` — 支持 `search`、`department_id`、`date_start`/`date_end`、`feedback` 筛选

返回格式统一为 `{ "data": [...], "total": N }` 或 `{ "documents": [...], "total": N }`。

### 日期筛选注意事项

MySQL + `USE_TZ=True` 环境下，`__date` 查找依赖 `CONVERT_TZ()` 函数，若 MySQL 未加载时区表会返回 NULL 导致筛选失效。因此日期筛选统一使用 `make_aware(datetime.strptime(...))` + `created_at__gte`/`created_at__lt` 方式，结束日期取次日零点（`<`）确保包含整个结束日期。

### 反馈 Toggle（MessageFeedbackView）

- 提交 `like`/`dislike` → 保存 feedback + feedback_detail
- 再次提交同一类型且无 `feedback_detail` → 清除 feedback=None + feedback_detail=None（取消反馈）
- 提交同一类型且携带 `feedback_detail` → 视为更新详情，不触发 toggle 取消

### 消息截断（MessageTruncateView）

- `DELETE /api/chat/conversations/<conv_id>/messages/` + body `{ from_message_id }`
- 验证用户归属后删除该会话中 `id >= from_message_id` 的所有消息（用于重新生成和编辑重发）
- `Message` 的 `on_delete=CASCADE` 自动清理 `MessageAttachment`

### 会话导出（ConversationExportView）

- `GET /api/chat/conversations/<pk>/export/?export_format=pdf|docx|txt`
- 权限：`IsAuthenticated`，所有者或管理员（dept_admin/sys_admin）可导出
- 后端实时生成文件，通过 `HttpResponse` 返回二进制流，不存储到 MinIO
- PDF 使用 `reportlab`（支持中文字体 SimHei），DOCX 使用 `python-docx`，TXT 为纯文本
- 生成逻辑在 `chat/export.py`：`generate_pdf()` / `generate_docx()` / `generate_txt()`

### 文档处理流程

1. 前端上传 → Backend 保存到 MinIO + 写 DB（status=pending）
2. Backend 触发 AI Service Celery 任务
3. AI Service 处理完成后回调 `/api/knowledge/documents/<doc_id>/status-callback/`（无认证）
4. Backend 更新文档状态

### AI 生成文件管理（PPT 等）

1. AI Service PPT 工具渲染 .pptx → 上传 MinIO → 回调 `/api/chat/files/create/`（Service Token 认证）创建 `GeneratedFile` 记录
2. 前端从 AI 回答中解析 `<!--PPT_FILE:{json}-->` 标记获取 `file_id`，渲染下载卡片
3. 下载：GET `/api/chat/files/<pk>/download/`（JWT 认证，归属校验 `user=request.user`），代理 MinIO 文件
4. 列表/删除：`GeneratedFileListView`（GET 获取用户文件，DELETE 从 MinIO + DB 删除）
5. 清理：`python manage.py cleanup_generated_files --days=30`（管理命令，删除过期文件）
6. 桶迁移：`python manage.py migrate_minio_buckets --dry-run`（预览旧桶数据迁移到新桶）

### MinIO 桶结构

| 桶名 | 内容 | 路径格式 | 配置项 |
|------|------|----------|--------|
| `knowledge-base` | 知识库文档（源文件+Markdown+图片） | `{kb_id}/{doc_id}/{filename}` | `MINIO_BUCKET` |
| `avatar` | 用户头像 | `{uuid}{ext}` | 硬编码 `"avatar"` |
| `generated-files` | AI 生成文件（PPT等） | `{uuid}.pptx` | `MINIO_GENERATED_BUCKET` |
| `chat-uploads` | 聊天临时上传文件 | `{uuid}_{filename}` | `MINIO_CHAT_UPLOAD_BUCKET` |

`GeneratedFile.minio_path` 和 `MessageAttachment.file_path_minio` 存储完整路径（`桶名/对象名`），下载/删除时通过 `split("/", 1)` 动态解析桶名。

## 代码规范

- View 使用 DRF `APIView` + `Serializer`
- 权限通过 `permission_classes` 声明
- 代理 AI Service 统一走 `_proxy()` 助手函数（`knowledge/views.py`），AI Service 返回错误时抛出 `APIException` 并转发状态码和错误信息
- 函数签名标注参数和返回类型
- 注释使用中文，标识符使用英文
- 行宽上限 100 字符

## 文档

完整数据表与接口文档见 `docs/API.md`，包含所有模型的字段定义、API 端点、请求/响应格式、权限说明。
