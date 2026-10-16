import { useEffect, useRef } from 'react'

import { motionAllowed } from '../../lib/motion'

/**
 * Campo de trazos de rotulador detrás de la portada: cientos de rayas cortas con los colores de
 * los rotuladores de la app, orientadas hacia el tablero como limaduras hacia un imán. Al cargar
 * llegan desde fuera; después respiran despacio y el centro se inclina un poco hacia el ratón.
 *
 * Canvas 2D sin dependencias. Se pausa fuera de pantalla y con la pestaña oculta; con
 * "reducir movimiento" se pinta una sola vez, quieto.
 */

// Degradado alrededor del imán: cobalto → azul → verde → ámbar → cobalto (los rotuladores de la app).
const STOPS_LIGHT = ['#2747d9', '#3b82f6', '#16a34a', '#d99a00', '#2747d9']
const STOPS_DARK = ['#6a86f1', '#60a5fa', '#4ade80', '#fbbf24', '#6a86f1']

const INTRO_MS = 1700
const MAX_DPR = 2
const POINTER_PULL = 0.07 // fracción de la distancia al ratón que se desplaza el centro
const POINTER_MAX = 46 // px

interface Stroke {
  r: number
  theta: number
  len: number
  phase: number
  alpha: number
  color: string
  delay: number
}

function hexToRgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function colorAt(stops: string[], t: number): string {
  const x = (((t % 1) + 1) % 1) * (stops.length - 1)
  const i = Math.floor(x)
  const f = x - i
  const a = hexToRgb(stops[i])
  const b = hexToRgb(stops[Math.min(i + 1, stops.length - 1)])
  const mix = (k: number) => Math.round(a[k] + (b[k] - a[k]) * f)
  return `rgb(${mix(0)} ${mix(1)} ${mix(2)})`
}

// Pseudoaleatorio determinista: el campo es igual en cada visita (sin "saltos" al redimensionar).
function seeded(seed: number) {
  let s = seed
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296
    return s / 4294967296
  }
}

interface Rect {
  left: number
  top: number
  right: number
  bottom: number
}

/** Atenuación dentro de las zonas de texto (con borde suave): el texto siempre se lee bien. */
function avoidFactor(x: number, y: number, zones: Rect[]): number {
  let factor = 1
  for (const zone of zones) {
    const edge = 36
    const inside = Math.min(x - zone.left, zone.right - x, y - zone.top, zone.bottom - y)
    if (inside <= -edge) continue
    factor = Math.min(factor, inside >= 0 ? 0.15 : 0.15 + (0.85 * -inside) / edge)
  }
  return factor
}

function buildStrokes(width: number, height: number, inner: number, dark: boolean): Stroke[] {
  const rand = seeded(20261016)
  const stops = dark ? STOPS_DARK : STOPS_LIGHT
  const outer = Math.hypot(width, height) * 0.62
  const spacing = width < 640 ? 26 : 30 // distancia entre anillos
  const strokes: Stroke[] = []
  for (let ring = 0, r = inner; r < outer; ring++, r += spacing * (1 + ring * 0.035)) {
    const closeness = 1 - (r - inner) / (outer - inner)
    // Más trazos cerca del imán; los anillos exteriores quedan ralos.
    const perimeter = 2 * Math.PI * r
    const gap = 26 + (1 - closeness) * 46
    const count = Math.max(6, Math.round(perimeter / gap))
    const twist = rand() * Math.PI * 2
    for (let i = 0; i < count; i++) {
      const theta = twist + (i / count) * Math.PI * 2 + (rand() - 0.5) * (Math.PI / count)
      if (rand() < 0.12) continue // huecos: a mano nunca sale perfecto
      strokes.push({
        r: r + (rand() - 0.5) * spacing * 0.35,
        theta,
        len: 4 + rand() * 4 + closeness * 4,
        phase: ring * 0.45 + rand() * 0.6,
        alpha: (dark ? 0.16 : 0.12) + Math.pow(closeness, 1.4) * (dark ? 0.7 : 0.72),
        color: colorAt(stops, theta / (Math.PI * 2) + 0.15),
        delay: ((r - inner) / (outer - inner)) * 650 + rand() * 200,
      })
    }
  }
  return strokes
}

const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)

export function MarkerField({ anchorSelector, avoidSelector }: { anchorSelector: string; avoidSelector?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    const host = canvas?.parentElement
    // jsdom (tests) no tiene IntersectionObserver ni canvas: no hay nada que pintar.
    if (!canvas || !host || typeof IntersectionObserver === 'undefined') return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const darkQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const animate = motionAllowed()
    let strokes: Stroke[] = []
    let width = 0
    let height = 0
    let center = { x: 0, y: 0 }
    let avoid: Rect[] = []
    const offset = { x: 0, y: 0 }
    const target = { x: 0, y: 0 }
    let start = performance.now()
    let frame = 0
    let visible = true

    const layout = () => {
      const box = host.getBoundingClientRect()
      const anchor = host.querySelector(anchorSelector)?.getBoundingClientRect()
      width = box.width
      height = box.height
      const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      center = anchor
        ? { x: anchor.left - box.left + anchor.width / 2, y: anchor.top - box.top + anchor.height / 2 }
        : { x: width * 0.72, y: height * 0.5 }
      avoid = avoidSelector
        ? [...host.querySelectorAll(avoidSelector)].map((el) => {
            const r = el.getBoundingClientRect()
            return {
              left: r.left - box.left,
              top: r.top - box.top,
              right: r.right - box.left,
              bottom: r.bottom - box.top,
            }
          })
        : []
      // El hueco interior lo tapa el tablero: los trazos empiezan justo fuera de él.
      const inner = anchor ? Math.max(anchor.width, anchor.height) * 0.42 : Math.min(width, height) * 0.25
      strokes = buildStrokes(width, height, inner, darkQuery.matches)
    }

    const draw = (now: number) => {
      const elapsed = now - start
      const t = now / 1000
      offset.x += (target.x - offset.x) * 0.06
      offset.y += (target.y - offset.y) * 0.06
      const cx = center.x + offset.x
      const cy = center.y + offset.y
      ctx.clearRect(0, 0, width, height)
      ctx.lineCap = 'round'
      ctx.lineWidth = 2
      for (const s of strokes) {
        const k = animate ? easeOut(Math.min(1, Math.max(0, (elapsed - s.delay) / (INTRO_MS - 650)))) : 1
        if (k <= 0) continue
        const breathe = animate ? 1 + Math.sin(t * 0.9 - s.phase) * 0.014 : 1
        const r = s.r * breathe * (1 + (1 - k) * 0.55)
        const theta = s.theta + (animate ? Math.sin(t * 0.25 + s.phase) * 0.012 : 0)
        const dx = Math.cos(theta)
        const dy = Math.sin(theta)
        const x = cx + dx * r
        const y = cy + dy * r
        if (x < -10 || y < -10 || x > width + 10 || y > height + 10) continue
        const half = s.len / 2
        ctx.globalAlpha = s.alpha * k * avoidFactor(x, y, avoid)
        ctx.strokeStyle = s.color
        ctx.beginPath()
        ctx.moveTo(x - dx * half, y - dy * half)
        ctx.lineTo(x + dx * half, y + dy * half)
        ctx.stroke()
      }
      ctx.globalAlpha = 1
    }

    const loop = (now: number) => {
      draw(now)
      frame = visible && !document.hidden ? requestAnimationFrame(loop) : 0
    }
    const resume = () => {
      if (animate && !frame && visible && !document.hidden) frame = requestAnimationFrame(loop)
    }

    layout()
    if (animate) frame = requestAnimationFrame(loop)
    else draw(performance.now())

    const resizeObserver = new ResizeObserver(() => {
      layout()
      if (!animate) draw(performance.now())
    })
    resizeObserver.observe(host)
    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting
      resume()
    })
    io.observe(host)
    const onVisibility = () => resume()
    document.addEventListener('visibilitychange', onVisibility)
    const onScheme = () => {
      layout()
      if (!animate) draw(performance.now())
    }
    darkQuery.addEventListener('change', onScheme)
    const onPointer = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse' || !animate) return
      const box = host.getBoundingClientRect()
      const clamp = (v: number) => Math.max(-POINTER_MAX, Math.min(POINTER_MAX, v))
      target.x = clamp((e.clientX - box.left - center.x) * POINTER_PULL)
      target.y = clamp((e.clientY - box.top - center.y) * POINTER_PULL)
    }
    const onLeave = () => {
      target.x = 0
      target.y = 0
    }
    host.addEventListener('pointermove', onPointer, { passive: true })
    host.addEventListener('pointerleave', onLeave)
    start = performance.now()

    return () => {
      cancelAnimationFrame(frame)
      resizeObserver.disconnect()
      io.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      darkQuery.removeEventListener('change', onScheme)
      host.removeEventListener('pointermove', onPointer)
      host.removeEventListener('pointerleave', onLeave)
    }
  }, [anchorSelector, avoidSelector])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 -z-10 size-full [mask-image:linear-gradient(to_bottom,black_70%,transparent)]"
    />
  )
}
