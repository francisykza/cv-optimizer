// Utilidades de animación con la Web Animations API (sin dependencias).
// Toda animación respeta prefers-reduced-motion y se omite si el navegador no soporta animate()
// (p. ej. jsdom en los tests): el contenido siempre queda en su estado final.

export function motionAllowed(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Movimiento permitido y un navegador real (jsdom no implementa animate()). */
export function animationsSupported(): boolean {
  return motionAllowed() && typeof document !== 'undefined' && typeof document.body?.animate === 'function'
}

export function canAnimate(el: Element | null | undefined): el is HTMLElement {
  return Boolean(el) && typeof (el as HTMLElement).animate === 'function' && motionAllowed()
}

/** Anima y espera a que termine (si se cancela, resuelve igual). */
export async function play(
  el: HTMLElement | SVGElement,
  keyframes: Keyframe[],
  options: KeyframeAnimationOptions,
): Promise<void> {
  const animation = el.animate(keyframes, { fill: 'forwards', ...options })
  try {
    await animation.finished
  } catch {
    // Cancelada (desmontaje o repetición): no es un error.
  }
}

export const wait = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms))

/** Curvas: un "aterrizaje" con rebote leve y un movimiento de mano natural. */
export const EASE_LAND = 'cubic-bezier(0.2, 0.9, 0.25, 1.15)'
export const EASE_HAND = 'cubic-bezier(0.45, 0, 0.25, 1)'
