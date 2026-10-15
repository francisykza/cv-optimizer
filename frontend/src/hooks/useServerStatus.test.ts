import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { validateApiKey } from '../services/api'
import { useServerStatus } from './useServerStatus'

const healthy = () =>
  new Response(JSON.stringify({ status: 'ok', version: '0.1.0', server_llm_available: true }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('useServerStatus', () => {
  it('trata los fallos del arranque en frío como "despertando" y se recupera solo', async () => {
    // Render, mientras despierta, devuelve una página sin CORS: el navegador lo ve como error de red.
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(healthy())
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useServerStatus())
    await act(async () => {})
    expect(result.current.state).toBe('waking')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(result.current.state).toBe('waking')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(result.current.state).toBe('online')
    expect(result.current.serverKeyAvailable).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('solo marca "offline" tras agotar el margen de arranque', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))

    const { result } = renderHook(() => useServerStatus())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    expect(result.current.state).toBe('waking')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(70_000)
    })
    expect(result.current.state).toBe('offline')
  })

  it('pasa a operativo en cuanto cualquier petición a la API recibe respuesta', async () => {
    // /health falla durante más de 2 minutos (arranque en frío largo): la cabecera dice "no disponible".
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => useServerStatus())
    await act(async () => {
      await vi.advanceTimersByTimeAsync(125_000)
    })
    expect(result.current.state).toBe('offline')

    // Una petición real responde (aunque sea con un error de validación): el servidor está vivo.
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: 'INVALID_API_KEY_FORMAT', message: 'x' } }), { status: 422 }),
    )
    await act(async () => {
      await validateApiKey('gsk_x').catch(() => {})
    })
    expect(result.current.state).toBe('online')
  })
})
