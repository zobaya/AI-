import { useEffect, useState, useCallback, useMemo } from 'react'
import { tagsApi, type TagItem, type RelatedDoc } from '@/api/tags'
import { useAuthStore } from '@/stores/authStore'
import { useUIStore } from '@/stores/uiStore'
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  TagsOutlined,
  FolderOutlined,
  TagOutlined,
  CaretRightOutlined,
  FileTextOutlined,
  EllipsisOutlined,
  PlusCircleOutlined,
} from '@ant-design/icons'

export default function Tags() {
  const user = useAuthStore((s) => s.user)
  const toast = useUIStore((s) => s.toast)
  const confirmDialog = useUIStore((s) => s.confirm)

  // ── 核心数据 ─────────────────────────────────────────────

  const [tags, setTags] = useState<TagItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set())

  // ── 详情面板 ─────────────────────────────────────────────

  const [documents, setDocuments] = useState<RelatedDoc[]>([])
  const [docTotal, setDocTotal] = useState(0)
  const [docLoading, setDocLoading] = useState(false)

  // ── 菜单 ─────────────────────────────────────────────────

  const [menuTagId, setMenuTagId] = useState<number | null>(null)

  // ── 统一弹窗 ─────────────────────────────────────────────

  const [modalMode, setModalMode] = useState<'createL1' | 'createL2' | 'edit' | null>(null)
  const [modalParent, setModalParent] = useState<TagItem | null>(null)
  const [modalTarget, setModalTarget] = useState<TagItem | null>(null)
  const [modalName, setModalName] = useState('')
  const [modalDesc, setModalDesc] = useState('')
  const [modalError, setModalError] = useState('')
  const [modalSaving, setModalSaving] = useState(false)

  // ── 数据加载 ─────────────────────────────────────────────

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await tagsApi.getTree()
      setTags(data)
    } catch (e) {
      console.error('加载标签失败:', e)
    }
    setLoading(false)
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // 选中标签变化时加载关联文档
  useEffect(() => {
    if (!selectedId) {
      setDocuments([])
      setDocTotal(0)
      return
    }
    setDocLoading(true)
    tagsApi
      .getDocuments(selectedId)
      .then(({ data }) => {
        setDocuments(data.documents)
        setDocTotal(data.total)
      })
      .catch(() => {
        setDocuments([])
        setDocTotal(0)
      })
      .finally(() => setDocLoading(false))
  }, [selectedId])

  // ── 计算值 ───────────────────────────────────────────────

  const selectedTag = useMemo(() => {
    if (!selectedId) return null
    for (const t of tags) {
      if (t.id === selectedId) return t
      if (t.children) {
        for (const c of t.children) {
          if (c.id === selectedId) return c
        }
      }
    }
    return null
  }, [tags, selectedId])

  const totalL1 = tags.length
  const totalL2 = tags.reduce((sum, t) => sum + (t.children?.length || 0), 0)

  // ── 交互处理 ─────────────────────────────────────────────

  const toggleExpand = useCallback((id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const handleSelect = useCallback(
    (tag: TagItem) => {
      setSelectedId(tag.id)
      setMenuTagId(null)
      // L1 标签选中时自动展开
      if (tag.level === 1 && !expandedIds.has(tag.id)) {
        setExpandedIds((prev) => new Set(prev).add(tag.id))
      }
    },
    [expandedIds],
  )

  // ── 弹窗操作 ─────────────────────────────────────────────

  const openCreateL1 = useCallback(() => {
    setModalMode('createL1')
    setModalParent(null)
    setModalTarget(null)
    setModalName('')
    setModalDesc('')
    setModalError('')
  }, [])

  const openCreateL2 = useCallback((parent: TagItem) => {
    setModalMode('createL2')
    setModalParent(parent)
    setModalTarget(null)
    setModalName('')
    setModalDesc('')
    setModalError('')
    setMenuTagId(null)
  }, [])

  const openEdit = useCallback((tag: TagItem) => {
    setModalMode('edit')
    setModalParent(null)
    setModalTarget(tag)
    setModalName(tag.name)
    setModalDesc(tag.description || '')
    setModalError('')
    setMenuTagId(null)
  }, [])

  const handleModalSave = useCallback(async () => {
    if (!modalName.trim()) {
      setModalError('名称不能为空')
      return
    }
    setModalSaving(true)
    setModalError('')
    try {
      if (modalMode === 'createL1') {
        await tagsApi.create({
          name: modalName.trim(),
          description: modalDesc.trim(),
        })
      } else if (modalMode === 'createL2' && modalParent) {
        await tagsApi.create({
          name: modalName.trim(),
          description: modalDesc.trim(),
          parent_id: modalParent.id,
        })
        // 确保父级展开
        setExpandedIds((prev) => new Set(prev).add(modalParent.id))
      } else if (modalMode === 'edit' && modalTarget) {
        await tagsApi.update(modalTarget.id, {
          name: modalName.trim(),
          description: modalDesc.trim(),
        })
      }
      setModalMode(null)
      loadData()
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { error?: string } } })?.response?.data
          ?.error || '操作失败'
      setModalError(msg)
    }
    setModalSaving(false)
  }, [modalMode, modalParent, modalTarget, modalName, modalDesc, loadData])

  // ── 删除 ─────────────────────────────────────────────────

  const handleDelete = useCallback(
    async (tag: TagItem) => {
      setMenuTagId(null)
      const childCount = tag.children?.length || 0
      let msg = ''
      if (tag.level === 1 && childCount > 0) {
        const totalDocs =
          tag.doc_count +
          (tag.children?.reduce((s, c) => s + c.doc_count, 0) || 0)
        msg = `删除一级标签「${tag.name}」将同时删除 ${childCount} 个二级标签。`
        if (totalDocs > 0) msg += `${totalDocs} 篇文档将失去标签标记。`
      } else {
        msg = `确定删除「${tag.name}」？`
        if (tag.doc_count > 0)
          msg += `${tag.doc_count} 篇文档将失去此标签标记。`
      }
      if (!(await confirmDialog({ title: '确认删除', message: msg, danger: true })))
        return
      try {
        await tagsApi.delete(tag.id)
        if (
          selectedId === tag.id ||
          tag.children?.some((c) => c.id === selectedId)
        ) {
          setSelectedId(null)
        }
        loadData()
      } catch (e: unknown) {
        const err =
          (e as { response?: { data?: { error?: string } } })?.response?.data
            ?.error || '删除失败'
        toast(err, 'error')
      }
    },
    [confirmDialog, selectedId, loadData, toast],
  )

  // ── 权限检查 ─────────────────────────────────────────────

  if (user?.role !== 'sys_admin') {
    return (
      <div
        className="flex items-center justify-center h-full text-sm"
        style={{ color: 'var(--text-muted)' }}
      >
        无权访问此页面
      </div>
    )
  }

  // ── 弹窗标题与图标 ──────────────────────────────────────

  const modalTitle =
    modalMode === 'createL1'
      ? '新建一级标签'
      : modalMode === 'createL2'
        ? '添加二级标签'
        : `编辑${modalTarget?.level === 1 ? '一级标签' : '二级标签'}`
  const modalIcon =
    modalMode === 'edit' && modalTarget?.level === 2 ? (
      <TagOutlined style={{ color: 'var(--primary)' }} />
    ) : (
      <FolderOutlined style={{ color: 'var(--primary)' }} />
    )

  // ── 渲染 ─────────────────────────────────────────────────

  return (
    <div className="flex flex-col h-full">
      {/* 顶部栏 */}
      <div
        className="flex items-center h-12 border-b shrink-0 px-6"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <TagsOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>标签管理</h2>
        </div>
        <span className="text-xs ml-3" style={{ color: 'var(--text-muted)' }}>
          {totalL1} 个一级标签 · {totalL2} 个二级标签
        </span>
      </div>

      {/* 左右分栏 */}
      <div className="flex flex-1 overflow-hidden">
      {/* ===== 左侧标签树 ===== */}
      <div
        className="w-72 flex flex-col shrink-0 border-r"
        style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}
      >
        {/* 添加一级标签入口 */}
        <div className="px-4 pt-3 pb-3">
          <button
            onClick={openCreateL1}
            className="flex items-center gap-1.5 w-full justify-center py-2 rounded-lg text-sm cursor-pointer"
            style={{
              color: 'var(--primary)',
              background: 'transparent',
              border: '1px dashed var(--primary)',
              transition: 'background 0.15s cubic-bezier(0.4, 0, 0.2, 1), color 0.15s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.15s cubic-bezier(0.4, 0, 0.2, 1)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--primary-light)'
              e.currentTarget.style.color = 'var(--primary)'
              e.currentTarget.style.borderColor = 'var(--primary)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent'
              e.currentTarget.style.color = 'var(--primary)'
              e.currentTarget.style.borderColor = 'var(--primary)'
            }}
          >
            <PlusOutlined style={{ fontSize: 12 }} /> 添加一级标签
          </button>
        </div>

        <div className="border-b" style={{ borderColor: 'var(--border)' }} />

        {/* 树列表 */}
        <div className="flex-1 overflow-y-auto py-1">
          {loading ? (
            <div
              className="flex items-center justify-center h-32 text-sm"
              style={{ color: 'var(--text-muted)' }}
            >
              加载中...
            </div>
          ) : tags.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 gap-2">
              <TagsOutlined
                style={{ fontSize: 32, opacity: 0.2, color: 'var(--text-muted)' }}
              />
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                暂无标签
              </span>
            </div>
          ) : (
            tags.map((tag) => {
              const expanded = expandedIds.has(tag.id)
              const isSelected = selectedId === tag.id
              const childCount = tag.children?.length || 0
              return (
                <div key={tag.id}>
                  {/* 一级标签行 */}
                  <div
                    className="conv-item flex items-center gap-2 mx-2 px-2 py-2 rounded-lg cursor-pointer group relative"
                    data-active={isSelected}
                    style={{
                      background: isSelected
                        ? 'var(--primary-light)'
                        : undefined,
                    }}
                    onClick={() => handleSelect(tag)}
                  >
                    {/* 展开/折叠 */}
                    {childCount > 0 ? (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          toggleExpand(tag.id)
                        }}
                        className="flex items-center justify-center w-4 h-4 cursor-pointer"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        <CaretRightOutlined
                          style={{
                            fontSize: 10,
                            transition: 'transform 0.2s',
                            transform: expanded
                              ? 'rotate(90deg)'
                              : 'rotate(0deg)',
                          }}
                        />
                      </button>
                    ) : (
                      <span className="w-4" />
                    )}

                    <FolderOutlined
                      style={{ fontSize: 14, color: isSelected ? 'var(--primary)' : 'var(--text-secondary)' }}
                    />

                    <span
                      className="font-medium text-sm flex-1 truncate"
                      style={{ color: isSelected ? 'var(--primary)' : 'var(--text)' }}
                    >
                      {tag.name}
                    </span>

                    {/* 子标签数 */}
                    {childCount > 0 && (
                      <span
                        className="text-xs shrink-0"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {childCount}
                      </span>
                    )}

                    {/* ... 按钮 */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        setMenuTagId(
                          menuTagId === tag.id ? null : tag.id,
                        )
                      }}
                      className="flex items-center justify-center w-6 h-6 rounded cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      <EllipsisOutlined style={{ fontSize: 14 }} />
                    </button>

                    {/* 下拉菜单 */}
                    {menuTagId === tag.id && (
                      <div
                        className="absolute right-2 top-full z-30 min-w-[140px] py-1 rounded-lg shadow-lg border"
                        style={{
                          background: 'var(--surface)',
                          borderColor: 'var(--border)',
                        }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => openCreateL2(tag)}
                          className="flex items-center gap-2 w-full px-3 py-2 text-sm cursor-pointer"
                          style={{ color: 'var(--text)' }}
                          onMouseEnter={(e) =>
                            (e.currentTarget.style.background =
                              'var(--primary-light)')
                          }
                          onMouseLeave={(e) =>
                            (e.currentTarget.style.background = 'transparent')
                          }
                        >
                          <PlusCircleOutlined style={{ fontSize: 13 }} />{' '}
                          添加子标签
                        </button>
                        <button
                          onClick={() => openEdit(tag)}
                          className="flex items-center gap-2 w-full px-3 py-2 text-sm cursor-pointer"
                          style={{ color: 'var(--text)' }}
                          onMouseEnter={(e) =>
                            (e.currentTarget.style.background =
                              'var(--primary-light)')
                          }
                          onMouseLeave={(e) =>
                            (e.currentTarget.style.background = 'transparent')
                          }
                        >
                          <EditOutlined style={{ fontSize: 13 }} /> 编辑
                        </button>
                        <button
                          onClick={() => handleDelete(tag)}
                          className="flex items-center gap-2 w-full px-3 py-2 text-sm cursor-pointer"
                          style={{ color: '#ef4444' }}
                          onMouseEnter={(e) =>
                            (e.currentTarget.style.background = '#fef2f2')
                          }
                          onMouseLeave={(e) =>
                            (e.currentTarget.style.background = 'transparent')
                          }
                        >
                          <DeleteOutlined style={{ fontSize: 13 }} /> 删除
                        </button>
                      </div>
                    )}
                  </div>

                  {/* 二级标签 */}
                  {expanded &&
                    childCount > 0 &&
                    tag.children!.map((child) => {
                      const childSelected = selectedId === child.id
                      return (
                        <div
                          key={child.id}
                          className="conv-item flex items-center gap-2 mx-2 pl-8 pr-2 py-1.5 rounded-lg cursor-pointer group relative"
                          data-active={childSelected}
                          style={{
                            background: childSelected
                              ? 'var(--primary-light)'
                              : undefined,
                          }}
                          onClick={() => handleSelect(child)}
                        >
                          <TagOutlined
                            style={{
                              fontSize: 11,
                              color: childSelected ? 'var(--primary)' : 'var(--text-muted)',
                            }}
                          />

                          <span
                            className={`text-sm flex-1 truncate${childSelected ? ' font-medium' : ''}`}
                            style={{ color: childSelected ? 'var(--primary)' : 'var(--text)' }}
                          >
                            {child.name}
                          </span>

                          {/* ... 按钮 */}
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setMenuTagId(
                                menuTagId === child.id ? null : child.id,
                              )
                            }}
                            className="flex items-center justify-center w-6 h-6 rounded cursor-pointer opacity-0 group-hover:opacity-100 transition-opacity"
                            style={{ color: 'var(--text-muted)' }}
                          >
                            <EllipsisOutlined style={{ fontSize: 14 }} />
                          </button>

                          {menuTagId === child.id && (
                            <div
                              className="absolute right-2 top-full z-30 min-w-[120px] py-1 rounded-lg shadow-lg border"
                              style={{
                                background: 'var(--surface)',
                                borderColor: 'var(--border)',
                              }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <button
                                onClick={() => openEdit(child)}
                                className="flex items-center gap-2 w-full px-3 py-2 text-sm cursor-pointer"
                                style={{ color: 'var(--text)' }}
                                onMouseEnter={(e) =>
                                  (e.currentTarget.style.background =
                                    'var(--primary-light)')
                                }
                                onMouseLeave={(e) =>
                                  (e.currentTarget.style.background =
                                    'transparent')
                                }
                              >
                                <EditOutlined style={{ fontSize: 13 }} /> 编辑
                              </button>
                              <button
                                onClick={() => handleDelete(child)}
                                className="flex items-center gap-2 w-full px-3 py-2 text-sm cursor-pointer"
                                style={{ color: '#ef4444' }}
                                onMouseEnter={(e) =>
                                  (e.currentTarget.style.background = '#fef2f2')
                                }
                                onMouseLeave={(e) =>
                                  (e.currentTarget.style.background =
                                    'transparent')
                                }
                              >
                                <DeleteOutlined style={{ fontSize: 13 }} />{' '}
                                删除
                              </button>
                            </div>
                          )}
                        </div>
                      )
                    })}
                </div>
              )
            })
          )}
        </div>

      </div>

      {/* ===== 右侧详情面板 ===== */}
      <div className="flex-1 overflow-y-auto" style={{ background: 'var(--surface)' }}>
        {selectedTag ? (
          <div className="max-w-5xl mx-auto px-8 py-8">
            {/* 头部 */}
            <div className="flex items-start justify-between mb-1">
              <div className="flex items-center gap-3">
                {selectedTag.level === 1 ? (
                  <FolderOutlined
                    style={{ fontSize: 24, color: 'var(--primary)' }}
                  />
                ) : (
                  <TagOutlined
                    style={{ fontSize: 24, color: 'var(--primary)' }}
                  />
                )}
                <div>
                  <h3
                    className="text-xl font-bold"
                    style={{ color: 'var(--text)' }}
                  >
                    {selectedTag.name}
                  </h3>
                  <p
                    className="text-xs mt-0.5"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    {selectedTag.level === 1 ? '一级标签' : '二级标签'}
                    {selectedTag.level === 1 &&
                      selectedTag.children &&
                      selectedTag.children.length > 0 &&
                      ` · ${selectedTag.children.length} 个子标签`}
                    {selectedTag.doc_count > 0 &&
                      ` · ${selectedTag.doc_count} 篇文档`}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                  {/* 一级标签：显示「添加二级标签」主按钮 */}
                  {selectedTag.level === 1 && (
                    <button
                      onClick={() => openCreateL2(selectedTag)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium cursor-pointer text-white transition-opacity duration-150 hover:opacity-90"
                      style={{ background: 'var(--primary)' }}
                    >
                      <PlusOutlined style={{ fontSize: 12 }} /> 添加二级标签
                    </button>
                  )}
                  <button
                    onClick={() => openEdit(selectedTag)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm cursor-pointer"
                    style={{
                      borderColor: 'var(--border)',
                      color: 'var(--text-secondary)',
                      transition: 'color 0.15s ease, border-color 0.15s ease, background 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = 'var(--primary)'
                      e.currentTarget.style.borderColor = 'var(--primary)'
                      e.currentTarget.style.background = 'var(--primary-light)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = 'var(--text-secondary)'
                      e.currentTarget.style.borderColor = 'var(--border)'
                      e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    <EditOutlined style={{ fontSize: 13 }} /> 编辑
                  </button>
                  <button
                    onClick={() => handleDelete(selectedTag)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm cursor-pointer"
                    style={{
                      borderColor: 'var(--border)',
                      color: 'var(--text-secondary)',
                      transition: 'color 0.15s ease, border-color 0.15s ease, background 0.15s ease',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = '#ef4444'
                      e.currentTarget.style.borderColor = '#ef4444'
                      e.currentTarget.style.background = 'rgba(239, 68, 68, 0.06)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = 'var(--text-secondary)'
                      e.currentTarget.style.borderColor = 'var(--border)'
                      e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    <DeleteOutlined style={{ fontSize: 13 }} /> 删除
                  </button>
                </div>
            </div>

            {/* 分割线 */}
            <div className="border-b my-5" style={{ borderColor: 'var(--divider-subtle)' }} />

            {/* 概览卡片 */}
            <div className="flex gap-4 mb-6">
              {/* 描述卡片 */}
              <div
                className="flex-1 p-4 rounded-lg border"
                style={{
                  borderColor: 'var(--border)',
                  background: 'var(--surface)',
                }}
              >
                <div className="flex items-center gap-2 mb-2">
                  <FileTextOutlined
                    style={{ fontSize: 14, color: 'var(--primary)' }}
                  />
                  <span
                    className="text-xs font-medium"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    描述
                  </span>
                </div>
                <p
                  className="text-sm leading-relaxed"
                  style={{
                    color: selectedTag.description
                      ? 'var(--text)'
                      : 'var(--text-muted)',
                  }}
                >
                  {selectedTag.description || '暂无描述'}
                </p>
              </div>

              {/* 文档数卡片 */}
              <div
                className="w-36 p-4 rounded-lg border flex flex-col items-center justify-center shrink-0"
                style={{
                  borderColor: 'var(--border)',
                  background: 'var(--surface)',
                }}
              >
                <span
                  className="text-2xl font-bold"
                  style={{ color: 'var(--primary)' }}
                >
                  {selectedTag.doc_count}
                </span>
                <span
                  className="text-xs mt-1"
                  style={{ color: 'var(--text-muted)' }}
                >
                  关联文档
                </span>
              </div>
            </div>

            {/* 文档列表 */}
            <div>
              <h4
                className="text-sm font-medium mb-3"
                style={{ color: 'var(--text)' }}
              >
                关联文档{' '}
                {docTotal > 0 && (
                  <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>
                    ({docTotal})
                  </span>
                )}
              </h4>

              {docLoading ? (
                <div
                  className="text-sm py-4"
                  style={{ color: 'var(--text-muted)' }}
                >
                  加载中...
                </div>
              ) : documents.length === 0 ? (
                <div className="flex flex-col items-center py-8 gap-2">
                  <FileTextOutlined
                    style={{
                      fontSize: 32,
                      opacity: 0.15,
                      color: 'var(--text-muted)',
                    }}
                  />
                  <span
                    className="text-xs"
                    style={{ color: 'var(--text-muted)' }}
                  >
                    暂无关联文档
                  </span>
                </div>
              ) : (
                <div>
                  {documents.map((doc) => (
                    <div
                      key={doc.id}
                      className="flex items-center gap-3 py-2.5"
                      style={{ borderBottom: '1px solid var(--divider-subtle)' }}
                    >
                      <FileTextOutlined
                        style={{ fontSize: 14, color: 'var(--text-muted)' }}
                      />
                      <span
                        className="text-sm flex-1 truncate"
                        style={{ color: 'var(--text)' }}
                      >
                        {doc.file_name}
                      </span>
                      {doc.kb_name && (
                        <span
                          className="text-xs shrink-0"
                          style={{ color: 'var(--text-muted)' }}
                        >
                          {doc.kb_name}
                        </span>
                      )}
                    </div>
                  ))}
                  {docTotal > documents.length && (
                    <p
                      className="text-xs mt-2"
                      style={{ color: 'var(--text-muted)' }}
                    >
                      仅展示前 {documents.length} 条，共 {docTotal} 条
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* 创建信息 */}
            <div
              className="mt-6 pt-4 border-t"
              style={{ borderColor: 'var(--divider-subtle)' }}
            >
              <div
                className="flex items-center gap-4 text-xs"
                style={{ color: 'var(--text-muted)' }}
              >
                {selectedTag.created_by && (
                  <span>创建者: {selectedTag.created_by}</span>
                )}
                <span>
                  创建时间:{' '}
                  {new Date(selectedTag.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          </div>
        ) : (
          /* 空状态 */
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <TagsOutlined
              style={{
                fontSize: 48,
                opacity: 0.12,
                color: 'var(--text-muted)',
              }}
            />
            <span
              className="text-sm"
              style={{ color: 'var(--text-muted)' }}
            >
              选择左侧标签查看详情
            </span>
          </div>
        )}
      </div>

      {/* ===== 菜单关闭层 ===== */}
      {menuTagId !== null && (
        <div
          className="fixed inset-0 z-20"
          onClick={() => setMenuTagId(null)}
        />
      )}

      {/* ===== 统一创建/编辑弹窗 ===== */}
      {modalMode && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={() => setModalMode(null)}
        >
          <div
            className="w-full max-w-md rounded-xl p-6 space-y-4"
            style={{ background: 'var(--surface)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3
              className="text-base font-semibold flex items-center gap-2"
              style={{ color: 'var(--text)' }}
            >
              {modalIcon} {modalTitle}
            </h3>

            {modalError && (
              <p className="text-xs" style={{ color: '#ef4444' }}>
                {modalError}
              </p>
            )}

            {/* 所属一级标签（仅创建二级标签时显示，只读） */}
            {modalMode === 'createL2' && modalParent && (
              <div>
                <label
                  className="block text-xs mb-1"
                  style={{ color: 'var(--text-muted)' }}
                >
                  所属一级标签
                </label>
                <input
                  readOnly
                  value={modalParent.name}
                  className="w-full px-3 py-2.5 rounded-lg border text-sm outline-none cursor-not-allowed"
                  style={{
                    borderColor: 'var(--border)',
                    background: 'var(--bg)',
                    color: 'var(--text-secondary)',
                  }}
                />
              </div>
            )}

            <div>
              <label
                className="block text-xs mb-1"
                style={{ color: 'var(--text-muted)' }}
              >
                标签名称
              </label>
              <input
                value={modalName}
                onChange={(e) => setModalName(e.target.value)}
                placeholder={
                  modalMode === 'createL1'
                    ? '如: 技术文档、产品手册'
                    : '如: API文档、使用指南'
                }
                className="w-full px-3 py-2.5 rounded-lg border text-sm outline-none"
                style={{
                  borderColor: 'var(--border)',
                  background: 'var(--bg)',
                  color: 'var(--text)',
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleModalSave()
                }}
              />
            </div>

            <div>
              <label
                className="block text-xs mb-1"
                style={{ color: 'var(--text-muted)' }}
              >
                描述（可选）
              </label>
              <textarea
                value={modalDesc}
                onChange={(e) => setModalDesc(e.target.value)}
                rows={3}
                className="w-full px-3 py-2.5 rounded-lg border text-sm outline-none resize-y"
                style={{
                  borderColor: 'var(--border)',
                  background: 'var(--bg)',
                  color: 'var(--text)',
                }}
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setModalMode(null)}
                className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
                style={{
                  borderColor: 'var(--border)',
                  color: 'var(--text-secondary)',
                }}
              >
                取消
              </button>
              <button
                onClick={handleModalSave}
                disabled={modalSaving}
                className="px-4 py-2 rounded-lg text-white text-sm font-medium cursor-pointer disabled:opacity-50"
                style={{ background: 'var(--primary)' }}
              >
                {modalSaving
                  ? '保存中...'
                  : modalMode === 'edit'
                    ? '保存'
                    : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  )
}
