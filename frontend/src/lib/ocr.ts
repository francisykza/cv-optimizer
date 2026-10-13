// OCR de capturas de pantalla en el navegador con tesseract.js.
// Se carga con import() solo al pegar una imagen: no pesa en la carga inicial, la captura nunca
// sale del navegador y no consume tokens de Groq. El motor (WASM) y los idiomas se descargan de
// cdn.jsdelivr.net la primera vez (ver la CSP en vercel.json) y el navegador los cachea.

export interface OcrProgress {
  phase: 'loading' | 'recognizing'
  /** 0 a 1 */
  progress: number
}

export async function recognizeImage(image: Blob, onProgress?: (p: OcrProgress) => void): Promise<string> {
  const { createWorker } = await import('tesseract.js')
  const worker = await createWorker(['spa', 'eng'], undefined, {
    logger: (m: { status: string; progress: number }) => {
      onProgress?.({ phase: m.status === 'recognizing text' ? 'recognizing' : 'loading', progress: m.progress })
    },
  })
  try {
    const { data } = await worker.recognize(image)
    return data.text
  } finally {
    await worker.terminate()
  }
}
