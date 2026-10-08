// Edge Function テスト用: supabase-js の最小インメモリ偽物(RLS相当の絞り込みを含む)
export type Row = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any
export const db: Record<string, Row[]> = {}
export const failures = { audit: false }          // true で write_audit を失敗させる
export const deletedUsers: string[] = []
export const invited: string[] = []

const claims = (t: string) => { try { return JSON.parse(Buffer.from(t.split('.')[1], 'base64url').toString()) } catch { return {} } }

class Q {
  private f: ((r: Row) => boolean)[] = []; private op: 'select' | 'update' | 'insert' | 'upsert' | 'delete' = 'select'
  private payload: Row = {}; private onConflict = ''; private head = false; private count = false; private wantRow = false
  private lim = 1e9; private rng: [number, number] | null = null
  constructor(private table: string, private scope: (rows: Row[]) => Row[]) {}
  select(_c?: string, o?: { count?: string; head?: boolean }) { if (this.op !== 'select') this.wantRow = true; this.head = !!o?.head; this.count = !!o?.count; return this }
  eq(k: string, v: unknown) { this.f.push((r) => r[k] === v); return this }
  gte(k: string, v: string) { this.f.push((r) => String(r[k]) >= v); return this }
  lte(k: string, v: string) { this.f.push((r) => String(r[k]) <= v); return this }
  order() { return this } limit(n: number) { this.lim = n; return this } range(a: number, b: number) { this.rng = [a, b]; return this }
  update(p: Row) { this.op = 'update'; this.payload = p; return this }
  insert(p: Row) { this.op = 'insert'; this.payload = p; return this }
  upsert(p: Row, o: { onConflict: string }) { this.op = 'upsert'; this.payload = p; this.onConflict = o.onConflict; return this }
  delete() { this.op = 'delete'; return this }
  private run() {
    const all = (db[this.table] ??= [])
    const match = this.scope(all).filter((r) => this.f.every((x) => x(r)))
    if (this.op === 'update') { match.forEach((r) => Object.assign(r, this.payload)); return { data: this.wantRow ? match : null, error: null } }
    if (this.op === 'insert') { all.push({ ...this.payload }); return { data: this.wantRow ? [this.payload] : null, error: null } }
    if (this.op === 'upsert') {
      const ex = all.find((r) => r[this.onConflict] === this.payload[this.onConflict])
      if (ex) Object.assign(ex, this.payload); else all.push({ ...this.payload })
      return { data: this.wantRow ? [ex ?? this.payload].map((r) => ({ ...r, ...(ex ? ex : {}) })) : null, error: null }
    }
    if (this.op === 'delete') { db[this.table] = all.filter((r) => !match.includes(r)); return { data: null, error: null } }
    let rows = match.slice(0, this.lim)
    if (this.rng) rows = match.slice(this.rng[0], this.rng[1] + 1)
    return { data: this.head ? null : rows.map((r) => ({ ...r })), count: this.count ? match.length : null, error: null }
  }
  private one(must: boolean) {
    const r = this.run(); const row = (r.data as Row[] | null)?.[0] ?? null
    return !row && must ? { data: null, error: { message: 'no rows' } } : { data: row, error: null }
  }
  single() { return Promise.resolve(this.one(true)) }
  maybeSingle() { return Promise.resolve(this.one(false)) }
  then(res: (v: unknown) => unknown, rej?: (e: unknown) => unknown) { return Promise.resolve(this.run()).then(res, rej) }
}

export function createClient(_url: string, key: string, opts?: { global?: { headers?: Record<string, string> } }) {
  const token = (opts?.global?.headers?.Authorization ?? '').replace(/^Bearer\s+/i, '')
  const isService = key === 'service'
  const uid = claims(token).sub as string | undefined
  // RLS 相当(ユーザークライアントのみ): admin=全件 / hq=全件(削除除く) / staff・viewer=自拠点(削除除く)
  const scope = (table: string) => (rows: Row[]) => {
    if (isService || table !== 'repairs') return rows
    const p = (db.profiles ?? []).find((x) => x.user_id === uid && x.active)
    if (!p || claims(token).aal !== 'aal2') return []
    if (p.role === 'admin') return rows
    return rows.filter((r) => !r.deleted_at && (p.role === 'hq_viewer' || r.branch_id === p.branch_id))
  }
  return {
    from: (t: string) => new Q(t, scope(t)),
    rpc: async (fn: string, args: Row) => {
      if (fn === 'write_audit') {
        if (failures.audit) return { data: null, error: { message: 'audit down' } }
        ;(db.audit_log ??= []).push({ actor: args.p_actor, action: args.p_action, repair_id: args.p_repair_id, meta: args.p_meta, at: new Date().toISOString(), seq: db.audit_log.length })
        return { data: null, error: null }
      }
      return { data: null, error: { message: 'unknown rpc' } }
    },
    auth: {
      getUser: async (t: string) => { const c = claims(t); return c.sub ? { data: { user: { id: c.sub } }, error: null } : { data: { user: null }, error: { message: 'bad' } } },
      admin: {
        inviteUserByEmail: async (email: string) => { invited.push(email); return { data: { user: { id: '99999999-9999-4999-8999-999999999999' } }, error: null } },
        deleteUser: async (id: string) => { deletedUsers.push(id); return { error: null } },
        mfa: { listFactors: async () => ({ data: { factors: [{ id: 'f1' }] }, error: null }), deleteFactor: async () => ({ error: null }) },
      },
    },
  }
}
