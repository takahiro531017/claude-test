import { useEffect, useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import { supabase } from '../lib/supabase'
import { ACCESSORY_CHOICES, CARRIERS, type Repair } from '../lib/types'
import { Field } from './ui'

export type Section = 'basic' | 'dealer' | 'product' | 'maker' | 'return'
type Props = { value: Partial<Repair>; onChange: (patch: Partial<Repair>) => void; sections: Section[]; disabled?: boolean; onSerialBlur?: () => void }

const num = (v: string) => (v === '' ? null : Number(v))
const str = (v: string) => (v === '' ? null : v)

export function RepairForm({ value: v, onChange, sections, disabled, onSerialBlur }: Props) {
  const { masters } = useAuth()
  const [models, setModels] = useState<string[]>([])
  useEffect(() => {
    if (!v.manufacturer_id) return setModels([])
    void supabase.from('repairs').select('model_no').eq('manufacturer_id', v.manufacturer_id).not('model_no', 'is', null).limit(300)
      .then(({ data }) => setModels([...new Set((data ?? []).map((r) => r.model_no as string))].sort()))
  }, [v.manufacturer_id])
  const acc = v.accessories ?? []
  const toggleAcc = (a: string) => onChange({ accessories: acc.includes(a) ? acc.filter((x) => x !== a) : [...acc, a] })
  const pickDealer = (name: string) => {
    const d = masters.dealers.find((x) => x.name === name)
    onChange({ dealer_name: name, dealer_id: d?.id ?? null, dealer_code: d?.code ?? v.dealer_code ?? null })
  }

  return (
    <fieldset disabled={disabled} className="form">
      {sections.includes('basic') && <section><h2>基本情報</h2><div className="grid">
        <Field label="優先度"><select value={v.priority ?? 'normal'} onChange={(e) => onChange({ priority: e.target.value as Repair['priority'] })}><option value="normal">通常</option><option value="urgent">至急</option></select></Field>
        <Field label="納期目安"><input type="date" value={v.due_on ?? ''} onChange={(e) => onChange({ due_on: str(e.target.value) })} /></Field>
      </div></section>}

      {sections.includes('dealer') && <section><h2>販売店情報</h2><div className="grid">
        <Field label="販売店名" required><input list="dealers" required maxLength={100} value={v.dealer_name ?? ''} onChange={(e) => pickDealer(e.target.value)} />
          <datalist id="dealers">{masters.dealers.filter((d) => d.active).map((d) => <option key={d.id} value={d.name} />)}</datalist></Field>
        <Field label="販売店コード"><input maxLength={30} value={v.dealer_code ?? ''} onChange={(e) => onChange({ dealer_code: str(e.target.value) })} /></Field>
        <Field label="販売店担当者名"><input maxLength={60} value={v.dealer_contact_name ?? ''} onChange={(e) => onChange({ dealer_contact_name: str(e.target.value) })} /></Field>
        <Field label="連絡先"><input maxLength={100} value={v.dealer_contact ?? ''} onChange={(e) => onChange({ dealer_contact: str(e.target.value) })} /></Field>
      </div></section>}

      {sections.includes('product') && <section><h2>商品情報</h2><div className="grid">
        <Field label="メーカー" required><select required value={v.manufacturer_id ?? ''} onChange={(e) => onChange({ manufacturer_id: Number(e.target.value) })}>
          <option value="">選択してください</option>{masters.manufacturers.filter((m) => m.active).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></Field>
        <Field label="商品名" required><input required maxLength={150} value={v.product_name ?? ''} onChange={(e) => onChange({ product_name: e.target.value })} /></Field>
        <Field label="型番" hint="過去の入力から候補を表示します"><input list="models" maxLength={60} value={v.model_no ?? ''} onChange={(e) => onChange({ model_no: str(e.target.value) })} />
          <datalist id="models">{models.map((m) => <option key={m} value={m} />)}</datalist></Field>
        <Field label="シリアル番号"><input maxLength={60} value={v.serial_no ?? ''} onChange={(e) => onChange({ serial_no: str(e.target.value) })} onBlur={onSerialBlur} /></Field>
        <Field label="購入日"><input type="date" value={v.purchased_on ?? ''} onChange={(e) => onChange({ purchased_on: str(e.target.value) })} /></Field>
        <Field label="保証書"><select value={String(v.has_warranty_card ?? false)} onChange={(e) => onChange({ has_warranty_card: e.target.value === 'true' })}><option value="false">なし</option><option value="true">あり</option></select></Field>
        <Field label="保証期間"><select value={v.in_warranty === null || v.in_warranty === undefined ? '' : String(v.in_warranty)} onChange={(e) => onChange({ in_warranty: e.target.value === '' ? null : e.target.value === 'true' })}><option value="">不明</option><option value="true">期間内</option><option value="false">期間外</option></select></Field>
      </div>
        <Field label="付属品"><div className="checks">{ACCESSORY_CHOICES.map((a) => <label key={a} className="check"><input type="checkbox" checked={acc.includes(a)} onChange={() => toggleAcc(a)} /> {a}</label>)}</div></Field>
        <Field label="故障症状" required><textarea required rows={3} maxLength={2000} value={v.symptom ?? ''} onChange={(e) => onChange({ symptom: e.target.value })} /></Field>
        <Field label="外観状態メモ"><textarea rows={2} maxLength={2000} value={v.appearance_note ?? ''} onChange={(e) => onChange({ appearance_note: str(e.target.value) })} /></Field>
      </section>}

      {sections.includes('maker') && <section><h2>メーカー対応</h2><div className="grid">
        <Field label="メーカー受付番号"><input maxLength={60} value={v.maker_receipt_no ?? ''} onChange={(e) => onChange({ maker_receipt_no: str(e.target.value) })} /></Field>
        <Field label="メーカー発送日"><input type="date" value={v.maker_sent_on ?? ''} onChange={(e) => onChange({ maker_sent_on: str(e.target.value) })} /></Field>
        <Field label="運送会社(発送)"><select value={v.outbound_carrier ?? ''} onChange={(e) => onChange({ outbound_carrier: str(e.target.value) })}><option value="">-</option>{CARRIERS.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="送り状番号(発送)"><input maxLength={60} value={v.outbound_tracking_no ?? ''} onChange={(e) => onChange({ outbound_tracking_no: str(e.target.value) })} /></Field>
        <Field label="見積金額(円)"><input type="number" min={0} inputMode="numeric" value={v.quote_amount ?? ''} onChange={(e) => onChange({ quote_amount: num(e.target.value) })} /></Field>
        <Field label="見積の承認"><select value={v.quote_approved === null || v.quote_approved === undefined ? '' : String(v.quote_approved)} onChange={(e) => onChange({ quote_approved: e.target.value === '' ? null : e.target.value === 'true' })}><option value="">未確認</option><option value="true">承認</option><option value="false">不承認</option></select></Field>
        <Field label="修理費用(円)"><input type="number" min={0} inputMode="numeric" value={v.repair_cost ?? ''} onChange={(e) => onChange({ repair_cost: num(e.target.value) })} /></Field>
        <Field label="メーカー返却日"><input type="date" value={v.maker_returned_on ?? ''} onChange={(e) => onChange({ maker_returned_on: str(e.target.value) })} /></Field>
      </div><Field label="修理内容"><textarea rows={2} maxLength={2000} value={v.repair_detail ?? ''} onChange={(e) => onChange({ repair_detail: str(e.target.value) })} /></Field></section>}

      {sections.includes('return') && <section><h2>返送・完了</h2><div className="grid">
        <Field label="販売店返送日"><input type="date" value={v.dealer_returned_on ?? ''} onChange={(e) => onChange({ dealer_returned_on: str(e.target.value) })} /></Field>
        <Field label="運送会社(返送)"><select value={v.return_carrier ?? ''} onChange={(e) => onChange({ return_carrier: str(e.target.value) })}><option value="">-</option>{CARRIERS.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="送り状番号(返送)"><input maxLength={60} value={v.return_tracking_no ?? ''} onChange={(e) => onChange({ return_tracking_no: str(e.target.value) })} /></Field>
        <Field label="完了日"><input type="date" value={v.completed_on ?? ''} onChange={(e) => onChange({ completed_on: str(e.target.value) })} /></Field>
      </div><Field label="備考"><textarea rows={2} maxLength={2000} value={v.note ?? ''} onChange={(e) => onChange({ note: str(e.target.value) })} /></Field></section>}
    </fieldset>
  )
}
