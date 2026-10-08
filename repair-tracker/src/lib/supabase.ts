import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined
const anon = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined
export const configured = Boolean(url && anon)

// セッショントークンのみをタブ単位の sessionStorage に保持(localStorage は使わない)。
// 個人情報はここに保存しない。ブラウザを閉じるとログアウトされる。
/* eslint-disable no-restricted-globals, no-restricted-properties */
const tabStorage = {
  getItem: (k: string) => { try { return window.sessionStorage.getItem(k) } catch { return null } },
  setItem: (k: string, v: string) => { try { window.sessionStorage.setItem(k, v) } catch { /* 無視 */ } },
  removeItem: (k: string) => { try { window.sessionStorage.removeItem(k) } catch { /* 無視 */ } },
}
/* eslint-enable no-restricted-globals, no-restricted-properties */

export const supabase = createClient(url ?? 'http://localhost:54321', anon ?? 'missing', {
  auth: { storage: tabStorage, persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
})
