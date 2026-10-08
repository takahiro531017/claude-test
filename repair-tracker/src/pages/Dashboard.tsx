import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { listRepairs } from '../lib/api'
import { ALL_STATUSES, staleReason, type Status } from '../lib/status'
import type { Repair } from '../lib/types'
import { useRepairsRealtime } from '../hooks/useRealtime'
import { Banner, StatusBadge } from '../components/ui'

export default function Dashboard() {
  const { masters } = useAuth()
  const [rows, setRows] = useState<Repair[]>([])
  const [err, setErr] = useState('')
  const load = useCallback(() => { listRepairs({ limit: 2000 }).then(setRows).catch((e: Error) => setErr(e.message)) }, [])
  useEffect(load, [load])
  const live = useRepairsRealtime(load)

  const byStatus = useMemo(() => {
    const m = new Map<string, number>()
    rows.forEach((r) => m.set(r.status, (m.get(r.status) ?? 0) + 1))
    return m
  }, [rows])
  const alerts = useMemo(() => rows.map((r) => ({ r, why: staleReason(r, masters.settings) })).filter((x) => x.why), [rows, masters.settings])

  return (
    <>
      <h1>ダッシュボード {live && <small className="live">● リアルタイム更新中</small>}</h1>
      {err && <Banner kind="error">{err}</Banner>}
      <section aria-label="ステータス別件数" className="cards">
        {ALL_STATUSES.map((s: Status) => (
          <Link key={s} to={`/repairs?status=${s}`} className="card"><span className="num">{byStatus.get(s) ?? 0}</span><StatusBadge status={s} /></Link>
        ))}
      </section>
      <section>
        <h2>拠点別件数</h2>
        <table className="tbl"><thead><tr><th>拠点</th><th>全件</th><th>対応中</th><th>完了</th></tr></thead>
          <tbody>{masters.branches.map((b) => {
            const mine = rows.filter((r) => r.branch_id === b.id)
            const done = mine.filter((r) => r.status === 'completed' || r.status === 'cancelled').length
            return <tr key={b.id}><td><Link to={`/repairs?branch=${b.id}`}>{b.name}</Link></td><td>{mine.length}</td><td>{mine.length - done}</td><td>{done}</td></tr>
          })}</tbody></table>
      </section>
      <section>
        <h2>滞留アラート <small>(メーカー発送後{masters.settings.stale_sent_days}日超 / 返却受領後{masters.settings.stale_return_days}日超で未返送)</small></h2>
        {alerts.length === 0 ? <Banner kind="ok">滞留している案件はありません。</Banner> : (
          <ul className="alerts">{alerts.map(({ r, why }) => (
            <li key={r.id}><Link to={`/repairs/${r.id}`}><strong>{r.mgmt_no}</strong></Link> {r.dealer_name} / {r.product_name} <StatusBadge status={r.status} /> <span className="warn-text">⚠ {why}</span></li>
          ))}</ul>)}
      </section>
    </>
  )
}

