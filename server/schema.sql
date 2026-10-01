CREATE TABLE IF NOT EXISTS locations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT,
  width_m REAL,
  depth_m REAL,
  height_m REAL,
  volume_m3 REAL,
  weight_kg REAL,
  low_stock_threshold INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  product_id INTEGER NOT NULL REFERENCES products(id),
  location_id INTEGER REFERENCES locations(id),
  type TEXT NOT NULL CHECK (type IN ('inbound', 'outbound', 'damage')),
  quantity INTEGER NOT NULL CHECK (quantity > 0),
  note TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_movements_product ON movements(product_id);
CREATE INDEX IF NOT EXISTS idx_movements_location ON movements(location_id);
CREATE INDEX IF NOT EXISTS idx_movements_occurred_at ON movements(occurred_at);
