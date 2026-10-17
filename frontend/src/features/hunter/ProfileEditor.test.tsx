import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { loadCv } from '../../lib/cvStore'
import { HunterError, hunterApi, normalizeProfile } from './hunterClient'
import { cleanProfile, profileChars, ProfileEditor } from './ProfileEditor'
import type { Profile, ProfileDraft } from './types'

vi.mock('../../lib/cvStore', () => ({ loadCv: vi.fn() }))

const TEXT = '## Habilidades técnicas\n- Python, LLM\n'
const NEW = '## Resumen\nJunior en IA aplicada.\n\n## Habilidades técnicas\n- Python, FastAPI\n'

function profile(overrides: Partial<Profile> = {}): Profile {
  return {
    text: TEXT,
    sha256: 'a'.repeat(64),
    chars: TEXT.trim().length,
    max_chars: 4000,
    terms: ['Python', 'LLM'],
    is_example: false,
    exists: true,
    updated_at: '2026-10-16T20:00:00+00:00',
    previous_text: null,
    outdated: { count: 0, from_cache: 0, days: 7, est_tokens: 0, est_minutes: 0, tokens_left_today: 74_000 },
    ...overrides,
  }
}

const OUTDATED = { count: 21, from_cache: 0, days: 7, est_tokens: 69_111, est_minutes: 17, tokens_left_today: 74_311 }

function renderEditor(onRejudgeStarted = vi.fn()) {
  render(<ProfileEditor token="t" refreshKey={0} onRejudgeStarted={onRejudgeStarted} />)
  return screen.findByLabelText('Texto de tu perfil')
}

beforeEach(() => {
  vi.mocked(loadCv).mockResolvedValue(null)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ProfileEditor', () => {
  it('muestra tu perfil, cuánto ocupa y lo que buscará el pre-score', async () => {
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile())
    const editor = await renderEditor()
    expect(editor).toHaveValue(TEXT)
    expect(screen.getByText(`${TEXT.trim().length} / 4000 caracteres`)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Términos de tu perfil' })).toHaveTextContent('PythonLLM')
    expect(screen.getByRole('button', { name: 'Guardar perfil' })).toBeDisabled() // sin cambios
    expect(screen.queryByText(/perfil de ejemplo/)).not.toBeInTheDocument()
  })

  it('avisa de que sigue siendo el perfil de ejemplo', async () => {
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile({ is_example: true }))
    await renderEditor()
    expect(screen.getByText(/Todavía es el perfil de ejemplo/)).toBeInTheDocument()
  })

  it('guarda con la huella del perfil leído y ofrece volver a juzgar las notas viejas', async () => {
    const user = userEvent.setup()
    const onRejudgeStarted = vi.fn()
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile())
    vi.spyOn(hunterApi, 'saveProfile').mockResolvedValue(
      profile({
        text: NEW,
        sha256: 'b'.repeat(64),
        terms: ['Python', 'FastAPI'],
        previous_text: TEXT,
        outdated: OUTDATED,
      }),
    )
    vi.spyOn(hunterApi, 'startRun').mockResolvedValue({ run_id: 'run-9', status: 'running' })
    const editor = await renderEditor(onRejudgeStarted)

    fireEvent.change(editor, { target: { value: NEW } })
    await user.click(screen.getByRole('button', { name: 'Guardar perfil' }))

    expect(hunterApi.saveProfile).toHaveBeenCalledWith('t', NEW, 'a'.repeat(64))
    expect(await screen.findByText('Guardado. Las ofertas nuevas ya se puntúan con este perfil.')).toBeInTheDocument()
    expect(
      screen.getByText('21 ofertas de los últimos 7 días tienen la nota de un perfil anterior.'),
    ).toBeInTheDocument()
    expect(screen.getByText(/unos 69\.111 tokens \(te quedan 74\.311 hoy\) y unos 17 minutos/)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Términos de tu perfil' })).toHaveTextContent('PythonFastAPI')

    await user.click(screen.getByRole('button', { name: 'Volver a juzgarlas' }))
    expect(hunterApi.startRun).toHaveBeenCalledWith('t', 'rejudge')
    expect(onRejudgeStarted).toHaveBeenCalledWith('run-9')
    expect(screen.getByText(/La IA las está volviendo a puntuar/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Volver a juzgarlas' })).not.toBeInTheDocument()
  })

  it('"Ahora no" deja las notas como están', async () => {
    const user = userEvent.setup()
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile({ outdated: OUTDATED }))
    const startRun = vi.spyOn(hunterApi, 'startRun')
    await renderEditor()
    await user.click(screen.getByRole('button', { name: 'Ahora no' }))
    expect(screen.queryByText(/tienen la nota de un perfil anterior/)).not.toBeInTheDocument()
    expect(startRun).not.toHaveBeenCalled()
  })

  it('avisa si hoy no llega el presupuesto para todas', async () => {
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile({ outdated: { ...OUTDATED, tokens_left_today: 20_000 } }))
    await renderEditor()
    expect(screen.getByText(/Hoy no llega para todas/)).toBeInTheDocument()
  })

  it('si el archivo cambió fuera de la web, deja elegir con cuál quedarse', async () => {
    const user = userEvent.setup()
    const hand = '## Resumen\nEditado a mano\n'
    vi.spyOn(hunterApi, 'profile')
      .mockResolvedValueOnce(profile())
      .mockResolvedValue(profile({ text: hand, sha256: 'c'.repeat(64) }))
    vi.spyOn(hunterApi, 'saveProfile')
      .mockRejectedValueOnce(new HunterError('PROFILE_CHANGED', 'Tu perfil ha cambiado', 409))
      .mockResolvedValueOnce(profile({ text: NEW, sha256: 'd'.repeat(64) }))
    const editor = await renderEditor()
    fireEvent.change(editor, { target: { value: NEW } })
    await user.click(screen.getByRole('button', { name: 'Guardar perfil' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('ha cambiado fuera de la web')

    await user.click(screen.getByRole('button', { name: 'Con el de la web' }))
    expect(hunterApi.saveProfile).toHaveBeenLastCalledWith('t', NEW, 'c'.repeat(64))
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
    expect(editor).toHaveValue(NEW)
  })

  it('"Con el del archivo" carga la versión editada a mano', async () => {
    const user = userEvent.setup()
    const hand = '## Resumen\nEditado a mano\n'
    vi.spyOn(hunterApi, 'profile')
      .mockResolvedValueOnce(profile())
      .mockResolvedValue(profile({ text: hand, sha256: 'c'.repeat(64) }))
    vi.spyOn(hunterApi, 'saveProfile').mockRejectedValue(new HunterError('PROFILE_CHANGED', 'cambiado', 409))
    const editor = await renderEditor()
    fireEvent.change(editor, { target: { value: NEW } })
    await user.click(screen.getByRole('button', { name: 'Guardar perfil' }))
    await user.click(await screen.findByRole('button', { name: 'Con el del archivo' }))
    await waitFor(() => expect(editor).toHaveValue(hand))
  })

  it('no deja guardar más de lo que lee el juez', async () => {
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile())
    const editor = await renderEditor()
    fireEvent.change(editor, { target: { value: 'x'.repeat(4001) } })
    expect(screen.getByText(/4001 \/ 4000 caracteres · te sobran 1/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guardar perfil' })).toBeDisabled()
    expect(editor).toHaveAttribute('aria-invalid', 'true')
  })

  it('enseña el error de la API al guardar', async () => {
    const user = userEvent.setup()
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile())
    vi.spyOn(hunterApi, 'saveProfile').mockRejectedValue(
      new HunterError('PROFILE_INVALID', 'El perfil está vacío: el juez no tendría con qué comparar las ofertas.', 422),
    )
    const editor = await renderEditor()
    fireEvent.change(editor, { target: { value: 'algo' } })
    await user.click(screen.getByRole('button', { name: 'Guardar perfil' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('El perfil está vacío')
  })

  it('crea un borrador desde el CV en PDF y no lo guarda hasta que se revisa', async () => {
    const user = userEvent.setup()
    const draft: ProfileDraft = {
      text: '## Resumen\nDesarrolladora junior.\n',
      chars: 32,
      sections: ['Resumen'],
      warnings: ['He dejado fuera la cabecera del CV (tu nombre y tus datos de contacto).'],
    }
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile())
    vi.spyOn(hunterApi, 'profileDraft').mockResolvedValue(draft)
    const save = vi.spyOn(hunterApi, 'saveProfile')
    const editor = await renderEditor()

    const pdf = new File(['%PDF-1.4'], 'cv-ana.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByLabelText('CV en PDF'), pdf)

    expect(hunterApi.profileDraft).toHaveBeenCalledWith('t', pdf)
    await waitFor(() => expect(editor).toHaveValue(draft.text))
    expect(screen.getByText('Borrador de cv-ana.pdf, aún sin guardar:')).toBeInTheDocument()
    expect(screen.getByText(/He dejado fuera la cabecera del CV/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guardar perfil' })).toBeEnabled()
    expect(save).not.toHaveBeenCalled()
  })

  it('usa el CV que recuerda este navegador', async () => {
    const user = userEvent.setup()
    const remembered = new File(['%PDF-1.4'], 'mi-cv.pdf', { type: 'application/pdf' })
    vi.mocked(loadCv).mockResolvedValue(remembered)
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile({ is_example: true }))
    vi.spyOn(hunterApi, 'profileDraft').mockResolvedValue({
      text: '## Resumen\nA\n',
      chars: 12,
      sections: [],
      warnings: [],
    })
    await renderEditor()
    await user.click(await screen.findByRole('button', { name: 'Usar mi-cv.pdf' }))
    expect(hunterApi.profileDraft).toHaveBeenCalledWith('t', remembered)
  })

  it('pregunta antes de sustituir cambios sin guardar por un borrador', async () => {
    const user = userEvent.setup()
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile())
    const draft = vi.spyOn(hunterApi, 'profileDraft')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const editor = await renderEditor()
    fireEvent.change(editor, { target: { value: NEW } })
    await user.upload(screen.getByLabelText('CV en PDF'), new File(['%PDF'], 'cv.pdf', { type: 'application/pdf' }))
    expect(confirm).toHaveBeenCalled()
    expect(draft).not.toHaveBeenCalled()
    expect(editor).toHaveValue(NEW)
  })

  it('recupera la versión anterior en el editor, sin guardarla', async () => {
    const user = userEvent.setup()
    const old = '## Resumen\nLa de antes\n'
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile({ previous_text: old }))
    const save = vi.spyOn(hunterApi, 'saveProfile')
    const editor = await renderEditor()
    await user.click(screen.getByRole('button', { name: 'Recuperar la versión anterior' }))
    expect(editor).toHaveValue(old)
    expect(save).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Descartar cambios' })).toBeInTheDocument()
  })

  it('lo escrito sin guardar sobrevive a cambiar de pestaña', async () => {
    vi.spyOn(hunterApi, 'profile').mockResolvedValue(profile())
    const first = render(<ProfileEditor token="t" refreshKey={0} onRejudgeStarted={vi.fn()} />)
    fireEvent.change(await screen.findByLabelText('Texto de tu perfil'), { target: { value: NEW } })
    first.unmount() // como al ir a "Para ti" y volver
    expect(await renderEditor()).toHaveValue(NEW)
    expect(screen.getByRole('button', { name: 'Descartar cambios' })).toBeInTheDocument()
  })
})

describe('texto del perfil', () => {
  it('se limpia como lo guardará la API y cuenta lo que lee el juez', () => {
    expect(cleanProfile('\n\n## Resumen  \r\nJunior \n\n')).toBe('## Resumen\nJunior')
    expect(profileChars('  😀 IA  \n')).toBe(4)
  })

  it('normalizeProfile rellena lo que falte', () => {
    const raw = { text: null, terms: null, outdated: null, previous_text: undefined } as unknown as Profile
    const p = normalizeProfile(raw)
    expect(p.text).toBe('')
    expect(p.terms).toEqual([])
    expect(p.previous_text).toBeNull()
    expect(p.outdated.count).toBe(0)
  })
})
