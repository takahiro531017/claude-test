// アップロード前のクライアント検証(サーバー側は Storage バケット設定とRLSで同様に制限)
export const ALLOWED_MIME = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
export const MAX_BYTES = 10 * 1024 * 1024
const EXT: Record<string, string> = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'application/pdf': 'pdf' }

export function validateFile(f: { type: string; size: number }): string | null {
  if (!ALLOWED_MIME.includes(f.type)) return '画像(JPEG/PNG/WebP)またはPDFのみアップロードできます'
  if (f.size > MAX_BYTES) return 'ファイルサイズは10MB以内にしてください'
  if (f.size === 0) return '空のファイルです'
  return null
}
export const extFor = (mime: string) => EXT[mime] ?? 'bin'

/** マジックバイト確認(拡張子/MIMEの偽装対策) */
export async function sniffMime(f: Blob): Promise<string | null> {
  const b = new Uint8Array(await f.slice(0, 12).arrayBuffer())
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return 'image/jpeg'
  if (b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return 'image/png'
  if (b[0] === 0x25 && b[1] === 0x50 && b[2] === 0x44 && b[3] === 0x46) return 'application/pdf'
  if (b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 && b[8] === 0x57 && b[9] === 0x45) return 'image/webp'
  return null
}
