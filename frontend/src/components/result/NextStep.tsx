import { Check, ClipboardCheck, ExternalLink, LoaderCircle } from 'lucide-react'
import { useId, useState } from 'react'

import { newApplicationId, registerApplication } from '../../features/hunter/applications'
import { guessTitle, offerHost, type OfferSource } from '../../lib/offerSource'

interface NextStepProps {
  offer: OfferSource | null
  offerText: string
  /** El CV tal y como se descarga, con lo que haya añadido el usuario. */
  markdown: string
  scoreBefore: number
  scoreAfter: number
  /** Con el Buscador activado se puede apuntar la candidatura. */
  tracking: boolean
}

interface Saved {
  result: 'saved' | 'queued'
  score: number
}

/**
 * Después de optimizar: volver a la oferta original para inscribirse y apuntar la candidatura con la
 * compatibilidad del CV que se envía (SPEC del hunter §18.5).
 */
export function NextStep({ offer, offerText, markdown, scoreBefore, scoreAfter, tracking }: NextStepProps) {
  const [saved, setSaved] = useState<Saved | null>(null)
  const [asking, setAsking] = useState(false)
  const [company, setCompany] = useState(offer?.company ?? '')
  const [title, setTitle] = useState(offer?.title || guessTitle(offerText))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const id = useId()
  const url = offer?.url

  if (!url && !tracking) return null

  const save = async () => {
    if (!company.trim() || !title.trim()) {
      setAsking(true)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const result = await registerApplication({
        id: newApplicationId(),
        source: 'optimizer',
        job_id: offer?.jobId ?? null,
        company: company.trim(),
        title: title.trim(),
        url: url ?? null,
        location: offer?.location ?? '',
        ats_score_before: scoreBefore,
        ats_score_after: scoreAfter,
        judge_score: offer?.matchScore ?? null,
        offer_text: offerText,
        cv_markdown: markdown,
      })
      setSaved({ result, score: scoreAfter })
      setAsking(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se ha podido guardar la candidatura.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby={`${id}-title`} className="card mb-6 p-4 sm:p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 id={`${id}-title`} className="text-sm font-semibold">
            Siguiente paso
          </h3>
          {saved ? (
            <p className="mt-1 flex items-start gap-1.5 text-sm text-slate-600 dark:text-slate-300" role="status">
              <Check className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />
              <span>
                {saved.result === 'saved' ? (
                  <>
                    Apuntada en tus candidaturas con un{' '}
                    <strong className="font-semibold tabular-nums">{saved.score} %</strong> de compatibilidad.{' '}
                    <a
                      href="#/buscar/candidaturas"
                      className="focus-ring rounded font-medium text-cobalt-700 underline-offset-2 hover:underline dark:text-cobalt-300"
                    >
                      Ver mis candidaturas
                    </a>
                  </>
                ) : (
                  <>
                    Apuntada en este navegador con un{' '}
                    <strong className="font-semibold tabular-nums">{saved.score} %</strong>. El Buscador está apagado:
                    pasará a tus candidaturas en cuanto lo abras.
                  </>
                )}
              </span>
            </p>
          ) : (
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {tracking
                ? 'Envía este CV en la oferta y apúntalo aquí: así sabrás con qué compatibilidad te presentaste a cada una.'
                : 'Descarga el CV y envíalo en la oferta original.'}
            </p>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          {url && (
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="focus-ring inline-flex h-10 items-center gap-2 rounded-lg bg-cobalt-600 px-4 text-sm font-semibold text-white transition hover:bg-cobalt-700"
            >
              Abrir la oferta en {offerHost(url)}
              <ExternalLink className="size-4" aria-hidden />
            </a>
          )}
          {tracking && !saved && !asking && (
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy}
              className="focus-ring inline-flex h-10 items-center gap-2 rounded-lg px-4 text-sm font-semibold text-ink ring-1 ring-slate-300 transition hover:bg-slate-50 disabled:opacity-60 dark:text-slate-100 dark:ring-slate-700 dark:hover:bg-slate-800"
            >
              {busy ? (
                <LoaderCircle className="size-4 animate-spin" aria-hidden />
              ) : (
                <ClipboardCheck className="size-4" aria-hidden />
              )}
              Me he inscrito con este CV
              <span className="tabular-nums text-slate-500 dark:text-slate-400">· {scoreAfter} %</span>
            </button>
          )}
        </div>
      </div>

      {asking && !saved && (
        <form
          className="mt-4 grid gap-3 border-t border-slate-200 pt-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end dark:border-slate-800"
          onSubmit={(e) => {
            e.preventDefault()
            void save()
          }}
        >
          <div>
            <label htmlFor={`${id}-company`} className="text-sm font-medium">
              Empresa
            </label>
            <input
              id={`${id}-company`}
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              required
              autoFocus
              maxLength={200}
              className="focus-ring mt-1 h-10 w-full rounded-md border border-slate-300 bg-paper px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div>
            <label htmlFor={`${id}-title-input`} className="text-sm font-medium">
              Puesto
            </label>
            <input
              id={`${id}-title-input`}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              maxLength={300}
              className="focus-ring mt-1 h-10 w-full rounded-md border border-slate-300 bg-paper px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
          </div>
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={busy}
              className="focus-ring inline-flex h-10 items-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white transition hover:bg-ink/90 disabled:opacity-60 dark:bg-white dark:text-slate-900"
            >
              {busy && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
              Guardar candidatura
            </button>
            <button
              type="button"
              onClick={() => setAsking(false)}
              className="focus-ring h-10 rounded-lg px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {error && (
        <p className="mt-3 text-sm text-rose-700 dark:text-rose-400" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
