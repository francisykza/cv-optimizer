import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, optimizeCv, type OptimizeParams } from '../services/api'
import type { OptimizeResponse } from '../types/api'

export type OptimizeStatus = 'idle' | 'loading' | 'success' | 'error'

/** Fases mostradas durante la espera. El backend no emite progreso (llegará con SSE en v2),
 *  así que avanzan con temporizadores y la última se mantiene hasta que llega la respuesta. */
export const LOADING_STEPS = [
  'Leyendo tu PDF…',
  'Analizando la oferta…',
  'Adaptando tu CV…',
  'Calculando la compatibilidad…',
] as const
const STEP_DELAYS_MS = [1200, 2500, 6000]

export function useOptimize() {
  const [status, setStatus] = useState<OptimizeStatus>('idle')
  const [result, setResult] = useState<OptimizeResponse | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [step, setStep] = useState(0)
  const controllerRef = useRef<AbortController | null>(null)
  const timersRef = useRef<number[]>([])

  const clearTimers = () => {
    timersRef.current.forEach((id) => window.clearTimeout(id))
    timersRef.current = []
  }

  useEffect(
    () => () => {
      clearTimers()
      controllerRef.current?.abort()
    },
    [],
  )

  const run = useCallback(async (params: Omit<OptimizeParams, 'signal'>) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    clearTimers()
    setStatus('loading')
    setError(null)
    setStep(0)
    let elapsed = 0
    STEP_DELAYS_MS.forEach((delay, index) => {
      elapsed += delay
      timersRef.current.push(window.setTimeout(() => setStep(index + 1), elapsed))
    })

    try {
      const data = await optimizeCv({ ...params, signal: controller.signal })
      setResult(data)
      setStatus('success')
    } catch (err) {
      if (controller.signal.aborted) return
      setError(err instanceof ApiError ? err : new ApiError('UNKNOWN', 'Ha ocurrido un error inesperado.', 0))
      setStatus('error')
    } finally {
      clearTimers()
    }
  }, [])

  const cancel = useCallback(() => {
    controllerRef.current?.abort()
    clearTimers()
    setStatus(result ? 'success' : 'idle')
  }, [result])

  const reset = useCallback(() => {
    controllerRef.current?.abort()
    clearTimers()
    setStatus('idle')
    setResult(null)
    setError(null)
  }, [])

  return { status, result, error, step, run, cancel, reset }
}
