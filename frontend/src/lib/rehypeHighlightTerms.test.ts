import { describe, expect, it } from 'vitest'

import { buildTermsRegExp } from './rehypeHighlightTerms'

describe('buildTermsRegExp', () => {
  it('solo coincide con palabras completas', () => {
    const re = buildTermsRegExp(['45', 'Java'])!
    expect('un 45% más'.match(re)).toEqual(['45'])
    expect('en 2045 y 145'.match(re)).toBeNull()
    expect('JavaScript'.match(re)).toBeNull()
  })

  it('prioriza los términos más largos y escapa caracteres especiales', () => {
    const re = buildTermsRegExp(['C++', 'Universidad', 'Universidad de Oxford'])!
    expect('Universidad de Oxford y C++'.match(re)).toEqual(['Universidad de Oxford', 'C++'])
  })

  it('devuelve null sin términos', () => {
    expect(buildTermsRegExp(['', '  '])).toBeNull()
  })
})
