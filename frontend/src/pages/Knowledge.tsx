import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  knowledgeApi,
  type KnowledgeBaseItem,
  type DocumentItem,
  type TaskStatus,
} from '@/api/knowledge'
import { tagsApi, type TagItem } from '@/api/tags'
import { orgApi, type DepartmentItem } from '@/api/org'
import { useAuthStore } from '@/stores/authStore'
import FilterSelect from '@/components/FilterSelect'
import { useUIStore } from '@/stores/uiStore'
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SearchOutlined,

  BookOutlined,
  FileTextOutlined,
  InboxOutlined,
  CloseOutlined,
  TagOutlined,
  FolderOutlined,
  UploadOutlined,
  EllipsisOutlined,
  CheckCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'

const DOC_PAGE_SIZE = 20

export default function Knowledge() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const confirm = useUIStore((s) => s.confirm)
  const isSysAdmin = user?.role === 'sys_admin'

  // ── KB 层 ──
  const [bases, setBases] = useState<KnowledgeBaseItem[]>([])
  const [departments, setDepartments] = useState<DepartmentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null)
  const [filterDeptId, setFilterDeptId] = useState<number | null>(null)

  // KB 弹窗
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newDeptId, setNewDeptId] = useState<number>(0)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
  const [editKb, setEditKb] = useState<KnowledgeBaseItem | null>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [saving, setSaving] = useState(false)
  const [activeMenu, setActiveMenu] = useState<string | null>(null)

  // ── 文档层 ──
  const [kbInfo, setKbInfo] = useState<KnowledgeBaseItem | null>(null)
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [docTotal, setDocTotal] = useState(0)
  const [docPage, setDocPage] = useState(1)
  const [docLoading, setDocLoading] = useState(false)
  const [docSearch, setDocSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState<'all' | 'completed' | 'other'>('all')
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<TaskStatus | null>(null)
  const [uploadingFileIndex, setUploadingFileIndex] = useState(0)
  const [uploadingTotal, setUploadingTotal] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [showUploadModal, setShowUploadModal] = useState(false)
  const [editingDoc, setEditingDoc] = useState<DocumentItem | null>(null)

  // ── KB 列表加载 ──
  const loadBases = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await knowledgeApi.getBases()
      setBases(data)
      if (isSysAdmin) {
        const { data: depts } = await orgApi.getDepartments()
        setDepartments(depts)
      }
    } catch (e) {
      console.error('加载知识库列表失败:', e)
    }
    setLoading(false)
  }, [isSysAdmin])

  useEffect(() => { loadBases() }, [loadBases])

  // ── 文档列表加载 ──
  const loadDocuments = useCallback(async () => {
    if (!selectedKbId) return
    setDocLoading(true)
    try {
      const { data: kbData } = await knowledgeApi.getBase(selectedKbId)
      setKbInfo(kbData)
      const params: Record<string, string | number> = {
        kb_id: selectedKbId,
        page: docPage,
        page_size: DOC_PAGE_SIZE,
      }
      if (docSearch) params.search = docSearch
      if (filterStatus === 'completed') params.status = 'completed'
      else if (filterStatus === 'other') params.status = 'other'
      const { data } = await knowledgeApi.getDocuments(params)
      setDocuments(data.documents || [])
      setDocTotal(data.total || 0)
    } catch (e) {
      console.error('加载文档失败:', e)
    }
    setDocLoading(false)
  }, [selectedKbId, docPage, docSearch, filterStatus])

  useEffect(() => { loadDocuments() }, [loadDocuments])

  // 切换 KB 时重置文档层状态
  const handleSelectKb = useCallback((kbId: string) => {
    setSelectedKbId(kbId)
    setDocPage(1)
    setDocSearch('')
    setFilterStatus('all')
    setSelectedIds(new Set())
    setActiveMenu(null)
  }, [])

  // ── KB CRUD ──
  const handleCreate = async () => {
    setCreateError('')
    if (!newName.trim()) { setCreateError('请输入知识库名称'); return }
    if (!newDeptId) { setCreateError('请选择所属部门'); return }
    setCreating(true)
    try {
      await knowledgeApi.createBase({
        name: newName.trim(),
        department_id: newDeptId,
        description: newDesc.trim(),
      })
      setShowCreate(false)
      setNewName(''); setNewDesc(''); setNewDeptId(0)
      loadBases()
    } catch (e: any) {
      setCreateError(e.response?.data?.error || '创建失败')
    }
    setCreating(false)
  }

  const startEdit = (kb: KnowledgeBaseItem) => {
    setEditKb(kb)
    setEditName(kb.name)
    setEditDesc(kb.description)
  }

  const handleUpdate = async () => {
    if (!editKb) return
    setSaving(true)
    try {
      await knowledgeApi.updateBase(editKb.kb_id, {
        name: editName.trim(),
        description: editDesc.trim(),
      })
      setEditKb(null)
      loadBases()
    } catch (e) {
      console.error('更新失败:', e)
    }
    setSaving(false)
  }

  const handleDeleteKb = async (kbId: string) => {
    if (!await confirm({ title: '确认删除', message: '确定删除此知识库？仅删除本地记录，ES 数据不会被删除。', danger: true })) return
    try {
      await knowledgeApi.deleteBase(kbId)
      if (selectedKbId === kbId) {
        setSelectedKbId(null)
        setKbInfo(null)
      }
      loadBases()
    } catch (e) {
      console.error('删除失败:', e)
    }
  }

  // ── 文档 CRUD ──
  const handleBatchUpload = async (files: File[], categoryL1Id?: number, categoryL2Id?: number) => {
    if (!files.length || !selectedKbId) return
    setUploading(true)
    setUploadingFileIndex(0)
    setUploadingTotal(files.length)
    setUploadProgress(null)
    for (let i = 0; i < files.length; i++) {
      setUploadingFileIndex(i + 1)
      try {
        const { data } = await knowledgeApi.uploadDocument(files[i], {
          kb_id: selectedKbId,
          category_l1_id: categoryL1Id,
          category_l2_id: categoryL2Id,
        })
        const taskId = (data as Record<string, unknown>).task_id as string
        if (taskId) {
          await knowledgeApi.pollTaskStatus(taskId, (status) => setUploadProgress(status))
        }
      } catch (e) {
        console.error(`上传失败 ${files[i].name}:`, e)
      }
    }
    setUploading(false)
    setUploadProgress(null)
    setUploadingFileIndex(0)
    setUploadingTotal(0)
    loadDocuments()
  }

  const toggleActive = async (doc: DocumentItem) => {
    try {
      if (doc.is_active) await knowledgeApi.disableDocument(doc.doc_id)
      else await knowledgeApi.enableDocument(doc.doc_id)
      loadDocuments()
    } catch (e) { console.error('操作失败:', e) }
  }

  const handleDeleteDoc = async (docId: string) => {
    if (!await confirm({ title: '确认删除', message: '确定删除此文档？', danger: true })) return
    try {
      await knowledgeApi.deleteDocument(docId)
      loadDocuments()
    } catch (e) { console.error('删除失败:', e) }
  }

  const handleBatchDelete = async () => {
    if (!await confirm({ title: '批量删除', message: `确定删除选中的 ${selectedIds.size} 个文档？`, danger: true })) return
    for (const id of selectedIds) {
      await knowledgeApi.deleteDocument(id)
    }
    setSelectedIds(new Set())
    loadDocuments()
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === documents.length) setSelectedIds(new Set())
    else setSelectedIds(new Set(documents.map((d) => d.doc_id)))
  }

  const toggleSelect = (id: string) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const docTotalPages = Math.max(1, Math.ceil(docTotal / DOC_PAGE_SIZE))

  // ── 左侧 KB 列表侧边栏 ──
  const filterDepts = useMemo(() => {
    const seen = new Map<number, string>()
    for (const kb of bases) {
      if (kb.department?.id && !seen.has(kb.department.id)) {
        seen.set(kb.department.id, kb.department.name)
      }
    }
    return Array.from(seen.entries())
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
  }, [bases])

  const filtered = filterDeptId
    ? bases.filter((kb) => kb.department?.id === filterDeptId)
    : bases

  const renderSidebar = () => (
    <div className="flex flex-col shrink-0"
      style={{ width: 280, background: 'var(--bg)', borderRight: '1px solid var(--border)' }}>

      {/* 部门筛选（与右侧 h-12 顶部栏对齐） */}
      {filterDepts.length > 1 && (
        <div className="flex items-center px-3 border-b shrink-0" style={{ height: 48, borderColor: 'var(--border)' }}>
          <FilterSelect
            value={filterDeptId?.toString() ?? ''}
            onChange={(v) => setFilterDeptId(v ? Number(v) : null)}
            options={[
              { value: '', label: '全部部门' },
              ...filterDepts.map((d) => {
                const count = bases.filter((kb) => kb.department?.id === d.id).length
                return { value: String(d.id), label: `${d.name} (${count})` }
              }),
            ]}
            className="w-full"
          />
        </div>
      )}

      {/* 知识库列表 */}
      <div className="flex-1 overflow-y-auto py-1">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-xs" style={{ color: 'var(--text-muted)' }}>加载中...</div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-xs gap-2" style={{ color: 'var(--text-muted)' }}>
            <BookOutlined style={{ fontSize: 24, opacity: 0.3 }} />
            <span>暂无知识库</span>
          </div>
        ) : (
          filtered.map((kb) => {
            const isActive = selectedKbId === kb.kb_id
            return (
              <div key={kb.kb_id} className="relative group mx-2 rounded-lg mb-0.5">
                <button
                  onClick={() => handleSelectKb(kb.kb_id)}
                  className="conv-item w-full flex items-center justify-between px-3 py-2 text-sm cursor-pointer transition-colors duration-150 rounded-lg"
                  data-active={isActive}
                  style={{
                    background: isActive ? 'var(--primary-light)' : undefined,
                    color: isActive ? 'var(--primary)' : 'var(--text-secondary)',
                    fontWeight: isActive ? 600 : 400,
                  }}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <BookOutlined style={{ fontSize: 13, flexShrink: 0 }} />
                    <div className="min-w-0">
                      <div className="truncate">{kb.name}</div>
                      {kb.department && (
                        <div className="text-[11px] truncate" style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
                          {kb.department.name}
                        </div>
                      )}
                    </div>
                  </div>
                  <span
                    className="opacity-0 group-hover:opacity-100 p-1 rounded cursor-pointer transition-opacity duration-150 shrink-0"
                    style={{ color: 'var(--text-muted)' }}
                    onClick={(e) => { e.stopPropagation(); setActiveMenu(activeMenu === kb.kb_id ? null : kb.kb_id) }}
                  >
                    <EllipsisOutlined style={{ fontSize: 14 }} />
                  </span>
                </button>

                {/* 下拉菜单 */}
                {activeMenu === kb.kb_id && (
                  <div className="absolute right-2 top-full mt-1 py-1 rounded-lg shadow-lg border z-30"
                    style={{ background: 'var(--surface)', borderColor: 'var(--border)', minWidth: 120 }}>
                    <button
                      onClick={() => { setActiveMenu(null); startEdit(kb) }}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-left text-sm cursor-pointer"
                      style={{ color: 'var(--text)' }}
                      onMouseEnter={(e) => e.currentTarget.style.background = 'var(--primary-light)'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                    >
                      <EditOutlined style={{ fontSize: 13 }} /> 编辑
                    </button>
                    <button
                      onClick={() => { setActiveMenu(null); handleDeleteKb(kb.kb_id) }}
                      className="flex items-center gap-2 w-full px-3 py-1.5 text-left text-sm cursor-pointer"
                      style={{ color: '#ef4444' }}
                      onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239,68,68,0.08)'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                    >
                      <DeleteOutlined style={{ fontSize: 13 }} /> 删除
                    </button>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>

      {/* 底部新建按钮 */}
      <div className="px-5 py-3 border-t" style={{ borderColor: 'var(--border)' }}>
        <button
          onClick={() => {
            setNewDeptId(isSysAdmin ? 0 : (user?.department?.id ?? 0))
            setShowCreate(true)
          }}
          className="w-full flex items-center justify-start gap-2.5 px-3 py-2 rounded-lg text-sm cursor-pointer hover-gray"
          style={{ color: 'var(--text)' }}
        >
          <PlusOutlined style={{ fontSize: 14 }} /> 新建知识库
        </button>
      </div>
    </div>
  )

  // ── 右侧文档区 ──
  const renderContent = () => {
    if (!selectedKbId) {
      return (
        <div className="flex-1 flex flex-col items-center justify-center gap-3"
          style={{ background: 'var(--surface)' }}>
          <BookOutlined style={{ fontSize: 48, opacity: 0.12, color: 'var(--text-muted)' }} />
          <span className="text-sm" style={{ color: 'var(--text-muted)' }}>选择左侧知识库查看文档</span>
        </div>
      )
    }

    return (
      <div className="flex-1 flex flex-col overflow-hidden min-w-0"
        style={{ background: 'var(--surface)' }}>
        {/* 顶部工具栏 */}
        <div className="flex items-center justify-between px-6 h-12 border-b shrink-0"
          style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>
              {kbInfo?.name || selectedKbId}
            </h2>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              共 {docTotal} 个文档
            </span>
            {kbInfo?.department && (
              <span className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: 'rgba(0,123,255,0.1)', color: 'var(--primary)' }}>
                {kbInfo.department.name}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg border"
              style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}>
              <SearchOutlined style={{ color: 'var(--text-muted)', fontSize: 14 }} />
              <input value={docSearch}
                onChange={(e) => { setDocSearch(e.target.value); setDocPage(1) }}
                onKeyDown={(e) => { if (e.key === 'Enter') loadDocuments() }}
                placeholder="搜索文档..."
                className="outline-none text-sm bg-transparent"
                style={{ color: 'var(--text)', width: 140 }} />
            </div>
            <FilterSelect
              value={filterStatus}
              onChange={(v) => { setFilterStatus(v as 'all' | 'completed' | 'other'); setDocPage(1) }}
              options={[
                { value: 'all', label: '全部状态' },
                { value: 'completed', label: '已完成' },
                { value: 'other', label: '处理中/失败' },
              ]}
            />
            <button onClick={() => setShowUploadModal(true)} disabled={uploading}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50 transition-opacity duration-150 hover:opacity-90"
              style={{ background: 'var(--primary)' }}>
              <UploadOutlined /> {uploading ? '上传中...' : '上传文档'}
            </button>
          </div>
        </div>

        {/* 上传进度 */}
        {uploading && (
          <div className="px-6 py-3 border-b"
            style={{ background: 'rgba(0,123,255,0.06)', borderColor: 'var(--border)' }}>
            <div className="flex items-center justify-between text-sm">
              <span style={{ color: 'var(--primary)' }}>
                {uploadProgress?.current_step || uploadProgress?.message || `正在上传 ${uploadingFileIndex}/${uploadingTotal}...`}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>
                {uploadingFileIndex}/{uploadingTotal}
                {uploadProgress ? ` · ${uploadProgress.progress}%` : ''}
              </span>
            </div>
            <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border)' }}>
              <div className="h-full rounded-full transition-all"
                style={{ width: `${uploadProgress?.progress || 0}%`, background: 'var(--primary)' }} />
            </div>
          </div>
        )}

        {/* 批量操作 */}
        {selectedIds.size > 0 && (
          <div className="flex items-center gap-4 px-6 py-2 border-b text-sm"
            style={{ background: 'rgba(0,123,255,0.06)', borderColor: 'var(--border)' }}>
            <span style={{ color: 'var(--primary)' }}>已选择 {selectedIds.size} 个文档</span>
            <button onClick={handleBatchDelete}
              className="flex items-center gap-1 cursor-pointer" style={{ color: '#ef4444' }}>
              <DeleteOutlined /> 批量删除
            </button>
          </div>
        )}

        {/* 文档列表 */}
        <div className="flex-1 overflow-y-auto">
          {docLoading ? (
            <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--text-muted)' }}>
              加载中...
            </div>
          ) : documents.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-sm gap-3"
              style={{ color: 'var(--text-muted)' }}>
              <FileTextOutlined style={{ fontSize: 48, opacity: 0.3 }} />
              <span>暂无文档</span>
              <button onClick={() => setShowUploadModal(true)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-white text-sm cursor-pointer transition-opacity duration-150 hover:opacity-90"
                style={{ background: 'var(--primary)' }}>
                <UploadOutlined /> 上传第一个文档
              </button>
            </div>
          ) : (
            <>
              {/* 列表头 */}
              <div className="shrink-0 sticky top-0 z-10 px-6 py-2 flex items-center border-b"
                style={{
                  background: 'var(--surface)',
                  borderBottomColor: 'var(--border)',
                }}>
                <span className="w-10 shrink-0">
                  <input type="checkbox"
                    checked={selectedIds.size === documents.length && documents.length > 0}
                    onChange={toggleSelectAll}
                    className="accent-blue-500" />
                </span>
                <span className="flex-1 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>文档名称</span>
                <span className="w-16 shrink-0 text-xs font-medium text-center" style={{ color: 'var(--text-secondary)' }}>大小</span>
                <span className="w-28 shrink-0 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>分类</span>
                <span className="w-20 shrink-0 text-xs font-medium text-center" style={{ color: 'var(--text-secondary)' }}>状态</span>
                <span className="w-16 shrink-0 text-xs font-medium text-center" style={{ color: 'var(--text-secondary)' }}>启用</span>
                <span className="w-20 shrink-0 text-xs font-medium text-center" style={{ color: 'var(--text-secondary)' }}>时间</span>
                <span className="w-16 shrink-0" />
              </div>

              {/* 文档行 */}
              {documents.map((doc) => (
                <div key={doc.doc_id}
                  className="group flex items-center px-6 py-3 cursor-pointer transition-colors duration-150"
                  style={{ borderBottom: '1px solid rgba(0,0,0,0.04)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  {/* 勾选 */}
                  <span className="w-10 shrink-0">
                    <input type="checkbox" checked={selectedIds.has(doc.doc_id)}
                      onChange={() => toggleSelect(doc.doc_id)} className="accent-blue-500" />
                  </span>

                  {/* 文档名 */}
                  <span className="flex-1 min-w-0 overflow-hidden">
                    <button onClick={() => navigate(`/knowledge/${selectedKbId}/docs/${doc.doc_id}`)}
                      className="flex items-center gap-2 text-sm cursor-pointer hover:underline min-w-0 w-full"
                      style={{ color: 'var(--primary)' }}>
                      <FileTextOutlined style={{ fontSize: 14, flexShrink: 0 }} />
                      <span className="truncate">{doc.file_name}</span>
                    </button>
                  </span>

                  {/* 大小 */}
                  <span className="w-16 shrink-0 text-xs text-center" style={{ color: 'var(--text-muted)' }}>
                    {doc.file_size > 1048576
                      ? `${(doc.file_size / 1048576).toFixed(1)} MB`
                      : `${(doc.file_size / 1024).toFixed(1)} KB`}
                  </span>

                  {/* 分类（一级/二级分行显示） */}
                  <span className="w-28 shrink-0 flex flex-col gap-0.5">
                    {doc.category_l1?.name ? (
                      <>
                        <span className="text-xs truncate" style={{ color: 'var(--text-secondary)' }}>{doc.category_l1.name}</span>
                        {doc.category_l2?.name && (
                          <span className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>{doc.category_l2.name}</span>
                        )}
                      </>
                    ) : (
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>-</span>
                    )}
                  </span>

                  {/* 状态 */}
                  <span className="w-20 shrink-0 flex justify-center">
                    <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full"
                      style={{
                        background: doc.status === 'completed' ? '#dcfce7'
                          : doc.status === 'failed' ? '#fee2e2'
                          : doc.status === 'processing' ? '#e6f2ff'
                          : '#f3f4f6',
                        color: doc.status === 'completed' ? '#16a34a'
                          : doc.status === 'failed' ? '#ef4444'
                          : doc.status === 'processing' ? '#3b82f6'
                          : '#6b7280',
                      }}>
                      {doc.status === 'completed' ? <><CheckCircleOutlined /> 完成</>
                        : doc.status === 'failed' ? <><StopOutlined /> 失败</>
                        : doc.status === 'processing' ? '处理中'
                        : '待处理'}
                    </span>
                  </span>

                  {/* 启用开关 */}
                  <span className="w-16 shrink-0 flex justify-center">
                    <button onClick={() => toggleActive(doc)}
                      className="relative inline-flex h-6 w-11 items-center rounded-full cursor-pointer transition-colors duration-200 select-none"
                      style={{ background: doc.is_active ? '#16a34a' : '#ef4444' }}
                      title={doc.is_active ? '点击禁用' : '点击启用'}>
                      <span className="inline-block h-4 w-4 rounded-full bg-white transition-transform duration-200 shadow-sm"
                        style={{ transform: doc.is_active ? 'translateX(24px)' : 'translateX(2px)' }} />
                    </button>
                  </span>

                  {/* 时间 */}
                  <span className="w-20 shrink-0 text-xs text-center" style={{ color: 'var(--text-muted)' }}>
                    {doc.created_at ? new Date(doc.created_at).toLocaleDateString('zh-CN') : '-'}
                  </span>

                  {/* 操作（hover 显示） */}
                  <span className="w-16 shrink-0 flex items-center justify-end gap-1">
                    <button onClick={() => setEditingDoc(doc)}
                      className="p-2 rounded cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: 'var(--primary)' }} title="编辑">
                      <EditOutlined style={{ fontSize: 16 }} />
                    </button>
                    <button onClick={() => handleDeleteDoc(doc.doc_id)}
                      className="p-2 rounded cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: 'var(--text-muted)' }} title="删除">
                      <DeleteOutlined style={{ fontSize: 16 }} />
                    </button>
                  </span>
                </div>
              ))}
            </>
          )}
        </div>

        {/* 分页 */}
        {docTotalPages > 1 && (
          <div className="flex items-center justify-between px-6 py-3 border-t shrink-0"
            style={{ borderColor: 'var(--border)' }}>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              第 {docPage}/{docTotalPages} 页，共 {docTotal} 条
            </span>
            <div className="flex items-center gap-1">
              <button disabled={docPage <= 1} onClick={() => setDocPage(1)}
                className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>首页</button>
              <button disabled={docPage <= 1} onClick={() => setDocPage((p) => p - 1)}
                className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>上一页</button>
              <button disabled={docPage >= docTotalPages} onClick={() => setDocPage((p) => p + 1)}
                className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>下一页</button>
              <button disabled={docPage >= docTotalPages} onClick={() => setDocPage(docTotalPages)}
                className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>末页</button>
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* 顶部栏 */}
      <div
        className="flex items-center h-12 border-b shrink-0 px-6"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <BookOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>知识库管理</h2>
        </div>
        <span className="text-xs ml-3" style={{ color: 'var(--text-muted)' }}>
          {bases.length} 个知识库
        </span>
      </div>

      {/* 左右分栏 */}
      <div className="flex flex-1 overflow-hidden">
      {renderSidebar()}
      {renderContent()}

      {/* 创建知识库弹窗 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={(e) => { if (e.target === e.currentTarget) { setShowCreate(false); setCreateError('') } }}>
          <div className="w-full max-w-md rounded-xl p-6 space-y-4" style={{ background: 'var(--surface)' }}
            onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold" style={{ color: 'var(--text)' }}>新建知识库</h3>
            {createError && <p className="text-xs" style={{ color: '#ef4444' }}>{createError}</p>}
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>知识库名称</label>
              <input value={newName} onChange={(e) => setNewName(e.target.value)}
                placeholder="如: IT知识库, HR政策库"
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }} />
            </div>
            {isSysAdmin && (
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>所属部门</label>
                <select value={newDeptId} onChange={(e) => setNewDeptId(Number(e.target.value))}
                  className="w-full px-3 py-2 rounded-lg border text-sm cursor-pointer"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}>
                  <option value={0}>请选择部门</option>
                  {departments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
              </div>
            )}
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>描述（可选）</label>
              <textarea value={newDesc} onChange={(e) => setNewDesc(e.target.value)}
                placeholder="知识库用途说明..." rows={3}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none resize-y"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }} />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button onClick={() => { setShowCreate(false); setCreateError('') }}
                className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>取消</button>
              <button onClick={handleCreate} disabled={creating}
                className="px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50"
                style={{ background: 'var(--primary)' }}>
                {creating ? '创建中...' : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 编辑知识库弹窗 */}
      {editKb && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={(e) => { if (e.target === e.currentTarget) setEditKb(null) }}>
          <div className="w-full max-w-md rounded-xl p-6 space-y-4" style={{ background: 'var(--surface)' }}
            onClick={(e) => e.stopPropagation()}>
            <h3 className="text-base font-semibold" style={{ color: 'var(--text)' }}>
              编辑知识库 - {editKb.kb_id}
            </h3>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>名称</label>
              <input value={editName} onChange={(e) => setEditName(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }} />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>描述</label>
              <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 rounded-lg border text-sm outline-none resize-y"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }} />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button onClick={() => setEditKb(null)}
                className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>取消</button>
              <button onClick={handleUpdate} disabled={saving}
                className="px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50"
                style={{ background: 'var(--primary)' }}>
                {saving ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 上传文档弹窗 */}
      {showUploadModal && (
        <UploadModal
          onClose={() => setShowUploadModal(false)}
          onUpload={(files, l1Id, l2Id) => {
            setShowUploadModal(false)
            handleBatchUpload(files, l1Id, l2Id)
          }}
        />
      )}

      {/* 编辑文档弹窗 */}
      {editingDoc && (
        <DocEditModal
          doc={editingDoc}
          onClose={() => setEditingDoc(null)}
          onSaved={() => { setEditingDoc(null); loadDocuments() }}
        />
      )}
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════
//  上传弹窗组件
// ════════════════════════════════════════════════════════════════

function UploadModal({
  onClose,
  onUpload,
}: {
  onClose: () => void
  onUpload: (files: File[], categoryL1Id?: number, categoryL2Id?: number) => void
}) {
  const [files, setFiles] = useState<File[]>([])
  const [tags, setTags] = useState<TagItem[]>([])
  const [selectedL1, setSelectedL1] = useState<number | undefined>()
  const [selectedL2, setSelectedL2] = useState<number | undefined>()
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    tagsApi.getTree().then(({ data }) => setTags(data)).catch(() => {})
  }, [])

  const l2Options = tags.find((t) => t.id === selectedL1)?.children || []

  const addFiles = (newFiles: FileList | File[]) => {
    const arr = Array.from(newFiles)
    setFiles([...files, ...arr].slice(0, 10))
  }

  const removeFile = (index: number) => {
    setFiles(files.filter((_, i) => i !== index))
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)
  }

  const handleSubmit = () => {
    if (!files.length) return
    onUpload(files, selectedL1, selectedL2)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="w-full max-w-lg rounded-xl p-6 space-y-5" style={{ background: 'var(--surface)' }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold" style={{ color: 'var(--text)' }}>上传文档</h3>
          <button onClick={onClose} className="cursor-pointer p-1" style={{ color: 'var(--text-muted)' }}>
            <CloseOutlined />
          </button>
        </div>

        {/* 拖拽上传区 */}
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className="flex flex-col items-center justify-center py-8 rounded-lg border-2 border-dashed cursor-pointer transition-colors"
          style={{
            borderColor: dragOver ? 'var(--primary)' : 'var(--border)',
            background: dragOver ? 'rgba(0,123,255,0.04)' : 'var(--bg)',
          }}>
          <InboxOutlined style={{ fontSize: 36, color: dragOver ? 'var(--primary)' : 'var(--text-muted)', marginBottom: 8 }} />
          <p className="text-sm" style={{ color: dragOver ? 'var(--primary)' : 'var(--text-secondary)' }}>
            {dragOver ? '松开鼠标上传' : '拖拽文件到此处，或点击选择文件'}
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>支持 PDF、Word、txt、Markdown，一次最多 10 个文件</p>
          <input ref={fileInputRef} type="file" multiple accept=".pdf,.docx,.xlsx,.txt,.md,.pptx"
            className="hidden"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files)
              if (fileInputRef.current) fileInputRef.current.value = ''
            }} />
        </div>

        {/* 已选文件列表 */}
        {files.length > 0 && (
          <div className="space-y-1.5 max-h-36 overflow-y-auto">
            {files.map((file, idx) => (
              <div key={`${file.name}-${idx}`}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
                style={{ background: 'var(--bg)' }}>
                <FileTextOutlined style={{ color: 'var(--text-muted)' }} />
                <span className="flex-1 truncate" style={{ color: 'var(--text)' }}>{file.name}</span>
                <span className="text-xs shrink-0" style={{ color: 'var(--text-muted)' }}>
                  {file.size > 1048576 ? `${(file.size / 1048576).toFixed(1)} MB` : `${(file.size / 1024).toFixed(1)} KB`}
                </span>
                <button onClick={() => removeFile(idx)} className="cursor-pointer shrink-0"
                  style={{ color: 'var(--text-muted)' }}>
                  <CloseOutlined style={{ fontSize: 12 }} />
                </button>
              </div>
            ))}
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>已选 {files.length}/10 个文件</p>
          </div>
        )}

        {/* 标签选择 */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <TagOutlined style={{ color: 'var(--primary)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>分类标签</span>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>所有文件共用同一标签</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>一级分类</label>
              <select value={selectedL1 ?? ''}
                onChange={(e) => { setSelectedL1(e.target.value ? Number(e.target.value) : undefined); setSelectedL2(undefined) }}
                className="w-full px-3 py-2 rounded-lg border text-sm"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}>
                <option value="">不选择</option>
                {tags.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>二级标签</label>
              <select value={selectedL2 ?? ''}
                onChange={(e) => setSelectedL2(e.target.value ? Number(e.target.value) : undefined)}
                disabled={!selectedL1 || l2Options.length === 0}
                className="w-full px-3 py-2 rounded-lg border text-sm disabled:opacity-40"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}>
                <option value="">{!selectedL1 ? '请先选择一级分类' : l2Options.length === 0 ? '无二级标签' : '不选择'}</option>
                {l2Options.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-1">
          <button onClick={onClose}
            className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>取消</button>
          <button onClick={handleSubmit} disabled={!files.length}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50"
            style={{ background: 'var(--primary)' }}>
            <UploadOutlined /> 上传 {files.length > 0 ? `${files.length} 个文件` : ''}
          </button>
        </div>
      </div>
    </div>
  )
}

// ════════════════════════════════════════════════════════════════
//  文档编辑弹窗
// ════════════════════════════════════════════════════════════════

function DocEditModal({
  doc,
  onClose,
  onSaved,
}: {
  doc: DocumentItem
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useUIStore((s) => s.toast)
  const [fileName, setFileName] = useState(doc.file_name)
  const [tags, setTags] = useState<TagItem[]>([])
  const [selectedL1, setSelectedL1] = useState<number | undefined>(doc.category_l1?.id ?? undefined)
  const [selectedL2, setSelectedL2] = useState<number | undefined>(doc.category_l2?.id ?? undefined)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    tagsApi.getTree().then(({ data }) => setTags(data)).catch(() => {})
  }, [])

  const l2Options = tags.find((t) => t.id === selectedL1)?.children || []

  const handleSubmit = async () => {
    const trimmed = fileName.trim()
    if (!trimmed) return
    setSaving(true)
    try {
      await knowledgeApi.updateDocumentMetadata(doc.doc_id, {
        file_name: trimmed,
        category_l1_id: selectedL1 ?? null,
        category_l2_id: selectedL2 ?? null,
      })
      onSaved()
    } catch (e) {
      console.error('保存失败:', e)
      toast('保存失败，请重试', 'error')
    }
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="w-full max-w-md rounded-xl p-6 space-y-5" style={{ background: 'var(--surface)' }}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold" style={{ color: 'var(--text)' }}>编辑文档</h3>
          <button onClick={onClose} className="cursor-pointer p-1" style={{ color: 'var(--text-muted)' }}>
            <CloseOutlined />
          </button>
        </div>

        <div>
          <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--text-secondary)' }}>文档名称</label>
          <input value={fileName} onChange={(e) => setFileName(e.target.value)}
            className="w-full px-3 py-2 rounded-lg border text-sm outline-none"
            style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }} />
        </div>

        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <TagOutlined style={{ color: 'var(--primary)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>分类标签</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>一级分类</label>
              <select value={selectedL1 ?? ''}
                onChange={(e) => { setSelectedL1(e.target.value ? Number(e.target.value) : undefined); setSelectedL2(undefined) }}
                className="w-full px-3 py-2 rounded-lg border text-sm"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}>
                <option value="">不选择</option>
                {tags.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>二级标签</label>
              <select value={selectedL2 ?? ''}
                onChange={(e) => setSelectedL2(e.target.value ? Number(e.target.value) : undefined)}
                disabled={!selectedL1 || l2Options.length === 0}
                className="w-full px-3 py-2 rounded-lg border text-sm disabled:opacity-40"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }}>
                <option value="">{!selectedL1 ? '请先选择一级分类' : l2Options.length === 0 ? '无二级标签' : '不选择'}</option>
                {l2Options.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-1">
          <button onClick={onClose}
            className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>取消</button>
          <button onClick={handleSubmit} disabled={saving || !fileName.trim()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50"
            style={{ background: 'var(--primary)' }}>
            {saving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
