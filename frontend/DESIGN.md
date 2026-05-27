# Frontend 设计规格文档

本文档记录前端所有 UI 组件的精确设计参数。修改样式时必须参考此文档，修改后同步更新。

---

## 1. 设计令牌（CSS 变量）

定义位置：`src/index.css` `:root` / `[data-theme="dark"]`

### 1.1 颜色

| 变量 | 亮色值 | 暗色值 | 用途 |
|------|--------|--------|------|
| `--primary` | `#007bff` | `#3b82f6` | 主色调，按钮/链接/活跃态 |
| `--primary-dark` | `#0062cc` | `#2563eb` | 渐变终点色 |
| `--primary-light` | `rgba(0,123,255,0.08)` | `rgba(59,130,246,0.1)` | 活跃背景/选中态 |
| `--bg` | `#f4f5f9` | `#0f1020` | 页面底色 |
| `--surface` | `#ffffff` | `#1a1b30` | 卡片/面板底色 |
| `--border` | `#e8eaef` | `#2c2d48` | 边框线 |
| `--text` | `#1a1d2e` | `#e4e5f0` | 主文字 |
| `--text-secondary` | `#5f6580` | `#a0a2b8` | 辅助文字 |
| `--text-muted` | `#9ca0b0` | `#6b6d82` | 占位/弱化文字 |
| `--think` | `#5a9fd4` | `#6bb3e0` | 思考过程标题色 |
| `--think-bg` | `#eef5fb` | `#151d30` | 思考过程背景色（暂未使用） |
| `--tool` | `#2a9d8f` | `#3bc4b1` | 工具调用标题色 |
| `--tool-bg` | `#edf7f6` | `#122a27` | 工具调用背景色（暂未使用） |
| `--success` | `#16a34a` | `#22c55e` | 成功/状态点 |
| `--rewrite` | `#8b5cf6` | `#a78bfa` | 查询优化标题色 |
| `--rewrite-bg` | `#f3f0ff` | `#1a1530` | 查询优化背景色（暂未使用） |

### 1.2 字号层级

| 变量 | 值 | 使用场景 |
|------|------|----------|
| `--text-lg` | `18px` | 页面标题、空状态大标题 |
| `--text-base` | `16px` | 正文、消息内容、输入框 |
| `--text-sm` | `14px` | 副标题、导航项、表格正文、按钮文字 |
| `--text-xs` | `12px` | 标签、辅助信息、时间戳、表格表头 |

### 1.3 圆角

| 变量 | 值 | 使用场景 |
|------|------|----------|
| `--radius-sm` | `8px` | 按钮、输入框、导航项 |
| `--radius-md` | `--card-radius` = `12px` | 卡片、面板 |
| `--radius-lg` | `16px` | 大面板、输入容器 |

### 1.4 间距

| Tailwind | 像素 | 典型用途 |
|----------|------|----------|
| `p-1` | 4px | 小图标按钮内边距 |
| `p-1.5` | 6px | 操作按钮内边距 |
| `p-2` | 8px | 紧凑元素内边距 |
| `p-3` | 12px | 输入区域内边距、小组件 |
| `p-4` | 16px | 中等容器内边距 |
| `p-5` | 20px | 卡片内边距、区块内边距 |
| `p-6` | 24px | 页面内边距 |
| `p-8` | 32px | 登录卡片内边距 |
| `px-4 py-3` | 16px/12px | 输入框内边距 |
| `px-4 py-2` | 16px/8px | 标准按钮内边距 |
| `px-3 py-1.5` | 12px/6px | 小按钮/标签内边距 |

### 1.5 阴影

| 变量 | 亮色值 | 用途 |
|------|--------|------|
| `--card-shadow` | `0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.06)` | 卡片默认阴影 |
| `--glass-shadow` | `0 4px 24px rgba(0,0,0,0.06)` | 玻璃面板阴影 |

### 1.6 过渡动画

| 变量 | 值 | 用途 |
|------|------|------|
| `--transition-sidebar` | `0.25s cubic-bezier(0.4,0,0.2,1)` | 侧边栏折叠/展开 |
| `--transition-fast` | `0.15s cubic-bezier(0.4,0,0.2,1)` | hover、按钮等快速过渡 |

### 1.7 布局尺寸

| 变量 | 值 | 说明 |
|------|------|------|
| `--sidebar-collapsed-w` | `56px` | 主侧边栏宽度（永久锁定折叠态） |
| `--chat-sidebar-w` | `260px` | 聊天历史栏宽度 |

### 1.8 玻璃效果

| 变量 | 亮色值 | 暗色值 |
|------|--------|--------|
| `--glass-bg` | `rgba(255,255,255,0.72)` | `rgba(26,27,48,0.78)` |
| `--glass-border` | `rgba(255,255,255,0.35)` | `rgba(255,255,255,0.06)` |
| `--glass-blur` | `16px` | `16px` |

---

## 2. 图标规格

全项目统一使用 **@ant-design/icons** 图标库。自定义图标使用内联 SVG。

### 2.1 图标尺寸标准

| 场景 | 尺寸 | 代码 |
|------|------|------|
| 导航图标 | 16px | `style={{ fontSize: 16 }}` 或 `className="text-[16px]"` |
| 按钮图标 | 16-20px | `style={{ fontSize: 16/20 }}` |
| 消息操作图标 | 16px | `style={{ fontSize: 16 }}` |
| 会话菜单图标 | 13-14px | `style={{ fontSize: 13/14 }}` |
| 小操作图标（置顶/编辑/删除） | 10px | `style={{ fontSize: 10 }}` |
| 分组箭头/文件夹图标 | 10-12px | `style={{ fontSize: 10/12 }}` |

### 2.2 自定义 SVG 图标

消息卡片使用内联 SVG（viewBox `0 0 24 24`，stroke-width 2）：
- **ThinkIcon** — 灯泡形状
- **ToolIcon** — 扳手形状
- **RewriteIcon** — 笔形状

显示尺寸由 CSS 类 `.card-icon` 控制：`width: var(--icon-sm); height: var(--icon-sm)` = `20px × 20px`。

### 2.3 头像/Logo

| 元素 | 尺寸 | 圆角 |
|------|------|------|
| Sidebar 底部头像 | `w-9 h-9` (36px) | `rounded-full` |
| Popover 菜单 | — | `var(--radius-md)` = 12px，玻璃态 |
| Settings 用户头像 | `w-16 h-16` (64px) | `rounded-full` |
| Login Logo | `w-14 h-14` (56px) | `rounded-2xl` (16px) |
| 空状态 Logo | `56px × 56px` | `border-radius: 16px` |

---

## 3. 布局组件

### 3.1 AppLayout（`components/Layout/AppLayout.tsx`）

```
┌─────────┬──────────────────────────────────┐
│ Sidebar │                                  │
│ (56px)  │  <Outlet /> (flex-1 overflow)    │
│         │                                  │
│         │                                  │
└─────────┴──────────────────────────────────┘
```

- 外层：`flex h-screen`，底色 `var(--bg)`
- Sidebar：固定 56px，左侧
- 主内容区：`flex-1 overflow-hidden min-w-0`
- 无 Header 组件（已移除，内容区直接占满右侧）

### 3.2 Sidebar（`components/Layout/Sidebar.tsx`）

**永久折叠态**：宽度固定 `--sidebar-collapsed-w` = 56px，无展开/折叠切换。

| 参数 | 值 |
|------|------|
| 宽度 | `--sidebar-collapsed-w` = 56px（永久锁定） |
| 背景 | `var(--surface)` |
| 边框 | `border-right: 1px solid var(--border)` |
| 阴影 | `2px 0 8px rgba(0,0,0,0.04)` |

**顶部 Logo 区域**：`h-12` (48px)，`border-bottom` 分隔，居中显示 SVG 图标 (24×24px)

**导航项**（永久折叠态）：
- 布局：`justify-center` 居中，仅图标
- 间距：`py-2.5` (10px) 上下
- 圆角：`4px`
- 图标字号：`18px`
- 活跃态：背景 `var(--primary-light)`，文字 `var(--primary)`，`fontWeight: 700`
- 非活跃态：背景透明，文字 `var(--text-secondary)`，`fontWeight: 500`
- 活跃指示器：左侧 `3px` 竖条，高度 60%，颜色 `var(--primary)`

**折叠态 Tooltip**：
- 位置：`left: calc(100% + 8px)`，垂直居中
- 样式：`padding: 4px 10px`，`border-radius: 6px`，`font-size: 12px`
- 背景：`var(--surface)`，边框 `var(--border)`，阴影 `0 2px 8px rgba(0,0,0,0.12)`

**底部用户头像区域**：
- 位置：Sidebar 底部，`border-top` 分隔，`py-3`，居中
- 头像按钮：`w-9 h-9` (36px)，`rounded-full`，背景 `var(--primary)`
- 头像图片：有 avatar URL 时显示 `<img>`，否则显示 `UserOutlined` 图标 (16px)

**用户菜单 Popover（玻璃态）**：
- 触发：点击底部头像按钮
- 位置：`bottom: calc(100% + 8px)`，`left: calc(100% + 10px)`
- 最小宽度：`180px`
- 圆角：`var(--radius-md)` = 12px
- 背景：`var(--glass-bg)` + `backdrop-filter: blur(20px)`
- 边框：`var(--glass-border)`
- 阴影：`0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06)`
- 入场动画：`popover-in 0.18s cubic-bezier(0.16, 1, 0.3, 1)`，`transform-origin: bottom left`
- 内容：
  - 用户信息头：用户名 (`text-sm font-medium`) + 角色 (`text-xs text-muted`)
  - "设置"按钮：`SettingOutlined` + 文字，hover 背景 `var(--primary-light)`
  - "退出登录"按钮：`LogoutOutlined` + 文字，颜色 `#ef4444`，hover 背景 `rgba(239,68,68,0.08)`
- 菜单项内边距：`10px 14px`
- 关闭方式：点击外部遮罩层 / 按 ESC 键

---

## 4. 聊天组件

### 4.1 Chat 页面布局（`pages/Chat.tsx`）

```
┌──────────────┬────────────────────────────────────┐
│ ChatSidebar  │  ChatHeader (h-11, 毛玻璃)          │
│ (260px)      ├────────────────────────────────────┤
│              │                                    │
│              │  ChatMessages (flex-1)              │
│              │                                    │
│              ├────────────────────────────────────┤
│              │  ChatInput (shrink-0)               │
│              │  "内容由AI生成" 免责声明              │
└──────────────┴────────────────────────────────────┘
```

- ChatHeader：`h-11` (44px)，`.glass-header` 毛玻璃效果，居中标题 `text-sm font-semibold`，右侧更多按钮（EllipsisOutlined）→ 下拉菜单（重命名/置顶/删除）
- 顶部栏：`h-12` (48px)，`px-4` (16px)，背景 `var(--surface)`
- 三横线按钮：`w-8 h-8` (32px)，`rounded-lg`，SVG 16×16

### 4.2 ChatSidebar（`components/Chat/ChatSidebar.tsx`）

- 宽度：`--chat-sidebar-w` = 260px
- 背景：`var(--glass-bg)` + `backdrop-filter: blur(16px)` 玻璃效果
- 边框：`border-right: 1px solid var(--glass-border)`
- 折叠态：渲染为 `null`（完全隐藏）

**新对话按钮**：
- 内边距：`py-2.5` (10px)
- 背景：`linear-gradient(135deg, var(--primary), var(--primary-dark))`
- 阴影：`0 2px 8px rgba(0,123,255,0.25)`
- 字号：`text-sm` (14px)，`font-medium` (500)

**分组标题栏**：
- 内边距：`px-4 py-2`
- 字号：`text-xs` (12px)，`font-semibold` (600)
- 背景：`var(--bg)`
- 边框：`border-y`

**会话项**：
- 内边距：`px-3 py-2` (12px/8px)
- 字号：`text-sm` (14px)
- 圆角：`rounded-lg` (8px)
- 选中态：背景 `var(--primary-light)`，文字 `var(--primary)`，`fontWeight: 500`
- hover 态：三点菜单 `opacity: 0 → 1`

**下拉菜单**（Dropdown）：
- 最小宽度：`140px`
- 圆角：`rounded-lg` (8px)
- 菜单项：`px-3 py-2`，`text-sm`
- 危险操作色：`#ef4444`

### 4.3 ChatMessages（`components/Chat/ChatMessages.tsx`）

**消息列表容器**：
- 内边距：`16px 24px`
- 消息间距：`gap: 20px`

**用户消息气泡**：
- 内边距：`12px 18px`
- 圆角：`18px`，右下角 `4px`
- 最大宽度：`70%`
- 字号：`var(--text-base)` (16px)，行高 `1.7`
- 背景：`linear-gradient(135deg, var(--primary), var(--primary-dark))`
- 文字色：`#fff`
- 阴影：`0 2px 10px rgba(0,123,255,0.2)`

**AI 消息区域**：
- 最大宽度：`85%`
- 内边距：`padding: 12px 0`

**可折叠卡片（CollapsibleCard）**：

| 参数 | 值 |
|------|------|
| 边框 | `1px solid var(--card-border)` |
| 圆角 | `var(--card-radius)` = 12px |
| 背景 | `var(--card-bg)` |
| 阴影 | `var(--card-shadow)` |
| 标题栏内边距 | `12px 16px` |
| 标题栏最小高度 | `48px` |
| 标题字号 | `var(--text-sm)` (14px)，`font-weight: 600` |
| 副标题字号 | `var(--text-xs)` (12px)，颜色 `var(--text-muted)` |
| 图标尺寸 | `var(--icon-sm)` = 20px |
| Chevron 尺寸 | `20px × 20px` |
| 内容区内边距 | `12px 16px` |
| 展开动画 | CSS Grid `grid-template-rows: 1fr → 0fr`，`0.25s ease-out` |

**状态指示点**：
- 尺寸：`8px × 8px`，`border-radius: 50%`
- 完成态：背景 `var(--success)`
- 运行态：CSS `pulse` 动画 (1.2s)

**弹跳等待动画（BouncingDots）**：
- 圆点尺寸：`8px × 8px`
- 间距：`gap: 6px`
- 颜色：`var(--primary)`
- 动画：`bouncing 0.6s infinite alternate`

**操作栏（MessageActions）**：
- 默认透明度：`opacity: 0`，hover 时 `opacity: 1`（过渡 0.2s）
- 按钮内边距：`6px 10px`
- 按钮字号：`var(--text-xs)` (12px)
- 按钮图标：`16px`
- hover 态：背景 `var(--primary-light)`，文字 `var(--primary)`
- 点赞/点踩按钮 title：`答得好` / `答得不好`
- 再次点击同一按钮：取消反馈（后端清除 feedback + feedback_detail）

**反馈详情面板（FeedbackDetailPanel）**：
- 定位：`position: absolute; top: 100%`（操作栏下方），`marginTop: 8px`
- 尺寸：`minWidth: 340px; maxWidth: 420px`，内边距 `20px 24px`
- 圆角：`12px`，阴影 `0 4px 20px rgba(0,0,0,0.12)`
- 右上角关闭按钮：`CloseOutlined` 图标，`14px`，颜色 `var(--text-muted)`
- 提问文案：字号 `var(--text-sm)`，`fontWeight: 500`，`paddingRight: 24`
  - 点赞：`你觉得什么让你满意？`
  - 点踩：`你觉得什么让你不满意？`
- 选项标签：`border-radius: 20px`，内边距 `7px 16px`，间距 `gap: 10px`
  - 点赞选项：`内容准确`、`易于理解`、`内容完善`
  - 点踩选项：`有害/不安全`、`信息虚假`、`没有帮助`、`信息不全`、`隐私相关`
  - `其他` 按钮：展开文本输入框
  - 选中态：边框 `var(--primary)`，背景 `var(--primary-light)`，文字 `var(--primary)`
- 其他输入框：`width: 100%`，内边距 `8px 12px`，圆角 `8px`
- 提交按钮：内边距 `8px 20px`，背景 `var(--primary)`，白色文字
- 感谢提示：提交后显示 `非常感谢！你的反馈有助于改进AI小助手。`，2秒后自动关闭
- 自动滚动：面板挂载时 `scrollIntoView({ behavior: 'smooth', block: 'nearest' })`

**PPT 下载卡片（PPTDownloadCard）**：
- 定位：在 Markdown 回答内容下方，`marginTop: 12px`
- 布局：`flex`，内边距 `12px 16px`，圆角 `8px`
- 图标：`FilePptOutlined`，`32px`，颜色 `var(--primary)`
- 文件名：`fontWeight: 500`，`text-overflow: ellipsis`
- 文件信息：`text-xs`，颜色 `var(--text-muted)`
- 下载按钮：内边距 `8px 16px`，背景 `var(--primary)`，白色文字
- PPT 文件标记：`<!--PPT_FILE:{json}-->` HTML 注释，由 `parsePPTFileMarkers()` 解析
- JSON 中 `file_id` 字段用于 GET `/api/chat/files/<file_id>/download/` 下载（归属校验）

**猜你想问（MaybeQuestions）**：
- 间距：`gap: 8px`
- 标签字号：`var(--text-sm)` (14px)，`font-weight: 500`
- 按钮内边距：`8px 16px`
- 圆角：`20px`（胶囊形）
- 边框：`1px solid rgba(0,123,255,0.15)`
- 背景：`var(--primary-light)`
- hover：`scale(1.02)` + `box-shadow: 0 2px 8px rgba(0,123,255,0.12)`

**空状态**：
- Logo：`56px × 56px`，圆角 `16px`，渐变背景
- 问候语字号：`var(--text-lg)` (18px)，`font-weight: 600`
- 副文字：`var(--text-sm)` (14px)，颜色 `var(--text-muted)`

### 4.4 ChatHeader（`components/Chat/ChatHeader.tsx`）

- 仅在对话模式且 `currentConvId` 存在时渲染
- 高度：`h-11` (44px)
- 背景：`.glass-header`（亮色 `rgba(255,255,255,0.80)` + `backdrop-blur(12px)`，暗色 `rgba(26,27,48,0.85)`）
- 底部边框：`var(--border)`

**标题**：
- 居中：`flex-1 justify-center`，`max-width: 60%`
- 字号：`text-sm`，`font-semibold`
- 颜色：`var(--text)`，单行截断 `truncate`

**更多按钮**：
- 图标：`EllipsisOutlined` (18px)
- 尺寸：`w-8 h-8`，`rounded-md`
- Hover：`.hover-gray`

**下拉菜单**：
- 背景：`var(--surface)`，圆角 `rounded-lg`，投影 `0 8px 24px`
- 入场动画：`popover-in 0.15s`
- 菜单项使用 `.chat-menu-item`（中性 hover `#f9fafb`），删除项加 `.danger`（红色 hover `#fef2f2` + `#dc2626`）
- 深色模式：`.chat-menu-item:hover` → `rgba(255,255,255,0.06)`，`.danger:hover` → `rgba(239,68,68,0.12)` + `#f87171`
- 操作：重命名（`useUIStore.prompt`）、置顶/取消置顶（`chatApi.updateConversation`）、删除（`useUIStore.confirm` + 导航回 `/chat`）

### 4.5 ChatInput（`components/Chat/ChatInput.tsx`）

**容器**：
- 对话模式内边距：`px-5 pb-3`（无顶部内边距，消除白色遮挡）
- 欢迎模式内边距：`px-5 py-3`

**AI 免责声明**：
- 仅对话模式显示，位于输入框下方
- 文字："内容由AI生成"，字号 11px，颜色 `var(--text-muted)`，居中

**输入框容器**：
- 圆角：`rounded-2xl` (16px)
- 内边距：`p-3` (12px)
- 边框：`1px solid var(--border)`，聚焦时 `var(--primary)`
- 聚焦光环：`box-shadow: 0 0 0 3px rgba(0,123,255,0.1)`
- 背景：`var(--surface)`

**文本域**：
- 字号：`var(--text-base)` (16px)
- 最小高度：`44px`
- 最大高度：`120px`
- 行高：`1.75`（由 `leading-relaxed` 控制）

**发送按钮**：
- 尺寸：`w-9 h-9` (36px)
- 圆角：`rounded-full`
- 背景：`linear-gradient(135deg, var(--primary), var(--primary-dark))`
- 阴影：`0 2px 8px rgba(0,123,255,0.3)`
- 禁用态：`opacity: 0.4`

**停止按钮**：
- 尺寸：`w-9 h-9` (36px)
- 圆角：`rounded-full`
- 背景：`#ef4444`（红色）

**文件标签**：
- 内边距：`px-3 py-1.5` (12px/6px)
- 圆角：`rounded-lg` (8px)
- 字号：`text-xs` (12px)
- 背景：`var(--primary-light)`，边框 `rgba(0,123,255,0.2)`

**工具按钮**：
- 尺寸：`w-9 h-9` (36px) 或高度 `h-9` (36px)
- 字号：`var(--text-sm)` (14px)，`font-weight: 500`
- 弹出层最小宽度：`200px`

---

## 5. 页面组件

### 5.1 Login（`pages/Login.tsx`）

**页面**：`flex items-center justify-center h-screen`，背景 `var(--bg)`

**登录卡片**：
- 最大宽度：`max-w-sm` (384px)
- 内边距：`p-8` (32px)
- 圆角：`rounded-xl` (12px)
- 阴影：`shadow-lg`

**Logo**：`w-14 h-14` (56px)，`rounded-2xl` (16px)，字号 `text-2xl` (24px)，`font-bold` (700)

**输入框**：
- 内边距：`px-4 py-3` (16px/12px)
- 圆角：`rounded-lg` (8px)
- 字号：`text-sm` (14px)
- 聚焦边框：`var(--primary)`

**登录按钮**：
- 内边距：`py-3` (12px)
- 圆角：`rounded-lg` (8px)
- 字号：`text-sm` (14px)，`font-medium` (500)
- 背景：`var(--primary)`
- 禁用态：`opacity: 0.6`

### 5.2 Settings（`pages/Settings.tsx`）

**页面顶部栏**：
- 统一规格：`h-12` (48px) + `px-6`，背景 `var(--surface)`
- 左侧：图标(18px, var(--primary)) + 标题(text-base font-bold) + 描述(text-xs text-muted)
- 右侧：操作按钮
- 关闭按钮：`w-8 h-8` (32px)，`rounded-lg`

**内容区**：`max-w-lg mx-auto w-full p-6`，`space-y-8`

**区块卡片**：
- 内边距：`p-5` (20px)
- 圆角：`rounded-xl` (12px)
- 边框：`1px solid var(--border)`
- 背景：`var(--surface)`
- 阴影：`var(--glass-shadow)`

**区块标题**：`text-sm` (14px)，`font-semibold` (600)

**表单输入框**：
- 内边距：`px-3 py-2` (12px/8px)
- 圆角：`rounded-lg` (8px)
- 字号：`text-sm` (14px)
- 聚焦：边框 `var(--primary)` + 光环 `0 0 0 3px rgba(0,123,255,0.1)`

**主题选择按钮**：
- 内边距：`px-4 py-2` (16px/8px)
- 圆角：`rounded-lg` (8px)
- 字号：`text-sm` (14px)
- 选中态：边框 `var(--primary)`，背景 `var(--primary-light)`，文字 `var(--primary)`，`fontWeight: 600`，光环 `0 0 0 3px rgba(0,123,255,0.1)`

**我的生成文件区块（MyFilesList）**：
- 刷新按钮：`text-xs`，颜色 `var(--text-muted)`，图标 `ReloadOutlined`
- 文件项：`flex`，`gap-3`，`p-3`，`rounded-lg`，`border`
- 文件图标：`FilePptOutlined`，`24px`，颜色 `var(--primary)`
- 文件名：`text-sm font-medium`，`truncate`
- 文件信息：`text-xs`，颜色 `var(--text-muted)`（大小 · 页数 · 日期）
- 下载按钮：`p-1.5`，颜色 `var(--primary)`
- 删除按钮：`p-1.5`，颜色 `var(--text-muted)`

### 5.3 Dashboard（`pages/Dashboard.tsx`）

**页面顶部栏**：
- 统一规格：`h-12` (48px) + `px-6`，背景 `var(--surface)`
- 左侧：图标(18px, var(--primary)) + 标题(text-base font-bold)

**概览卡片**（StatCard）：
- 布局：`grid grid-cols-4 gap-4`
- 内边距：`p-5` (20px)
- 圆角：`rounded-xl` (12px)
- 标签字号：`text-xs` (12px)
- 数值字号：`text-2xl` (24px)，`font-bold` (700)
- 副标题字号：`text-xs` (12px)

**对话趋势图**：
- 高度：`h-40` (160px)
- 柱状条宽度：`flex-1`（等宽）
- 柱状条颜色：`var(--primary)`，`opacity: 0.7`
- 日期标签：每 5 个柱状条显示一个，`text-[10px]`

**部门活跃度卡片**：
- 布局：`grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4`
- 卡片内边距：`p-4` (16px)
- 圆角：`rounded-xl` (12px)
- 部门首字母图标：`w-8 h-8` (32px)，`rounded-lg`，背景 `var(--primary)`
- 对话数：`text-2xl` (24px)，`font-bold`，颜色 `var(--primary)`
- 成员数：`text-sm` (14px)，`font-medium` (500)
- 标签字号：`text-[11px]`
- 进度条高度：`h-1.5` (6px)
- 进度条渐变：`linear-gradient(90deg, var(--primary), var(--primary-dark))`

**员工统计表格**：
- 表头：`px-5 py-2.5`，`text-xs` (12px)，`font-medium` (500)，颜色 `var(--text-muted)`
- 表格行：`px-5 py-2.5`
- 空数据：`py-6` 居中提示

### 5.4 Users（`pages/Users.tsx`）— 主从分栏布局

**页面结构**：`flex h-full`，左侧部门导航（240px）+ 右侧数据网格 + Drawer

**数据加载**：`page_size=999` 一次加载全部用户，客户端按部门分组 + 客户端搜索。

**左侧部门导航（Master）**：
- 宽度：固定 `240px`，`border-right: 1px solid var(--border)`，背景 `var(--bg)`
- 两大分组区域：
  - **全局视图**：顶部固定，含「全部用户」（TeamOutlined 14px 图标）+ 「未分配」（InboxOutlined 14px 图标，条件渲染：仅 unassignedCount > 0 时显示）
  - **部门列表**：Section Header「部门」（`text-xs font-semibold`，`var(--text-secondary)` 颜色）+ 右侧内联 `+` 图标按钮（`w-6 h-6`，title="新增部门"，`.hover-gray`，仅 sys_admin），mt-4 mb-1 间距
- 列表项统一样式（与 Chat 侧边栏一致）：
  - `conv-item` 类 + `data-active` 属性，`py-[9px] rounded-lg`，外层 `mb-0.5`
  - 内距 `px-3`，左侧图标（14px）+ `gap-2` + 文字，右侧计数胶囊
  - 所有项文本左边缘绝对对齐（统一 icon + gap + padding）
- 计数胶囊：`text-xs px-1.5 py-0.5 rounded-full leading-none min-w-[20px] text-center`
  - 选中态：`var(--primary)` 蓝底 + `#fff` 白字
  - 默认态：`var(--bg)` 底 + `var(--text-muted)` 字
- Hover 态：使用 CSS `.conv-item:not([data-active="true"]):hover { background: rgba(0,0,0,0.04) }` 灰色（与 Chat 侧边栏一致）；选中项保持 `var(--primary-light)` 背景 + `var(--primary)` 文字 + `font-weight: 500`
- 部门项 hover 显示 `...` 操作按钮（仅 sys_admin），下拉菜单含重命名/删除
- 排序：部门名按拼音排序

**右侧数据网格（Detail Grid）**：
- 顶部栏（`h-12`）：当前部门标题 + 搜索框 + 批量导入/新增按钮
- 网格列宽：`grid-template-columns: 2fr 1.5fr 1fr 1fr 80px`
- 网格表头（sticky）：姓名/手机号/角色/状态/（空），`text-xs` `var(--text-muted)`
- 数据行背景：`var(--surface)`，hover `var(--primary-light)`
- 数据行边框：仅 `border-bottom: rgba(0,0,0,0.04)` 极淡水平线，无垂直线
- 行内边距：`10px 24px`

**网格列内容**：
- 姓名（2fr）：28px 圆形头像 + 用户名（`font-medium`）
- 手机号（1.5fr）：`var(--text-secondary)`，无手机号显示 "-"
- 角色（1fr）：胶囊标签 `text-xs px-2.5 py-0.5 rounded-full`，`var(--primary-light)` 背景
- 状态（1fr）：6px 圆点 + 文字（正常/禁用），活跃 `var(--success)` / 禁用 `#d1d5db`
- 操作（80px）：`EllipsisOutlined`，默认 `opacity-0`，行 hover `opacity-1`

**`...` 操作菜单**（`.action-dropdown`）：
- 定位：锚定在 `...` 按钮下方
- 玻璃态背景：`var(--glass-bg)` + `backdrop-filter: blur(20px)`
- 菜单项：编辑 / 重置密码 / 启禁用 / 调动 / 知识库权限 / Agent 权限

**右侧 Drawer**（`.drawer-panel`）：
- 宽度：`420px`（`max-width: 90vw`）
- 背景：`var(--surface)`，阴影 `box-shadow: -4px 0 24px rgba(0,0,0,0.08)`
- 动画：`drawer-slide-in 0.25s cubic-bezier(0.16, 1, 0.3, 1)`
- Drawer 头部（h-14）：40px 头像 + 用户名 + 角色胶囊 + 状态
- Drawer Tab："基本信息" / "权限管理"，底边框指示器
- 基本信息Tab：用户名/手机号输入框 + 角色/部门下拉 + 注册时间 + 底部固定保存栏（`editDirty` 时显示撤销/保存修改）
- 权限管理Tab：启禁用/重置密码/调动/知识库权限/Agent 权限快捷操作
- 确认弹窗：启禁用操作需二次确认（显示用户名+警告文字，禁用按钮红色）；部门调动需先选中目标部门再点击确认

### 5.5 Knowledge / KnowledgeDetail / ChunkDetail

**页面结构**：同 Dashboard 的 `flex flex-col h-full` 模式

**知识库卡片**：
- 布局：`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4`
- 内边距：`p-5` (20px)
- 圆角：`rounded-xl` (12px)

**搜索框**：
- 内边距：`px-3 py-2`
- 宽度：`160px`
- 字号：`text-sm` (14px)

**表格**：
- 单元格内边距：`px-4 py-3`
- 操作按钮：`p-1.5` (6px)

---

## 6. 动画

定义位置：`src/index.css`

| 动画名 | CSS | 时长 | 用途 |
|--------|-----|------|------|
| `bouncing` | `translateY(-6px); opacity: 0.2` | `0.6s infinite alternate` | 等待圆点弹跳 |
| `fade-in-up` | `translateY(8px) → translateY(0)` | `0.2s ease-out` | 消息出现 |
| `pulse` | `opacity: 1 → 0.4 → 1` | `1.2s ease-in-out infinite` | 状态点闪烁 |

**可折叠卡片展开/收起**：CSS Grid `grid-template-rows: 1fr ↔ 0fr`，`0.25s ease-out`

**侧边栏**：永久锁定折叠态（56px），无展开/折叠动画

**用户菜单 Popover**：`popover-in 0.18s cubic-bezier(0.16, 1, 0.3, 1)`，从 `scale(0.95) translateY(4px)` 到 `scale(1) translateY(0)`

**右侧 Drawer**：`drawer-slide-in 0.25s cubic-bezier(0.16, 1, 0.3, 1)`，从 `translateX(100%)` 滑入
**Drawer 遮罩**：`drawer-fade-in 0.2s ease-out`，`opacity: 0 → 1`

---

## 7. 字重标准

| 字重值 | CSS | 使用场景 |
|--------|-----|----------|
| 400 | `font-normal` | 正文、普通文字 |
| 500 | `font-medium` | 按钮、选中态导航、用户名 |
| 600 | `font-semibold` | 区块标题、活跃态导航、页面标题 |
| 700 | `font-bold` | 大数字（统计卡片）、Logo |

---

## 8. 按钮规格汇总

**强制规则：所有可交互按钮必须具备 hover 效果，不允许出现无 hover 反馈的按钮。**

| 类型 | 内边距 | 圆角 | hover 效果 | 示例 |
|------|--------|------|------------|------|
| 主要按钮（蓝底白字） | `py-3` 或 `px-4 py-2` | `rounded-lg` (8px) | `transition-opacity duration-150 hover:opacity-90` 透明度微调 | 登录、上传文档、新增用户、添加二级标签 |
| 次要按钮（边框幽灵） | `px-3 py-1.5` ~ `px-4 py-2` | `rounded-lg` (8px) | `.hover-gray` 浅灰背景 + `transition-colors duration-150` | 批量导入、导出Excel/报表、取消 |
| 图标按钮（小） | `w-8 h-8` | `rounded-lg` (8px) | `.hover-gray` 浅灰背景 | 关闭、菜单 |
| 图标按钮（中） | `w-9 h-9` | `rounded-lg` 或 `rounded-full` | `.hover-gray` 浅灰背景 | 发送、附件 |
| 导航项 | `py-2.5` | 4px（永久折叠态） | `var(--primary-light)` 背景高亮 | 侧边栏导航（图标居中） |
| 胶囊按钮 | `8px 16px` | `20px` | `scale(1.02)` + 阴影 | 猜你想问 |
| 危险按钮 | 同次要按钮 | `rounded-lg` (8px) | hover 切换为红色危险色 | 删除 |
| 虚线幽灵按钮 | `py-2` | `rounded-lg` (8px) | `var(--primary-light)` 背景 + `var(--primary)` 文字，`var(--transition-fast)` 过渡 | 添加一级标签 |

---

## 更新日志

| 日期 | 修改内容 |
|------|----------|
| 2026-04-29 | 初始创建：完整设计规格文档 |
| 2026-04-29 | 新增 token_usage SSE 事件追踪 |
| 2026-04-29 | 部门活跃度改为卡片网格布局 |
| 2026-04-29 | 全页面顶部栏统一为 h-12 (48px) + px-6 |
| 2026-04-29 | 顶部栏样式统一：图标+标题+描述单行居中，字号text-sm |
| 2026-04-30 | 反馈详情面板（FeedbackDetailPanel）：可选原因标签+感谢提示+右上角X关闭 |
| 2026-04-30 | PPT 下载卡片（PPTDownloadCard）：文件信息+下载按钮 |
| 2026-04-30 | 操作栏点赞/点踩 title 改为"答得好"/"答得不好"，支持取消清除记录 |
| 2026-05-01 | 布局重构：Header 精简（移除角色文字和头像），Sidebar 永久锁定折叠态（56px），底部新增用户头像+玻璃态 Popover 菜单（设置/退出登录） |
| 2026-05-01 | 用户管理页面重构：传统表格改为部门分组 Accordion + 去线化行 + 角色/状态胶囊 + hover ...菜单 + 右侧 Drawer 详情编辑 |
| 2026-05-01 | 用户管理页面二次重构：改为主从分栏布局（240px 部门导航 + CSS Grid 数据网格），客户端搜索，解决"拉面效应"和"手风琴灾难" |
| 2026-05-03 | 按钮交互统一：全站所有按钮强制 hover 效果；主要按钮 `opacity-90`，次要/图标按钮 `.hover-gray`；移除 Knowledge/Users/Feedback/Dashboard 刷新按钮 |
| 2026-05-03 | 用户管理侧边栏重构：双区布局（全局视图 + 部门分组 Section Header）；`h-8 rounded-md` 统一列表项；`+` 内联按钮替代底部添加按钮；条件渲染"未分配"（count > 0）；计数胶囊改为 `var(--bg)` 底色 + `leading-none` |
| 2026-05-01 | 用户管理交互优化：启禁用操作增加二次确认弹窗，部门调动改为选择+确认两步操作，Drawer 保存按钮移至底部固定栏 |
| 2026-05-03 | Chat区域新增毛玻璃Header（ChatHeader h-11）：居中会话标题+更多菜单（重命名/置顶/删除）；ChatInput对话模式去除顶部内边距消除白色遮挡；输入框下方增加"内容由AI生成"免责声明 |
