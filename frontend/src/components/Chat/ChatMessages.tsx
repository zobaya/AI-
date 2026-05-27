import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react'
import { CopyOutlined, LikeOutlined, LikeFilled, DislikeOutlined, DislikeFilled, RedoOutlined, CheckOutlined, DownloadOutlined, FilePptOutlined, CloseOutlined, EditOutlined } from '@ant-design/icons'
import { chatApi, type Message, parsePPTFileMarkers, downloadGeneratedFile, type PPTFileInfo } from '@/api/chat'
import { renderMarkdown } from '@/utils/markdown'
import type { StreamingMessage } from '@/hooks/useChatStream'
import { useAuthStore } from '@/stores/authStore'

export interface ChatMessagesHandle {
  scrollToBottom: () => void
}

interface Props {
  messages: Message[]
  streamingMessage: StreamingMessage | null
  onSuggestClick: (q: string) => void
  onResend: (deleteFromMsgId: number, query: string) => void
  onScrollAway?: (away: boolean) => void
}

/** 从 metadata_json.entries 中提取可展示的条目 */
function getEntries(metadata: Record<string, unknown>) {
  const entries = metadata?.entries as Array<Record<string, unknown>> | undefined
  if (!entries || !Array.isArray(entries) || entries.length === 0) return null
  return entries
}

/** 从 entries 中提取 maybe 推荐问题 */
function getMaybeQuestions(entries: Array<Record<string, unknown>>) {
  return entries
    .filter(e => String(e.event || e.type) === 'maybe')
    .flatMap(e => (e.questions as string[]) || [])
    .slice(0, 3)
}


// ── 可折叠卡片组件 ──────────────────────────────────────────

interface CollapsibleCardProps {
  /** 卡片样式类名前缀，如 'think-card' | 'tool-card' | 'rewrite-card' */
  variant: string
  /** 标题 */
  title: string
  /** 标题右侧副文本（如 "完成"、"执行中..."） */
  subtitle?: string
  /** 左侧 SVG 图标 */
  icon: React.ReactNode
  /** 是否默认展开 */
  defaultOpen?: boolean
  /** 状态点颜色 key */
  statusDot?: 'running' | 'done' | null
  /** 卡片内容 */
  children: React.ReactNode
}

function CollapsibleCard({
  variant,
  title,
  subtitle,
  icon,
  defaultOpen = true,
  statusDot,
  children,
}: CollapsibleCardProps) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <div className={`collapsible-card ${variant}`} style={{ marginBottom: 8 }}>
      <div
        className="collapsible-header"
        onClick={() => setOpen(prev => !prev)}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setOpen(prev => !prev) }}
      >
        <span className="card-icon">{icon}</span>
        <span className="card-title">{title}</span>
        <span className="header-spacer" />
        {statusDot && <span className={`status-dot ${statusDot}`} style={{ marginRight: 8 }} />}
        {subtitle && <span className="card-subtitle">{subtitle}</span>}
        <svg
          className={`chevron-icon ${open ? '' : 'collapsed'}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </div>
      <div className={`collapsible-body ${open ? '' : 'collapsed'}`}>
        <div className={`${variant}-content`}>
          {children}
        </div>
      </div>
    </div>
  )
}


// ── SVG 图标常量 ──────────────────────────────────────────────

const ThinkIcon = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2a8 8 0 0 0-8 8c0 3.1 1.8 5.8 4.4 7.1.3.2.6.5.6.9V20a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2v-2c0-.4.3-.7.6-.9A8 8 0 0 0 20 10a8 8 0 0 0-8-2z" />
    <path d="M9 22h6" />
  </svg>
)

const ToolIcon = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
)

const RewriteIcon = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    <path d="m15 5 4 4" />
  </svg>
)


// ── 猜你想问 ──────────────────────────────────────────────────

function MaybeQuestions({ questions, onClick }: { questions: string[]; onClick: (q: string) => void }) {
  return (
    <div style={{ padding: '12px 0 0 0', marginTop: 8, borderTop: '1px solid var(--border)' }}>
      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-muted)', marginBottom: 10 }}>
        猜你想问：
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {questions.map((q, i) => (
          <button
            key={i}
            onClick={() => onClick(q)}
            style={{
              padding: '8px 16px',
              borderRadius: 20,
              fontSize: 'var(--text-sm)',
              cursor: 'pointer',
              border: '1px solid rgba(0, 123, 255, 0.15)',
              background: 'var(--primary-light)',
              color: 'var(--primary)',
              transition: 'all 0.2s ease',
              fontWeight: 500,
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'scale(1.02)'
              e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,123,255,0.12)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'scale(1)'
              e.currentTarget.style.boxShadow = 'none'
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}


// ── PPT 下载卡片 ──────────────────────────────────────────────

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function PPTDownloadCard({ file }: { file: PPTFileInfo }) {
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')

  const handleDownload = async () => {
    if (!file.file_id) {
      setError('文件记录不存在')
      return
    }
    setDownloading(true)
    setError('')
    try {
      await downloadGeneratedFile(file.file_id, file.file_name)
    } catch (e) {
      setError('下载失败')
      console.error('PPT 下载失败:', e)
    }
    setDownloading(false)
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12,
      padding: '12px 16px', borderRadius: 8,
      border: '1px solid var(--border)', marginTop: 12,
      background: 'var(--bg-secondary)',
    }}>
      <FilePptOutlined style={{ fontSize: 32, color: 'var(--primary)' }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 500, fontSize: 'var(--text-base)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {file.file_name}
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: 2 }}>
          {formatFileSize(file.file_size)} · {file.slide_count} 页
        </div>
      </div>
      <button
        onClick={handleDownload}
        disabled={downloading}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '8px 16px', borderRadius: 6,
          fontSize: 'var(--text-sm)', fontWeight: 500,
          cursor: downloading ? 'not-allowed' : 'pointer',
          border: 'none',
          background: downloading ? 'var(--bg-tertiary)' : 'var(--primary)',
          color: downloading ? 'var(--text-muted)' : '#fff',
          opacity: downloading ? 0.7 : 1,
          transition: 'all 0.2s ease',
        }}
      >
        <DownloadOutlined />
        {downloading ? '下载中...' : '下载'}
      </button>
      {error && <span style={{ fontSize: 'var(--text-xs)', color: '#e53e3e' }}>{error}</span>}
    </div>
  )
}

/** 渲染 Markdown 内容 + PPT 下载卡片 */
function MarkdownWithDownloads({ content }: { content: string }) {
  const { cleanContent, files } = parsePPTFileMarkers(content)
  return (
    <>
      <div dangerouslySetInnerHTML={{ __html: renderMarkdown(cleanContent) }} />
      {files.map((f, i) => <PPTDownloadCard key={i} file={f} />)}
    </>
  )
}


// ── 反馈详情面板 ──────────────────────────────────────────────

const LIKE_OPTIONS = ['内容准确', '易于理解', '内容完善']
const DISLIKE_OPTIONS = ['有害/不安全', '信息虚假', '没有帮助', '信息不全', '隐私相关']

interface FeedbackDetailPanelProps {
  type: 'like' | 'dislike'
  onSubmit: (detail: { reasons: string[]; comment?: string }) => void
  onClose: () => void
}

function FeedbackDetailPanel({ type, onSubmit, onClose }: FeedbackDetailPanelProps) {
  const options = type === 'like' ? LIKE_OPTIONS : DISLIKE_OPTIONS
  const [selected, setSelected] = useState<string[]>([])
  const [otherText, setOtherText] = useState('')
  const [showOther, setShowOther] = useState(false)
  const [thankYou, setThankYou] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (panelRef.current) {
      panelRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [showOther])

  const toggleOption = (opt: string) => {
    setSelected(prev => prev.includes(opt) ? prev.filter(o => o !== opt) : [...prev, opt])
  }

  const handleSubmit = () => {
    const reasons = [...selected]
    const comment = otherText.trim()
    if (comment) reasons.push('其他')
    if (reasons.length === 0 && !comment) {
      onClose()
      return
    }
    onSubmit({ reasons, comment: comment || undefined })
    setThankYou(true)
    setTimeout(onClose, 2000)
  }

  if (thankYou) {
    return (
      <div
        ref={panelRef}
        style={{
          position: 'absolute', top: '100%', left: 0, marginTop: 8,
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 12, padding: '18px 24px', minWidth: 280,
          boxShadow: '0 4px 20px rgba(0,0,0,0.12)', zIndex: 50,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--primary)', fontWeight: 500, textAlign: 'center' }}>
          非常感谢！你的反馈有助于改进AI小助手。
        </div>
      </div>
    )
  }

  return (
    <div
      ref={panelRef}
      style={{
        position: 'absolute', top: '100%', left: 0, marginTop: 8,
        background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 12, padding: '20px 24px', minWidth: 340, maxWidth: 420,
        boxShadow: '0 4px 20px rgba(0,0,0,0.12)', zIndex: 50,
      }}
      onClick={(e) => e.stopPropagation()}
    >
      {/* 右上角关闭按钮 */}
      <button
        onClick={onClose}
        style={{
          position: 'absolute', top: 10, right: 10,
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-muted)', fontSize: 14, padding: 4,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          borderRadius: 4,
        }}
      >
        <CloseOutlined />
      </button>

      {/* 提问文案 */}
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text)', fontWeight: 500, marginBottom: 14, paddingRight: 24 }}>
        {type === 'like' ? '你觉得什么让你满意？' : '你觉得什么让你不满意？'}
      </div>

      {/* 选项标签 */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: showOther ? 10 : 16 }}>
        {options.map(opt => (
          <button
            key={opt}
            onClick={() => toggleOption(opt)}
            style={{
              padding: '7px 16px', borderRadius: 20,
              fontSize: 'var(--text-xs)', cursor: 'pointer',
              border: `1px solid ${selected.includes(opt) ? 'var(--primary)' : 'var(--border)'}`,
              background: selected.includes(opt) ? 'var(--primary-light)' : 'transparent',
              color: selected.includes(opt) ? 'var(--primary)' : 'var(--text-secondary)',
              fontWeight: selected.includes(opt) ? 500 : 400,
              transition: 'all 0.15s ease',
            }}
          >
            {opt}
          </button>
        ))}
        <button
          onClick={() => setShowOther(prev => !prev)}
          style={{
            padding: '7px 16px', borderRadius: 20,
            fontSize: 'var(--text-xs)', cursor: 'pointer',
            border: `1px solid ${showOther ? 'var(--primary)' : 'var(--border)'}`,
            background: showOther ? 'var(--primary-light)' : 'transparent',
            color: showOther ? 'var(--primary)' : 'var(--text-secondary)',
            fontWeight: showOther ? 500 : 400,
            transition: 'all 0.15s ease',
          }}
        >
          其他
        </button>
      </div>

      {/* 其他输入框 */}
      {showOther && (
        <input
          value={otherText}
          onChange={(e) => setOtherText(e.target.value)}
          placeholder="请输入具体原因..."
          style={{
            width: '100%', padding: '8px 12px', borderRadius: 8,
            fontSize: 'var(--text-sm)', border: '1px solid var(--border)',
            background: 'var(--bg)', color: 'var(--text)', outline: 'none',
            marginBottom: 16, boxSizing: 'border-box',
          }}
          autoFocus
        />
      )}

      {/* 提交按钮 */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={handleSubmit}
          style={{
            padding: '8px 20px', borderRadius: 6,
            fontSize: 'var(--text-sm)', cursor: 'pointer',
            border: 'none', background: 'var(--primary)', color: '#fff',
            fontWeight: 500,
          }}
        >
          提交
        </button>
      </div>
    </div>
  )
}


// ── 操作栏（hover 时淡入）───────────────────────────────────────

function MessageActions({ msg, isLast, onResend }: { msg: Message; isLast: boolean; onResend: (msgId: number, q: string) => void }) {
  const [copied, setCopied] = useState(false)
  const [feedback, setFeedback] = useState<'like' | 'dislike' | null>(msg.feedback)
  const [showDetail, setShowDetail] = useState<'like' | 'dislike' | null>(null)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = msg.content
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  const handleFeedback = async (type: 'like' | 'dislike') => {
    // 再次点击同一个 → 取消反馈
    if (feedback === type) {
      try {
        await chatApi.setFeedback(msg.id, type)
        setFeedback(null)
        setShowDetail(null)
      } catch (e) {
        console.error('反馈失败:', e)
      }
      return
    }
    // 先发送基础反馈
    try {
      await chatApi.setFeedback(msg.id, type)
      setFeedback(type)
      // 显示详情面板
      setShowDetail(type)
    } catch (e) {
      console.error('反馈失败:', e)
    }
  }

  const handleDetailSubmit = async (detail: { reasons: string[]; comment?: string }) => {
    try {
      await chatApi.setFeedback(msg.id, feedback as 'like' | 'dislike', detail)
    } catch (e) {
      console.error('反馈详情提交失败:', e)
    }
  }

  return (
    <div className="message-actions" style={{ position: 'relative' }}>
      {/* 反馈详情面板 */}
      {showDetail && (
        <FeedbackDetailPanel
          type={showDetail}
          onSubmit={handleDetailSubmit}
          onClose={() => setShowDetail(null)}
        />
      )}
      <button onClick={handleCopy} title="复制">
        {copied ? <CheckOutlined style={{ fontSize: 16 }} /> : <CopyOutlined style={{ fontSize: 16 }} />}
        {copied && <span style={{ fontSize: 12 }}>已复制</span>}
      </button>
      <button onClick={() => handleFeedback('like')} title="答得好">
        {feedback === 'like' ? <LikeFilled style={{ fontSize: 16 }} /> : <LikeOutlined style={{ fontSize: 16 }} />}
      </button>
      <button onClick={() => handleFeedback('dislike')} title="答得不好">
        {feedback === 'dislike' ? <DislikeFilled style={{ fontSize: 16 }} /> : <DislikeOutlined style={{ fontSize: 16 }} />}
      </button>
      {isLast && (
        <button onClick={() => onResend(msg.id, '')} title="重新生成">
          <RedoOutlined style={{ fontSize: 16 }} />
        </button>
      )}
    </div>
  )
}


// ── 流式步骤渲染 ────────────────────────────────────────────────

/** 三点弹跳等待动画 */
function BouncingDots() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '12px 16px' }}>
      <span className="animate-bouncing" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--primary)' }} />
      <span className="animate-bouncing" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--primary)', animationDelay: '0.2s' }} />
      <span className="animate-bouncing" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--primary)', animationDelay: '0.4s' }} />
    </div>
  )
}

/** 流式步骤：将 steps 映射为可折叠卡片 */
function StreamingStepRenderer({ steps }: { steps: StreamingMessage['steps'] }) {
  return (
    <>
      {steps.length === 0 && <BouncingDots />}
      {steps.map((step, i) => {
        if (step.type === 'rewrite') {
          return (
            <CollapsibleCard
              key={i}
              variant="rewrite-card"
              title="查询优化"
              icon={RewriteIcon}
              defaultOpen={true}
              statusDot={step.done ? 'done' : 'running'}
              subtitle={step.done ? '完成' : '优化中...'}
            >
              <div className="rewrite-content">
                {step.content && step.content !== '处理中...' ? (
                  <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>{step.content}</span>
                ) : (
                  <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>正在优化查询...</span>
                )}
              </div>
            </CollapsibleCard>
          )
        }

        if (step.type === 'think') {
          return (
            <CollapsibleCard
              key={i}
              variant="think-card"
              title="思考过程"
              icon={ThinkIcon}
              defaultOpen={true}
            >
              <div className="think-content">
                {step.content.replace(/\n\s*\n/g, '\n')}
              </div>
            </CollapsibleCard>
          )
        }

        if (step.type === 'tool') {
          return (
            <CollapsibleCard
              key={i}
              variant="tool-card"
              title={`调用工具：${step.toolName || '...'}`}
              icon={ToolIcon}
              defaultOpen={true}
              statusDot={step.done ? 'done' : 'running'}
              subtitle={step.done ? '完成' : '执行中...'}
            >
              {step.content && (
                <div className="tool-content">
                  {step.content}
                </div>
              )}
            </CollapsibleCard>
          )
        }

        if (step.type === 'answer') {
          return (
            <div key={i} className="answer-section" style={{ padding: '16px 0 0 0' }}>
              <MarkdownWithDownloads content={step.content} />
            </div>
          )
        }

        return null
      })}
    </>
  )
}


// ── 空状态 ──────────────────────────────────────────────────────

function EmptyState() {
  const user = useAuthStore((s) => s.user)
  const name = user?.username || ''

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      paddingTop: 80,
      userSelect: 'none', color: 'var(--text-secondary)',
    }}>
      <div style={{
        width: 56, height: 56, borderRadius: 16, display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 24, fontWeight: 700, marginBottom: 16,
        background: 'linear-gradient(135deg, var(--primary), var(--primary-dark))',
        color: '#fff', boxShadow: '0 4px 16px rgba(0, 123, 255, 0.2)',
      }}>
        AI
      </div>
      <div style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: 4 }}>
        {name}{name ? '，你好！' : '你好！'}
      </div>
      <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-muted)' }}>需要我为你做些什么？</div>
    </div>
  )
}


// ── 历史消息步骤渲染 ──────────────────────────────────────────

/** 将 metadata_json.entries 按原始顺序解析为可折叠卡片 + 回答。
 *  核心逻辑："调用工具"之后的连续 progress 事件归入同一张工具卡片，
 *  直到遇到下一个非 progress 事件（think / 调用工具 / 结束）为止。
 */
function HistoryStepRenderer({
  entries,
  content,
}: {
  entries: Array<Record<string, unknown>>
  content: string
}) {
  // 预处理：遍历 entries，把工具调用和它的中间 progress 合并
  type ParsedEntry =
    | { kind: 'think'; content: string }
    | { kind: 'rewrite'; content: string }
    | { kind: 'tool'; toolName: string; details: string[] }

  const parsed: ParsedEntry[] = []
  let currentTool: { toolName: string; details: string[] } | null = null

  for (const e of entries) {
    const evt = String(e.event || e.type || '')
    const msg = String(e.message || '')

    if (evt === 'think') {
      currentTool = null
      const text = String(e.content || '').replace(/\n\s*\n/g, '\n').trim()
      if (text) parsed.push({ kind: 'think', content: text })
      continue
    }

    if (evt !== 'progress') continue

    // "调用工具" → 开始新的工具分组
    if (msg.includes('调用工具')) {
      const toolName = msg.replace(/^调用工具[：:]\s*/, '').trim() || msg
      currentTool = { toolName, details: [] }
      parsed.push({ kind: 'tool', toolName, details: currentTool.details })
      continue
    }

    // "查询已优化" → 独立的 rewrite 卡片
    if (msg.includes('查询已优化')) {
      currentTool = null
      const optimized = msg.replace(/.*查询已优化[：:]\s*/, '').trim()
      parsed.push({ kind: 'rewrite', content: optimized || '查询已优化' })
      continue
    }

    // 跳过"正在优化..."
    if (msg.includes('优化')) {
      currentTool = null
      continue
    }

    // 其它 progress 消息：归入当前工具卡片，或跳过
    if (currentTool && msg.trim()) {
      currentTool.details.push(msg)
    }
  }

  return (
    <>
      {parsed.map((item, i) => {
        if (item.kind === 'think') {
          return (
            <CollapsibleCard
              key={i}
              variant="think-card"
              title="思考过程"
              icon={ThinkIcon}
              defaultOpen={true}
            >
              <div className="think-content">{item.content}</div>
            </CollapsibleCard>
          )
        }

        if (item.kind === 'rewrite') {
          return (
            <CollapsibleCard
              key={i}
              variant="rewrite-card"
              title="查询优化"
              icon={RewriteIcon}
              defaultOpen={true}
              statusDot="done"
              subtitle="完成"
            >
              <div className="rewrite-content">
                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>{item.content}</span>
              </div>
            </CollapsibleCard>
          )
        }

        if (item.kind === 'tool') {
          const hasDetails = item.details.length > 0
          return (
            <CollapsibleCard
              key={i}
              variant="tool-card"
              title={`调用工具：${item.toolName}`}
              icon={ToolIcon}
              defaultOpen={hasDetails}
              statusDot="done"
              subtitle="完成"
            >
              {hasDetails ? (
                <div className="tool-content">
                  {item.details.join('\n')}
                </div>
              ) : (
                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>工具已完成调用</span>
              )}
            </CollapsibleCard>
          )
        }

        return null
      })}

      {/* 回答内容 */}
      {content && (
        <div className="answer-section" style={{ padding: '8px 0 0 0' }}>
          <MarkdownWithDownloads content={content} />
        </div>
      )}
    </>
  )
}


// ── 用户消息操作栏（复制 + 编辑）─────────────────────────────────

function UserMessageActions({ msgId, content, canEdit, onEdit }: {
  msgId: number
  content: string
  canEdit: boolean
  onEdit: () => void
}) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = content
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  return (
    <div className="message-actions" style={{ marginTop: 4 }}>
      <button onClick={handleCopy} title="复制">
        {copied ? <CheckOutlined style={{ fontSize: 14 }} /> : <CopyOutlined style={{ fontSize: 14 }} />}
        {copied && <span style={{ fontSize: 11 }}>已复制</span>}
      </button>
      {canEdit && (
        <button onClick={onEdit} title="编辑并重新发送">
          <EditOutlined style={{ fontSize: 14 }} />
        </button>
      )}
    </div>
  )
}


// ── 主组件 ──────────────────────────────────────────────────────

const ChatMessages = forwardRef<ChatMessagesHandle, Props>(function ChatMessages({
  messages,
  streamingMessage,
  onSuggestClick,
  onResend,
  onScrollAway,
}, ref) {
  const containerRef = useRef<HTMLDivElement>(null)

  // 暴露 scrollToBottom 给父组件
  useImperativeHandle(ref, () => ({
    scrollToBottom: () => {
      if (containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight
      }
    },
  }), [])

  // 自动滚动到底部
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [messages, streamingMessage])

  // 监听滚动位置，通知父组件是否离开了底部
  useEffect(() => {
    const el = containerRef.current
    if (!el || !onScrollAway) return

    const threshold = 80
    const handler = () => {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
      onScrollAway(!atBottom)
    }
    el.addEventListener('scroll', handler, { passive: true })
    return () => el.removeEventListener('scroll', handler)
  }, [onScrollAway])

  // 编辑状态
  const [editingUserMsgId, setEditingUserMsgId] = useState<number | null>(null)
  const [editText, setEditText] = useState('')

  // 找到最后一条 user 消息及其前一条 user 消息的 id
  const lastUserIdx = messages.findLastIndex((m) => m.role === 'user')
  const isLastMessage = (idx: number) => idx === messages.length - 1

  // 空状态
  if (messages.length === 0 && !streamingMessage) {
    return (
      <div ref={containerRef} style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
        <EmptyState />
      </div>
    )
  }

  return (
    <div ref={containerRef} style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {messages.map((msg, idx) =>
          msg.role === 'user' ? (
            /* ── 用户消息 ── */
            <div key={msg.id} className="animate-fade-in-up group" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
              {editingUserMsgId === msg.id ? (
                /* 编辑模式 */
                <div style={{
                  maxWidth: '70%', width: '100%',
                  padding: '12px 18px',
                  borderRadius: 18, borderBottomRightRadius: 4,
                  background: 'var(--surface)',
                  border: '2px solid var(--primary)',
                  boxShadow: '0 2px 10px rgba(0, 123, 255, 0.15)',
                }}>
                  <textarea
                    autoFocus
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        const trimmed = editText.trim()
                        if (trimmed && msg.id > 0) {
                          setEditingUserMsgId(null)
                          onResend(msg.id, trimmed)
                        }
                      }
                      if (e.key === 'Escape') setEditingUserMsgId(null)
                    }}
                    style={{
                      width: '100%', minHeight: 60, resize: 'vertical',
                      padding: 0, border: 'none', outline: 'none',
                      fontSize: 'var(--text-base)', lineHeight: 1.7,
                      background: 'transparent', color: 'var(--text)',
                      fontFamily: 'inherit',
                    }}
                  />
                  <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
                    <button
                      onClick={() => setEditingUserMsgId(null)}
                      style={{
                        padding: '4px 12px', borderRadius: 6, fontSize: 'var(--text-xs)',
                        cursor: 'pointer', border: '1px solid var(--border)',
                        background: 'transparent', color: 'var(--text-muted)',
                      }}
                    >取消</button>
                    <button
                      onClick={() => {
                        const trimmed = editText.trim()
                        if (trimmed && msg.id > 0) {
                          setEditingUserMsgId(null)
                          onResend(msg.id, trimmed)
                        }
                      }}
                      style={{
                        padding: '4px 12px', borderRadius: 6, fontSize: 'var(--text-xs)',
                        cursor: 'pointer', border: 'none',
                        background: 'var(--primary)', color: '#fff', fontWeight: 500,
                      }}
                    >发送</button>
                  </div>
                </div>
              ) : (
                /* 正常显示 */
                <>
                  <div style={{
                    padding: '12px 18px',
                    borderRadius: 18,
                    borderBottomRightRadius: 4,
                    maxWidth: '70%',
                    fontSize: 'var(--text-base)',
                    lineHeight: 1.7,
                    whiteSpace: 'pre-wrap' as const,
                    background: 'linear-gradient(135deg, var(--primary), var(--primary-dark))',
                    color: '#fff',
                    boxShadow: '0 2px 10px rgba(0, 123, 255, 0.2)',
                    wordBreak: 'break-word',
                  }}>
                    {msg.content}
                    {msg.attachments && msg.attachments.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                        {msg.attachments.map((att) => (
                          <span
                            key={att.id}
                            style={{
                              display: 'inline-flex', alignItems: 'center',
                              padding: '2px 8px', borderRadius: 4,
                              fontSize: 'var(--text-xs)',
                              background: 'rgba(255,255,255,0.15)',
                            }}
                          >
                            {att.file_name}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {/* 用户消息操作栏（hover 显示） */}
                  {msg.id > 0 && (
                    <UserMessageActions
                      msgId={msg.id}
                      content={msg.content}
                      canEdit={idx === lastUserIdx}
                      onEdit={() => {
                        setEditingUserMsgId(msg.id)
                        setEditText(msg.content)
                      }}
                    />
                  )}
                </>
              )}
            </div>
          ) : (
            /* ── Assistant 消息（历史）── */
            <div key={msg.id} className="animate-fade-in-up group" style={{ maxWidth: '85%' }}>
              <div style={{
                padding: '12px 0',
              }}>
                {(() => {
                  const entries = getEntries(msg.metadata_json)
                  if (entries && entries.length > 0) {
                    return (
                      <HistoryStepRenderer entries={entries} content={msg.content} />
                    )
                  }
                  // 无过程数据时直接显示回答
                  return (
                    <div className="answer-section">
                      <MarkdownWithDownloads content={msg.content} />
                    </div>
                  )
                })()}
              </div>

              {/* 猜你想问 */}
              {(() => {
                const entries = getEntries(msg.metadata_json)
                if (!entries) return null
                const questions = getMaybeQuestions(entries)
                if (questions.length === 0) return null
                return <MaybeQuestions questions={questions} onClick={onSuggestClick} />
              })()}

              {/* 操作栏：重新生成仅最后一条消息 */}
              {msg.id > 0 && (
                <MessageActions
                  msg={msg}
                  isLast={isLastMessage(idx)}
                  onResend={(assistantMsgId) => {
                    // 重新生成：找到此 AI 回复前面的用户消息，从用户消息开始截断
                    for (let i = idx - 1; i >= 0; i--) {
                      if (messages[i].role === 'user') {
                        onResend(messages[i].id, messages[i].content)
                        return
                      }
                    }
                  }}
                />
              )}
            </div>
          ),
        )}

        {/* ── 正在生成的流式消息 ── */}
        {streamingMessage && (
          <div className="animate-fade-in-up" style={{ maxWidth: '85%' }}>
            <div style={{ padding: '4px 0' }}>
              <StreamingStepRenderer steps={streamingMessage.steps} />
            </div>

            {/* 猜你想问 */}
            {streamingMessage.suggestQuestions.length > 0 && (
              <div style={{ padding: '0 0 8px 0' }}>
                <MaybeQuestions questions={streamingMessage.suggestQuestions} onClick={onSuggestClick} />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
})

export default ChatMessages
