import { useState, useRef, useEffect } from 'react'
import { DownOutlined } from '@ant-design/icons'

interface Option {
  value: string
  label: string
}

interface FilterSelectProps {
  value: string
  onChange: (value: string) => void
  options: Option[]
  placeholder?: string
  small?: boolean
  className?: string
}

export default function FilterSelect({
  value,
  onChange,
  options,
  placeholder,
  small,
  className,
}: FilterSelectProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const selected = options.find((o) => o.value === value)
  const label = selected ? selected.label : (placeholder || '请选择')

  return (
    <div ref={ref} className={`relative ${className || 'inline-flex'}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center justify-between gap-1.5 rounded-lg border cursor-pointer transition-colors duration-150 w-full"
        style={{
          padding: small ? '4px 10px' : '7px 12px',
          fontSize: small ? 12 : 14,
          borderColor: open ? 'var(--primary)' : 'var(--border)',
          background: 'var(--surface)',
          color: selected ? 'var(--text)' : 'var(--text-muted)',
        }}
      >
        <span className="truncate">{label}</span>
        <DownOutlined
          style={{
            fontSize: 10,
            color: 'var(--text-muted)',
            transition: 'transform 0.15s',
            transform: open ? 'rotate(180deg)' : undefined,
            flexShrink: 0,
          }}
        />
      </button>
      {open && (
        <div
          className="absolute top-full left-0 mt-1 py-1 rounded-lg overflow-hidden z-50"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            minWidth: '100%',
            boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
          }}
        >
          {options.map((opt) => {
            const active = opt.value === value
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => {
                  onChange(opt.value)
                  setOpen(false)
                }}
                className="w-full text-left px-3 py-2 text-sm cursor-pointer transition-colors"
                style={{
                  color: active ? 'var(--primary)' : 'var(--text-secondary)',
                  background: active ? 'var(--primary-light)' : 'transparent',
                }}
                onMouseEnter={(e) => {
                  if (!active) e.currentTarget.style.background = 'rgba(0,0,0,0.03)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = active
                    ? 'var(--primary-light)'
                    : 'transparent'
                }}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
