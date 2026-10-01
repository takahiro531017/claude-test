/** バイト列を文字列にする。UTF-8として不正ならShift_JIS（CP932）として読む */
export function decodeBytes(buf: ArrayBuffer): { text: string; encoding: 'utf-8' | 'shift_jis' } {
  const bytes = new Uint8Array(buf);
  try {
    const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    return { text, encoding: 'utf-8' };
  } catch {
    const text = new TextDecoder('shift_jis').decode(bytes);
    return { text, encoding: 'shift_jis' };
  }
}
