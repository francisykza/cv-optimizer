import { useCallback, useEffect, useState } from 'react'

import { forgetCv, loadCv, saveCv } from '../lib/cvStore'

/** 'restored': se recuperó al abrir la página. 'saved': se acaba de guardar. 'error': el navegador
 *  no permite guardarlo (modo privado, cuota...). */
export type CvMemoryStatus = 'off' | 'saved' | 'restored' | 'error'

/**
 * Memoria local del CV, desactivada por defecto. Si el usuario la activa, el PDF se guarda en este
 * navegador (IndexedDB) y se recupera al volver. "Olvidar" o quitar el archivo la borran.
 */
export function useCvMemory(file: File | null, setFile: (update: (prev: File | null) => File | null) => void) {
  const [remember, setRemember] = useState(false)
  const [status, setStatus] = useState<CvMemoryStatus>('off')

  // Al abrir la página: si hay un CV guardado, se recupera (sin pisar uno elegido mientras tanto).
  useEffect(() => {
    let cancelled = false
    void loadCv().then((stored) => {
      if (cancelled || !stored) return
      setFile((prev) => prev ?? stored)
      setRemember(true)
      setStatus('restored')
    })
    return () => {
      cancelled = true
    }
  }, [setFile])

  const persist = useCallback(async (candidate: File) => {
    setStatus((await saveCv(candidate)) ? 'saved' : 'error')
  }, [])

  const setRememberAndSave = useCallback(
    (on: boolean) => {
      setRemember(on)
      if (on && file) void persist(file)
      if (!on) {
        setStatus('off')
        void forgetCv()
      }
    },
    [file, persist],
  )

  /** El usuario elige otro PDF (o lo quita) con la memoria activa: se guarda el nuevo o se borra. */
  const onFileChosen = useCallback(
    (next: File | null) => {
      setFile(() => next)
      if (!remember) return
      if (next) void persist(next)
      else setRememberAndSave(false)
    },
    [remember, persist, setFile, setRememberAndSave],
  )

  return { remember, status, setRemember: setRememberAndSave, forget: () => setRememberAndSave(false), onFileChosen }
}
