import { create } from 'zustand'

// ── Toast 通知 ────────────────────────────────────────────────

export interface Toast {
  id: number
  message: string
  type: 'success' | 'error' | 'info'
}

// ── 确认弹窗 ──────────────────────────────────────────────────

export interface ConfirmOptions {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

interface ConfirmDialog extends ConfirmOptions {
  onConfirm: () => void
  onCancel: () => void
}

// ── 输入弹窗 ──────────────────────────────────────────────────

export interface PromptOptions {
  title: string
  message?: string
  placeholder?: string
  defaultValue?: string
  required?: boolean
}

interface PromptDialog extends PromptOptions {
  onSubmit: (value: string) => void
  onCancel: () => void
}

// ── Store ─────────────────────────────────────────────────────

interface UIState {
  toasts: Toast[]
  confirmDialog: ConfirmDialog | null
  promptDialog: PromptDialog | null

  toast: (message: string, type?: Toast['type']) => void
  removeToast: (id: number) => void

  confirm: (options: ConfirmOptions) => Promise<boolean>
  dismissConfirm: () => void

  prompt: (options: PromptOptions) => Promise<string | null>
  dismissPrompt: () => void
}

let _toastId = 0

export const useUIStore = create<UIState>((set) => ({
  toasts: [],
  confirmDialog: null,
  promptDialog: null,

  toast: (message, type = 'info') => {
    const id = ++_toastId
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }))
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 3000)
  },

  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  confirm: (options) =>
    new Promise<boolean>((resolve) => {
      set({
        confirmDialog: {
          ...options,
          confirmText: options.confirmText || '确认',
          cancelText: options.cancelText || '取消',
          onConfirm: () => {
            set({ confirmDialog: null })
            resolve(true)
          },
          onCancel: () => {
            set({ confirmDialog: null })
            resolve(false)
          },
        },
      })
    }),

  dismissConfirm: () => set({ confirmDialog: null }),

  prompt: (options) =>
    new Promise<string | null>((resolve) => {
      set({
        promptDialog: {
          ...options,
          onSubmit: (value: string) => {
            set({ promptDialog: null })
            resolve(value)
          },
          onCancel: () => {
            set({ promptDialog: null })
            resolve(null)
          },
        },
      })
    }),

  dismissPrompt: () => set({ promptDialog: null }),
}))
