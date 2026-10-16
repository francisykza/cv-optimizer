import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { flushOutbox, newApplicationId, outbox, registerApplication } from './applications'
import { HunterError, hunterApi, tokenStore } from './hunterClient'
import { takePairCode } from './pairing'
import type { ApplicationDetail, ApplicationInput } from './types'

const input = (id: string): ApplicationInput => ({ id, company: 'Acme', title: 'Dev', source: 'optimizer' })
const stored = { id: 'x' } as ApplicationDetail

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  window.location.hash = ''
})

describe('candidaturas desde el navegador', () => {
  it('genera ids que la API acepta', () => {
    const id = newApplicationId()
    expect(id).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
    expect(newApplicationId()).not.toBe(id)
  })

  it('con la API encendida, se guarda directamente', async () => {
    tokenStore.set('t', false)
    const create = vi.spyOn(hunterApi, 'createApplication').mockResolvedValue(stored)
    expect(await registerApplication(input('a1b2c3d4'))).toBe('saved')
    expect(create).toHaveBeenCalledWith('t', input('a1b2c3d4'))
    expect(outbox.list()).toEqual([])
  })

  it('sin token o sin conexión, espera en la cola del navegador', async () => {
    expect(await registerApplication(input('sin-token-1'))).toBe('queued')
    tokenStore.set('t', false)
    vi.spyOn(hunterApi, 'createApplication').mockRejectedValue(new HunterError('OFFLINE', 'no', 0))
    expect(await registerApplication(input('apagada-1'))).toBe('queued')
    expect(outbox.list().map((i) => i.id)).toEqual(['sin-token-1', 'apagada-1'])
  })

  it('una candidatura inválida no se encola: se avisa', async () => {
    tokenStore.set('t', false)
    vi.spyOn(hunterApi, 'createApplication').mockRejectedValue(new HunterError('VALIDATION_ERROR', 'mal', 422))
    await expect(registerApplication(input('invalida-1'))).rejects.toThrow('mal')
    expect(outbox.list()).toEqual([])
  })

  it('la cola se vacía al volver la conexión y se detiene si vuelve a fallar', async () => {
    outbox.add(input('uno-1234'))
    outbox.add(input('dos-1234'))
    outbox.add(input('tres-1234'))
    outbox.add(input('dos-1234')) // reencolar la misma no la duplica
    const create = vi
      .spyOn(hunterApi, 'createApplication')
      .mockResolvedValueOnce(stored)
      .mockRejectedValueOnce(new HunterError('VALIDATION_ERROR', 'mal', 422)) // inválida: se descarta
      .mockRejectedValueOnce(new HunterError('OFFLINE', 'no', 0)) // apagada: se reintenta luego
    expect(await flushOutbox('t')).toBe(1)
    expect(create).toHaveBeenCalledTimes(3)
    expect(outbox.list().map((i) => i.id)).toEqual(['tres-1234'])
  })
})

describe('código de emparejado', () => {
  it('se lee una vez y desaparece de la dirección', () => {
    window.history.replaceState(null, '', '/?hunter=1#/buscar?pair=abc123def')
    expect(takePairCode()).toBe('abc123def')
    expect(window.location.hash).toBe('#/buscar')
    expect(window.location.search).toBe('')
    expect(takePairCode()).toBeNull()
  })
})
