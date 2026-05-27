import { useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { chatApi, streamChat } from '@/api/chat'
import { useChatStore } from '@/stores/chatStore'

// ── 类型 ──────────────────────────────────────────────────────

export type Phase = 'idle' | 'rewrite' | 'thinking' | 'tool' | 'answering'

export interface StreamingStep {
  type: 'rewrite' | 'think' | 'tool' | 'answer'
  content: string
  toolName?: string
  done: boolean
}

export interface StreamingMessage {
  entries: Array<Record<string, unknown>>
  steps: StreamingStep[]
  fullAnswer: string
  suggestQuestions: string[]
}

// ── Hook ──────────────────────────────────────────────────────

export function useChatStream() {
  const navigate = useNavigate()
  const {
    conversations,
    currentConvId,
    setConversations,
    setCurrentConvId,
    addMessage,
    setPhase: setStorePhase,
    setIsGenerating,
    setAbortController,
    updateConversationTitle,
  } = useChatStore()

  // 流式状态
  const [streamingMessage, setStreamingMessage] = useState<StreamingMessage | null>(null)
  const [isGenerating, setIsGeneratingState] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')

  // 内部 refs（不触发重渲染，由 setStreamingMessage 统一驱动渲染）
  const stepsRef = useRef<StreamingStep[]>([])
  const fullAnswerRef = useRef('')
  const collectedEntriesRef = useRef<Array<Record<string, unknown>>>([])
  const thinkBufRef = useRef('')
  const suggestQuestionsRef = useRef<string[]>([])

  /** 流式生成中标记：防止 navigate 触发 useEffect 重复加载 */
  const generatingRef = useRef(false)

  // ── SSE 事件处理 ─────────────────────────────────────────

  const flushThinkBuffer = () => {
    if (thinkBufRef.current) {
      collectedEntriesRef.current.push({ event: 'think', content: thinkBufRef.current })
      thinkBufRef.current = ''
    }
  }

  const pushStreamingUpdate = () => {
    setStreamingMessage({
      entries: [...collectedEntriesRef.current],
      steps: [...stepsRef.current],
      fullAnswer: fullAnswerRef.current,
      suggestQuestions: [...suggestQuestionsRef.current],
    })
  }

  const handleEvent = useCallback((event: string, data: Record<string, unknown>) => {
    // ── 收集 entries ──
    if (event === 'think') {
      thinkBufRef.current += String(data.content || data.message || '')
    } else {
      flushThinkBuffer()
      if (event === 'progress' || event === 'title' || event === 'maybe' || event === 'error') {
        collectedEntriesRef.current.push({ event, ...data })
      }
    }

    // ── 更新 steps ──
    switch (event) {
      case 'progress': {
        const msg = String(data.message || '')
        const lastStep = stepsRef.current[stepsRef.current.length - 1]

        if (msg.includes('调用工具')) {
          const toolName = msg.replace(/^调用工具[：:]\s*/, '').trim() || msg
          if (lastStep?.type === 'tool') {
            lastStep.toolName = toolName
          } else {
            stepsRef.current.push({ type: 'tool', content: '', toolName, done: false })
          }
          setPhase('tool')
          setStorePhase('tool')
        } else if (msg.includes('查询已优化')) {
          const rewriteStep = stepsRef.current.find((s) => s.type === 'rewrite')
          if (rewriteStep) {
            rewriteStep.content = msg.replace(/.*查询已优化[：:]\s*/, '').trim()
            rewriteStep.done = true
          }
        } else if (msg.includes('优化')) {
          stepsRef.current.push({ type: 'rewrite', content: '处理中...', done: false })
          setPhase('rewrite')
          setStorePhase('rewrite')
        } else if (lastStep?.type === 'tool' && msg.trim()) {
          // 工具执行过程中的中间 progress 消息（检索结果、分类、评估等）归入工具内容
          lastStep.content = lastStep.content
            ? lastStep.content + '\n' + msg
            : msg
        }
        break
      }
      case 'think': {
        const text = String(data.content || data.message || '')
        if (!text) break
        const lastStep = stepsRef.current[stepsRef.current.length - 1]
        if (lastStep?.type === 'think') {
          lastStep.content += text
        } else {
          stepsRef.current.push({ type: 'think', content: text, done: false })
        }
        setPhase('thinking')
        setStorePhase('thinking')
        break
      }
      case 'output': {
        const text = String(data.content || '')
        if (!text) break
        const lastStep = stepsRef.current[stepsRef.current.length - 1]
        if (lastStep?.type === 'answer') {
          lastStep.content += text
        } else {
          if (lastStep) lastStep.done = true
          stepsRef.current.push({ type: 'answer', content: text, done: false })
        }
        fullAnswerRef.current += text
        setPhase('answering')
        setStorePhase('answering')
        break
      }
      case 'title': {
        const title = String(data.content || '').trim()
        const latestConvId = useChatStore.getState().currentConvId
        if (title && latestConvId) {
          updateConversationTitle(latestConvId, title)
        }
        break
      }
      case 'maybe': {
        const questions = (data.questions as string[]) || []
        if (questions.length) {
          suggestQuestionsRef.current = questions.slice(0, 3)
        }
        break
      }
      case 'error': {
        console.error('SSE error:', data.message)
        break
      }
    }

    pushStreamingUpdate()
  }, [setPhase, setStorePhase, updateConversationTitle])

  // ── 发送消息 ─────────────────────────────────────────────

  const send = useCallback(
    async (query: string, filePaths?: string[], fileNames?: string[], tools?: string[] | null) => {
      // 重置所有状态
      stepsRef.current = []
      fullAnswerRef.current = ''
      collectedEntriesRef.current = []
      thinkBufRef.current = ''
      suggestQuestionsRef.current = []
      setPhase('idle')
      setStorePhase('idle')
      setStreamingMessage(null)
      setIsGeneratingState(true)
      setIsGenerating(true)
      generatingRef.current = true

      // 从 store 实时读取 currentConvId（避免闭包陈旧）
      let convIdNow = useChatStore.getState().currentConvId

      // 无会话时先创建，让侧边栏立刻出现新对话
      if (!convIdNow) {
        try {
          const { data: conv } = await chatApi.createConversation()
          convIdNow = conv.id
          const store = useChatStore.getState()
          store.setCurrentConvId(conv.id)
          store.setConversations([conv, ...store.conversations])
          navigate(`/chat/${conv.id}`, { replace: true })
        } catch (e) {
          console.error('创建会话失败:', e)
          setIsGeneratingState(false)
          setIsGenerating(false)
          generatingRef.current = false
          return
        }
      }

      // 本地添加用户消息（临时负 ID）
      useChatStore.getState().addMessage({
        id: -Date.now(),
        role: 'user',
        content: query,
        workflow_id: '',
        feedback: null,
        metadata_json: {},
        tokens_used: 0,
        attachments: (fileNames || []).map((name, i) => ({
          id: -(i + 1),
          file_name: name,
          file_path_minio: filePaths?.[i] || '',
          file_size: 0,
          content_type: '',
          created_at: new Date().toISOString(),
        })),
        created_at: new Date().toISOString(),
      })

      // 启动 SSE 流式请求
      const controller = streamChat(
        {
          query,
          conversation_id: convIdNow || null,
          file_paths: filePaths,
          file_names: fileNames,
          allowed_tools: tools,
        },
        handleEvent,
        // onError
        (err) => {
          console.error('Stream error:', err)
          setIsGeneratingState(false)
          setIsGenerating(false)
          generatingRef.current = false
          // 保留已生成的部分
          if (fullAnswerRef.current.trim()) {
            flushThinkBuffer()
            useChatStore.getState().addMessage({
              id: Date.now(),
              role: 'assistant',
              content: fullAnswerRef.current.trim(),
              workflow_id: '',
              feedback: null,
              metadata_json: collectedEntriesRef.current.length > 0
                ? { entries: collectedEntriesRef.current }
                : {},
              tokens_used: 0,
              attachments: [],
              created_at: new Date().toISOString(),
            })
          }
          setStreamingMessage(null)
        },
        // onDone — 流式完成
        (newConvId) => {
          const store = useChatStore.getState()
          const effectiveConvId = store.currentConvId || newConvId || 0

          // flush 最后的 think buffer
          flushThinkBuffer()

          // 先用本地消息立即显示（id 用 Date.now() 临时占位）
          if (fullAnswerRef.current.trim()) {
            store.addMessage({
              id: Date.now(),
              role: 'assistant',
              content: fullAnswerRef.current.trim(),
              workflow_id: '',
              feedback: null,
              metadata_json: collectedEntriesRef.current.length > 0
                ? { entries: collectedEntriesRef.current }
                : {},
              tokens_used: 0,
              attachments: [],
              created_at: new Date().toISOString(),
            })
          }

          // 如果是新创建的对话，更新 URL
          if (!store.currentConvId && effectiveConvId) {
            setCurrentConvId(effectiveConvId)
            navigate(`/chat/${effectiveConvId}`, { replace: true })
          }

          // 从 API 重新加载消息，获取真实数据库 ID（用于点赞/点踩等操作）
          if (effectiveConvId) {
            chatApi.getConversation(effectiveConvId).then(({ data }) => {
              store.setMessages(data.messages)
            })
          }

          // 刷新侧边栏会话列表
          chatApi.getConversations().then(({ data }) => setConversations(data))

          // 清理流式状态
          setStreamingMessage(null)
          setIsGeneratingState(false)
          setIsGenerating(false)
          generatingRef.current = false
        },
      )
      setAbortController(controller)
    },
    [handleEvent, navigate, setCurrentConvId, setConversations, setIsGenerating, setAbortController, setStorePhase],
  )

  // ── 停止生成 ─────────────────────────────────────────────

  const stop = useCallback(() => {
    const ctrl = useChatStore.getState().abortController
    if (ctrl) ctrl.abort()
    setAbortController(null)
    setIsGeneratingState(false)
    setIsGenerating(false)
    generatingRef.current = false

    // 保留已生成的部分为正式消息（先用临时 ID 立即显示）
    flushThinkBuffer()
    if (fullAnswerRef.current.trim()) {
      useChatStore.getState().addMessage({
        id: Date.now(),
        role: 'assistant',
        content: fullAnswerRef.current.trim(),
        workflow_id: '',
        feedback: null,
        metadata_json: collectedEntriesRef.current.length > 0
          ? { entries: collectedEntriesRef.current }
          : {},
        tokens_used: 0,
        attachments: [],
        created_at: new Date().toISOString(),
      })
    }

    // 从 API 重新加载消息以获取真实数据库 ID
    const convId = useChatStore.getState().currentConvId
    if (convId) {
      chatApi.getConversation(convId).then(({ data }) => {
        useChatStore.getState().setMessages(data.messages)
      })
    }

    setStreamingMessage(null)
  }, [setAbortController, setIsGenerating])

  return {
    streamingMessage,
    isGenerating,
    phase,
    send,
    stop,
    generatingRef,
  }
}
