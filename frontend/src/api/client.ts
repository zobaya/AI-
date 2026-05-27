import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const client = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
})

// 请求拦截：从 Zustand 内存读 access token
client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 时用 Cookie 自动续期
client.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true
      try {
        // refresh_token 在 HttpOnly Cookie 中，浏览器自动携带
        const { data } = await axios.post(`${API_BASE}/api/auth/token/refresh/`, null, {
          withCredentials: true,
        })
        const newToken = data.access
        useAuthStore.getState().setAccessToken(newToken)
        // 刷新后重拼 avatar URL 中的 token
        const currentUser = useAuthStore.getState().user
        if (currentUser) {
          useAuthStore.getState().setUser(currentUser)
        }
        original.headers.Authorization = `Bearer ${newToken}`
        return client(original)
      } catch {
        // Cookie 续期失败，清理状态并跳转登录
        useAuthStore.getState().setAccessToken(null)
        useAuthStore.getState().setUser(null)
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export default client
