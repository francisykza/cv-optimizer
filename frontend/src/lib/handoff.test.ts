import { describe, expect, it } from 'vitest'

import { consumeHandoff, HANDOFF_KEY, HANDOFF_MAX_AGE_MS, writeHandoff } from './handoff'
import { parseRoute } from './route'

const TEXT = 'Junior AI Engineer — Acme (Málaga, híbrido)\n\n' + 'Python, LLM y RAG con mentoría. '.repeat(10)

describe('handoff Buscador → Optimizador', () => {
  it('escribe y consume una sola vez', () => {
    expect(writeHandoff({ text: TEXT, title: 'Junior AI Engineer', company: 'Acme', language: 'es' })).toBe(true)
    const handoff = consumeHandoff()
    expect(handoff).toMatchObject({ version: 1, company: 'Acme', language: 'es', text: TEXT })
    expect(sessionStorage.getItem(HANDOFF_KEY)).toBeNull()
    expect(consumeHandoff()).toBeNull()
  })

  it('caduca a los 10 minutos', () => {
    writeHandoff({ text: TEXT, title: 'x', company: 'Acme' })
    expect(consumeHandoff(Date.now() + HANDOFF_MAX_AGE_MS + 1)).toBeNull()
    expect(sessionStorage.getItem(HANDOFF_KEY)).toBeNull() // también se borra si no vale
  })

  it.each([
    ['texto demasiado corto', { text: 'corto' }],
    ['otra versión', { version: 2 }],
    ['idioma desconocido', { language: 'fr' }],
    ['sin empresa', { company: 42 }],
  ])('rechaza un traspaso con %s', (_, patch) => {
    const value = { version: 1, text: TEXT, title: 't', company: 'Acme', createdAt: Date.now(), ...patch }
    sessionStorage.setItem(HANDOFF_KEY, JSON.stringify(value))
    expect(consumeHandoff()).toBeNull()
  })

  it('ignora JSON corrupto', () => {
    sessionStorage.setItem(HANDOFF_KEY, '{roto')
    expect(consumeHandoff()).toBeNull()
  })
})

describe('parseRoute', () => {
  it.each([
    ['', 'optimizar'],
    ['#/buscar', 'buscar'],
    ['#buscar', 'buscar'],
    ['#/buscar?x=1', 'buscar'],
    ['#/optimizar', 'optimizar'],
    ['#optimizar', 'optimizar'],
    ['#/otra', 'optimizar'],
  ])('%s → %s', (hash, route) => {
    expect(parseRoute(hash)).toBe(route)
  })
})
