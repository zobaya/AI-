import { useState, useRef, useCallback } from 'react'
import { chatApi } from '@/api/chat'
import { SendOutlined, StopOutlined, PaperClipOutlined, ToolOutlined, LinkOutlined, AudioOutlined } from '@ant-design/icons'

/** 获取浏览器 SpeechRecognition 构造函数 */
const SpeechRecognitionAPI = typeof window !== 'undefined'
  ? (window.SpeechRecognition || window.webkitSpeechRecognition)
  : undefined

interface Props {
  onSend: (query: string, filePaths?: string[], fileNames?: string[], tools?: string[] | null) => void
  onStop: () => void
  isGenerating: boolean
  isWelcome?: boolean
}

const TOOLS = [
  { key: 'es_search', label: '检索', desc: '知识库' },
  { key: 'manual_search', label: '手册', desc: '电热合金' },
  { key: 'calculate', label: '计算', desc: '合金参数' },
  { key: 'file_parse', label: '文件', desc: 'PDF/Word' },
  { key: 'ppt_generate', label: 'PPT', desc: '生成演示文稿' },
]

export default function ChatInput({ onSend, onStop, isGenerating, isWelcome }: Props) {
  const [input, setInput] = useState('')
  const [uploadedFiles, setUploadedFiles] = useState<Array<{ path: string; name: string }>>([])
  const [showTools, setShowTools] = useState(false)
  const [enabledTools, setEnabledTools] = useState<Record<string, boolean>>(
    Object.fromEntries(TOOLS.map((t) => [t.key, true])),
  )
  const [uploading, setUploading] = useState(false)
  const [focused, setFocused] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const recognitionRef = useRef<SpeechRecognition | null>(null)

  const autoResize = () => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 120) + 'px'
    }
  }

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    try {
      const { data } = await chatApi.uploadFiles(Array.from(files))
      setUploadedFiles((prev) => [
        ...prev,
        ...data.paths.map((p, i) => ({ path: p, name: data.names[i] })),
      ])
    } catch (err) {
      console.error('Upload failed:', err)
    }
    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)
    const files = e.dataTransfer.files
    if (files.length) handleUpload(files)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    // 只在真正离开容器时取消
    if (e.currentTarget.contains(e.relatedTarget as Node)) return
    setDragOver(false)
  }

  const handleSend = () => {
    const query = input.trim()
    if (!query || isGenerating) return
    setInput('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    const filePaths = uploadedFiles.map((f) => f.path)
    const fileNames = uploadedFiles.map((f) => f.name)
    const tools = Object.entries(enabledTools)
      .filter(([, v]) => v)
      .map(([k]) => k)

    setUploadedFiles([])
    onSend(query, filePaths.length ? filePaths : undefined, fileNames.length ? fileNames : undefined, tools)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const toggleTool = (key: string) => {
    setEnabledTools((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  /** 开始语音识别 */
  const handleStartRecording = useCallback(() => {
    if (!SpeechRecognitionAPI || isGenerating) return
    const recognition = new SpeechRecognitionAPI()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.maxAlternatives = 1

    let finalTranscript = ''
    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i]
        if (result.isFinal) {
          finalTranscript += result[0].transcript
        } else {
          interim += result[0].transcript
        }
      }
      setInput(finalTranscript + interim)
      // 输入内容变化时自动调整高度
      requestAnimationFrame(() => {
        const el = textareaRef.current
        if (el) {
          el.style.height = 'auto'
          el.style.height = Math.min(el.scrollHeight, 120) + 'px'
        }
      })
    }

    recognition.onerror = () => {
      setIsRecording(false)
      recognitionRef.current = null
    }

    recognition.onend = () => {
      setIsRecording(false)
      recognitionRef.current = null
    }

    recognitionRef.current = recognition
    recognition.start()
    setIsRecording(true)
  }, [isGenerating])

  /** 停止语音识别 */
  const handleStopRecording = useCallback(() => {
    recognitionRef.current?.stop()
    setIsRecording(false)
  }, [])

  return (
    <div className={`px-5 ${isWelcome ? 'py-3' : 'pb-3'} shrink-0 ${isWelcome ? 'max-w-3xl mx-auto w-full' : ''}`}>
      {/* 文件标签 */}
      {uploadedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {uploadedFiles.map((f, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs"
              style={{ background: 'var(--primary-light)', color: 'var(--primary)', border: '1px solid rgba(0, 123, 255, 0.2)' }}
            >
              {f.name}
              <button
                onClick={() => setUploadedFiles((prev) => prev.filter((_, j) => j !== i))}
                className="cursor-pointer opacity-60 hover:opacity-100"
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}

      {/* 输入框 */}
      <div
        className="rounded-2xl p-3 border-2 transition-all duration-200 relative"
        style={{
          background: dragOver ? 'rgba(0,0,0,0.02)' : 'var(--surface)',
          borderColor: dragOver ? 'var(--primary)' : isRecording ? '#ef4444' : focused ? 'var(--primary)' : 'var(--border)',
          borderStyle: dragOver ? 'dashed' : 'solid',
          boxShadow: dragOver ? 'none' : isRecording ? '0 0 0 3px rgba(239, 68, 68, 0.1)' : focused ? '0 0 0 3px rgba(0, 123, 255, 0.1)' : 'var(--glass-shadow)',
        }}
        onDragOver={handleDragOver}
        onDragEnter={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* 拖拽覆盖层 */}
        {dragOver && (
          <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-2xl pointer-events-none"
            style={{ background: 'var(--surface)', color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}
          >
            <LinkOutlined style={{ fontSize: 18 }} />
            <span style={{ fontWeight: 500 }}>将文件拖放到此处</span>
          </div>
        )}
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => {
            setInput(e.target.value)
            autoResize()
          }}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder="输入问题，支持多轮对话..."
          rows={1}
          className="w-full resize-none border-none outline-none leading-relaxed"
          style={{ background: 'transparent', color: dragOver ? 'transparent' : 'var(--text)', fontSize: 'var(--text-base)', minHeight: '44px', maxHeight: '120px' }}
        />

        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2">
            {/* 上传按钮 */}
            <button
              className="w-9 h-9 flex items-center justify-center rounded-full cursor-pointer hover-gray"
              style={{ color: 'var(--text-secondary)' }}
              onClick={() => fileInputRef.current?.click()}
              title="上传文件"
            >
              <PaperClipOutlined style={{ fontSize: 20 }} />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.xlsx,.txt,.md,.pptx"
              className="hidden"
              onChange={(e) => handleUpload(e.target.files)}
            />

            {/* 工具按钮 */}
            <div className="relative">
              <button
                onClick={() => setShowTools(!showTools)}
                className="flex items-center gap-1 px-2 h-9 rounded-lg cursor-pointer hover-gray"
                style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', fontWeight: 500 }}
              >
                <ToolOutlined style={{ fontSize: 20 }} />
                工具
              </button>
              {showTools && (
                <div
                  className="absolute bottom-full left-0 mb-2 p-2 rounded-lg border shadow-lg z-20"
                  style={{ background: 'var(--surface)', borderColor: 'var(--border)', minWidth: 200 }}
                >
                  {TOOLS.map((t) => (
                    <label
                      key={t.key}
                      className="flex items-center gap-2 px-3 py-2 rounded cursor-pointer text-sm hover:opacity-80"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      <input
                        type="checkbox"
                        checked={enabledTools[t.key]}
                        onChange={() => toggleTool(t.key)}
                        className="accent-blue-500"
                      />
                      <span className="font-medium">{t.label}</span>
                      <span className="ml-auto text-xs" style={{ color: 'var(--text-muted)' }}>
                        {t.desc}
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* 发送/停止/话筒按钮 */}
          {isGenerating ? (
            <button
              onClick={onStop}
              className="w-9 h-9 flex items-center justify-center rounded-full cursor-pointer transition-transform duration-150 hover:scale-95"
              style={{ background: '#ef4444', color: '#fff' }}
              title="停止生成"
            >
              <StopOutlined />
            </button>
          ) : isRecording ? (
            <button
              onClick={handleStopRecording}
              className="w-9 h-9 flex items-center justify-center rounded-full cursor-pointer transition-transform duration-150 hover:scale-95 recording-pulse"
              style={{ background: '#ef4444', color: '#fff' }}
              title="停止录音"
            >
              <StopOutlined style={{ fontSize: 16 }} />
            </button>
          ) : input.trim() ? (
            <button
              onClick={handleSend}
              className="w-9 h-9 flex items-center justify-center rounded-full cursor-pointer transition-all duration-200 hover:scale-95"
              style={{
                background: 'linear-gradient(135deg, var(--primary), var(--primary-dark))',
                color: '#fff',
                boxShadow: '0 2px 8px rgba(0, 123, 255, 0.3)',
              }}
              title="发送"
            >
              <SendOutlined />
            </button>
          ) : SpeechRecognitionAPI ? (
            <button
              onClick={handleStartRecording}
              className="w-9 h-9 flex items-center justify-center rounded-full cursor-pointer hover-gray"
              style={{ color: 'var(--text-secondary)' }}
              title="语音输入"
            >
              <AudioOutlined style={{ fontSize: 18 }} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled
              className="w-9 h-9 flex items-center justify-center rounded-full cursor-pointer disabled:opacity-40"
              style={{ background: 'var(--primary)', color: '#fff' }}
              title="发送"
            >
              <SendOutlined />
            </button>
          )}
        </div>
      </div>

      {/* AI 免责声明 */}
      {!isWelcome && (
        <div className="text-center pt-1.5 pb-1" style={{ fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.02em' }}>
          内容由AI生成
        </div>
      )}
    </div>
  )
}
