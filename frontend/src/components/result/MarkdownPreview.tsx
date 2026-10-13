import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

import { type HighlightGroup, rehypeHighlightTerms } from '../../lib/rehypeHighlightTerms'

interface MarkdownPreviewProps {
  markdown: string
  /** Resaltados de la vista previa: datos no respaldados (ámbar), habilidades añadidas por el
   *  usuario (azul) y reformulaciones (verde). */
  highlightGroups?: HighlightGroup[]
}

const MARK_STYLES = {
  ungrounded: {
    title: 'No aparece en tu CV original',
    className:
      'rounded bg-amber-200/80 px-0.5 text-inherit underline decoration-amber-500 decoration-wavy underline-offset-4 dark:bg-amber-400/25 dark:text-amber-100',
  },
  added: {
    title: 'Añadido por ti',
    className: 'rounded bg-sky-100 px-0.5 text-inherit ring-1 ring-sky-300 dark:bg-sky-500/20 dark:text-sky-100 dark:ring-sky-500/40',
  },
  change: {
    title: 'Reformulado respecto a tu CV original',
    className: 'rounded bg-emerald-100 px-0.5 text-inherit dark:bg-emerald-500/20 dark:text-emerald-100',
  },
} as const

/** El Markdown viene de un LLM alimentado con texto del usuario: se trata como no confiable.
 *  No se renderiza HTML embebido (sin rehype-raw) y además se sanitiza. */
export function MarkdownPreview({ markdown, highlightGroups = [] }: MarkdownPreviewProps) {
  return (
    <article
      className="prose prose-slate max-w-none prose-headings:tracking-tight prose-h1:mb-2 prose-h1:text-3xl prose-h2:mt-8 prose-h2:border-b prose-h2:border-slate-200 prose-h2:pb-2 prose-h2:text-sm prose-h2:font-semibold prose-h2:uppercase prose-h2:tracking-wider prose-h2:text-indigo-700 prose-h3:mb-1 prose-h3:text-base prose-p:leading-relaxed prose-a:text-indigo-600 prose-li:my-0.5 prose-li:marker:text-indigo-400 prose-strong:text-slate-900 dark:prose-invert dark:prose-h2:border-slate-700 dark:prose-h2:text-indigo-300 dark:prose-strong:text-white"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize, [rehypeHighlightTerms, { groups: highlightGroups }]]}
        components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer nofollow" />,
          mark: ({ node: _node, ...props }) => {
            const raw = (props as Record<string, unknown>)['data-kind']
            const kind: keyof typeof MARK_STYLES = raw === 'change' || raw === 'added' ? raw : 'ungrounded'
            return <mark {...props} {...MARK_STYLES[kind]} className={`scroll-mt-28 ${MARK_STYLES[kind].className}`} />
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  )
}
