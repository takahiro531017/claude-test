async function load() {
  const message = document.getElementById("message");
  try {
    const rows = await Api.get("/api/locations");
    clearMessage(message);
    const tbody = document.getElementById("rows");
    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="2" class="empty">拠点がありません</td></tr>`;
      return;
    }
    tbody.innerHTML = rows
      .map(
        (l) => `
          <tr>
            <td>${escapeHtml(l.name)}</td>
            <td class="actions-cell"><button class="danger" data-del="${l.id}">削除</button></td>
          </tr>
        `
      )
      .join("");
    tbody.querySelectorAll("button[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!confirm("この拠点を削除します。よろしいですか？")) return;
        try {
          await Api.delete(`/api/locations/${btn.dataset.del}`);
          await load();
        } catch (e) {
          showMessage(message, e.message);
        }
      });
    });
  } catch (e) {
    showMessage(message, e.message);
  }
}

document.getElementById("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = document.getElementById("message");
  clearMessage(message);
  const name = document.getElementById("name").value.trim();
  try {
    await Api.post("/api/locations", { name });
    document.getElementById("name").value = "";
    showMessage(message, "拠点を追加しました", "success");
    await load();
  } catch (e) {
    showMessage(message, e.message);
  }
});

load();
