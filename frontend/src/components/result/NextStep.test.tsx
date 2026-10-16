import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { outbox } from '../../features/hunter/applications'
import { hunterApi, tokenStore } from '../../features/hunter/hunterClient'
import type { ApplicationDetail } from '../../features/hunter/types'
import type { OfferSource } from '../../lib/offerSource'
import { NextStep } from './NextStep'

const OFFER_TEXT = 'Data Analyst Junior\n\nBuscamos a alguien con SQL y Python para el equipo de datos.'
const FROM_HUNTER: OfferSource = {
  from: 'hunter',
  url: 'https://www.linkedin.com/jobs/view/1',
  title: 'Junior AI Engineer',
  company: 'Acme Labs',
  location: 'Málaga',
  jobId: 'job-1',
  matchScore: 82,
}

function renderStep(props: Partial<Parameters<typeof NextStep>[0]> = {}) {
  return render(
    <NextStep
      offer={FROM_HUNTER}
      offerText={OFFER_TEXT}
      markdown="# Francisco Muñoz"
      scoreBefore={54}
      scoreAfter={86}
      tracking
      {...props}
    />,
  )
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => vi.restoreAllMocks())

describe('Siguiente paso tras optimizar', () => {
  it('sin el Buscador, solo lleva de vuelta a la oferta', () => {
    renderStep({ tracking: false, offer: { from: 'url', url: 'https://www.infojobs.net/oferta/1' } })
    expect(screen.getByRole('link', { name: /Abrir la oferta en infojobs.net/ })).toHaveAttribute(
      'href',
      'https://www.infojobs.net/oferta/1',
    )
    expect(screen.queryByRole('button', { name: /Me he inscrito/ })).not.toBeInTheDocument()
  })

  it('sin enlace y sin Buscador no enseña nada', () => {
    const { container } = renderStep({ tracking: false, offer: null })
    expect(container).toBeEmptyDOMElement()
  })

  it('apunta la candidatura con la compatibilidad del CV que se envía', async () => {
    tokenStore.set('t', false)
    const create = vi.spyOn(hunterApi, 'createApplication').mockResolvedValue({ id: 'x' } as ApplicationDetail)
    const user = userEvent.setup()
    renderStep()
    await user.click(screen.getByRole('button', { name: /Me he inscrito con este CV/ }))
    expect(await screen.findByText(/Apuntada en tus candidaturas con un/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver mis candidaturas' })).toHaveAttribute('href', '#/buscar/candidaturas')
    expect(create).toHaveBeenCalledWith(
      't',
      expect.objectContaining({
        source: 'optimizer',
        job_id: 'job-1',
        company: 'Acme Labs',
        title: 'Junior AI Engineer',
        url: 'https://www.linkedin.com/jobs/view/1',
        ats_score_before: 54,
        ats_score_after: 86,
        judge_score: 82,
        offer_text: OFFER_TEXT,
        cv_markdown: '# Francisco Muñoz',
      }),
    )
    expect(screen.queryByRole('button', { name: /Me he inscrito/ })).not.toBeInTheDocument()
  })

  it('si no sabe la empresa, la pide (con el puesto adivinado) antes de apuntarla', async () => {
    const user = userEvent.setup()
    renderStep({ offer: { from: 'url', url: 'https://www.infojobs.net/oferta/1' } })
    await user.click(screen.getByRole('button', { name: /Me he inscrito con este CV/ }))
    expect(screen.getByLabelText('Puesto')).toHaveValue('Data Analyst Junior')
    await user.type(screen.getByLabelText('Empresa'), 'Datos S.L.')
    await user.click(screen.getByRole('button', { name: 'Guardar candidatura' }))
    // Sin token del Buscador: queda en este navegador hasta que la API responda.
    expect(await screen.findByText(/Apuntada en este navegador/)).toBeInTheDocument()
    expect(outbox.list()[0]).toMatchObject({ company: 'Datos S.L.', title: 'Data Analyst Junior', ats_score_after: 86 })
  })
})
