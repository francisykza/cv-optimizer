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
  // Los tres rotuladores de la app (ver .marker en index.css).
  ungrounded: {
    title: 'No aparece en tu CV original',
    className: 'marker marker-amber underline decoration-amber-600 decoration-wavy underline-offset-4',
  },
  added: {
    title: 'Añadido por ti',
    className: 'marker marker-blue',
  },
  change: {
    title: 'Reformulado respecto a tu CV original',
    className: 'marker marker-green',
  },
} as const

/** El Markdown viene de un LLM alimentado con texto del usuario: se trata como no confiable.
 *  No se renderiza HTML embebido (sin rehype-raw) y además se sanitiza. */
export function MarkdownPreview({ markdown, highlightGroups = [] }: MarkdownPreviewProps) {
  return (
    <article
      className="prose prose-slate max-w-none font-serif text-[15.5px] leading-[1.7] text-ink prose-headings:font-semibold prose-headings:text-ink prose-h1:mb-1 prose-h1:text-[1.9rem] prose-h1:tracking-tight prose-h2:mt-8 prose-h2:mb-3 prose-h2:border-b prose-h2:border-slate-300 prose-h2:pb-1.5 prose-h2:text-lg prose-h3:mt-5 prose-h3:mb-1 prose-h3:text-base prose-p:my-2 prose-a:text-cobalt-700 prose-li:my-0.5 prose-li:marker:text-slate-400 prose-strong:text-ink dark:text-slate-200 dark:prose-invert dark:prose-headings:text-white dark:prose-h2:border-slate-700 dark:prose-strong:text-white"
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
