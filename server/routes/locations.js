const express = require("express");
const db = require("../db");

const router = express.Router();

router.get("/", (req, res) => {
  const rows = db.prepare("SELECT * FROM locations ORDER BY name").all();
  res.json(rows);
});

router.post("/", (req, res) => {
  const name = (req.body.name || "").trim();
  if (!name) return res.status(400).json({ error: "拠点名を入力してください" });
  try {
    const info = db.prepare("INSERT INTO locations (name) VALUES (?)").run(name);
    res.status(201).json({ id: info.lastInsertRowid, name });
  } catch (e) {
    if (String(e.message).includes("UNIQUE")) {
      return res.status(409).json({ error: "同じ名前の拠点が既に存在します" });
    }
    res.status(500).json({ error: e.message });
  }
});

router.delete("/:id", (req, res) => {
  const used = db.prepare("SELECT COUNT(*) AS n FROM movements WHERE location_id = ?").get(req.params.id).n;
  if (used > 0) {
    return res.status(409).json({ error: "この拠点は入出庫履歴で使用されているため削除できません" });
  }
  db.prepare("DELETE FROM locations WHERE id = ?").run(req.params.id);
  res.status(204).end();
});

module.exports = router;
