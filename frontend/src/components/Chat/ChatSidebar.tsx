import { useEffect, useState, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { chatApi } from '@/api/chat'
import { useChatStore } from '@/stores/chatStore'
import { useLayoutStore } from '@/stores/layoutStore'
import { useUIStore } from '@/stores/uiStore'
import {
  PlusOutlined,
  DeleteOutlined,
  PushpinOutlined,
  EllipsisOutlined,
  FolderOutlined,
  EditOutlined,
  DownOutlined,
  RightOutlined,
  CheckOutlined,
  CloseOutlined,
  FormOutlined,
  SearchOutlined,
  MenuOutlined,
  ExportOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  FileTextOutlined,
} from '@ant-design/icons'
import type { Conversation } from '@/api/chat'

interface FolderItem {
  id: number
  name: string
  conversation_count: number
}

/** 按时间段分组会话 */
function groupByTime(convs: Conversation[]) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const week = new Date(today.getTime() - 7 * 86400000)

  const groups: { label: string; convs: Conversation[] }[] = [
    { label: '今天', convs: [] },
    { label: '昨天', convs: [] },
    { label: '最近7天', convs: [] },
    { label: '更早', convs: [] },
  ]

  for (const conv of convs) {
    const date = new Date(conv.updated_at)
    if (date >= today) {
      groups[0].convs.push(conv)
    } else if (date >= yesterday) {
      groups[1].convs.push(conv)
    } else if (date >= week) {
      groups[2].convs.push(conv)
    } else {
      groups[3].convs.push(conv)
    }
  }

  return groups.filter((g) => g.convs.length > 0)
}

interface SubItem { label: string; icon?: React.ReactNode; onClick: () => void }
interface MenuItem { label: string; icon?: React.ReactNode; danger?: boolean; onClick?: () => void; subItems?: SubItem[] }

/** 三点下拉菜单 — Portal 渲染，避免被 overflow:hidden 裁切 */
function Dropdown({
  items,
  onClose,
  anchorRef,
}: {
  items: MenuItem[]
  onClose: () => void
  anchorRef: React.RefObject<HTMLElement | null>
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  // 计算定位
  useEffect(() => {
    const anchor = anchorRef.current
    if (!anchor) return
    const r = anchor.getBoundingClientRect()
    setPos({ top: r.bottom + 4, left: r.left })
  }, [anchorRef])

  // 点击外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node) &&
          anchorRef.current && !anchorRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose, anchorRef])

  if (!pos) return null

  const menu = (
    <div
      ref={ref}
      className="py-1 rounded-lg border shadow-lg z-[9999]"
      style={{
        background: 'var(--surface)',
        borderColor: 'var(--border)',
        minWidth: 140,
        position: 'fixed',
        top: pos.top,
        left: pos.left,
        animation: 'popover-in 0.15s cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      {items.map((item, i) => (
        item.subItems ? (
          <div key={i} className="sidebar-export-trigger relative">
            <div
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left cursor-default"
              style={{ color: 'var(--text-secondary)' }}
            >
              {item.icon}
              <span className="flex-1">{item.label}</span>
              <RightOutlined style={{ fontSize: 10, color: 'var(--text-muted)' }} />
            </div>
            <div className="sidebar-export-submenu">
              {item.subItems.map((sub, si) => (
                <button
                  key={si}
                  onClick={(e) => {
                    e.stopPropagation()
                    sub.onClick()
                    onClose()
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left cursor-pointer transition-colors hover:opacity-80"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {sub.icon}
                  {sub.label}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <button
            key={i}
            onClick={(e) => {
              e.stopPropagation()
              item.onClick?.()
              onClose()
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left cursor-pointer transition-colors hover:opacity-80"
            style={{ color: item.danger ? '#ef4444' : 'var(--text-secondary)' }}
          >
            {item.icon}
            {item.label}
          </button>
        )
      ))}
    </div>
  )

  return createPortal(menu, document.body)
}

export default function ChatSidebar({ onNew }: { onNew: () => void }) {
  const navigate = useNavigate()
  const conversations = useChatStore((s) => s.conversations)
  const currentConvId = useChatStore((s) => s.currentConvId)
  const setConversations = useChatStore((s) => s.setConversations)
  const setCurrentConvId = useChatStore((s) => s.setCurrentConvId)
  const setMessages = useChatStore((s) => s.setMessages)
  const chatSidebarCollapsed = useLayoutStore((s) => s.chatSidebarCollapsed)
  const confirm = useUIStore((s) => s.confirm)
  const prompt = useUIStore((s) => s.prompt)

  const [folders, setFolders] = useState<FolderItem[]>([])
  const [openMenuId, setOpenMenuId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [showNewFolder, setShowNewFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [moveConvId, setMoveConvId] = useState<number | null>(null)
  const [collapsedGroups, setCollapsedGroups] = useState<Set<number>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<typeof conversations>([])
  const [isSearching, setIsSearching] = useState(false)
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const menuButtonRefs = useRef<Map<number, HTMLButtonElement>>(new Map())

  const loadAll = async () => {
    const [{ data: convData }, { data: folderData }] = await Promise.all([
      chatApi.getConversations(),
      chatApi.getFolders(),
    ])
    setConversations(convData)
    setFolders(folderData)
  }

  useEffect(() => {
    loadAll()
  }, [])

  // ── 搜索 ──────────────────────────────────────────────────

  const handleSearchChange = (value: string) => {
    setSearchQuery(value)
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
    if (!value.trim()) {
      setSearchResults([])
      setIsSearching(false)
      return
    }
    setIsSearching(true)
    searchTimerRef.current = setTimeout(async () => {
      try {
        const { data } = await chatApi.getConversations({ search: value.trim() })
        setSearchResults(data)
      } catch {
        setSearchResults([])
      }
      setIsSearching(false)
    }, 300)
  }

  const handleClearSearch = () => {
    setSearchQuery('')
    setSearchResults([])
    setIsSearching(false)
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current)
  }

  const toggleGroup = (id: number) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  // ── 会话操作 ──────────────────────────────────────────────

  const handleNew = () => {
    onNew()
  }

  const handleSwitch = (id: number) => {
    if (editingId) return
    setCurrentConvId(id)
    navigate(`/chat/${id}`)
  }

  const handleDelete = async (id: number) => {
    await chatApi.deleteConversation(id)
    if (currentConvId === id) {
      setCurrentConvId(null)
      setMessages([])
      navigate('/chat')
    }
    loadAll()
  }

  const handleTogglePin = async (id: number, pinned: boolean) => {
    await chatApi.updateConversation(id, { is_pinned: !pinned })
    loadAll()
  }

  const handleRename = (id: number, title: string) => {
    setEditingId(id)
    setEditTitle(title)
    setOpenMenuId(null)
  }

  const handleRenameSave = async (id: number) => {
    const trimmed = editTitle.trim()
    if (trimmed) {
      await chatApi.updateConversation(id, { title: trimmed })
    }
    setEditingId(null)
    loadAll()
  }

  const handleMoveToFolder = async (convId: number, folderId: number | null) => {
    await chatApi.updateConversation(convId, { folder_id: folderId })
    setMoveConvId(null)
    loadAll()
  }

  const handleExport = async (convId: number, format: 'pdf' | 'docx' | 'txt') => {
    const conv = conversations.find((c) => c.id === convId)
    const title = conv?.title || '新对话'
    try {
      const { data: blob } = await chatApi.exportConversation(convId, format)
      const url = URL.createObjectURL(blob as unknown as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${title}.${format}`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch {
      useUIStore.getState().toast('导出失败', 'error')
    }
  }

  // ── 分组操作 ────────────────────────────────────────────

  const handleCreateFolder = async () => {
    const name = newFolderName.trim()
    if (!name) return
    await chatApi.createFolder(name)
    setNewFolderName('')
    setShowNewFolder(false)
    loadAll()
  }

  const handleDeleteFolder = async (id: number) => {
    if (!await confirm({ title: '确认删除', message: '删除分组？其中的会话将移出分组。', danger: true })) return
    await chatApi.deleteFolder(id)
    loadAll()
  }

  const handleRenameFolder = async (id: number) => {
    const name = await prompt({ title: '重命名分组', message: '输入新的分组名称：', required: true })
    if (!name) return
    await chatApi.updateFolder(id, { name })
    loadAll()
  }

  // ── 分组逻辑 ──────────────────────────────────────────────

  const pinnedConvs = conversations.filter((c) => c.is_pinned && !c.folder)
  const folderMap = new Map<number, typeof conversations>()
  folders.forEach((f) => folderMap.set(f.id, []))
  const ungrouped = conversations.filter((c) => {
    if (c.is_pinned && !c.folder) return false
    if (c.folder) {
      const arr = folderMap.get(c.folder.id)
      if (arr) arr.push(c)
      return false
    }
    return true
  })

  // ── 渲染单个会话行 ────────────────────────────────────────

  const renderConvItem = (conv: typeof conversations[0]) => {
    if (editingId === conv.id) {
      return (
        <div key={conv.id} className="flex items-center gap-1.5 px-3 py-1.5">
          <input
            autoFocus
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRenameSave(conv.id)
              if (e.key === 'Escape') setEditingId(null)
            }}
            className="flex-1 min-w-0 px-2 py-1.5 rounded border text-sm outline-none"
            style={{ borderColor: 'var(--primary)', background: 'var(--bg)', color: 'var(--text)' }}
          />
          <button onClick={() => handleRenameSave(conv.id)}
            className="shrink-0 p-1 rounded cursor-pointer transition-colors duration-150"
            style={{ color: 'var(--primary)' }}
            title="确认">
            <CheckOutlined style={{ fontSize: 13 }} />
          </button>
          <button onClick={() => setEditingId(null)}
            className="shrink-0 p-1 rounded cursor-pointer transition-colors duration-150"
            style={{ color: 'var(--text-muted)' }}
            title="取消">
            <CloseOutlined style={{ fontSize: 13 }} />
          </button>
        </div>
      )
    }

    const menuItems: MenuItem[] = [
      { label: conv.is_pinned ? '取消置顶' : '置顶', icon: <PushpinOutlined style={{ fontSize: 13 }} />, onClick: () => handleTogglePin(conv.id, conv.is_pinned) },
      { label: '重命名', icon: <EditOutlined style={{ fontSize: 13 }} />, onClick: () => handleRename(conv.id, conv.title) },
      { label: '移到分组', icon: <FolderOutlined style={{ fontSize: 13 }} />, onClick: () => setMoveConvId(conv.id) },
      {
        label: '导出会话', icon: <ExportOutlined style={{ fontSize: 13 }} />,
        subItems: [
          { label: 'PDF', icon: <FilePdfOutlined style={{ fontSize: 13, color: '#ef4444' }} />, onClick: () => handleExport(conv.id, 'pdf') },
          { label: 'Word', icon: <FileWordOutlined style={{ fontSize: 13, color: '#2563eb' }} />, onClick: () => handleExport(conv.id, 'docx') },
          { label: 'TXT', icon: <FileTextOutlined style={{ fontSize: 13 }} />, onClick: () => handleExport(conv.id, 'txt') },
        ],
      },
      { label: '删除', icon: <DeleteOutlined style={{ fontSize: 13 }} />, danger: true, onClick: () => handleDelete(conv.id) },
    ]

    return (
      <div key={conv.id} className="relative">
        <div
          onClick={() => handleSwitch(conv.id)}
          className="conv-item flex items-center group px-3 py-[9px] rounded-lg cursor-pointer text-sm mb-0.5 transition-colors duration-150"
          data-active={conv.id === currentConvId}
          style={{
            background: conv.id === currentConvId ? 'var(--primary-light)' : undefined,
            color: conv.id === currentConvId ? 'var(--primary)' : 'var(--text-secondary)',
            fontWeight: conv.id === currentConvId ? 500 : 400,
          }}
        >
          {conv.is_pinned && (
            <PushpinOutlined style={{ fontSize: 10, marginRight: 4, color: 'var(--primary)' }} />
          )}
          <span className="flex-1 truncate">{conv.title}</span>
          <button
            ref={(el) => { if (el) menuButtonRefs.current.set(conv.id, el) }}
            onClick={(e) => {
              e.stopPropagation()
              setOpenMenuId(openMenuId === conv.id ? null : conv.id)
              setMoveConvId(null)
            }}
            className="opacity-0 group-hover:opacity-100 p-1 rounded cursor-pointer transition-opacity duration-150"
            style={{ color: 'var(--text-muted)' }}
          >
            <EllipsisOutlined style={{ fontSize: 14 }} />
          </button>
        </div>
        {openMenuId === conv.id && (
          <Dropdown
            items={menuItems}
            onClose={() => setOpenMenuId(null)}
            anchorRef={{ current: menuButtonRefs.current.get(conv.id) ?? null }}
          />
        )}
        {/* 移到分组子菜单 */}
        {moveConvId === conv.id && (
          <div
            className="ml-6 mt-1 mb-1 py-1 rounded-lg border"
            style={{ background: 'var(--bg)', borderColor: 'var(--border)' }}
          >
            <button
              onClick={(e) => { e.stopPropagation(); handleMoveToFolder(conv.id, null) }}
              className="w-full text-left px-3 py-1.5 text-xs cursor-pointer hover:opacity-80"
              style={{ color: !conv.folder ? 'var(--primary)' : 'var(--text-muted)' }}
            >
              无分组
            </button>
            {folders.map((f) => (
              <button
                key={f.id}
                onClick={(e) => { e.stopPropagation(); handleMoveToFolder(conv.id, f.id) }}
                className="w-full text-left px-3 py-1.5 text-xs cursor-pointer hover:opacity-80"
                style={{ color: conv.folder?.id === f.id ? 'var(--primary)' : 'var(--text-muted)' }}
              >
                {f.name}
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div
      className={`flex flex-col shrink-0 border-r sidebar-transition ${chatSidebarCollapsed ? 'sidebar-collapsed' : ''}`}
      style={{
        width: chatSidebarCollapsed ? 48 : 'var(--chat-sidebar-w)',
        background: 'var(--bg)',
        borderColor: 'var(--border)',
        overflow: 'hidden',
      }}
    >
      {/* 顶部行：折叠/展开按钮（48px 居中区域，折叠前后图标位置不变） */}
      <div className="sidebar-item relative flex items-center" style={{ height: 48 }}>
        <div className="flex justify-center shrink-0" style={{ width: 48 }}>
          <button
            onClick={() => useLayoutStore.getState().toggleChatSidebar()}
            className="w-8 h-8 flex items-center justify-center rounded-lg cursor-pointer hover-gray"
            style={{ color: 'var(--text-secondary)' }}
          >
            <MenuOutlined style={{ fontSize: 16 }} />
          </button>
        </div>
        <span className="sidebar-tooltip">展开侧边栏</span>
      </div>

      {/* 新对话按钮（图标 48px 居中区域，折叠前后图标位置不变） */}
      <div className="sidebar-item relative mt-1 mb-1">
        <button
          onClick={handleNew}
          className="w-full flex items-center py-2 text-sm cursor-pointer hover-gray"
          style={{ color: 'var(--text-secondary)' }}
        >
          <div className="flex justify-center shrink-0" style={{ width: 48 }}>
            <FormOutlined style={{ fontSize: 16 }} />
          </div>
          <span className="sidebar-text" style={{ color: 'var(--text)' }}>新对话</span>
        </button>
        <span className="sidebar-tooltip">新对话</span>
      </div>

      {/* 展开态内容：搜索 + 会话列表（折叠时淡出隐藏） */}
      <div
        className="flex-1 flex flex-col min-w-0"
        style={{
          opacity: chatSidebarCollapsed ? 0 : 1,
          transition: 'opacity 0.15s ease',
          pointerEvents: chatSidebarCollapsed ? 'none' : 'auto',
          overflow: 'hidden',
        }}
      >
        {/* 搜索 */}
        <div className="px-3 mb-1">
          <div className="flex items-center gap-1 px-3 py-1.5 rounded-lg border" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
            <SearchOutlined style={{ fontSize: 14, color: 'var(--text-muted)', flexShrink: 0 }} />
            <input
              value={searchQuery}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="搜索对话标题或内容..."
              className="flex-1 min-w-0 px-1 py-0.5 text-sm outline-none bg-transparent"
              style={{ color: 'var(--text)' }}
            />
            {searchQuery && (
              <button
                onClick={handleClearSearch}
                className="shrink-0 w-5 h-5 flex items-center justify-center rounded-full cursor-pointer"
                style={{ color: 'var(--text-muted)', fontSize: 10, background: 'var(--border)' }}
              >
                <CloseOutlined style={{ fontSize: 10 }} />
              </button>
            )}
          </div>
        </div>

        {/* 会话列表 */}
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {searchQuery.trim() ? (
            /* ── 搜索结果 ── */
            <>
              {isSearching ? (
                <div className="px-3 py-6 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                  搜索中...
                </div>
              ) : searchResults.length > 0 ? (
                <>
                  <div className="px-3 mb-2 text-xs" style={{ color: 'var(--text-muted)' }}>
                    找到 {searchResults.length} 个结果
                  </div>
                  {searchResults.map(renderConvItem)}
                </>
              ) : (
                <div className="px-3 py-6 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                  未找到相关对话
                </div>
              )}
            </>
          ) : (
          <>
          {/* 置顶会话 */}
          {pinnedConvs.length > 0 && (
            <div className="mb-2 mt-1">
              <div className="px-3 mb-2 text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
                置顶
              </div>
              {pinnedConvs.map(renderConvItem)}
            </div>
          )}

          {/* 分组标题 + 创建分组 */}
          <div className={pinnedConvs.length > 0 ? 'mt-4' : 'mt-1'}>
            <div className="flex items-center justify-between px-3 mb-1">
              <span className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>分组</span>
              <button
                onClick={() => setShowNewFolder(true)}
                title="创建分组"
                className="flex items-center justify-center w-6 h-6 rounded-full cursor-pointer transition-colors duration-150"
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.06)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)' }}
              >
                <PlusOutlined style={{ fontSize: 14 }} />
              </button>
            </div>
          </div>

          {/* 创建分组输入框 */}
          {showNewFolder && (
            <div className="px-3 pb-2">
              <input
                autoFocus
                value={newFolderName}
                onChange={(e) => setNewFolderName(e.target.value)}
                placeholder="输入分组名称"
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200"
                style={{ borderColor: 'var(--primary)', background: 'var(--surface)', color: 'var(--text)' }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateFolder()
                  if (e.key === 'Escape') { setShowNewFolder(false); setNewFolderName('') }
                }}
              />
              <div className="flex items-center gap-2 mt-2">
                <button
                  onClick={handleCreateFolder}
                  className="px-3 py-1.5 rounded-lg text-xs text-white cursor-pointer"
                  style={{ background: 'var(--primary)' }}
                >
                  确定
                </button>
                <button
                  onClick={() => { setShowNewFolder(false); setNewFolderName('') }}
                  className="px-3 py-1.5 rounded-lg text-xs cursor-pointer border"
                  style={{ color: 'var(--text-muted)', borderColor: 'var(--border)' }}
                >
                  取消
                </button>
              </div>
            </div>
          )}

          {/* 分组（可折叠） */}
          {folders.map((f) => {
            const convs = folderMap.get(f.id) || []
            const collapsed = collapsedGroups.has(f.id)
            return (
              <div key={f.id} className="mb-1">
                <div
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium group/folder cursor-pointer select-none"
                  style={{ color: 'var(--text-secondary)' }}
                  onClick={() => toggleGroup(f.id)}
                >
                  {collapsed
                    ? <RightOutlined style={{ fontSize: 12 }} />
                    : <DownOutlined style={{ fontSize: 12 }} />}
                  <FolderOutlined style={{ fontSize: 14 }} />
                  <span className="flex-1 truncate">{f.name}</span>
                  <span
                    className="opacity-0 group-hover/folder:opacity-100 flex items-center gap-1 transition-opacity duration-150"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => handleRenameFolder(f.id)}
                      className="p-1 cursor-pointer hover:opacity-80"
                      title="重命名分组"
                    >
                      <EditOutlined style={{ fontSize: 14 }} />
                    </button>
                    <button
                      onClick={() => handleDeleteFolder(f.id)}
                      className="p-1 cursor-pointer hover:opacity-80"
                      title="删除分组"
                    >
                      <DeleteOutlined style={{ fontSize: 14 }} />
                    </button>
                  </span>
                </div>
                {!collapsed && (convs.length > 0 ? <div className="ml-4">{convs.map(renderConvItem)}</div> : (
                  <div className="ml-4 px-3 py-1 text-xs" style={{ color: 'var(--text-muted)', opacity: 0.5 }}>
                    暂无会话
                  </div>
                ))}
              </div>
            )
          })}

          {/* 未分组会话（按时间分组） */}
          {ungrouped.length > 0 && (
            <div className="mb-2">
              {groupByTime(ungrouped).map((group, gi) => (
                <div key={group.label} className={gi > 0 ? 'mt-4' : ''}>
                  <div className="px-3 mb-2 text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
                    {group.label}
                  </div>
                  {group.convs.map(renderConvItem)}
                </div>
              ))}
            </div>
          )}

          {/* 无任何会话 */}
          {conversations.length === 0 && (
            <div className="px-3 py-6 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
              暂无会话，开始新对话吧
            </div>
          )}
          </>
          )}
        </div>
      </div>
    </div>
  )
}

