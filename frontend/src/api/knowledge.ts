import client from './client'

// ── 类型定义 ──────────────────────────────────────────────────

export interface TagRef {
  id: number
  name: string
}

export interface KnowledgeBaseItem {
  kb_id: string
  name: string
  department: { id: number; name: string }
  description: string
  created_by: { id: number; username: string } | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface DocumentItem {
  doc_id: string
  file_name: string
  minio_path: string
  file_size: number
  category_l1: TagRef | null
  category_l2: TagRef | null
  status: string
  is_active: boolean
  task_id: string
  uploaded_by: string | null
  created_at: string
  updated_at: string
}

export interface ChunkItem {
  chunk_id: string
  kb_id: string
  doc_id: string
  is_active: boolean
  content: string
  department: string | null
  category_l1: string | null
  category_l2: string | null
  parent_id: string | null
  chunk_level: number
  chunk_length: number
  file_name: string | null
  headers: string
  upload_time: string | null
  update_time: string | null
  delete_time: string | null
}

export interface TaskStatus {
  task_id: string
  status: string // PENDING | STARTED | PROGRESS | SUCCESS | FAILURE
  progress: number
  message: string
  current_step?: string
}

export interface DocumentListResponse {
  kb_id: string
  total: number
  documents: DocumentItem[]
}

export interface ChunkListResponse {
  kb_id: string
  doc_id: string | null
  total: number
  chunks: ChunkItem[]
}

export interface ChunkDetailResponse {
  chunks: ChunkItem[]
  total: number
}

// ── API ───────────────────────────────────────────────────────

export const knowledgeApi = {
  // ── 知识库 (KB) CRUD ──
  /** 知识库列表 */
  getBases: () =>
    client.get<KnowledgeBaseItem[]>('/api/knowledge/bases/'),

  /** 创建知识库（kb_id 由后端自动生成） */
  createBase: (data: { name: string; department_id: number; description?: string }) =>
    client.post<KnowledgeBaseItem>('/api/knowledge/bases/', data),

  /** 知识库详情 */
  getBase: (kbId: string) =>
    client.get<KnowledgeBaseItem>(`/api/knowledge/bases/${kbId}/`),

  /** 更新知识库 */
  updateBase: (kbId: string, data: { name?: string; description?: string; department_id?: number; is_active?: boolean }) =>
    client.put(`/api/knowledge/bases/${kbId}/`, data),

  /** 删除知识库 */
  deleteBase: (kbId: string) =>
    client.delete(`/api/knowledge/bases/${kbId}/`),

  // ── 文档管理 ──
  /** 文档列表 */
  getDocuments: (params?: Record<string, string | number>) =>
    client.get<DocumentListResponse>('/api/knowledge/documents/', { params }),

  /** 上传文档 */
  uploadDocument: async (
    file: File,
    options?: {
      kb_id?: string
      category_l1_id?: number
      category_l2_id?: number
    },
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    if (options?.kb_id) formData.append('kb_id', options.kb_id)
    if (options?.category_l1_id) formData.append('category_l1_id', String(options.category_l1_id))
    if (options?.category_l2_id) formData.append('category_l2_id', String(options.category_l2_id))
    return client.post('/api/knowledge/documents/upload/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    })
  },

  /** 删除文档 */
  deleteDocument: (docId: string, hard?: boolean) =>
    client.delete(`/api/knowledge/documents/${docId}/`, { params: { hard: hard || false } }),

  /** 启用文档 */
  enableDocument: (docId: string) =>
    client.post(`/api/knowledge/documents/${docId}/enable/`),

  /** 禁用文档 */
  disableDocument: (docId: string) =>
    client.post(`/api/knowledge/documents/${docId}/disable/`),

  /** 更新文档元数据 */
  updateDocumentMetadata: (
    docId: string,
    data: {
      file_name?: string
      category_l1_id?: number | null
      category_l2_id?: number | null
    },
  ) => client.put(`/api/knowledge/documents/${docId}/metadata/`, data),

  /** 获取文档的父块列表 */
  getDocumentChunks: (docId: string, includeInactive = true) =>
    client.get<ChunkListResponse>(`/api/knowledge/chunks/`, {
      params: { doc_id: docId, chunk_level: 1, include_inactive: includeInactive },
    }),

  /** 获取某个父块的子块 */
  getChildChunks: (parentId: string) =>
    client.get<ChunkListResponse>(`/api/knowledge/chunks/`, {
      params: { parent_id: parentId },
    }),

  /** 获取单个分块详情 */
  getChunk: (chunkId: string) =>
    client.get<ChunkItem>(`/api/knowledge/chunks/${chunkId}/`),

  /** 更新分块（修改内容会触发子块重建） */
  updateChunk: (
    chunkId: string,
    data: {
      content?: string
      department?: string
      category_l1?: string
      category_l2?: string
      is_active?: boolean
    },
  ) => client.put(`/api/knowledge/chunks/${chunkId}/`, data),

  /** 删除分块 */
  deleteChunk: (chunkId: string, hard?: boolean) =>
    client.delete(`/api/knowledge/chunks/${chunkId}/`, { params: { hard: hard || false } }),

  /** 启用分块 */
  enableChunk: (chunkId: string) =>
    client.post(`/api/knowledge/chunks/${chunkId}/enable/`),

  /** 禁用分块 */
  disableChunk: (chunkId: string) =>
    client.post(`/api/knowledge/chunks/${chunkId}/disable/`),

  /** 查询上传任务状态 */
  getTaskStatus: (taskId: string) =>
    client.get<TaskStatus>(`/api/knowledge/tasks/${taskId}/`),

  /** 轮询任务状态直到完成 */
  pollTaskStatus: (
    taskId: string,
    onProgress: (status: TaskStatus) => void,
    interval = 2000,
  ): Promise<TaskStatus> =>
    new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          const { data } = await client.get<TaskStatus>(`/api/knowledge/tasks/${taskId}/`)
          onProgress(data)
          if (data.status === 'SUCCESS') {
            resolve(data)
          } else if (data.status === 'FAILURE') {
            reject(new Error(data.message || '任务失败'))
          } else {
            setTimeout(poll, interval)
          }
        } catch (e) {
          reject(e)
        }
      }
      poll()
    }),

  /** 标签列表 */
  getTags: () => client.get('/api/knowledge/tags/'),
}
