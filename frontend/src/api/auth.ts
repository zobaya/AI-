import client from './client'

export interface LoginParams {
  phone: string
  password: string
}

export interface UserInfo {
  id: number
  username: string
  phone: string
  role: 'user' | 'dept_admin' | 'sys_admin'
  department: { id: number; name: string } | null
  avatar: string | null
  date_joined: string
}

export const authApi = {
  login: (params: LoginParams) =>
    client.post<{ access: string; user: UserInfo }>('/api/auth/login/', params),

  logout: () =>
    client.post('/api/auth/logout/'),

  getProfile: () =>
    client.get<UserInfo>('/api/auth/profile/'),

  changePassword: (oldPassword: string, newPassword: string) =>
    client.put('/api/auth/profile/', { old_password: oldPassword, new_password: newPassword }),

  uploadAvatar: (file: File) => {
    const formData = new FormData()
    formData.append('avatar', file)
    return client.post<{ avatar: string }>('/api/auth/avatar/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  deleteAvatar: () =>
    client.delete<{ avatar: null }>('/api/auth/avatar/'),
}
