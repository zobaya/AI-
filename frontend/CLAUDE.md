# Frontend CLAUDE.md

本文件为 Claude Code 在前端目录 (`frontend/`) 下工作时提供指引。

## 技术栈

| 依赖 | 版本 | 用途 |
|------|------|------|
| React | 19.1 | UI 框架，函数组件 + Hooks |
| TypeScript | 5.8 | 类型安全，`strict: true` + `noUnusedLocals` + `noUnusedParameters` |
| Vite | 6.3 | 构建工具，使用 `@tailwindcss/vite` 插件 |
| Tailwind CSS | 4.2 | 原子化 CSS，通过 `@import "tailwindcss"` 引入 |
| Ant Design | 6.3 | UI 组件库（主要用 @ant-design/icons 图标） |
| @ant-design/icons | 6.1 | 图标库，全项目统一图标来源 |
| Zustand | 5.0 | 全局状态管理，每个 store 独立文件 |
| Axios | 1.15 | HTTP 客户端，JWT 拦截器 + Token 刷新 |
| react-router-dom | 7.14 | 路由管理 |
| marked | 18.0 | Markdown 渲染（含自定义扩展） |
| KaTeX | 0.16 | LaTeX 数学公式渲染（`$...$` 行内 + `$$...$$` 块级） |
| react-easy-crop | 5.5 | 头像裁剪 |

## 常用命令

```bash
npm run dev              # 开发服务器（端口 5173）
npm run build            # 生产构建（tsc + vite build）
npx tsc --noEmit         # TypeScript 类型检查
```

## 目录结构

```
src/
├── pages/                # 页面组件（对应路由）
├── components/
│   ├── Layout/           # AppLayout / Sidebar（永久折叠56px+底部头像Popover，无Header）
│   ├── Chat/             # ChatSidebar / ChatHeader(毛玻璃标题栏+更多菜单+导出子菜单PDF/Word/TXT) / ChatMessages(含FeedbackDetailPanel+PPTDownloadCard) / ChatInput(拖拽上传覆盖层+蓝色虚线边框+链接图标提示+语音输入Web Speech API) / AvatarCropModal / ChatSessionViewerDrawer(只读回放抽屉)
│   ├── FilterSelect.tsx  # 通用筛选下拉组件（自定义面板+阴影+圆角，替代原生select）
│   └── GlobalDialogs.tsx # Toast 通知 + 确认弹窗 + 输入弹窗（替代浏览器原生弹窗）
├── stores/               # Zustand stores
│   ├── authStore.ts      # JWT 认证（user/role/avatar）
│   ├── chatStore.ts      # 对话列表、消息、流式 phase
│   ├── themeStore.ts     # 主题：light / dark / system
│   ├── layoutStore.ts    # ChatSidebar 折叠状态（localStorage 持久化）
│   └── uiStore.ts        # Toast 通知 + 确认弹窗 + 输入弹窗状态
├── api/                  # HTTP + SSE 层
│   ├── client.ts         # Axios 实例（JWT + Token 刷新）
│   ├── chat.ts           # chatApi + streamChat(SSE) + PPT文件下载/解析 + memoryApi(用户长期记忆CRUD)
│   ├── knowledge.ts      # 知识库 CRUD
│   ├── org.ts            # 用户/部门/看板 API（UserItem.avatar 为绝对 URL）
│   └── auth.ts           # 登录/头像/改密
├── hooks/
│   └── useChatStream.ts  # SSE 流式聊天 Hook（阶段状态机）
├── utils/
│   ├── markdown.ts       # marked 渲染配置（GFM + 知识库图片代理 + KaTeX 数学公式扩展）
│   └── relativeTime.ts   # 中文相对时间格式化（刚刚/X分钟前/昨天/X天前）
└── index.css             # 全局样式 + CSS 变量设计系统
```

## 代码规范

### 组件

- 函数组件 + Hooks，禁止 class 组件
- Props 用 `interface` 定义
- 事件处理函数使用 `useCallback` 包裹
- 组件内聚，不跨页面复用

### 弹窗与通知（禁止浏览器原生弹窗）

- **禁止使用** `window.alert()`、`window.confirm()`、`window.prompt()`，所有弹窗必须为页面自绘组件
- **Toast 通知**：通过 `useUIStore` 的 `toast(message, type)` 显示短暂提示（3 秒自动消失），type 为 `'success'` / `'error'` / `'info'`
- **确认弹窗**：通过 `useUIStore` 的 `confirm({ title, message, danger? })` 替代 `window.confirm()`，返回 `Promise<boolean>`
- **输入弹窗**：通过 `useUIStore` 的 `prompt({ title, message?, placeholder?, required? })` 替代 `window.prompt()`，返回 `Promise<string | null>`
- **渲染入口**：`GlobalDialogs` 组件挂载在 `AppLayout`，自动渲染所有 Toast、确认弹窗、输入弹窗
- **Store 文件**：`src/stores/uiStore.ts`

### 样式

- **设计令牌**：`src/index.css` 的 `:root` 定义 CSS 变量，组件通过 `var(--xxx)` 引用
- **统一顶部栏**：所有页面使用全宽顶部栏（`h-12`，`var(--surface)` 白底 + 底部边框），包含图标 + 标题 + 统计/状态文本。左右分栏页面采用 `flex-col` 外层 + 顶部栏 + `flex flex-1 overflow-hidden` 内层包裹左右分栏
- **深色模式**：`[data-theme="dark"]` 覆盖变量值，由 `themeStore` 切换
- **布局/间距**：Tailwind 原子类（`px-4 py-2 gap-3`）
- **动态值**：`style={{ }}` 内联（颜色、尺寸等由状态驱动的值）
- **禁止**：在组件中硬编码颜色 hex 值（应使用 CSS 变量）
- **按钮 hover 规则（强制）**：所有可交互按钮必须具备 hover 效果。主要按钮（蓝底白字）使用 `transition-opacity duration-150 hover:opacity-90`；次要/图标按钮（边框或透明背景）使用 `.hover-gray` CSS 类（`transition-colors duration-150` + 浅灰背景）；危险按钮 hover 切换红色；虚线幽灵按钮 hover 切换 `var(--primary-light)` 背景 + `var(--primary)` 文字。不允许出现无 hover 反馈的按钮
- **筛选下拉组件（FilterSelect）**：所有筛选类下拉统一使用 `components/FilterSelect.tsx` 组件（替代原生 `<select>`），自定义触发按钮 + 定位面板（圆角 + 阴影 + 选中高亮 + hover 效果），聚焦时蓝色边框，箭头图标旋转动画。支持 `small` 模式。用于：Knowledge（部门筛选+状态筛选）、Feedback（反馈类型+部门筛选）、Dashboard（部门筛选）

### 排版体系（Typography）

- **全局字体**：`--font-base: 'Inter', -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif`（英文字体在前，中文字体在后）
- **字体渲染**：body 开启 `antialiased` + `grayscale` 抗锯齿
- **字号层级**：`--text-lg: 18px` → `--text-base: 16px` → `--text-sm: 14px` → `--text-xs: 12px`
- **状态标签/徽章**：使用 `.badge` 类（11px + font-weight 500 + 0.02em letter-spacing），确保小字锐利清晰
- **悬浮气泡/Popover**：字号 12px + line-height 1.5 + letter-spacing 0.02em
- **统计看板大数字**：使用 `tabular-nums` Tailwind 类实现等宽数字对齐 + font-weight 700 + letter-spacing -0.02em
- **聊天区域行高**：AI 回答 `.answer-section` line-height 1.75，用户气泡 `.chat-bubble-text` line-height 1.7

### API 层

- HTTP 请求走 `api/client.ts` Axios 实例（`withCredentials: true`，自动带 Cookie）
- SSE 流式走 `api/chat.ts` 的 `streamChat()`（原生 fetch + ReadableStream）
- API 函数按领域分文件

### 认证机制

- **Access Token**：存储在 Zustand 内存（`authStore.accessToken`），不写 localStorage，刷新页面丢失后自动续期
- **Refresh Token**：HttpOnly Cookie（`path=/api/auth`），JS 不可读，30天滑动窗口
- **启动恢复**：`AuthInitializer` 组件在 App 加载时调用 `/api/auth/token/refresh/`（Cookie 自动带），恢复 Access Token + 用户信息
- **无感续期**：Axios 响应拦截器捕获 401 → 自动调用 refresh → 重发原始请求
- **路由守卫**：`ProtectedRoute`（未登录 → `/login`）、`PublicRoute`（已登录 → `/chat`）
- **退出**：调用后端 `/api/auth/logout/` 清除 Cookie + 黑名单 Token + 重定向 `/login`

### SSE 流式模式

- `useChatStream.ts` 管理 phases：`idle → rewrite → thinking → tool → answering`
- 消息先用 `Date.now()` 临时 ID，完成后从 API 重新加载获取真实数据库 ID
- 流式消息通过 `streamingMessage` 状态渲染，完成后转为正式消息

### SSE 事件契约

完整事件顺序：`workflow_id → progress → think → output → title → maybe → token_usage → final → error`

前端 `useChatStream.ts` 只处理：`progress`、`think`、`output`、`title`、`maybe`、`error`。`token_usage` 和 `final` 由 Django 代理层处理。

### 反馈系统

- 点击点赞/点踩按钮 → 发送基础反馈（`like`/`dislike`）→ 弹出 `FeedbackDetailPanel`
- `FeedbackDetailPanel`：可选原因标签（点赞 3 项 / 点踩 5 项）+ "其他"文本输入 + 右上角 X 关闭
- 提交后显示感谢提示，2 秒自动关闭；提交详情调用 `chatApi.setFeedback(id, type, {reasons, comment})`
- 再次点击同一按钮取消反馈，后端清除 `feedback` + `feedback_detail`（仅当未携带 feedback_detail 时才触发 toggle）
- 按钮 hover title：`答得好` / `答得不好`

### 消息重新生成与编辑

- 重新生成按钮仅显示在最后一条 AI 回复上
- 点击重新生成 → `chatApi.truncateMessages(convId, userMsgId)` 删除最后的用户消息+AI回复 → `send()` 重新发送
- 用户消息 hover 显示复制按钮（所有用户消息）和编辑按钮（仅最新一条用户消息）
- 编辑模式：气泡替换为白色背景 textarea（蓝色边框），Enter 提交 / Escape 取消
- 编辑提交 → 截断该消息及后续所有消息 → 用编辑后文本重新发送
- `Chat.tsx` 的 `handleResend` 统一处理截断+重发流程，`onResend(deleteFromMsgId, query)` 传递给 `ChatMessages`

### 表格分页与样式

- 列表表格页面统一使用服务端分页（`page`/`page_size` 参数），每页 20 条
- 分页栏样式统一：首页 / 上一页 / 下一页 / 末页 + 页码信息（"第 X/Y 页，共 N 条"）
- 表格行 hover 高亮（`var(--primary-light)` 背景），表头 sticky 固定（`sticky top-0 z-10`）
- 表头统一样式：`text-sm` + `--text-secondary`（所有表格页面一致）
- 操作列图标统一：`fontSize: 16` + `p-2` padding
- 已有分页页面：Knowledge（文档列表）、Dashboard（员工统计）、Feedback（反馈管理）、ChunkDetail（分块列表）、Departments（部门管理）
- Users 页面使用主从分栏布局（240px 部门导航 + CSS Grid 数据网格），`page_size=999` 一次加载全部用户，客户端搜索筛选

### 标签管理页面（Tags）

- 主从分栏布局：左侧 w-72 标签树（`var(--bg)` 灰底）+ 右侧 flex-1 详情面板（`var(--surface)` 白底）
- 左侧标签树：一级标签（FolderOutlined + 加粗名称 + 子标签计数）+ 二级标签（缩进 + TagOutlined）
- 全站术语统一使用"标签"（Tag），废弃"分类"（Category）一词
- 统计信息格式：`X 个一级标签 · Y 个二级标签`
- 左侧标题区（text-lg font-semibold）下方紧跟「+ 添加一级标签」幽灵按钮（虚线边框，默认 `var(--text-secondary)` + 透明背景，hover 平滑过渡为 `var(--primary-light)` 背景 + `var(--primary)` 文字，使用 `var(--transition-fast)` 曲线），与标签树间距 `mt-4`
- 去线化树状列表，标签行 hover 高亮 `var(--primary-light)`（选中态常驻），Hover 显示 `...` 操作菜单（一级：添加二级标签/编辑/删除；二级：编辑/删除）
- 选中态强化：选中节点的文字和图标变为 `var(--primary)` + `font-medium`，背景 `var(--primary-light)` 常驻
- 右侧操作区上下文联动：一级标签显示 3 按钮（「+ 添加二级标签」主按钮蓝底白字 + `hover:opacity-90` + 编辑幽灵按钮 + 删除按钮）；二级标签显示 2 按钮（编辑 + 删除）
- 编辑按钮 hover 效果：默认态中性色（`var(--text-secondary)` + `var(--border)`），Hover 时切换为蓝色（`var(--primary)` 文字/边框 + `var(--primary-light)` 背景），0.15s 过渡
- 删除按钮克制设计：默认态中性色（`var(--text-secondary)` + `var(--border)`），仅 Hover 时切换为红色危险色
- 右侧内容区使用 `max-w-5xl mx-auto px-8` 居中限宽，内部分割线使用 `var(--divider-subtle)` 极低透明度
- 概览区：描述卡片（flex-1）+ 关联文档数卡片（w-36）
- 文档列表：调用 `GET /api/tags/<id>/documents/` 获取关联文档，显示文件名 + 知识库名
- 统一创建/编辑弹窗（modalMode: createL1/createL2/edit），支持名称 + 描述字段
- 删除确认使用 `useUIStore.confirm()`，智能文案含子标签数和受影响文档数

### 知识库管理页面（Knowledge）

- 主从分栏布局：左侧 280px 知识库列表（`var(--bg)` 灰底）+ 右侧 flex-1 文档列表（`var(--surface)` 白底）
- 左侧侧边栏：顶部部门筛选（`FilterSelect` 组件，从知识库列表提取唯一部门，2+ 部门时显示，选项含数量）+ 知识库列表 + 底部「+ 新建知识库」幽灵按钮（`var(--text-muted)` → Hover `var(--primary)`）
- 知识库行选中态：`var(--primary-light)` 背景 + `var(--primary)` 文字 + `font-weight: 600`；列表项使用 `conv-item` 类，hover 灰色 `rgba(0,0,0,0.04)`（与 Chat 侧边栏一致）
- 知识库行 Hover：`...` 操作按钮（编辑/删除），`opacity-0 group-hover:opacity-100` 显隐
- 右侧文档列表：无边框现代样式（仅 `rgba(0,0,0,0.04)` 底部分割线），表头无灰底
- 文档操作图标默认隐藏（`opacity-0`），行 Hover 时显示（`group-hover:opacity-100`）
- 文档名点击导航至 `/knowledge/:kbId/docs/:docId`（ChunkDetail 页面）
- 启用/禁用开关：CSS 滑动开关（绿/红）
- 上传弹窗（UploadModal）：拖拽上传 + 文件列表 + 标签选择（一级/二级），支持批量（最多10个）+ 进度轮询
- 编辑弹窗（DocEditModal）：文档名 + 标签选择
- 创建/编辑知识库弹窗：名称 + 部门选择（仅 sys_admin）+ 描述
- 空状态：未选中知识库时显示提示「选择左侧知识库查看文档」
- 分页栏样式统一：首页/上一页/下一页/末页 + 页码信息

### 分块管理页面（ChunkDetail）

- 独立路由页面（`/knowledge/:kbId/docs/:docId`），不再嵌套于 KnowledgeDetail
- 面包屑导航：蓝色圆角返回按钮 + `KB名称 / 文档名称`，KB 名称通过 `knowledgeApi.getBase(kbId)` 获取，点击返回 `/knowledge`
- 左右分栏：左侧 35% 分块列表 + 右侧 65% 分块详情
- 左侧分块行样式：小圆点（6px，`var(--success)` 绿=启用/`#d1d5db` 灰=禁用）+ 灰色序号（`var(--text-muted)`）+ 柔和预览文字
- 右侧详情区：浮动卡片样式（`var(--surface)` + `var(--card-radius)` + `var(--glass-shadow)`），背景 `var(--bg)`

- Knowledge 文档列表的"启用状态"列使用 CSS 滑动开关（toggle switch）组件
- 启用状态：绿色背景（`#16a34a`），滑块在右；禁用状态：红色背景（`#ef4444`），滑块在左
- 操作列仅保留编辑和删除按钮，启用/禁用统一由滑动开关控制

### 用户管理页面（Users）

- 主从分栏布局：左侧 240px 侧边栏（`var(--bg)` 灰底）+ 右侧数据网格（`var(--surface)` 白底）
- 左侧侧边栏分为两个区域：
  - **全局视图**：「全部用户」（TeamOutlined 图标）+ 「未分配」（InboxOutlined 图标，仅 unassignedCount > 0 时渲染）
  - **部门列表**：Section Header「部门」（`text-sm font-semibold` + `var(--text-secondary)`）+ 右侧内联 `+` 圆形按钮（`w-6 h-6 rounded-full`，hover 深色背景，title="新增部门"，仅 sys_admin 可见）
- 列表项统一样式（与 Chat 侧边栏一致）：`conv-item` 类 + `data-active` 属性 + `py-[9px] rounded-lg` + `px-3 gap-2` 内距，左侧图标 14px，右侧计数胶囊
- 所有列表项文本左边缘绝对对齐（统一 icon 14px + gap-2 + px-3 内距）
- Hover 态统一使用 `.conv-item:not([data-active="true"]):hover { background: rgba(0,0,0,0.04) }` 灰色（与 Chat 侧边栏一致），选中态保持 `var(--primary-light)` 蓝色 + `font-weight: 500`
- 「未分配」条件渲染：仅当未分配用户数 > 0 时才渲染 DOM 节点，保持侧边栏清爽
- 部门项 Hover 显示 `...` 按钮（仅系统管理员），点击弹出重命名/删除下拉菜单
- 部门 CRUD：创建/重命名通过 `useUIStore.prompt()`，删除通过 `useUIStore.confirm()` 携带智能文案（含用户数提示）
- 删除部门时后端自动将该部门用户 `department` 置空（归入未分配），不再阻止删除
- 右侧数据网格 + 抽屉式详情：点击行打开 Drawer，基本信息 Tab 可编辑（用户名/手机号），权限管理 Tab 含角色变更 + 快捷操作，对话历史 Tab 查看用户会话列表；顶部栏含搜索框 + 批量导入（`.hover-gray`）+ 新增用户（`hover:opacity-90`）按钮
- 权限管理 Tab：顶部角色变更下拉框 + 分割线 + 快捷操作列表（启禁用、重置密码、部门调动[仅sys_admin]、知识库权限[sys_admin+dept_admin]、Agent 权限[sys_admin+dept_admin]、删除用户）
- 对话历史 Tab：调用 `chatApi.getConversationsForUser(userId)` 加载用户会话列表，每项显示标题+消息数+日期，点击打开 `ChatSessionViewerDrawer` 只读回放
- 保存栏：基本信息/权限管理 Tab 有修改时显示保存/撤销按钮（对话历史 Tab 不显示）
- 删除用户：`DELETE /api/org/users/{id}/`，后端校验不能删自己，Django CASCADE 清理关联数据

### ChatSidebar（历史对话栏）

- 支持分组管理（创建/重命名/删除分组，拖拽会话到分组）、置顶、重命名、删除
- 重命名对话：点击后显示内联输入框 + 确认（✓）/ 取消（✗）按钮，Enter 提交、Escape 取消，不使用 onBlur 自动保存
- 搜索功能：常驻搜索输入框，输入关键词后 300ms 防抖调用 `chatApi.getConversations({ search })` 搜索标题和消息内容，清除按钮清空搜索恢复完整列表，搜索中显示"搜索中..."，无结果时显示"未找到相关对话"，有结果时显示"找到 N 个结果"
- 折叠/展开（统一单容器 + CSS 驱动动画）：
  - 单一 JSX 容器通过 `chatSidebarCollapsed` 状态控制宽度（260px ↔ 48px），使用 `sidebar-transition` 类 CSS `width` 过渡 + `sidebar-collapsed` 类触发折叠态样式
  - `MenuOutlined` 和 `FormOutlined` 图标始终在 48px 居中区域（`width: 48, justify-center`），折叠前后位置完全不变，颜色统一为 `var(--text-secondary)`
  - "新对话"文字使用 `.sidebar-text` 类，折叠时 CSS 淡出（`opacity: 0, width: 0`）
  - 搜索 + 会话列表区域折叠时通过 `opacity` 过渡淡出 + `pointerEvents: 'none'` 禁用交互
  - 折叠态图标 hover 显示 `.sidebar-tooltip` 悬浮文字（由 `.sidebar-collapsed .sidebar-item:hover .sidebar-tooltip` CSS 控制）
- 分组标题视觉强化：所有分段标题（置顶/分组/时间分组）统一 `text-sm font-semibold` + `var(--text-secondary)` 颜色，后续标题上方 `mt-4`（第一个 `mt-1`），标题下方 `mb-2`；"分组"标题右侧 `+` 圆形按钮（`w-6 h-6 rounded-full`，hover 深色背景，`title="创建分组"`），移入滚动区域内
- 未分组会话按时间分组显示：「今天」「昨天」「最近7天」「更早」，使用 `updated_at` 字段分组，仅显示有会话的分组
- 会话列表项交互：使用 `.conv-item` 类 + `data-active` 属性，选中态保持 `var(--primary-light)` 蓝色高亮，未选中态 hover 使用 `.conv-item:not([data-active="true"]):hover` 浅灰色（`rgba(0,0,0,0.04)`），支持深色模式，`transition-colors duration-150` 平滑过渡
- 主侧边栏（Sidebar）导航项统一使用 `var(--primary-light)` 作为 hover 背景高亮色，激活项保持原有样式

### 知识库图片代理

- AI 回答中引用知识库文档图片时，图片路径格式为 `knowledge-base/{kb_id}/{doc_id}/images/{filename}`
- 前端 `markdown.ts` 通过自定义 `marked` image renderer 将 MinIO 路径重写为 Django 代理 URL
- 重写规则：`knowledge-base/...` 或 `http://{minio_host}/knowledge-base/...` → `{API_BASE}/api/knowledge/images/{object_path}?token={jwt}`（`API_BASE` 与 `api/client.ts` 一致，解决 `<img>` 标签不走 Axios 导致相对 URL 指向 Vite 端口的问题）
- 后端 `KnowledgeBaseImageView`（`GET /api/knowledge/images/<path:path>`）验证 JWT → 从 MinIO `knowledge-base` 桶取图 → 返回图片
- 认证支持 `?token=` query 参数（`<img src>` 场景）和标准 `Authorization` Header

### PPT 文件下载

- AI 回答中的 `<!--PPT_FILE:{json}-->` HTML 注释由 `parsePPTFileMarkers()` 提取，渲染为 `PPTDownloadCard`
- 下载通过 `downloadGeneratedFile(fileId, fileName)` → Django `FileDownloadView`（GET `/api/chat/files/<id>/download/`，JWT 认证，归属校验，代理 MinIO）
- `PPTFileInfo` 接口包含 `file_id: number | null`，通过数据库记录 ID 下载而非 MinIO 路径
- Settings 页面 "我的生成文件" 区域展示用户所有 PPT 文件，支持下载和删除

### ChatSessionViewerDrawer（只读聊天回放抽屉）

- 560px 宽度抽屉（`.chat-viewer-drawer`），从右侧滑入，复用 `.drawer-overlay` + `.drawer-panel` CSS
- 只读模式：无输入框、无反馈按钮、无编辑、无重新生成、无复制按钮
- 消息气泡复用 ChatMessages 样式：用户消息蓝色渐变右对齐 70%，AI 消息左对齐 + `renderMarkdown()` 渲染
- Props：`conversationId`（必传）、`highlightMessageId?`（高亮消息ID）、`feedbackData?`（反馈详情）、`onClose`
- 高亮逻辑：传入 `highlightMessageId` 时自动滚动到该消息，添加淡色背景（踩=淡红 `rgba(254,226,226,0.5)`，赞=淡绿 `rgba(220,252,231,0.5)`）
- 反馈详情：高亮消息下方显示原因标签（绿/红色药丸）+ 评论文本
- 数据加载：`chatApi.getConversation(id)` 获取完整对话消息列表
- 使用场景：用户管理"对话历史"Tab 查看完整对话、反馈管理点击卡片定位到案发消息

### 反馈管理页面（Feedback）

- 卡片信息流布局：每条反馈渲染为水平卡片（`rounded-xl` + `border`），替代原来的 Table 布局
- 卡片结构：上方行（头像首字母 + 用户名 + 部门胶囊 + 时间 | 点赞/踩徽章）→ 中间行（会话标题 + 内容预览）→ 下方行（反馈原因标签）
- 卡片 hover：`borderColor: var(--primary)` + `background: var(--primary-light)`
- 点击卡片打开 `ChatSessionViewerDrawer`，传入 `conversationId` + `highlightMessageId` + `feedbackData` 高亮案发消息
- 保留原有筛选区（反馈类型/部门/日期/搜索）和分页栏

### AI 记忆管理页面（AIMemory）

- 独立路由页面（`/settings/memory`），从 Settings 页面"AI 记忆"导航卡片进入
- 页面布局：sticky 顶部栏（BrainOutlined + "AI 记忆" + 返回按钮）+ `max-w-4xl` 居中内容区
- 添加记忆卡片：textarea 输入框 + 4 分类内联按钮（偏好/知识/目标/上下文，各有独立颜色）+ "添加记忆"主按钮
- 分类 Tab 筛选栏：全部/偏好/知识/目标/背景，带计数徽章 + 底部蓝色指示条
- 卡片网格：`grid grid-cols-1 md:grid-cols-2 gap-4`，每张卡片含分类彩色标签 + 事实文本 + 相对时间 + 来源标识（自动提取/手动添加）+ hover 显示删除按钮
- 删除确认使用 `useUIStore.confirm()`，禁止浏览器原生弹窗
- API：`memoryApi.list/create/delete`，对应后端 `/api/chat/memory/` 系列 CRUD 接口

## 路由结构

| 路径 | 组件 | 权限 |
|------|------|------|
| `/login` | Login | 公开 |
| `/chat` | Chat | 所有用户 |
| `/chat/:convId` | Chat | 所有用户 |
| `/knowledge` | Knowledge | 管理员 |
| `/knowledge/:kbId/docs/:docId` | ChunkDetail | 管理员 |
| `/admin/users` | Users | 管理员 |
| `/admin/tags` | Tags | 系统管理员 |
| `/admin/feedback` | Feedback | 管理员 |
| `/dashboard` | Dashboard | 管理员 |
| `/settings` | Settings | 所有用户 |
| `/settings/memory` | AIMemory | 所有用户 |

## 构建验证

每次修改前端代码后，运行：

```bash
npx tsc --noEmit    # TypeScript 类型检查
npx vite build      # 生产构建
```
