/**
 * Código de emparejado que trae el acceso directo (SPEC §18.2): `?hunter=1#/buscar?pair=CÓDIGO`.
 * Se lee una vez y se quita de la barra de direcciones; de todos modos solo sirve una vez y caduca
 * a los 2 minutos.
 */
export function takePairCode(): string | null {
  const query = window.location.hash.split('?')[1] ?? ''
  const code = new URLSearchParams(query).get('pair')
  if (!code) return null
  try {
    const url = new URL(window.location.href)
    url.searchParams.delete('hunter') // la bandera ya quedó guardada al cargar la app
    url.hash = '#/buscar'
    window.history.replaceState(window.history.state, '', url)
  } catch {
    // Sin History API (entornos raros): el código caduca solo.
  }
  return code
}
