import client from './client'
import { useAuthStore } from '@/stores/authStore'

export interface Attachment {
  id: number
  file_name: string
  file_path_minio: string
  file_size: number
  content_type: string
  created_at: string
}

export interface Conversation {
  id: number
  title: string
  folder: { id: number; name: string } | null
  is_pinned: boolean
  message_count: number
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  workflow_id: string
  feedback: 'like' | 'dislike' | null
  feedback_detail: { reasons: string[]; comment?: string } | null
  metadata_json: Record<string, unknown>
  tokens_used: number
  attachments: Attachment[]
  created_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export interface SendChatParams {
  query: string
  conversation_id?: number | null
  file_paths?: string[]
  file_names?: string[]
  allowed_tools?: string[] | null
}

export interface PromptItem {
  id: number
  title: string
  content: string
  is_system: boolean
  created_at: string
  updated_at: string
}

export const chatApi = {
  // 会话
  getConversations: (params?: { folder_id?: number; search?: string }) =>
    client.get<Conversation[]>('/api/chat/conversations/', { params }),

  getConversationsForUser: (userId: number) =>
    client.get<Conversation[]>('/api/chat/conversations/', { params: { user_id: userId } }),

  getConversation: (id: number) =>
    client.get<ConversationDetail>(`/api/chat/conversations/${id}/`),

  createConversation: (data?: { title?: string; folder_id?: number }) =>
    client.post<Conversation>('/api/chat/conversations/', data),

  updateConversation: (id: number, data: { title?: string; folder_id?: number | null; is_pinned?: boolean }) =>
    client.patch<Conversation>(`/api/chat/conversations/${id}/`, data),

  deleteConversation: (id: number) =>
    client.delete(`/api/chat/conversations/${id}/`),

  // 消息截断（重新生成 / 编辑重发）
  truncateMessages: (convId: number, fromMessageId: number) =>
    client.delete(`/api/chat/conversations/${convId}/messages/`, {
      data: { from_message_id: fromMessageId },
    }),

  // 会话导出
  exportConversation: (id: number, format: 'pdf' | 'docx' | 'txt') =>
    client.get(`/api/chat/conversations/${id}/export/`, {
      params: { export_format: format },
      responseType: 'blob',
    }),

  // 消息反馈
  setFeedback: (messageId: number, feedback: 'like' | 'dislike', feedbackDetail?: {
    reasons: string[]
    comment?: string
  }) =>
    client.post(`/api/chat/messages/${messageId}/feedback/`, {
      feedback,
      feedback_detail: feedbackDetail,
    }),

  // 文件上传
  uploadFiles: (files: File[]) => {
    const formData = new FormData()
    files.forEach((f) => formData.append('files', f))
    return client.post<{ paths: string[]; names: string[] }>('/api/chat/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  // 文件夹
  getFolders: () => client.get('/api/chat/folders/'),
  createFolder: (name: string) => client.post('/api/chat/folders/', { name }),
  updateFolder: (id: number, data: { name?: string; sort_order?: number }) =>
    client.put(`/api/chat/folders/${id}/`, data),
  deleteFolder: (id: number) => client.delete(`/api/chat/folders/${id}/`),

  // 快捷提示词
  getPrompts: () => client.get<PromptItem[]>('/api/chat/prompts/'),
  createPrompt: (data: { title: string; content: string }) =>
    client.post<PromptItem>('/api/chat/prompts/', data),
  deletePrompt: (id: number) => client.delete(`/api/chat/prompts/${id}/`),
}

/** SSE 流式聊天 — 直接 fetch，绕过 axios */
export function streamChat(
  params: SendChatParams,
  onEvent: (event: string, data: Record<string, unknown>) => void,
  onError?: (err: Error) => void,
  onDone?: (conversationId: number) => void,
): AbortController {
  const controller = new AbortController()
  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
  const token = useAuthStore.getState().accessToken

  fetch(`${API_BASE}/api/chat/send/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(params),
    signal: controller.signal,
  })
    .then(async (resp) => {
      const convId = resp.headers.get('Conversation-Id')
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentEvent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              onEvent(currentEvent, data)
            } catch {
              // skip malformed JSON
            }
          }
        }
      }
      if (onDone) onDone(convId ? parseInt(convId) : 0)
    })
    .catch((err) => {
      if (err.name !== 'AbortError' && onError) onError(err)
    })

  return controller
}

/** 下载 AI 生成的文件（通过 file_id，JWT 认证） */
export async function downloadGeneratedFile(fileId: number, fileName: string): Promise<void> {
  const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
  const token = useAuthStore.getState().accessToken

  const resp = await fetch(`${API_BASE}/api/chat/files/${fileId}/download/`, {
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })

  if (!resp.ok) throw new Error('下载失败')

  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

/** PPT 文件标记信息 */
export interface PPTFileInfo {
  file_id: number | null
  file_name: string
  file_size: number
  slide_count: number
  theme: string
}

/** 从 Markdown 内容中解析 PPT 文件标记 */
export function parsePPTFileMarkers(content: string): {
  cleanContent: string
  files: PPTFileInfo[]
} {
  const files: PPTFileInfo[] = []
  const markerRegex = /<!--PPT_FILE:(.+?)-->/g
  const cleanContent = content.replace(markerRegex, (_match, jsonStr) => {
    try {
      const info = JSON.parse(jsonStr)
      files.push(info)
    } catch {
      // 忽略格式错误的标记
    }
    return ''
  })
  return { cleanContent, files }
}

/** 生成文件记录（列表页用） */
export interface GeneratedFileItem {
  id: number
  file_name: string
  file_size: number
  file_type: string
  slide_count: number
  theme: string
  conversation_id: number | null
  created_at: string
}

/** 获取用户的生成文件列表 */
export async function fetchGeneratedFiles(fileType?: string): Promise<GeneratedFileItem[]> {
  const params = fileType ? { file_type: fileType } : undefined
  const { data } = await client.get<{ files: GeneratedFileItem[] }>('/api/chat/files/', { params })
  return data.files
}

/** 删除生成文件 */
export async function deleteGeneratedFile(id: number): Promise<void> {
  await client.delete('/api/chat/files/', { data: { id } })
}

// ── 用户记忆 ──────────────────────────────────────────────────────

export interface MemoryItem {
  id: number
  fact: string
  category: 'preference' | 'knowledge' | 'goal' | 'context'
  confidence: number
  source_conv_id: number | null
  created_at: string
  updated_at: string
  access_count: number
}

export const memoryApi = {
  list: () =>
    client.get<{ facts: MemoryItem[] }>('/api/chat/memory/', {
      params: { limit: 999 },
    }),

  create: (data: { fact: string; category: string }) =>
    client.post<{ created: number; facts: MemoryItem[] }>('/api/chat/memory/batch/', {
      facts: [data],
      agent_name: 'default',
    }),

  delete: (id: number) => client.delete(`/api/chat/memory/${id}/`),
}
