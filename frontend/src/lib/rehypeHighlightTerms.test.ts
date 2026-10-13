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

  it('prioriza los avisos ámbar sobre los cambios en verde', async () => {
    const { rehypeHighlightTerms } = await import('./rehypeHighlightTerms')
    const tree = { type: 'root', children: [{ type: 'text', value: 'Kubernetes y Diseñé' }] }
    rehypeHighlightTerms({
      groups: [
        { kind: 'change', terms: ['Kubernetes', 'Diseñé'] },
        { kind: 'ungrounded', terms: ['kubernetes'] },
      ],
    })(tree)
    const marks = tree.children
      .filter((n): n is { type: 'element'; properties: Record<string, string> } & typeof n => n.type === 'element')
      .map((n) => (n as unknown as { properties: Record<string, string> }).properties)
    expect(marks).toEqual([
      { dataTerm: 'kubernetes', dataKind: 'ungrounded' },
      { dataTerm: 'Diseñé', dataKind: 'change' },
    ])
  })

  it('devuelve null sin términos', () => {
    expect(buildTermsRegExp(['', '  '])).toBeNull()
  })
})
