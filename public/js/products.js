let allProducts = [];

const FIELDS = ["code", "name", "width_m", "depth_m", "height_m", "volume_m3", "weight_kg", "low_stock_threshold"];

function resetForm() {
  document.getElementById("id").value = "";
  document.getElementById("form").reset();
  document.getElementById("low_stock_threshold").value = 0;
  document.getElementById("formTitle").textContent = "商品を追加";
  document.getElementById("cancelEdit").style.display = "none";
}

function fillForm(p) {
  document.getElementById("id").value = p.id;
  for (const f of FIELDS) {
    document.getElementById(f).value = p[f] ?? "";
  }
  document.getElementById("formTitle").textContent = `商品を編集: ${p.code}`;
  document.getElementById("cancelEdit").style.display = "inline-block";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderRows() {
  const q = document.getElementById("search").value.trim().toLowerCase();
  const rows = q
    ? allProducts.filter((p) => p.code.toLowerCase().includes(q) || (p.name || "").toLowerCase().includes(q))
    : allProducts;

  const tbody = document.getElementById("rows");
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty">商品がありません</td></tr>`;
    return;
  }
  tbody.innerHTML = rows
    .map(
      (p) => `
        <tr>
          <td>${escapeHtml(p.code)}</td>
          <td>${escapeHtml(p.name || "-")}</td>
          <td class="text-right">${p.stock.toLocaleString()}</td>
          <td class="text-right">${p.width_m ?? "-"}</td>
          <td class="text-right">${p.depth_m ?? "-"}</td>
          <td class="text-right">${p.height_m ?? "-"}</td>
          <td class="text-right">${p.volume_m3 ?? "-"}</td>
          <td class="text-right">${p.weight_kg ?? "-"}</td>
          <td class="text-right">${p.low_stock_threshold || 0}</td>
          <td class="actions-cell">
            <button class="secondary" data-edit="${p.id}">編集</button>
            <button class="danger" data-del="${p.id}">削除</button>
          </td>
        </tr>
      `
    )
    .join("");

  tbody.querySelectorAll("button[data-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const p = allProducts.find((x) => x.id === Number(btn.dataset.edit));
      if (p) fillForm(p);
    });
  });
  tbody.querySelectorAll("button[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("この商品を削除します。よろしいですか？")) return;
      const message = document.getElementById("message");
      try {
        await Api.delete(`/api/products/${btn.dataset.del}`);
        await load();
      } catch (e) {
        showMessage(message, e.message);
      }
    });
  });
}

async function load() {
  const message = document.getElementById("message");
  try {
    allProducts = await Api.get("/api/products");
    clearMessage(message);
    renderRows();
  } catch (e) {
    showMessage(message, e.message);
  }
}

document.getElementById("search").addEventListener("input", renderRows);
document.getElementById("cancelEdit").addEventListener("click", resetForm);

document.getElementById("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = document.getElementById("message");
  clearMessage(message);

  const id = document.getElementById("id").value;
  const payload = {};
  for (const f of FIELDS) {
    const v = document.getElementById(f).value;
    payload[f] = v === "" ? null : v;
  }

  try {
    if (id) {
      await Api.put(`/api/products/${id}`, payload);
      showMessage(message, "商品を更新しました", "success");
    } else {
      await Api.post("/api/products", payload);
      showMessage(message, "商品を追加しました", "success");
    }
    resetForm();
    await load();
  } catch (e) {
    showMessage(message, e.message);
  }
});

load();
