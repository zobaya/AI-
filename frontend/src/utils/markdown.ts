import { marked } from 'marked'
import katex from 'katex'
import { useAuthStore } from '@/stores/authStore'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// 配置 marked
marked.setOptions({
  breaks: false,
  gfm: true,
})

// KaTeX 数学公式渲染
function renderKatex(latex: string, displayMode: boolean): string {
  try {
    return katex.renderToString(latex, { displayMode, throwOnError: false })
  } catch {
    return `<code>${escapeHtml(latex)}</code>`
  }
}

// 块级数学公式扩展（$$...$$）
marked.use({
  extensions: [
    {
      name: 'blockMath',
      level: 'block',
      start(src: string) {
        return src.indexOf('$$')
      },
      tokenizer(src: string) {
        const match = src.match(/^\$\$([\s\S]+?)\$\$/)
        if (match) {
          return { type: 'blockMath', raw: match[0], text: match[1].trim() }
        }
      },
      renderer(token: { text: string }) {
        return `<div class="math-block">${renderKatex(token.text, true)}</div>`
      },
    },
    {
      name: 'inlineMath',
      level: 'inline',
      start(src: string) {
        let idx = src.indexOf('$')
        while (idx !== -1 && idx + 1 < src.length && src[idx + 1] === '$') {
          idx = src.indexOf('$', idx + 2)
        }
        return idx
      },
      tokenizer(src: string) {
        const match = src.match(/^\$([^\$\n]+?)\$/)
        if (match) {
          return { type: 'inlineMath', raw: match[0], text: match[1].trim() }
        }
      },
      renderer(token: { text: string }) {
        return renderKatex(token.text, false)
      },
    },
  ],
})

/**
 * 从 MinIO URL 或路径中提取桶内对象路径。
 * 例如：
 *   "http://localhost:9000/knowledge-base/kb_xxx/..." → "kb_xxx/..."
 *   "knowledge-base/kb_xxx/..."                        → "kb_xxx/..."
 */
function extractMinioObjectPath(href: string): string | null {
  // 完整 MinIO URL: http(s)://.../{bucket}/object...
  const urlMatch = href.match(/^https?:\/\/[^/]+\/knowledge-base\/(.+)$/)
  if (urlMatch) return urlMatch[1]
  // 路径含桶名前缀
  if (href.startsWith('knowledge-base/')) return href.slice('knowledge-base/'.length)
  return null
}

// 自定义 image renderer：将知识库图片路径重写为后端代理 URL
marked.use({
  renderer: {
    image({ href, title, text }: { href: string; title: string | null; text: string }) {
      const objectPath = extractMinioObjectPath(href)
      if (objectPath) {
        const token = useAuthStore.getState().accessToken
        const proxyUrl = `${API_BASE}/api/knowledge/images/${objectPath}${token ? '?token=' + token : ''}`
        const titleAttr = title ? ` title="${title}"` : ''
        return `<img src="${proxyUrl}" alt="${text}"${titleAttr} style="max-width:100%;border-radius:8px;margin:8px 0;" />`
      }
      return false
    },
  },
})

/** 将 Markdown 文本渲染为 HTML */
export function renderMarkdown(text: string): string {
  if (!text) return ''

  const normalized = text
    .replace(/\r\n/g, '\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/\n{2,}/g, '\n\n')
    .replace(/^\n+/, '')
    .replace(/\n+$/, '')

  try {
    return marked.parse(normalized) as string
  } catch {
    return escapeHtml(text)
  }
}

function escapeHtml(t: string): string {
  return t
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
