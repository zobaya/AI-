import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'
import { useUIStore } from '@/stores/uiStore'
import { UserOutlined, LockOutlined, BgColorsOutlined, CloseOutlined, SettingOutlined, FilePptOutlined, DownloadOutlined, DeleteOutlined, ReloadOutlined, BulbOutlined, RightOutlined } from '@ant-design/icons'
import { fetchGeneratedFiles, deleteGeneratedFile, downloadGeneratedFile, type GeneratedFileItem } from '@/api/chat'
import AvatarCropModal from '@/components/AvatarCropModal'

type Theme = 'light' | 'dark' | 'system'

const MAX_SIZE = 2 * 1024 * 1024 // 2MB

const themeOptions: { value: Theme; label: string }[] = [
  { value: 'light', label: '浅色' },
  { value: 'dark', label: '深色' },
  { value: 'system', label: '跟随系统' },
]

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function MyFilesList() {
  const toast = useUIStore((s) => s.toast)
  const [files, setFiles] = useState<GeneratedFileItem[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchGeneratedFiles('pptx')
      setFiles(data)
    } catch {
      // ignore
    }
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const handleDelete = async (id: number) => {
    try {
      await deleteGeneratedFile(id)
      setFiles((prev) => prev.filter((f) => f.id !== id))
    } catch {
      toast('删除失败', 'error')
    }
  }

  const handleDownload = async (f: GeneratedFileItem) => {
    try {
      await downloadGeneratedFile(f.id, f.file_name)
    } catch {
      toast('下载失败', 'error')
    }
  }

  if (loading) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>加载中...</p>
  }

  if (files.length === 0) {
    return <p className="text-xs" style={{ color: 'var(--text-muted)' }}>暂无生成文件</p>
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-end mb-1">
        <button
          onClick={load}
          className="flex items-center gap-1 text-xs cursor-pointer"
          style={{ color: 'var(--text-muted)' }}
        >
          <ReloadOutlined /> 刷新
        </button>
      </div>
      {files.map((f) => (
        <div
          key={f.id}
          className="flex items-center gap-3 p-3 rounded-lg border"
          style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}
        >
          <FilePptOutlined style={{ fontSize: 24, color: 'var(--primary)' }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="text-sm font-medium truncate" style={{ color: 'var(--text)' }}>{f.file_name}</div>
            <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {formatFileSize(f.file_size)} · {f.slide_count} 页 · {formatDate(f.created_at)}
            </div>
          </div>
          <button
            onClick={() => handleDownload(f)}
            className="p-1.5 rounded cursor-pointer hover:opacity-80"
            style={{ color: 'var(--primary)' }}
            title="下载"
          >
            <DownloadOutlined style={{ fontSize: 16 }} />
          </button>
          <button
            onClick={() => handleDelete(f.id)}
            className="p-1.5 rounded cursor-pointer hover:opacity-80"
            style={{ color: 'var(--text-muted)' }}
            title="删除"
          >
            <DeleteOutlined style={{ fontSize: 16 }} />
          </button>
        </div>
      ))}
    </div>
  )
}


export default function Settings() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const theme = useThemeStore((s) => s.theme)
  const toast = useUIStore((s) => s.toast)
  const setTheme = useThemeStore((s) => s.setTheme)
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  // 头像裁切相关
  const [cropSrc, setCropSrc] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (file.size > MAX_SIZE) {
      toast('图片大小不能超过 2MB', 'error')
      e.target.value = ''
      return
    }

    const reader = new FileReader()
    reader.onload = () => setCropSrc(reader.result as string)
    reader.readAsDataURL(file)
    // 重置 input 以便再次选择同一文件
    e.target.value = ''
  }

  const handleCropConfirm = async (blob: Blob) => {
    setCropSrc(null)
    setUploading(true)
    try {
      const file = new File([blob], 'avatar.jpg', { type: 'image/jpeg' })
      const { data } = await authApi.uploadAvatar(file)
      if (user) {
        useAuthStore.getState().setUser({ ...user, avatar: data.avatar })
      }
    } catch {
      toast('头像上传失败', 'error')
    }
    setUploading(false)
  }

  const handleCropCancel = () => {
    setCropSrc(null)
  }

  const handleResetAvatar = async () => {
    try {
      await authApi.deleteAvatar()
      if (user) {
        useAuthStore.getState().setUser({ ...user, avatar: null })
      }
    } catch {
      toast('恢复默认头像失败', 'error')
    }
  }

  const handleChangePassword = async () => {
    setMsg('')
    if (newPassword.length < 6) {
      setMsg('新密码至少 6 位')
      return
    }
    if (newPassword !== confirmPassword) {
      setMsg('两次密码不一致')
      return
    }
    setSaving(true)
    try {
      await authApi.changePassword(oldPassword, newPassword)
      setMsg('密码修改成功')
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch {
      setMsg('密码修改失败，请检查旧密码是否正确')
    }
    setSaving(false)
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div
        className="flex items-center justify-between px-6 h-12 border-b shrink-0 sticky top-0 z-10"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <SettingOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>设置</h2>
        </div>
        <button
          onClick={() => navigate(-1)}
          className="w-8 h-8 flex items-center justify-center rounded-lg transition-colors cursor-pointer hover:opacity-80"
          style={{ color: 'var(--text-muted)' }}
          title="关闭"
        >
          <CloseOutlined style={{ fontSize: 16 }} />
        </button>
      </div>

      <div className="max-w-lg mx-auto w-full p-6 space-y-8">
        {/* 基本信息 */}
        <section
          className="border rounded-xl p-5"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--surface)',
            boxShadow: 'var(--glass-shadow)',
          }}
        >
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text)' }}>基本信息</h3>

          <div className="flex items-center gap-4 mb-4">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center text-xl"
              style={{
                background: 'linear-gradient(135deg, var(--primary), var(--primary-dark))',
                color: '#fff',
                boxShadow: '0 2px 10px rgba(0, 123, 255, 0.25)',
              }}
            >
              {user?.avatar ? (
                <img src={user.avatar} className="w-full h-full rounded-full object-cover" alt="avatar" />
              ) : (
                <UserOutlined />
              )}
            </div>
            <div>
              <p className="text-base font-medium" style={{ color: 'var(--text)' }}>{user?.username}</p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {user?.role === 'sys_admin' ? '系统管理员' : user?.role === 'dept_admin' ? '部门管理员' : '普通用户'}
                {user?.department?.name && ` · ${user.department.name}`}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <label
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs cursor-pointer transition-colors"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              {uploading ? '上传中...' : '更换头像'}
              <input ref={fileRef} type="file" accept="image/*" onChange={handleFileSelect} className="hidden" />
            </label>
            {user?.avatar && (
              <button
                onClick={handleResetAvatar}
                className="px-3 py-1.5 rounded-lg border text-xs cursor-pointer transition-colors"
                style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
              >
                恢复默认
              </button>
            )}
          </div>
          <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>支持 JPG/PNG，不超过 2MB</p>
        </section>

        {/* 外观设置 */}
        <section
          className="border rounded-xl p-5"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--surface)',
            boxShadow: 'var(--glass-shadow)',
          }}
        >
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--text)' }}>
            <BgColorsOutlined /> 外观设置
          </h3>

          <div className="space-y-3">
            <label className="block text-xs" style={{ color: 'var(--text-muted)' }}>主题</label>
            <div className="flex gap-2">
              {themeOptions.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setTheme(opt.value)}
                  className="px-4 py-2 rounded-lg text-sm cursor-pointer transition-all duration-200 border"
                  style={{
                    borderColor: theme === opt.value ? 'var(--primary)' : 'var(--border)',
                    background: theme === opt.value ? 'var(--primary-light)' : 'transparent',
                    color: theme === opt.value ? 'var(--primary)' : 'var(--text-secondary)',
                    fontWeight: theme === opt.value ? 600 : 400,
                    boxShadow: theme === opt.value ? '0 0 0 3px rgba(0, 123, 255, 0.1)' : 'none',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* 修改密码 */}
        <section
          className="border rounded-xl p-5"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--surface)',
            boxShadow: 'var(--glass-shadow)',
          }}
        >
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--text)' }}>
            <LockOutlined /> 修改密码
          </h3>

          <div className="space-y-3">
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>当前密码</label>
              <input type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200"
                style={{
                  borderColor: 'var(--border)',
                  background: 'var(--bg)',
                  color: 'var(--text)',
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = 'var(--primary)'
                  e.currentTarget.style.boxShadow = '0 0 0 3px rgba(0, 123, 255, 0.1)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>新密码（至少 6 位）</label>
              <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200"
                style={{
                  borderColor: 'var(--border)',
                  background: 'var(--bg)',
                  color: 'var(--text)',
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = 'var(--primary)'
                  e.currentTarget.style.boxShadow = '0 0 0 3px rgba(0, 123, 255, 0.1)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>确认新密码</label>
              <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200"
                style={{
                  borderColor: 'var(--border)',
                  background: 'var(--bg)',
                  color: 'var(--text)',
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = 'var(--primary)'
                  e.currentTarget.style.boxShadow = '0 0 0 3px rgba(0, 123, 255, 0.1)'
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor = 'var(--border)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              />
            </div>
          </div>

          {msg && (
            <p className="text-xs mt-3" style={{ color: msg.includes('成功') ? 'var(--success)' : '#ef4444' }}>{msg}</p>
          )}

          <button
            onClick={handleChangePassword}
            disabled={saving}
            className="mt-4 px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50 transition-all duration-200"
            style={{
              background: 'linear-gradient(135deg, var(--primary), var(--primary-dark))',
              boxShadow: '0 2px 8px rgba(0, 123, 255, 0.25)',
            }}
          >
            {saving ? '保存中...' : '修改密码'}
          </button>
        </section>

        {/* AI 记忆 */}
        <section
          className="border rounded-xl p-5 cursor-pointer transition-all duration-150"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--surface)',
            boxShadow: 'var(--glass-shadow)',
          }}
          onClick={() => navigate('/settings/memory')}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'var(--primary)'
            e.currentTarget.style.background = 'var(--primary-light)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'var(--border)'
            e.currentTarget.style.background = 'var(--surface)'
          }}
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: 'var(--text)' }}>
                <BulbOutlined style={{ color: 'var(--primary)' }} /> AI 记忆
              </h3>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                管理 AI 对你的了解，包括偏好、知识和目标
              </p>
            </div>
            <RightOutlined style={{ color: 'var(--text-muted)', fontSize: 14 }} />
          </div>
        </section>

        {/* 我的文件 */}
        <section
          className="border rounded-xl p-5"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--surface)',
            boxShadow: 'var(--glass-shadow)',
          }}
        >
          <h3 className="text-sm font-semibold mb-4 flex items-center gap-2" style={{ color: 'var(--text)' }}>
            <FilePptOutlined /> 我的生成文件
          </h3>

          <MyFilesList />
        </section>

      </div>

      {/* 裁切弹窗 */}
      {cropSrc && (
        <AvatarCropModal
          imageSrc={cropSrc}
          onConfirm={handleCropConfirm}
          onCancel={handleCropCancel}
        />
      )}
    </div>
  )
}
