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

function currentProduct() {
  const code = document.getElementById("code").value.trim();
  return products.find((x) => x.code === code);
}

function updateCurrentStockHint() {
  const p = currentProduct();
  const hint = document.getElementById("currentStock");
  hint.textContent = p ? `現在庫: ${p.stock.toLocaleString()}` : "";
}

function typeBadge(type) {
  const map = { inbound: ["入庫", "type-inbound"], outbound: ["出荷", "type-outbound"], damage: ["破損", "type-damage"] };
  const [label, cls] = map[type] || [type, ""];
  return `<span class="badge ${cls}">${label}</span>`;
}

async function loadRecent() {
  const [outRows, dmgRows] = await Promise.all([
    Api.get("/api/movements?type=outbound&limit=15"),
    Api.get("/api/movements?type=damage&limit=15"),
  ]);
  const rows = [...outRows, ...dmgRows]
    .sort((a, b) => (a.occurred_at < b.occurred_at ? 1 : -1))
    .slice(0, 15);

  const tbody = document.getElementById("recentRows");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty">履歴がありません</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      (m) => `
        <tr>
          <td>${formatDateTime(m.occurred_at)}</td>
          <td>${escapeHtml(m.product_code)}</td>
          <td>${escapeHtml(m.location_name || "-")}</td>
          <td>${typeBadge(m.type)}</td>
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
  const quantity = parseInt(document.getElementById("quantity").value, 10) || 0;
  const damage_quantity = parseInt(document.getElementById("damage_quantity").value, 10) || 0;
  const occurred_at = document.getElementById("occurred_at").value || null;
  const note = document.getElementById("note").value.trim();

  const p = currentProduct();
  const totalOut = quantity + damage_quantity;
  if (p && totalOut > p.stock) {
    const ok = confirm(
      `現在庫（${p.stock}）を超える数量（${totalOut}）が出荷・破損として登録されます。在庫がマイナスになりますが続行しますか？`
    );
    if (!ok) return;
  }

  try {
    await Api.post("/api/movements/outbound", {
      product_code: code,
      location_id,
      quantity,
      damage_quantity,
      occurred_at: occurred_at ? new Date(occurred_at).toISOString() : null,
      note,
    });
    showMessage(message, `出荷を登録しました（品番: ${code} / 出荷: ${quantity} / 破損: ${damage_quantity}）`, "success");
    e.target.reset();
    document.getElementById("quantity").value = 0;
    document.getElementById("damage_quantity").value = 0;
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
