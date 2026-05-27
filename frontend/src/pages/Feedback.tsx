import { useEffect, useState, useCallback } from 'react'
import { dashboardApi, orgApi, type FeedbackItem, type DepartmentItem } from '@/api/org'
import { useAuthStore } from '@/stores/authStore'
import ChatSessionViewerDrawer from '@/components/Chat/ChatSessionViewerDrawer'
import FilterSelect from '@/components/FilterSelect'
import {
  SearchOutlined,
  DownloadOutlined,

  LikeFilled,
  LikeOutlined,
  DislikeFilled,
} from '@ant-design/icons'

const PAGE_SIZE = 20

export default function Feedback() {
  const currentUser = useAuthStore((s) => s.user)
  const isSysAdmin = currentUser?.role === 'sys_admin'

  const [data, setData] = useState<FeedbackItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [departments, setDepartments] = useState<DepartmentItem[]>([])

  // 筛选条件
  const [feedbackType, setFeedbackType] = useState<string>('')
  const [search, setSearch] = useState('')
  const [deptId, setDeptId] = useState<number | undefined>()
  const [dateStart, setDateStart] = useState('')
  const [dateEnd, setDateEnd] = useState('')

  // 会话查看器
  const [viewerConvId, setViewerConvId] = useState<number | null>(null)
  const [viewerMsgId, setViewerMsgId] = useState<number | null>(null)
  const [viewerFeedback, setViewerFeedback] = useState<{
    feedback: 'like' | 'dislike'
    feedback_detail: { reasons: string[]; comment?: string } | null
  } | undefined>(undefined)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const { data: res } = await dashboardApi.getFeedbackList({
        feedback: feedbackType || undefined,
        search: search || undefined,
        department_id: isSysAdmin ? deptId : undefined,
        date_start: dateStart || undefined,
        date_end: dateEnd || undefined,
        page,
        page_size: PAGE_SIZE,
      })
      setData(res.data)
      setTotal(res.total)
    } catch (e) {
      console.error('加载反馈列表失败:', e)
    }
    setLoading(false)
  }, [feedbackType, search, deptId, dateStart, dateEnd, page, isSysAdmin])

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
    loadData()
    loadDepartments()
  }, [loadData, loadDepartments])

  const handleExport = async () => {
    try {
      const { data: blob } = await dashboardApi.exportFeedback({
        feedback: feedbackType || undefined,
        search: search || undefined,
        department_id: isSysAdmin ? deptId : undefined,
        date_start: dateStart || undefined,
        date_end: dateEnd || undefined,
      })
      const url = URL.createObjectURL(blob as unknown as Blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `feedback-export-${new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('导出失败:', e)
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const openViewer = useCallback((item: FeedbackItem) => {
    setViewerConvId(item.conversation_id)
    setViewerMsgId(item.id)
    setViewerFeedback({ feedback: item.feedback, feedback_detail: item.feedback_detail })
  }, [])

  const closeViewer = useCallback(() => {
    setViewerConvId(null)
    setViewerMsgId(null)
    setViewerFeedback(undefined)
  }, [])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 顶部栏 */}
      <div
        className="flex items-center justify-between px-6 h-12 border-b shrink-0"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <LikeOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>反馈管理</h2>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            共 {total} 条反馈
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleExport}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg border text-sm cursor-pointer transition-colors duration-150 hover-gray"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
            <DownloadOutlined /> 导出 Excel
          </button>
        </div>
      </div>

      {/* 筛选区 */}
      <div
        className="flex items-center gap-3 px-6 py-3 border-b shrink-0 flex-wrap"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <FilterSelect
          value={feedbackType}
          onChange={(v) => { setFeedbackType(v); setPage(1) }}
          options={[
            { value: '', label: '全部反馈' },
            { value: 'like', label: '点赞' },
            { value: 'dislike', label: '点踩' },
          ]}
        />

        {isSysAdmin && (
          <FilterSelect
            value={deptId?.toString() ?? ''}
            onChange={(v) => { setDeptId(v ? Number(v) : undefined); setPage(1) }}
            options={[
              { value: '', label: '全部部门' },
              ...departments.map((d) => ({ value: String(d.id), label: d.name })),
            ]}
          />
        )}

        <input type="date" value={dateStart} onChange={(e) => { setDateStart(e.target.value); setPage(1) }}
          className="px-3 py-2 rounded-lg border text-sm"
          style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }} />
        <span className="text-xs" style={{ color: 'var(--text-muted)' }}>至</span>
        <input type="date" value={dateEnd} onChange={(e) => { setDateEnd(e.target.value); setPage(1) }}
          className="px-3 py-2 rounded-lg border text-sm"
          style={{ borderColor: 'var(--border)', background: 'var(--bg)', color: 'var(--text)' }} />

        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border"
          style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}>
          <SearchOutlined style={{ color: 'var(--text-muted)', fontSize: 14 }} />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { setPage(1); loadData() } }}
            placeholder="搜索用户名..."
            className="outline-none text-sm bg-transparent"
            style={{ color: 'var(--text)', width: 120 }} />
        </div>
      </div>

      {/* 卡片信息流 */}
      <div className="flex-1 overflow-y-auto" style={{ padding: '16px 24px' }}>
        {loading ? (
          <div className="flex items-center justify-center h-32 text-sm" style={{ color: 'var(--text-muted)' }}>
            加载中...
          </div>
        ) : data.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-sm" style={{ color: 'var(--text-muted)' }}>
            暂无反馈数据
          </div>
        ) : (
          <div className="space-y-3">
            {data.map((item) => (
              <FeedbackCard key={item.id} item={item} onClick={() => openViewer(item)} />
            ))}
          </div>
        )}
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-6 py-3 border-t shrink-0"
          style={{ borderColor: 'var(--border)' }}>
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            第 {page}/{totalPages} 页，共 {total} 条
          </span>
          <div className="flex items-center gap-1">
            <button disabled={page <= 1} onClick={() => setPage(1)}
              className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
              首页
            </button>
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
              上一页
            </button>
            <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
              下一页
            </button>
            <button disabled={page >= totalPages} onClick={() => setPage(totalPages)}
              className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
              style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
              末页
            </button>
          </div>
        </div>
      )}

      {/* 会话查看器抽屉 */}
      {viewerConvId !== null && (
        <ChatSessionViewerDrawer
          conversationId={viewerConvId}
          highlightMessageId={viewerMsgId ?? undefined}
          feedbackData={viewerFeedback}
          onClose={closeViewer}
        />
      )}
    </div>
  )
}

/** 单条反馈卡片 */
function FeedbackCard({ item, onClick }: { item: FeedbackItem; onClick: () => void }) {
  return (
    <div
      onClick={onClick}
      className="cursor-pointer rounded-xl border transition-all duration-150"
      style={{
        background: 'var(--surface)',
        borderColor: 'var(--border)',
        padding: '16px 20px',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--primary)'
        e.currentTarget.style.background = 'var(--primary-light)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.background = 'var(--surface)'
      }}
    >
      {/* 上方：用户信息（左）| 反馈徽章（右） */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-9 h-9 rounded-full flex items-center justify-center text-xs shrink-0"
            style={{ background: 'var(--primary-light)', color: 'var(--primary)', fontWeight: 600 }}
          >
            {item.user.charAt(0).toUpperCase()}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium" style={{ color: 'var(--text)' }}>{item.user}</span>
              {item.department && (
                <span className="text-xs px-2 py-0.5 rounded-full"
                  style={{ background: 'var(--primary-light)', color: 'var(--primary)' }}>
                  {item.department}
                </span>
              )}
            </div>
            <div className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{item.created_at}</div>
          </div>
        </div>
        {/* 反馈徽章 */}
        {item.feedback === 'like' ? (
          <span className="inline-flex items-center gap-1 text-sm px-3 py-1 rounded-full shrink-0"
            style={{ background: '#dcfce7', color: '#16a34a', fontWeight: 500 }}>
            <LikeFilled /> 赞
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-sm px-3 py-1 rounded-full shrink-0"
            style={{ background: '#fee2e2', color: '#ef4444', fontWeight: 500 }}>
            <DislikeFilled /> 踩
          </span>
        )}
      </div>

      {/* 中间：会话标题 + 内容预览 */}
      <div className="mt-3 ml-12">
        <div className="text-sm font-medium truncate" style={{ color: 'var(--text-secondary)' }}>
          {item.conversation_title}
        </div>
        {item.content_preview && (
          <div className="text-xs mt-1 truncate" style={{ color: 'var(--text-muted)', maxWidth: 400 }}>
            {item.content_preview}
          </div>
        )}
      </div>

      {/* 下方：反馈详情标签 */}
      {item.feedback_detail && (
        <div className="mt-3 ml-12 flex flex-wrap gap-1.5">
          {item.feedback_detail.reasons.map((r, i) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded"
              style={{
                background: item.feedback === 'like' ? '#dcfce7' : '#fee2e2',
                color: item.feedback === 'like' ? '#16a34a' : '#ef4444',
              }}>
              {r}
            </span>
          ))}
          {item.feedback_detail.comment && (
            <span className="text-xs self-center" style={{ color: 'var(--text-muted)' }}>
              {item.feedback_detail.comment}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
