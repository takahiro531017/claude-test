import { useEffect, useState, type FormEvent } from 'react'
import { useAuth } from '../auth/AuthContext'
import { exportCsv, inviteUser, resetMfa } from '../lib/api'
import { supabase } from '../lib/supabase'
import { ROLE_LABEL, type Role } from '../lib/types'
import { Banner, Field, fmtDateTime } from '../components/ui'

type Tab = 'users' | 'masters' | 'settings' | 'audit' | 'export'
const TABS: [Tab, string][] = [['users', 'ユーザー'], ['masters', 'マスタ'], ['settings', '設定'], ['audit', '監査ログ'], ['export', '全件エクスポート']]

export default function Admin() {
  const [tab, setTab] = useState<Tab>('users')
  return (
    <>
      <h1>管理画面</h1>
      <div className="tabs" role="tablist">{TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === 'users' && <Users />}{tab === 'masters' && <Masters />}{tab === 'settings' && <SettingsTab />}{tab === 'audit' && <Audit />}{tab === 'export' && <Export />}
    </>
  )
}

function Users() {
  const { masters, refreshMasters, session } = useAuth()
  const [msg, setMsg] = useState<{ k: 'ok' | 'error'; t: string } | null>(null)
  const [f, setF] = useState({ email: '', display_name: '', role: 'branch_staff' as Role, branch_id: '' })
  const needBranch = f.role === 'branch_staff' || f.role === 'branch_viewer'
  const invite = async (e: FormEvent) => {
    e.preventDefault()
    try { await inviteUser({ email: f.email, display_name: f.display_name, role: f.role, branch_id: needBranch ? Number(f.branch_id) : null })
      setMsg({ k: 'ok', t: '招待メールを送信しました' }); setF({ ...f, email: '', display_name: '' }); await refreshMasters()
    } catch (x) { setMsg({ k: 'error', t: (x as Error).message }) }
  }
  const patch = async (id: string, p: Record<string, unknown>) => {
    const { error } = await supabase.from('profiles').update(p).eq('user_id', id)
    setMsg(error ? { k: 'error', t: '更新できませんでした(自分自身の権限は変更できません等)' } : { k: 'ok', t: '更新しました' }); await refreshMasters()
  }
  return (
    <>
      {msg && <Banner kind={msg.k}>{msg.t}</Banner>}
      <form onSubmit={invite} className="grid box"><h2>ユーザー招待</h2>
        <Field label="メールアドレス" required><input type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="表示名" required><input required maxLength={60} value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} /></Field>
        <Field label="権限"><select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value as Role })}>{(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></Field>
        {needBranch && <Field label="所属拠点" required><select required value={f.branch_id} onChange={(e) => setF({ ...f, branch_id: e.target.value })}><option value="">選択</option>{masters.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></Field>}
        <button className="btn primary">招待する</button></form>
      <div className="scroll"><table className="tbl"><thead><tr><th>表示名</th><th>権限</th><th>拠点</th><th>状態</th><th></th></tr></thead>
        <tbody>{masters.profiles.map((p) => (
          <tr key={p.user_id}><td>{p.display_name}</td>
            <td><select value={p.role} disabled={p.user_id === session?.user.id} onChange={(e) => void patch(p.user_id, { role: e.target.value, ...(e.target.value === 'admin' || e.target.value === 'hq_viewer' ? { branch_id: null } : {}) })}>{(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select></td>
            <td><select value={p.branch_id ?? ''} onChange={(e) => void patch(p.user_id, { branch_id: e.target.value ? Number(e.target.value) : null })}><option value="">(全拠点)</option>{masters.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></td>
            <td>{p.active ? '有効' : <strong className="warn-text">無効</strong>}</td>
            <td className="row"><button className="btn small" disabled={p.user_id === session?.user.id} onClick={() => void patch(p.user_id, { active: !p.active })}>{p.active ? '無効化' : '有効化'}</button>
              <button className="btn small" onClick={() => { if (window.confirm(`${p.display_name} さんのMFAを再設定します(次回ログイン時に再登録)。よろしいですか?`)) void resetMfa(p.user_id).then(() => setMsg({ k: 'ok', t: 'MFAをリセットしました' })).catch((x: Error) => setMsg({ k: 'error', t: x.message })) }}>MFA再設定</button></td></tr>))}</tbody></table></div>
    </>
  )
}

function Masters() {
  const { masters, refreshMasters } = useAuth()
  const [err, setErr] = useState('')
  const add = async (table: string, row: Record<string, unknown>) => {
    const { error } = await supabase.from(table).insert(row); setErr(error ? '追加できません(重複の可能性)' : ''); await refreshMasters()
  }
  const toggle = async (table: string, id: number, active: boolean) => { await supabase.from(table).update({ active: !active }).eq('id', id); await refreshMasters() }
  const [nb, setNb] = useState({ code: '', name: '' }); const [nm, setNm] = useState(''); const [nd, setNd] = useState({ code: '', name: '' })
  const List = ({ table, rows }: { table: string; rows: { id: number; name: string; active: boolean; code?: string }[] }) => (
    <ul className="plain">{rows.map((r) => <li key={r.id}>{r.code && <code>{r.code}</code>} {r.name} {!r.active && <em>(無効)</em>} <button className="btn small" onClick={() => void toggle(table, r.id, r.active)}>{r.active ? '無効化' : '有効化'}</button></li>)}</ul>)
  return (
    <>
      {err && <Banner kind="error">{err}</Banner>}
      <section className="box"><h2>拠点</h2><List table="branches" rows={masters.branches} />
        <form className="row" onSubmit={(e) => { e.preventDefault(); void add('branches', nb).then(() => setNb({ code: '', name: '' })) }}>
          <input placeholder="コード(英大文字2〜4)" pattern="[A-Z]{2,4}" required value={nb.code} onChange={(e) => setNb({ ...nb, code: e.target.value.toUpperCase() })} />
          <input placeholder="拠点名" required value={nb.name} onChange={(e) => setNb({ ...nb, name: e.target.value })} /><button className="btn">追加</button></form></section>
      <section className="box"><h2>メーカー</h2><List table="manufacturers" rows={masters.manufacturers} />
        <form className="row" onSubmit={(e) => { e.preventDefault(); void add('manufacturers', { name: nm }).then(() => setNm('')) }}>
          <input placeholder="メーカー名" required value={nm} onChange={(e) => setNm(e.target.value)} /><button className="btn">追加</button></form></section>
      <section className="box"><h2>販売店</h2><List table="dealers" rows={masters.dealers} />
        <form className="row" onSubmit={(e) => { e.preventDefault(); void add('dealers', nd).then(() => setNd({ code: '', name: '' })) }}>
          <input placeholder="販売店コード" required value={nd.code} onChange={(e) => setNd({ ...nd, code: e.target.value })} />
          <input placeholder="販売店名" required value={nd.name} onChange={(e) => setNd({ ...nd, name: e.target.value })} /><button className="btn">追加</button></form></section>
    </>
  )
}

function SettingsTab() {
  const { masters, refreshMasters } = useAuth()
  const [s, setS] = useState(masters.settings); const [msg, setMsg] = useState('')
  const LABELS: Record<keyof typeof s, string> = { stale_sent_days: '滞留: メーカー発送後(日)', stale_return_days: '滞留: 返却受領後に販売店へ未返送(日)', retention_years: '完了後の個人情報保持期間(年)', session_timeout_min: '無操作で自動ログアウト(分)' }
  const save = async () => {
    const { error } = await supabase.from('settings').upsert(Object.entries(s).map(([key, v]) => ({ key, value: String(v) })))
    setMsg(error ? '保存できませんでした' : '保存しました'); await refreshMasters()
  }
  return <section className="box stack">{(Object.keys(LABELS) as (keyof typeof s)[]).map((k) => (
    <Field key={k} label={LABELS[k]}><input type="number" min={1} max={k === 'retention_years' ? 30 : 365} value={s[k]} onChange={(e) => setS({ ...s, [k]: Number(e.target.value) })} /></Field>))}
    <button className="btn primary" onClick={() => void save()}>保存</button>{msg && <Banner kind="ok">{msg}</Banner>}</section>
}

type AuditRow = { id: number; at: string; actor: string | null; actor_role: string | null; action: string; repair_id: string | null; meta: Record<string, unknown> }
const ACTION_LABEL: Record<string, string> = { login: 'ログイン', logout: 'ログアウト', create: '作成', update: '更新', status_change: 'ステータス変更', pii_reveal: '個人情報の閲覧', pii_write: '個人情報の更新', export: 'CSV出力', permission_change: '権限変更', soft_delete: '削除', restore: '復元', pii_purge: '個人情報の匿名化', user_invite: 'ユーザー招待', mfa_reset: 'MFA再設定' }
function Audit() {
  const { userName } = useAuth()
  const [rows, setRows] = useState<AuditRow[]>([]); const [action, setAction] = useState(''); const [verify, setVerify] = useState('')
  useEffect(() => {
    let q = supabase.from('audit_log').select('*').order('id', { ascending: false }).limit(300)
    if (action) q = q.eq('action', action)
    void q.then(({ data }) => setRows((data ?? []) as AuditRow[]))
  }, [action])
  const check = async () => {
    const { data, error } = await supabase.rpc('verify_audit_chain')
    setVerify(error ? '検証に失敗しました' : data === null ? '✅ 改ざんは検出されませんでした' : `⚠ ID ${data} の行で不整合を検出しました`)
  }
  return (
    <>
      <div className="row"><select aria-label="操作で絞り込み" value={action} onChange={(e) => setAction(e.target.value)}><option value="">すべての操作</option>{Object.entries(ACTION_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <button className="btn" onClick={() => void check()}>改ざんチェック</button>{verify && <span>{verify}</span>}</div>
      <div className="scroll"><table className="tbl"><thead><tr><th>日時</th><th>操作者</th><th>操作</th><th>案件</th><th>詳細</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}><td>{fmtDateTime(r.at)}</td><td>{userName(r.actor)}</td><td>{ACTION_LABEL[r.action] ?? r.action}</td><td>{String(r.meta.mgmt_no ?? '-')}</td>
          <td><small>{r.action === 'status_change' ? `${r.meta.from} → ${r.meta.to}` : r.action === 'update' || r.action === 'pii_write' ? `項目: ${(r.meta.fields as string[] | undefined)?.join(', ')}` : r.action === 'export' ? `${r.meta.row_count}件${r.meta.include_pii ? '(個人情報含む)' : ''}` : ''}</small></td></tr>)}</tbody></table></div>
    </>
  )
}

function Export() {
  const [pii, setPii] = useState(false); const [msg, setMsg] = useState('')
  const go = async () => {
    if (pii && !window.confirm('個人情報(氏名・電話・住所)を含むCSVを出力します。出力は監査ログに記録されます。取り扱いに十分注意してください。')) return
    try { const b = await exportCsv({}, pii); const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'repairs-all.csv'; a.click(); URL.revokeObjectURL(a.href); setMsg('出力しました(監査ログに記録済み)') }
    catch (x) { setMsg((x as Error).message) }
  }
  return <section className="box stack"><p>全案件(削除済みを含む)をCSVで出力します。SQLでの全件バックアップは docs/運用マニュアル.md を参照してください。</p>
    <label className="check"><input type="checkbox" checked={pii} onChange={(e) => setPii(e.target.checked)} /> 個人情報列(氏名・電話・住所)を含める【要注意】</label>
    <button className="btn primary" onClick={() => void go()}>CSVを出力</button>{msg && <Banner kind="info">{msg}</Banner>}</section>
}
