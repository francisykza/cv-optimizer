import { Clipboard } from '../ui/Clipboard'

// Líneas de la hoja: ancho y, si la repasa un rotulador, su color y retardo.
type Line = { w: string; mark?: 'green' | 'amber' | 'blue'; delay?: number }
const SECTIONS: Line[][] = [
  [{ w: '78%', mark: 'amber', delay: 0 }, { w: '92%' }, { w: '64%' }],
  [{ w: '40%' }, { w: '88%', mark: 'green', delay: 0.5 }, { w: '95%' }, { w: '70%', mark: 'green', delay: 1 }],
  [{ w: '58%' }, { w: '84%', mark: 'blue', delay: 1.5 }],
]

/** Mientras la IA trabaja: la hoja ya está en el tablero y los rotuladores van repasándola. */
export function ResultSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]" aria-hidden>
      <div className="card overflow-hidden">
        <div className="bg-desk p-3 sm:p-6 dark:bg-slate-950/60">
          <Clipboard className="mx-auto max-w-3xl">
            <div className="sheet px-6 pt-11 pb-10 sm:px-14 sm:pt-14 sm:pb-14">
              <div className="h-5 w-1/2 rounded-full bg-slate-300" />
              <div className="mt-3 h-3 w-1/3 rounded-full bg-slate-200" />
              {SECTIONS.map((lines, s) => (
                <div key={s} className="mt-8 space-y-3.5">
                  <div className="h-3 w-28 rounded-full bg-slate-300" />
                  <div className="h-px bg-slate-200" />
                  {lines.map((line, i) => (
                    <div key={i} className="working-line" style={{ width: line.w }}>
                      {line.mark && (
                        <span
                          className={`working-mark marker-${line.mark}`}
                          style={{ animationDelay: `${line.delay}s` }}
                        />
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </Clipboard>
        </div>
      </div>
      <div className="space-y-6">
        <div className="card flex items-center gap-5 p-5">
          <div className="skeleton size-28 rounded-full" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-4 w-3/4" />
            <div className="skeleton h-4 w-1/2" />
          </div>
        </div>
        <div className="card space-y-3 p-5">
          <div className="skeleton h-4 w-1/2" />
          <div className="flex flex-wrap gap-1.5">
            {[16, 20, 12, 24, 14, 18].map((w, i) => (
              <div key={i} className="skeleton h-6" style={{ width: `${w * 4}px` }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
