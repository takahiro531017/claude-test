const path = require("path");
const fs = require("fs");
const { createClient } = require("@libsql/client");

const SCHEMA_PATH = path.join(__dirname, "schema.sql");

// TURSO_DATABASE_URL / TURSO_AUTH_TOKEN point at a Turso cloud database in
// production. Without them, data is kept in a local file so `npm start`
// still works with zero setup for local development.
const url = process.env.TURSO_DATABASE_URL || `file:${path.join(__dirname, "..", "data", "inventory.db")}`;
const authToken = process.env.TURSO_AUTH_TOKEN;

const db = createClient(authToken ? { url, authToken } : { url });

const ready = (async () => {
  const schema = fs.readFileSync(SCHEMA_PATH, "utf-8");
  await db.executeMultiple(schema);
})();

module.exports = { db, ready };
