import { Plus, ShieldAlert, X } from 'lucide-react'
import { type FormEvent, useId, useState } from 'react'

import { type ExperienceEntry, experienceNote, SKILLS_TARGET } from '../../lib/injectSkill'

export interface ExperienceNote {
  gap: string
  note: string
  /** SKILLS_TARGET o la línea del puesto donde se añade. */
  target: string
}

interface GapListProps {
  /** Requisitos pendientes (sin los que el usuario ya ha resuelto). */
  gaps: string[]
  notes: ExperienceNote[]
  /** Puestos del CV donde se puede añadir la experiencia, además de Habilidades. */
  entries: ExperienceEntry[]
  onAddNote: (note: ExperienceNote) => void
  onRemoveNote: (gap: string) => void
}

const MIN_NOTE_CHARS = 8

/** "Lo que pide la oferta y no está en tu CV", con la opción de aportar experiencia real. */
export function GapList({ gaps, notes, entries, onAddNote, onRemoveNote }: GapListProps) {
  const [editing, setEditing] = useState<string | null>(null)
  if (gaps.length === 0 && notes.length === 0) return null

  return (
    <div className="card p-5">
      <div className="flex items-center gap-2.5">
        <span className="flex size-7 items-center justify-center rounded-md bg-amber-50 text-amber-600 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20">
          <ShieldAlert className="size-4" aria-hidden />
        </span>
        <h3 className="text-sm font-semibold">Lo que pide la oferta y no está en tu CV</h3>
      </div>
      <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        No lo hemos añadido porque no aparece en tu CV original. Si tienes experiencia real, cuéntala en una frase y
        elige dónde añadirla: en Habilidades o en el puesto donde la usaste.
      </p>

      {gaps.length > 0 && (
        <ul className="mt-3 space-y-3" aria-label="Requisitos que no están en tu CV">
          {gaps.map((gap) => (
            <li key={gap} className="text-sm leading-relaxed text-slate-700 dark:text-slate-300">
              <div className="flex gap-2">
                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-400" aria-hidden />
                <span className="flex-1">{gap}</span>
              </div>
              {editing === gap ? (
                <NoteForm
                  gap={gap}
                  entries={entries}
                  onCancel={() => setEditing(null)}
                  onSubmit={(note, target) => {
                    onAddNote({ gap, note, target })
                    setEditing(null)
                  }}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setEditing(gap)}
                  className="focus-ring mt-1.5 ml-3.5 inline-flex items-center gap-1 rounded-full py-0.5 pr-2.5 pl-1.5 text-xs font-medium text-cobalt-700 ring-1 ring-cobalt-200 transition hover:bg-cobalt-50 dark:text-cobalt-300 dark:ring-cobalt-500/30 dark:hover:bg-cobalt-500/10"
                >
                  <Plus className="size-3.5" aria-hidden />
                  Sí tengo experiencia en esto
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {notes.length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
          <p className="text-xs font-medium text-slate-600 dark:text-slate-300">Añadido por ti</p>
          <ul className="mt-2 space-y-2" aria-label="Experiencia añadida por ti">
            {notes.map(({ gap, note, target }) => (
              <li
                key={gap}
                className="flex items-start gap-2 rounded-md bg-sky-50 px-2.5 py-2 text-xs text-sky-900 ring-1 ring-sky-200 dark:bg-sky-500/10 dark:text-sky-100 dark:ring-sky-500/30"
              >
                <span className="flex-1">
                  {experienceNote(gap, note, target)}
                  <span className="mt-0.5 block text-[11px] text-sky-700 dark:text-sky-300">
                    En {target === SKILLS_TARGET ? 'Habilidades' : entries.find((e) => e.line === target)?.label}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => onRemoveNote(gap)}
                  aria-label={`Quitar del CV: ${gap}`}
                  className="focus-ring -m-0.5 rounded-full p-0.5 transition hover:bg-sky-200 dark:hover:bg-sky-500/30"
                >
                  <X className="size-3" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

interface NoteFormProps {
  gap: string
  entries: ExperienceEntry[]
  onSubmit: (note: string, target: string) => void
  onCancel: () => void
}

function NoteForm({ gap, entries, onSubmit, onCancel }: NoteFormProps) {
  const [note, setNote] = useState('')
  const [target, setTarget] = useState(SKILLS_TARGET)
  const inputId = useId()
  const targetId = useId()
  const valid = note.trim().length >= MIN_NOTE_CHARS

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (valid) onSubmit(note.trim(), target)
  }

  return (
    <form onSubmit={submit} className="mt-2 ml-3.5 space-y-2">
      <label htmlFor={inputId} className="block text-xs text-slate-600 dark:text-slate-400">
        ¿Cómo lo has usado? Una frase basta.
      </label>
      <input
        id={inputId}
        autoFocus
        value={note}
        onChange={(e) => setNote(e.target.value)}
        maxLength={160}
        placeholder="Ej.: Lo apliqué en proyectos de automatización en Python"
        aria-label={`Tu experiencia con ${gap}`}
        className="focus-ring h-9 w-full rounded-md border border-slate-300 bg-paper px-2.5 text-sm dark:border-slate-700 dark:bg-slate-950"
      />
      {entries.length > 0 && (
        <div>
          <label htmlFor={targetId} className="block text-xs text-slate-600 dark:text-slate-400">
            ¿Dónde lo añadimos?
          </label>
          <select
            id={targetId}
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="focus-ring mt-1 h-9 w-full rounded-md border border-slate-300 bg-paper px-2 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value={SKILLS_TARGET}>Habilidades</option>
            {entries.map((entry) => (
              <option key={entry.line} value={entry.line}>
                Experiencia: {entry.label}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!valid}
          className="focus-ring h-8 rounded-md bg-cobalt-600 px-3 text-xs font-semibold text-white transition-colors hover:bg-cobalt-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-cobalt-500"
        >
          Añadir al CV
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="focus-ring h-8 rounded-md px-3 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
        >
          Cancelar
        </button>
      </div>
    </form>
  )
}
