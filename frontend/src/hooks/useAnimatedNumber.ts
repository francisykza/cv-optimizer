import { useEffect, useRef, useState } from 'react'

import { animationsSupported } from '../lib/motion'

/** Cuenta desde `from` hasta `target` al montar, y desde el valor anterior cuando `target` cambia
 *  (p. ej. al añadir una habilidad). Sin movimiento, devuelve directamente `target`. */
export function useAnimatedNumber(target: number, from: number, duration = 1200): number {
  const animate = animationsSupported()
  const [value, setValue] = useState(animate ? from : target)
  const current = useRef(animate ? from : target)

  useEffect(() => {
    if (!animationsSupported()) {
      current.current = target
      setValue(target)
      return
    }
    const start = performance.now()
    const origin = current.current
    let frame = 0
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - k, 3)
      current.current = origin + (target - origin) * eased
      setValue(current.current)
      if (k < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration])

  return value
}
