import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { canWrite, useAuth } from '../auth/AuthContext'
import { exportCsv, listRepairs, type ListFilters } from '../lib/api'
import { ALL_STATUSES, MAIN_FLOW, STATUS_LABEL, staleReason } from '../lib/status'
import type { Repair } from '../lib/types'
import { useRepairsRealtime } from '../hooks/useRealtime'
import { Banner, StatusBadge, fmtDate, fmtDateTime } from '../components/ui'

export default function RepairList() {
  const { masters, profile, userName } = useAuth()
  const [sp, setSp] = useSearchParams()
  const [rows, setRows] = useState<Repair[]>([])
  const [err, setErr] = useState('')
  const [view, setView] = useState<'table' | 'kanban'>('table')
  const [staleOnly, setStaleOnly] = useState(false)
  const f: ListFilters = {
    q: sp.get('q') ?? '', branchId: sp.get('branch') ? Number(sp.get('branch')) : undefined, status: sp.get('status') ?? undefined,
    manufacturerId: sp.get('mk') ? Number(sp.get('mk')) : undefined, from: sp.get('from') ?? undefined, to: sp.get('to') ?? undefined,
    sort: (sp.get('sort') as ListFilters['sort']) ?? 'updated_at', asc: sp.get('asc') === '1',
  }
  const key = sp.toString()
  const load = useCallback(() => { listRepairs(f).then(setRows).catch((e: Error) => setErr(e.message)) }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(load, [load])
  const live = useRepairsRealtime(load)

  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }
  const shown = useMemo(() => staleOnly ? rows.filter((r) => staleReason(r, masters.settings)) : rows, [rows, staleOnly, masters.settings])
  const branchName = (id: number) => masters.branches.find((b) => b.id === id)?.name ?? ''
  const showBranchFilter = (profile?.role === 'admin' || profile?.role === 'hq_viewer') && masters.branches.length > 1
  const canExport = profile?.role !== 'branch_viewer'

  const download = async () => {
    try {
      const blob = await exportCsv({ branch_id: f.branchId, status: f.status, from: f.from, to: f.to }, false)
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'repairs.csv'; a.click(); URL.revokeObjectURL(a.href)
    } catch (e) { setErr((e as Error).message) }
  }

  return (
    <>
      <h1>修理品一覧 {live && <small className="live">● リアルタイム更新中</small>}</h1>
      {err && <Banner kind="error">{err}</Banner>}
      <div className="filters">
        <input type="search" placeholder="管理番号・販売店・型番・シリアル・送り状番号・メーカー受付番号" aria-label="検索" value={sp.get('q') ?? ''} onChange={(e) => set('q', e.target.value)} />
        {showBranchFilter && <select aria-label="拠点" value={sp.get('branch') ?? ''} onChange={(e) => set('branch', e.target.value)}><option value="">全拠点</option>{masters.branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select>}
        <select aria-label="ステータス" value={sp.get('status') ?? ''} onChange={(e) => set('status', e.target.value)}><option value="">全ステータス</option>{ALL_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</select>
        <select aria-label="メーカー" value={sp.get('mk') ?? ''} onChange={(e) => set('mk', e.target.value)}><option value="">全メーカー</option>{masters.manufacturers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>
        <label>受付日 <input type="date" value={sp.get('from') ?? ''} onChange={(e) => set('from', e.target.value)} /> 〜 <input type="date" value={sp.get('to') ?? ''} onChange={(e) => set('to', e.target.value)} /></label>
        <label><input type="checkbox" checked={staleOnly} onChange={(e) => setStaleOnly(e.target.checked)} /> 滞留のみ</label>
        <select aria-label="並び替え" value={`${f.sort}:${f.asc ? 1 : 0}`} onChange={(e) => { const [s, a] = e.target.value.split(':'); const n = new URLSearchParams(sp); n.set('sort', s); n.set('asc', a); setSp(n, { replace: true }) }}>
          <option value="updated_at:0">更新が新しい順</option><option value="updated_at:1">更新が古い順</option>
          <option value="received_on:0">受付日が新しい順</option><option value="received_on:1">受付日が古い順</option><option value="mgmt_no:1">管理番号順</option>
        </select>
        <button className="btn" onClick={() => setView(view === 'table' ? 'kanban' : 'table')}>{view === 'table' ? 'カンバン表示' : '一覧表示'}</button>
        {canExport && <button className="btn" onClick={() => void download()}>CSV出力</button>}
        {canWrite(profile) && <Link className="btn primary" to="/repairs/new">＋ 新規受付</Link>}
      </div>
      <p className="hint">{shown.length}件{rows.length >= 500 && '(最大500件まで表示。条件を絞り込んでください)'} ※個人情報は一覧ではマスク表示です。</p>

      {view === 'table' ? (
        <div className="scroll"><table className="tbl">
          <thead><tr><th>管理番号</th><th>拠点</th><th>状態</th><th>販売店</th><th>商品 / 型番</th><th>エンドユーザー</th><th>受付日</th><th>最終更新</th></tr></thead>
          <tbody>{shown.map((r) => {
            const stale = staleReason(r, masters.settings)
            return (
              <tr key={r.id} className={stale ? 'stale' : ''}>
                <td><Link to={`/repairs/${r.id}`}><strong>{r.mgmt_no}</strong></Link>{r.priority === 'urgent' && <span className="urgent">至急</span>}</td>
                <td>{branchName(r.branch_id)}</td>
                <td><StatusBadge status={r.status} />{stale && <div className="warn-text">⚠ {stale}</div>}</td>
                <td>{r.dealer_name}</td>
                <td>{r.product_name}<br /><small>{r.model_no}</small></td>
                <td>{r.enduser_name_mask ?? '-'}<br /><small>{r.enduser_phone_mask ?? ''}</small></td>
                <td>{fmtDate(r.received_on)}</td>
                <td>{userName(r.updated_by)}<br /><small>{fmtDateTime(r.updated_at)}</small></td>
              </tr>)
          })}</tbody></table></div>
      ) : (
        <div className="kanban">
          {[...MAIN_FLOW, 'on_hold', 'quote_pending', 'unrepairable'].map((s) => (
            <section key={s} className="col"><h3>{STATUS_LABEL[s as keyof typeof STATUS_LABEL]} <small>{shown.filter((r) => r.status === s).length}</small></h3>
              {shown.filter((r) => r.status === s).slice(0, 50).map((r) => (
                <Link key={r.id} to={`/repairs/${r.id}`} className={`kcard ${staleReason(r, masters.settings) ? 'stale' : ''}`}>
                  <strong>{r.mgmt_no}</strong>{r.priority === 'urgent' && <span className="urgent">至急</span>}
                  <div>{r.dealer_name}</div><small>{r.product_name} {r.model_no}</small></Link>))}
            </section>))}
        </div>)}
    </>
  )
}
