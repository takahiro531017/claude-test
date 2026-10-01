/**
 * CSVの列名の対応表。
 * 実際のCSVの列名が違う場合は、ここに候補を足すだけで対応できます。
 * 照合は「前後の空白・全角半角・大文字小文字・記号（！ ? など）」を無視して行います。
 */
export type FieldKey =
  | 'publishedAt'
  | 'date'
  | 'time'
  | 'caption'
  | 'type'
  | 'reach'
  | 'likes'
  | 'comments'
  | 'shares'
  | 'saves';

export const COLUMN_CANDIDATES: Record<FieldKey, string[]> = {
  publishedAt: ['公開日時', '投稿日時', '公開時間', '投稿日時(JST)', 'publish time', 'published time', 'publish date time', 'posted at', 'created time', 'post time'],
  date: ['日付', '公開日', '投稿日', 'date', 'publish date', 'post date'],
  time: ['時間', '時刻', '公開時刻', 'time'],
  caption: ['説明', 'キャプション', '投稿内容', 'タイトル', '本文', 'description', 'caption', 'title', 'post caption'],
  type: ['投稿タイプ', '投稿の種類', '種類', 'タイプ', 'コンテンツタイプ', 'post type', 'type', 'media type', 'content type'],
  reach: ['リーチ', 'リーチしたアカウント', 'reach', 'accounts reached'],
  likes: ['いいね', 'いいね数', 'likes', 'like'],
  comments: ['コメント', 'コメント数', 'comments', 'comment'],
  shares: ['シェア', 'シェア数', '共有', 'shares', 'share'],
  saves: ['保存', '保存数', '保存済み', 'saves', 'save', 'saved'],
};

/** 画面表示用の列名（エラー文言などで使う） */
export const FIELD_LABEL: Record<FieldKey, string> = {
  publishedAt: '公開日時',
  date: '日付',
  time: '時間',
  caption: 'キャプション（説明）',
  type: '投稿タイプ',
  reach: 'リーチ',
  likes: 'いいね',
  comments: 'コメント',
  shares: 'シェア',
  saves: '保存',
};

/** 必須の数値列（これが無いと分析できない） */
export const REQUIRED_NUMERIC: FieldKey[] = ['reach'];
/** 無くても動くが、あると精度が上がる列 */
export const OPTIONAL_FIELDS: FieldKey[] = ['caption', 'type', 'likes', 'comments', 'shares', 'saves'];

/** 投稿タイプの値の判定。上から順に部分一致で判定する */
export const TYPE_PATTERNS: { type: 'reel' | 'feed' | 'story'; patterns: string[] }[] = [
  { type: 'story', patterns: ['ストーリー', 'story', 'stories'] },
  { type: 'reel', patterns: ['リール', 'reel', 'video', '動画'] },
  { type: 'feed', patterns: ['フィード', 'feed', '画像', 'image', 'photo', 'carousel', 'カルーセル', '写真', '投稿'] },
];

/** 時間帯の区分（開始時, ラベル）。変更したい場合はここを編集 */
export const TIME_BANDS: { from: number; to: number; label: string }[] = [
  { from: 5, to: 10, label: '朝 5–10時' },
  { from: 11, to: 15, label: '昼 11–15時' },
  { from: 16, to: 19, label: '夕 16–19時' },
  { from: 20, to: 23, label: '夜 20–23時' },
  { from: 0, to: 4, label: '深夜 0–4時' },
];
