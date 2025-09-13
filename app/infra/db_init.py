from .db import connect

SCHEMA_SQL = """
PRAGMA foreign_keys=ON;

-- =========================
-- CORE TABLES
-- =========================

CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY,
  uuid TEXT UNIQUE NOT NULL DEFAULT (lower(hex(randomblob(16)))),
  barcode TEXT UNIQUE,                 -- EAN-13 
  internal_sku TEXT UNIQUE,            -- internal code (optional)
  name TEXT NOT NULL,
  unit TEXT NOT NULL CHECK(unit IN ('buc','kg','l')), -- human unit of quantify lets call it
  price_per_unit_cents INTEGER NOT NULL DEFAULT 0,   -- moeny (cents)
  vat_rate INTEGER NOT NULL DEFAULT 9,               -- tva rate (ex 9/19)
  active INTEGER NOT NULL DEFAULT 1,                 -- 1  = active product
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME,
  version INTEGER NOT NULL DEFAULT 1
);

-- Batches (loturi) for traceability or expiring date
-- FK with ON DELETE CASCADE, so if you delete the product the batch is deleted as well
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY,
  uuid TEXT UNIQUE NOT NULL DEFAULT (lower(hex(randomblob(16)))),
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  lot_code TEXT,
  expiry_date DATE,
  unit_cost_cents INTEGER,             -- opțional (cost pe lot)
  supplier_name TEXT,                  -- opțional
  received_at DATETIME,                -- opțional
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME,
  version INTEGER NOT NULL DEFAULT 1
);

-- Indexes for fast filtering process
CREATE INDEX IF NOT EXISTS ix_batches_product_expiry ON batches(product_id, expiry_date);
CREATE INDEX IF NOT EXISTS ix_batches_expiry ON batches(expiry_date, product_id);

-- Append only stock movements
--Every entry, exist, adjustment its a new line, we are not rewriting the history
CREATE TABLE IF NOT EXISTS movements (
  id INTEGER PRIMARY KEY,
  uuid TEXT UNIQUE NOT NULL DEFAULT (lower(hex(randomblob(16)))),
  ts DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL,
  quantity_base INTEGER NOT NULL,      -- unități de bază: buc/grame/ml
  reason TEXT NOT NULL CHECK(reason IN ('stock_in','sale','adjustment','waste','return')),
  receipt_id INTEGER,                  -- legătură cu bonul intern (dacă e cazul)
  note TEXT
);

-- Indexes here for filtering if needed.
CREATE INDEX IF NOT EXISTS ix_movements_product_ts ON movements(product_id, ts);
CREATE INDEX IF NOT EXISTS ix_movements_batch ON movements(batch_id);
CREATE INDEX IF NOT EXISTS ix_movements_reason_ts ON movements(reason, ts);

-- Internal receipt, and status for open, closed, canceled receipt
CREATE TABLE IF NOT EXISTS receipts (
  id INTEGER PRIMARY KEY,
  uuid TEXT UNIQUE NOT NULL DEFAULT (lower(hex(randomblob(16)))),
  opened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  closed_at DATETIME,
  status TEXT NOT NULL CHECK(status IN ('open','closed','void')) DEFAULT 'open',
  total_cached_cents INTEGER           -- opțional (afișare rapidă)
);
CREATE INDEX IF NOT EXISTS ix_receipts_status ON receipts(status);

-- Linii de bon / What was sold on the receipt, in what quantity
CREATE TABLE IF NOT EXISTS receipt_lines (
  id INTEGER PRIMARY KEY,
  receipt_id INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
  qty_base INTEGER NOT NULL,
  unit_price_cents INTEGER NOT NULL,
  vat_rate INTEGER NOT NULL DEFAULT 9,
  line_total_cents INTEGER NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_receipt_lines_receipt ON receipt_lines(receipt_id);

-- Sesiuni de intrare + linii (pentru rezumat)
CREATE TABLE IF NOT EXISTS stock_in_sessions (
  id INTEGER PRIMARY KEY,
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  closed_at DATETIME,
  note TEXT
);
CREATE TABLE IF NOT EXISTS stock_in_lines (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES stock_in_sessions(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL,
  quantity_base INTEGER NOT NULL,      -- unități de bază
  unit_cost_cents INTEGER,             -- opțional
  supplier_name TEXT,                  -- opțional
  supplier_doc TEXT,                   -- opțional
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Secvențe pentru generări (ex: EAN-13 intern)
CREATE TABLE IF NOT EXISTS sequences (
  name TEXT PRIMARY KEY,
  value INTEGER NOT NULL
);
INSERT OR IGNORE INTO sequences(name, value) VALUES ('ean_internal', 100000);

-- =========================
-- VIEWS
-- =========================
CREATE VIEW IF NOT EXISTS current_stock_per_product AS
SELECT
  p.id AS product_id,
  p.name AS product_name,
  p.barcode AS barcode,
  COALESCE(SUM(m.quantity_base),0) AS stock_qty_base
FROM products p
LEFT JOIN movements m ON m.product_id = p.id
GROUP BY p.id;

CREATE VIEW IF NOT EXISTS current_stock_per_batch AS
SELECT
  b.id AS batch_id,
  b.product_id,
  b.expiry_date,
  COALESCE(SUM(m.quantity_base),0) AS stock_qty_base
FROM batches b
LEFT JOIN movements m ON m.batch_id = b.id
GROUP BY b.id;

CREATE VIEW IF NOT EXISTS expiring_soon AS
SELECT
  b.id AS batch_id,
  b.product_id,
  b.expiry_date,
  COALESCE(SUM(m.quantity_base),0) AS stock_qty_base
FROM batches b
LEFT JOIN movements m ON m.batch_id = b.id
GROUP BY b.id
HAVING COALESCE(SUM(m.quantity_base),0) > 0 AND expiry_date IS NOT NULL;

-- =========================
-- TRIGGERS (updated_at/version) - minimal
-- =========================
DROP TRIGGER IF EXISTS trg_products_au;
DROP TRIGGER IF EXISTS trg_batches_au;

CREATE TRIGGER trg_products_au
AFTER UPDATE ON products
FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at  -- optional: evita update inutil daca e setat manual
BEGIN
  UPDATE products
  SET
    updated_at = CURRENT_TIMESTAMP,
    version    = OLD.version + 1
  WHERE id = NEW.id;
END;

CREATE TRIGGER trg_batches_au
AFTER UPDATE ON batches
FOR EACH ROW
WHEN NEW.updated_at IS OLD.updated_at
BEGIN
  UPDATE batches
  SET
    updated_at = CURRENT_TIMESTAMP,
    version    = OLD.version + 1
  WHERE id = NEW.id;
END;
"""
def init_db(db_path: str):
    conn = connect(db_path)
    with conn:
        # rulează TOATA schema ca un singur script
        conn.executescript(SCHEMA_SQL)
    return conn