import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'
import { loadMasters, logEvent } from '../lib/api'
import type { Branch, Dealer, Named, Profile, Settings } from '../lib/types'
import { DEFAULT_SETTINGS } from '../lib/types'

export type Masters = { branches: Branch[]; manufacturers: Named[]; dealers: Dealer[]; profiles: Profile[]; settings: Settings }
type Phase = 'loading' | 'signedOut' | 'setPassword' | 'mfaEnroll' | 'mfaVerify' | 'noProfile' | 'ready'

type Ctx = {
  phase: Phase; session: Session | null; profile: Profile | null; masters: Masters
  refreshMasters: () => Promise<void>; signOut: () => Promise<void>; recheck: () => Promise<void>
  userName: (id: string | null) => string
}
const empty: Masters = { branches: [], manufacturers: [], dealers: [], profiles: [], settings: DEFAULT_SETTINGS }
const AuthCtx = createContext<Ctx | null>(null)
export const useAuth = () => { const c = useContext(AuthCtx); if (!c) throw new Error('AuthProvider外です'); return c }

// 招待・パスワード再設定リンクから来た場合はパスワード設定を先に行う(URLのハッシュはsupabase-jsが消費する前に判定)
const arrivedViaLink = /type=(invite|recovery)/.test(window.location.hash)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>('loading')
  const [session, setSession] = useState<Session | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [masters, setMasters] = useState<Masters>(empty)
  const needPw = useRef(arrivedViaLink)
  const loggedLogin = useRef(false)

  const refreshMasters = useCallback(async () => { setMasters(await loadMasters()) }, [])

  const evaluate = useCallback(async (s: Session | null) => {
    setSession(s)
    if (!s) { setProfile(null); setPhase('signedOut'); loggedLogin.current = false; return }
    if (needPw.current) { setPhase('setPassword'); return }
    const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel()
    if (aal?.currentLevel !== 'aal2') { setPhase(aal?.nextLevel === 'aal2' ? 'mfaVerify' : 'mfaEnroll'); return }
    const { data: p } = await supabase.from('profiles').select('*').eq('user_id', s.user.id).maybeSingle()
    if (!p || !p.active) { setPhase('noProfile'); return }
    setProfile(p as Profile)
    try { await refreshMasters() } catch { /* 画面側でエラー表示 */ }
    if (!loggedLogin.current) { loggedLogin.current = true; void logEvent('login') }
    setPhase('ready')
  }, [refreshMasters])

  useEffect(() => {
    void supabase.auth.getSession().then(({ data }) => evaluate(data.session))
    const { data: sub } = supabase.auth.onAuthStateChange((event, s) => {
      if (event === 'PASSWORD_RECOVERY') needPw.current = true
      if (event === 'TOKEN_REFRESHED') { setSession(s); return }
      // コールバック内で await する supabase 呼び出しはデッドロックし得るため setTimeout で逃がす
      setTimeout(() => void evaluate(s), 0)
    })
    return () => sub.subscription.unsubscribe()
  }, [evaluate])

  const signOut = useCallback(async () => {
    try { await logEvent('logout') } catch { /* ログアウトは継続 */ }
    await supabase.auth.signOut()
  }, [])

  const recheck = useCallback(async () => {
    needPw.current = false
    const { data } = await supabase.auth.getSession()
    await evaluate(data.session)
  }, [evaluate])

  const userName = useCallback((id: string | null) => masters.profiles.find((p) => p.user_id === id)?.display_name ?? '(不明)', [masters.profiles])
  const value = useMemo(() => ({ phase, session, profile, masters, refreshMasters, signOut, recheck, userName }),
    [phase, session, profile, masters, refreshMasters, signOut, recheck, userName])
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export const canWrite = (p: Profile | null) => p?.role === 'admin' || p?.role === 'branch_staff'
export const isAdmin = (p: Profile | null) => p?.role === 'admin'
