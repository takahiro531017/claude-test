function typeBadge(type) {
  const map = { inbound: ["入庫", "type-inbound"], outbound: ["出荷", "type-outbound"], damage: ["破損", "type-damage"] };
  const [label, cls] = map[type] || [type, ""];
  return `<span class="badge ${cls}">${label}</span>`;
}

async function loadFilters() {
  const [prods, locs] = await Promise.all([Api.get("/api/products"), Api.get("/api/locations")]);
  document.getElementById("product-list").innerHTML = prods
    .map((p) => `<option value="${escapeHtml(p.code)}"></option>`)
    .join("");
  document.getElementById("fLocation").innerHTML =
    `<option value="">すべて</option>` + locs.map((l) => `<option value="${l.id}">${escapeHtml(l.name)}</option>`).join("");
}

async function loadRows() {
  const message = document.getElementById("message");
  clearMessage(message);

  const params = new URLSearchParams();
  const code = document.getElementById("fProduct").value.trim();
  const locationId = document.getElementById("fLocation").value;
  const type = document.getElementById("fType").value;
  const from = document.getElementById("fFrom").value;
  const to = document.getElementById("fTo").value;

  if (locationId) params.set("location_id", locationId);
  if (type) params.set("type", type);
  if (from) params.set("from", from);
  if (to) params.set("to", `${to}T23:59:59`);
  params.set("limit", "300");

  try {
    let rows = await Api.get(`/api/movements?${params.toString()}`);
    if (code) rows = rows.filter((m) => m.product_code === code);

    const tbody = document.getElementById("rows");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="empty">該当する履歴がありません</td></tr>`;
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
            <td class="actions-cell"><button class="danger" data-id="${m.id}">削除</button></td>
          </tr>
        `
      )
      .join("");

    tbody.querySelectorAll("button[data-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("この履歴を削除します。よろしいですか？（在庫数の再計算に反映されます）")) return;
        try {
          await Api.delete(`/api/movements/${btn.dataset.id}`);
          await loadRows();
        } catch (e) {
          showMessage(message, e.message);
        }
      });
    });
  } catch (e) {
    showMessage(message, e.message);
  }
}

document.getElementById("filterBtn").addEventListener("click", loadRows);
document.getElementById("resetBtn").addEventListener("click", () => {
  document.getElementById("fProduct").value = "";
  document.getElementById("fLocation").value = "";
  document.getElementById("fType").value = "";
  document.getElementById("fFrom").value = "";
  document.getElementById("fTo").value = "";
  loadRows();
});

loadFilters();
loadRows();
