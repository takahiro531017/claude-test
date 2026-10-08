import { useEffect, useRef, useState } from 'react'
import { supabase } from '../lib/supabase'

/** repairs の変更を購読し、変化があれば onChange(デバウンス付き)。RLSによりユーザーに見える行のみ届く */
export function useRepairsRealtime(onChange: () => void, repairId?: string) {
  const cb = useRef(onChange)
  cb.current = onChange
  const [connected, setConnected] = useState(false)
  useEffect(() => {
    let timer: number | undefined
    const ch = supabase.channel(`repairs-${repairId ?? 'all'}-${Math.random().toString(36).slice(2)}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'repairs', ...(repairId ? { filter: `id=eq.${repairId}` } : {}) },
        () => { window.clearTimeout(timer); timer = window.setTimeout(() => cb.current(), 300) })
      .subscribe((s) => setConnected(s === 'SUBSCRIBED'))
    return () => { window.clearTimeout(timer); void supabase.removeChannel(ch) }
  }, [repairId])
  return connected
}

/** 同じ案件を開いている他ユーザー(表示名のみ共有。個人情報は載せない) */
export function useEditors(repairId: string, myId: string, myName: string): string[] {
  const [names, setNames] = useState<string[]>([])
  useEffect(() => {
    const ch = supabase.channel(`presence-${repairId}`, { config: { presence: { key: myId } } })
    ch.on('presence', { event: 'sync' }, () => {
      const st = ch.presenceState() as Record<string, { name: string }[]>
      setNames(Object.entries(st).filter(([k]) => k !== myId).map(([, v]) => v[0]?.name).filter(Boolean))
    }).subscribe(async (s) => { if (s === 'SUBSCRIBED') await ch.track({ name: myName }) })
    return () => { void supabase.removeChannel(ch) }
  }, [repairId, myId, myName])
  return names
}
