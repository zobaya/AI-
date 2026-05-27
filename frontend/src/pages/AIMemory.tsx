import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { BulbOutlined, CloseOutlined, PlusCircleOutlined, DeleteOutlined, InboxOutlined } from '@ant-design/icons'
import { memoryApi, type MemoryItem } from '@/api/chat'
import { useUIStore } from '@/stores/uiStore'
import { formatRelativeTime } from '@/utils/relativeTime'

const CATEGORIES = [
  { key: 'preference', label: '偏好', color: '#dbeafe', textColor: '#2563eb' },
  { key: 'knowledge', label: '知识', color: '#dcfce7', textColor: '#16a34a' },
  { key: 'goal', label: '目标', color: '#fef3c7', textColor: '#d97706' },
  { key: 'context', label: '背景', color: '#f3e8ff', textColor: '#7c3aed' },
] as const

const TABS = [
  { key: 'all', label: '全部' },
  { key: 'preference', label: '偏好' },
  { key: 'knowledge', label: '知识' },
  { key: 'goal', label: '目标' },
  { key: 'context', label: '背景' },
] as const

function getCategoryStyle(key: string) {
  return CATEGORIES.find((c) => c.key === key) ?? CATEGORIES[0]
}

export default function AIMemory() {
  const navigate = useNavigate()
  const toast = useUIStore((s) => s.toast)
  const confirm = useUIStore((s) => s.confirm)

  const [memories, setMemories] = useState<MemoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<string>('all')
  const [newFact, setNewFact] = useState('')
  const [newCategory, setNewCategory] = useState<string>('preference')
  const [saving, setSaving] = useState(false)

  // 加载记忆列表
  const loadMemories = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await memoryApi.list()
      setMemories(data.facts)
    } catch {
      toast('加载记忆失败', 'error')
    }
    setLoading(false)
  }, [toast])

  useEffect(() => {
    loadMemories()
  }, [loadMemories])

  // 添加记忆
  const handleAdd = async () => {
    const fact = newFact.trim()
    if (!fact) return
    setSaving(true)
    try {
      const { data } = await memoryApi.create({ fact, category: newCategory })
      if (data.facts.length > 0) {
        setMemories((prev) => [data.facts[0], ...prev])
      }
      setNewFact('')
      toast('记忆已添加', 'success')
    } catch {
      toast('添加失败', 'error')
    }
    setSaving(false)
  }

  // 删除记忆
  const handleDelete = async (m: MemoryItem) => {
    const preview = m.fact.length > 50 ? m.fact.slice(0, 50) + '...' : m.fact
    const ok = await confirm({
      title: '删除记忆',
      message: `确定要删除这条记忆吗？\n「${preview}」`,
      danger: true,
    })
    if (!ok) return
    try {
      await memoryApi.delete(m.id)
      setMemories((prev) => prev.filter((item) => item.id !== m.id))
      toast('记忆已删除', 'success')
    } catch {
      toast('删除失败', 'error')
    }
  }

  // 按分类计算计数
  const counts = memories.reduce<Record<string, number>>((acc, m) => {
    acc[m.category] = (acc[m.category] || 0) + 1
    return acc
  }, {})
  const totalCount = memories.length

  // 按当前 tab 筛选
  const filtered = activeTab === 'all' ? memories : memories.filter((m) => m.category === activeTab)

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* 顶部栏 */}
      <div
        className="flex items-center justify-between px-6 h-12 border-b shrink-0 sticky top-0 z-10"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <BulbOutlined style={{ fontSize: 18, color: 'var(--primary)' }} />
          <h2 className="text-base font-bold" style={{ color: 'var(--text)' }}>AI 记忆</h2>
        </div>
        <button
          onClick={() => navigate('/settings')}
          className="w-8 h-8 flex items-center justify-center rounded-lg transition-colors cursor-pointer hover:opacity-80"
          style={{ color: 'var(--text-muted)' }}
          title="返回设置"
        >
          <CloseOutlined style={{ fontSize: 16 }} />
        </button>
      </div>

      <div className="max-w-4xl mx-auto w-full p-6 space-y-6">
        {/* 提示文案 */}
        <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
          AI 在过去对话中记住的关于您的信息。AI 会基于这些记忆为您提供更懂您的个性化回答，您可以随时添加、修改或删除它们。
        </p>

        {/* 添加记忆卡片 */}
        <section
          className="border rounded-xl p-5"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--surface)',
            boxShadow: 'var(--glass-shadow)',
          }}
        >
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2" style={{ color: 'var(--text)' }}>
            <PlusCircleOutlined style={{ color: 'var(--primary)' }} />
            主动告诉 AI
          </h3>

          <textarea
            value={newFact}
            onChange={(e) => setNewFact(e.target.value)}
            placeholder="比如：我是一个10年经验的Go后端，平时喜欢看技术源码..."
            rows={2}
            className="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-all duration-200 resize-none leading-relaxed"
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

          <div className="flex items-center justify-between mt-3">
            {/* 分类选择器 */}
            <div className="flex gap-2">
              {CATEGORIES.map((cat) => (
                <button
                  key={cat.key}
                  onClick={() => setNewCategory(cat.key)}
                  className="px-3 py-1.5 rounded-lg text-xs cursor-pointer transition-all duration-200 border"
                  style={{
                    borderColor: newCategory === cat.key ? cat.textColor : 'var(--border)',
                    background: newCategory === cat.key ? cat.color : 'transparent',
                    color: newCategory === cat.key ? cat.textColor : 'var(--text-secondary)',
                    fontWeight: newCategory === cat.key ? 600 : 400,
                  }}
                >
                  {cat.label}
                </button>
              ))}
            </div>

            {/* 添加按钮 */}
            <button
              onClick={handleAdd}
              disabled={!newFact.trim() || saving}
              className="px-4 py-1.5 rounded-lg text-white text-sm cursor-pointer disabled:opacity-50 transition-opacity duration-150"
              style={{
                background: 'linear-gradient(135deg, var(--primary), var(--primary-dark))',
                boxShadow: '0 2px 8px rgba(0, 123, 255, 0.25)',
              }}
            >
              {saving ? '添加中...' : '添加记忆'}
            </button>
          </div>
        </section>

        {/* Tab 筛选栏 */}
        <div className="flex items-center gap-1 border-b" style={{ borderColor: 'var(--border)' }}>
          {TABS.map((tab) => {
            const count = tab.key === 'all' ? totalCount : (counts[tab.key] || 0)
            const isActive = activeTab === tab.key
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className="px-4 py-2.5 text-sm cursor-pointer transition-colors duration-150 relative"
                style={{
                  color: isActive ? 'var(--primary)' : 'var(--text-secondary)',
                  fontWeight: isActive ? 600 : 400,
                }}
              >
                <span>{tab.label}</span>
                <span
                  className="ml-1 text-xs"
                  style={{ color: isActive ? 'var(--primary)' : 'var(--text-muted)' }}
                >
                  {count}
                </span>
                {/* 底部指示条 */}
                {isActive && (
                  <span
                    className="absolute bottom-0 left-4 right-4 h-0.5 rounded-full"
                    style={{ background: 'var(--primary)' }}
                  />
                )}
              </button>
            )
          })}
        </div>

        {/* 卡片网格 / 空状态 */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <span className="text-sm" style={{ color: 'var(--text-muted)' }}>加载中...</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12">
            <InboxOutlined style={{ fontSize: 48, color: 'var(--text-muted)' }} />
            <p className="mt-3 text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>暂无记忆</p>
            <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
              对话中 AI 会自动记录你的偏好和重要信息，也可以手动添加
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filtered.map((m) => {
              const cat = getCategoryStyle(m.category)
              return (
                <div
                  key={m.id}
                  className="border rounded-xl p-4 transition-all duration-150 group"
                  style={{
                    borderColor: 'var(--border)',
                    background: 'var(--surface)',
                    boxShadow: 'var(--glass-shadow)',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.borderColor = 'var(--primary)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.borderColor = 'var(--border)'
                  }}
                >
                  {/* 顶行：分类标签 + 删除按钮 */}
                  <div className="flex items-center justify-between mb-2">
                    <span
                      className="badge rounded-full px-2.5 py-0.5"
                      style={{ background: cat.color, color: cat.textColor }}
                    >
                      {cat.label}
                    </span>
                    <button
                      onClick={() => handleDelete(m)}
                      className="p-1 rounded cursor-pointer transition-colors duration-150 opacity-0 group-hover:opacity-100"
                      style={{ color: 'var(--text-muted)' }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.color = '#ef4444'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.color = 'var(--text-muted)'
                      }}
                      title="删除"
                    >
                      <DeleteOutlined style={{ fontSize: 14 }} />
                    </button>
                  </div>

                  {/* 事实文本 */}
                  <p className="text-sm leading-relaxed" style={{ color: 'var(--text)' }}>
                    {m.fact}
                  </p>

                  {/* 底行：时间 + 来源 */}
                  <div className="flex items-center gap-2 mt-3 text-xs" style={{ color: 'var(--text-muted)' }}>
                    <span>{formatRelativeTime(m.updated_at)}</span>
                    <span>·</span>
                    <span>{m.source_conv_id ? '自动提取' : '手动添加'}</span>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
