import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'

export default function Login() {
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const setUser = useAuthStore((s) => s.setUser)
  const setAccessToken = useAuthStore((s) => s.setAccessToken)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await authApi.login({ phone, password })
      setAccessToken(data.access)
      setUser(data.user)
      navigate('/chat', { replace: true })
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string; non_field_errors?: string[] } } })?.response?.data?.detail ||
        (err as { response?: { data?: { detail?: string; non_field_errors?: string[] } } })?.response?.data?.non_field_errors?.[0] ||
        '登录失败，请检查手机号和密码'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="flex items-center justify-center h-screen"
      style={{ background: 'var(--bg)' }}
    >
      <div
        className="w-full max-w-sm p-8 rounded-xl shadow-lg"
        style={{ background: 'var(--surface)' }}
      >
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center w-14 h-14 rounded-2xl text-white text-2xl font-bold mb-4"
            style={{ background: 'var(--primary)' }}
          >
            AI
          </div>
          <h1 className="text-xl font-semibold" style={{ color: 'var(--text)' }}>
            智能问答系统
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
            请登录您的账号
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <input
              type="text"
              placeholder="手机号"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
              className="w-full px-4 py-3 rounded-lg border text-sm outline-none transition-colors"
              style={{
                borderColor: 'var(--border)',
                background: 'var(--bg)',
                color: 'var(--text)',
              }}
              onFocus={(e) => (e.target.style.borderColor = 'var(--primary)')}
              onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
            />
          </div>
          <div>
            <input
              type="password"
              placeholder="密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-4 py-3 rounded-lg border text-sm outline-none transition-colors"
              style={{
                borderColor: 'var(--border)',
                background: 'var(--bg)',
                color: 'var(--text)',
              }}
              onFocus={(e) => (e.target.style.borderColor = 'var(--primary)')}
              onBlur={(e) => (e.target.style.borderColor = 'var(--border)')}
            />
          </div>

          {error && (
            <p className="text-sm text-red-500 text-center">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg text-white text-sm font-medium transition-colors cursor-pointer disabled:opacity-60"
            style={{ background: 'var(--primary)' }}
          >
            {loading ? '登录中...' : '登 录'}
          </button>
        </form>

        <p className="text-xs text-center mt-6" style={{ color: 'var(--text-muted)' }}>
          忘记密码？请联系管理员重置
        </p>
      </div>
    </div>
  )
}
