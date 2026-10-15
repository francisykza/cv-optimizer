import { describe, expect, it } from 'vitest'

import { experienceEntries, experienceNote, injectExperience } from './injectSkill'
import { rehypeHighlightTerms } from './rehypeHighlightTerms'

const CV = [
  '# Ana García',
  '',
  '## Experiencia',
  '### Acme SL - Administrativa (2021 - 2023)',
  '- Facturación de clientes.',
  '- Atención telefónica.',
  '',
  '**Gestoría Sur - Auxiliar** (2023 - Actualidad)',
  '- Nóminas.',
  '',
  '## Habilidades',
  '- Excel',
].join('\n')

describe('experienceEntries', () => {
  it('encuentra los puestos con subtítulo o en negrita', () => {
    expect(experienceEntries(CV).map((e) => e.label)).toEqual([
      'Acme SL - Administrativa (2021 - 2023)',
      'Gestoría Sur - Auxiliar (2023 - Actualidad)',
    ])
  })
})

describe('injectExperience con destino', () => {
  it('añade la viñeta al final del puesto elegido y conserva el requisito para el ATS', () => {
    const [acme] = experienceEntries(CV)
    const result = injectExperience(CV, 'ChatGPT', 'automaticé respuestas a clientes', acme.line)
    expect(result).toContain('- Atención telefónica.\n- Automaticé respuestas a clientes (ChatGPT)\n\n**Gestoría Sur')
  })

  it('no repite el requisito si la frase ya lo menciona', () => {
    expect(experienceNote('SAP', 'usé SAP en facturación', '**Gestoría Sur - Auxiliar** (2023 - Actualidad)')).toBe(
      'Usé SAP en facturación',
    )
  })

  it('si el puesto ya no existe, la añade en Habilidades', () => {
    expect(injectExperience(CV, 'SAP', 'lo usé a diario', '### Puesto borrado')).toContain('- SAP: lo usé a diario')
  })
})

describe('rehypeHighlightTerms', () => {
  it('no marca como reformulado el texto de un título', () => {
    const tree = {
      type: 'root',
      children: [
        { type: 'element', tagName: 'h2', properties: {}, children: [{ type: 'text', value: 'Resumen profesional' }] },
        { type: 'element', tagName: 'p', properties: {}, children: [{ type: 'text', value: 'Resumen de logros' }] },
      ],
    }
    rehypeHighlightTerms({ groups: [{ kind: 'change', terms: ['Resumen'] }] })(tree)
    const [h2, p] = tree.children as { children: { type: string }[] }[]
    expect(h2.children.map((c) => c.type)).toEqual(['text'])
    expect(p.children[0].type).toBe('element')
  })
})
