import { animationsSupported, EASE_HAND } from './motion'

/**
 * Hace "volar" una copia del chip pulsado hasta su resaltado en el CV y lo hace brillar al llegar.
 * Hay que llamarla en el clic, antes de que el chip desaparezca: mide y clona en ese momento.
 * Si el resaltado está fuera de la pantalla, el chip vuela hacia el borde por el que queda el CV.
 */
export function flyToMark(source: HTMLElement, getContainer: () => HTMLElement | null, term: string): void {
  if (!animationsSupported()) return
  const from = source.getBoundingClientRect()
  const ghost = source.cloneNode(true) as HTMLElement
  ghost.removeAttribute('id')
  ghost.setAttribute('aria-hidden', 'true')
  Object.assign(ghost.style, {
    position: 'fixed',
    left: `${from.left}px`,
    top: `${from.top}px`,
    width: `${from.width}px`,
    height: `${from.height}px`,
    margin: '0',
    zIndex: '60',
    pointerEvents: 'none',
  })

  // Dos fotogramas: React ya ha pintado el CV con la habilidad añadida.
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      const marks = getContainer()?.querySelectorAll<HTMLElement>('mark[data-kind="added"]') ?? []
      const mark = [...marks].find((m) => m.dataset.term?.toLowerCase() === term.toLowerCase())
      if (!mark) return
      const to = mark.getBoundingClientRect()
      const visible = to.bottom > 0 && to.top < window.innerHeight
      const targetY = visible ? to.top : Math.min(Math.max(to.top, 72), window.innerHeight - 48)
      const dx = to.left - from.left
      const dy = targetY - from.top

      document.body.appendChild(ghost)
      const flight = ghost.animate(
        [
          { transform: 'translate(0, 0) scale(1)', opacity: 1 },
          {
            transform: `translate(${dx * 0.45}px, ${dy * 0.45 - 90}px) scale(1.1) rotate(-4deg)`,
            opacity: 1,
            offset: 0.5,
          },
          { transform: `translate(${dx}px, ${dy}px) scale(0.8)`, opacity: visible ? 0.15 : 0 },
        ],
        { duration: 750, easing: EASE_HAND },
      )
      void flight.finished
        .catch(() => undefined)
        .then(() => {
          ghost.remove()
          if (!visible) return
          mark.animate(
            [{ boxShadow: '0 0 0 0 rgb(96 165 250 / 0.85)' }, { boxShadow: '0 0 0 12px rgb(96 165 250 / 0)' }],
            { duration: 650, iterations: 2, easing: 'ease-out' },
          )
        })
    }),
  )
}
