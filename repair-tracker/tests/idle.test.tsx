import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useIdleLogout } from '../src/hooks/useIdleLogout'

describe('自動ログアウト', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())
  it('無操作が指定時間続くとログアウトされる', () => {
    const out = vi.fn()
    renderHook(() => useIdleLogout(30, out, true))
    vi.advanceTimersByTime(29 * 60_000); expect(out).not.toHaveBeenCalled()
    vi.advanceTimersByTime(2 * 60_000); expect(out).toHaveBeenCalledTimes(1)
  })
  it('操作があるとタイマーがリセットされる', () => {
    const out = vi.fn()
    renderHook(() => useIdleLogout(30, out, true))
    vi.advanceTimersByTime(25 * 60_000); window.dispatchEvent(new Event('keydown'))
    vi.advanceTimersByTime(25 * 60_000); expect(out).not.toHaveBeenCalled()
    vi.advanceTimersByTime(6 * 60_000); expect(out).toHaveBeenCalledTimes(1)
  })
  it('無効時は動作しない', () => {
    const out = vi.fn()
    renderHook(() => useIdleLogout(1, out, false)); vi.advanceTimersByTime(10 * 60_000); expect(out).not.toHaveBeenCalled()
  })
})
