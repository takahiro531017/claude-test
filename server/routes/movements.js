const express = require("express");
const db = require("../db");

const router = express.Router();

router.get("/", (req, res) => {
  const { product_id, location_id, type, from, to, limit } = req.query;
  const clauses = [];
  const params = [];

  if (product_id) {
    clauses.push("m.product_id = ?");
    params.push(product_id);
  }
  if (location_id) {
    clauses.push("m.location_id = ?");
    params.push(location_id);
  }
  if (type) {
    clauses.push("m.type = ?");
    params.push(type);
  }
  if (from) {
    clauses.push("m.occurred_at >= ?");
    params.push(from);
  }
  if (to) {
    clauses.push("m.occurred_at <= ?");
    params.push(to);
  }

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const lim = Math.min(parseInt(limit, 10) || 200, 1000);

  const rows = db
    .prepare(
      `SELECT m.*, p.code AS product_code, p.name AS product_name, l.name AS location_name
       FROM movements m
       JOIN products p ON p.id = m.product_id
       LEFT JOIN locations l ON l.id = m.location_id
       ${where}
       ORDER BY m.occurred_at DESC, m.id DESC
       LIMIT ?`
    )
    .all(...params, lim);
  res.json(rows);
});

function resolveProductId({ product_id, product_code }) {
  if (product_id) return product_id;
  const code = (product_code || "").trim();
  if (!code) return null;
  const existing = db.prepare("SELECT id FROM products WHERE code = ?").get(code);
  if (existing) return existing.id;
  const info = db.prepare("INSERT INTO products (code) VALUES (?)").run(code);
  return info.lastInsertRowid;
}

router.post("/inbound", (req, res) => {
  const { location_id, quantity, occurred_at, note } = req.body;
  const qty = parseInt(quantity, 10);
  if (!qty || qty <= 0) return res.status(400).json({ error: "数量は1以上を入力してください" });

  const productId = resolveProductId(req.body);
  if (!productId) return res.status(400).json({ error: "商品を選択するか、品番を入力してください" });

  const info = db
    .prepare(
      `INSERT INTO movements (occurred_at, product_id, location_id, type, quantity, note)
       VALUES (?, ?, ?, 'inbound', ?, ?)`
    )
    .run(occurred_at || new Date().toISOString(), productId, location_id || null, qty, note || null);

  res.status(201).json({ id: info.lastInsertRowid, product_id: productId });
});

router.post("/outbound", (req, res) => {
  const { location_id, quantity, damage_quantity, occurred_at, note } = req.body;
  const qty = parseInt(quantity, 10) || 0;
  const damageQty = parseInt(damage_quantity, 10) || 0;
  if (qty <= 0 && damageQty <= 0) {
    return res.status(400).json({ error: "出荷数量または破損数量のいずれかを1以上で入力してください" });
  }

  const productId = resolveProductId(req.body);
  if (!productId) return res.status(400).json({ error: "商品を選択するか、品番を入力してください" });

  const when = occurred_at || new Date().toISOString();
  const insert = db.prepare(
    `INSERT INTO movements (occurred_at, product_id, location_id, type, quantity, note)
     VALUES (?, ?, ?, ?, ?, ?)`
  );

  const ids = [];
  const tx = db.transaction(() => {
    if (qty > 0) {
      const info = insert.run(when, productId, location_id || null, "outbound", qty, note || null);
      ids.push(info.lastInsertRowid);
    }
    if (damageQty > 0) {
      const info = insert.run(when, productId, location_id || null, "damage", damageQty, note || null);
      ids.push(info.lastInsertRowid);
    }
  });
  tx();

  res.status(201).json({ ids, product_id: productId });
});

router.delete("/:id", (req, res) => {
  db.prepare("DELETE FROM movements WHERE id = ?").run(req.params.id);
  res.status(204).end();
});

module.exports = router;
