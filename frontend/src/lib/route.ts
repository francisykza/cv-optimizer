import { useEffect, useState } from 'react'

/** Vistas de la app. Sin react-router: dos vistas no lo justifican (SPEC del hunter, D4). */
export type Route = 'optimizar' | 'buscar'

export function parseRoute(hash: string): Route {
  return hash.replace(/^#\/?/, '').split(/[/?]/)[0] === 'buscar' ? 'buscar' : 'optimizar'
}

/** Sección dentro de una vista: `#/buscar/candidaturas` → 'candidaturas'. */
export function routeSection(hash: string = window.location.hash): string | null {
  return hash.replace(/^#\/?/, '').split('?')[0].split('/')[1] || null
}

export function navigate(route: Route): void {
  window.location.hash = route === 'buscar' ? '#/buscar' : '#/optimizar'
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

const HUNTER_FLAG = 'cvopt:hunter'

/**
 * La pestaña "Buscador" solo se ve en local (VITE_HUNTER_ENABLED=true) o tras abrir la web una vez
 * con ?hunter=1 (se recuerda en este navegador). En la web pública queda oculta para los visitantes.
 */
export function hunterEnabled(): boolean {
  if (import.meta.env.VITE_HUNTER_ENABLED === 'true') return true
  try {
    const params = new URLSearchParams(window.location.search)
    if (params.get('hunter') === '1') localStorage.setItem(HUNTER_FLAG, '1')
    if (params.get('hunter') === '0') localStorage.removeItem(HUNTER_FLAG)
    return localStorage.getItem(HUNTER_FLAG) === '1'
  } catch {
    return false
  }
}
