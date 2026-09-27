let allProducts = [];

function statusOf(p) {
  if (p.movement_count === 0) return { label: "未計上", cls: "neutral" };
  if (p.stock <= 0) return { label: "欠品", cls: "out" };
  if (p.low_stock_threshold > 0 && p.stock <= p.low_stock_threshold) return { label: "在庫僅少", cls: "low" };
  return { label: "正常", cls: "ok" };
}

function renderStats() {
  const total = allProducts.length;
  const out = allProducts.filter((p) => p.movement_count > 0 && p.stock <= 0).length;
  const low = allProducts.filter((p) => p.stock > 0 && p.low_stock_threshold > 0 && p.stock <= p.low_stock_threshold).length;
  const totalStock = allProducts.reduce((sum, p) => sum + p.stock, 0);

  document.getElementById("stats").innerHTML = `
    <div class="stat"><div class="stat-value">${total}</div><div class="stat-label">登録商品数</div></div>
    <div class="stat"><div class="stat-value">${totalStock.toLocaleString()}</div><div class="stat-label">総在庫数</div></div>
    <div class="stat"><div class="stat-value" style="color:#c2410c">${low}</div><div class="stat-label">在庫僅少</div></div>
    <div class="stat"><div class="stat-value" style="color:#dc2626">${out}</div><div class="stat-label">欠品</div></div>
  `;
}

function renderRows() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const lowOnly = document.getElementById("lowOnly").checked;

  let rows = allProducts;
  if (q) {
    rows = rows.filter(
      (p) => p.code.toLowerCase().includes(q) || (p.name || "").toLowerCase().includes(q)
    );
  }
  if (lowOnly) {
    rows = rows.filter((p) => {
      const s = statusOf(p);
      return s.cls === "low" || s.cls === "out";
    });
  }

  const tbody = document.getElementById("rows");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="5" class="empty">該当する商品がありません</td></tr>`;
    return;
  }

  tbody.innerHTML = rows
    .map((p) => {
      const s = statusOf(p);
      return `
        <tr>
          <td>${escapeHtml(p.code)}</td>
          <td>${escapeHtml(p.name || "-")}</td>
          <td class="text-right">${p.stock.toLocaleString()}</td>
          <td class="text-right">${p.low_stock_threshold || 0}</td>
          <td><span class="badge ${s.cls}">${s.label}</span></td>
        </tr>
      `;
    })
    .join("");
}

async function load() {
  const message = document.getElementById("message");
  try {
    allProducts = await Api.get("/api/products");
    clearMessage(message);
    renderStats();
    renderRows();
  } catch (e) {
    showMessage(message, e.message);
  }
}

document.getElementById("search").addEventListener("input", renderRows);
document.getElementById("lowOnly").addEventListener("change", renderRows);

load();
