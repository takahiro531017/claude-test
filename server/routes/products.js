const express = require("express");
const db = require("../db");

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

router.get("/", (req, res) => {
  const q = (req.query.q || "").trim();
  let rows;
  if (q) {
    rows = db
      .prepare(`${STOCK_SELECT} WHERE p.code LIKE ? OR p.name LIKE ? GROUP BY p.id ORDER BY p.code`)
      .all(`%${q}%`, `%${q}%`);
  } else {
    rows = db.prepare(`${STOCK_SELECT} GROUP BY p.id ORDER BY p.code`).all();
  }
  res.json(rows);
});

router.get("/:id", (req, res) => {
  const product = db.prepare(`${STOCK_SELECT} WHERE p.id = ? GROUP BY p.id`).get(req.params.id);
  if (!product) return res.status(404).json({ error: "商品が見つかりません" });
  const movements = db
    .prepare(
      `SELECT m.*, l.name AS location_name
       FROM movements m
       LEFT JOIN locations l ON l.id = m.location_id
       WHERE m.product_id = ?
       ORDER BY m.occurred_at DESC, m.id DESC
       LIMIT 50`
    )
    .all(req.params.id);
  res.json({ ...product, movements });
});

function validateProductBody(body) {
  const code = (body.code || "").trim();
  if (!code) return "品番を入力してください";
  return null;
}

router.post("/", (req, res) => {
  const err = validateProductBody(req.body);
  if (err) return res.status(400).json({ error: err });
  const { code, name, width_m, depth_m, height_m, volume_m3, weight_kg, low_stock_threshold } = req.body;
  try {
    const info = db
      .prepare(
        `INSERT INTO products (code, name, width_m, depth_m, height_m, volume_m3, weight_kg, low_stock_threshold)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        code,
        name || null,
        width_m ?? null,
        depth_m ?? null,
        height_m ?? null,
        volume_m3 ?? null,
        weight_kg ?? null,
        low_stock_threshold ?? 0
      );
    res.status(201).json({ id: info.lastInsertRowid });
  } catch (e) {
    if (String(e.message).includes("UNIQUE")) {
      return res.status(409).json({ error: "同じ品番の商品が既に存在します" });
    }
    res.status(500).json({ error: e.message });
  }
});

router.put("/:id", (req, res) => {
  const existing = db.prepare("SELECT * FROM products WHERE id = ?").get(req.params.id);
  if (!existing) return res.status(404).json({ error: "商品が見つかりません" });
  const err = validateProductBody(req.body);
  if (err) return res.status(400).json({ error: err });
  const { code, name, width_m, depth_m, height_m, volume_m3, weight_kg, low_stock_threshold } = req.body;
  try {
    db.prepare(
      `UPDATE products SET code=?, name=?, width_m=?, depth_m=?, height_m=?, volume_m3=?, weight_kg=?, low_stock_threshold=?
       WHERE id=?`
    ).run(
      code,
      name || null,
      width_m ?? null,
      depth_m ?? null,
      height_m ?? null,
      volume_m3 ?? null,
      weight_kg ?? null,
      low_stock_threshold ?? 0,
      req.params.id
    );
    res.json({ ok: true });
  } catch (e) {
    if (String(e.message).includes("UNIQUE")) {
      return res.status(409).json({ error: "同じ品番の商品が既に存在します" });
    }
    res.status(500).json({ error: e.message });
  }
});

router.delete("/:id", (req, res) => {
  const used = db.prepare("SELECT COUNT(*) AS n FROM movements WHERE product_id = ?").get(req.params.id).n;
  if (used > 0) {
    return res.status(409).json({ error: "この商品は入出庫履歴で使用されているため削除できません" });
  }
  db.prepare("DELETE FROM products WHERE id = ?").run(req.params.id);
  res.status(204).end();
});

module.exports = router;
