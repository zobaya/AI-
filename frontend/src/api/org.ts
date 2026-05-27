import client from './client'

// ── 类型 ──────────────────────────────────────────────────────

export interface DepartmentItem {
  id: number
  name: string
  description: string
  member_count: number
}

export interface UserItem {
  id: number
  username: string
  phone: string
  role: string
  department: { id: number; name: string } | null
  avatar: string | null
  is_active: boolean
  date_joined: string
}

export interface KBPermission {
  kb_id: string
  name: string
}

export interface AgentPermission {
  agent_name: string
}

export interface OverviewData {
  total_users: number
  active_users: number
  total_conversations: number
  like_count: number
  dislike_count: number
  satisfaction_rate: number
}

export interface TrendItem {
  date: string
  count: number
}

export interface DeptCompareItem {
  department: string
  user_count: number
  conversation_count: number
}

export interface FeedbackItem {
  id: number
  conversation_id: number
  user: string
  department: string
  conversation_title: string
  content_preview: string
  feedback: 'like' | 'dislike'
  feedback_detail: { reasons: string[]; comment?: string } | null
  created_at: string
}

export interface FeedbackListResponse {
  total: number
  page: number
  page_size: number
  data: FeedbackItem[]
}

export interface UserStatsItem {
  id: number
  username: string
  department: string
  conversation_count: number
  message_count: number
  tokens_used: number
  last_active: string
}

// ── 部门管理 ──────────────────────────────────────────────────

export const orgApi = {
  // 部门
  getDepartments: () =>
    client.get<DepartmentItem[]>('/api/org/departments/'),

  createDepartment: (name: string, description?: string) =>
    client.post('/api/org/departments/', { name, description }),

  updateDepartment: (id: number, data: { name?: string; description?: string }) =>
    client.put(`/api/org/departments/${id}/`, data),

  deleteDepartment: (id: number) =>
    client.delete(`/api/org/departments/${id}/`),

  // 用户
  getUsers: (params?: { search?: string; page?: number; page_size?: number }) =>
    client.get<{ data: UserItem[]; total: number }>('/api/org/users/', { params }),

  createUser: (data: { username: string; password: string; phone: string; role: string; department_id?: number }) =>
    client.post('/api/org/users/create/', data),

  resetPassword: (userId: number, newPassword?: string) =>
    client.post(`/api/org/users/${userId}/reset-password/`, { new_password: newPassword }),

  updateUser: (userId: number, data: { username?: string; phone?: string; role?: string; department_id?: number | null }) =>
    client.put(`/api/org/users/${userId}/`, data),

  toggleActive: (userId: number) =>
    client.post(`/api/org/users/${userId}/toggle-active/`),

  transferUser: (userId: number, departmentId: number) =>
    client.post(`/api/org/users/${userId}/transfer/`, { department_id: departmentId }),

  deleteUser: (userId: number) =>
    client.delete(`/api/org/users/${userId}/`),

  batchImport: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/api/org/users/batch-import/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  // 权限
  getKBPermissions: (userId: number) =>
    client.get<KBPermission[]>(`/api/org/users/${userId}/kb-permissions/`),

  setKBPermissions: (userId: number, kbIds: string[]) =>
    client.post(`/api/org/users/${userId}/kb-permissions/`, { kb_ids: kbIds }),

  getAgentPermissions: (userId: number) =>
    client.get<AgentPermission[]>(`/api/org/users/${userId}/agent-permissions/`),

  setAgentPermissions: (userId: number, agentNames: string[]) =>
    client.post(`/api/org/users/${userId}/agent-permissions/`, { agent_names: agentNames }),
}

// ── 统计看板 ──────────────────────────────────────────────────

export const dashboardApi = {
  getOverview: () =>
    client.get<OverviewData>('/api/dashboard/overview/'),

  getTrend: () =>
    client.get<TrendItem[]>('/api/dashboard/trend/'),

  getDeptCompare: () =>
    client.get<DeptCompareItem[]>('/api/dashboard/departments-compare/'),

  getExportData: () =>
    client.get('/api/dashboard/export/'),

  getFeedbackList: (params: {
    feedback?: string
    search?: string
    department_id?: number
    date_start?: string
    date_end?: string
    page?: number
    page_size?: number
  }) => client.get<FeedbackListResponse>('/api/dashboard/feedback/', { params }),

  exportFeedback: (params: {
    feedback?: string
    search?: string
    department_id?: number
    date_start?: string
    date_end?: string
  }) => client.get('/api/dashboard/feedback/export/', { params, responseType: 'blob' }),

  getUserStats: (params: { search?: string; department_id?: number; page?: number; page_size?: number }) =>
    client.get<{ data: UserStatsItem[]; total: number }>('/api/dashboard/user-stats/', { params }),
}
