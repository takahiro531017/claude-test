const fs = require("fs");
const path = require("path");
const db = require("./db");

const SEED_PATH = path.join(__dirname, "..", "data", "seed_data.json");

function seed() {
  const alreadyHasData = db.prepare("SELECT COUNT(*) AS n FROM products").get().n > 0;
  if (alreadyHasData) {
    console.log("すでにデータが存在するためシードをスキップしました。");
    return;
  }

  const { locations, products } = JSON.parse(fs.readFileSync(SEED_PATH, "utf-8"));

  const insertLocation = db.prepare("INSERT OR IGNORE INTO locations (name) VALUES (?)");
  const insertProduct = db.prepare("INSERT OR IGNORE INTO products (code) VALUES (?)");

  const tx = db.transaction(() => {
    for (const name of locations) insertLocation.run(name);
    for (const code of products) insertProduct.run(code);
  });
  tx();

  console.log(`シード完了: 拠点 ${locations.length}件, 商品 ${products.length}件`);
}

seed();
