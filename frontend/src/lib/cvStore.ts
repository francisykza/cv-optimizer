// Memoria local del CV, solo si el usuario la activa ("Recordar mi CV en este navegador").
// Se guarda el PDF en IndexedDB: el backend necesita el PDF (no el texto) y localStorage no admite
// archivos de hasta 5 MB. Nunca sale del navegador. Cualquier fallo (modo privado, cuota, datos
// del sitio bloqueados) se ignora: la app funciona igual, solo que sin memoria.

const DB_NAME = 'cv-optimizer'
const STORE = 'cv'
const KEY = 'current'

interface StoredCv {
  name: string
  type: string
  lastModified: number
  savedAt: number
  data: Blob
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

async function run<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await openDb()
  try {
    return await new Promise<T>((resolve, reject) => {
      const request = action(db.transaction(STORE, mode).objectStore(STORE))
      request.onsuccess = () => resolve(request.result as T)
      request.onerror = () => reject(request.error)
    })
  } finally {
    db.close()
  }
}

export async function saveCv(file: File): Promise<boolean> {
  try {
    const record: StoredCv = {
      name: file.name,
      type: file.type || 'application/pdf',
      lastModified: file.lastModified,
      savedAt: Date.now(),
      data: new Blob([file], { type: file.type || 'application/pdf' }),
    }
    await run('readwrite', (store) => store.put(record, KEY))
    return true
  } catch {
    return false
  }
}

export async function loadCv(): Promise<File | null> {
  try {
    const record = await run<StoredCv | undefined>('readonly', (store) => store.get(KEY))
    if (!record) return null
    return new File([record.data], record.name, { type: record.type, lastModified: record.lastModified })
  } catch {
    return null
  }
}

export async function forgetCv(): Promise<void> {
  try {
    await run('readwrite', (store) => store.delete(KEY))
  } catch {
    // Sin IndexedDB no hay nada que borrar.
  }
}
