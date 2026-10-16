/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_REPO_URL?: string
  /** "true" muestra la pestaña Buscador (API local del Job Hunter). */
  readonly VITE_HUNTER_ENABLED?: string
  /** Por defecto http://127.0.0.1:8001 */
  readonly VITE_HUNTER_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
