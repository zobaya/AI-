import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  knowledgeApi,
  type ChunkItem,
  type DocumentItem,
  type KnowledgeBaseItem,
} from '@/api/knowledge'
import { useUIStore } from '@/stores/uiStore'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  StopOutlined,
  DeleteOutlined,
  EditOutlined,
  DownOutlined,
  RightOutlined,
  SaveOutlined,
  CloseOutlined,
  ReloadOutlined,
  SearchOutlined,
  WarningOutlined,
  FileTextOutlined,
  EyeOutlined,
} from '@ant-design/icons'

const PAGE_SIZE = 20

export default function ChunkDetail() {
  const { kbId, docId } = useParams<{ kbId: string; docId: string }>()
  const navigate = useNavigate()
  const toast = useUIStore((s) => s.toast)
  const confirm = useUIStore((s) => s.confirm)

  // ── Data state ──
  const [allChunks, setAllChunks] = useState<ChunkItem[]>([])
  const [docInfo, setDocInfo] = useState<DocumentItem | null>(null)
  const [kbInfo, setKbInfo] = useState<KnowledgeBaseItem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // ── Left panel: filter / search / pagination ──
  const [filter, setFilter] = useState<'all' | 'active' | 'inactive'>('all')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  // ── Right panel: selected chunk ──
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedChunk, setSelectedChunk] = useState<ChunkItem | null>(null)

  // ── Edit mode ──
  const [editing, setEditing] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)

  // ── Child chunks ──
  const [children, setChildren] = useState<ChunkItem[]>([])
  const [childrenOpen, setChildrenOpen] = useState(false)
  const [childrenLoading, setChildrenLoading] = useState(false)

  // ── Load data ──
  const loadData = useCallback(async () => {
    if (!docId) return
    setLoading(true)
    setError(null)
    try {
      // Get KB info
      if (kbId) {
        try {
          const { data: kbData } = await knowledgeApi.getBase(kbId)
          setKbInfo(kbData)
        } catch { /* ignore */ }
      }
      // Get doc info first (from Django DB)
      const { data: docList } = await knowledgeApi.getDocuments({ kb_id: kbId })
      const doc = (docList.documents || []).find((d) => d.doc_id === docId)
      if (doc) setDocInfo(doc)

      // Load chunks (from ai-service via proxy), sorted by chunk_id (格式: {doc_id}_P_{N:03d})
      const { data } = await knowledgeApi.getDocumentChunks(docId)
      const sorted = [...(data.chunks || [])].sort((a, b) => a.chunk_id.localeCompare(b.chunk_id))
      setAllChunks(sorted)
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '未知错误'
      setError(msg)
      console.error('加载分块失败:', e)
    }
    setLoading(false)
  }, [docId, kbId])

  useEffect(() => { loadData() }, [loadData])

  // ── Filtered + searched chunks ──
  const filteredChunks = allChunks.filter((c) => {
    if (filter === 'active' && !c.is_active) return false
    if (filter === 'inactive' && c.is_active) return false
    if (search && !c.content.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  const totalPages = Math.max(1, Math.ceil(filteredChunks.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const pagedChunks = filteredChunks.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  // ── Select chunk ──
  const selectChunk = (chunk: ChunkItem) => {
    setSelectedId(chunk.chunk_id)
    setSelectedChunk(chunk)
    setEditing(false)
    setChildren([])
    setChildrenOpen(false)
  }

  // ── Refresh selected chunk data ──
  const refreshSelected = async (chunkId: string) => {
    try {
      const { data } = await knowledgeApi.getChunk(chunkId)
      setSelectedChunk(data)
    } catch {
      // fallback: find from allChunks
      const found = allChunks.find((c) => c.chunk_id === chunkId)
      if (found) setSelectedChunk(found)
    }
  }

  // ── Load children ──
  const loadChildren = async (parentId: string) => {
    setChildrenLoading(true)
    try {
      const { data } = await knowledgeApi.getChildChunks(parentId)
      setChildren(data.chunks || [])
    } catch (e) {
      console.error('加载子块失败:', e)
    }
    setChildrenLoading(false)
  }

  const toggleChildren = () => {
    if (!selectedId) return
    if (!childrenOpen && children.length === 0) {
      loadChildren(selectedId)
    }
    setChildrenOpen(!childrenOpen)
  }

  // ── Edit ──
  const startEdit = () => {
    if (!selectedChunk) return
    setEditing(true)
    setEditContent(selectedChunk.content)
  }

  const cancelEdit = () => {
    setEditing(false)
    setEditContent('')
  }

  const saveEdit = async () => {
    if (!selectedId) return
    setSaving(true)
    try {
      await knowledgeApi.updateChunk(selectedId, { content: editContent })
    } catch {
      toast('保存失败，请重试', 'error')
      setSaving(false)
      return
    }
    setEditing(false)
    try {
      await loadData()
      await refreshSelected(selectedId)
      if (childrenOpen) loadChildren(selectedId)
    } catch {
      // 刷新失败不影响保存结果
    }
    setSaving(false)
  }

  // ── Enable / Disable ──
  const toggleActive = async () => {
    if (!selectedChunk) return
    try {
      if (selectedChunk.is_active) {
        await knowledgeApi.disableChunk(selectedChunk.chunk_id)
      } else {
        await knowledgeApi.enableChunk(selectedChunk.chunk_id)
      }
      await loadData()
      await refreshSelected(selectedChunk.chunk_id)
    } catch (e) {
      console.error('操作失败:', e)
    }
  }

  // ── Delete ──
  const handleDelete = async () => {
    if (!selectedChunk) return
    if (!await confirm({ title: '确认删除', message: '确定删除此分块及其所有子块？', danger: true })) return
    try {
      await knowledgeApi.deleteChunk(selectedChunk.chunk_id)
      setSelectedId(null)
      setSelectedChunk(null)
      setChildren([])
      setChildrenOpen(false)
      loadData()
    } catch (e) {
      console.error('删除失败:', e)
    }
  }

  // ── Parse headers breadcrumb ──
  const getBreadcrumb = (headers: string): string[] => {
    if (!headers) return []
    return headers.split('>').map((h) => h.trim()).filter(Boolean)
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top bar - Breadcrumb */}
      <div
        className="flex items-center justify-between px-6 h-12 border-b shrink-0"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2 text-sm">
          <button
            onClick={() => navigate('/knowledge')}
            className="flex items-center justify-center w-8 h-8 rounded-lg cursor-pointer transition-colors duration-150"
            style={{ color: 'var(--primary)', background: 'var(--primary-light)' }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary)', e.currentTarget.style.color = '#fff')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--primary-light)', e.currentTarget.style.color = 'var(--primary)')}
          >
            <ArrowLeftOutlined style={{ fontSize: 14 }} />
          </button>
          <span style={{ color: 'var(--text-muted)' }}>/</span>
          <button
            onClick={() => navigate('/knowledge')}
            className="cursor-pointer transition-colors duration-150 font-medium"
            style={{ color: 'var(--text-secondary)' }}
            onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--primary)')}
            onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-secondary)')}
          >
            {kbInfo?.name || kbId}
          </button>
          <span style={{ color: 'var(--text-muted)' }}>/</span>
          <span className="font-medium" style={{ color: 'var(--text)' }}>
            {docInfo?.file_name || docId}
          </span>
          {docInfo && (
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              共 {allChunks.length} 个父块
            </span>
          )}
        </div>
        <button
          onClick={loadData}
          className="flex items-center gap-1 px-3 py-1.5 rounded-lg border text-xs cursor-pointer"
          style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
        >
          <ReloadOutlined /> 刷新
        </button>
      </div>

      {/* Main content: left-right split */}
      <div className="flex flex-1 overflow-hidden">
        {/* ── Left sidebar: parent chunk list ── */}
        <div
          className="flex flex-col border-r"
          style={{ width: '35%', minWidth: 300, borderColor: 'var(--border)', background: 'var(--bg)' }}
        >
          {/* Filter tabs */}
          <div
            className="flex border-b shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            {(['all', 'active', 'inactive'] as const).map((f) => (
              <button
                key={f}
                onClick={() => { setFilter(f); setPage(1) }}
                className="flex-1 px-3 py-2.5 text-xs font-medium cursor-pointer transition-colors"
                style={{
                  color: filter === f ? 'var(--primary)' : 'var(--text-muted)',
                  borderBottom: filter === f ? '2px solid var(--primary)' : '2px solid transparent',
                  background: filter === f ? 'rgba(0,123,255,0.04)' : 'transparent',
                }}
              >
                {f === 'all' ? '全部' : f === 'active' ? '启用' : '禁用'}
                <span className="ml-1 opacity-60">
                  {f === 'all'
                    ? allChunks.length
                    : f === 'active'
                      ? allChunks.filter((c) => c.is_active).length
                      : allChunks.filter((c) => !c.is_active).length}
                </span>
              </button>
            ))}
          </div>

          {/* Search */}
          <div
            className="px-3 py-2 border-b shrink-0"
            style={{ borderColor: 'var(--border)' }}
          >
            <div
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border"
              style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
            >
              <SearchOutlined style={{ color: 'var(--text-muted)', fontSize: 12 }} />
              <input
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                placeholder="搜索分块内容..."
                className="outline-none text-xs bg-transparent flex-1"
                style={{ color: 'var(--text)' }}
              />
            </div>
          </div>

          {/* Chunk list */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex items-center justify-center h-32 text-xs" style={{ color: 'var(--text-muted)' }}>
                加载中...
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center h-32 text-xs gap-2 px-4 text-center">
                <WarningOutlined style={{ fontSize: 32, color: '#ef4444', opacity: 0.6 }} />
                <span style={{ color: '#ef4444' }}>加载失败</span>
                <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>{error}</span>
              </div>
            ) : pagedChunks.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-32 text-xs gap-2" style={{ color: 'var(--text-muted)' }}>
                <FileTextOutlined style={{ fontSize: 32, opacity: 0.3 }} />
                {docInfo && docInfo.status !== 'completed' ? (
                  <>
                    <span>文档状态：{docInfo.status === 'processing' ? '处理中' : docInfo.status === 'failed' ? '处理失败' : '待处理'}</span>
                    <span style={{ fontSize: 11, opacity: 0.7 }}>分块需等文档处理完成后才可查看</span>
                  </>
                ) : (
                  <span>暂无分块数据</span>
                )}
              </div>
            ) : (
              pagedChunks.map((chunk, idx) => {
                const isSelected = selectedId === chunk.chunk_id
                const seqNum = (safePage - 1) * PAGE_SIZE + idx + 1
                const preview = chunk.content.length > 120
                  ? chunk.content.slice(0, 120) + '...'
                  : chunk.content

                return (
                  <div
                    key={chunk.chunk_id}
                    onClick={() => selectChunk(chunk)}
                    className="px-4 py-3 border-b cursor-pointer transition-colors"
                    style={{
                      borderColor: isSelected ? 'var(--border)' : 'rgba(0,0,0,0.04)',
                      background: isSelected ? 'rgba(0,123,255,0.06)' : 'transparent',
                      borderLeft: isSelected ? '3px solid var(--primary)' : '3px solid transparent',
                    }}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span style={{
                        width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                        background: chunk.is_active ? 'var(--success)' : '#d1d5db',
                      }} />
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>#{seqNum}</span>
                      <span className="flex-1" />
                      <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        {chunk.chunk_length} 字
                      </span>
                    </div>
                    <p
                      className="text-xs leading-relaxed line-clamp-2"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      {preview}
                    </p>
                  </div>
                )
              })
            )}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div
              className="flex items-center justify-between px-4 py-2 border-t shrink-0"
              style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
            >
              <button
                onClick={() => setPage(Math.max(1, safePage - 1))}
                disabled={safePage <= 1}
                className="px-2.5 py-1 rounded text-xs cursor-pointer disabled:opacity-30 border"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                上一页
              </button>
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {safePage} / {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages, safePage + 1))}
                disabled={safePage >= totalPages}
                className="px-2.5 py-1 rounded text-xs cursor-pointer disabled:opacity-30 border"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                下一页
              </button>
            </div>
          )}
        </div>

        {/* ── Right panel: detail view ── */}
        <div
          className="flex-1 flex flex-col overflow-hidden"
          style={{ background: 'var(--bg)' }}
        >
          {selectedChunk ? (
            <>
              {/* Detail header */}
              <div
                className="flex items-center gap-3 px-6 py-3 border-b shrink-0"
                style={{ borderColor: 'var(--border)' }}
              >
                <span
                  className="text-sm font-semibold"
                  style={{ color: 'var(--text)' }}
                >
                  父块 #{allChunks.indexOf(selectedChunk) + 1}
                </span>
                <span
                  className="text-xs px-2 py-0.5 rounded-full"
                  style={{
                    background: selectedChunk.is_active ? '#dcfce7' : '#fee2e2',
                    color: selectedChunk.is_active ? '#16a34a' : '#ef4444',
                  }}
                >
                  {selectedChunk.is_active ? '启用' : '禁用'}
                </span>

                {/* Breadcrumb from headers */}
                {getBreadcrumb(selectedChunk.headers).length > 0 && (
                  <div className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                    <span>|</span>
                    {getBreadcrumb(selectedChunk.headers).map((h, i, arr) => (
                      <span key={i} className="flex items-center gap-1">
                        {i > 0 && <RightOutlined style={{ fontSize: 8 }} />}
                        <span>{h}</span>
                      </span>
                    ))}
                  </div>
                )}

                <div className="flex-1" />

                {/* Action buttons */}
                <div className="flex items-center gap-1">
                  {!editing && (
                    <button
                      onClick={startEdit}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs cursor-pointer border"
                      style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                    >
                      <EditOutlined /> 编辑
                    </button>
                  )}
                  <button
                    onClick={toggleActive}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs cursor-pointer border"
                    style={{
                      borderColor: 'var(--border)',
                      color: selectedChunk.is_active ? '#ef4444' : '#16a34a',
                    }}
                  >
                    {selectedChunk.is_active ? (
                      <><StopOutlined /> 禁用</>
                    ) : (
                      <><CheckCircleOutlined /> 启用</>
                    )}
                  </button>
                  <button
                    onClick={handleDelete}
                    className="flex items-center gap-1 px-2.5 py-1.5 rounded text-xs cursor-pointer border"
                    style={{ borderColor: 'var(--border)', color: '#ef4444' }}
                  >
                    <DeleteOutlined /> 删除
                  </button>
                </div>
              </div>

              {/* Content area */}
              <div className="flex-1 overflow-y-auto px-6 py-4">
                {/* Card wrapper */}
                <div style={{
                  background: 'var(--surface)',
                  borderRadius: 'var(--card-radius)',
                  boxShadow: 'var(--glass-shadow)',
                  padding: 24,
                }}>
                {/* Edit mode */}
                {editing ? (
                  <div>
                    {/* Reconstruction warning */}
                    <div
                      className="flex items-center gap-2 px-4 py-2.5 rounded-lg mb-4 text-xs"
                      style={{ background: '#fffbeb', color: '#b45309', border: '1px solid #fde68a' }}
                    >
                      <WarningOutlined />
                      <span>修改父块内容将触发子块重建，原有子块数据会被替换</span>
                    </div>

                    <textarea
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      className="w-full p-4 rounded-lg border text-sm leading-relaxed resize-y"
                      style={{
                        borderColor: 'var(--border)',
                        background: 'var(--bg)',
                        color: 'var(--text)',
                        minHeight: 200,
                        maxHeight: 500,
                      }}
                    />
                    <div className="flex items-center justify-between mt-3">
                      <span className="text-xs" style={{ color: editContent.length > 3000 ? '#ef4444' : 'var(--text-muted)' }}>
                        {editContent.length} / 3000 字符
                      </span>
                      <div className="flex gap-2">
                        <button
                          onClick={cancelEdit}
                          className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs cursor-pointer border"
                          style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                        >
                          <CloseOutlined /> 取消
                        </button>
                        <button
                          onClick={saveEdit}
                          disabled={saving || editContent.length > 3000}
                          className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs text-white cursor-pointer disabled:opacity-50"
                          style={{ background: 'var(--primary)' }}
                        >
                          <SaveOutlined /> {saving ? '保存中...' : '保存'}
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  /* View mode */
                  <div>
                    {/* Metadata info */}
                    <div className="flex items-center gap-4 mb-4 text-xs" style={{ color: 'var(--text-muted)' }}>
                      <span>ID: {selectedChunk.chunk_id}</span>
                      <span>{selectedChunk.chunk_length} 字符</span>
                      {selectedChunk.department && <span>部门: {selectedChunk.department}</span>}
                      {selectedChunk.category_l1 && <span>分类: {[selectedChunk.category_l1, selectedChunk.category_l2].filter(Boolean).join(' / ')}</span>}
                    </div>

                    {/* Content display */}
                    <div
                      className="p-4 rounded-lg border text-sm leading-relaxed whitespace-pre-wrap"
                      style={{
                        borderColor: 'var(--border)',
                        background: 'var(--bg)',
                        color: 'var(--text)',
                      }}
                    >
                      {selectedChunk.content}
                    </div>
                  </div>
                )}

                {/* ── Collapsible child chunks panel ── */}
                {!editing && (
                  <div className="mt-6">
                    {/* Toggle button */}
                    <button
                      onClick={toggleChildren}
                      className="flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm cursor-pointer w-full"
                      style={{
                        borderColor: 'var(--border)',
                        background: 'var(--bg)',
                        color: 'var(--text)',
                      }}
                    >
                      {childrenOpen ? (
                        <DownOutlined style={{ fontSize: 10 }} />
                      ) : (
                        <RightOutlined style={{ fontSize: 10 }} />
                      )}
                      <span className="font-medium">子块</span>
                      <span
                        className="text-xs px-1.5 py-0.5 rounded-full"
                        style={{ background: 'var(--surface)', color: 'var(--text-muted)' }}
                      >
                        {children.length || '...'}
                      </span>
                    </button>

                    {/* Child chunks list */}
                    {childrenOpen && (
                      <div className="mt-3 space-y-2">
                        {childrenLoading ? (
                          <div className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
                            加载子块中...
                          </div>
                        ) : children.length === 0 ? (
                          <div className="text-xs py-4 text-center" style={{ color: 'var(--text-muted)' }}>
                            暂无子块
                          </div>
                        ) : (
                          children.map((child, childIdx) => (
                            <div
                              key={child.chunk_id}
                              className="border rounded-lg overflow-hidden"
                              style={{ borderColor: 'var(--border)' }}
                            >
                              {/* Child header */}
                              <div
                                className="flex items-center gap-2 px-4 py-2"
                                style={{ background: 'var(--bg)' }}
                              >
                                <span
                                  className="text-xs font-medium px-1.5 py-0.5 rounded"
                                  style={{ background: 'var(--surface)', color: 'var(--text-muted)' }}
                                >
                                  子块 #{childIdx + 1}
                                </span>
                                <span
                                  className="text-xs px-1.5 py-0.5 rounded-full"
                                  style={{
                                    background: child.is_active ? '#dcfce7' : '#fee2e2',
                                    color: child.is_active ? '#16a34a' : '#ef4444',
                                  }}
                                >
                                  {child.is_active ? '启用' : '禁用'}
                                </span>
                                <span className="flex-1" />
                                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                                  {child.chunk_length} 字
                                </span>
                                <div className="flex items-center gap-1">
                                  <button
                                    onClick={async () => {
                                      try {
                                        if (child.is_active) {
                                          await knowledgeApi.disableChunk(child.chunk_id)
                                        } else {
                                          await knowledgeApi.enableChunk(child.chunk_id)
                                        }
                                        if (selectedId) loadChildren(selectedId)
                                      } catch (e) {
                                        console.error('操作失败:', e)
                                      }
                                    }}
                                    className="p-1 rounded cursor-pointer"
                                    style={{ color: child.is_active ? '#ef4444' : '#16a34a' }}
                                    title={child.is_active ? '禁用' : '启用'}
                                  >
                                    {child.is_active ? (
                                      <StopOutlined style={{ fontSize: 12 }} />
                                    ) : (
                                      <CheckCircleOutlined style={{ fontSize: 12 }} />
                                    )}
                                  </button>
                                  <button
                                    onClick={async () => {
                                      if (!await confirm({ title: '确认删除', message: '确定删除此子块？', danger: true })) return
                                      try {
                                        await knowledgeApi.deleteChunk(child.chunk_id)
                                        if (selectedId) loadChildren(selectedId)
                                      } catch (e) {
                                        console.error('删除失败:', e)
                                      }
                                    }}
                                    className="p-1 rounded cursor-pointer"
                                    style={{ color: 'var(--text-muted)' }}
                                    title="删除"
                                  >
                                    <DeleteOutlined style={{ fontSize: 12 }} />
                                  </button>
                                </div>
                              </div>
                              {/* Child content */}
                              <div
                                className="px-4 py-2.5 border-t text-xs leading-relaxed whitespace-pre-wrap"
                                style={{
                                  borderColor: 'var(--border)',
                                  color: 'var(--text-secondary)',
                                  background: 'var(--bg)',
                                  maxHeight: 120,
                                  overflow: 'auto',
                                }}
                              >
                                {child.content}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                )}
                </div>{/* end card wrapper */}
              </div>
            </>
          ) : (
            /* Empty state */
            <div className="flex flex-col items-center justify-center h-full text-sm gap-3" style={{ color: 'var(--text-muted)' }}>
              <EyeOutlined style={{ fontSize: 48, opacity: 0.3 }} />
              <span>选择左侧分块查看详情</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
