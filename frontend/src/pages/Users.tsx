import { useEffect, useState, useCallback, useMemo } from 'react'
import { orgApi, type UserItem, type DepartmentItem, type KBPermission } from '@/api/org'
import { chatApi, type Conversation } from '@/api/chat'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import ChatSessionViewerDrawer from '@/components/Chat/ChatSessionViewerDrawer'
import {
  SearchOutlined,
  PlusOutlined,

  StopOutlined,
  CheckCircleOutlined,
  SwapOutlined,
  UploadOutlined,
  TeamOutlined,
  UserOutlined,
  KeyOutlined,
  BookOutlined,
  RobotOutlined,
  CloseOutlined,
  EditOutlined,
  DeleteOutlined,
  EllipsisOutlined,
  InboxOutlined,
  MessageOutlined,
} from '@ant-design/icons'

/** 给头像 URL 附加 access token，使 <img src> 能通过认证 */
function avatarUrl(url: string | null): string | undefined {
  if (!url) return undefined
  const token = useAuthStore.getState().accessToken
  if (!token) return url
  return `${url}?token=${token}`
}

const ROLE_MAP: Record<string, string> = {
  user: '普通用户',
  dept_admin: '部门管理员',
  sys_admin: '系统管理员',
}

const ROLE_ORDER: Record<string, number> = {
  sys_admin: 0,
  dept_admin: 1,
  user: 2,
}

/** 数据网格列宽定义（固定宽度，左侧聚拢） */
const GRID_COLS = '200px 150px 110px 80px'

export default function Users() {
  const currentUser = useAuthStore((s) => s.user)
  const toast = useUIStore((s) => s.toast)
  const confirmDialog = useUIStore((s) => s.confirm)
  const promptDialog = useUIStore((s) => s.prompt)
  const isSysAdmin = currentUser?.role === 'sys_admin'
  const isDeptAdmin = currentUser?.role === 'dept_admin'

  const [users, setUsers] = useState<UserItem[]>([])
  const [departments, setDepartments] = useState<DepartmentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')

  // 部门导航选中状态（null = "全部"）
  const [selectedDept, setSelectedDept] = useState<string | null>(null)
  const [deptMenuId, setDeptMenuId] = useState<number | null>(null)

  // Drawer 状态
  const [drawerUser, setDrawerUser] = useState<UserItem | null>(null)
  const [drawerTab, setDrawerTab] = useState<'info' | 'permissions' | 'history'>('info')

  // 弹窗状态
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showResetPwdModal, setShowResetPwdModal] = useState(false)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const [showKbPermModal, setShowKbPermModal] = useState(false)
  const [showAgentPermModal, setShowAgentPermModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [showToggleActiveModal, setShowToggleActiveModal] = useState(false)
  const [targetUser, setTargetUser] = useState<UserItem | null>(null)

  // 调动：选中的目标部门 ID
  const [transferTargetDeptId, setTransferTargetDeptId] = useState<number | null>(null)

  // 编辑用户表单（Drawer 内）
  const [editUsername, setEditUsername] = useState('')
  const [editPhone, setEditPhone] = useState('')
  const [editRole, setEditRole] = useState('')
  const [editDeptId, setEditDeptId] = useState<number | undefined>()
  const [editSaving, setEditSaving] = useState(false)
  const [editDirty, setEditDirty] = useState(false)

  // 对话历史 Tab
  const [userConversations, setUserConversations] = useState<Conversation[]>([])
  const [viewerConvId, setViewerConvId] = useState<number | null>(null)

  // 新建用户表单
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('123456')
  const [newPhone, setNewPhone] = useState('')
  const [newRole, setNewRole] = useState('user')
  const [newDeptId, setNewDeptId] = useState<number | undefined>()

  // 重置密码
  const [resetPwdValue, setResetPwdValue] = useState('')

  // ── 数据加载 ──────────────────────────────────────────────

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const { data: res } = await orgApi.getUsers({ page: 1, page_size: 999 })
      setUsers(res.data)
    } catch (e) {
      console.error('加载用户失败:', e)
    }
    setLoading(false)
  }, [])

  const loadDepartments = useCallback(async () => {
    if (!isSysAdmin) return
    try {
      const { data } = await orgApi.getDepartments()
      setDepartments(data)
    } catch (e) {
      console.error('加载部门失败:', e)
    }
  }, [isSysAdmin])

  useEffect(() => {
    loadUsers()
    loadDepartments()
  }, [loadUsers, loadDepartments])

  // 加载用户对话历史
  useEffect(() => {
    if (drawerTab === 'history' && drawerUser) {
      chatApi
        .getConversationsForUser(drawerUser.id)
        .then(({ data }) => setUserConversations(data))
        .catch(console.error)
    }
  }, [drawerTab, drawerUser])

  // ── 客户端计算 ────────────────────────────────────────────

  // 侧边栏部门列表（含 ID 和用户计数，用于导航 + 管理）
  const sidebarDepts = useMemo(() => {
    const countMap = new Map<string, number>()
    let unassignedCount = 0
    for (const user of users) {
      if (user.department?.name) {
        countMap.set(user.department.name, (countMap.get(user.department.name) || 0) + 1)
      } else {
        unassignedCount++
      }
    }
    const source = departments.length > 0
      ? departments.map(d => ({ id: d.id, name: d.name, count: countMap.get(d.name) || 0 }))
      : Array.from(countMap.entries()).map(([name, count]) => ({ id: -1, name, count }))
    return source.sort((a, b) => a.name.localeCompare(b, 'zh-CN'))
  }, [users, departments])

  // 未分配用户计数（与 displayUsers 过滤逻辑一致）
  const unassignedCount = useMemo(() => {
    return users.filter((u) => !u.department?.name).length
  }, [users])

  // 查找待删除部门的用户数
  const getDeptUserCount = useCallback((deptName: string) => {
    return users.filter((u) => u.department?.name === deptName).length
  }, [users])

  // 展示用户（部门筛选 + 客户端搜索）
  const displayUsers = useMemo(() => {
    let result = users
    if (selectedDept) {
      result = result.filter((u) => (u.department?.name || '未分配') === selectedDept)
    }
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(
        (u) => u.username.toLowerCase().includes(q) || (u.phone || '').includes(q),
      )
    }
    return [...result].sort((a, b) => (ROLE_ORDER[a.role] ?? 9) - (ROLE_ORDER[b.role] ?? 9))
  }, [users, selectedDept, search])

  // ── Drawer 操作 ───────────────────────────────────────────

  const openDrawer = useCallback((user: UserItem) => {
    setDrawerUser(user)
    setDrawerTab('info')
    setEditUsername(user.username)
    setEditPhone(user.phone)
    setEditRole(user.role)
    setEditDeptId(user.department?.id)
    setEditDirty(false)
  }, [])

  const closeDrawer = useCallback(() => {
    setDrawerUser(null)
  }, [])

  const handleEdit = useCallback(async () => {
    if (!drawerUser) return
    if (!editUsername.trim() || !editPhone.trim()) return
    setEditSaving(true)
    try {
      await orgApi.updateUser(drawerUser.id, {
        username: editUsername.trim(),
        phone: editPhone.trim(),
        role: editRole,
        department_id: isSysAdmin ? (editDeptId ?? null) : undefined,
      })
      setEditDirty(false)
      loadUsers()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error || '更新失败'
      toast(msg, 'error')
    }
    setEditSaving(false)
  }, [drawerUser, editUsername, editPhone, editRole, editDeptId, isSysAdmin, loadUsers])

  // ── 弹窗操作 ──────────────────────────────────────────────

  const openAction = useCallback((action: string, user: UserItem) => {
    setTargetUser(user)
    if (action === 'resetPwd') setShowResetPwdModal(true)
    else if (action === 'transfer') setShowTransferModal(true)
    else if (action === 'kbPerm') setShowKbPermModal(true)
    else if (action === 'agentPerm') setShowAgentPermModal(true)
    else if (action === 'delete') handleDeleteUser(user)
  }, [])

  const handleDeleteUser = useCallback(async (user: UserItem) => {
    if (!await confirmDialog({ title: `确认删除「${user.username}」`, message: '删除后该用户的所有数据将被清除，此操作不可恢复。', danger: true })) return
    try {
      await orgApi.deleteUser(user.id)
      closeDrawer()
      loadUsers()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error || '删除失败'
      toast(msg, 'error')
    }
  }, [confirmDialog, closeDrawer, loadUsers, toast])

  // ── 部门管理 ──────────────────────────────────────────────

  const handleCreateDept = useCallback(async () => {
    const name = await promptDialog({ title: '添加部门', message: '输入部门名称：', required: true })
    if (!name) return
    try {
      await orgApi.createDepartment(name)
      loadDepartments()
    } catch {
      toast('添加部门失败', 'error')
    }
  }, [promptDialog, loadDepartments, toast])

  const handleRenameDept = useCallback(async (id: number, oldName: string) => {
    const name = await promptDialog({ title: '重命名部门', message: `当前名称：${oldName}`, placeholder: oldName, required: true })
    if (!name) return
    try {
      await orgApi.updateDepartment(id, { name })
      if (selectedDept === oldName) setSelectedDept(name)
      loadDepartments()
      loadUsers()
    } catch {
      toast('重命名失败', 'error')
    }
  }, [promptDialog, selectedDept, loadDepartments, loadUsers, toast])

  const handleDeleteDept = useCallback(async (id: number, name: string) => {
    const count = getDeptUserCount(name)
    const hint = count > 0
      ? `该部门包含的 ${count} 名用户将被转移至「未分配」列表中。`
      : '该部门暂无用户。'
    if (!await confirmDialog({ title: `确认删除「${name}」`, message: hint, danger: true })) return
    try {
      await orgApi.deleteDepartment(id)
      if (selectedDept === name) setSelectedDept(null)
      loadDepartments()
      loadUsers()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error || '删除部门失败'
      toast(msg, 'error')
    }
  }, [confirmDialog, getDeptUserCount, selectedDept, loadDepartments, loadUsers, toast])

  const handleToggleActive = useCallback((user: UserItem) => {
    setTargetUser(user)
    setShowToggleActiveModal(true)
  }, [])

  const confirmToggleActive = useCallback(async () => {
    if (!targetUser) return
    try {
      await orgApi.toggleActive(targetUser.id)
      loadUsers()
    } catch (e) {
      console.error('操作失败:', e)
    }
    setShowToggleActiveModal(false)
    setTargetUser(null)
  }, [targetUser, loadUsers])

  const handleCreate = async () => {
    if (!newUsername.trim() || !newPhone.trim()) return
    try {
      await orgApi.createUser({
        username: newUsername.trim(),
        password: newPassword,
        phone: newPhone.trim(),
        role: newRole,
        department_id: isSysAdmin ? newDeptId : undefined,
      })
      setShowCreateModal(false)
      setNewUsername('')
      setNewPassword('123456')
      setNewPhone('')
      setNewRole('user')
      setNewDeptId(undefined)
      loadUsers()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error || '创建失败'
      toast(msg, 'error')
    }
  }

  const handleResetPwd = async () => {
    if (!targetUser) return
    const pwd = resetPwdValue.trim() || '123456'
    try {
      await orgApi.resetPassword(targetUser.id, pwd)
      toast(`密码已重置为 ${pwd}`, 'success')
      setShowResetPwdModal(false)
      setTargetUser(null)
    } catch (e) {
      console.error('重置密码失败:', e)
    }
  }

  const handleTransfer = async (deptId: number) => {
    if (!targetUser) return
    try {
      await orgApi.transferUser(targetUser.id, deptId)
      setShowTransferModal(false)
      setTargetUser(null)
      closeDrawer()
      loadUsers()
    } catch (e) {
      console.error('调动失败:', e)
    }
  }

  const handleImport = async (file: File | undefined) => {
    if (!file) return
    try {
      const { data } = await orgApi.batchImport(file)
      const result = data as { created?: string[]; errors?: string[]; total?: number }
      toast(`导入完成：成功 ${result.created?.length || 0} 个${(result.errors || []).join('；')}`, result.errors?.length ? 'error' : 'success')
      setShowImportModal(false)
      loadUsers()
    } catch (e) {
      console.error('导入失败:', e)
    }
  }

  // ── 渲染 ──────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      {/* 顶部栏 */}
      <div
        className="flex items-center h-12 border-b shrink-0 px-6"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <TeamOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>用户管理</h2>
        </div>
        <span className="text-xs ml-3" style={{ color: 'var(--text-muted)' }}>
          {users.length} 位用户 · {departments.length} 个部门
        </span>
      </div>

      {/* 左右分栏 */}
      <div className="flex flex-1 overflow-hidden">
      {/* ═══ 左侧：部门导航侧边栏（Master）═══ */}
      <div
        className="flex flex-col shrink-0"
        style={{
          width: 240,
          background: 'var(--bg)',
          borderRight: '1px solid var(--border)',
        }}
      >
        {/* 全局视图（与右侧 h-12 顶部栏对齐） */}
        <div className="flex items-center px-2 border-b shrink-0" style={{ height: 48, borderColor: 'var(--border)' }}>
            <button
              onClick={() => setSelectedDept(null)}
              className="conv-item w-full flex items-center justify-between px-3 py-[9px] rounded-lg text-sm cursor-pointer transition-colors duration-150"
              data-active={selectedDept === null}
              style={{
                background: selectedDept === null ? 'var(--primary-light)' : undefined,
                color: selectedDept === null ? 'var(--primary)' : 'var(--text-secondary)',
                fontWeight: selectedDept === null ? 500 : 400,
              }}
            >
              <span className="flex items-center gap-2">
                <TeamOutlined style={{ fontSize: 14 }} />
                全部用户
              </span>
              <span
                className="text-xs px-1.5 py-0.5 rounded-full leading-none"
                style={{
                  background: selectedDept === null ? 'var(--primary)' : 'var(--bg)',
                  color: selectedDept === null ? '#fff' : 'var(--text-muted)',
                  minWidth: 20,
                  textAlign: 'center' as const,
                }}
              >
                {users.length}
              </span>
            </button>
        </div>

        {/* 导航列表 */}
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {/* "未分配" — 仅在有未分配用户时渲染 */}
          {unassignedCount > 0 && (
            <div className="mt-1 mb-0.5">
              <button
                onClick={() => setSelectedDept('未分配')}
                className="conv-item w-full flex items-center justify-between px-3 py-[9px] rounded-lg text-sm cursor-pointer transition-colors duration-150 mb-0.5"
                data-active={selectedDept === '未分配'}
                style={{
                  background: selectedDept === '未分配' ? 'var(--primary-light)' : undefined,
                  color: selectedDept === '未分配' ? 'var(--primary)' : 'var(--text-secondary)',
                  fontWeight: selectedDept === '未分配' ? 500 : 400,
                }}
              >
                <span className="flex items-center gap-2">
                  <InboxOutlined style={{ fontSize: 14 }} />
                  未分配
                </span>
                <span
                  className="text-xs px-1.5 py-0.5 rounded-full leading-none"
                  style={{
                    background: selectedDept === '未分配' ? 'var(--primary)' : 'var(--bg)',
                    color: selectedDept === '未分配' ? '#fff' : 'var(--text-muted)',
                    minWidth: 20,
                    textAlign: 'center' as const,
                  }}
                >
                  {unassignedCount}
                </span>
              </button>
            </div>
          )}

          {/* ── 部门分组 ── */}
          {/* Section Header */}
          <div className="flex items-center justify-between px-3 mt-4 mb-1">
            <span className="text-sm font-semibold" style={{ color: 'var(--text-secondary)' }}>
              部门
            </span>
            {isSysAdmin && (
              <button
                onClick={handleCreateDept}
                title="新增部门"
                className="flex items-center justify-center w-6 h-6 rounded-full cursor-pointer transition-colors duration-150"
                style={{ color: 'var(--text-muted)' }}
                onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(0,0,0,0.06)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
                onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)' }}
              >
                <PlusOutlined style={{ fontSize: 14 }} />
              </button>
            )}
          </div>

          {/* 各部门列表 */}
          {sidebarDepts.map((dept) => {
            const isActive = selectedDept === dept.name
            const isRealDept = dept.id > 0
            return (
              <div key={dept.name} className="relative group mb-0.5">
                <button
                  onClick={() => setSelectedDept(dept.name)}
                  className="conv-item w-full flex items-center justify-between px-3 py-[9px] rounded-lg text-sm cursor-pointer transition-colors duration-150"
                  data-active={isActive}
                  style={{
                    background: isActive ? 'var(--primary-light)' : undefined,
                    color: isActive ? 'var(--primary)' : 'var(--text-secondary)',
                    fontWeight: isActive ? 500 : 400,
                  }}
                >
                  <span className="flex items-center gap-2 truncate">
                    <InboxOutlined style={{ fontSize: 14 }} />
                    {dept.name}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span
                      className="text-xs px-1.5 py-0.5 rounded-full leading-none"
                      style={{
                        background: isActive ? 'var(--primary)' : 'var(--bg)',
                        color: isActive ? '#fff' : 'var(--text-muted)',
                        minWidth: 20,
                        textAlign: 'center' as const,
                      }}
                    >
                      {dept.count}
                    </span>
                    {isRealDept && isSysAdmin && (
                      <span
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeptMenuId(deptMenuId === dept.id ? null : dept.id)
                        }}
                        className="opacity-0 group-hover:opacity-100 p-1 rounded cursor-pointer transition-opacity duration-150"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        <EllipsisOutlined style={{ fontSize: 14 }} />
                      </span>
                    )}
                  </div>
                </button>
                {/* 部门操作下拉菜单 */}
                {deptMenuId === dept.id && isRealDept && (
                  <>
                    <div className="fixed inset-0" onClick={() => setDeptMenuId(null)} />
                    <div
                      className="absolute right-2 top-full mt-1 py-1 rounded-lg border shadow-lg z-50"
                      style={{ background: 'var(--surface)', borderColor: 'var(--border)', minWidth: 120 }}
                    >
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleRenameDept(dept.id, dept.name)
                          setDeptMenuId(null)
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left cursor-pointer transition-colors hover:opacity-80"
                        style={{ color: 'var(--text-secondary)' }}
                      >
                        <EditOutlined style={{ fontSize: 13 }} /> 重命名
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleDeleteDept(dept.id, dept.name)
                          setDeptMenuId(null)
                        }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left cursor-pointer transition-colors hover:opacity-80"
                        style={{ color: '#ef4444' }}
                      >
                        <DeleteOutlined style={{ fontSize: 13 }} /> 删除
                      </button>
                    </div>
                  </>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ═══ 右侧：现代无边框数据网格（Detail Grid）═══ */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0" style={{ background: 'var(--surface)' }}>
        {/* 顶部操作栏 */}
        <div
          className="flex items-center justify-between px-6 h-12 border-b shrink-0"
          style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        >
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>
              {selectedDept || '全部用户'}
            </h2>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              {displayUsers.length} 人
            </span>
          </div>

          <div className="flex items-center gap-3">
            <div
              className="flex items-center gap-2 px-3 py-2 rounded-lg border"
              style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}
            >
              <SearchOutlined style={{ color: 'var(--text-muted)', fontSize: 14 }} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索用户名/手机号..."
                className="outline-none text-sm bg-transparent"
                style={{ color: 'var(--text)', width: 170 }}
              />
            </div>

            <button
              onClick={() => setShowImportModal(true)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm cursor-pointer transition-colors duration-150 hover-gray"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              <UploadOutlined /> 批量导入
            </button>

            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-white text-sm font-medium cursor-pointer transition-opacity duration-150 hover:opacity-90"
              style={{ background: 'var(--primary)' }}
            >
              <PlusOutlined /> 新增用户
            </button>
          </div>
        </div>

        {/* 网格表头（sticky） */}
        <div
          className="shrink-0 px-6 py-2 border-b"
          style={{
            display: 'grid',
            gridTemplateColumns: GRID_COLS,
            alignItems: 'center',
            background: 'var(--surface)',
            borderBottomColor: 'var(--border)',
          }}
        >
          <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
            姓名
          </span>
          <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
            手机号
          </span>
          <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
            角色
          </span>
          <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
            状态
          </span>
        </div>

        {/* 网格数据行 */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div
              className="flex items-center justify-center h-32 text-sm"
              style={{ color: 'var(--text-muted)' }}
            >
              加载中...
            </div>
          ) : displayUsers.length === 0 ? (
            <div
              className="flex items-center justify-center h-32 text-sm"
              style={{ color: 'var(--text-muted)' }}
            >
              暂无数据
            </div>
          ) : (
            displayUsers.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                onClickRow={() => openDrawer(user)}
              />
            ))
          )}
        </div>
      </div>

      {/* ── 右侧 Drawer（用户详情/编辑） ────────────────────── */}
      {drawerUser && (
        <>
          <div className="drawer-overlay" onClick={closeDrawer} />
          <div className="drawer-panel">
            {/* Drawer 头 */}
            <div
              className="flex items-center justify-between px-6 h-14 border-b shrink-0"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center text-sm overflow-hidden"
                  style={{ background: 'var(--primary)', color: '#fff' }}
                >
                  {drawerUser.avatar ? (
                    <img src={avatarUrl(drawerUser.avatar)} className="w-full h-full object-cover" alt="" />
                  ) : (
                    <UserOutlined style={{ fontSize: 18 }} />
                  )}
                </div>
                <div>
                  <div className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
                    {drawerUser.username}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span
                      className="text-xs px-2 py-0.5 rounded-full"
                      style={{ background: 'var(--primary-light)', color: 'var(--primary)' }}
                    >
                      {ROLE_MAP[drawerUser.role] || drawerUser.role}
                    </span>
                    <span
                      className="flex items-center gap-1 text-xs"
                      style={{
                        color: drawerUser.is_active ? 'var(--success)' : 'var(--text-muted)',
                      }}
                    >
                      <span
                        className="status-dot"
                        style={{
                          background: drawerUser.is_active ? 'var(--success)' : '#d1d5db',
                          width: 6,
                          height: 6,
                        }}
                      />
                      {drawerUser.is_active ? '正常' : '禁用'}
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={closeDrawer}
                className="p-2 rounded-lg cursor-pointer"
                style={{ color: 'var(--text-muted)' }}
              >
                <CloseOutlined style={{ fontSize: 16 }} />
              </button>
            </div>

            {/* Drawer Tab 切换 */}
            <div
              className="flex px-6 gap-6 border-b shrink-0"
              style={{ borderColor: 'var(--border)' }}
            >
              {(['info', 'permissions', 'history'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setDrawerTab(tab)}
                  className="py-3 text-sm font-medium cursor-pointer border-b-2 transition-colors"
                  style={{
                    color: drawerTab === tab ? 'var(--primary)' : 'var(--text-muted)',
                    borderColor: drawerTab === tab ? 'var(--primary)' : 'transparent',
                  }}
                >
                  {tab === 'info' ? '基本信息' : tab === 'permissions' ? '权限管理' : '对话历史'}
                </button>
              ))}
            </div>

            {/* Drawer 内容 */}
            <div className="flex-1 overflow-y-auto p-6">
              {drawerTab === 'history' ? (
                <div className="space-y-2">
                  {userConversations.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12" style={{ color: 'var(--text-muted)' }}>
                      <MessageOutlined style={{ fontSize: 32, marginBottom: 8, opacity: 0.4 }} />
                      <span className="text-sm">暂无对话记录</span>
                    </div>
                  ) : (
                    userConversations.map((conv) => (
                      <button
                        key={conv.id}
                        onClick={() => setViewerConvId(conv.id)}
                        className="w-full text-left px-4 py-3 rounded-lg border text-sm cursor-pointer transition-colors duration-150"
                        style={{ borderColor: 'var(--border)', color: 'var(--text)' }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                      >
                        <div style={{ fontWeight: 500, marginBottom: 4 }}>{conv.title || '未命名对话'}</div>
                        <div className="flex items-center gap-3" style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
                          <span>{conv.message_count} 条消息</span>
                          <span>{new Date(conv.updated_at).toLocaleDateString('zh-CN')}</span>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              ) : drawerTab === 'info' ? (
                <div className="space-y-4">
                  <InputField
                    label="用户名"
                    value={editUsername}
                    onChange={(v) => {
                      setEditUsername(v)
                      setEditDirty(true)
                    }}
                  />
                  <InputField
                    label="手机号"
                    value={editPhone}
                    onChange={(v) => {
                      setEditPhone(v)
                      setEditDirty(true)
                    }}
                  />
                  <div>
                    <label
                      className="block text-xs mb-1.5 font-medium"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      部门
                    </label>
                    <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {drawerUser.department?.name || '未分配'}
                    </div>
                  </div>
                  <div>
                    <label
                      className="block text-xs mb-1.5 font-medium"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      注册时间
                    </label>
                    <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {new Date(drawerUser.date_joined).toLocaleString('zh-CN')}
                    </div>
                  </div>
                </div>
              ) : (
                <DrawerPermissions
                  user={drawerUser}
                  isSysAdmin={isSysAdmin}
                  editRole={editRole}
                  onEditRoleChange={(v) => {
                    setEditRole(v)
                    setEditDirty(true)
                  }}
                  onAction={openAction}
                  onToggleActive={handleToggleActive}
                />
              )}
            </div>

            {/* 底部保存栏（仅基本信息/权限管理 Tab） */}
            {editDirty && drawerTab !== 'history' && (
              <div
                className="shrink-0 flex justify-end gap-2 px-6 py-4 border-t"
                style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
              >
                <button
                  onClick={() => {
                    setEditUsername(drawerUser!.username)
                    setEditPhone(drawerUser!.phone)
                    setEditRole(drawerUser!.role)
                    setEditDeptId(drawerUser!.department?.id)
                    setEditDirty(false)
                  }}
                  className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                >
                  撤销
                </button>
                <button
                  onClick={handleEdit}
                  disabled={editSaving}
                  className="px-4 py-2 rounded-lg text-white text-sm font-medium cursor-pointer disabled:opacity-50"
                  style={{ background: 'var(--primary)' }}
                >
                  {editSaving ? '保存中...' : '保存修改'}
                </button>
              </div>
            )}
          </div>
        </>
      )}

      {/* ── 新建用户弹窗 ────────────────────────────────────── */}
      {showCreateModal && (
        <ModalOverlay onClose={() => setShowCreateModal(false)}>
          <h3 className="text-base font-semibold mb-4" style={{ color: 'var(--text)' }}>
            新增用户
          </h3>
          <div className="space-y-3">
            <InputField label="用户名" value={newUsername} onChange={setNewUsername} placeholder="请输入用户名" />
            <InputField label="手机号" value={newPhone} onChange={setNewPhone} placeholder="请输入手机号" />
            <InputField label="密码" value={newPassword} onChange={setNewPassword} placeholder="默认 123456" />
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>
                角色
              </label>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border text-sm"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}
              >
                <option value="user">普通用户</option>
                <option value="dept_admin">部门管理员</option>
              </select>
            </div>
            {isSysAdmin && (
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>
                  部门
                </label>
                <select
                  value={newDeptId || ''}
                  onChange={(e) => setNewDeptId(e.target.value ? Number(e.target.value) : undefined)}
                  className="w-full px-3 py-2 rounded-lg border text-sm"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}
                >
                  <option value="">不指定</option>
                  {departments.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <div className="flex justify-end gap-2 mt-6">
            <button
              onClick={() => setShowCreateModal(false)}
              className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              取消
            </button>
            <button
              onClick={handleCreate}
              className="px-4 py-2 rounded-lg text-white text-sm cursor-pointer"
              style={{ background: 'var(--primary)' }}
            >
              创建
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* ── 重置密码弹窗 ────────────────────────────────────── */}
      {showResetPwdModal && targetUser && (
        <ModalOverlay
          onClose={() => {
            setShowResetPwdModal(false)
            setTargetUser(null)
          }}
        >
          <h3 className="text-base font-semibold mb-4" style={{ color: 'var(--text)' }}>
            重置密码 — {targetUser.username}
          </h3>
          <InputField
            label="新密码"
            value={resetPwdValue}
            onChange={setResetPwdValue}
            placeholder="留空则重置为 123456"
          />
          <div className="flex justify-end gap-2 mt-6">
            <button
              onClick={() => {
                setShowResetPwdModal(false)
                setTargetUser(null)
              }}
              className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              取消
            </button>
            <button
              onClick={handleResetPwd}
              className="px-4 py-2 rounded-lg text-white text-sm cursor-pointer"
              style={{ background: 'var(--primary)' }}
            >
              确认重置
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* ── 启禁用确认弹窗 ────────────────────────────────────── */}
      {showToggleActiveModal && targetUser && (
        <ModalOverlay
          onClose={() => {
            setShowToggleActiveModal(false)
            setTargetUser(null)
          }}
        >
          <h3 className="text-base font-semibold mb-2" style={{ color: 'var(--text)' }}>
            {targetUser.is_active ? '禁用用户' : '启用用户'}
          </h3>
          <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>
            确定要{targetUser.is_active ? '禁用' : '启用'}用户「{targetUser.username}」吗？
            {targetUser.is_active && (
              <span style={{ color: '#ef4444' }}> 禁用后该用户将无法登录系统。</span>
            )}
          </p>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => {
                setShowToggleActiveModal(false)
                setTargetUser(null)
              }}
              className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              取消
            </button>
            <button
              onClick={confirmToggleActive}
              className="px-4 py-2 rounded-lg text-white text-sm font-medium cursor-pointer"
              style={{ background: targetUser.is_active ? '#ef4444' : 'var(--primary)' }}
            >
              确认{targetUser.is_active ? '禁用' : '启用'}
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* ── 调动弹窗 ────────────────────────────────────────── */}
      {showTransferModal && targetUser && (
        <ModalOverlay
          onClose={() => {
            setShowTransferModal(false)
            setTargetUser(null)
            setTransferTargetDeptId(null)
          }}
        >
          <h3 className="text-base font-semibold mb-2" style={{ color: 'var(--text)' }}>
            调动用户：{targetUser.username}
          </h3>
          <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
            当前部门：{targetUser.department?.name || '无'}
          </p>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {departments.map((d) => {
              const selected = transferTargetDeptId === d.id
              const isCurrent = d.id === targetUser.department?.id
              return (
                <button
                  key={d.id}
                  onClick={() => setTransferTargetDeptId(d.id)}
                  className="w-full text-left px-4 py-2.5 rounded-lg border text-sm cursor-pointer transition-colors"
                  style={{
                    borderColor: selected ? 'var(--primary)' : 'var(--border)',
                    color: selected ? 'var(--primary)' : isCurrent ? 'var(--primary)' : 'var(--text-secondary)',
                    background: selected ? 'var(--primary-light)' : isCurrent ? 'rgba(0,123,255,0.05)' : 'transparent',
                  }}
                >
                  {d.name} ({d.member_count} 人)
                </button>
              )
            })}
          </div>
          <div className="flex justify-end gap-2 mt-5">
            <button
              onClick={() => {
                setShowTransferModal(false)
                setTargetUser(null)
                setTransferTargetDeptId(null)
              }}
              className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
            >
              取消
            </button>
            <button
              onClick={() => {
                if (transferTargetDeptId != null) handleTransfer(transferTargetDeptId)
              }}
              disabled={transferTargetDeptId == null}
              className="px-4 py-2 rounded-lg text-white text-sm font-medium cursor-pointer disabled:opacity-50"
              style={{ background: 'var(--primary)' }}
            >
              确认调动
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* ── 知识库权限弹窗 ────────────────────────────────────── */}
      {showKbPermModal && targetUser && (
        <KbPermModal
          user={targetUser}
          onClose={() => {
            setShowKbPermModal(false)
            setTargetUser(null)
          }}
          onSaved={loadUsers}
        />
      )}

      {/* ── Agent 权限弹窗 ──────────────────────────────────── */}
      {showAgentPermModal && targetUser && (
        <AgentPermModal
          user={targetUser}
          onClose={() => {
            setShowAgentPermModal(false)
            setTargetUser(null)
          }}
          onSaved={loadUsers}
        />
      )}

      {/* ── 批量导入弹窗 ────────────────────────────────────── */}
      {showImportModal && (
        <ModalOverlay onClose={() => setShowImportModal(false)}>
          <h3 className="text-base font-semibold mb-2" style={{ color: 'var(--text)' }}>
            批量导入用户
          </h3>
          <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
            上传 Excel 文件（.xlsx），第一行为表头：用户名 | 密码 | 角色 |
            手机号。密码、角色和手机号可选，默认 123456 / user。
          </p>
          <input
            type="file"
            accept=".xlsx,.xls"
            onChange={(e) => handleImport(e.target.files?.[0])}
            className="w-full text-sm"
            style={{ color: 'var(--text)' }}
          />
        </ModalOverlay>
      )}

      {/* ── 会话查看器抽屉 ── */}
      {viewerConvId !== null && (
        <ChatSessionViewerDrawer
          conversationId={viewerConvId}
          onClose={() => setViewerConvId(null)}
        />
      )}
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════
//  用户数据行（CSS Grid 对齐）
// ════════════════════════════════════════════════════════════════

function UserRow({
  user,
  onClickRow,
}: {
  user: UserItem
  onClickRow: () => void
}) {
  return (
    <div
      className="group cursor-pointer transition-colors duration-150 border-b"
      style={{
        display: 'grid',
        gridTemplateColumns: GRID_COLS,
        alignItems: 'center',
        padding: '10px 24px',
        borderBottomColor: 'rgba(0, 0, 0, 0.04)',
        background: 'var(--surface)',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--surface)')}
      onClick={onClickRow}
    >
      {/* 头像 + 用户名 */}
      <div className="flex items-center gap-2.5 min-w-0">
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs overflow-hidden shrink-0"
          style={{ background: 'var(--primary)', color: '#fff' }}
        >
          {user.avatar ? (
            <img src={avatarUrl(user.avatar)} className="w-full h-full object-cover" alt="" />
          ) : (
            <UserOutlined style={{ fontSize: 12 }} />
          )}
        </div>
        <span className="text-sm font-medium truncate" style={{ color: 'var(--text)' }}>
          {user.username}
        </span>
      </div>

      {/* 手机号 */}
      <span className="text-sm truncate" style={{ color: 'var(--text-secondary)' }}>
        {user.phone || '-'}
      </span>

      {/* 角色胶囊 */}
      <span
        className="text-xs px-2.5 py-0.5 rounded-full w-fit"
        style={{ background: 'var(--primary-light)', color: 'var(--primary)', fontWeight: 500 }}
      >
        {ROLE_MAP[user.role] || user.role}
      </span>

      {/* 状态 */}
      <span
        className="flex items-center gap-1.5 text-xs"
        style={{ color: user.is_active ? 'var(--success)' : 'var(--text-muted)' }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            background: user.is_active ? 'var(--success)' : '#d1d5db',
            flexShrink: 0,
          }}
        />
        {user.is_active ? '正常' : '禁用'}
      </span>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════
//  Drawer 内权限管理 Tab
// ════════════════════════════════════════════════════════════════

function DrawerPermissions({
  user,
  isSysAdmin,
  editRole,
  onEditRoleChange,
  onAction,
  onToggleActive,
}: {
  user: UserItem
  isSysAdmin: boolean
  editRole: string
  onEditRoleChange: (v: string) => void
  onAction: (action: string, user: UserItem) => void
  onToggleActive: (user: UserItem) => void
}) {
  const currentUser = useAuthStore((s) => s.user)
  const isSelf = currentUser?.id === user.id

  return (
    <div className="space-y-3">
      {/* 角色变更 */}
      <h4 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
        角色变更
      </h4>
      <select
        value={editRole}
        onChange={(e) => onEditRoleChange(e.target.value)}
        className="w-full px-3 py-2.5 rounded-lg border text-sm outline-none"
        style={{
          borderColor: 'var(--border)',
          background: 'var(--bg)',
          color: 'var(--text)',
        }}
      >
        <option value="user">普通用户</option>
        <option value="dept_admin">部门管理员</option>
        {isSysAdmin && <option value="sys_admin">系统管理员</option>}
      </select>

      <div className="my-4" style={{ borderBottom: '1px solid var(--divider-subtle)' }} />

      <h4 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
        快捷操作
      </h4>
      <div className="space-y-2">
        <button
          onClick={() => onToggleActive(user)}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-sm cursor-pointer transition-colors"
          style={{ borderColor: 'var(--border)', color: 'var(--text)' }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        >
          {user.is_active ? (
            <StopOutlined style={{ color: '#ef4444' }} />
          ) : (
            <CheckCircleOutlined style={{ color: 'var(--success)' }} />
          )}
          {user.is_active ? '禁用此用户' : '启用此用户'}
        </button>
        <button
          onClick={() => onAction('resetPwd', user)}
          className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-sm cursor-pointer transition-colors"
          style={{ borderColor: 'var(--border)', color: 'var(--text)' }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        >
          <KeyOutlined style={{ color: 'var(--primary)' }} /> 重置密码
        </button>
        {isSysAdmin && (
          <button
            onClick={() => onAction('transfer', user)}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-sm cursor-pointer transition-colors"
            style={{ borderColor: 'var(--border)', color: 'var(--text)' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <SwapOutlined style={{ color: 'var(--primary)' }} /> 部门调动
          </button>
        )}
        {(isSysAdmin || isDeptAdmin) && (
          <>
            <button
              onClick={() => onAction('kbPerm', user)}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-sm cursor-pointer transition-colors"
              style={{ borderColor: 'var(--border)', color: 'var(--text)' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <BookOutlined style={{ color: 'var(--primary)' }} /> 知识库权限
            </button>
            <button
              onClick={() => onAction('agentPerm', user)}
              className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-sm cursor-pointer transition-colors"
              style={{ borderColor: 'var(--border)', color: 'var(--text)' }}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              <RobotOutlined style={{ color: 'var(--primary)' }} /> Agent 权限
            </button>
          </>
        )}
        {/* 删除用户（不能删自己） */}
        {!isSelf && (
          <button
            onClick={() => onAction('delete', user)}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-sm cursor-pointer transition-colors"
            style={{ borderColor: 'var(--border)', color: '#ef4444' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(239,68,68,0.06)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
          >
            <DeleteOutlined /> 删除用户
          </button>
        )}
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════
//  知识库权限弹窗
// ════════════════════════════════════════════════════════════════

function KbPermModal({
  user,
  onClose,
  onSaved,
}: {
  user: UserItem
  onClose: () => void
  onSaved: () => void
}) {
  const [allKbs, setAllKbs] = useState<{ kb_id: string; name: string }[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    Promise.all([
      orgApi
        .getKBPermissions(user.id)
        .then(({ data }) => setSelectedIds(new Set(data.map((p: KBPermission) => p.kb_id)))),
      import('@/api/knowledge').then(({ knowledgeApi }) =>
        knowledgeApi
          .getBases()
          .then(({ data }) => setAllKbs(data.map((kb) => ({ kb_id: kb.kb_id, name: kb.name })))),
      ),
    ]).finally(() => setLoading(false))
  }, [user.id])

  const toggle = (kbId: string) => {
    const next = new Set(selectedIds)
    if (next.has(kbId)) next.delete(kbId)
    else next.add(kbId)
    setSelectedIds(next)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await orgApi.setKBPermissions(user.id, Array.from(selectedIds))
      onSaved()
      onClose()
    } catch (e) {
      console.error('保存权限失败:', e)
    }
    setSaving(false)
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h3 className="text-base font-semibold mb-1" style={{ color: 'var(--text)' }}>
        知识库权限 — {user.username}
      </h3>
      <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
        已授权 {selectedIds.size} 个知识库
      </p>
      {loading ? (
        <div className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          加载中...
        </div>
      ) : allKbs.length === 0 ? (
        <div className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          暂无知识库
        </div>
      ) : (
        <div className="space-y-1.5 max-h-64 overflow-y-auto">
          {allKbs.map((kb) => (
            <label
              key={kb.kb_id}
              className="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer"
              style={{ background: selectedIds.has(kb.kb_id) ? 'rgba(0,123,255,0.06)' : 'transparent' }}
            >
              <input
                type="checkbox"
                checked={selectedIds.has(kb.kb_id)}
                onChange={() => toggle(kb.kb_id)}
                className="accent-blue-500"
              />
              <span className="text-sm" style={{ color: 'var(--text)' }}>
                {kb.name}
              </span>
              <span className="text-xs ml-auto" style={{ color: 'var(--text-muted)' }}>
                {kb.kb_id}
              </span>
            </label>
          ))}
        </div>
      )}
      <div className="flex justify-end gap-2 mt-4">
        <button
          onClick={onClose}
          className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
          style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
        >
          关闭
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50"
          style={{ background: 'var(--primary)' }}
        >
          {saving ? '保存中...' : '保存'}
        </button>
      </div>
    </ModalOverlay>
  )
}

// ════════════════════════════════════════════════════════════════
//  Agent 权限弹窗
// ════════════════════════════════════════════════════════════════

const ALL_AGENTS = [
  { name: 'tool_calling_agent', label: '工具调用 Agent' },
  { name: 'knowledge_qa', label: '知识问答' },
]

function AgentPermModal({
  user,
  onClose,
  onSaved,
}: {
  user: UserItem
  onClose: () => void
  onSaved: () => void
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    orgApi
      .getAgentPermissions(user.id)
      .then(({ data }) => setSelected(new Set(data.map((p: { agent_name: string }) => p.agent_name))))
      .finally(() => setLoading(false))
  }, [user.id])

  const toggle = (name: string) => {
    const next = new Set(selected)
    if (next.has(name)) next.delete(name)
    else next.add(name)
    setSelected(next)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await orgApi.setAgentPermissions(user.id, Array.from(selected))
      onSaved()
      onClose()
    } catch (e) {
      console.error('保存权限失败:', e)
    }
    setSaving(false)
  }

  return (
    <ModalOverlay onClose={onClose}>
      <h3 className="text-base font-semibold mb-1" style={{ color: 'var(--text)' }}>
        Agent 权限 — {user.username}
      </h3>
      <p className="text-xs mb-4" style={{ color: 'var(--text-muted)' }}>
        已授权 {selected.size} 个 Agent
      </p>
      {loading ? (
        <div className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          加载中...
        </div>
      ) : (
        <div className="space-y-1.5">
          {ALL_AGENTS.map((agent) => (
            <label
              key={agent.name}
              className="flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer"
              style={{ background: selected.has(agent.name) ? 'rgba(0,123,255,0.06)' : 'transparent' }}
            >
              <input
                type="checkbox"
                checked={selected.has(agent.name)}
                onChange={() => toggle(agent.name)}
                className="accent-blue-500"
              />
              <RobotOutlined style={{ color: 'var(--primary)' }} />
              <span className="text-sm" style={{ color: 'var(--text)' }}>
                {agent.label}
              </span>
              <span className="text-xs ml-auto" style={{ color: 'var(--text-muted)' }}>
                {agent.name}
              </span>
            </label>
          ))}
        </div>
      )}
      <div className="flex justify-end gap-2 mt-4">
        <button
          onClick={onClose}
          className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
          style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
        >
          关闭
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50"
          style={{ background: 'var(--primary)' }}
        >
          {saving ? '保存中...' : '保存'}
        </button>
      </div>
    </ModalOverlay>
  )
}

// ── 通用弹窗组件 ──────────────────────────────────────────────

function ModalOverlay({
  children,
  onClose,
}: {
  children: React.ReactNode
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="w-full max-w-md p-6 rounded-xl shadow-xl"
        style={{ background: 'var(--surface)' }}
      >
        {children}
      </div>
    </div>
  )
}

function InputField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <div>
      <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--text-muted)' }}>
        {label}
      </label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full px-3 py-2.5 rounded-lg border text-sm outline-none"
        style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}
      />
    </div>
  )
}
