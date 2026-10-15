import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'

import { Clipboard } from '../ui/Clipboard'
import { CopyButton } from './CopyButton'

/** Pitch de candidatura: el texto para la carta de presentación de un portal o un mensaje directo. */
export function PitchPanel({ pitch }: { pitch: string }) {
  return (
    <div className="bg-desk p-3 sm:p-6 dark:bg-slate-950/60">
      <Clipboard className="mx-auto max-w-3xl">
        <div className="sheet px-6 pt-10 pb-7 sm:px-10 sm:pt-12 sm:pb-9">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <p className="max-w-[46ch] text-sm leading-relaxed text-slate-600">
              Pégalo en el campo de carta de presentación de InfoJobs o LinkedIn, o en un mensaje a quien recluta. Usa
              solo datos de tu CV.
            </p>
            <CopyButton text={pitch} label="Copiar pitch" />
          </div>
          <article className="prose prose-slate mt-6 max-w-none border-t border-slate-200 pt-6 text-ink prose-p:leading-relaxed prose-li:my-1 prose-li:marker:text-slate-400">
            <ReactMarkdown rehypePlugins={[rehypeSanitize]}>{pitch}</ReactMarkdown>
          </article>
        </div>
      </Clipboard>
    </div>
  )
}
