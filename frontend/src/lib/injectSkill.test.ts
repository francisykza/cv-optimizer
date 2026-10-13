import { describe, expect, it } from 'vitest'

import { injectSkill } from './injectSkill'

describe('injectSkill', () => {
  it('añade un elemento al final de una lista de habilidades', () => {
    const md = '# Ana\n\n## Habilidades\n- Excel\n- Contanet\n\n## Idiomas\n- Inglés B2'
    expect(injectSkill(md, 'SAP')).toBe('# Ana\n\n## Habilidades\n- Excel\n- Contanet\n- SAP\n\n## Idiomas\n- Inglés B2')
  })

  it('concatena al párrafo si las habilidades van separadas por comas', () => {
    const md = '## Competencias técnicas\nContanet, Excel, paquete Office.\n'
    expect(injectSkill(md, 'Carnet de conducir')).toBe(
      '## Competencias técnicas\nContanet, Excel, paquete Office, Carnet de conducir\n',
    )
  })

  it('respeta las subsecciones de habilidades', () => {
    const md = '## Skills\n### Backend\n* Python\n## Education\nBSc'
    expect(injectSkill(md, 'Docker')).toBe('## Skills\n### Backend\n* Python\n* Docker\n## Education\nBSc')
  })

  it('crea la sección si no existe, en el idioma del CV', () => {
    expect(injectSkill('# Ana\n\n## Experiencia\n- Algo', 'SAP')).toBe('# Ana\n\n## Experiencia\n- Algo\n\n## Habilidades\n\n- SAP\n')
    expect(injectSkill('# Ann\n\n## Experience\n- Stuff', 'SAP')).toMatch(/## Skills\n\n- SAP\n$/)
  })

  it('rellena una sección vacía', () => {
    expect(injectSkill('## Habilidades\n\n## Idiomas', 'SAP')).toBe('## Habilidades\n\n- SAP\n\n## Idiomas')
  })

  it('no duplica una habilidad que ya está en el CV', () => {
    const md = '## Habilidades\n- excel avanzado'
    expect(injectSkill(md, 'Excel')).toBe(md)
  })
})
