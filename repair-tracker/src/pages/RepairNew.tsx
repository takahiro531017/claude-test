import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { createRepair, serialWarnings, uploadFile, writePii } from '../lib/api'
import { validateFile } from '../lib/files'
import type { Repair } from '../lib/types'
import { RepairForm } from '../components/RepairForm'
import { Banner, Field } from '../components/ui'

export default function RepairNew() {
  const { profile, masters, session } = useAuth()
  const nav = useNavigate()
  const [v, setV] = useState<Partial<Repair>>({ priority: 'normal', accessories: [], has_warranty_card: false, branch_id: profile?.branch_id ?? undefined })
  const [pii, setPii] = useState({ name: '', phone: '', address: '' })
  const [files, setFiles] = useState<File[]>([])
  const [warn, setWarn] = useState<string[]>([])
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [ack, setAck] = useState(false)

  if (profile?.role !== 'admin' && profile?.role !== 'branch_staff') return <Banner kind="warn">新規受付の権限がありません。</Banner>

  const checkSerial = async () => {
    if (!v.serial_no || !v.branch_id) return setWarn([])
    const w = await serialWarnings(v.serial_no, v.branch_id)
    const msgs: string[] = []
    if (w.sameBranch.length) msgs.push(`同じシリアル番号が自拠点に登録済みです: ${w.sameBranch.join(', ')}`)
    if (w.elsewhere) msgs.push('同じシリアル番号が他拠点に登録されています(二重受付の可能性)')
    setWarn(msgs); setAck(false)
  }
  const addFiles = (list: FileList | null) => {
    if (!list) return
    const ok: File[] = []
    for (const f of Array.from(list)) { const e = validateFile(f); if (e) { setErr(`${f.name}: ${e}`); continue }
      ok.push(f) }
    setFiles((p) => [...p, ...ok].slice(0, 20))
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr('')
    if (!v.branch_id) return setErr('受付拠点を選択してください')
    if (warn.length && !ack) return setErr('重複の警告を確認し、「確認した」にチェックしてください')
    setBusy(true)
    try {
      const r = await createRepair({ ...v, branch_id: v.branch_id })
      const failures: string[] = []
      if (pii.name || pii.phone || pii.address) {
        try { await writePii(r.id, { name: pii.name || undefined, phone: pii.phone || undefined, address: pii.address || undefined }) } catch { failures.push('エンドユーザー情報') }
      }
      for (const f of files) { try { await uploadFile(r.id, f, session!.user.id) } catch { failures.push(f.name) } }
      nav(`/repairs/${r.id}?created=1${failures.length ? '&partial=1' : ''}`)
    } catch (ex) { setErr((ex as Error).message); setBusy(false) }
  }

  return (
    <form onSubmit={submit} className="stack">
      <h1>新規受付</h1>
      <p className="hint">管理番号は保存時に自動採番されます(例: SPR-20261008-001)。* は必須です。</p>
      {profile.role === 'admin' && (
        <Field label="受付拠点" required><select required value={v.branch_id ?? ''} onChange={(e) => setV({ ...v, branch_id: Number(e.target.value) })}>
          <option value="">選択してください</option>{masters.branches.filter((b) => b.active).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>)}
      <RepairForm value={v} onChange={(p) => setV((o) => ({ ...o, ...p }))} sections={['basic', 'dealer', 'product']} onSerialBlur={() => void checkSerial()} />
      {warn.map((w) => <Banner key={w} kind="warn">{w}</Banner>)}
      {warn.length > 0 && <label className="check"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> 重複でないことを確認した</label>}

      <section><h2>エンドユーザー情報(任意)</h2>
        <Banner kind="info">販売店の情報だけで足りる場合は入力しないでください。入力した内容は暗号化して保存され、一覧にはマスク表示されます。</Banner>
        <div className="grid">
          <Field label="氏名"><input autoComplete="off" maxLength={60} value={pii.name} onChange={(e) => setPii({ ...pii, name: e.target.value })} /></Field>
          <Field label="電話番号"><input autoComplete="off" inputMode="tel" maxLength={30} value={pii.phone} onChange={(e) => setPii({ ...pii, phone: e.target.value })} /></Field>
          <Field label="住所"><input autoComplete="off" maxLength={200} value={pii.address} onChange={(e) => setPii({ ...pii, address: e.target.value })} /></Field>
        </div></section>

      <section><h2>写真・添付(最大20枚 / 1枚10MBまで)</h2>
        <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" capture="environment" multiple onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} aria-label="写真を撮影または選択" />
        <ul className="files">{files.map((f, i) => <li key={i}>{f.name} <button type="button" className="btn small" onClick={() => setFiles(files.filter((_, j) => j !== i))}>取消</button></li>)}</ul>
      </section>
      {err && <Banner kind="error">{err}</Banner>}
      <button className="btn primary big" disabled={busy}>{busy ? '保存中…' : '受付を保存して管理番号を発行'}</button>
    </form>
  )
}
