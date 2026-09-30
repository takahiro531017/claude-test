export type PostType = 'reel' | 'feed' | 'story';
export type PostSource = 'csv' | 'manual' | 'sample';

export interface Post {
  /** 日付（分まで）＋キャプションから作る重複判定キー */
  id: string;
  /** ローカル時刻 "YYYY-MM-DDTHH:mm" */
  publishedAt: string;
  caption: string;
  /** 時刻がCSVに無い（日付のみ）場合は false。時間帯の集計から除く */
  timeKnown: boolean;
  type: PostType;
  reach: number;
  likes: number;
  comments: number;
  shares: number;
  saves: number;
  source: PostSource;
}

export const POST_TYPE_LABEL: Record<PostType, string> = {
  reel: 'リール',
  feed: 'フィード',
  story: 'ストーリーズ',
};

export interface ImportResult {
  posts: Post[];
  /** 読み込めなかった行数 */
  skippedRows: number;
  /** CSVに見つからなかった（任意）列の表示名 */
  missingOptional: string[];
  encoding: 'utf-8' | 'shift_jis';
}

export class ImportError extends Error {}
