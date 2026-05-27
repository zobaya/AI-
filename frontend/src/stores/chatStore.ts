import { create } from 'zustand'
import type { Message } from '@/api/chat'

type Phase = 'idle' | 'rewrite' | 'thinking' | 'tool' | 'answering'

interface ChatState {
  conversations: Array<{
    id: number
    title: string
    folder: { id: number; name: string } | null
    is_pinned: boolean
    message_count: number
    updated_at: string
  }>
  currentConvId: number | null
  messages: Message[]
  phase: Phase
  isGenerating: boolean
  abortController: AbortController | null

  setConversations: (list: ChatState['conversations']) => void
  setCurrentConvId: (id: number | null) => void
  setMessages: (msgs: Message[]) => void
  addMessage: (msg: Message) => void
  updateLastAssistantMessage: (content: string) => void
  setPhase: (phase: Phase) => void
  setIsGenerating: (v: boolean) => void
  setAbortController: (c: AbortController | null) => void
  updateConversationTitle: (id: number, title: string) => void
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  currentConvId: null,
  messages: [],
  phase: 'idle',
  isGenerating: false,
  abortController: null,

  setConversations: (list) => set({ conversations: list }),
  setCurrentConvId: (id) => set({ currentConvId: id }),
  setMessages: (msgs) => set({ messages: msgs }),
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  updateLastAssistantMessage: (content) =>
    set((s) => {
      const msgs = [...s.messages]
      const lastIdx = msgs.findLastIndex((m) => m.role === 'assistant')
      if (lastIdx >= 0) {
        msgs[lastIdx] = { ...msgs[lastIdx], content }
      }
      return { messages: msgs }
    }),
  setPhase: (phase) => set({ phase }),
  setIsGenerating: (v) => set({ isGenerating: v }),
  setAbortController: (c) => set({ abortController: c }),
  updateConversationTitle: (id, title) =>
    set((s) => ({
      conversations: s.conversations.map((c) => (c.id === id ? { ...c, title } : c)),
    })),
}))
