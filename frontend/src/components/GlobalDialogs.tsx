import { useState, useEffect, useRef } from 'react'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  InfoCircleOutlined,
  CloseOutlined,
  ExclamationCircleOutlined,
} from '@ant-design/icons'
import { useUIStore } from '@/stores/uiStore'

// ── Toast 图标映射 ────────────────────────────────────────────

const TOAST_ICON = {
  success: <CheckCircleOutlined style={{ color: 'var(--success)', fontSize: 16 }} />,
  error: <CloseCircleOutlined style={{ color: '#ef4444', fontSize: 16 }} />,
  info: <InfoCircleOutlined style={{ color: 'var(--primary)', fontSize: 16 }} />,
}

// ── 主渲染组件 ────────────────────────────────────────────────

export default function GlobalDialogs() {
  const toasts = useUIStore((s) => s.toasts)
  const removeToast = useUIStore((s) => s.removeToast)
  const confirmDialog = useUIStore((s) => s.confirmDialog)
  const dismissConfirm = useUIStore((s) => s.dismissConfirm)
  const promptDialog = useUIStore((s) => s.promptDialog)
  const dismissPrompt = useUIStore((s) => s.dismissPrompt)

  return (
    <>
      {/* Toast 通知 */}
      {toasts.length > 0 && (
        <div
          className="fixed top-4 right-4 z-[100] flex flex-col gap-2"
          style={{ maxWidth: 380 }}
        >
          {toasts.map((t) => (
            <div
              key={t.id}
              className="flex items-start gap-3 px-4 py-3 rounded-lg shadow-lg border"
              style={{
                background: 'var(--surface)',
                borderColor: 'var(--border)',
                animation: 'toast-in 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
              }}
            >
              <span className="shrink-0 mt-0.5">{TOAST_ICON[t.type]}</span>
              <span className="text-sm flex-1" style={{ color: 'var(--text)', lineHeight: 1.5 }}>
                {t.message}
              </span>
              <button
                onClick={() => removeToast(t.id)}
                className="shrink-0 cursor-pointer p-0.5"
                style={{ color: 'var(--text-muted)' }}
              >
                <CloseOutlined style={{ fontSize: 12 }} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 确认弹窗 */}
      {confirmDialog && (
        <div
          className="fixed inset-0 z-[90] flex items-center justify-center"
          style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={(e) => {
            if (e.target === e.currentTarget) dismissConfirm()
          }}
        >
          <div
            className="w-full max-w-sm p-6 rounded-xl shadow-xl"
            style={{ background: 'var(--surface)' }}
          >
            <div className="flex items-center gap-3 mb-3">
              <ExclamationCircleOutlined
                style={{ fontSize: 20, color: confirmDialog.danger ? '#ef4444' : 'var(--primary)' }}
              />
              <h3 className="text-base font-semibold" style={{ color: 'var(--text)' }}>
                {confirmDialog.title}
              </h3>
            </div>
            <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {confirmDialog.message}
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={confirmDialog.onCancel}
                className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                {confirmDialog.cancelText}
              </button>
              <button
                onClick={confirmDialog.onConfirm}
                className="px-4 py-2 rounded-lg text-white text-sm font-medium cursor-pointer"
                style={{
                  background: confirmDialog.danger ? '#ef4444' : 'var(--primary)',
                }}
              >
                {confirmDialog.confirmText}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 输入弹窗 */}
      {promptDialog && <PromptDialogView />}
    </>
  )
}

// ── 输入弹窗（含输入框） ──────────────────────────────────────

function PromptDialogView() {
  const promptDialog = useUIStore((s) => s.promptDialog)
  const dismissPrompt = useUIStore((s) => s.dismissPrompt)
  const [value, setValue] = useState(promptDialog?.defaultValue || '')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
  }, [])

  if (!promptDialog) return null

  const handleSubmit = () => {
    if (promptDialog.required && !value.trim()) return
    promptDialog.onSubmit(value.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSubmit()
    if (e.key === 'Escape') dismissPrompt()
  }

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) dismissPrompt()
      }}
    >
      <div
        className="w-full max-w-sm p-6 rounded-xl shadow-xl"
        style={{ background: 'var(--surface)' }}
      >
        <h3 className="text-base font-semibold mb-2" style={{ color: 'var(--text)' }}>
          {promptDialog.title}
        </h3>
        {promptDialog.message && (
          <p className="text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
            {promptDialog.message}
          </p>
        )}
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={promptDialog.placeholder}
          className="w-full px-3 py-2.5 rounded-lg border text-sm outline-none"
          style={{
            borderColor: 'var(--border)',
            background: 'var(--bg)',
            color: 'var(--text)',
          }}
        />
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={dismissPrompt}
            className="px-4 py-2 rounded-lg border text-sm cursor-pointer"
            style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            className="px-4 py-2 rounded-lg text-white text-sm font-medium cursor-pointer"
            style={{ background: 'var(--primary)' }}
          >
            确认
          </button>
        </div>
      </div>
    </div>
  )
}
