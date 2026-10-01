const express = require("express");
const { db } = require("../db");

const router = express.Router();

router.get("/", async (req, res) => {
  const result = await db.execute("SELECT * FROM locations ORDER BY name");
  res.json(result.rows);
});

router.post("/", async (req, res) => {
  const name = (req.body.name || "").trim();
  if (!name) return res.status(400).json({ error: "拠点名を入力してください" });
  try {
    const result = await db.execute({ sql: "INSERT INTO locations (name) VALUES (?)", args: [name] });
    res.status(201).json({ id: Number(result.lastInsertRowid), name });
  } catch (e) {
    if (String(e.message).includes("UNIQUE")) {
      return res.status(409).json({ error: "同じ名前の拠点が既に存在します" });
    }
    res.status(500).json({ error: e.message });
  }
});

router.delete("/:id", async (req, res) => {
  const usedResult = await db.execute({
    sql: "SELECT COUNT(*) AS n FROM movements WHERE location_id = ?",
    args: [req.params.id],
  });
  if (usedResult.rows[0].n > 0) {
    return res.status(409).json({ error: "この拠点は入出庫履歴で使用されているため削除できません" });
  }
  await db.execute({ sql: "DELETE FROM locations WHERE id = ?", args: [req.params.id] });
  res.status(204).end();
});

module.exports = router;
