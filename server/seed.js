const fs = require("fs");
const path = require("path");
const { db, ready } = require("./db");

const SEED_PATH = path.join(__dirname, "..", "data", "seed_data.json");

async function seed() {
  await ready;

  const countRes = await db.execute("SELECT COUNT(*) AS n FROM products");
  const alreadyHasData = countRes.rows[0].n > 0;
  if (alreadyHasData) {
    console.log("すでにデータが存在するためシードをスキップしました。");
    return;
  }

  const { locations, products } = JSON.parse(fs.readFileSync(SEED_PATH, "utf-8"));

  const statements = [
    ...locations.map((name) => ({ sql: "INSERT OR IGNORE INTO locations (name) VALUES (?)", args: [name] })),
    ...products.map((code) => ({ sql: "INSERT OR IGNORE INTO products (code) VALUES (?)", args: [code] })),
  ];
  await db.batch(statements, "write");

  console.log(`シード完了: 拠点 ${locations.length}件, 商品 ${products.length}件`);
}

module.exports = seed();
