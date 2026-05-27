import client from './client'

// ── 类型 ──────────────────────────────────────────────────────

export interface TagItem {
  id: number
  name: string
  description: string
  parent: number | null
  level: 1 | 2
  sort_order: number
  children?: TagItem[]
  created_by: string | null
  doc_count: number
  created_at: string
  updated_at: string
}

export interface RelatedDoc {
  id: number
  file_name: string
  kb_name: string | null
}

// ── 标签管理 ──────────────────────────────────────────────────

export const tagsApi = {
  getTree: () =>
    client.get<TagItem[]>('/api/tags/'),

  create: (data: { name: string; description?: string; parent_id?: number | null }) =>
    client.post<TagItem>('/api/tags/create/', data),

  update: (id: number, data: { name?: string; description?: string; sort_order?: number }) =>
    client.put(`/api/tags/${id}/`, data),

  delete: (id: number) =>
    client.delete(`/api/tags/${id}/`),

  getDocuments: (id: number) =>
    client.get<{ documents: RelatedDoc[]; total: number }>(`/api/tags/${id}/documents/`),
}
