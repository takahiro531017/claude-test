import { FIELD_LABEL, type FieldKey } from '../config/columnMap';
import { parseCsv, toCsv } from '../data/csv';
import { decodeBytes } from '../data/decode';
import { mapColumns, MissingColumnsError, normalizeTable, buildPost, type ColumnOverrides } from '../data/normalize';
import { POST_TYPE_LABEL, ImportError, type ImportResult, type Post, type PostType } from '../data/types';
import { $, confirmDialog, esc } from './dom';

export interface ImportHooks {
  getPosts(): Post[];
  isSample(): boolean;
  /** 投稿を取り込み、追加/更新件数を返す */
  onImported(posts: Post[]): { added: number; updated: number };
  onClear(): void;
  onSample(): void;
}

const MAX_BYTES = 20 * 1024 * 1024;
const TYPE_CSV: Record<PostType, string> = { reel: 'Instagramリール', feed: 'Instagram投稿', story: 'Instagramストーリーズ' };
const MAP_FIELDS: FieldKey[] = ['publishedAt', 'reach', 'type', 'caption', 'likes', 'comments', 'shares', 'saves'];

export function mountImportPanel(root: HTMLElement, hooks: ImportHooks) {
  root.innerHTML = `
    <div class="drop" id="drop">
      <label class="btn btn-primary" for="file-input">CSVを選ぶ</label>
      <input class="file-input" id="file-input" type="file" accept=".csv,.txt,text/csv" />
      <p>Meta Business Suite から書き出したCSVを選んでください。ここにファイルをドラッグしても読み込めます。<br />文字コード（UTF-8 / Shift_JIS）は自動で判定します。</p>
    </div>
    <div id="import-status" aria-live="polite"></div>
    <div id="mapping"></div>

    <div class="sub-block">
      <details>
        <summary class="btn" style="display:inline-flex">投稿を1件ずつ入力する</summary>
        <form id="manual" class="sub-block" style="border-top:0;padding-top:12px" novalidate>
          <div class="form-grid">
            <div class="field half"><label for="m-date">公開日時<span class="hint"> ※必須</span></label><input id="m-date" type="datetime-local" required /></div>
            <div class="field half"><label for="m-type">投稿タイプ</label>
              <select id="m-type">${(['reel', 'feed', 'story'] as PostType[]).map((t) => `<option value="${t}">${POST_TYPE_LABEL[t]}</option>`).join('')}</select></div>
            <div class="field wide"><label for="m-caption">キャプション<span class="hint">（投稿の文章。同じ日時・同じ文章の投稿は1つにまとまります）</span></label><textarea id="m-caption"></textarea></div>
            <div class="field"><label for="m-reach">リーチ<span class="hint"> ※必須</span></label><input id="m-reach" type="number" inputmode="numeric" min="0" step="1" /></div>
            <div class="field"><label for="m-likes">いいね</label><input id="m-likes" type="number" inputmode="numeric" min="0" step="1" value="0" /></div>
            <div class="field"><label for="m-comments">コメント</label><input id="m-comments" type="number" inputmode="numeric" min="0" step="1" value="0" /></div>
            <div class="field"><label for="m-shares">シェア</label><input id="m-shares" type="number" inputmode="numeric" min="0" step="1" value="0" /></div>
            <div class="field"><label for="m-saves">保存</label><input id="m-saves" type="number" inputmode="numeric" min="0" step="1" value="0" /></div>
          </div>
          <div id="manual-status" aria-live="polite"></div>
          <div class="btn-row"><button type="submit" class="btn btn-primary">この投稿を追加</button></div>
        </form>
      </details>
    </div>

    <div class="sub-block">
      <h3>データの管理</h3>
      <p class="note" style="margin:0 0 10px">データはこの端末のブラウザにだけ保存されています。ブラウザの履歴を消すと無くなることがあるため、ときどきバックアップを保存しておくと安心です。</p>
      <div class="btn-row" style="margin-top:0">
        <button type="button" class="btn" id="backup">データをCSVで保存（バックアップ）</button>
        <button type="button" class="btn" id="to-sample">サンプルデータに戻す</button>
        <button type="button" class="btn btn-danger" id="clear">すべてのデータを削除</button>
      </div>
    </div>`;

  const status = $('#import-status', root);
  const setStatus = (html: string, error = false, el: HTMLElement = status) => {
    el.innerHTML = html ? `<div class="status${error ? ' error' : ''}">${html}</div>` : '';
  };

  const finish = (r: ImportResult) => {
    if (r.posts.length === 0) {
      setStatus(`<strong>読み込める投稿がありませんでした。</strong>日付とリーチが入っている行が見つかりません。CSVの中身をご確認ください。`, true);
      return;
    }
    const { added, updated } = hooks.onImported(r.posts);
    const notes: string[] = [];
    if (r.skippedRows) notes.push(`読み取れなかった行が${r.skippedRows}行ありました（日付またはリーチが空・不正）。`);
    if (r.missingOptional.length) notes.push(`CSVに見つからなかった項目: ${esc(r.missingOptional.join('、'))}（0件または「フィード」として扱います）。`);
    setStatus(`<strong>${r.posts.length}件を読み込みました。</strong>新しい投稿 ${added}件、すでにあった投稿の更新 ${updated}件。${notes.length ? '<br>' + notes.join('<br>') : ''}`);
    $('#mapping', root).innerHTML = '';
  };

  const showMapping = (err: MissingColumnsError, table: string[][], enc: ImportResult['encoding']) => {
    const auto = mapColumns(err.headers);
    const opts = (sel: number | undefined, required: boolean) =>
      `${required ? '<option value="">選んでください</option>' : '<option value="">（なし）</option>'}${err.headers
        .map((h, i) => `<option value="${i}"${sel === i ? ' selected' : ''}>${esc(h || `（列${i + 1}）`)}</option>`)
        .join('')}`;
    const labelOf = (f: FieldKey) => (f === 'publishedAt' ? '公開日時（または日付）' : FIELD_LABEL[f]);
    setStatus(
      `<strong>必要な列が見つかりませんでした: ${esc(err.missing.map((k) => (k === 'publishedAt' ? '公開日時（日付）' : FIELD_LABEL[k])).join('、'))}</strong>
       CSVの列名が想定と違うようです。下で、どの列が何にあたるかを選んでください。`,
      true,
    );
    $('#mapping', root).innerHTML = `<form class="sub-block" id="map-form">
      <h3>列を手動で選ぶ</h3>
      <div class="form-grid">${MAP_FIELDS.map((f) => {
        const required = f === 'publishedAt' || f === 'reach';
        const sel = f === 'publishedAt' ? auto.publishedAt ?? auto.date : auto[f];
        return `<div class="field half"><label for="map-${f}">${labelOf(f)}${required ? '<span class="hint"> ※必須</span>' : ''}</label><select id="map-${f}" data-f="${f}">${opts(sel, required)}</select></div>`;
      }).join('')}</div>
      <div class="btn-row"><button class="btn btn-primary" type="submit">この内容で読み込む</button></div></form>`;
    $('#map-form', root).addEventListener('submit', (e) => {
      e.preventDefault();
      const ov: ColumnOverrides = {};
      root.querySelectorAll<HTMLSelectElement>('#map-form select').forEach((s) => {
        if (s.value !== '') ov[s.dataset.f as FieldKey] = Number(s.value);
      });
      try {
        finish(normalizeTable(table, enc, ov));
      } catch (e2) {
        if (e2 instanceof MissingColumnsError) setStatus(`<strong>まだ必要な列が選ばれていません: ${esc(e2.missing.map((k) => (k === 'publishedAt' ? '公開日時' : FIELD_LABEL[k])).join('、'))}</strong>`, true);
        else setStatus(esc(String((e2 as Error).message)), true);
      }
    });
  };

  async function handleFile(file: File) {
    $('#mapping', root).innerHTML = '';
    if (file.size > MAX_BYTES) return setStatus('<strong>ファイルが大きすぎます（20MBまで）。</strong>書き出す期間を短くしてお試しください。', true);
    try {
      const { text, encoding } = decodeBytes(await file.arrayBuffer());
      const table = parseCsv(text);
      try {
        finish(normalizeTable(table, encoding));
      } catch (e) {
        if (e instanceof MissingColumnsError) showMapping(e, table, encoding);
        else throw e;
      }
    } catch (e) {
      setStatus(`<strong>読み込めませんでした。</strong>${esc(e instanceof ImportError ? e.message : 'CSVファイルではないか、ファイルが壊れている可能性があります。')}`, true);
    }
  }

  const input = $<HTMLInputElement>('#file-input', root);
  input.addEventListener('change', () => {
    if (input.files?.[0]) void handleFile(input.files[0]);
    input.value = '';
  });
  const drop = $('#drop', root);
  ['dragenter', 'dragover'].forEach((t) => drop.addEventListener(t, (e) => (e.preventDefault(), drop.classList.add('over'))));
  ['dragleave', 'drop'].forEach((t) => drop.addEventListener(t, (e) => (e.preventDefault(), drop.classList.remove('over'))));
  drop.addEventListener('drop', (e) => {
    const f = (e as DragEvent).dataTransfer?.files?.[0];
    if (f) void handleFile(f);
  });

  // 手入力
  const form = $<HTMLFormElement>('#manual', root);
  const val = (id: string) => $<HTMLInputElement>('#' + id, root).value;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const st = $('#manual-status', root);
    const date = val('m-date');
    const reach = val('m-reach');
    const num = (id: string) => Math.max(0, Math.round(Number(val(id)) || 0));
    if (!date) return setStatus('公開日時を入力してください。', true, st);
    if (reach === '' || Number(reach) < 0) return setStatus('リーチを0以上の数字で入力してください。', true, st);
    const post = buildPost(
      { publishedAt: date.slice(0, 16), timeKnown: true, caption: val('m-caption').trim(), type: val('m-type') as PostType, reach: num('m-reach'), likes: num('m-likes'), comments: num('m-comments'), shares: num('m-shares'), saves: num('m-saves') },
      'manual',
    );
    const { added } = hooks.onImported([post]);
    setStatus(added ? '追加しました。' : '同じ日時・同じキャプションの投稿があったため、数値を更新しました。', false, st);
    (['m-caption', 'm-reach'] as const).forEach((id) => ($<HTMLInputElement>('#' + id, root).value = ''));
  });

  // データ管理
  $('#backup', root).addEventListener('click', () => {
    if (hooks.isSample() || hooks.getPosts().length === 0) return setStatus('保存できるデータがありません（サンプルデータは保存できません）。', true);
    const rows: (string | number)[][] = [['公開日時', '投稿タイプ', '説明', 'リーチ', 'いいね', 'コメント', 'シェア', '保存数']];
    for (const p of hooks.getPosts()) rows.push([p.publishedAt.replace('T', ' ').replace(/-/g, '/'), TYPE_CSV[p.type], p.caption, p.reach, p.likes, p.comments, p.shares, p.saves]);
    const blob = new Blob(['﻿' + toCsv(rows) + '\r\n'], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    const d = new Date();
    a.href = URL.createObjectURL(blob);
    a.download = `venusis-posts-${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
  $('#to-sample', root).addEventListener('click', async () => {
    if (await confirmDialog('サンプルデータに戻します。読み込み済みのデータは、この端末から削除されます。よろしいですか？', 'サンプルに戻す')) hooks.onSample();
  });
  $('#clear', root).addEventListener('click', async () => {
    if (await confirmDialog('読み込み済みのデータをすべて削除します。元に戻せません。よろしいですか？', '削除する')) {
      hooks.onClear();
      setStatus('削除しました。');
    }
  });
}
