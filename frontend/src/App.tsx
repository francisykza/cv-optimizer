import { CloudOff, Coffee } from 'lucide-react'
import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import toast, { Toaster } from 'react-hot-toast'

import { ApiKeySettings } from './components/ApiKeySettings'
import { ErrorAlert } from './components/ErrorAlert'
import { FileUploader } from './components/FileUploader'
import { JobDescription } from './components/JobDescription'
import { Footer } from './components/layout/Footer'
import { Header } from './components/layout/Header'
import { Hero } from './components/layout/Hero'
import { OptimizeButton } from './components/OptimizeButton'
import { ResultSkeleton } from './components/result/ResultSkeleton'
import { ResultViewer } from './components/result/ResultViewer'
import { useByokKey } from './hooks/useByokKey'
import { useCvMemory } from './hooks/useCvMemory'
import { useOptimize } from './hooks/useOptimize'
import { useServerStatus } from './hooks/useServerStatus'
import { JOB_OFFER_MAX_CHARS, JOB_OFFER_MIN_CHARS } from './lib/constants'
import { stripConsentNoise } from './lib/consentFilter'
import { consumeHandoff } from './lib/handoff'
import { motionAllowed } from './lib/motion'
import { hunterEnabled, useHashRoute } from './lib/route'
import type { AdjustmentLevel, OutputLanguage } from './types/api'

// El Buscador (Job Hunter) se carga aparte: quien solo usa el Optimizador no lo descarga.
const HunterView = lazy(() => import('./features/hunter/HunterView'))

export default function App() {
  const server = useServerStatus()
  const byok = useByokKey()
  const optimize = useOptimize()

  const [file, setFile] = useState<File | null>(null)
  const [jobOffer, setJobOffer] = useState('')
  const [language, setLanguage] = useState<OutputLanguage>('auto')
  const [adjustment, setAdjustment] = useState<AdjustmentLevel>('deep')
  const cvMemory = useCvMemory(file, setFile)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [offerBusy, setOfferBusy] = useState(false)

  const settingsRef = useRef<HTMLDivElement>(null)
  const resultsRef = useRef<HTMLElement>(null)
  const formRef = useRef<HTMLElement>(null)
  const [showHunter] = useState(hunterEnabled)
  const route = useHashRoute()
  const view = showHunter && route === 'buscar' ? 'buscar' : 'optimizar'

  // Oferta enviada desde el Buscador: rellena el paso 2 (se consume una sola vez).
  useEffect(() => {
    if (view !== 'optimizar') return
    const handoff = consumeHandoff()
    if (!handoff) return
    const replace =
      !jobOffer.trim() || window.confirm('Ya tienes una oferta escrita. ¿La sustituyo por la del Buscador?')
    if (!replace) return
    setJobOffer(stripConsentNoise(handoff.text))
    setLanguage(handoff.language ?? 'auto')
    toast.success(`Oferta de ${handoff.company} importada desde el Buscador`)
    // Tras el cambio de vista la portada aún se está montando: un scroll suave inmediato se corta.
    // setTimeout y no requestAnimationFrame: rAF no corre si el navegador deja de pintar la página.
    window.setTimeout(
      () => formRef.current?.scrollIntoView({ behavior: motionAllowed() ? 'smooth' : 'auto', block: 'start' }),
      300,
    )
    // Solo al entrar en la vista: jobOffer se lee en ese momento, no se vigila.
  }, [view])

  // Si el backend no tiene clave propia, BYOK pasa a ser obligatorio: se abre el panel.
  useEffect(() => {
    if (server.serverKeyAvailable === false) setSettingsOpen(true)
  }, [server.serverKeyAvailable])

  const loading = optimize.status === 'loading'
  const offerLength = jobOffer.trim().length
  const hasKey = byok.apiKey.trim().length > 0

  const disabledReason = !file
    ? 'Sube tu CV en PDF para continuar.'
    : offerLength < JOB_OFFER_MIN_CHARS
      ? `Pega la oferta completa (mínimo ${JOB_OFFER_MIN_CHARS} caracteres).`
      : offerLength > JOB_OFFER_MAX_CHARS
        ? 'La oferta es demasiado larga.'
        : offerBusy
          ? 'Espera a que terminemos de leer la oferta.'
          : server.serverKeyAvailable === false && !hasKey
            ? 'Introduce tu API key de Groq para continuar.'
            : server.state === 'waking'
              ? 'Esperando a que el servidor despierte…'
              : undefined

  const handleSubmit = () => {
    if (!file || disabledReason) return
    void optimize.run({
      file,
      // Los banners de cookies no llegan a la API (el backend vuelve a filtrarlos).
      jobOffer: stripConsentNoise(jobOffer),
      language,
      adjustment,
      apiKey: hasKey ? byok.apiKey.trim() : undefined,
    })
  }

  useEffect(() => {
    if (optimize.status === 'loading' || optimize.status === 'success') {
      resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [optimize.status])

  const showOwnKeySettings = () => {
    setSettingsOpen(true)
    settingsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <Header serverState={server.state} route={showHunter ? view : undefined} />

      <main className="flex-1">
        {view === 'buscar' ? (
          <Suspense
            fallback={
              <p className="mx-auto max-w-4xl px-4 pt-8 text-sm text-slate-500 sm:px-6">Cargando el Buscador…</p>
            }
          >
            <HunterView />
          </Suspense>
        ) : (
          <>
            <Hero />

            <section
              ref={formRef}
              id="optimizar"
              aria-label="Optimizar CV"
              className="mx-auto max-w-6xl scroll-mt-20 space-y-6 px-4 pb-12 sm:px-6"
            >
              {server.state === 'waking' && (
                <p className="flex animate-fade-in-up items-center gap-2.5 rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20">
                  <Coffee className="size-4 shrink-0" aria-hidden />
                  Despertando el servidor (plan gratuito): puede tardar hasta un minuto. Mientras, ve rellenando el
                  formulario.
                </p>
              )}
              {server.state === 'offline' && (
                <p className="flex animate-fade-in-up items-center gap-2.5 rounded-md bg-rose-50 px-4 py-3 text-sm text-rose-800 ring-1 ring-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/20">
                  <CloudOff className="size-4 shrink-0" aria-hidden />
                  No se puede contactar con el servidor. Inténtalo de nuevo en unos minutos.
                </p>
              )}

              <div ref={settingsRef}>
                <ApiKeySettings
                  apiKey={byok.apiKey}
                  onApiKeyChange={byok.setApiKey}
                  remember={byok.remember}
                  onRememberChange={byok.setRemember}
                  onClear={byok.clear}
                  open={settingsOpen}
                  onOpenChange={setSettingsOpen}
                  serverKeyAvailable={server.serverKeyAvailable}
                  disabled={loading}
                />
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <FileUploader
                  file={file}
                  onFileChange={cvMemory.onFileChosen}
                  disabled={loading}
                  memory={{
                    remember: cvMemory.remember,
                    status: cvMemory.status,
                    onRememberChange: cvMemory.setRemember,
                    onForget: cvMemory.forget,
                  }}
                />
                <JobDescription
                  value={jobOffer}
                  onChange={setJobOffer}
                  language={language}
                  onLanguageChange={setLanguage}
                  adjustment={adjustment}
                  onAdjustmentChange={setAdjustment}
                  disabled={loading}
                  onBusyChange={setOfferBusy}
                />
              </div>

              <OptimizeButton
                loading={loading}
                step={optimize.step}
                disabled={Boolean(disabledReason)}
                disabledReason={disabledReason}
                onClick={handleSubmit}
                onCancel={optimize.cancel}
              />

              {optimize.status === 'error' && optimize.error && (
                <ErrorAlert error={optimize.error} onRetry={handleSubmit} onUseOwnKey={showOwnKeySettings} />
              )}
            </section>

            {(loading || (optimize.status === 'success' && optimize.result)) && (
              <section
                ref={resultsRef}
                aria-label="Resultado"
                aria-busy={loading}
                className="scroll-mt-20 border-t border-slate-200/70 bg-white/40 py-12 dark:border-slate-800/70 dark:bg-slate-900/20"
              >
                <div className="mx-auto max-w-6xl px-4 sm:px-6">
                  {loading ? (
                    <ResultSkeleton />
                  ) : (
                    optimize.result && (
                      // La key reinicia las habilidades añadidas con cada resultado nuevo.
                      <ResultViewer
                        key={optimize.result.request_id ?? 'result'}
                        result={optimize.result}
                        onReset={optimize.reset}
                      />
                    )
                  )}
                </div>
              </section>
            )}
          </>
        )}
      </main>

      <Footer />
      <Toaster
        position="bottom-center"
        toastOptions={{ className: '!rounded-md !text-sm dark:!bg-slate-800 dark:!text-slate-100' }}
      />
    </div>
  )
}
