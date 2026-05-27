import { useEffect, useState, useCallback } from 'react'
import { orgApi, type DepartmentItem } from '@/api/org'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
  TeamOutlined,
  ApartmentOutlined,
} from '@ant-design/icons'

export default function Departments() {
  const user = useAuthStore((s) => s.user)
  const toast = useUIStore((s) => s.toast)
  const confirm = useUIStore((s) => s.confirm)
  const [departments, setDepartments] = useState<DepartmentItem[]>([])
  const [loading, setLoading] = useState(true)

  // 创建弹窗
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')

  // 编辑弹窗
  const [editDept, setEditDept] = useState<DepartmentItem | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [saving, setSaving] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await orgApi.getDepartments()
      setDepartments(data)
    } catch (e) {
      console.error('加载部门列表失败:', e)
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleCreate = async () => {
    setCreateError('')
    if (!newName.trim()) { setCreateError('请输入部门名称'); return }
    setCreating(true)
    try {
      await orgApi.createDepartment(newName.trim(), newDesc.trim())
      setShowCreate(false)
      setNewName(''); setNewDesc('')
      loadData()
    } catch (e: any) {
      setCreateError(e.response?.data?.error || '创建失败')
    }
    setCreating(false)
  }

  const handleUpdate = async () => {
    if (!editDept) return
    setSaving(true)
    try {
      await orgApi.updateDepartment(editDept.id, {
        name: editName.trim(),
        description: editDesc.trim(),
      })
      setEditDept(null)
      loadData()
    } catch (e) {
      console.error('更新失败:', e)
    }
    setSaving(false)
  }

  const handleDelete = async (id: number) => {
    if (!await confirm({ title: '确认删除', message: '确定删除此部门？', danger: true })) return
    try {
      await orgApi.deleteDepartment(id)
      loadData()
    } catch (e: any) {
      toast(e.response?.data?.error || '删除失败', 'error')
    }
  }

  if (user?.role !== 'sys_admin') {
    return (
      <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--text-muted)' }}>
        无权访问此页面
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 顶部 */}
      <div
        className="flex items-center justify-between px-6 h-12 border-b shrink-0"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <ApartmentOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>部门管理</h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            共 {departments.length} 个部门
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm cursor-pointer"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            <ReloadOutlined /> 刷新
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-white text-sm cursor-pointer"
            style={{ background: 'var(--primary)' }}
          >
            <PlusOutlined /> 新建部门
          </button>
        </div>
      </div>

      {/* 部门列表 */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--text-muted)' }}>
            加载中...
          </div>
        ) : departments.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-sm gap-3" style={{ color: 'var(--text-muted)' }}>
            <TeamOutlined style={{ fontSize: 48, opacity: 0.3 }} />
            <span>暂无部门</span>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="text-sm text-left border-b sticky top-0 z-10" style={{ color: 'var(--text-secondary)', borderColor: 'var(--border)', background: 'var(--surface)' }}>
                <th className="px-4 py-3 font-medium">ID</th>
                <th className="px-4 py-3 font-medium">部门名称</th>
                <th className="px-4 py-3 font-medium">描述</th>
                <th className="px-4 py-3 font-medium">成员数</th>
                <th className="px-4 py-3 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {departments.map((dept) => (
                <tr
                  key={dept.id}
                  className="border-b transition-colors duration-150"
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  style={{ borderColor: 'var(--border)' }}
                >
                  <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-muted)' }}>{dept.id}</td>
                  <td className="px-4 py-3 text-sm font-medium" style={{ color: 'var(--text)' }}>{dept.name}</td>
                  <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{dept.description || '-'}</td>
                  <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{dept.member_count}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => {
                          setEditDept(dept)
                          setEditName(dept.name)
                          setEditDesc(dept.description)
                        }}
                        className="flex items-center gap-1 p-2 rounded cursor-pointer"
                        style={{ color: 'var(--text-secondary)' }}
                        title="编辑"
                      >
                        <EditOutlined style={{ fontSize: 16 }} />
                      </button>
                      <button
                        onClick={() => handleDelete(dept.id)}
                        className="flex items-center gap-1 p-2 rounded cursor-pointer"
                        style={{ color: 'var(--text-muted)' }}
                        title="删除"
                      >
                        <DeleteOutlined style={{ fontSize: 16 }} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 创建部门弹窗 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }}>
          <div
            className="w-full max-w-md rounded-xl p-6 space-y-4"
            style={{ background: 'var(--surface)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold" style={{ color: 'var(--text)' }}>新建部门</h3>
            {createError && <p className="text-xs text-red-500">{createError}</p>}
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>部门名称</label>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="如: 技术部, 人事部"
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>描述（可选）</label>
              <textarea
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none resize-y"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => { setShowCreate(false); setCreateError('') }}
                className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={creating}
                className="px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50"
                style={{ background: 'var(--primary)' }}
              >
                {creating ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 编辑部门弹窗 */}
      {editDept && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }}>
          <div
            className="w-full max-w-md rounded-xl p-6 space-y-4"
            style={{ background: 'var(--surface)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-semibold" style={{ color: 'var(--text)' }}>
              编辑部门 - {editDept.name}
            </h3>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>部门名称</label>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>描述</label>
              <textarea
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none resize-y"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setEditDept(null)}
                className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                取消
              </button>
              <button
                onClick={handleUpdate}
                disabled={saving}
                className="px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50"
                style={{ background: 'var(--primary)' }}
              >
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
