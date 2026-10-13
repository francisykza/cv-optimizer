import { Plus, Sparkles, X } from 'lucide-react'

interface AtsSuggestionsProps {
  /** Sugerencias aún no añadidas. */
  suggestions: string[]
  /** Habilidades que el usuario ya ha añadido a su CV desde este panel. */
  added: string[]
  onAdd: (skill: string) => void
  onRemove: (skill: string) => void
  disabled?: boolean
}

export function AtsSuggestions({ suggestions, added, onAdd, onRemove, disabled = false }: AtsSuggestionsProps) {
  if (suggestions.length === 0 && added.length === 0) return null

  return (
    <div className="card p-5">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold">
        <Sparkles className="size-4 text-sky-500" aria-hidden />
        Sugerencias ATS
      </h3>
      <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
        Requisitos de la oferta que no están en tu CV. Añade solo lo que realmente dominas: el reclutador puede
        preguntarte por ello.
      </p>

      {suggestions.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2" aria-label="Habilidades sugeridas">
          {suggestions.map((skill) => (
            <li key={skill}>
              <button
                type="button"
                onClick={() => onAdd(skill)}
                disabled={disabled}
                aria-label={`Añadir ${skill} al CV`}
                className="focus-ring inline-flex items-center gap-1 rounded-full bg-white py-1 pr-3 pl-2 text-xs font-medium text-sky-800 ring-1 ring-sky-200 transition hover:bg-sky-50 hover:ring-sky-300 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-slate-900 dark:text-sky-300 dark:ring-sky-500/30 dark:hover:bg-sky-500/10"
              >
                <Plus className="size-3.5" aria-hidden />
                {skill}
              </button>
            </li>
          ))}
        </ul>
      )}

      {added.length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
          <p className="text-xs font-medium text-slate-600 dark:text-slate-300">Añadidas por ti</p>
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Habilidades añadidas">
            {added.map((skill) => (
              <li
                key={skill}
                className="inline-flex items-center gap-1 rounded-full bg-sky-100 py-1 pr-1 pl-3 text-xs font-medium text-sky-900 ring-1 ring-sky-300 dark:bg-sky-500/20 dark:text-sky-100 dark:ring-sky-500/40"
              >
                {skill}
                <button
                  type="button"
                  onClick={() => onRemove(skill)}
                  disabled={disabled}
                  aria-label={`Quitar ${skill} del CV`}
                  className="focus-ring rounded-full p-0.5 transition hover:bg-sky-200 disabled:cursor-not-allowed dark:hover:bg-sky-500/30"
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
