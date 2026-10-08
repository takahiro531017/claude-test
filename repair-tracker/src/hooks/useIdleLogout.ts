import { useEffect } from 'react'

/** 無操作が minutes 分続いたら onTimeout(自動ログアウト) */
export function useIdleLogout(minutes: number, onTimeout: () => void, enabled: boolean) {
  useEffect(() => {
    if (!enabled) return
    let t = window.setTimeout(onTimeout, minutes * 60_000)
    const reset = () => { window.clearTimeout(t); t = window.setTimeout(onTimeout, minutes * 60_000) }
    const evs = ['mousemove', 'keydown', 'touchstart', 'click', 'scroll'] as const
    evs.forEach((e) => window.addEventListener(e, reset, { passive: true }))
    return () => { window.clearTimeout(t); evs.forEach((e) => window.removeEventListener(e, reset)) }
  }, [minutes, onTimeout, enabled])
}
