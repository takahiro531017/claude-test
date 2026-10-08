import type { ReactNode } from 'react'
import { STATUS_COLOR, STATUS_LABEL, type Status } from '../lib/status'

export function StatusBadge({ status }: { status: string }) {
  const s = status as Status
  return <span className="badge" style={{ background: STATUS_COLOR[s] ?? '#475569' }}>{STATUS_LABEL[s] ?? status}</span>
}

export function Field({ label, required, hint, children }: { label: string; required?: boolean; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}{required && <em aria-label="必須"> *</em>}</span>
      {children}
      {hint && <small className="hint">{hint}</small>}
    </label>
  )
}

export function Banner({ kind, children }: { kind: 'error' | 'warn' | 'info' | 'ok'; children: ReactNode }) {
  return <div className={`banner ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div>
}

export const fmtDate = (s: string | null) => (s ? s.slice(0, 10) : '-')
export const fmtDateTime = (s: string | null) =>
  s ? new Date(s).toLocaleString('ja-JP', { timeZone: 'Asia/Tokyo', hour12: false, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-'
