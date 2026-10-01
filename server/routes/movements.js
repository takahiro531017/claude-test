const express = require("express");
const { db } = require("../db");

const router = express.Router();

router.get("/", async (req, res) => {
  const { product_id, location_id, type, from, to, limit } = req.query;
  const clauses = [];
  const args = [];

  if (product_id) {
    clauses.push("m.product_id = ?");
    args.push(product_id);
  }
  if (location_id) {
    clauses.push("m.location_id = ?");
    args.push(location_id);
  }
  if (type) {
    clauses.push("m.type = ?");
    args.push(type);
  }
  if (from) {
    clauses.push("m.occurred_at >= ?");
    args.push(from);
  }
  if (to) {
    clauses.push("m.occurred_at <= ?");
    args.push(to);
  }

  const where = clauses.length ? `WHERE ${clauses.join(" AND ")}` : "";
  const lim = Math.min(parseInt(limit, 10) || 200, 1000);
  args.push(lim);

  const result = await db.execute({
    sql: `SELECT m.*, p.code AS product_code, p.name AS product_name, l.name AS location_name
          FROM movements m
          JOIN products p ON p.id = m.product_id
          LEFT JOIN locations l ON l.id = m.location_id
          ${where}
          ORDER BY m.occurred_at DESC, m.id DESC
          LIMIT ?`,
    args,
  });
  res.json(result.rows);
});

async function resolveProductId({ product_id, product_code }) {
  if (product_id) return product_id;
  const code = (product_code || "").trim();
  if (!code) return null;
  const existingResult = await db.execute({ sql: "SELECT id FROM products WHERE code = ?", args: [code] });
  if (existingResult.rows[0]) return existingResult.rows[0].id;
  const insertResult = await db.execute({ sql: "INSERT INTO products (code) VALUES (?)", args: [code] });
  return Number(insertResult.lastInsertRowid);
}

router.post("/inbound", async (req, res) => {
  const { location_id, quantity, occurred_at, note } = req.body;
  const qty = parseInt(quantity, 10);
  if (!qty || qty <= 0) return res.status(400).json({ error: "数量は1以上を入力してください" });

  const productId = await resolveProductId(req.body);
  if (!productId) return res.status(400).json({ error: "商品を選択するか、品番を入力してください" });

  const result = await db.execute({
    sql: `INSERT INTO movements (occurred_at, product_id, location_id, type, quantity, note)
          VALUES (?, ?, ?, 'inbound', ?, ?)`,
    args: [occurred_at || new Date().toISOString(), productId, location_id || null, qty, note || null],
  });

  res.status(201).json({ id: Number(result.lastInsertRowid), product_id: productId });
});

router.post("/outbound", async (req, res) => {
  const { location_id, quantity, damage_quantity, occurred_at, note } = req.body;
  const qty = parseInt(quantity, 10) || 0;
  const damageQty = parseInt(damage_quantity, 10) || 0;
  if (qty <= 0 && damageQty <= 0) {
    return res.status(400).json({ error: "出荷数量または破損数量のいずれかを1以上で入力してください" });
  }

  const productId = await resolveProductId(req.body);
  if (!productId) return res.status(400).json({ error: "商品を選択するか、品番を入力してください" });

  const when = occurred_at || new Date().toISOString();
  const statements = [];
  if (qty > 0) {
    statements.push({
      sql: `INSERT INTO movements (occurred_at, product_id, location_id, type, quantity, note)
            VALUES (?, ?, ?, 'outbound', ?, ?)`,
      args: [when, productId, location_id || null, qty, note || null],
    });
  }
  if (damageQty > 0) {
    statements.push({
      sql: `INSERT INTO movements (occurred_at, product_id, location_id, type, quantity, note)
            VALUES (?, ?, ?, 'damage', ?, ?)`,
      args: [when, productId, location_id || null, damageQty, note || null],
    });
  }
  await db.batch(statements, "write");

  res.status(201).json({ product_id: productId });
});

router.delete("/:id", async (req, res) => {
  await db.execute({ sql: "DELETE FROM movements WHERE id = ?", args: [req.params.id] });
  res.status(204).end();
});

module.exports = router;
