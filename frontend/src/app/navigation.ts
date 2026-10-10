import { useSyncExternalStore } from 'react'
import { normalizePath } from './routes'

function subscribe(listener: () => void) {
  window.addEventListener('hashchange', listener)
  return () => window.removeEventListener('hashchange', listener)
}

export function usePath() {
  return useSyncExternalStore(subscribe, () => normalizePath(window.location.hash), () => '/')
}

export function navigate(path: string, replace = false) {
  if (replace) {
    window.history.replaceState(null, '', `#${path}`)
    window.dispatchEvent(new Event('hashchange'))
  } else window.location.hash = path
}
