import type { Post } from './types';

/**
 * 保存先はブラウザ内のみ（IndexedDB と localStorage）。サーバーには何も送らない。
 * IndexedDB が使えない環境（プライベートモード等）では、そのセッション中だけメモリに保持する。
 */
const DB_NAME = 'venusis-insights';
const STORE = 'posts';
let memoryFallback: Post[] = [];
let useMemory = false;

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') return reject(new Error('no indexedDB'));
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function loadPosts(): Promise<Post[]> {
  try {
    const db = await openDb();
    return await new Promise<Post[]>((resolve, reject) => {
      const req = db.transaction(STORE).objectStore(STORE).getAll();
      req.onsuccess = () => resolve(req.result as Post[]);
      req.onerror = () => reject(req.error);
    });
  } catch {
    useMemory = true;
    return memoryFallback;
  }
}

export async function savePosts(posts: Post[]): Promise<void> {
  if (useMemory) {
    memoryFallback = posts;
    return;
  }
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite');
      const store = tx.objectStore(STORE);
      store.clear();
      posts.forEach((p) => store.put(p));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    useMemory = true;
    memoryFallback = posts;
  }
}

/** 軽い設定（期間・テーマ・チェックリスト等）は localStorage */
export function getPref<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem('vi:' + key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

export function setPref(key: string, value: unknown): void {
  try {
    localStorage.setItem('vi:' + key, JSON.stringify(value));
  } catch {
    /* 保存できなくても動作は続ける */
  }
}
