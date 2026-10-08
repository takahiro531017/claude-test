// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { MAIN_FLOW, allowedTransitions, nextStatus, prevStatus, staleReason } from '../src/lib/status'
import { sanitizeSearch, searchFilter } from '../src/lib/search'
import { extFor, sniffMime, validateFile } from '../src/lib/files'

describe('ステータス遷移', () => {
  it('本流は6段階で次/前が決まる', () => {
    expect(MAIN_FLOW).toHaveLength(6)
    expect(nextStatus('received')).toBe('sent_to_maker')
    expect(nextStatus('completed')).toBeNull()
    expect(prevStatus('received')).toBeNull()
    expect(prevStatus('in_repair')).toBe('sent_to_maker')
  })
  it('一般ユーザーは1段ずつ前進/差し戻し+補助へ。工程飛ばし不可', () => {
    const t = allowedTransitions('sent_to_maker', false)
    expect(t).toContain('in_repair'); expect(t).toContain('received'); expect(t).toContain('on_hold')
    expect(t).not.toContain('completed'); expect(t).not.toContain('returned_to_dealer')
  })
  it('完了/キャンセルは一般ユーザーは変更不可、adminは可', () => {
    expect(allowedTransitions('completed', false)).toEqual([])
    expect(allowedTransitions('cancelled', false)).toEqual([])
    expect(allowedTransitions('completed', true)).toContain('returned_to_dealer')
  })
  it('保留から本流へ復帰できるが完了へは直接行けない', () => {
    const t = allowedTransitions('on_hold', false)
    expect(t).toContain('received'); expect(t).not.toContain('completed')
  })
})

describe('滞留アラート', () => {
  const st = { stale_sent_days: 14, stale_return_days: 7 }
  const today = new Date(2026, 9, 31) // 2026-10-31
  it('メーカー発送後14日超', () => {
    expect(staleReason({ status: 'in_repair', maker_sent_on: '2026-10-10', maker_returned_on: null }, st, today)).toContain('21日')
    expect(staleReason({ status: 'in_repair', maker_sent_on: '2026-10-17', maker_returned_on: null }, st, today)).toBeNull() // ちょうど14日
  })
  it('返却受領後7日超で未返送', () => {
    expect(staleReason({ status: 'returned_from_maker', maker_sent_on: null, maker_returned_on: '2026-10-20' }, st, today)).toContain('11日')
    expect(staleReason({ status: 'returned_from_maker', maker_sent_on: null, maker_returned_on: '2026-10-28' }, st, today)).toBeNull()
  })
  it('完了済みは対象外', () => {
    expect(staleReason({ status: 'completed', maker_sent_on: '2020-01-01', maker_returned_on: null }, st, today)).toBeNull()
  })
})

describe('検索の入力無害化', () => {
  it('フィルタ構文を壊す文字を除去', () => {
    expect(sanitizeSearch(`a,b)or(id.eq.1`)).not.toMatch(/[,()]/)
    expect(sanitizeSearch(`%_*'"`)).toBe('')
    expect(searchFilter('   ')).toBeNull()
    expect(searchFilter('SPR-2026')).toContain('mgmt_no.ilike.%SPR-2026%')
  })
})

describe('ファイル検証', () => {
  it('種類とサイズの制限', () => {
    expect(validateFile({ type: 'image/jpeg', size: 1000 })).toBeNull()
    expect(validateFile({ type: 'application/x-msdownload', size: 1000 })).not.toBeNull()
    expect(validateFile({ type: 'image/png', size: 11 * 1024 * 1024 })).not.toBeNull()
    expect(validateFile({ type: 'image/png', size: 0 })).not.toBeNull()
    expect(extFor('image/webp')).toBe('webp')
  })
  it('マジックバイトで中身を判定(拡張子偽装対策)', async () => {
    expect(await sniffMime(new Blob([new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0, 0, 0, 0, 0])]))).toBe('image/jpeg')
    expect(await sniffMime(new Blob([new TextEncoder().encode('%PDF-1.7 ....')]))).toBe('application/pdf')
    expect(await sniffMime(new Blob([new TextEncoder().encode('MZ\x90\x00 exe file')]))).toBeNull()
    expect(await sniffMime(new Blob([new TextEncoder().encode('<script>alert(1)</script>')]))).toBeNull()
  })
})
