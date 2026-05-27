# Backend 数据表与接口文档

本文档记录 Django Backend 所有数据表结构、API 接口定义、请求/响应格式。

---

## 一、数据表结构

### 1.1 users 模块

#### Department（部门）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| name | CharField(100) | unique | 部门名称 |
| description | TextField | blank=True, default="" | 描述 |
| created_at | DateTimeField | auto_now_add | 创建时间 |
| updated_at | DateTimeField | auto_now | 更新时间 |

排序：`["id"]`

#### User（用户，自定义认证模型 AUTH_USER_MODEL）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| username | CharField(150) | unique | 用户名，UnicodeUsernameValidator |
| password | CharField(128) | — | 密码哈希 |
| phone | CharField(20) | unique | 手机号 |
| role | CharField(20) | choices: user/dept_admin/sys_admin, default="user" | 角色 |
| department | ForeignKey(Department) | SET_NULL, null=True, related_name="members" | 所属部门 |
| avatar | CharField(500) | blank=True, default="" | 头像路径 |
| is_staff | BooleanField | default=False | 后台管理权限 |
| is_active | BooleanField | default=True | 激活状态 |
| date_joined | DateTimeField | default=timezone.now | 注册时间 |

排序：`["id"]`

#### KnowledgeBase（知识库）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| kb_id | CharField(100) | unique | ES 知识库 ID（对应 ES 索引名） |
| name | CharField(200) | — | 知识库名称 |
| department | ForeignKey(Department) | CASCADE, related_name="knowledge_bases" | 所属部门 |
| description | TextField | blank=True, default="" | 描述 |
| created_by | ForeignKey(User) | SET_NULL, null=True, related_name="created_knowledge_bases" | 创建者 |
| is_active | BooleanField | default=True | 激活状态 |
| created_at | DateTimeField | auto_now_add | 创建时间 |
| updated_at | DateTimeField | auto_now | 更新时间 |

#### UserKBPermission（用户-知识库权限）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| user | ForeignKey(User) | CASCADE, related_name="kb_permissions" | 用户 |
| knowledge_base | ForeignKey(KnowledgeBase) | CASCADE, related_name="user_permissions" | 知识库 |
| created_at | DateTimeField | auto_now_add | 授权时间 |
| granted_by | ForeignKey(User) | SET_NULL, null=True, related_name="granted_kb_permissions" | 授权人 |

唯一约束：`("user", "knowledge_base")`

#### UserAgentPermission（用户-Agent 权限）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| user | ForeignKey(User) | CASCADE, related_name="agent_permissions" | 用户 |
| agent_name | CharField(100) | — | Agent 名称（如 default、ppt_generate） |

唯一约束：`("user", "agent_name")`

---

### 1.2 chat 模块

#### ConversationFolder（会话文件夹）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| user | ForeignKey(User) | CASCADE, related_name="chat_folders" | 用户 |
| name | CharField(100) | — | 文件夹名称 |
| sort_order | IntegerField | default=0 | 排序权重 |
| created_at | DateTimeField | auto_now_add | 创建时间 |
| updated_at | DateTimeField | auto_now | 更新时间 |

排序：`["sort_order", "-created_at"]`

#### Conversation（会话）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| user | ForeignKey(User) | CASCADE, related_name="conversations" | 用户 |
| folder | ForeignKey(ConversationFolder) | SET_NULL, null=True, related_name="conversations" | 所属文件夹 |
| title | CharField(200) | default="新对话" | 会话标题 |
| agent_name | CharField(100) | blank=True, default="" | Agent 标识 |
| is_pinned | BooleanField | default=False | 是否置顶 |
| created_at | DateTimeField | auto_now_add | 创建时间 |
| updated_at | DateTimeField | auto_now | 更新时间 |

排序：`["-is_pinned", "-updated_at"]`

#### Message（消息）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| conversation | ForeignKey(Conversation) | CASCADE, related_name="messages" | 所属会话 |
| role | CharField(20) | choices: user/assistant | 角色 |
| content | TextField | — | 消息内容 |
| workflow_id | CharField(100) | blank=True, default="" | LangGraph 执行 ID |
| metadata_json | JSONField | default=dict | Agent 执行轨迹（entries 数组） |
| tokens_used | IntegerField | default=0 | Token 消耗 |
| feedback | CharField(10) | null=True, choices: like/dislike | 反馈类型 |
| feedback_detail | JSONField | null=True, blank=True | 反馈详情 `{"reasons": [], "comment": ""}` |
| created_at | DateTimeField | auto_now_add | 创建时间 |

排序：`["created_at"]`

#### MessageAttachment（消息附件）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| message | ForeignKey(Message) | CASCADE, related_name="attachments" | 所属消息 |
| file_name | CharField(500) | — | 原始文件名 |
| file_path_minio | CharField(500) | — | MinIO 存储路径 |
| file_size | IntegerField | default=0 | 文件大小（字节） |
| content_type | CharField(100) | blank=True, default="" | MIME 类型 |
| created_at | DateTimeField | auto_now_add | 上传时间 |

#### PromptLibrary（快捷提示词）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| owner | ForeignKey(User) | CASCADE, null=True, related_name="prompts" | 所有者（null=系统预设） |
| title | CharField(200) | — | 标题 |
| content | TextField | — | 提示词内容 |
| is_system | BooleanField | default=False | 是否系统预设 |
| created_at | DateTimeField | auto_now_add | 创建时间 |
| updated_at | DateTimeField | auto_now | 更新时间 |

排序：`["-is_system", "-created_at"]`

#### GeneratedFile（AI 生成文件，表名 chat_generated_file）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| user | ForeignKey(User) | CASCADE, related_name="generated_files" | 所属用户 |
| conversation | ForeignKey(Conversation) | SET_NULL, null=True, related_name="generated_files" | 关联会话 |
| message | ForeignKey(Message) | SET_NULL, null=True, related_name="generated_files" | 关联消息 |
| file_name | CharField(500) | — | 文件名 |
| minio_path | CharField(500) | — | MinIO 存储路径 |
| file_size | IntegerField | default=0 | 文件大小（字节） |
| file_type | CharField(20) | choices: pptx/pdf/xlsx/other, default="pptx" | 文件类型 |
| slide_count | IntegerField | default=0 | 幻灯片页数（PPT 特有） |
| theme | CharField(50) | blank=True, default="" | 主题风格 |
| expires_at | DateTimeField | null=True, blank=True | 过期时间（空=不过期） |
| created_at | DateTimeField | auto_now_add | 创建时间 |

索引：`(user, -created_at)` 名称 `idx_genfile_user_created`

排序：`["-created_at"]`

#### UserMemory（用户长期记忆，表名 chat_memory）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| user | ForeignKey(User) | CASCADE, related_name="memories" | 用户 |
| agent_name | CharField(100) | default="default" | Agent 标识 |
| fact | TextField | — | 事实内容 |
| category | CharField(50) | choices: preference/knowledge/goal/context | 分类 |
| confidence | FloatField | default=0.5 | 置信度 |
| source_conv_id | IntegerField | null=True | 来源会话 ID |
| created_at | DateTimeField | auto_now_add | 创建时间 |
| updated_at | DateTimeField | auto_now | 更新时间 |
| access_count | IntegerField | default=0 | 被使用次数 |

索引：
- `idx_memory_user_conf`: (user, agent_name, -confidence)
- `idx_memory_user_cat`: (user, category)

---

### 1.3 tags 模块

#### Tag（标签，二级树结构）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | AutoField | PK | 自增主键 |
| name | CharField(100) | — | 标签名称 |
| description | TextField | blank=True, default="" | 描述 |
| parent | ForeignKey("self") | CASCADE, null=True, related_name="children" | 父级标签 |
| level | PositiveSmallIntegerField | default=1 | 层级（1 或 2） |
| sort_order | IntegerField | default=0 | 排序序号 |
| created_by | ForeignKey(User) | SET_NULL, null=True, related_name="created_tags" | 创建人 |
| created_at | DateTimeField | auto_now_add | 创建时间 |
| updated_at | DateTimeField | auto_now | 更新时间 |

唯一约束：`("parent", "name")`，排序：`["sort_order", "id"]`

约束：最多两级，parent 必须是 level=1 的标签。

---

## 二、ER 关系图

```
Department ──1:N── User ──1:N── Conversation ──1:N── Message
     │                │                              │
     │                ├── ConversationFolder ──1:N──┘
     │                │                              │
     ├──1:N── KnowledgeBase          MessageAttachment
     │                │
     │                └── UserKBPermission ──N:1──┘
     │
     └── UserAgentPermission

User ──1:N── UserMemory
User ──1:N── PromptLibrary
User ──1:N── GeneratedFile ──N:1── Conversation
Tag (self-referencing, max 2 levels)
```

---

## 三、API 接口

### 3.1 认证模块 `/api/auth/`

#### POST `/api/auth/login/` — 登录

| 项 | 说明 |
|---|------|
| 认证 | AllowAny |
| 请求 | `{"username": "xxx", "password": "xxx"}` |
| 响应 | `{"access": "token", "user": {"id", "username", "phone", "role", "department": {"id","name"}, "avatar"}}` |
| 副作用 | Refresh Token 写入 HttpOnly Cookie（`path=/api/auth`，30天） |

#### POST `/api/auth/token/refresh/` — Token 续期

| 项 | 说明 |
|---|------|
| 认证 | AllowAny（Cookie 自动带） |
| 请求 | 无（Cookie 中的 refresh_token） |
| 响应 | `{"access": "new_token"}` |
| 副作用 | 旧 Refresh Token 黑名单，新 Cookie 写入 |

#### POST `/api/auth/logout/` — 登出

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 响应 | `{"message": "已退出登录"}` |
| 副作用 | Refresh Token 黑名单 + 清除 Cookie |

#### GET `/api/auth/profile/` — 获取当前用户信息

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 响应 | `{"id", "username", "phone", "role", "department", "avatar", "date_joined"}` |

#### PUT `/api/auth/profile/` — 修改个人信息

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 请求 | `{"username": "xxx", "phone": "xxx"}` |
| 响应 | 更新后的用户信息 |

#### POST `/api/auth/change-password/` — 修改密码

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 请求 | `{"old_password": "xxx", "new_password": "xxx"}`（min_length=6） |
| 响应 | `{"message": "密码修改成功"}` |

#### GET `/api/auth/avatar/` — 获取头像图片

| 项 | 说明 |
|---|------|
| 认证 | AllowAny（`?token=xxx` Query 参数认证） |
| 响应 | 图片二进制流 |

#### POST `/api/auth/avatar/` — 上传头像

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 请求 | FormData: `avatar` 文件 |
| 响应 | `{"avatar": "url"}` |

#### DELETE `/api/auth/avatar/` — 删除头像

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 响应 | `{"message": "头像已删除"}` |

---

### 3.2 聊天模块 `/api/chat/`

#### GET/POST `/api/chat/folders/` — 文件夹列表/创建

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| GET 响应 | `[{"id", "name", "sort_order", "conversation_count", "created_at", "updated_at"}]` |
| POST 请求 | `{"name": "xxx", "sort_order": 0}` |

#### PUT/DELETE `/api/chat/folders/<id>/` — 文件夹更新/删除

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| PUT 请求 | `{"name": "xxx", "sort_order": 0}` |

#### GET/POST `/api/chat/conversations/` — 会话列表/创建

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| GET 参数 | `?folder_id=1&search=关键词` |
| GET 响应 | `[{"id", "title", "folder", "is_pinned", "message_count", "created_at", "updated_at"}]` |
| POST 请求 | `{"title": "xxx", "folder_id": 1}` |

#### GET/PATCH/DELETE `/api/chat/conversations/<id>/` — 会话详情/更新/删除

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| GET 响应 | `{"id", "title", "folder", "is_pinned", "messages": [...], "created_at", "updated_at"}` |
| PATCH 请求 | `{"title": "xxx", "folder_id": 1, "is_pinned": true}` |

#### POST `/api/chat/send/` — SSE 流式聊天

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 请求 | `{"query": "xxx", "conversation_id": 1, "file_paths": [], "file_names": [], "allowed_tools": []}` |
| 响应 | `text/event-stream`，Header `Conversation-Id` |
| 逻辑 | 保存用户消息 → 代理到 AI Service → SSE 流式转发响应 → 保存 AI 消息 |

**SSE 事件顺序**：`workflow_id → progress → think → output → title → maybe → token_usage → final → error`

#### POST `/api/chat/upload/` — 文件上传

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 请求 | FormData: `files`（多文件） |
| 响应 | `{"paths": ["minio/path1"], "names": ["file1.pdf"]}` |
| 逻辑 | 上传到 MinIO，返回路径供 `send` 接口使用 |

#### POST `/api/chat/messages/<id>/feedback/` — 消息反馈

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 请求 | `{"feedback": "like"/"dislike", "feedback_detail": {"reasons": [...], "comment": "..."}}` |
| 响应 | `{"message": "反馈已记录"}` / `{"message": "反馈已取消"}` |
| 逻辑 | Toggle 机制：再次提交同一类型 → 清除 feedback + feedback_detail |

#### GET/POST `/api/chat/prompts/` — 提示词列表/创建

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| GET 响应 | `[{"id", "title", "content", "is_system", "created_at", "updated_at"}]` |
| POST 请求 | `{"title": "xxx", "content": "xxx"}` |

#### PUT/DELETE `/api/chat/prompts/<id>/` — 提示词更新/删除

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| PUT 请求 | `{"title": "xxx", "content": "xxx"}` |

#### GET `/api/chat/memory/` — 获取用户记忆

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated（JWT 或服务令牌） |
| GET 参数 | `?limit=50&agent_name=default` |
| 响应 | `{"facts": [{"id", "fact", "category", "confidence", "source_conv_id", "access_count"}]}` |
| 逻辑 | 按置信度降序返回，AI Service 调用时使用 |

#### POST/DELETE `/api/chat/memory/batch/` — 批量写入/删除记忆

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| POST 请求 | `{"agent_name": "default", "conversation_id": 1, "facts": [{"fact": "...", "category": "...", "confidence": 0.8}]}` |
| DELETE 请求 | `{"ids": [1, 2, 3]}` |

#### GET/PUT/DELETE `/api/chat/memory/<id>/` — 单条记忆 CRUD

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |

#### GET `/api/chat/files/` — AI 生成文件列表

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| GET 参数 | `?file_type=pptx`（可选，按类型过滤） |
| 响应 | `{"files": [{"id", "file_name", "file_size", "file_type", "slide_count", "theme", "conversation_id", "created_at"}]}` |
| 逻辑 | 返回当前用户的生成文件列表，最多 50 条，按创建时间倒序 |

#### DELETE `/api/chat/files/` — 删除 AI 生成文件

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| 请求 | `{"id": 123}` |
| 响应 | `{"message": "已删除"}` |
| 逻辑 | 校验文件归属当前用户 → 从 MinIO 删除文件 → 删除数据库记录 |

#### GET `/api/chat/files/<pk>/download/` — AI 文件下载

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated |
| URL 参数 | `pk` — GeneratedFile 记录 ID |
| 响应 | 文件二进制流（`Content-Disposition: attachment`） |
| 逻辑 | 校验文件归属当前用户 → 从 MinIO 获取文件 → 代理返回给前端 |

#### POST `/api/chat/files/create/` — 创建 AI 生成文件记录

| 项 | 说明 |
|---|------|
| 认证 | JWT 或 Service Token（ai-service 内部调用） |
| 请求 | `{"user_id": 1, "file_name": "xxx.pptx", "minio_path": "generated-files/xxx.pptx", "file_size": 12345, "file_type": "pptx", "slide_count": 12, "theme": "business_blue", "conversation_id": 1}` |
| 响应 | `{"id": 1, "file_name": "xxx.pptx", "created_at": "..."}`（201） |
| 逻辑 | ai-service PPT 生成工具调用，创建 GeneratedFile 记录 |

---

### 3.3 知识库模块 `/api/knowledge/`

所有接口需 IsAuthenticated + IsDeptAdmin 权限（状态回调除外）。

#### GET/POST `/api/knowledge/bases/` — 知识库列表/创建

| 项 | 说明 |
|---|------|
| GET 响应 | 知识库列表（按部门权限过滤） |
| POST 请求 | `{"name": "xxx", "department_id": 1, "description": "xxx"}` |

#### GET/PUT/DELETE `/api/knowledge/bases/<kb_id>/` — 知识库详情/更新/删除

| 项 | 说明 |
|---|------|
| PUT 请求 | `{"name": "xxx", "description": "xxx", "is_active": true}` |

#### GET `/api/knowledge/documents/` — 文档列表

| 项 | 说明 |
|---|------|
| GET 参数 | `?kb_id=xxx` |
| 响应 | 文档列表（含 status: pending/processing/completed/failed） |

#### POST `/api/knowledge/documents/upload/` — 文档上传

| 项 | 说明 |
|---|------|
| 请求 | FormData: `file` + `kb_id`, `category_l1_id`, `category_l2_id` |
| 响应 | `{"doc_id", "task_id", "kb_id", "file_name", "minio_path", "status": "processing"}` |
| 逻辑 | 上传到 MinIO → 写 DB → 触发 AI Service Celery 处理 → ES 索引 |

#### GET `/api/knowledge/documents/<doc_id>/` — 文档详情

#### POST `/api/knowledge/documents/<doc_id>/enable/` — 启用文档

#### POST `/api/knowledge/documents/<doc_id>/disable/` — 禁用文档

#### GET/PUT `/api/knowledge/documents/<doc_id>/metadata/` — 文档元数据

| 项 | 说明 |
|---|------|
| PUT 请求 | `{"category_l1_id": 1, "category_l2_id": 2, "file_name": "xxx"}` |

#### POST `/api/knowledge/documents/<doc_id>/status-callback/` — 处理状态回调

| 项 | 说明 |
|---|------|
| 认证 | **无认证**（AI Service 内部调用） |
| 请求 | `{"status": "completed"}` |
| 逻辑 | Celery 任务完成后回调，更新文档处理状态 |

#### GET `/api/knowledge/chunks/` — 分块列表

| 项 | 说明 |
|---|------|
| GET 参数 | `?kb_id=xxx&doc_id=xxx` 等 |
| 逻辑 | 代理到 AI Service ES 查询 |

#### GET `/api/knowledge/chunks/<chunk_id>/` — 分块详情

#### POST `/api/knowledge/chunks/<chunk_id>/enable/` — 启用分块

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated + IsDeptAdmin |
| URL 参数 | `chunk_id` — 分块 ID |
| 逻辑 | 代理 AI Service `/api/kb/chunks/{chunk_id}/enable`，仅父块（level=1）可启用，子块需恢复父块 |

#### POST `/api/knowledge/chunks/<chunk_id>/disable/` — 禁用分块

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated + IsDeptAdmin |
| URL 参数 | `chunk_id` — 分块 ID |
| 逻辑 | 代理 AI Service `/api/kb/chunks/{chunk_id}/disable`，仅父块（level=1）可禁用，子块不可单独操作 |

#### GET `/api/knowledge/tasks/<task_id>/` — 任务进度查询

#### POST `/api/knowledge/documents/reprocess/` — 重新处理所有文档

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated + IsSysAdmin |
| 逻辑 | 用于 ES 数据恢复，重新触发所有文档的 Celery 处理 |

---

### 3.4 组织管理模块 `/api/org/`

#### GET/POST `/api/org/departments/` — 部门列表/创建

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated + IsSysAdmin |
| GET 响应 | `[{"id", "name", "description", "member_count"}]` |
| POST 请求 | `{"name": "xxx", "description": "xxx"}` |

#### PUT/DELETE `/api/org/departments/<id>/` — 部门更新/删除

#### GET `/api/org/users/` — 用户列表

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated + IsDeptAdmin |
| GET 参数 | `?search=关键词` |
| 响应 | `[{"id", "username", "phone", "role", "department", "avatar", "is_active", "date_joined"}]` |
| 逻辑 | 部门管理员只看到本部门用户，系统管理员看到所有。`avatar` 为绝对 URL（`http://host/api/org/users/<id>/avatar/`）或 `null` |

#### POST `/api/org/users/create/` — 创建用户

| 项 | 说明 |
|---|------|
| 请求 | `{"username": "xxx", "password": "xxx", "phone": "xxx", "role": "user", "department_id": 1}` |
| 逻辑 | 部门管理员只能创建 user 角色，不能创建 dept_admin/sys_admin |

#### GET/PUT `/api/org/users/<id>/` — 用户详情/更新

#### POST `/api/org/users/<id>/reset-password/` — 重置密码

| 项 | 说明 |
|---|------|
| 请求 | `{"new_password": "xxx"}`（可选，不传则生成随机密码） |

#### POST `/api/org/users/<id>/toggle-active/` — 启用/禁用用户

#### POST `/api/org/users/<id>/transfer/` — 用户调动

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated + IsSysAdmin |
| 请求 | `{"department_id": 1}` |

#### POST `/api/org/users/batch-import/` — 批量导入

| 项 | 说明 |
|---|------|
| 请求 | FormData: `file`（Excel） |
| 响应 | `{"created": N, "skipped": N, "errors": [...]}` |

#### GET/POST `/api/org/users/<id>/kb-permissions/` — 知识库权限

| 项 | 说明 |
|---|------|
| GET 响应 | `[{"kb_id": "xxx", "name": "xxx"}]` |
| POST 请求 | `{"kb_ids": ["kb1", "kb2"]}`（全量覆盖） |

#### GET/POST `/api/org/users/<id>/agent-permissions/` — Agent 权限

#### GET `/api/org/users/<id>/avatar/` — 查看用户头像

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated + IsDeptAdmin（Header JWT），或 `?token=xxx` Query 参数认证（用于 `<img src>`） |
| 响应 | 图片二进制流（image/jpeg 等），无头像返回 404 |
| 逻辑 | 部门管理员只能查看本部门用户头像。Query token 模式下手动验证 JWT 并检查管理员角色 |

| 项 | 说明 |
|---|------|
| GET 响应 | `[{"agent_name": "xxx"}]` |
| POST 请求 | `{"agent_names": ["default", "ppt_generate"]}`（全量覆盖） |

---

### 3.5 统计看板模块 `/api/dashboard/`

所有接口需 IsAuthenticated + IsDeptAdmin 权限。部门管理员只能看到本部门数据。

#### GET `/api/dashboard/overview/` — 总览数据

| 项 | 说明 |
|---|------|
| 响应 | `{"total_users", "active_users", "total_conversations", "like_count", "dislike_count", "satisfaction_rate"}` |

#### GET `/api/dashboard/trend/` — 对话趋势

| 项 | 说明 |
|---|------|
| 响应 | `[{"date": "2024-01-01", "count": 10}]` |

#### GET `/api/dashboard/departments-compare/` — 部门对比

| 项 | 说明 |
|---|------|
| 认证 | IsAuthenticated + IsSysAdmin |
| 响应 | `[{"department": "xxx", "user_count": 10, "conversation_count": 100}]` |

#### GET `/api/dashboard/export/` — 数据导出

| 项 | 说明 |
|---|------|
| 响应 | JSON 格式对话数据 |

#### GET `/api/dashboard/feedback/` — 反馈列表

| 项 | 说明 |
|---|------|
| GET 参数 | `?feedback=like&search=用户名&department_id=1&date_start=2024-01-01&date_end=2024-12-31&page=1&page_size=20` |
| 响应 | `{"total", "page", "page_size", "data": [{"id", "user", "department", "conversation_title", "content_preview", "feedback", "feedback_detail", "created_at"}]}` |

#### GET `/api/dashboard/feedback/export/` — 反馈 Excel 导出

| 项 | 说明 |
|---|------|
| GET 参数 | 同 feedback 列表（无分页） |
| 响应 | `.xlsx` 文件流 |
| 表头 | 用户名、部门、会话标题、消息内容、反馈类型、反馈原因、反馈时间 |

#### GET `/api/dashboard/user-stats/` — 用户使用统计

| 项 | 说明 |
|---|------|
| GET 参数 | `?search=xxx&department_id=1` |
| 响应 | `[{"id", "username", "department", "conversation_count", "message_count", "tokens_used", "last_active"}]` |

---

### 3.6 标签管理模块 `/api/tags/`

所有接口需 IsAuthenticated + IsSysAdmin 权限。

#### GET `/api/tags/` — 标签树

| 项 | 说明 |
|---|------|
| 响应 | `[{"id", "name", "description", "level", "doc_count", "children": [...]}]` |

#### POST `/api/tags/create/` — 创建标签

| 项 | 说明 |
|---|------|
| 请求 | `{"name": "xxx", "description": "xxx", "parent_id": null}`（parent_id=null 创建一级标签） |

#### PUT `/api/tags/<id>/` — 更新标签

| 项 | 说明 |
|---|------|
| 请求 | `{"name": "xxx", "description": "xxx", "sort_order": 0}` |

#### DELETE `/api/tags/<id>/` — 删除标签

| 项 | 说明 |
|---|------|
| 逻辑 | 有子标签时拒绝删除 |

---

## 四、权限模型

| 角色 | 权限范围 |
|------|----------|
| user | 仅操作自己的会话/消息/记忆/提示词 |
| dept_admin | user 权限 + 管理本部门用户/知识库/看板 |
| sys_admin | 全部权限 + 部门管理/标签管理/用户调动 |

**关键隔离规则**：
- 部门管理员只能创建 `user` 角色的用户
- 部门管理员不能查看/修改系统管理员
- 部门管理员只能操作本部门用户和数据

---

## 五、认证机制

| 机制 | 说明 |
|------|------|
| Access Token | JWT，2小时有效期，存储在前端 Zustand 内存 |
| Refresh Token | JWT，30天有效期，HttpOnly Cookie（`path=/api/auth`） |
| Token 续期 | 前端 401 自动调用 `/api/auth/token/refresh/`，滑动窗口续期 |
| Token 黑名单 | 登出时 Refresh Token 加入黑名单，需 `rest_framework_simplejwt.token_blacklist` |
| 内部服务认证 | AI Service 回调通过 `Service-Token` Header 或无认证接口 |

---

## 六、外部服务交互

| 服务 | 用途 | 调用方向 |
|------|------|----------|
| AI Service (FastAPI:7729) | SSE 聊天代理、文档处理、知识库查询 | Backend → AI Service |
| AI Service (FastAPI:7729) | PPT 生成文件记录回调（Service Token 认证） | AI Service → Backend |
| MinIO | 文件上传/下载（附件、头像、PPT 生成文件） | Backend ↔ MinIO |
| Elasticsearch | 知识库索引（通过 AI Service 代理） | Backend → AI Service → ES |
| Celery/Redis | 异步文档处理任务 | Backend 触发 → AI Service Worker 执行 |

---

## 更新日志

| 日期 | 修改内容 |
|------|----------|
| 2026-04-30 | 初始创建：完整数据表 + API 接口文档 |
| 2026-04-30 | 新增 Message.feedback_detail 反馈详情字段 |
| 2026-04-30 | 新增反馈 toggle 取消机制（再次点击清除记录） |
| 2026-04-30 | 新增 FileDownloadView AI 文件下载接口 |
| 2026-04-30 | PPT 生成文件管理：GeneratedFile 模型 + 列表/创建/下载/删除接口 + MinIO 归属校验 |
