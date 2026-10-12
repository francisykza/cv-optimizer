/** Esqueleto del resultado mientras la IA trabaja. */
export function ResultSkeleton() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]" aria-hidden>
      <div className="card space-y-4 p-6 sm:p-10">
        <div className="skeleton h-8 w-1/2" />
        <div className="skeleton h-4 w-1/3" />
        <div className="space-y-2.5 pt-6">
          <div className="skeleton h-3 w-24" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-4 w-11/12" />
          <div className="skeleton h-4 w-4/5" />
        </div>
        <div className="space-y-2.5 pt-6">
          <div className="skeleton h-3 w-28" />
          <div className="skeleton h-4 w-2/3" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-4 w-5/6" />
          <div className="skeleton h-4 w-3/4" />
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
