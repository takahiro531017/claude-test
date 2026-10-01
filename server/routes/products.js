const express = require("express");
const { db } = require("../db");

const router = express.Router();

const STOCK_SELECT = `
  SELECT
    p.*,
    COALESCE(SUM(
      CASE
        WHEN m.type = 'inbound' THEN m.quantity
        WHEN m.type IN ('outbound', 'damage') THEN -m.quantity
        ELSE 0
      END
    ), 0) AS stock,
    COUNT(m.id) AS movement_count
  FROM products p
  LEFT JOIN movements m ON m.product_id = p.id
`;

router.get("/", async (req, res) => {
  const q = (req.query.q || "").trim();
  let result;
  if (q) {
    result = await db.execute({
      sql: `${STOCK_SELECT} WHERE p.code LIKE ? OR p.name LIKE ? GROUP BY p.id ORDER BY p.code`,
      args: [`%${q}%`, `%${q}%`],
    });
  } else {
    result = await db.execute(`${STOCK_SELECT} GROUP BY p.id ORDER BY p.code`);
  }
  res.json(result.rows);
});

router.get("/:id", async (req, res) => {
  const productResult = await db.execute({
    sql: `${STOCK_SELECT} WHERE p.id = ? GROUP BY p.id`,
    args: [req.params.id],
  });
  const product = productResult.rows[0];
  if (!product) return res.status(404).json({ error: "商品が見つかりません" });

  const movementsResult = await db.execute({
    sql: `SELECT m.*, l.name AS location_name
          FROM movements m
          LEFT JOIN locations l ON l.id = m.location_id
          WHERE m.product_id = ?
          ORDER BY m.occurred_at DESC, m.id DESC
          LIMIT 50`,
    args: [req.params.id],
  });

  res.json({ ...product, movements: movementsResult.rows });
});

function validateProductBody(body) {
  const code = (body.code || "").trim();
  if (!code) return "品番を入力してください";
  return null;
}

router.post("/", async (req, res) => {
  const err = validateProductBody(req.body);
  if (err) return res.status(400).json({ error: err });
  const { code, name, width_m, depth_m, height_m, volume_m3, weight_kg, low_stock_threshold } = req.body;
  try {
    const result = await db.execute({
      sql: `INSERT INTO products (code, name, width_m, depth_m, height_m, volume_m3, weight_kg, low_stock_threshold)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      args: [
        code,
        name || null,
        width_m ?? null,
        depth_m ?? null,
        height_m ?? null,
        volume_m3 ?? null,
        weight_kg ?? null,
        low_stock_threshold ?? 0,
      ],
    });
    res.status(201).json({ id: Number(result.lastInsertRowid) });
  } catch (e) {
    if (String(e.message).includes("UNIQUE")) {
      return res.status(409).json({ error: "同じ品番の商品が既に存在します" });
    }
    res.status(500).json({ error: e.message });
  }
});

router.put("/:id", async (req, res) => {
  const existingResult = await db.execute({ sql: "SELECT * FROM products WHERE id = ?", args: [req.params.id] });
  if (!existingResult.rows[0]) return res.status(404).json({ error: "商品が見つかりません" });
  const err = validateProductBody(req.body);
  if (err) return res.status(400).json({ error: err });
  const { code, name, width_m, depth_m, height_m, volume_m3, weight_kg, low_stock_threshold } = req.body;
  try {
    await db.execute({
      sql: `UPDATE products SET code=?, name=?, width_m=?, depth_m=?, height_m=?, volume_m3=?, weight_kg=?, low_stock_threshold=?
            WHERE id=?`,
      args: [
        code,
        name || null,
        width_m ?? null,
        depth_m ?? null,
        height_m ?? null,
        volume_m3 ?? null,
        weight_kg ?? null,
        low_stock_threshold ?? 0,
        req.params.id,
      ],
    });
    res.json({ ok: true });
  } catch (e) {
    if (String(e.message).includes("UNIQUE")) {
      return res.status(409).json({ error: "同じ品番の商品が既に存在します" });
    }
    res.status(500).json({ error: e.message });
  }
});

router.delete("/:id", async (req, res) => {
  const usedResult = await db.execute({
    sql: "SELECT COUNT(*) AS n FROM movements WHERE product_id = ?",
    args: [req.params.id],
  });
  if (usedResult.rows[0].n > 0) {
    return res.status(409).json({ error: "この商品は入出庫履歴で使用されているため削除できません" });
  }
  await db.execute({ sql: "DELETE FROM products WHERE id = ?", args: [req.params.id] });
  res.status(204).end();
});

module.exports = router;
