import { useState, useRef, useEffect, useCallback } from 'react'
import { EllipsisOutlined, EditOutlined, PushpinOutlined, PushpinFilled, DeleteOutlined, ExportOutlined, FilePdfOutlined, FileWordOutlined, FileTextOutlined, RightOutlined } from '@ant-design/icons'
import { chatApi } from '@/api/chat'
import { useChatStore } from '@/stores/chatStore'
import { useUIStore } from '@/stores/uiStore'

interface Props {
  convId: number
  onDeleted: () => void
}

export default function ChatHeader({ convId, onDeleted }: Props) {
  const conversations = useChatStore((s) => s.conversations)
  const updateConversationTitle = useChatStore((s) => s.updateConversationTitle)
  const setConversations = useChatStore((s) => s.setConversations)

  const currentConv = conversations.find((c) => c.id === convId)
  const title = currentConv?.title || '新对话'
  const isPinned = currentConv?.is_pinned || false

  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // 点击外部关闭菜单
  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  const handleRename = useCallback(async () => {
    setMenuOpen(false)
    const newTitle = await useUIStore.getState().prompt({
      title: '重命名对话',
      placeholder: '输入新名称',
      required: true,
    })
    if (!newTitle) return
    try {
      await chatApi.updateConversation(convId, { title: newTitle })
      updateConversationTitle(convId, newTitle)
    } catch {
      useUIStore.getState().toast('重命名失败', 'error')
    }
  }, [convId, updateConversationTitle])

  const handlePin = useCallback(async () => {
    setMenuOpen(false)
    try {
      await chatApi.updateConversation(convId, { is_pinned: !isPinned })
      const { data } = await chatApi.getConversations()
      setConversations(data)
    } catch {
      useUIStore.getState().toast('操作失败', 'error')
    }
  }, [convId, isPinned, setConversations])

  const handleDelete = useCallback(async () => {
    setMenuOpen(false)
    const confirmed = await useUIStore.getState().confirm({
      title: '删除对话',
      message: '确定要删除此对话吗？此操作无法恢复。',
      danger: true,
    })
    if (!confirmed) return
    try {
      await chatApi.deleteConversation(convId)
      onDeleted()
    } catch {
      useUIStore.getState().toast('删除失败', 'error')
    }
  }, [convId, onDeleted])

  const handleExport = useCallback(async (format: 'pdf' | 'docx' | 'txt') => {
    setMenuOpen(false)
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
  }, [convId, title])

  return (
    <div
      className="glass-header shrink-0 sticky top-0 flex items-center h-11 px-6 border-b z-10"
      style={{ borderColor: 'var(--border)' }}
    >
      {/* 左侧占位（平衡右侧按钮宽度） */}
      <div className="w-8 shrink-0" />

      {/* 居中标题 */}
      <div className="flex-1 flex justify-center min-w-0">
        <span
          className="text-sm font-semibold truncate"
          style={{ color: 'var(--text)', maxWidth: '60%' }}
        >
          {title}
        </span>
      </div>

      {/* 右侧操作 */}
      <div className="relative shrink-0" ref={menuRef}>
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="flex items-center justify-center w-8 h-8 rounded-md cursor-pointer transition-colors duration-150 hover-gray"
          style={{ color: 'var(--text-secondary)' }}
        >
          <EllipsisOutlined style={{ fontSize: 18 }} />
        </button>

        {menuOpen && (
          <div
            className="absolute right-0 top-full mt-1.5 py-1.5 rounded-lg border z-50"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              minWidth: 164,
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0, 0, 0, 0.04)',
              animation: 'popover-in 0.15s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          >
            {/* 重命名 */}
            <button onClick={handleRename} className="chat-menu-item">
              <EditOutlined style={{ fontSize: 14 }} />
              重命名
            </button>

            {/* 置顶 */}
            <button onClick={handlePin} className="chat-menu-item">
              {isPinned ? <PushpinFilled style={{ fontSize: 14 }} /> : <PushpinOutlined style={{ fontSize: 14 }} />}
              {isPinned ? '取消置顶' : '置顶'}
            </button>

            {/* 导出会话 — hover 展开子菜单 */}
            <div className="export-menu-trigger">
              <div className="chat-menu-item" style={{ cursor: 'default' }}>
                <ExportOutlined style={{ fontSize: 14 }} />
                导出会话
                <RightOutlined style={{ fontSize: 10, marginLeft: 'auto', color: 'var(--text-muted)' }} />
              </div>
              <div className="export-submenu">
                <button onClick={() => handleExport('pdf')} className="chat-menu-item">
                  <FilePdfOutlined style={{ fontSize: 14, color: '#ef4444' }} />
                  PDF
                </button>
                <button onClick={() => handleExport('docx')} className="chat-menu-item">
                  <FileWordOutlined style={{ fontSize: 14, color: '#2563eb' }} />
                  Word
                </button>
                <button onClick={() => handleExport('txt')} className="chat-menu-item">
                  <FileTextOutlined style={{ fontSize: 14, color: 'var(--text-secondary)' }} />
                  TXT
                </button>
              </div>
            </div>

            {/* 分割线 */}
            <div style={{ height: 1, background: 'var(--border)', margin: '4px 12px' }} />

            {/* 删除 */}
            <button onClick={handleDelete} className="chat-menu-item danger">
              <DeleteOutlined style={{ fontSize: 14 }} />
              删除
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
