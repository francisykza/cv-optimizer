import { describe, expect, it } from 'vitest'

import { appendBlock, cleanPastedText, insertText, isSingleUrl } from './pasteText'

describe('isSingleUrl', () => {
  it('detecta un único enlace http(s)', () => {
    expect(isSingleUrl('  https://www.infojobs.net/oferta/123?ref=abc \n')).toBe(true)
    expect(isSingleUrl('http://empresa.es/empleo')).toBe(true)
  })

  it('no confunde texto con enlaces ni otros esquemas con una URL', () => {
    expect(isSingleUrl('Oferta: https://empresa.es/empleo')).toBe(false)
    expect(isSingleUrl('https://a.es https://b.es')).toBe(false)
    expect(isSingleUrl('javascript:alert(1)')).toBe(false)
    expect(isSingleUrl('ftp://empresa.es')).toBe(false)
  })
})

describe('cleanPastedText', () => {
  it('quita espacios repetidos, tabulaciones y líneas en blanco múltiples', () => {
    const dirty = 'Inicio\t\tEmpleos\r\n\r\n\r\n\r\n  Auxiliar   administrativo  \n\n\n\nRequisitos​'
    expect(cleanPastedText(dirty)).toBe('Inicio Empleos\n\nAuxiliar administrativo\n\nRequisitos')
  })
})

describe('insertText', () => {
  it('sustituye la selección y deja el cursor tras lo pegado', () => {
    expect(insertText('Hola mundo', 5, 10, 'equipo')).toEqual({ value: 'Hola equipo', caret: 11, truncated: false })
  })

  it('recorta lo pegado para no superar el máximo', () => {
    const result = insertText('abc', 3, 3, 'x'.repeat(20), 10)
    expect(result.value).toBe('abc' + 'x'.repeat(7))
    expect(result.truncated).toBe(true)
  })
})

describe('appendBlock', () => {
  it('añade al final separado por una línea en blanco (varias capturas)', () => {
    expect(appendBlock('', 'Captura 1').value).toBe('Captura 1')
    expect(appendBlock('Captura 1\n', 'Captura 2').value).toBe('Captura 1\n\nCaptura 2')
  })

  it('nunca supera el máximo, ni siquiera con el separador', () => {
    const full = 'x'.repeat(10)
    expect(appendBlock(full, 'más', 10)).toEqual({ value: full, caret: 10, truncated: true })
    expect(appendBlock('x'.repeat(9), 'más', 10).value).toHaveLength(9)
  })
})
