"""SQLite local, chaves estrangeiras e transações que serializam alterações."""
import os
import sqlite3
import logging
from datetime import datetime
from uuid import uuid4
from contextlib import contextmanager, closing
from pathlib import Path

SCHEMA = '''
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO metadata VALUES ('schema_version', '1');
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY, supplier TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL,
 category TEXT NOT NULL DEFAULT '', material TEXT NOT NULL DEFAULT '', stone TEXT NOT NULL DEFAULT '',
 size TEXT NOT NULL DEFAULT '', collection TEXT NOT NULL DEFAULT '', image_url TEXT NOT NULL DEFAULT '',
 selling_cents INTEGER NOT NULL CHECK(selling_cents >= 0), active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(supplier, sku, material, stone, size)
);
CREATE TABLE IF NOT EXISTS invoices (
 id INTEGER PRIMARY KEY, access_key TEXT NOT NULL UNIQUE, number TEXT NOT NULL,
 issued_on TEXT NOT NULL, issuer_cnpj TEXT NOT NULL, issuer_name TEXT NOT NULL,
 recipient_cnpj TEXT NOT NULL, total_cents INTEGER NOT NULL, xml BLOB NOT NULL,
 sha256 TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS invoice_items (
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id),
 line_number TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL, quantity TEXT NOT NULL,
 cost_cents INTEGER NOT NULL, destination TEXT NOT NULL CHECK(destination IN ('estoque','despesa','ignorar')),
 product_id INTEGER REFERENCES products(id), UNIQUE(invoice_id, line_number)
);
CREATE TABLE IF NOT EXISTS sales (
 id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, sale_date TEXT NOT NULL,
 customer TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', event TEXT NOT NULL DEFAULT '',
 method TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
 subtotal_cents INTEGER NOT NULL, discount_cents INTEGER NOT NULL, revenue_cents INTEGER NOT NULL,
 cost_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL, tax_cents INTEGER NOT NULL,
 seller_cents INTEGER NOT NULL, store_cents INTEGER NOT NULL, net_cents INTEGER NOT NULL,
 cancelled_on TEXT, cancel_reason TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS sale_items (
 id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id),
 product_id INTEGER NOT NULL REFERENCES products(id), sku TEXT NOT NULL, name TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price_cents INTEGER NOT NULL,
 cost_cents INTEGER NOT NULL, UNIQUE(sale_id, product_id)
);
CREATE TABLE IF NOT EXISTS movements (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 occurred_on TEXT NOT NULL, quantity INTEGER NOT NULL, cost_cents INTEGER NOT NULL,
 kind TEXT NOT NULL, source TEXT NOT NULL, reason TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(kind, source, product_id)
);
CREATE TABLE IF NOT EXISTS receivables (
 id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id), installment INTEGER NOT NULL,
 due_on TEXT NOT NULL, gross_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL,
 paid_on TEXT, voided_on TEXT, UNIQUE(sale_id, installment)
);
CREATE TABLE IF NOT EXISTS expenses (
 id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, occurred_on TEXT NOT NULL,
 due_on TEXT NOT NULL, paid_on TEXT, category TEXT NOT NULL, description TEXT NOT NULL,
 vendor TEXT NOT NULL DEFAULT '', amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
 affects_result INTEGER NOT NULL CHECK(affects_result IN (0,1)),
 cash_effect INTEGER NOT NULL DEFAULT 1 CHECK(cash_effect IN (0,1)),
 sale_id INTEGER REFERENCES sales(id), invoice_item_id INTEGER REFERENCES invoice_items(id),
 cancelled_on TEXT, cancel_reason TEXT
);
CREATE TABLE IF NOT EXISTS audit (
 id INTEGER PRIMARY KEY, action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
 detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS movement_product_date ON movements(product_id, occurred_on);
CREATE INDEX IF NOT EXISTS sale_dates ON sales(sale_date, cancelled_on);
CREATE INDEX IF NOT EXISTS expense_dates ON expenses(occurred_on, cancelled_on);
CREATE VIEW IF NOT EXISTS inventory AS
 SELECT p.*, COALESCE(SUM(m.quantity),0) AS stock, COALESCE(SUM(m.cost_cents),0) AS stock_cents
 FROM products p LEFT JOIN movements m ON m.product_id=p.id GROUP BY p.id;
'''


class Database:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_backup = None
        with self.connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.executescript(SCHEMA)
            version = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
            if version not in {'1', '2', '3', '4', '5', '6', '7', '8'}:
                raise RuntimeError('Versão do banco incompatível; preserve o backup antes de migrar.')
        if version == '1':
            self._upgrade_v2()
        if version in {'1', '2'}:
            self._upgrade_v3()
        if version in {'1', '2', '3'}:
            self._upgrade_v4()
        if version in {'1', '2', '3', '4'}:
            self._upgrade_v5()
        if version not in {'6','7','8'}:
            self._upgrade_v6()
        if version not in {'7','8'}:
            self._upgrade_v7()
        if version != '8':
            self._upgrade_v8()
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _upgrade_v2(self):
        if self.rows('SELECT id FROM products LIMIT 1') or self.rows('SELECT id FROM expenses LIMIT 1') or self.rows('SELECT id FROM invoices LIMIT 1'):
            self.migration_backup = self.backup(self.path.parent / 'backups' /
                f'{self.path.stem}-antes-v02-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.sqlite3')
        with self.transaction() as conn:
            if conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] in {'2', '3', '4'}:
                return
            conn.execute("ALTER TABLE products ADD COLUMN history_status TEXT NOT NULL DEFAULT 'confirmed'")
            for table in ['sales', 'sale_items', 'movements']:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN cost_status TEXT NOT NULL DEFAULT 'confirmed'")
            conn.execute('ALTER TABLE movements ADD COLUMN counted_quantity INTEGER')
            conn.execute('ALTER TABLE movements ADD COLUMN input_unit_cost_cents INTEGER')
            conn.execute('CREATE TABLE history_issues (movement_id INTEGER PRIMARY KEY REFERENCES movements(id), '
                         'product_id INTEGER NOT NULL REFERENCES products(id), occurred_on TEXT NOT NULL, '
                         'missing_quantity INTEGER NOT NULL, detail TEXT NOT NULL)')
            conn.execute('CREATE TABLE deleted_sales (id INTEGER PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, '
                         'reason TEXT NOT NULL, deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            # A v0.1 guardava só o delta. Reconstrói a contagem na ordem antiga antes de recalcular.
            balances = {}
            for m in conn.execute('SELECT * FROM movements ORDER BY occurred_on,id').fetchall():
                balances[m['product_id']] = balances.get(m['product_id'], 0) + m['quantity']
                if m['kind'] == 'ADJUSTMENT':
                    from decimal import Decimal
                    from .money import rounded
                    unit = rounded(Decimal(m['cost_cents']) / m['quantity']) if m['quantity'] else 0
                    conn.execute('UPDATE movements SET counted_quantity=?,input_unit_cost_cents=? WHERE id=?',
                                 (balances[m['product_id']], unit, m['id']))
            conn.execute('DROP VIEW inventory')
            conn.execute("CREATE VIEW inventory AS SELECT p.*, COALESCE(SUM(m.quantity),0) AS stock, "
                         "CASE WHEN p.history_status='pending' THEN NULL ELSE COALESCE(SUM(m.cost_cents),0) END AS stock_cents "
                         'FROM products p LEFT JOIN movements m ON m.product_id=p.id GROUP BY p.id')
            from .ledger import rebuild_history
            rebuild_history(conn)
            conn.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
        if self.migration_backup:
            logging.info('Banco atualizado para v0.2. Backup anterior: %s', self.migration_backup)

    def _upgrade_v3(self):
        if not self.migration_backup and (self.rows('SELECT id FROM products LIMIT 1') or self.rows('SELECT id FROM expenses LIMIT 1') or self.rows('SELECT id FROM invoices LIMIT 1')):
            self.migration_backup = self.backup(self.path.parent / 'backups' /
                f'{self.path.stem}-antes-v03-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.sqlite3')
        with self.transaction() as conn:
            if conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] in {'3', '4'}:
                return
            conn.execute("ALTER TABLE invoices ADD COLUMN ownership TEXT NOT NULL DEFAULT 'own'")
            conn.execute('CREATE TABLE consignment_lots (id INTEGER PRIMARY KEY, invoice_item_id INTEGER NOT NULL UNIQUE REFERENCES invoice_items(id), product_id INTEGER NOT NULL REFERENCES products(id), received_on TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), unit_cost_cents INTEGER NOT NULL CHECK(unit_cost_cents>=0))')
            conn.execute('CREATE TABLE consignment_sale_items (id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales(id), lot_id INTEGER NOT NULL REFERENCES consignment_lots(id), product_id INTEGER NOT NULL REFERENCES products(id), sku TEXT NOT NULL, name TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), unit_price_cents INTEGER NOT NULL, cost_cents INTEGER NOT NULL, UNIQUE(sale_id,lot_id))')
            conn.execute("CREATE TABLE consignment_moves (id INTEGER PRIMARY KEY, lot_id INTEGER NOT NULL REFERENCES consignment_lots(id), occurred_on TEXT NOT NULL, quantity INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('SALE','CANCELLATION','RETURN')), sale_id INTEGER REFERENCES sales(id), request_key TEXT NOT NULL UNIQUE, reason TEXT NOT NULL)")
            conn.execute('CREATE INDEX consignment_lot_date ON consignment_moves(lot_id,occurred_on)')
            conn.execute("UPDATE metadata SET value='3' WHERE key='schema_version'")

    def _upgrade_v4(self):
        if not self.migration_backup and (self.rows('SELECT id FROM products LIMIT 1') or self.rows('SELECT id FROM expenses LIMIT 1')):
            self.migration_backup = self.backup(self.path.parent / 'backups' /
                f'{self.path.stem}-antes-v032-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}.sqlite3')
        with self.transaction() as conn:
            if conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == '4':
                return
            conn.execute('CREATE TABLE consignment_return_cancellations (movement_id INTEGER PRIMARY KEY REFERENCES consignment_moves(id), reason TEXT NOT NULL, cancelled_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
            conn.execute('CREATE VIEW active_consignment_moves AS SELECT m.* FROM consignment_moves m WHERE NOT EXISTS (SELECT 1 FROM consignment_return_cancellations c WHERE c.movement_id=m.id)')
            conn.execute("UPDATE metadata SET value='4' WHERE key='schema_version'")

    def _upgrade_v5(self):
        if not self.migration_backup and (self.rows('SELECT id FROM products LIMIT 1') or self.rows('SELECT id FROM sales LIMIT 1')):
            self.migration_backup = self.backup(self.path.parent / 'backups' / f'{self.path.stem}-antes-v05-{uuid4().hex[:12]}.sqlite3')
        with self.transaction() as c:
            if c.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == '5':
                return
            statements = [
                "CREATE TABLE beneficiaries(id INTEGER PRIMARY KEY,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '')",
                "CREATE TABLE channels(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,store_rate TEXT NOT NULL DEFAULT '0',seller_rate TEXT NOT NULL DEFAULT '0',store_beneficiary_id INTEGER REFERENCES beneficiaries(id),active INTEGER NOT NULL DEFAULT 1)",
                "CREATE TABLE channel_sellers(channel_id INTEGER NOT NULL REFERENCES channels(id),beneficiary_id INTEGER NOT NULL REFERENCES beneficiaries(id),PRIMARY KEY(channel_id,beneficiary_id))",
                "CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',birthday TEXT NOT NULL DEFAULT '',city TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',marketing_opt_in INTEGER NOT NULL DEFAULT 0,identity_key TEXT NOT NULL UNIQUE)",
                "ALTER TABLE sales ADD COLUMN operation TEXT NOT NULL DEFAULT 'sale'",
                "ALTER TABLE sales ADD COLUMN customer_id INTEGER REFERENCES customers(id)",
                "ALTER TABLE sales ADD COLUMN channel_id INTEGER REFERENCES channels(id)",
                "ALTER TABLE sales ADD COLUMN seller_id INTEGER REFERENCES beneficiaries(id)",
                "ALTER TABLE sales ADD COLUMN channel_name TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE sales ADD COLUMN seller_name TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE sales ADD COLUMN credit_beneficiary_id INTEGER REFERENCES beneficiaries(id)",
                "ALTER TABLE sales ADD COLUMN credit_cents INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE expenses ADD COLUMN beneficiary_id INTEGER REFERENCES beneficiaries(id)",
                "ALTER TABLE receivables ADD COLUMN cash_effect INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE receivables ADD COLUMN method TEXT NOT NULL DEFAULT ''",
                "CREATE TABLE commission_settlements(id INTEGER PRIMARY KEY,expense_id INTEGER NOT NULL REFERENCES expenses(id),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),settled_on TEXT NOT NULL,method TEXT NOT NULL,target_sale_id INTEGER REFERENCES sales(id),cash_expense_id INTEGER REFERENCES expenses(id),batch_key TEXT NOT NULL,UNIQUE(batch_key,expense_id))",
                "CREATE INDEX commission_expense ON commission_settlements(expense_id,settled_on)",
            ]
            for sql in statements:
                c.execute(sql)
            c.execute("INSERT INTO channels(name,kind) VALUES('Direto · Nanda','Direto')")
            c.execute("UPDATE receivables SET method=(SELECT method FROM sales WHERE sales.id=receivables.sale_id)")
            from .commerce import customer_for
            for sale in c.execute('SELECT id,customer,phone FROM sales').fetchall():
                cid,_,_=customer_for(c,sale['customer'],sale['phone'])
                c.execute('UPDATE sales SET customer_id=? WHERE id=?',(cid,sale['id']))
            c.execute("UPDATE metadata SET value='5' WHERE key='schema_version'")

    def _upgrade_v6(self):
        if not self.migration_backup:
            self.migration_backup = self.backup(self.path.parent / 'backups' / f'{self.path.stem}-antes-v06-{uuid4().hex[:12]}.sqlite3')
        with self.transaction() as c:
            c.execute('CREATE TABLE locations(id INTEGER PRIMARY KEY,name TEXT NOT NULL UNIQUE COLLATE NOCASE,active INTEGER NOT NULL DEFAULT 1)')
            c.execute("INSERT INTO locations(id,name) VALUES(1,'Local a definir'),(2,'Com Nanda')")
            c.execute('ALTER TABLE sales ADD COLUMN location_id INTEGER REFERENCES locations(id)')
            c.execute('UPDATE sales SET location_id=1')
            c.execute('ALTER TABLE channels ADD COLUMN location_id INTEGER REFERENCES locations(id)')
            c.execute('CREATE TABLE location_transfers(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL REFERENCES products(id),lot_id INTEGER REFERENCES consignment_lots(id),source_id INTEGER NOT NULL REFERENCES locations(id),target_id INTEGER NOT NULL REFERENCES locations(id),quantity INTEGER NOT NULL CHECK(quantity>0),occurred_on TEXT NOT NULL,reason TEXT NOT NULL,batch_key TEXT NOT NULL,CHECK(source_id<>target_id))')
            c.execute("UPDATE metadata SET value='6' WHERE key='schema_version'")

    def _upgrade_v7(self):
        if not self.migration_backup:
            self.migration_backup=self.backup(self.path.parent/'backups'/f'{self.path.stem}-antes-v07-{uuid4().hex[:12]}.sqlite3')
        with self.transaction() as c:
            c.execute('CREATE TABLE sale_locations(id INTEGER PRIMARY KEY,sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,product_id INTEGER NOT NULL REFERENCES products(id),lot_id INTEGER REFERENCES consignment_lots(id),location_id INTEGER NOT NULL REFERENCES locations(id),quantity INTEGER NOT NULL CHECK(quantity>0))')
            for table,lot in [('sale_items','NULL'),('consignment_sale_items','i.lot_id')]:
                c.execute(f'INSERT INTO sale_locations(sale_id,product_id,lot_id,location_id,quantity) SELECT i.sale_id,i.product_id,{lot},COALESCE(s.location_id,1),i.quantity FROM {table} i JOIN sales s ON s.id=i.sale_id')
            c.execute("UPDATE metadata SET value='7' WHERE key='schema_version'")

    def _upgrade_v8(self):
        if not self.migration_backup:
            self.migration_backup=self.backup(self.path.parent/'backups'/f'{self.path.stem}-antes-v08-{uuid4().hex[:12]}.sqlite3')
        with self.transaction() as c:
            c.execute('CREATE TABLE stock_losses(id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL REFERENCES products(id),lot_id INTEGER REFERENCES consignment_lots(id),location_id INTEGER NOT NULL REFERENCES locations(id),quantity INTEGER NOT NULL CHECK(quantity>0),occurred_on TEXT NOT NULL,reason TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,cancelled_on TEXT,cancel_reason TEXT,expense_id INTEGER REFERENCES expenses(id))')
            c.execute('DROP VIEW active_consignment_moves')
            c.execute("CREATE VIEW active_consignment_moves AS SELECT m.* FROM consignment_moves m WHERE NOT EXISTS (SELECT 1 FROM consignment_return_cancellations c WHERE c.movement_id=m.id) UNION ALL SELECT -2*id,lot_id,occurred_on,-quantity,'LOSS',NULL,'loss-'||id,reason FROM stock_losses WHERE lot_id IS NOT NULL UNION ALL SELECT -2*id+1,lot_id,cancelled_on,quantity,'LOSS_CANCEL',NULL,'loss-cancel-'||id,cancel_reason FROM stock_losses WHERE lot_id IS NOT NULL AND cancelled_on IS NOT NULL")
            c.execute("UPDATE metadata SET value='8' WHERE key='schema_version'")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=30000')
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                yield conn
                from .locations import validate_locations
                validate_locations(conn)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def rows(self, sql, args=()):
        with self.connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

    def backup(self, target):
        target = Path(target).resolve()
        if target == self.path:
            raise ValueError('O backup deve ter outro destino.')
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as source, closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
        return target
