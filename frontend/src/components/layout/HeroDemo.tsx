import { RotateCcw } from 'lucide-react'
import { type PointerEvent, useCallback, useLayoutEffect, useRef } from 'react'

import { cn } from '../../lib/format'
import { canAnimate, EASE_HAND, EASE_LAND, motionAllowed, play, wait } from '../../lib/motion'
import { MarkerPen } from '../ui/MarkerPen'

type Ink = 'green' | 'amber' | 'blue'

const INK: Record<Ink, string> = { green: '#4ade80', amber: '#f5b40b', blue: '#60a5fa' }

const LEGEND: { ink: Ink; color: string; text: string }[] = [
  { ink: 'green', color: 'bg-marker-green', text: 'Reformulado a partir de lo que ya pone tu CV' },
  { ink: 'amber', color: 'bg-marker-amber', text: 'No aparece en tu CV: te avisamos para que lo revises' },
  { ink: 'blue', color: 'bg-marker-blue', text: 'Añadido por ti, solo si lo dominas' },
]

// Orden de lectura del corrector: de arriba abajo.
const STROKES: Ink[] = ['amber', 'green', 'blue']
const PEN_HEIGHT = 32 // la punta del rotulador está en la esquina inferior izquierda del SVG
const DRAW_SPEED = 0.55 // px por ms al subrayar

/**
 * Demo de la portada: el tablero cae sobre la mesa, la pinza se cierra sobre la hoja y un
 * rotulador repasa el CV marcando cada tipo de cambio. Es la gran animación automática de la
 * web; sin movimiento reducido se muestra directamente el resultado final.
 */
export function HeroDemo() {
  const tiltRef = useRef<HTMLDivElement>(null)
  const boardRef = useRef<HTMLDivElement>(null)
  const clipRef = useRef<HTMLButtonElement>(null)
  const sheetRef = useRef<HTMLDivElement>(null)
  const penRef = useRef<SVGSVGElement>(null)
  const noteRef = useRef<HTMLParagraphElement>(null)
  const markerRefs = useRef<Partial<Record<Ink, HTMLSpanElement | null>>>({})
  const legendRefs = useRef<Partial<Record<Ink, HTMLLIElement | null>>>({})
  const runId = useRef(0)

  /** Estado inicial (antes de pintar) para que no haya parpadeo del resultado final. */
  const prepare = useCallback(() => {
    const board = boardRef.current
    if (!canAnimate(board)) return false
    board.getAnimations({ subtree: true }).forEach((a) => a.cancel())
    Object.values(legendRefs.current).forEach((li) => li?.getAnimations().forEach((a) => a.cancel()))
    board.style.opacity = '0'
    Object.values(markerRefs.current).forEach((m) => m && (m.style.backgroundSize = '0% 100%'))
    if (noteRef.current) noteRef.current.style.clipPath = 'inset(0 100% 0 0)'
    if (penRef.current) penRef.current.style.opacity = '0'
    Object.values(legendRefs.current).forEach((li) => li && (li.style.opacity = '0.45'))
    return true
  }, [])

  const run = useCallback(async () => {
    const id = ++runId.current
    const alive = () => id === runId.current
    const board = boardRef.current!
    const sheet = sheetRef.current!
    const clip = clipRef.current!
    const pen = penRef.current!

    // 1. El tablero cae sobre la mesa con un giro que se asienta.
    board.style.opacity = ''
    const landing = play(
      board,
      [
        { opacity: 0, transform: 'translateY(-48px) rotate(-7deg) scale(0.96)' },
        { opacity: 1, transform: 'translateY(0) rotate(0deg) scale(1)' },
      ],
      { duration: 750, easing: EASE_LAND },
    )
    // 2. La hoja se desliza bajo la pinza abierta.
    void play(
      sheet,
      [
        { transform: 'translateY(-22px)', opacity: 0 },
        { transform: 'translateY(0)', opacity: 1 },
      ],
      { duration: 520, delay: 260, easing: 'cubic-bezier(0.16, 1, 0.3, 1)' },
    )
    // 3. La pinza se cierra de golpe y el tablero acusa el impacto.
    void play(
      clip,
      [
        { transform: 'perspective(240px) rotateX(70deg) translateY(-6px)' },
        { transform: 'perspective(240px) rotateX(70deg) translateY(-6px)', offset: 0.55 },
        { transform: 'perspective(240px) rotateX(-12deg)', offset: 0.85 },
        { transform: 'perspective(240px) rotateX(0deg)' },
      ],
      { duration: 1050, easing: 'ease-in' },
    )
    await landing
    await wait(220)
    if (!alive()) return
    void play(
      board,
      [{ transform: 'translateY(0)' }, { transform: 'translateY(3px)' }, { transform: 'translateY(0)' }],
      {
        duration: 180,
        easing: 'ease-out',
        composite: 'add',
      },
    )

    // 4. El rotulador repasa el CV.
    await wait(250)
    const sheetBox = sheet.getBoundingClientRect()
    // El rotulador entra y sale por dentro de la hoja: fuera de ella provocaría scroll horizontal
    // en el móvil.
    const parkX = Math.max(0, sheetBox.width - 110)
    let penAt = { x: parkX, y: sheetBox.height * 0.18 }
    const penTo = (x: number, y: number) => `translate(${x}px, ${y - PEN_HEIGHT}px)`
    pen.style.transform = penTo(penAt.x, penAt.y)
    await play(pen, [{ opacity: 0 }, { opacity: 1 }], { duration: 200 })

    for (const ink of STROKES) {
      const marker = markerRefs.current[ink]
      if (!marker || !alive()) return
      pen.style.color = INK[ink]
      const lines = [...marker.getClientRects()].map((r) => ({
        x1: r.left - sheetBox.left,
        x2: r.right - sheetBox.left,
        y: r.bottom - sheetBox.top - 4,
      }))
      const total = lines.reduce((sum, l) => sum + (l.x2 - l.x1), 0)
      // Trayecto hasta el inicio del trazo, levantando un poco la mano.
      await play(pen, [{ transform: penTo(penAt.x, penAt.y) }, { transform: penTo(lines[0].x1, lines[0].y) }], {
        duration: 420,
        easing: EASE_HAND,
      })
      const drawMs = total / DRAW_SPEED
      void play(marker, [{ backgroundSize: '0% 100%' }, { backgroundSize: '100% 100%' }], {
        duration: drawMs,
        easing: 'linear',
      })
      for (const line of lines) {
        await play(pen, [{ transform: penTo(line.x1, line.y) }, { transform: penTo(line.x2, line.y) }], {
          duration: (line.x2 - line.x1) / DRAW_SPEED,
          easing: 'linear',
        })
        penAt = { x: line.x2, y: line.y }
      }
      marker.style.backgroundSize = '100% 100%'
      const legend = legendRefs.current[ink]
      if (legend) void play(legend, [{ opacity: 0.45 }, { opacity: 1 }], { duration: 300 })
      // La nota del corrector se "escribe" tras marcar lo que no está en el CV.
      if (ink === 'amber' && noteRef.current) {
        await play(noteRef.current, [{ clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)' }], {
          duration: 650,
          easing: 'linear',
        })
        noteRef.current.style.clipPath = ''
      }
    }

    // 5. El rotulador sale de la hoja.
    await play(
      pen,
      [
        { transform: penTo(penAt.x, penAt.y), opacity: 1 },
        { transform: penTo(parkX, penAt.y + 36), opacity: 0 },
      ],
      { duration: 500, easing: 'ease-in' },
    )
  }, [])

  useLayoutEffect(() => {
    if (prepare()) void run()
    return () => {
      runId.current++
    }
  }, [prepare, run])

  // Inclinación 3D: el tablero sigue al puntero como si se sostuviera en la mano.
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (e.pointerType !== 'mouse' || !motionAllowed() || !tiltRef.current) return
    const box = tiltRef.current.getBoundingClientRect()
    const dx = (e.clientX - box.left) / box.width - 0.5
    const dy = (e.clientY - box.top) / box.height - 0.5
    tiltRef.current.style.transform = `perspective(1100px) rotateX(${(-dy * 7).toFixed(2)}deg) rotateY(${(dx * 9).toFixed(2)}deg)`
  }
  const onPointerLeave = () => {
    if (tiltRef.current) tiltRef.current.style.transform = ''
  }

  const replay = () => {
    if (prepare()) void run()
  }

  return (
    <figure aria-label="Ejemplo de CV optimizado" className="mx-auto w-full max-w-md lg:max-w-none">
      <div
        ref={tiltRef}
        onPointerMove={onPointerMove}
        onPointerLeave={onPointerLeave}
        className="transition-transform duration-500 ease-out will-change-transform"
      >
        <div ref={boardRef} className="board lg:rotate-[0.8deg]">
          <button
            ref={clipRef}
            type="button"
            onClick={replay}
            aria-label="Repetir la demostración"
            title="Repetir la demostración"
            className="board-clip focus-ring pointer-events-auto cursor-pointer border-0 p-0"
          />
          <div
            ref={sheetRef}
            className="sheet relative px-7 pt-10 pb-8 font-serif text-[15px] leading-relaxed sm:px-10 sm:pt-12 sm:pb-10"
          >
            <p className="text-xl font-semibold">Laura Pérez Gil</p>
            <p className="text-slate-600">Auxiliar administrativa en Sevilla</p>

            <p className="mt-6 border-b border-slate-200 pb-1 font-semibold">Resumen profesional</p>
            <p className="mt-2">
              Auxiliar administrativa con experiencia en contabilidad y gestión laboral,{' '}
              <span ref={(el) => void (markerRefs.current.amber = el)} className="marker marker-amber">
                orientada a resultados
              </span>
              .
            </p>
            <p ref={noteRef} className="mt-1 font-sans text-xs text-amber-800 italic">
              Revisa esto: no aparece en tu CV original.
            </p>

            <p className="mt-6 border-b border-slate-200 pb-1 font-semibold">Experiencia</p>
            <p className="mt-2">
              <span ref={(el) => void (markerRefs.current.green = el)} className="marker marker-green">
                Gestión de la facturación y la contabilidad
              </span>{' '}
              de clientes con Contanet.
            </p>

            <p className="mt-6 border-b border-slate-200 pb-1 font-semibold">Habilidades</p>
            <p className="mt-2">
              Contanet, Excel, paquete Office,{' '}
              <span ref={(el) => void (markerRefs.current.blue = el)} className="marker marker-blue">
                carnet de conducir
              </span>
            </p>

            <MarkerPen ref={penRef} className="z-20 drop-shadow-[0_6px_6px_rgb(15_23_42/0.35)]" />
          </div>
        </div>
      </div>

      <figcaption className="mt-6 flex flex-wrap items-start justify-between gap-4">
        <ul className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
          {LEGEND.map(({ ink, color, text }) => (
            <li key={ink} ref={(el) => void (legendRefs.current[ink] = el)} className="flex items-center gap-3">
              <span className={cn('h-3 w-6 shrink-0 rounded-[2px]', color)} aria-hidden />
              {text}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={replay}
          className="focus-ring inline-flex items-center gap-1.5 rounded-md text-xs font-medium text-slate-500 hover:text-cobalt-700 dark:text-slate-400 dark:hover:text-cobalt-300"
        >
          <RotateCcw className="size-3.5" aria-hidden />
          Ver de nuevo
        </button>
      </figcaption>
    </figure>
  )
}
