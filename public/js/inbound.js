let products = [];

async function loadOptions() {
  const [prods, locs] = await Promise.all([Api.get("/api/products"), Api.get("/api/locations")]);
  products = prods;

  document.getElementById("product-list").innerHTML = products
    .map((p) => `<option value="${escapeHtml(p.code)}">${escapeHtml(p.name || "")}</option>`)
    .join("");

  const sel = document.getElementById("location");
  sel.innerHTML =
    `<option value="">選択してください</option>` +
    locs.map((l) => `<option value="${l.id}">${escapeHtml(l.name)}</option>`).join("");
}

function updateCurrentStockHint() {
  const code = document.getElementById("code").value.trim();
  const p = products.find((x) => x.code === code);
  const hint = document.getElementById("currentStock");
  hint.textContent = p ? `現在庫: ${p.stock.toLocaleString()}` : "";
}

async function loadRecent() {
  const rows = await Api.get("/api/movements?type=inbound&limit=15");
  const tbody = document.getElementById("recentRows");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">履歴がありません</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      (m) => `
        <tr>
          <td>${formatDateTime(m.occurred_at)}</td>
          <td>${escapeHtml(m.product_code)}</td>
          <td>${escapeHtml(m.location_name || "-")}</td>
          <td class="text-right">${m.quantity.toLocaleString()}</td>
          <td>${escapeHtml(m.note || "")}</td>
        </tr>
      `
    )
    .join("");
}

document.getElementById("code").addEventListener("input", updateCurrentStockHint);

document.getElementById("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = document.getElementById("message");
  clearMessage(message);

  const code = document.getElementById("code").value.trim();
  const location_id = document.getElementById("location").value || null;
  const quantity = document.getElementById("quantity").value;
  const occurred_at = document.getElementById("occurred_at").value || null;
  const note = document.getElementById("note").value.trim();

  try {
    await Api.post("/api/movements/inbound", {
      product_code: code,
      location_id,
      quantity,
      occurred_at: occurred_at ? new Date(occurred_at).toISOString() : null,
      note,
    });
    showMessage(message, `入庫を登録しました（品番: ${code} / 数量: ${quantity}）`, "success");
    e.target.reset();
    document.getElementById("currentStock").textContent = "";
    await loadOptions();
    await loadRecent();
  } catch (err) {
    showMessage(message, err.message);
  }
});

document.getElementById("occurred_at").value = nowForInput();
loadOptions();
loadRecent();
