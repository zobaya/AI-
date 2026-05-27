import { useEffect, useState, useRef, useCallback } from 'react'
import { chatApi, type ConversationDetail, type Message } from '@/api/chat'
import { CloseOutlined } from '@ant-design/icons'
import { renderMarkdown } from '@/utils/markdown'

interface Props {
  conversationId: number
  highlightMessageId?: number
  feedbackData?: {
    feedback: 'like' | 'dislike'
    feedback_detail: { reasons: string[]; comment?: string } | null
  }
  onClose: () => void
}

export default function ChatSessionViewerDrawer({
  conversationId,
  highlightMessageId,
  feedbackData,
  onClose,
}: Props) {
  const [conversation, setConversation] = useState<ConversationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const highlightRef = useRef<HTMLDivElement>(null)
  const loadedRef = useRef(false)

  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    chatApi
      .getConversation(conversationId)
      .then(({ data }) => setConversation(data))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [conversationId])

  // 自动滚动到高亮消息
  useEffect(() => {
    if (conversation && highlightMessageId && highlightRef.current) {
      setTimeout(() => {
        highlightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 100)
    }
  }, [conversation, highlightMessageId])

  const handleOverlayClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose()
  }, [onClose])

  const messages = conversation?.messages ?? []

  return (
    <>
      <div className="drawer-overlay" onClick={handleOverlayClick} />
      <div className="drawer-panel chat-viewer-drawer">
        {/* 头部 */}
        <div
          className="flex items-center justify-between px-5 shrink-0"
          style={{
            height: 56,
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span className="text-base font-bold truncate" style={{ color: 'var(--text)' }}>
              {conversation?.title || '加载中...'}
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 flex items-center justify-center rounded-lg cursor-pointer transition-colors duration-150 hover:opacity-70"
            style={{ color: 'var(--text-muted)' }}
          >
            <CloseOutlined />
          </button>
        </div>

        {/* 消息列表 */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
          {loading ? (
            <div className="flex items-center justify-center h-32 text-sm" style={{ color: 'var(--text-muted)' }}>
              加载中...
            </div>
          ) : messages.length === 0 ? (
            <div className="flex items-center justify-center h-32 text-sm" style={{ color: 'var(--text-muted)' }}>
              暂无消息
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  msg={msg}
                  isHighlighted={msg.id === highlightMessageId}
                  highlightRef={msg.id === highlightMessageId ? highlightRef : undefined}
                  feedbackData={msg.id === highlightMessageId ? feedbackData : undefined}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}

/** 单条消息气泡（只读） */
function MessageBubble({
  msg,
  isHighlighted,
  highlightRef,
  feedbackData,
}: {
  msg: Message
  isHighlighted: boolean
  highlightRef?: React.RefObject<HTMLDivElement>
  feedbackData?: Props['feedbackData']
}) {
  const isUser = msg.role === 'user'

  // 高亮背景色
  let highlightBg = 'transparent'
  if (isHighlighted && feedbackData) {
    highlightBg =
      feedbackData.feedback === 'like'
        ? 'rgba(220, 252, 231, 0.5)'
        : 'rgba(254, 226, 226, 0.5)'
  }

  return (
    <div
      ref={highlightRef}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: isUser ? 'flex-end' : 'flex-start',
        background: highlightBg,
        borderRadius: 12,
        padding: isHighlighted ? '12px 16px' : undefined,
        margin: isHighlighted ? '-12px -16px' : undefined,
        transition: 'background 0.3s ease',
      }}
    >
      {isUser ? (
        /* ── 用户消息气泡 ── */
        <div
          style={{
            padding: '12px 18px',
            borderRadius: 18,
            borderBottomRightRadius: 4,
            maxWidth: '70%',
            fontSize: 'var(--text-base)',
            lineHeight: 1.7,
            whiteSpace: 'pre-wrap',
            background: 'linear-gradient(135deg, var(--primary), var(--primary-dark))',
            color: '#fff',
            boxShadow: '0 2px 10px rgba(0, 123, 255, 0.2)',
            wordBreak: 'break-word',
          }}
        >
          {msg.content}
          {msg.attachments && msg.attachments.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
              {msg.attachments.map((att) => (
                <span
                  key={att.id}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: 'var(--text-xs)',
                    background: 'rgba(255,255,255,0.15)',
                  }}
                >
                  {att.file_name}
                </span>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* ── AI 消息气泡 ── */
        <div style={{ maxWidth: '100%', padding: '12px 0' }}>
          <div
            className="answer-section"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
          />
        </div>
      )}

      {/* 高亮消息的反馈详情 */}
      {isHighlighted && feedbackData?.feedback_detail && (
        <div
          style={{
            marginTop: 8,
            maxWidth: isUser ? '70%' : '100%',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 6,
            alignItems: 'center',
          }}
        >
          {feedbackData.feedback_detail.reasons.map((r, i) => (
            <span
              key={i}
              style={{
                fontSize: 'var(--text-xs)',
                padding: '2px 10px',
                borderRadius: 12,
                background: feedbackData.feedback === 'like' ? '#dcfce7' : '#fee2e2',
                color: feedbackData.feedback === 'like' ? '#16a34a' : '#ef4444',
              }}
            >
              {r}
            </span>
          ))}
          {feedbackData.feedback_detail.comment && (
            <span
              style={{
                fontSize: 'var(--text-xs)',
                color: 'var(--text-muted)',
                fontStyle: 'italic',
              }}
            >
              {feedbackData.feedback_detail.comment}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
