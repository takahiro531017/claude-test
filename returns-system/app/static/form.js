// 受付登録フォーム:候補表示・下書き保存・前回引き継ぎ・写真縮小・保存して次へ
(() => {
  const form = document.getElementById('rform');
  if (!form) return;
  const isNew = form.dataset.mode === 'new';
  const $ = (n) => form.elements[n];
  const FIELDS = ['customer', 'part_no', 'product_name', 'maker', 'serial_no', 'quantity', 'defect', 'defect_text', 'reason_note'];
  const DRAFT = 'rt_draft', LAST = 'rt_last';
  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* 端末の設定で保存できない場合は無視 */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* 同上 */ } },
  };
  const values = () => Object.fromEntries(FIELDS.map((f) => [f, $(f).value]));
  const fill = (v) => { FIELDS.forEach((f) => { if (v && v[f] !== undefined) $(f).value = v[f]; }); syncChips(); };
  const showErr = (msg) => { const e = document.getElementById('formerr'); e.textContent = msg; e.hidden = !msg; if (msg) e.scrollIntoView({ block: 'center' }); };

  // ---- 不良内容のチップ ----
  const chips = [...document.querySelectorAll('[data-defect]')];
  function syncChips() { chips.forEach((c) => c.classList.toggle('on', c.dataset.defect === $('defect').value.trim())); }
  chips.forEach((c) => c.addEventListener('click', () => { $('defect').value = c.dataset.defect; syncChips(); saveDraft(); }));
  $('defect').addEventListener('input', syncChips);

  // ---- 数量 ----
  form.querySelectorAll('[data-qty]').forEach((b) => b.addEventListener('click', () => {
    $('quantity').value = Math.max(1, (parseInt($('quantity').value, 10) || 1) + parseInt(b.dataset.qty, 10)); saveDraft();
  }));

  // ---- 候補表示 ----
  let productMaster = null;  // 選択中の品番にひもづく既存の商品名
  function attachSuggest(input) {
    const kind = input.dataset.ac;
    const list = document.createElement('ul'); list.className = 'suggest'; list.hidden = true;
    input.parentNode.appendChild(list);
    let timer = 0, seq = 0;
    const close = () => { list.hidden = true; };
    async function load() {
      const my = ++seq;
      let items = [];
      try { items = await (await fetch(`/api/suggest?kind=${kind}&q=${encodeURIComponent(input.value)}`)).json(); } catch (e) { return; }
      if (my !== seq) return;
      list.innerHTML = '';
      items.forEach((it) => {
        const li = document.createElement('li');
        if (kind === 'product') {
          li.innerHTML = '<b></b><small></small>';
          li.firstChild.textContent = it.part_no;
          li.lastChild.textContent = [it.name, it.maker].filter(Boolean).join(' / ');
        } else li.textContent = it.name;
        li.addEventListener('mousedown', (e) => { e.preventDefault(); pick(it); });
        li.addEventListener('touchstart', (e) => { e.preventDefault(); pick(it); }, { passive: false });
        list.appendChild(li);
      });
      list.hidden = !items.length;
    }
    function pick(it) {
      if (kind === 'product') { input.value = it.part_no; applyProduct(it); } else input.value = it.name;
      close(); saveDraft();
    }
    input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 150); });
    input.addEventListener('focus', () => { if (kind !== 'product' || !input.value) load(); else load(); });
    input.addEventListener('blur', () => setTimeout(close, 150));
    if (kind === 'product') input.addEventListener('blur', async () => {
      if (!input.value.trim()) return;
      try { const p = await (await fetch(`/api/product?part_no=${encodeURIComponent(input.value)}`)).json(); if (p.id) applyProduct(p); } catch (e) { /* 通信できなくても入力は続けられる */ }
    });
  }
  function applyProduct(p) {
    productMaster = p;
    if (!$('product_name').value.trim() || $('product_name').dataset.auto === '1') { $('product_name').value = p.name || ''; $('product_name').dataset.auto = '1'; }
    if (!$('maker').value.trim() || $('maker').dataset.auto === '1') { $('maker').value = p.maker || ''; $('maker').dataset.auto = '1'; }
    checkName();
  }
  function checkName() {
    const w = document.getElementById('namewarn');
    const typed = $('product_name').value.trim();
    if (productMaster && productMaster.name && typed && typed.normalize('NFKC').toLowerCase() !== productMaster.name.normalize('NFKC').toLowerCase()) {
      w.textContent = `この品番は以前「${productMaster.name}」で登録されています。商品名が違いますが、このまま登録もできます。`; w.hidden = false;
    } else w.hidden = true;
  }
  ['product_name', 'maker'].forEach((n) => $(n).addEventListener('input', () => { $(n).dataset.auto = '0'; checkName(); }));
  $('part_no').addEventListener('input', () => { productMaster = null; document.getElementById('namewarn').hidden = true; });
  form.querySelectorAll('[data-ac]').forEach(attachSuggest);

  // ---- 下書き(入力途中で閉じても残る) ----
  let dt = 0;
  function saveDraft() { if (!isNew) return; clearTimeout(dt); dt = setTimeout(() => store.set(DRAFT, values()), 200); }
  if (isNew) {
    form.addEventListener('input', saveDraft);
    const d = store.get(DRAFT);
    if (d && (d.part_no || d.customer || d.defect || d.serial_no)) { fill(d); document.getElementById('draftnote').hidden = false; }
    document.getElementById('carry').addEventListener('click', () => {
      const l = store.get(LAST); if (!l) { showErr('引き継げる前回の入力がありません'); return; }
      showErr(''); fill({ ...l, serial_no: '' }); $('product_name').dataset.auto = '0'; saveDraft();
    });
    document.getElementById('clear').addEventListener('click', () => {
      if (!confirm('入力した内容をクリアしますか?')) return;
      form.reset(); $('quantity').value = 1; store.del(DRAFT); syncChips(); showErr('');
    });
  }
  syncChips();

  // ---- 写真(アップロード前に縮小) ----
  const picked = [];
  const thumbs = document.getElementById('thumbs');
  async function shrink(file) {
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
      const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
      const cv = document.createElement('canvas'); cv.width = Math.round(bmp.width * k); cv.height = Math.round(bmp.height * k);
      cv.getContext('2d').drawImage(bmp, 0, 0, cv.width, cv.height);
      const blob = await new Promise((r) => cv.toBlob(r, 'image/jpeg', 0.82));
      return blob || file;
    } catch (e) { return file; }  // 縮小できなければ原本を送る(サーバー側でも縮小する)
  }
  document.getElementById('photos').addEventListener('change', async (e) => {
    for (const f of e.target.files) {
      const blob = await shrink(f); picked.push(blob);
      const img = document.createElement('img'); img.src = URL.createObjectURL(blob); thumbs.appendChild(img);
    }
    e.target.value = '';
  });

  // ---- 送信 ----
  let nextMode = false;
  form.querySelectorAll('button[type=submit]').forEach((b) => b.addEventListener('click', () => { nextMode = b.dataset.next === '1'; }));
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault(); showErr('');
    if (!$('part_no').value.trim()) { showErr('品番を入力してください'); $('part_no').focus(); return; }
    if (!$('defect').value.trim()) { showErr('不良内容を選ぶか入力してください'); return; }
    const btns = form.querySelectorAll('button'); btns.forEach((b) => { b.disabled = true; });
    const fd = new FormData();
    FIELDS.forEach((f) => fd.append(f, $(f).value));
    fd.append('received_on', $('received_on').value);
    picked.forEach((b, i) => fd.append('photos', b, `photo${i}.jpg`));
    let res;
    try {
      const r = await fetch(form.dataset.action, { method: 'POST', body: fd });
      res = await r.json();
      if (r.status === 401) { location.href = '/staff?next=' + encodeURIComponent(location.pathname); return; }
    } catch (e) { res = { ok: false, error: '通信できませんでした。入力内容は残してあります。Wi-Fiを確認して、もう一度押してください。' }; }
    btns.forEach((b) => { b.disabled = false; });
    if (!res.ok) { showErr(res.error || '保存できませんでした'); return; }
    if (!isNew) { location.href = '/r/' + res.receipt_no + '?msg=' + encodeURIComponent('修正を保存しました'); return; }
    store.set(LAST, values()); store.del(DRAFT);
    const warn = (res.warnings || []).join('|');
    if (!nextMode) { location.href = '/done/' + res.receipt_no + (warn ? '?warn=' + encodeURIComponent(warn) : ''); return; }
    // 保存して次を入力:返品元は残してフォームを空にする
    const customer = $('customer').value;
    form.reset(); $('quantity').value = 1; $('customer').value = customer; picked.length = 0; thumbs.innerHTML = '';
    productMaster = null; syncChips(); document.getElementById('namewarn').hidden = true;
    const t = document.getElementById('toast');
    t.innerHTML = ''; t.append(`${res.receipt_no} を登録しました `);
    const a = document.createElement('a'); a.href = '/print/' + res.receipt_no; a.textContent = '[印刷]'; t.append(a);
    (res.warnings || []).forEach((w) => { const p = document.createElement('div'); p.textContent = '⚠ ' + w; t.append(p); });
    t.hidden = false; setTimeout(() => { t.hidden = true; }, 8000);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
})();
