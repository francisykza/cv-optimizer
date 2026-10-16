import { HunterError, hunterApi, tokenStore } from './hunterClient'
import type { ApplicationInput, ApplicationStatus } from './types'

/**
 * Candidaturas desde el navegador (SPEC §18.4). Se guardan en la API local del Buscador; si está
 * apagada, esperan en una cola de este navegador y se envían solas en cuanto vuelve a responder.
 * El id lo pone el navegador: reenviar una candidatura nunca la duplica.
 */

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  applied: 'Enviada',
  in_process: 'En proceso',
  interview: 'Entrevista',
  offer: 'Oferta',
  rejected: 'Rechazada',
  no_response: 'Sin respuesta',
  withdrawn: 'Retirada',
}

export function newApplicationId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID().replaceAll('-', '')
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 12)}`
}

const OUTBOX_KEY = 'cvopt:applications-outbox'

function readOutbox(): ApplicationInput[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(OUTBOX_KEY) ?? '[]')
    return Array.isArray(parsed) ? (parsed as ApplicationInput[]) : []
  } catch {
    return []
  }
}

function writeOutbox(items: ApplicationInput[]): void {
  try {
    if (items.length) localStorage.setItem(OUTBOX_KEY, JSON.stringify(items))
    else localStorage.removeItem(OUTBOX_KEY)
  } catch {
    // Almacenamiento lleno o bloqueado: no hay dónde guardarla.
    throw new Error('No se ha podido guardar la candidatura en este navegador.')
  }
}

export const outbox = {
  list: readOutbox,
  /** Reencolar la misma candidatura la actualiza en su sitio (el orden es el de llegada). */
  add(item: ApplicationInput): void {
    const items = readOutbox()
    const at = items.findIndex((i) => i.id === item.id)
    if (at >= 0) items[at] = item
    else items.push(item)
    writeOutbox(items)
  },
  remove(id: string): void {
    writeOutbox(readOutbox().filter((i) => i.id !== id))
  },
}

/** Envía lo que esperaba en la cola. Devuelve cuántas se han guardado. Para en el primer fallo de
 *  conexión (se reintentará); una candidatura que la API rechaza por inválida se descarta. */
export async function flushOutbox(token: string): Promise<number> {
  let saved = 0
  for (const item of readOutbox()) {
    try {
      await hunterApi.createApplication(token, item)
      outbox.remove(item.id)
      saved++
    } catch (err) {
      if (err instanceof HunterError && err.status === 422) {
        outbox.remove(item.id)
        continue
      }
      break
    }
  }
  return saved
}

/** 'saved': ya está en tus candidaturas · 'queued': espera en este navegador a que vuelva la API. */
export async function registerApplication(input: ApplicationInput): Promise<'saved' | 'queued'> {
  const token = tokenStore.get()
  if (token) {
    try {
      await hunterApi.createApplication(token, input)
      return 'saved'
    } catch (err) {
      if (err instanceof HunterError && err.status === 422) throw err
    }
  }
  outbox.add(input)
  return 'queued'
}
