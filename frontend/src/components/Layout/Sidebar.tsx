import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  MessageOutlined,
  BookOutlined,
  TeamOutlined,
  BarChartOutlined,
  SettingOutlined,
  TagsOutlined,
  LikeOutlined,
  UserOutlined,
  LogoutOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'

const navItems = [
  { key: '/chat', label: 'AI 问答', icon: <MessageOutlined /> },
]

const adminItems = [
  { key: '/knowledge', label: '知识库管理', icon: <BookOutlined /> },
  { key: '/admin/users', label: '用户管理', icon: <TeamOutlined /> },
  { key: '/admin/tags', label: '标签管理', icon: <TagsOutlined />, sysAdminOnly: true },
  { key: '/admin/feedback', label: '反馈管理', icon: <LikeOutlined /> },
  { key: '/dashboard', label: '统计看板', icon: <BarChartOutlined /> },
]

export default function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  const [popoverOpen, setPopoverOpen] = useState(false)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)
  const popoverRef = useRef<HTMLDivElement>(null)

  const isAdmin = user?.role === 'dept_admin' || user?.role === 'sys_admin'
  const isSysAdmin = user?.role === 'sys_admin'

  const items = isAdmin
    ? [
        ...navItems,
        ...adminItems.filter(
          (item) => !item.sysAdminOnly || isSysAdmin
        ),
      ]
    : navItems

  const isActive = (key: string) =>
    key === '/knowledge'
      ? location.pathname.startsWith('/knowledge')
      : location.pathname.startsWith(key)

  const handleLogout = useCallback(() => {
    setPopoverOpen(false)
    setShowLogoutConfirm(true)
  }, [])

  const confirmLogout = useCallback(async () => {
    setShowLogoutConfirm(false)
    await logout()
  }, [logout])

  const handleSettings = useCallback(() => {
    setPopoverOpen(false)
    navigate('/settings')
  }, [navigate])

  // 点击 Popover 外部关闭
  useEffect(() => {
    if (!popoverOpen) return
    const handleClick = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setPopoverOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [popoverOpen])

  // ESC 关闭 Popover
  useEffect(() => {
    if (!popoverOpen) return
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPopoverOpen(false)
    }
    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [popoverOpen])

  return (
    <aside
      className="sidebar-collapsed flex flex-col shrink-0 sidebar-transition"
      style={{
        width: 'var(--sidebar-collapsed-w)',
        background: 'var(--surface)',
        borderRight: '1px solid var(--border)',
        boxShadow: '2px 0 8px rgba(0, 0, 0, 0.04)',
        zIndex: 30,
      }}
    >
      {/* 顶部 Logo — 文字 "AI" */}
      <div
        className="flex items-center justify-center h-12 border-b shrink-0"
        style={{ borderColor: 'var(--border)' }}
      >
        <span
          className="text-lg font-bold select-none"
          style={{ color: 'var(--primary)', letterSpacing: '-0.5px' }}
        >
          AI
        </span>
      </div>

      {/* 导航列表 — 永久折叠态，仅图标 */}
      <nav className="flex-1 space-y-0.5 py-2 px-0 overflow-visible">
        {items.map((item) => {
          const active = isActive(item.key)
          return (
            <button
              key={item.key}
              onClick={() => navigate(item.key)}
              data-active={active || undefined}
              className="sidebar-item relative w-full flex items-center justify-center py-2.5 text-base transition-all duration-200 cursor-pointer"
              style={{
                background: active ? 'var(--primary-light)' : 'transparent',
                color: active ? 'var(--primary)' : 'var(--text-secondary)',
                fontWeight: active ? 700 : 500,
                borderRadius: 4,
                paddingLeft: 0,
                paddingRight: 0,
              }}
              onMouseEnter={(e) => {
                if (!active) e.currentTarget.style.background = 'var(--primary-light)'
              }}
              onMouseLeave={(e) => {
                if (!active) e.currentTarget.style.background = 'transparent'
              }}
            >
              {/* 活跃指示器 — 左侧竖条 */}
              {active && (
                <span
                  className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] rounded-r-full"
                  style={{ height: '60%', background: 'var(--primary)' }}
                />
              )}
              <span className="text-[18px] shrink-0">{item.icon}</span>
              {/* 折叠态 tooltip */}
              <span className="sidebar-tooltip">{item.label}</span>
            </button>
          )
        })}
      </nav>

      {/* 底部用户头像 + Popover 菜单 */}
      <div
        className="relative border-t py-3 flex justify-center shrink-0"
        style={{ borderColor: 'var(--border)' }}
        ref={popoverRef}
      >
        <button
          onClick={() => setPopoverOpen((v) => !v)}
          className="w-9 h-9 rounded-full flex items-center justify-center text-sm overflow-hidden cursor-pointer transition-all duration-200 hover:opacity-80"
          style={{ background: 'var(--primary)', color: '#fff' }}
          title={user?.username || '用户'}
        >
          {user?.avatar ? (
            <img src={user.avatar} className="w-full h-full object-cover" alt="avatar" />
          ) : (
            <UserOutlined style={{ fontSize: 16 }} />
          )}
        </button>

        {/* 玻璃态 Popover 菜单 */}
        {popoverOpen && (
          <>
            <div className="popover-overlay" onClick={() => setPopoverOpen(false)} />
            <div className="user-popover">
              {/* 用户信息头 */}
              <div
                className="px-3 py-2.5 mb-1"
                style={{ borderBottom: '1px solid var(--border)' }}
              >
                <div
                  className="text-sm font-medium truncate"
                  style={{ color: 'var(--text)' }}
                >
                  {user?.username || '用户'}
                </div>
                {user?.role && user.role !== 'user' && (
                  <div
                    className="text-xs mt-0.5 truncate"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {user.role === 'sys_admin' ? '系统管理员' : '部门管理员'}
                  </div>
                )}
              </div>
              {/* 设置 */}
              <button className="user-popover-item" onClick={handleSettings}>
                <SettingOutlined style={{ fontSize: 16 }} />
                <span>设置</span>
              </button>
              {/* 退出登录 */}
              <button className="user-popover-item danger" onClick={handleLogout}>
                <LogoutOutlined style={{ fontSize: 16 }} />
                <span>退出登录</span>
              </button>
            </div>
          </>
        )}
      </div>

      {/* 退出登录确认弹窗 */}
      {showLogoutConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowLogoutConfirm(false)
          }}
        >
          <div
            className="w-full max-w-xs p-6 rounded-xl shadow-xl"
            style={{ background: 'var(--surface)' }}
          >
            <h3 className="text-base font-semibold mb-2" style={{ color: 'var(--text)' }}>
              确认退出
            </h3>
            <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>
              确定要退出登录吗？
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowLogoutConfirm(false)}
                className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                取消
              </button>
              <button
                onClick={confirmLogout}
                className="px-4 py-2 rounded-lg text-white text-sm font-medium cursor-pointer"
                style={{ background: '#ef4444' }}
              >
                退出登录
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}
