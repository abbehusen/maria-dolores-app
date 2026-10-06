BEGIN TRANSACTION;
CREATE TABLE audit (
 id INTEGER PRIMARY KEY, action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
 detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE deleted_sales (id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, reason TEXT NOT NULL, deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE expenses (
 id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, occurred_on TEXT NOT NULL,
 due_on TEXT NOT NULL, paid_on TEXT, category TEXT NOT NULL, description TEXT NOT NULL,
 vendor TEXT NOT NULL DEFAULT '', amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
 affects_result INTEGER NOT NULL CHECK(affects_result IN (0,1)),
 cash_effect INTEGER NOT NULL DEFAULT 1 CHECK(cash_effect IN (0,1)),
 sale_id INTEGER REFERENCES sales(id), invoice_item_id INTEGER REFERENCES invoice_items(id),
 cancelled_on TEXT, cancel_reason TEXT
);
CREATE TABLE history_issues (movement_id INTEGER PRIMARY KEY REFERENCES movements(id), product_id INTEGER NOT NULL REFERENCES products(id), occurred_on TEXT NOT NULL, missing_quantity INTEGER NOT NULL, detail TEXT NOT NULL);
CREATE TABLE invoice_items (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 line_number TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL, quantity TEXT NOT NULL,
 cost_cents INTEGER NOT NULL, destination TEXT NOT NULL CHECK(destination IN ('estoque','despesa','ignorar')),
 product_id INTEGER REFERENCES products(id), UNIQUE(invoice_id, line_number)
);
CREATE TABLE invoices (
 id INTEGER PRIMARY KEY, access_key TEXT NOT NULL UNIQUE, number TEXT NOT NULL,
 issued_on TEXT NOT NULL, issuer_cnpj TEXT NOT NULL, issuer_name TEXT NOT NULL,
 recipient_cnpj TEXT NOT NULL, total_cents INTEGER NOT NULL, xml BLOB NOT NULL,
 sha256 TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO "metadata" VALUES('schema_version','2');
CREATE TABLE movements (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 occurred_on TEXT NOT NULL, quantity INTEGER NOT NULL, cost_cents INTEGER NOT NULL,
 kind TEXT NOT NULL, source TEXT NOT NULL, reason TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, cost_status TEXT NOT NULL DEFAULT 'confirmed', counted_quantity INTEGER, input_unit_cost_cents INTEGER, UNIQUE(kind, source, product_id)
);
CREATE TABLE products (
 id INTEGER PRIMARY KEY, supplier TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL,
 category TEXT NOT NULL DEFAULT '', material TEXT NOT NULL DEFAULT '', stone TEXT NOT NULL DEFAULT '',
 size TEXT NOT NULL DEFAULT '', collection TEXT NOT NULL DEFAULT '', image_url TEXT NOT NULL DEFAULT '',
 selling_cents INTEGER NOT NULL CHECK(selling_cents >= 0), active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, history_status TEXT NOT NULL DEFAULT 'confirmed',
 UNIQUE(supplier, sku, material, stone, size)
);
CREATE TABLE receivables (
 id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id), installment INTEGER NOT NULL,
 due_on TEXT NOT NULL, gross_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL,
 paid_on TEXT, voided_on TEXT, UNIQUE(sale_id, installment)
);
CREATE TABLE sale_items (
 id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id),
 product_id INTEGER NOT NULL REFERENCES products(id), sku TEXT NOT NULL, name TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price_cents INTEGER NOT NULL,
 cost_cents INTEGER NOT NULL, cost_status TEXT NOT NULL DEFAULT 'confirmed', UNIQUE(sale_id, product_id)
);
CREATE TABLE sales (
 id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, sale_date TEXT NOT NULL,
 customer TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', event TEXT NOT NULL DEFAULT '',
 method TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
 subtotal_cents INTEGER NOT NULL, discount_cents INTEGER NOT NULL, revenue_cents INTEGER NOT NULL,
 cost_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL, tax_cents INTEGER NOT NULL,
 seller_cents INTEGER NOT NULL, store_cents INTEGER NOT NULL, net_cents INTEGER NOT NULL,
 cancelled_on TEXT, cancel_reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
, cost_status TEXT NOT NULL DEFAULT 'confirmed');
CREATE INDEX movement_product_date ON movements(product_id, occurred_on);
CREATE INDEX sale_dates ON sales(sale_date, cancelled_on);
CREATE INDEX expense_dates ON expenses(occurred_on, cancelled_on);
CREATE VIEW inventory AS SELECT p.*, COALESCE(SUM(m.quantity),0) AS stock, CASE WHEN p.history_status='pending' THEN NULL ELSE COALESCE(SUM(m.cost_cents),0) END AS stock_cents FROM products p LEFT JOIN movements m ON m.product_id=p.id GROUP BY p.id;
COMMIT;