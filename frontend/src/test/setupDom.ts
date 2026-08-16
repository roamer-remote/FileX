;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true

function createMemoryStorage(): Storage {
  const storage = new Map<string, string>()
  return {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => {
      storage.set(key, value)
    },
    removeItem: (key: string) => {
      storage.delete(key)
    },
    clear: () => {
      storage.clear()
    },
    get length() {
      return storage.size
    },
    key: (index: number) => Array.from(storage.keys())[index] ?? null,
  }
}

const localStorageMock = createMemoryStorage()
const sessionStorageMock = createMemoryStorage()

Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  writable: true,
  value: localStorageMock,
})

Object.defineProperty(globalThis, 'sessionStorage', {
  configurable: true,
  writable: true,
  value: sessionStorageMock,
})

if (typeof window !== 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })

  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    writable: true,
    value: localStorageMock,
  })

  Object.defineProperty(window, 'sessionStorage', {
    configurable: true,
    writable: true,
    value: sessionStorageMock,
  })

  const nativeGetComputedStyle = window.getComputedStyle.bind(window)
  window.getComputedStyle = (elt: Element, pseudoElt?: string | null) => {
    if (pseudoElt) {
      return nativeGetComputedStyle(elt)
    }
    return nativeGetComputedStyle(elt, pseudoElt)
  }
}
