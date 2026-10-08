import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { getRepair } from '../lib/api'
import type { Repair } from '../lib/types'
import { Banner, fmtDate } from '../components/ui'

/** 預り証。ブラウザの印刷機能(PDFに保存可)を使用。エンドユーザーの個人情報は記載しない。 */
export default function Receipt() {
  const { id = '' } = useParams()
  const { masters } = useAuth()
  const [r, setR] = useState<Repair | null | undefined>(undefined)
  useEffect(() => { void getRepair(id).then(setR) }, [id])
  if (r === undefined) return <p>読み込み中…</p>
  if (!r) return <Banner kind="warn">案件が見つかりません。</Banner>
  const mk = masters.manufacturers.find((m) => m.id === r.manufacturer_id)?.name
  const br = masters.branches.find((b) => b.id === r.branch_id)?.name
  return (
    <div>
      <div className="noprint row"><button className="btn primary big" onClick={() => window.print()}>印刷 / PDFとして保存</button><Link className="btn" to={`/repairs/${r.id}`}>戻る</Link></div>
      <article className="receipt">
        <h1>修理品 預り証</h1>
        <p className="big-no">管理番号: <strong>{r.mgmt_no}</strong></p>
        <table className="tbl"><tbody>
          <tr><th>受付日</th><td>{fmtDate(r.received_on)}</td><th>受付拠点</th><td>{br}</td></tr>
          <tr><th>販売店</th><td colSpan={3}>{r.dealer_name}{r.dealer_contact_name && `(${r.dealer_contact_name} 様)`}</td></tr>
          <tr><th>メーカー</th><td>{mk}</td><th>商品名</th><td>{r.product_name}</td></tr>
          <tr><th>型番</th><td>{r.model_no ?? '-'}</td><th>シリアル</th><td>{r.serial_no ?? '-'}</td></tr>
          <tr><th>付属品</th><td colSpan={3}>{r.accessories.length ? r.accessories.join('、') : 'なし'}</td></tr>
          <tr><th>故障症状</th><td colSpan={3}>{r.symptom}</td></tr>
          <tr><th>外観状態</th><td colSpan={3}>{r.appearance_note ?? '-'}</td></tr>
        </tbody></table>
        <p className="hint">上記の修理品を確かにお預かりしました。お問い合わせの際は管理番号をお知らせください。</p>
      </article>
    </div>
  )
}
