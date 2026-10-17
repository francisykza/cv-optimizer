import { FileUp, LoaderCircle } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import toast from 'react-hot-toast'

import { loadCv } from '../../lib/cvStore'
import { cn, formatNumber } from '../../lib/format'
import { canAnimate, EASE_HAND } from '../../lib/motion'
import { HunterError, hunterApi } from './hunterClient'
import type { OutdatedVerdicts, Profile } from './types'

const MAX_PDF_BYTES = 5 * 1024 * 1024
// Lo escrito y sin guardar sobrevive a un cambio de pestaña o a recargar (solo en esta pestaña).
const UNSAVED_KEY = 'cvopt:profile-unsaved'

const PLACEHOLDER = `## Resumen
Quién eres y qué puesto buscas, en dos o tres frases.

## Habilidades técnicas
- Lenguajes: Python, SQL
- Herramientas: Git, Docker

## Idiomas
- Español nativo, inglés B2

## Experiencia relevante
- Puesto, empresa y lo que hiciste`

/** El texto como lo guardará la API: sin espacios al final de las líneas ni líneas vacías en los bordes. */
export function cleanProfile(text: string): string {
  return text
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => line.trimEnd())
    .join('\n')
    .replace(/^\n+|\n+$/g, '')
}

/** Caracteres que cuentan para el límite: los que lee el juez (un emoji cuenta como uno). */
export const profileChars = (text: string) => [...cleanProfile(text).trim()].length

const fold = (term: string) => term.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase()

function readUnsaved(sha256: string): string | null {
  try {
    const stored = JSON.parse(sessionStorage.getItem(UNSAVED_KEY) ?? 'null') as { base: string; text: string } | null
    return stored && stored.base === sha256 && typeof stored.text === 'string' ? stored.text : null
  } catch {
    return null
  }
}

function writeUnsaved(sha256: string, text: string | null): void {
  try {
    if (text === null) sessionStorage.removeItem(UNSAVED_KEY)
    else sessionStorage.setItem(UNSAVED_KEY, JSON.stringify({ base: sha256, text }))
  } catch {
    // Almacenamiento bloqueado: lo no guardado vive lo que viva la vista.
  }
}

function outdatedText(o: OutdatedVerdicts): string[] {
  const lines = [
    o.count === 1
      ? `Una oferta de los últimos ${o.days} días tiene la nota de un perfil anterior.`
      : `${o.count} ofertas de los últimos ${o.days} días tienen la nota de un perfil anterior.`,
  ]
  if (o.est_tokens === 0) {
    lines.push('Ponerlas al día no gasta tokens: ya se juzgaron con este perfil.')
    return lines
  }
  const left = o.tokens_left_today === null ? '' : ` (te quedan ${formatNumber(o.tokens_left_today)} hoy)`
  lines.push(
    `Volver a juzgarlas costaría unos ${formatNumber(o.est_tokens)} tokens${left} y unos ${o.est_minutes} minutos. ` +
      'Mientras, cada una conserva su nota.',
  )
  if (o.tokens_left_today !== null && o.est_tokens > o.tokens_left_today) {
    lines.push('Hoy no llega para todas: primero se puntúan las mejor colocadas y el resto conserva su nota.')
  }
  return lines
}

interface ProfileEditorProps {
  token: string
  /** Cambia al terminar una búsqueda o una vuelta del juez: hay que volver a contar las notas viejas. */
  refreshKey: number
  onRejudgeStarted: (runId: string) => void
}

/** Tu perfil: lo que lee la IA antes de puntuar cada oferta, escrito en una hoja del tablero de pinza. */
export function ProfileEditor({ token, refreshKey, onRejudgeStarted }: ProfileEditorProps) {
  const [saved, setSaved] = useState<Profile | null>(null)
  const [text, setText] = useState('')
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [busy, setBusy] = useState<'save' | 'draft' | 'rejudge' | 'conflict' | null>(null)
  const [justSaved, setJustSaved] = useState(false)
  const [offerClosed, setOfferClosed] = useState(false)
  const [rejudging, setRejudging] = useState(false)
  const [draftNotes, setDraftNotes] = useState<{ source: string; warnings: string[] } | null>(null)
  const [rememberedCv, setRememberedCv] = useState<File | null>(null)
  const [newTerms, setNewTerms] = useState<ReadonlySet<string>>(new Set())
  const clipRef = useRef<HTMLSpanElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const seenRefresh = useRef(refreshKey)
  const titleId = useId()
  const editorId = useId()
  const hintId = useId()
  const countId = useId()

  useEffect(() => {
    let cancelled = false
    hunterApi
      .profile(token)
      .then((profile) => {
        if (cancelled) return
        setSaved(profile)
        setText(readUnsaved(profile.sha256) ?? profile.text)
      })
      .catch((err: Error) => {
        if (!cancelled) setLoadError(err.message)
      })
    void loadCv().then((cv) => {
      if (!cancelled) setRememberedCv(cv)
    })
    return () => {
      cancelled = true
    }
  }, [token])

  // Al terminar una búsqueda o una vuelta del juez cambian las notas: se vuelven a contar.
  useEffect(() => {
    if (refreshKey === seenRefresh.current) return
    seenRefresh.current = refreshKey
    let cancelled = false
    hunterApi
      .profile(token)
      .then((fresh) => {
        if (cancelled) return
        setSaved((prev) => (prev && prev.sha256 === fresh.sha256 ? { ...prev, outdated: fresh.outdated } : prev))
        setRejudging(false)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [refreshKey, token])

  const dirty = saved !== null && cleanProfile(text) !== cleanProfile(saved.text)

  useEffect(() => {
    if (saved) writeUnsaved(saved.sha256, dirty ? text : null)
  }, [saved, text, dirty])

  if (!saved) {
    return loadError ? (
      <p className="card p-5 text-sm text-rose-700 dark:text-rose-400" role="alert">
        {loadError}
      </p>
    ) : (
      <p className="card flex items-center gap-2 p-5 text-sm">
        <LoaderCircle className="size-4 animate-spin" aria-hidden /> Cargando tu perfil…
      </p>
    )
  }

  const chars = profileChars(text)
  const max = saved.max_chars
  const over = chars > max
  const outdated = saved.outdated
  const offer = !dirty && outdated.count > 0 && !offerClosed && !rejudging
  const previous = saved.previous_text
  const canRestore = previous !== null && cleanProfile(previous) !== '' && cleanProfile(previous) !== cleanProfile(text)

  // La pinza aprieta la hoja: guardado.
  const pressClip = () => {
    const clip = clipRef.current
    if (!canAnimate(clip)) return
    clip.animate([{ transform: 'none' }, { transform: 'translateY(3px) scaleY(0.84)' }, { transform: 'none' }], {
      duration: 380,
      easing: EASE_HAND,
    })
  }

  const save = async (base: string = saved.sha256) => {
    setBusy('save')
    setError(null)
    try {
      const next = await hunterApi.saveProfile(token, text, base)
      const before = new Set(saved.terms.map(fold))
      setNewTerms(new Set(next.terms.filter((t) => !before.has(fold(t)))))
      setSaved(next)
      setText(next.text)
      setConflict(false)
      setDraftNotes(null)
      setJustSaved(true)
      setOfferClosed(false)
      pressClip()
      toast.success('Perfil guardado. Las ofertas nuevas ya se puntúan con él.')
    } catch (err) {
      if (err instanceof HunterError && err.code === 'PROFILE_CHANGED') setConflict(true)
      else setError(err instanceof Error ? err.message : 'No se pudo guardar el perfil.')
    } finally {
      setBusy(null)
    }
  }

  /** El archivo cambió fuera de la web: quedarse con esa versión o guardar encima la de la web. */
  const resolveConflict = async (keep: 'file' | 'mine') => {
    setBusy('conflict')
    setError(null)
    try {
      const current = await hunterApi.profile(token)
      if (keep === 'mine') {
        await save(current.sha256)
        return
      }
      setSaved(current)
      setText(current.text)
      setConflict(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo leer el perfil.')
    } finally {
      setBusy((b) => (b === 'conflict' ? null : b))
    }
  }

  const draftFrom = async (file: File, source: string) => {
    if (file.size > MAX_PDF_BYTES) {
      setError('El PDF supera los 5 MB.')
      return
    }
    if (dirty && !window.confirm('Tienes cambios sin guardar en tu perfil. ¿Los sustituyo por el borrador de tu CV?')) {
      return
    }
    setBusy('draft')
    setError(null)
    try {
      const draft = await hunterApi.profileDraft(token, file)
      setText(draft.text)
      setDraftNotes({ source, warnings: draft.warnings })
      toast.success('Borrador listo. Revísalo y guárdalo cuando te convenza.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo leer el CV.')
    } finally {
      setBusy(null)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const rejudge = async () => {
    setBusy('rejudge')
    setError(null)
    try {
      const { run_id } = await hunterApi.startRun(token, 'rejudge')
      setRejudging(true)
      onRejudgeStarted(run_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo empezar a juzgar.')
    } finally {
      setBusy(null)
    }
  }

  const canSave = dirty && !over && busy === null

  return (
    <section aria-labelledby={titleId} className="space-y-4">
      <div>
        <h2 id={titleId} className="text-base font-semibold">
          Tu perfil
        </h2>
        <p className="mt-0.5 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
          La IA lo lee antes de puntuar cada oferta. Se guarda en tu equipo y se envía a Groq con cada oferta que juzga,
          así que no pongas tu nombre ni tus datos de contacto.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_16rem]">
        <div className="min-w-0 space-y-3">
          <div className="board">
            <span ref={clipRef} className="board-clip origin-top" aria-hidden />
            <div className="sheet px-5 pt-9 pb-3 focus-within:ring-2 focus-within:ring-cobalt-500 sm:px-8 sm:pt-11">
              {!dirty && (saved.is_example || !saved.exists) && (
                <p className="mb-3 font-sans text-[13px] leading-5 text-amber-800 italic">
                  {saved.exists
                    ? 'Todavía es el perfil de ejemplo: la IA está puntuando las ofertas para otra persona.'
                    : 'Aún no tienes perfil: escríbelo aquí o empieza desde tu CV.'}
                </p>
              )}
              <label htmlFor={editorId} className="sr-only">
                Texto de tu perfil
              </label>
              <textarea
                id={editorId}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
                    e.preventDefault()
                    if (canSave) void save()
                  }
                }}
                placeholder={PLACEHOLDER}
                spellCheck
                lang="es"
                aria-describedby={`${hintId} ${countId}`}
                aria-invalid={over || undefined}
                className="renglones block max-h-[70vh] min-h-[392px] w-full resize-none overflow-y-auto bg-transparent p-0 font-serif text-[15px] leading-7 text-ink outline-none field-sizing-content placeholder:text-slate-400"
              />
              <p
                id={countId}
                className={cn(
                  'mt-2 text-right font-sans text-xs tabular-nums',
                  over ? 'font-medium text-rose-700' : chars > max * 0.9 ? 'text-amber-800' : 'text-slate-500',
                )}
              >
                {formatNumber(chars)} / {formatNumber(max)} caracteres
                {over && ` · te sobran ${formatNumber(chars - max)}`}
              </p>
            </div>
          </div>
          <p id={hintId} className="text-xs leading-5 text-slate-500 dark:text-slate-400">
            Cada apartado empieza por «## ». El pre-score saca tus tecnologías de los apartados de habilidades. El juez
            lee como mucho {formatNumber(max)} caracteres. Ctrl + S guarda.
          </p>

          {conflict && (
            <div
              className="rounded-md bg-amber-50 p-3 text-sm leading-6 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
              role="alert"
            >
              <p>
                El archivo del perfil ha cambiado fuera de la web desde que lo abriste (¿lo editaste a mano?). ¿Con cuál
                te quedas?
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void resolveConflict('file')}
                  disabled={busy !== null}
                  className="focus-ring h-8 rounded-md px-3 text-sm font-medium ring-1 ring-amber-700/40 transition hover:bg-amber-100 disabled:opacity-60 dark:hover:bg-amber-900/40"
                >
                  Con el del archivo
                </button>
                <button
                  type="button"
                  onClick={() => void resolveConflict('mine')}
                  disabled={busy !== null}
                  className="focus-ring h-8 rounded-md px-3 text-sm font-medium ring-1 ring-amber-700/40 transition hover:bg-amber-100 disabled:opacity-60 dark:hover:bg-amber-900/40"
                >
                  Con el de la web
                </button>
              </div>
            </div>
          )}
          {error && (
            <p className="text-sm text-rose-700 dark:text-rose-400" role="alert">
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => void save()}
              disabled={!canSave}
              className="focus-ring inline-flex h-9 items-center gap-2 rounded-md bg-cobalt-600 px-3.5 text-sm font-semibold text-white transition hover:bg-cobalt-700 disabled:opacity-60"
            >
              {busy === 'save' && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
              Guardar perfil
            </button>
            {dirty && (
              <button
                type="button"
                onClick={() => {
                  setText(saved.text)
                  setDraftNotes(null)
                  setError(null)
                }}
                disabled={busy !== null}
                className="focus-ring h-9 rounded-md px-3.5 text-sm font-medium ring-1 ring-slate-300 transition hover:bg-white disabled:opacity-60 dark:ring-slate-700 dark:hover:bg-slate-800"
              >
                Descartar cambios
              </button>
            )}
            {canRestore && (
              <button
                type="button"
                onClick={() => {
                  setText(previous)
                  setDraftNotes(null)
                }}
                disabled={busy !== null}
                className="focus-ring ml-auto h-9 rounded-md px-2 text-sm font-medium text-cobalt-700 transition hover:bg-cobalt-50 disabled:opacity-60 dark:text-cobalt-300 dark:hover:bg-slate-800"
              >
                Recuperar la versión anterior
              </button>
            )}
          </div>
        </div>

        <aside className="space-y-6 text-sm leading-6" aria-label="Lo que hace la IA con tu perfil">
          {offer && (
            <div className="space-y-2" role="status">
              {justSaved && <p className="font-medium">Guardado. Las ofertas nuevas ya se puntúan con este perfil.</p>}
              {outdatedText(outdated).map((line) => (
                <p key={line} className="text-slate-600 dark:text-slate-300">
                  {line}
                </p>
              ))}
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => void rejudge()}
                  disabled={busy !== null}
                  className="focus-ring inline-flex h-9 items-center gap-2 rounded-md bg-ink px-3.5 text-sm font-semibold text-white transition hover:bg-ink/90 disabled:opacity-60 dark:bg-white dark:text-slate-900"
                >
                  {busy === 'rejudge' && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
                  Volver a juzgarlas
                </button>
                <button
                  type="button"
                  onClick={() => setOfferClosed(true)}
                  className="focus-ring h-9 rounded-md px-2.5 text-sm font-medium text-slate-600 transition hover:bg-white dark:text-slate-300 dark:hover:bg-slate-800"
                >
                  Ahora no
                </button>
              </div>
            </div>
          )}
          {rejudging && (
            <p className="text-slate-600 dark:text-slate-300" role="status">
              La IA las está volviendo a puntuar: lo ves en el panel de arriba. Cada una conserva su nota hasta que
              llega la nueva.
            </p>
          )}
          {justSaved && !dirty && outdated.count === 0 && !rejudging && (
            <p className="font-medium" role="status">
              Guardado. Las ofertas nuevas ya se puntúan con este perfil.
            </p>
          )}

          <div>
            <h3 className="font-medium">Lo que buscará el pre-score</h3>
            {saved.terms.length > 0 ? (
              <>
                <ul className="mt-2 flex flex-wrap gap-x-2 gap-y-1.5" aria-label="Términos de tu perfil">
                  {saved.terms.map((term) => (
                    <li key={term}>
                      <span className={cn('marker marker-blue', newTerms.has(term) && 'animate-marker')}>{term}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                  {dirty
                    ? 'Son los del perfil guardado: cambian al guardar.'
                    : 'Ordenan qué ofertas juzga antes la IA.'}
                </p>
              </>
            ) : (
              <p className="mt-1 text-slate-600 dark:text-slate-300">
                Ninguno todavía: los saca de un apartado de habilidades, por ejemplo «## Habilidades técnicas».
              </p>
            )}
          </div>

          <div>
            <h3 className="font-medium">Empezar desde tu CV</h3>
            <p className="mt-1 text-slate-600 dark:text-slate-300">
              Copia los apartados de tu CV en PDF, sin tu nombre ni tus datos de contacto. No usa IA y no se guarda
              hasta que lo revisas.
            </p>
            <div className="mt-2 flex flex-col items-start gap-1.5">
              {rememberedCv && (
                <button
                  type="button"
                  onClick={() => void draftFrom(rememberedCv, rememberedCv.name)}
                  disabled={busy !== null}
                  className="focus-ring inline-flex max-w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm font-medium ring-1 ring-slate-300 transition hover:bg-white disabled:opacity-60 dark:ring-slate-700 dark:hover:bg-slate-800"
                >
                  {busy === 'draft' ? (
                    <LoaderCircle className="size-4 shrink-0 animate-spin" aria-hidden />
                  ) : (
                    <FileUp className="size-4 shrink-0" aria-hidden />
                  )}
                  <span className="truncate">Usar {rememberedCv.name}</span>
                </button>
              )}
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={busy !== null}
                className={cn(
                  'focus-ring inline-flex items-center gap-2 rounded-md text-sm font-medium transition disabled:opacity-60',
                  rememberedCv
                    ? 'px-1 py-1 text-cobalt-700 hover:underline dark:text-cobalt-300'
                    : 'px-3 py-1.5 ring-1 ring-slate-300 hover:bg-white dark:ring-slate-700 dark:hover:bg-slate-800',
                )}
              >
                {!rememberedCv &&
                  (busy === 'draft' ? (
                    <LoaderCircle className="size-4 animate-spin" aria-hidden />
                  ) : (
                    <FileUp className="size-4" aria-hidden />
                  ))}
                {rememberedCv ? 'Elegir otro PDF' : 'Elegir tu CV en PDF'}
              </button>
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf,.pdf"
                aria-label="CV en PDF"
                tabIndex={-1}
                className="sr-only"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) void draftFrom(file, file.name)
                }}
              />
            </div>
            {draftNotes && (
              <div className="mt-3 space-y-1" role="status">
                <p className="font-medium">Borrador de {draftNotes.source}, aún sin guardar:</p>
                <ul className="list-disc space-y-1 pl-5 text-slate-600 dark:text-slate-300">
                  {draftNotes.warnings.map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </aside>
      </div>
    </section>
  )
}
