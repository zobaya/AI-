import { create } from 'zustand'
import { authApi } from '@/api/auth'
import type { UserInfo } from '@/api/auth'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

interface AuthState {
  user: UserInfo | null
  accessToken: string | null
  isAuthenticated: boolean
  isInitialized: boolean
  setUser: (user: UserInfo | null) => void
  setAccessToken: (token: string | null) => void
  initialize: () => Promise<void>
  logout: () => Promise<void>
}

/** 给头像代理 URL 附加 access token + 时间戳，使 <img src> 能通过认证且不缓存 */
function patchAvatarUrl(user: UserInfo | null, token: string | null): UserInfo | null {
  if (!user || !user.avatar) return user
  if (!token) return user
  const base = user.avatar.split('?')[0]
  return { ...user, avatar: `${base}?token=${token}&t=${Date.now()}` }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  isInitialized: false,

  setUser: (user) => {
    const token = get().accessToken
    set({ user: patchAvatarUrl(user, token), isAuthenticated: !!user })
  },

  setAccessToken: (token) => {
    set({ accessToken: token, isAuthenticated: !!token })
    // token 变化时更新 avatar URL
    const user = get().user
    if (user) {
      set({ user: patchAvatarUrl(user, token) })
    }
  },

  initialize: async () => {
    try {
      // 用 Cookie 中的 refresh_token 换新的 access_token
      const { data } = await axios.post(`${API_BASE}/api/auth/token/refresh/`, null, {
        withCredentials: true,
      })
      const token = data.access
      set({ accessToken: token, isAuthenticated: true })
      // 获取用户信息
      const { data: profile } = await authApi.getProfile()
      set({ user: patchAvatarUrl(profile, token) })
    } catch {
      set({ accessToken: null, user: null, isAuthenticated: false })
    } finally {
      set({ isInitialized: true })
    }
  },

  logout: async () => {
    try {
      await authApi.logout()
    } catch {
      // 忽略退出请求失败
    }
    set({ accessToken: null, user: null, isAuthenticated: false })
    window.location.href = '/login'
  },
}))
