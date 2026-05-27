import { useEffect, useCallback, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { chatApi } from '@/api/chat'
import { useChatStore } from '@/stores/chatStore'
import { useChatStream } from '@/hooks/useChatStream'
import ChatSidebar from '@/components/Chat/ChatSidebar'
import ChatMessages, { type ChatMessagesHandle } from '@/components/Chat/ChatMessages'
import ChatInput from '@/components/Chat/ChatInput'
import ChatHeader from '@/components/Chat/ChatHeader'
import { useAuthStore } from '@/stores/authStore'
import { MessageOutlined } from '@ant-design/icons'

export default function Chat() {
  const { convId } = useParams<{ convId?: string }>()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const {
    conversations,
    currentConvId,
    messages,
    isGenerating: storeIsGenerating,
    setConversations,
    setCurrentConvId,
    setMessages,
    setIsGenerating,
    setAbortController,
  } = useChatStore()

  const { streamingMessage, isGenerating, send, stop, generatingRef } = useChatStream()

  // 截断消息并重新发送（用于重新生成和编辑重发）
  const handleResend = useCallback(async (deleteFromMsgId: number, query: string) => {
    if (!currentConvId) return
    await chatApi.truncateMessages(currentConvId, deleteFromMsgId)
    setMessages(messages.filter((m) => m.id < deleteFromMsgId))
    send(query)
  }, [currentConvId, messages, setMessages, send])
  const messagesRef = useRef<ChatMessagesHandle>(null)
  const [scrolledAway, setScrolledAway] = useState(false)

  // 加载会话列表
  useEffect(() => {
    chatApi.getConversations().then(({ data }) => setConversations(data))
  }, [setConversations])

  // 切换会话：加载消息（generatingRef 防止流式结束时 navigate 重复加载）
  useEffect(() => {
    if (generatingRef.current) return

    const id = convId ? parseInt(convId) : null
    if (id) {
      setCurrentConvId(id)
      chatApi.getConversation(id).then(({ data }) => {
        setMessages(data.messages)
      })
    } else {
      setCurrentConvId(null)
      setMessages([])
    }
  }, [convId, setCurrentConvId, setMessages])

  // 新建对话 — 回到首页，发送第一条消息时自动创建会话
  const handleNew = useCallback(() => {
    const store = useChatStore.getState()
    if (store.abortController) {
      store.abortController.abort()
      store.setAbortController(null)
    }
    setIsGenerating(false)
    store.setCurrentConvId(null)
    store.setMessages([])
    navigate('/chat', { replace: true })
  }, [navigate, setIsGenerating])

  // 是否为欢迎首页（无会话、无消息、无流式）
  const isWelcome = !currentConvId && messages.length === 0 && !streamingMessage
  const userName = user?.username || ''

  return (
    <div className="flex flex-col h-full">
      {/* 顶部栏 */}
      <div
        className="flex items-center h-12 border-b shrink-0 px-6"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <MessageOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>AI 问答</h2>
        </div>
        <span className="text-xs ml-3" style={{ color: 'var(--text-muted)' }}>
          {isGenerating ? '生成中...' : '就绪'}
        </span>
      </div>

      {/* 左右分栏 */}
      <div className="flex flex-1 overflow-hidden">
      {/* 聊天历史栏 */}
      <ChatSidebar onNew={handleNew} />

      {/* 主聊天区 */}
      <div className="flex flex-1 flex-col min-w-0" style={{ background: 'var(--surface)' }}>

        {isWelcome ? (
          /* ── 欢迎首页：文字 + 输入框垂直居中 ── */
          <div className="flex-1 flex flex-col items-center justify-center px-6 -mt-8">
            <div style={{ fontSize: 24, fontWeight: 700, marginBottom: 6, color: 'var(--text)' }}>
              {userName}{userName ? '，你好！' : '你好！'}
            </div>
            <div style={{ fontSize: 15, color: 'var(--text-muted)', marginBottom: 40 }}>
              需要我为你做些什么？
            </div>
            <div className="w-full max-w-3xl">
              <ChatInput
                onSend={send}
                onStop={stop}
                isGenerating={isGenerating}
                isWelcome={true}
              />
            </div>
          </div>
        ) : (
          /* ── 对话模式 ── */
          <>
            {currentConvId && (
              <ChatHeader
                convId={currentConvId}
                onDeleted={() => navigate('/chat', { replace: true })}
              />
            )}
            <ChatMessages
              ref={messagesRef}
              messages={messages}
              streamingMessage={streamingMessage}
              onSuggestClick={(q) => send(q)}
              onResend={handleResend}
              onScrollAway={setScrolledAway}
            />

            {scrolledAway && (
              <div className="flex justify-center -mt-2 relative z-10">
                <button
                  onClick={() => messagesRef.current?.scrollToBottom()}
                  className="flex items-center justify-center w-8 h-8 rounded-full cursor-pointer transition-all duration-200 shadow-md"
                  style={{
                    background: 'var(--surface)',
                    color: 'var(--primary)',
                    border: '1px solid var(--border)',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'var(--primary)'
                    e.currentTarget.style.color = '#fff'
                    e.currentTarget.style.borderColor = 'var(--primary)'
                    e.currentTarget.style.transform = 'scale(1.1)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'var(--surface)'
                    e.currentTarget.style.color = 'var(--primary)'
                    e.currentTarget.style.borderColor = 'var(--border)'
                    e.currentTarget.style.transform = 'scale(1)'
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 5v14M5 12l7 7 7-7" />
                  </svg>
                </button>
              </div>
            )}

            <ChatInput
              onSend={send}
              onStop={stop}
              isGenerating={isGenerating}
            />
          </>
        )}
      </div>
      </div>
    </div>
  )
}
