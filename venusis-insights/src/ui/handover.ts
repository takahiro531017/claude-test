import { getPref, setPref } from '../data/storage';
import { EXPORT_STEPS, METRIC_HELP, MONTHLY_CHECKLIST } from '../config/labels';
import { esc } from './dom';

export function renderHandover(el: HTMLElement) {
  const now = new Date();
  const monthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const done = new Set<string>(getPref<string[]>('check:' + monthKey, []));

  el.innerHTML = `
    <div class="card">
      <h3 style="font-size:16px;margin-bottom:4px">毎月やること（${now.getFullYear()}年${now.getMonth() + 1}月）</h3>
      <p class="note" style="margin:0 0 8px">終わったらチェックを入れてください。月が変わると、自動で新しいチェックリストになります。</p>
      <ul class="checklist">${MONTHLY_CHECKLIST.map(
        (c) => `<li><label><input type="checkbox" data-id="${c.id}"${done.has(c.id) ? ' checked' : ''} /><span><span class="t">${esc(c.title)}</span><br /><span class="n">${esc(c.note)}</span></span></label></li>`,
      ).join('')}</ul>
    </div>
    <div class="card">
      <h3 style="font-size:16px;margin-bottom:8px">CSVの書き出し手順</h3>
      <ol class="steps">${EXPORT_STEPS.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>
      <p class="note">画面の名称はMetaの更新で変わることがあります。「インサイト」の中の「コンテンツ」から、CSVで書き出せる項目を探してください。リーチと、いいね・コメント・シェア・保存が含まれていると、すべての分析ができます。</p>
    </div>
    <div class="card">
      <h3 style="font-size:16px;margin-bottom:4px">数字の意味</h3>
      <dl class="glossary">${METRIC_HELP.map((h) => `<dt>${esc(h.title)}</dt><dd>${esc(h.body)}</dd>`).join('')}</dl>
      <p class="note">「前の期間と比べて」は、選んだ期間と同じ日数だけ前の期間との比較です（例: 直近30日なら、その前の30日）。基準日は、データの中でいちばん新しい投稿の日です。▲は増加、▼は減少、―は変化なしです。</p>
    </div>`;

  el.querySelectorAll<HTMLInputElement>('input[type=checkbox]').forEach((cb) =>
    cb.addEventListener('change', () => {
      cb.checked ? done.add(cb.dataset.id!) : done.delete(cb.dataset.id!);
      setPref('check:' + monthKey, [...done]);
    }),
  );
}
