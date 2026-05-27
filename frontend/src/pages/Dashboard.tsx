import { useEffect, useState, useCallback } from 'react'
import { dashboardApi, orgApi, type OverviewData, type TrendItem, type DeptCompareItem, type UserStatsItem, type DepartmentItem } from '@/api/org'
import { useAuthStore } from '@/stores/authStore'
import FilterSelect from '@/components/FilterSelect'
import { BarChartOutlined, DownloadOutlined, SearchOutlined } from '@ant-design/icons'

export default function Dashboard() {
  const currentUser = useAuthStore((s) => s.user)
  const isSysAdmin = currentUser?.role === 'sys_admin'

  const [overview, setOverview] = useState<OverviewData | null>(null)
  const [trend, setTrend] = useState<TrendItem[]>([])
  const [deptCompare, setDeptCompare] = useState<DeptCompareItem[]>([])
  const [loading, setLoading] = useState(true)

  // 员工使用统计
  const [userStats, setUserStats] = useState<UserStatsItem[]>([])
  const [statsTotal, setStatsTotal] = useState(0)
  const [statsPage, setStatsPage] = useState(1)
  const [statsSearch, setStatsSearch] = useState('')
  const [statsDeptId, setStatsDeptId] = useState<number | undefined>()
  const [departments, setDepartments] = useState<DepartmentItem[]>([])
  const STATS_PAGE_SIZE = 20

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [overviewRes, trendRes, deptRes] = await Promise.all([
        dashboardApi.getOverview(),
        dashboardApi.getTrend(),
        dashboardApi.getDeptCompare().catch(() => ({ data: [] })),
      ])
      setOverview(overviewRes.data)
      setTrend(trendRes.data)
      setDeptCompare(deptRes.data as DeptCompareItem[])
    } catch (e) {
      console.error('加载看板数据失败:', e)
    }
    setLoading(false)
  }, [])

  const loadUserStats = useCallback(async () => {
    try {
      const { data: res } = await dashboardApi.getUserStats({
        search: statsSearch || undefined,
        department_id: isSysAdmin ? statsDeptId : undefined,
        page: statsPage,
        page_size: STATS_PAGE_SIZE,
      })
      setUserStats(res.data)
      setStatsTotal(res.total)
    } catch (e) {
      console.error('加载用户统计失败:', e)
    }
  }, [statsSearch, statsDeptId, isSysAdmin, statsPage])

  const loadDepartments = useCallback(async () => {
    if (!isSysAdmin) return
    try {
      const { data } = await orgApi.getDepartments()
      setDepartments(data)
    } catch (e) {
      console.error('加载部门失败:', e)
    }
  }, [isSysAdmin])

  useEffect(() => { loadData() }, [loadData])

  useEffect(() => { loadUserStats() }, [loadUserStats])

  useEffect(() => { loadDepartments() }, [loadDepartments])

  // 简易柱状图：纯 CSS 实现（无需 ECharts 重依赖）
  const maxConvCount = Math.max(...deptCompare.map((d) => d.conversation_count), 1)
  const maxTrendCount = Math.max(...trend.map((t) => t.count), 1)

  // 导出报表（下载 JSON 为文件，后续可接 Excel 导出）
  const handleExport = async () => {
    try {
      const { data } = await dashboardApi.getExportData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `dashboard-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('导出失败:', e)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-sm" style={{ color: 'var(--text-muted)' }}>
        加载中...
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* 顶部 */}
      <div
        className="flex items-center justify-between px-6 h-12 border-b shrink-0"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <BarChartOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>统计看板</h2>
        </div>
        <button onClick={handleExport}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg border text-sm cursor-pointer transition-colors duration-150 hover-gray"
          style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
          <DownloadOutlined /> 导出报表
        </button>
      </div>

      <div className="p-6 space-y-6">
        {/* 概览卡片 */}
        <div className="grid grid-cols-4 gap-4">
          <StatCard label="总用户数" value={overview?.total_users ?? 0} color="#3b82f6" />
          <StatCard label="今日活跃" value={overview?.active_users ?? 0} color="#22c55e" />
          <StatCard label="总对话数" value={overview?.total_conversations ?? 0} color="#f59e0b" />
          <StatCard
            label="满意率"
            value={`${overview?.satisfaction_rate ?? 0}%`}
            color="#8b5cf6"
            subtitle={`${overview?.like_count ?? 0} 赞 / ${overview?.dislike_count ?? 0} 踩`}
          />
        </div>

        {/* 对话趋势 */}
        <div className="border rounded-xl p-5" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
          <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text)' }}>对话趋势</h3>
          {trend.length === 0 ? (
            <p className="text-xs py-8 text-center" style={{ color: 'var(--text-muted)' }}>暂无趋势数据</p>
          ) : (
            <div className="flex items-end gap-1 h-40">
              {trend.slice(-30).map((item, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className="w-full rounded-t transition-all"
                    style={{
                      height: `${(item.count / maxTrendCount) * 120}px`,
                      background: 'var(--primary)',
                      minHeight: item.count > 0 ? 2 : 0,
                      opacity: 0.7,
                    }}
                    title={`${item.date}: ${item.count} 次`}
                  />
                  {i % 5 === 0 && (
                    <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      {item.date.slice(5)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 部门活跃度对比 */}
        {deptCompare.length > 0 && (
          <div className="border rounded-xl p-5" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
            <h3 className="text-sm font-semibold mb-4" style={{ color: 'var(--text)' }}>部门活跃度</h3>
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {deptCompare.map((dept) => (
                <div
                  key={dept.department}
                  className="rounded-xl p-4 border transition-all duration-200 hover:shadow-md"
                  style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}
                >
                  <div className="flex items-center gap-2 mb-3">
                    <div
                      className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold"
                      style={{ background: 'var(--primary)' }}
                    >
                      {dept.department.charAt(0)}
                    </div>
                    <span className="text-sm font-medium truncate" style={{ color: 'var(--text)' }}>
                      {dept.department}
                    </span>
                  </div>
                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-2xl font-bold tabular-nums" style={{ color: 'var(--primary)' }}>
                        {dept.conversation_count}
                      </p>
                      <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>对话数</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>
                        {dept.user_count}
                      </p>
                      <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>成员</p>
                    </div>
                  </div>
                  {/* 活跃度进度条 */}
                  <div className="mt-3 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--border)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.max((dept.conversation_count / maxConvCount) * 100, 4)}%`,
                        background: 'linear-gradient(90deg, var(--primary), var(--primary-dark))',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 员工使用统计 */}
        <div className="border rounded-xl" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
          <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
            <h3 className="text-sm font-semibold" style={{ color: 'var(--text)' }}>员工使用统计</h3>
            <div className="flex items-center gap-2">
              {isSysAdmin && (
                <FilterSelect
                  value={statsDeptId?.toString() ?? ''}
                  onChange={(v) => { setStatsDeptId(v ? Number(v) : undefined); setStatsPage(1) }}
                  options={[
                    { value: '', label: '全部部门' },
                    ...departments.map((d) => ({ value: String(d.id), label: d.name })),
                  ]}
                  small
                />
              )}
              <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg border"
                style={{ borderColor: 'var(--border)', background: 'var(--bg)' }}>
                <SearchOutlined style={{ color: 'var(--text-muted)', fontSize: 12 }} />
                <input value={statsSearch} onChange={(e) => setStatsSearch(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { setStatsPage(1); loadUserStats() } }}
                  placeholder="搜索用户名..."
                  className="outline-none text-xs bg-transparent"
                  style={{ color: 'var(--text)', width: 100 }} />
              </div>
            </div>
          </div>
          <table className="w-full">
            <thead>
              <tr className="text-sm text-left border-b sticky top-0 z-10" style={{ color: 'var(--text-secondary)', borderColor: 'var(--border)', background: 'var(--surface)' }}>
                <th className="px-5 py-2.5 font-medium">用户名</th>
                <th className="px-5 py-2.5 font-medium">部门</th>
                <th className="px-5 py-2.5 font-medium">对话数</th>
                <th className="px-5 py-2.5 font-medium">消息数</th>
                <th className="px-5 py-2.5 font-medium">Token 消耗</th>
                <th className="px-5 py-2.5 font-medium">最后活跃</th>
              </tr>
            </thead>
            <tbody>
              {userStats.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-6 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                    暂无数据
                  </td>
                </tr>
              ) : (
                userStats.map((u) => (
                  <tr key={u.id} className="border-b transition-colors duration-150"
                    style={{ borderColor: 'var(--border)' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--primary-light)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                  >
                    <td className="px-5 py-2.5 text-sm" style={{ color: 'var(--text)' }}>{u.username}</td>
                    <td className="px-5 py-2.5 text-sm" style={{ color: 'var(--text-secondary)' }}>{u.department || '-'}</td>
                    <td className="px-5 py-2.5 text-sm" style={{ color: 'var(--text-secondary)' }}>{u.conversation_count}</td>
                    <td className="px-5 py-2.5 text-sm" style={{ color: 'var(--text-secondary)' }}>{u.message_count}</td>
                    <td className="px-5 py-2.5 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      {u.tokens_used > 1000 ? `${(u.tokens_used / 1000).toFixed(1)}k` : u.tokens_used}
                    </td>
                    <td className="px-5 py-2.5 text-xs" style={{ color: 'var(--text-muted)' }}>{u.last_active || '-'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* 员工统计分页 */}
        {(() => {
          const totalPages = Math.max(1, Math.ceil(statsTotal / STATS_PAGE_SIZE))
          return totalPages > 1 ? (
            <div
              className="flex items-center justify-between px-5 py-3 border-t"
              style={{ borderColor: 'var(--border)' }}
            >
              <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                第 {statsPage}/{totalPages} 页，共 {statsTotal} 条
              </span>
              <div className="flex items-center gap-1">
                <button disabled={statsPage <= 1} onClick={() => setStatsPage(1)}
                  className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                  首页
                </button>
                <button disabled={statsPage <= 1} onClick={() => setStatsPage((p) => p - 1)}
                  className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                  上一页
                </button>
                <button disabled={statsPage >= totalPages} onClick={() => setStatsPage((p) => p + 1)}
                  className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                  下一页
                </button>
                <button disabled={statsPage >= totalPages} onClick={() => setStatsPage(totalPages)}
                  className="px-3 py-1.5 rounded border text-xs cursor-pointer disabled:opacity-30"
                  style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                  末页
                </button>
              </div>
            </div>
          ) : null
        })()}
      </div>
    </div>
  )
}

function StatCard({ label, value, color, subtitle }: {
  label: string; value: number | string; color: string; subtitle?: string
}) {
  return (
    <div
      className="border rounded-xl p-5"
      style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
    >
      <p className="text-xs mb-2" style={{ color: 'var(--text-muted)' }}>{label}</p>
      <p className="text-2xl font-bold tabular-nums" style={{ color }}>{value}</p>
      {subtitle && <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{subtitle}</p>}
    </div>
  )
}
