import { describe, expect, it } from 'vitest'

import { consumeHandoff, HANDOFF_KEY, HANDOFF_MAX_AGE_MS, writeHandoff } from './handoff'
import { guessTitle, offerHost } from './offerSource'
import { parseRoute, routeSection } from './route'

const TEXT = 'Junior AI Engineer — Acme (Málaga, híbrido)\n\n' + 'Python, LLM y RAG con mentoría. '.repeat(10)

describe('handoff Buscador → Optimizador', () => {
  it('escribe y consume una sola vez', () => {
    expect(writeHandoff({ text: TEXT, title: 'Junior AI Engineer', company: 'Acme', language: 'es' })).toBe(true)
    const handoff = consumeHandoff()
    expect(handoff).toMatchObject({ version: 1, company: 'Acme', language: 'es', text: TEXT })
    expect(sessionStorage.getItem(HANDOFF_KEY)).toBeNull()
    expect(consumeHandoff()).toBeNull()
  })

  it('lleva la ficha del Buscador para volver a la oferta y apuntar la candidatura', () => {
    writeHandoff({
      text: TEXT,
      title: 'Junior AI Engineer',
      company: 'Acme',
      sourceUrl: 'https://www.linkedin.com/jobs/view/1',
      location: 'Málaga',
      jobId: 'job-1',
      matchScore: 86,
    })
    expect(consumeHandoff()).toMatchObject({ jobId: 'job-1', matchScore: 86, location: 'Málaga' })
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
    ['una nota imposible', { matchScore: 140 }],
    ['un id que no es texto', { jobId: 7 }],
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

describe('routeSection', () => {
  it.each([
    ['#/buscar/candidaturas', 'candidaturas'],
    ['#/buscar/candidaturas?x=1', 'candidaturas'],
    ['#/buscar?pair=abc', null],
    ['#/buscar', null],
    ['', null],
  ])('%s → %s', (hash, section) => {
    expect(routeSection(hash)).toBe(section)
  })
})

describe('origen de la oferta', () => {
  it('enseña solo el dominio del enlace', () => {
    expect(offerHost('https://www.linkedin.com/jobs/view/1?trk=x')).toBe('linkedin.com')
    expect(offerHost('no es una url')).toBe('no es una url')
  })

  it('adivina el puesto por la primera línea', () => {
    expect(guessTitle(TEXT)).toBe('Junior AI Engineer')
    expect(guessTitle('\n\n  Data Analyst Junior\nEmpresa: Acme')).toBe('Data Analyst Junior')
    expect(guessTitle('ok')).toBe('')
    expect(guessTitle('x'.repeat(200))).toBe('')
  })
})
