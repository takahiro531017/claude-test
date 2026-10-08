import { useEffect, useState, type FormEvent } from 'react'
import { supabase, configured } from '../lib/supabase'
import { useAuth } from '../auth/AuthContext'
import { Banner } from '../components/ui'

const Shell = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <main className="auth-shell"><h1>修理品管理システム</h1><h2>{title}</h2>{children}</main>
)

export function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('')
    const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
    // 失敗理由は区別せず表示(アカウント存在の推測を防ぐ)。試行回数の制限は Supabase Auth 側で実施
    if (error) setErr(error.status === 429 ? '試行回数が多すぎます。しばらく待ってから再度お試しください' : 'メールアドレスまたはパスワードが正しくありません')
    setBusy(false)
  }
  return (
    <Shell title="ログイン">
      {!configured && <Banner kind="error">接続先が未設定です(.env の VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY)。</Banner>}
      <form onSubmit={submit} className="stack">
        <label className="field"><span className="field-label">メールアドレス</span>
          <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
        <label className="field"><span className="field-label">パスワード</span>
          <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {err && <Banner kind="error">{err}</Banner>}
        <button className="btn primary big" disabled={busy}>{busy ? '確認中…' : 'ログイン'}</button>
        <p className="hint">アカウントは管理者が招待します。自己登録はできません。</p>
      </form>
    </Shell>
  )
}

export function SetPassword() {
  const { recheck } = useAuth()
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState(''); const [err, setErr] = useState('')
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (pw.length < 12) return setErr('パスワードは12文字以上にしてください')
    if (pw !== pw2) return setErr('確認用パスワードが一致しません')
    const { error } = await supabase.auth.updateUser({ password: pw })
    if (error) return setErr('パスワードを設定できませんでした。より推測されにくい文字列にしてください')
    history.replaceState(null, '', window.location.pathname)
    await recheck()
  }
  return (
    <Shell title="パスワードの設定">
      <form onSubmit={submit} className="stack">
        <label className="field"><span className="field-label">新しいパスワード(12文字以上)</span>
          <input type="password" autoComplete="new-password" minLength={12} required value={pw} onChange={(e) => setPw(e.target.value)} /></label>
        <label className="field"><span className="field-label">確認のため再入力</span>
          <input type="password" autoComplete="new-password" minLength={12} required value={pw2} onChange={(e) => setPw2(e.target.value)} /></label>
        {err && <Banner kind="error">{err}</Banner>}
        <button className="btn primary big">設定する</button>
      </form>
    </Shell>
  )
}

export function MfaEnroll() {
  const { recheck, signOut } = useAuth()
  const [factor, setFactor] = useState<{ id: string; qr: string; secret: string } | null>(null)
  const [code, setCode] = useState(''); const [err, setErr] = useState('')
  useEffect(() => {
    void (async () => {
      // 未検証の古い登録が残っていれば削除してから登録し直す
      const { data: fs } = await supabase.auth.mfa.listFactors()
      for (const f of fs?.all ?? []) if (f.status === 'unverified') await supabase.auth.mfa.unenroll({ factorId: f.id })
      const { data, error } = await supabase.auth.mfa.enroll({ factorType: 'totp', friendlyName: '認証アプリ' })
      if (error || !data || data.type !== 'totp') return setErr('多要素認証の準備に失敗しました')
      setFactor({ id: data.id, qr: data.totp.qr_code, secret: data.totp.secret })
    })()
  }, [])
  const verify = async (e: FormEvent) => {
    e.preventDefault(); if (!factor) return
    const { error } = await supabase.auth.mfa.challengeAndVerify({ factorId: factor.id, code: code.trim() })
    if (error) return setErr('コードが正しくありません。認証アプリの最新の6桁を入力してください')
    await recheck()
  }
  return (
    <Shell title="多要素認証(MFA)の登録">
      <p>スマートフォンの認証アプリ(Google Authenticator / Microsoft Authenticator 等)でQRコードを読み取り、表示される6桁のコードを入力してください。</p>
      {factor && <>
        <img src={factor.qr} alt="多要素認証用QRコード" width={200} height={200} />
        <details><summary>QRコードを読み取れない場合</summary><code className="secret">{factor.secret}</code></details>
        <form onSubmit={verify} className="stack">
          <label className="field"><span className="field-label">6桁のコード</span>
            <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={(e) => setCode(e.target.value)} /></label>
          {err && <Banner kind="error">{err}</Banner>}
          <button className="btn primary big">登録する</button>
        </form></>}
      {!factor && err && <Banner kind="error">{err}</Banner>}
      <button className="btn link" onClick={() => void signOut()}>ログアウト</button>
    </Shell>
  )
}

export function MfaVerify() {
  const { recheck, signOut } = useAuth()
  const [code, setCode] = useState(''); const [err, setErr] = useState('')
  const verify = async (e: FormEvent) => {
    e.preventDefault()
    const { data: fs } = await supabase.auth.mfa.listFactors()
    const f = fs?.totp.find((x) => x.status === 'verified')
    if (!f) return setErr('登録済みの認証アプリがありません。管理者に再設定を依頼してください')
    const { error } = await supabase.auth.mfa.challengeAndVerify({ factorId: f.id, code: code.trim() })
    if (error) return setErr('コードが正しくありません')
    await recheck()
  }
  return (
    <Shell title="認証コードの入力">
      <form onSubmit={verify} className="stack">
        <label className="field"><span className="field-label">認証アプリの6桁のコード</span>
          <input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required autoFocus value={code} onChange={(e) => setCode(e.target.value)} /></label>
        {err && <Banner kind="error">{err}</Banner>}
        <button className="btn primary big">確認</button>
      </form>
      <button className="btn link" onClick={() => void signOut()}>ログアウト</button>
    </Shell>
  )
}

export function NoProfile() {
  const { signOut } = useAuth()
  return <Shell title="利用権限がありません"><Banner kind="warn">このアカウントには利用権限が割り当てられていないか、無効化されています。管理者に連絡してください。</Banner>
    <button className="btn" onClick={() => void signOut()}>ログアウト</button></Shell>
}
