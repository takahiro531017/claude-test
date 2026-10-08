import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { canWrite, isAdmin, useAuth } from '../auth/AuthContext'
import { ConflictError, changeStatus, deleteFile, getRepair, listFiles, listHistory, revealPii, softDelete, updateRepair, uploadFile, writePii } from '../lib/api'
import { MAIN_FLOW, STATUS_LABEL, allowedTransitions, nextStatus, staleReason, type Status } from '../lib/status'
import type { FileRow, HistoryRow, Repair } from '../lib/types'
import { useEditors, useRepairsRealtime } from '../hooks/useRealtime'
import { RepairForm } from '../components/RepairForm'
import { Banner, Field, StatusBadge, fmtDateTime } from '../components/ui'

const REVEAL_SECONDS = 60

export default function RepairDetail() {
  const { id = '' } = useParams()
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const { profile, session, masters, userName } = useAuth()
  const [repair, setRepair] = useState<Repair | null | undefined>(undefined)
  const [draft, setDraft] = useState<Partial<Repair>>({})
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [files, setFiles] = useState<(FileRow & { url: string | null })[]>([])
  const [msg, setMsg] = useState<{ kind: 'error' | 'ok' | 'warn'; text: string } | null>(null)
  const [remote, setRemote] = useState<Repair | null>(null) // 編集中に他者が更新した最新版
  const [comment, setComment] = useState('')
  const dirty = Object.keys(draft).length > 0
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty

  const load = useCallback(async () => {
    const r = await getRepair(id)
    if (!r) { setRepair(null); return }
    setRepair((cur) => {
      if (cur && r.version > cur.version && dirtyRef.current) { setRemote(r); return cur }  // 未保存の編集を守る
      return r
    })
    setHistory(await listHistory(id)); setFiles(await listFiles(id))
  }, [id])
  useEffect(() => { void load().catch((e: Error) => setMsg({ kind: 'error', text: e.message })) }, [load])
  const live = useRepairsRealtime(() => void load(), id)
  const editors = useEditors(id, session!.user.id, profile!.display_name)

  const writable = canWrite(profile) && (isAdmin(profile) || profile?.branch_id === repair?.branch_id) && !repair?.deleted_at
  const view = useMemo(() => ({ ...repair, ...draft }) as Repair, [repair, draft])

  if (repair === undefined) return <p>読み込み中…</p>
  if (repair === null) return <Banner kind="warn">案件が見つからないか、閲覧権限がありません。</Banner>

  const adopt = (r: Repair) => { setRepair(r); setDraft({}); setRemote(null) }
  const conflict = async () => { const latest = await getRepair(id); if (latest) setRemote(latest); setMsg({ kind: 'error', text: '他のユーザーが先に更新しました。最新の内容を確認してください。' }) }

  const save = async () => {
    try { adopt(await updateRepair(repair.id, repair.version, draft)); setMsg({ kind: 'ok', text: '保存しました' }); void load() }
    catch (e) { if (e instanceof ConflictError) await conflict(); else setMsg({ kind: 'error', text: (e as Error).message }) }
  }
  const move = async (to: Status) => {
    if (dirty) return setMsg({ kind: 'warn', text: '未保存の変更があります。先に保存してください。' })
    try { adopt(await changeStatus(repair.id, repair.version, to, comment)); setComment(''); void load() }
    catch (e) { if (e instanceof ConflictError) await conflict(); else setMsg({ kind: 'error', text: (e as Error).message }) }
  }
  const remove = async (restore: boolean) => {
    if (!restore && !window.confirm('この案件を削除します(論理削除。管理者のみ復元できます)。よろしいですか?')) return
    try { await softDelete(repair.id, repair.version, restore); if (restore) void load(); else nav('/repairs') }
    catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) }
  }

  const next = nextStatus(repair.status as Status)
  const others = allowedTransitions(repair.status as Status, isAdmin(profile)).filter((s) => s !== next)
  const stale = staleReason(repair, masters.settings)
  const branch = masters.branches.find((b) => b.id === repair.branch_id)?.name

  return (
    <div className="stack">
      <h1>{repair.mgmt_no} <StatusBadge status={repair.status} /> {repair.priority === 'urgent' && <span className="urgent">至急</span>} {live && <small className="live">● リアルタイム</small>}</h1>
      <p className="meta">{branch} / 受付 {repair.received_on} / 作成: {userName(repair.created_by)} / <strong>最終更新: {userName(repair.updated_by)}({fmtDateTime(repair.updated_at)})</strong> / v{repair.version}</p>
      {sp.get('created') && <Banner kind="ok">受付を保存しました。<Link to={`/repairs/${repair.id}/receipt`}>預り証を印刷する</Link></Banner>}
      {sp.get('partial') && <Banner kind="warn">一部(個人情報/写真)の保存に失敗しました。下の欄から再度登録してください。</Banner>}
      {repair.deleted_at && <Banner kind="error">この案件は削除済みです。{isAdmin(profile) && <button className="btn small" onClick={() => void remove(true)}>復元</button>}</Banner>}
      {stale && <Banner kind="warn">⚠ 滞留: {stale}</Banner>}
      {editors.length > 0 && <Banner kind="warn">👥 {editors.join('、')} さんもこの案件を開いています。同時に編集すると競合する可能性があります。</Banner>}
      {remote && <Banner kind="error">{userName(remote.updated_by)} さんが {fmtDateTime(remote.updated_at)} に更新しました。あなたの未保存の変更は残っています。
        <button className="btn small" onClick={() => adopt(remote)}>最新を読み込む(自分の変更は破棄)</button></Banner>}
      {msg && <Banner kind={msg.kind}>{msg.text}</Banner>}

      {writable && (
        <section className="status-panel" aria-label="ステータス変更">
          {next ? <button className="btn primary huge" onClick={() => void move(next)}>次へ進める → {STATUS_LABEL[next]}</button> : <p>最終工程です。</p>}
          <input placeholder="変更コメント(任意)" maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} aria-label="変更コメント" />
          {others.length > 0 && <div className="row">その他: {others.map((s) => <button key={s} className="btn small" onClick={() => void move(s)}>{STATUS_LABEL[s]}</button>)}</div>}
        </section>)}

      <RepairForm value={view} onChange={(p) => setDraft((d) => ({ ...d, ...p }))} disabled={!writable} sections={['basic', 'dealer', 'product', 'maker', 'return']} />
      {writable && <div className="savebar"><button className="btn primary big" disabled={!dirty} onClick={() => void save()}>変更を保存</button>
        {dirty && <button className="btn" onClick={() => setDraft({})}>変更を破棄</button>}</div>}

      <PiiPanel repair={repair} canReveal={isAdmin(profile) || (profile?.role === 'branch_staff' && profile.branch_id === repair.branch_id)} canEdit={writable} onSaved={() => void load()} />

      <section><h2>写真・添付</h2>
        <div className="thumbs">{files.map((f) => (
          <figure key={f.id}>{f.url && (f.mime.startsWith('image/') ? <a href={f.url} target="_blank" rel="noreferrer noopener"><img src={f.url} alt="添付写真" loading="lazy" /></a> : <a href={f.url} target="_blank" rel="noreferrer noopener">PDFを開く</a>)}
            {writable && <button className="btn small" onClick={() => { if (window.confirm('このファイルを削除しますか?')) void deleteFile(f).then(load) }}>削除</button>}</figure>))}</div>
        {writable && <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" capture="environment" multiple aria-label="写真を追加"
          onChange={(e) => { const list = Array.from(e.target.files ?? []); e.target.value = ''; void Promise.all(list.map((f) => uploadFile(repair.id, f, session!.user.id))).then(load).catch((x: Error) => setMsg({ kind: 'error', text: x.message })) }} />}
      </section>

      <section><h2>ステータス変更履歴</h2>
        <ol className="timeline">{history.map((h) => (
          <li key={h.id}><time>{fmtDateTime(h.changed_at)}</time> {userName(h.changed_by)}:{' '}
            {h.from_status ? <>{STATUS_LABEL[h.from_status as Status]} → </> : '新規受付 → '}<strong>{STATUS_LABEL[h.to_status as Status]}</strong>{h.comment && <em>「{h.comment}」</em>}</li>))}</ol>
      </section>

      <div className="row">
        <Link className="btn" to={`/repairs/${repair.id}/receipt`}>預り証(印刷/PDF)</Link>
        {writable && !repair.deleted_at && <button className="btn danger" onClick={() => void remove(false)}>この案件を削除</button>}
      </div>
      <p className="hint">工程: {MAIN_FLOW.map((s) => STATUS_LABEL[s]).join(' → ')}</p>
    </div>
  )
}

function PiiPanel({ repair, canReveal, canEdit, onSaved }: { repair: Repair; canReveal: boolean; canEdit: boolean; onSaved: () => void }) {
  const [plain, setPlain] = useState<{ name: string | null; phone: string | null; address: string | null } | null>(null)
  const [left, setLeft] = useState(0)
  const [edit, setEdit] = useState(false)
  const [form, setForm] = useState({ name: '', phone: '', address: '' })
  const [err, setErr] = useState('')

  useEffect(() => {  // 一定時間で自動的に非表示に戻す
    if (!plain) return
    setLeft(REVEAL_SECONDS)
    const t = window.setInterval(() => setLeft((l) => { if (l <= 1) { setPlain(null); return 0 } return l - 1 }), 1000)
    return () => window.clearInterval(t)
  }, [plain])
  useEffect(() => { setPlain(null); setEdit(false) }, [repair.id])

  const reveal = async () => { setErr(''); try { setPlain(await revealPii(repair.id)) } catch (e) { setErr((e as Error).message) } }
  const startEdit = async () => { try { const p = plain ?? await revealPii(repair.id); setForm({ name: p.name ?? '', phone: p.phone ?? '', address: p.address ?? '' }); setEdit(true) } catch (e) { setErr((e as Error).message) } }
  const save = async () => {
    try { await writePii(repair.id, form); setEdit(false); setPlain(null); onSaved() } catch (e) { setErr((e as Error).message) }
  }

  if (repair.pii_purged_at) return <section><h2>エンドユーザー情報</h2><Banner kind="info">保存期間経過のため匿名化済みです。</Banner></section>
  return (
    <section><h2>エンドユーザー情報(個人情報)</h2>
      {!edit ? (<>
        <dl className="pii">
          <dt>氏名</dt><dd>{plain ? plain.name ?? '-' : repair.enduser_name_mask ?? '-'}</dd>
          <dt>電話番号</dt><dd>{plain ? plain.phone ?? '-' : repair.enduser_phone_mask ?? '-'}</dd>
          <dt>住所</dt><dd>{plain ? plain.address ?? '-' : repair.has_pii ? '（非表示）' : '-'}</dd>
        </dl>
        {canReveal && repair.has_pii && !plain && <button className="btn" onClick={() => void reveal()}>🔓 表示する(閲覧が監査ログに記録されます)</button>}
        {plain && <p className="warn-text">あと{left}秒で自動的に非表示になります。 <button className="btn small" onClick={() => setPlain(null)}>今すぐ隠す</button></p>}
        {canEdit && <button className="btn" onClick={() => void startEdit()}>{repair.has_pii ? '編集' : '入力する'}</button>}
      </>) : (
        <div className="stack">
          <Field label="氏名"><input autoComplete="off" maxLength={60} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="電話番号"><input autoComplete="off" inputMode="tel" maxLength={30} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          <Field label="住所"><input autoComplete="off" maxLength={200} value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
          <div className="row"><button className="btn primary" onClick={() => void save()}>暗号化して保存</button><button className="btn" onClick={() => setEdit(false)}>キャンセル</button></div>
        </div>)}
      {err && <Banner kind="error">{err}</Banner>}
    </section>
  )
}
