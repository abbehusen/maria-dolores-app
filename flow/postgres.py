"""PostgreSQL compatibility layer for the existing sqlite-oriented business code.

The application intentionally keeps SQL in the business modules simple.  This
module adapts qmark placeholders and a few SQLite introspection idioms so the
same code can run against Supabase/PostgreSQL without duplicating the business
rules.
"""
from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path


POSTGRES_SCHEMA = r'''
CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO metadata(key,value) VALUES ('schema_version','8') ON CONFLICT (key) DO NOTHING;

CREATE TABLE IF NOT EXISTS products (
 id BIGSERIAL PRIMARY KEY, supplier TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL,
 category TEXT NOT NULL DEFAULT '', material TEXT NOT NULL DEFAULT '', stone TEXT NOT NULL DEFAULT '',
 size TEXT NOT NULL DEFAULT '', collection TEXT NOT NULL DEFAULT '', image_url TEXT NOT NULL DEFAULT '',
 selling_cents BIGINT NOT NULL CHECK(selling_cents >= 0), active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text), history_status TEXT NOT NULL DEFAULT 'confirmed',
 UNIQUE(supplier, sku, material, stone, size)
);
CREATE TABLE IF NOT EXISTS invoices (
 id BIGSERIAL PRIMARY KEY, access_key TEXT NOT NULL UNIQUE, number TEXT NOT NULL,
 issued_on TEXT NOT NULL, issuer_cnpj TEXT NOT NULL, issuer_name TEXT NOT NULL,
 recipient_cnpj TEXT NOT NULL, total_cents BIGINT NOT NULL, xml BYTEA NOT NULL,
 sha256 TEXT NOT NULL, imported_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
 ownership TEXT NOT NULL DEFAULT 'own'
);
CREATE TABLE IF NOT EXISTS invoice_items (
 id BIGSERIAL PRIMARY KEY, invoice_id BIGINT NOT NULL REFERENCES invoices(id),
 line_number TEXT NOT NULL, sku TEXT NOT NULL, name TEXT NOT NULL, quantity TEXT NOT NULL,
 cost_cents BIGINT NOT NULL, destination TEXT NOT NULL CHECK(destination IN ('estoque','despesa','ignorar')),
 product_id BIGINT REFERENCES products(id), UNIQUE(invoice_id, line_number)
);
CREATE TABLE IF NOT EXISTS beneficiaries(
 id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS customers(
 id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL,phone TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',
 birthday TEXT NOT NULL DEFAULT '',city TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',
 marketing_opt_in INTEGER NOT NULL DEFAULT 0,identity_key TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS locations(
 id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,active INTEGER NOT NULL DEFAULT 1
);
INSERT INTO locations(id,name) VALUES(1,'Local a definir'),(2,'Com Nanda') ON CONFLICT DO NOTHING;
CREATE UNIQUE INDEX IF NOT EXISTS locations_name_nocase ON locations ((lower(name)));
CREATE TABLE IF NOT EXISTS channels(
 id BIGSERIAL PRIMARY KEY,name TEXT NOT NULL UNIQUE,kind TEXT NOT NULL,
 store_rate TEXT NOT NULL DEFAULT '0',seller_rate TEXT NOT NULL DEFAULT '0',
 store_beneficiary_id BIGINT REFERENCES beneficiaries(id),active INTEGER NOT NULL DEFAULT 1,
 location_id BIGINT REFERENCES locations(id)
);
CREATE TABLE IF NOT EXISTS channel_sellers(
 channel_id BIGINT NOT NULL REFERENCES channels(id),beneficiary_id BIGINT NOT NULL REFERENCES beneficiaries(id),
 PRIMARY KEY(channel_id,beneficiary_id)
);
CREATE TABLE IF NOT EXISTS sales (
 id BIGSERIAL PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, sale_date TEXT NOT NULL,
 customer TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', event TEXT NOT NULL DEFAULT '',
 method TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '', subtotal_cents BIGINT NOT NULL,
 discount_cents BIGINT NOT NULL, revenue_cents BIGINT NOT NULL, cost_cents BIGINT NOT NULL,
 fee_cents BIGINT NOT NULL, tax_cents BIGINT NOT NULL, seller_cents BIGINT NOT NULL,
 store_cents BIGINT NOT NULL, net_cents BIGINT NOT NULL, cancelled_on TEXT, cancel_reason TEXT,
 created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text), cost_status TEXT NOT NULL DEFAULT 'confirmed',
 operation TEXT NOT NULL DEFAULT 'sale', customer_id BIGINT REFERENCES customers(id),
 channel_id BIGINT REFERENCES channels(id), seller_id BIGINT REFERENCES beneficiaries(id),
 channel_name TEXT NOT NULL DEFAULT '', seller_name TEXT NOT NULL DEFAULT '',
 credit_beneficiary_id BIGINT REFERENCES beneficiaries(id), credit_cents BIGINT NOT NULL DEFAULT 0,
 location_id BIGINT REFERENCES locations(id)
);
CREATE TABLE IF NOT EXISTS sale_items (
 id BIGSERIAL PRIMARY KEY, sale_id BIGINT NOT NULL REFERENCES sales(id),
 product_id BIGINT NOT NULL REFERENCES products(id), sku TEXT NOT NULL, name TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity > 0), unit_price_cents BIGINT NOT NULL,
 cost_cents BIGINT NOT NULL, cost_status TEXT NOT NULL DEFAULT 'confirmed', UNIQUE(sale_id, product_id)
);
CREATE TABLE IF NOT EXISTS movements (
 id BIGSERIAL PRIMARY KEY, product_id BIGINT NOT NULL REFERENCES products(id), occurred_on TEXT NOT NULL,
 quantity INTEGER NOT NULL, cost_cents BIGINT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL,
 reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text),
 cost_status TEXT NOT NULL DEFAULT 'confirmed', counted_quantity INTEGER, input_unit_cost_cents BIGINT,
 UNIQUE(kind, source, product_id)
);
CREATE TABLE IF NOT EXISTS receivables (
 id BIGSERIAL PRIMARY KEY, sale_id BIGINT NOT NULL REFERENCES sales(id), installment INTEGER NOT NULL,
 due_on TEXT NOT NULL, gross_cents BIGINT NOT NULL, fee_cents BIGINT NOT NULL, paid_on TEXT, voided_on TEXT,
 cash_effect INTEGER NOT NULL DEFAULT 1, method TEXT NOT NULL DEFAULT '', UNIQUE(sale_id, installment)
);
CREATE TABLE IF NOT EXISTS expenses (
 id BIGSERIAL PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, occurred_on TEXT NOT NULL, due_on TEXT NOT NULL,
 paid_on TEXT, category TEXT NOT NULL, description TEXT NOT NULL, vendor TEXT NOT NULL DEFAULT '',
 amount_cents BIGINT NOT NULL CHECK(amount_cents >= 0), affects_result INTEGER NOT NULL CHECK(affects_result IN (0,1)),
 cash_effect INTEGER NOT NULL DEFAULT 1 CHECK(cash_effect IN (0,1)), sale_id BIGINT REFERENCES sales(id),
 invoice_item_id BIGINT REFERENCES invoice_items(id), cancelled_on TEXT, cancel_reason TEXT,
 beneficiary_id BIGINT REFERENCES beneficiaries(id)
);
CREATE TABLE IF NOT EXISTS audit (
 id BIGSERIAL PRIMARY KEY, action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT NOT NULL,
 detail TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text)
);
CREATE TABLE IF NOT EXISTS history_issues (
 movement_id BIGINT PRIMARY KEY REFERENCES movements(id), product_id BIGINT NOT NULL REFERENCES products(id),
 occurred_on TEXT NOT NULL, missing_quantity INTEGER NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS deleted_sales (
 id BIGINT PRIMARY KEY, request_key TEXT NOT NULL UNIQUE, reason TEXT NOT NULL,
 deleted_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text)
);
CREATE TABLE IF NOT EXISTS consignment_lots (
 id BIGSERIAL PRIMARY KEY, invoice_item_id BIGINT NOT NULL UNIQUE REFERENCES invoice_items(id),
 product_id BIGINT NOT NULL REFERENCES products(id), received_on TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), unit_cost_cents BIGINT NOT NULL CHECK(unit_cost_cents>=0)
);
CREATE TABLE IF NOT EXISTS consignment_sale_items (
 id BIGSERIAL PRIMARY KEY, sale_id BIGINT NOT NULL REFERENCES sales(id), lot_id BIGINT NOT NULL REFERENCES consignment_lots(id),
 product_id BIGINT NOT NULL REFERENCES products(id), sku TEXT NOT NULL, name TEXT NOT NULL,
 quantity INTEGER NOT NULL CHECK(quantity>0), unit_price_cents BIGINT NOT NULL, cost_cents BIGINT NOT NULL,
 UNIQUE(sale_id,lot_id)
);
CREATE TABLE IF NOT EXISTS consignment_moves (
 id BIGSERIAL PRIMARY KEY, lot_id BIGINT NOT NULL REFERENCES consignment_lots(id), occurred_on TEXT NOT NULL,
 quantity INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('SALE','CANCELLATION','RETURN')),
 sale_id BIGINT REFERENCES sales(id), request_key TEXT NOT NULL UNIQUE, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS consignment_return_cancellations (
 movement_id BIGINT PRIMARY KEY REFERENCES consignment_moves(id), reason TEXT NOT NULL,
 cancelled_at TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text)
);
CREATE TABLE IF NOT EXISTS commission_settlements(
 id BIGSERIAL PRIMARY KEY,expense_id BIGINT NOT NULL REFERENCES expenses(id),amount_cents BIGINT NOT NULL CHECK(amount_cents>0),
 settled_on TEXT NOT NULL,method TEXT NOT NULL,target_sale_id BIGINT REFERENCES sales(id),
 cash_expense_id BIGINT REFERENCES expenses(id),batch_key TEXT NOT NULL,UNIQUE(batch_key,expense_id)
);
CREATE TABLE IF NOT EXISTS location_transfers(
 id BIGSERIAL PRIMARY KEY,product_id BIGINT NOT NULL REFERENCES products(id),lot_id BIGINT REFERENCES consignment_lots(id),
 source_id BIGINT NOT NULL REFERENCES locations(id),target_id BIGINT NOT NULL REFERENCES locations(id),
 quantity INTEGER NOT NULL CHECK(quantity>0),occurred_on TEXT NOT NULL,reason TEXT NOT NULL,batch_key TEXT NOT NULL,
 CHECK(source_id<>target_id)
);
CREATE TABLE IF NOT EXISTS sale_locations(
 id BIGSERIAL PRIMARY KEY,sale_id BIGINT NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
 product_id BIGINT NOT NULL REFERENCES products(id),lot_id BIGINT REFERENCES consignment_lots(id),
 location_id BIGINT NOT NULL REFERENCES locations(id),quantity INTEGER NOT NULL CHECK(quantity>0)
);
CREATE TABLE IF NOT EXISTS stock_losses(
 id BIGSERIAL PRIMARY KEY,product_id BIGINT NOT NULL REFERENCES products(id),lot_id BIGINT REFERENCES consignment_lots(id),
 location_id BIGINT NOT NULL REFERENCES locations(id),quantity INTEGER NOT NULL CHECK(quantity>0),occurred_on TEXT NOT NULL,
 reason TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,cancelled_on TEXT,cancel_reason TEXT,expense_id BIGINT REFERENCES expenses(id)
);

CREATE INDEX IF NOT EXISTS movement_product_date ON movements(product_id, occurred_on);
CREATE INDEX IF NOT EXISTS sale_dates ON sales(sale_date, cancelled_on);
CREATE INDEX IF NOT EXISTS expense_dates ON expenses(occurred_on, cancelled_on);
CREATE INDEX IF NOT EXISTS consignment_lot_date ON consignment_moves(lot_id,occurred_on);
CREATE INDEX IF NOT EXISTS commission_expense ON commission_settlements(expense_id,settled_on);

CREATE OR REPLACE VIEW inventory AS
 SELECT p.*, COALESCE(SUM(m.quantity),0)::bigint AS stock,
 CASE WHEN p.history_status='pending' THEN NULL ELSE COALESCE(SUM(m.cost_cents),0)::bigint END AS stock_cents
 FROM products p LEFT JOIN movements m ON m.product_id=p.id GROUP BY p.id;

CREATE OR REPLACE VIEW active_consignment_moves AS
 SELECT m.id,m.lot_id,m.occurred_on,m.quantity,m.kind,m.sale_id,m.request_key,m.reason
 FROM consignment_moves m
 WHERE NOT EXISTS (SELECT 1 FROM consignment_return_cancellations c WHERE c.movement_id=m.id)
 UNION ALL
 SELECT -2*id,lot_id,occurred_on,-quantity,'LOSS',NULL,'loss-'||id::text,reason
 FROM stock_losses WHERE lot_id IS NOT NULL
 UNION ALL
 SELECT -2*id+1,lot_id,cancelled_on,quantity,'LOSS_CANCEL',NULL,'loss-cancel-'||id::text,cancel_reason
 FROM stock_losses WHERE lot_id IS NOT NULL AND cancelled_on IS NOT NULL;
'''

ID_TABLES = {
    'products','invoices','invoice_items','beneficiaries','customers','locations','channels','sales',
    'sale_items','movements','receivables','expenses','audit','consignment_lots','consignment_sale_items',
    'consignment_moves','commission_settlements','location_transfers','sale_locations','stock_losses'
}

TABLES = [
    'metadata','products','invoices','invoice_items','beneficiaries','customers','locations','channels','channel_sellers',
    'sales','sale_items','movements','receivables','expenses','audit','history_issues','deleted_sales','consignment_lots',
    'consignment_sale_items','consignment_moves','consignment_return_cancellations','commission_settlements',
    'location_transfers','sale_locations','stock_losses'
]


class CompatRow(Mapping):
    def __init__(self, names, values):
        self._names = list(names)
        self._values = tuple(values)
        self._data = dict(zip(self._names, self._values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._data[key]

    def __iter__(self):
        return iter(self._names)

    def __len__(self):
        return len(self._names)

    def keys(self):
        return self._data.keys()

    def __repr__(self):
        return repr(self._data)


def _qmark_to_format(sql: str) -> str:
    out = []
    quote = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out.append(sql[i + 1]); i += 1
                else:
                    quote = None
        else:
            if ch in ("'", '"'):
                quote = ch; out.append(ch)
            elif ch == '?':
                out.append('%s')
            else:
                out.append(ch)
        i += 1
    return ''.join(out)


def _normalize_sql(sql: str) -> str:
    sql = sql.replace(' COLLATE NOCASE', '')
    sql = re.sub(r'INSERT\s+OR\s+IGNORE\s+INTO', 'INSERT INTO', sql, flags=re.I)
    # SQLite accepts SUM(boolean); PostgreSQL needs an explicit cast.
    sql = re.sub(r"SUM\(\s*cost_status\s*=\s*'pending'\s*\)", "SUM((cost_status='pending')::int)", sql, flags=re.I)
    sql = _qmark_to_format(sql)
    return sql


class PgCursor:
    def __init__(self, conn, raw):
        self._conn = conn
        self._raw = raw
        self.lastrowid = None
        self._buffer = None

    @property
    def description(self):
        return self._raw.description

    def _row(self, values):
        if values is None:
            return None
        names = [d.name if hasattr(d, 'name') else d[0] for d in self._raw.description]
        return CompatRow(names, values)

    def fetchone(self):
        if self._buffer is not None:
            value = self._buffer
            self._buffer = None
            return value
        return self._row(self._raw.fetchone())

    def fetchall(self):
        rows = []
        if self._buffer is not None:
            rows.append(self._buffer); self._buffer = None
        rows.extend(self._row(r) for r in self._raw.fetchall())
        return rows

    def __iter__(self):
        if self._buffer is not None:
            yield self._buffer
            self._buffer = None
        for row in self._raw:
            yield self._row(row)


class PgConnection:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, args=()):
        stripped = sql.strip()
        lower = stripped.lower()

        # SQLite introspection used by compatibility guards in the legacy modules.
        m = re.search(r"select\s+1\s+from\s+sqlite_master\s+where\s+name\s*=\s*'([^']+)'", lower, re.I)
        if m:
            raw = self._raw.cursor()
            raw.execute("SELECT 1 WHERE to_regclass(%s) IS NOT NULL", (m.group(1),))
            return PgCursor(self, raw)
        if lower.startswith('pragma table_info('):
            table = re.search(r'pragma\s+table_info\(([^)]+)\)', lower, re.I).group(1).strip(" '\"")
            raw = self._raw.cursor()
            raw.execute("SELECT ordinal_position-1 AS cid,column_name AS name,data_type AS type,'' AS notnull,'' AS dflt_value,'' AS pk FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (table,))
            return PgCursor(self, raw)
        if lower.startswith('pragma '):
            raw = self._raw.cursor(); raw.execute('SELECT 1'); return PgCursor(self, raw)

        normalized = _normalize_sql(sql)
        ignore = bool(re.match(r'\s*insert\s+or\s+ignore\s+', sql, re.I))
        if ignore and ' on conflict ' not in normalized.lower():
            normalized = normalized.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'

        table = None
        insert = re.match(r'\s*insert\s+into\s+([a-zA-Z_][\w]*)', normalized, re.I)
        wants_id = False
        if insert:
            table = insert.group(1).lower()
            wants_id = table in ID_TABLES and ' returning ' not in normalized.lower()
            if wants_id:
                normalized = normalized.rstrip().rstrip(';') + ' RETURNING id'

        raw = self._raw.cursor()
        raw.execute(normalized, args)
        cursor = PgCursor(self, raw)
        if wants_id:
            returned = raw.fetchone()
            cursor.lastrowid = returned[0] if returned else None
        return cursor

    def commit(self):
        self._raw.commit()

    def rollback(self):
        self._raw.rollback()

    def close(self):
        self._raw.close()


class PostgresDatabase:
    is_postgres = True

    def __init__(self, url, local_path=None):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError('PostgreSQL requer psycopg. Instale as dependências de requirements.txt.') from exc
        self._psycopg = psycopg
        self.url = url
        self.path = Path(local_path or 'data/flow.sqlite3').resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migration_backup = None
        with psycopg.connect(self.url) as conn:
            # psycopg can execute a multi-statement schema string directly.
            conn.execute(POSTGRES_SCHEMA)
            version = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
            if version != '8':
                raise RuntimeError(f'Versão PostgreSQL incompatível: {version}. Esperado schema 8.')
            conn.commit()

    @contextmanager
    def connect(self):
        raw = self._psycopg.connect(self.url)
        conn = PgConnection(raw)
        try:
            yield conn
        finally:
            raw.close()

    @contextmanager
    def transaction(self):
        with self.connect() as conn:
            try:
                conn.execute('BEGIN')
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
        """Create a portable JSON safety snapshot for destructive operations.

        PostgreSQL itself remains persistent in Supabase.  The snapshot is an extra
        application-level safety copy and intentionally includes invoice XML as base64.
        """
        target = Path(target).resolve().with_suffix('.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        data = {'format': 'fe-abbehusen-flow-postgres-snapshot-v1', 'tables': {}}
        with self.connect() as conn:
            for table in TABLES:
                rows = [dict(r) for r in conn.execute(f'SELECT * FROM {table}')]
                for row in rows:
                    for key, value in list(row.items()):
                        if isinstance(value, (bytes, bytearray, memoryview)):
                            row[key] = {'__base64__': base64.b64encode(bytes(value)).decode('ascii')}
                data['tables'][table] = rows
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        return target

    def reset_sequences(self):
        with self.transaction() as conn:
            for table in sorted(ID_TABLES):
                # deleted_sales/history_issues do not own sequences and are not in ID_TABLES.
                conn.execute(
                    "SELECT setval(pg_get_serial_sequence(%s,'id'), COALESCE((SELECT MAX(id) FROM " + table + "),1), COALESCE((SELECT MAX(id) FROM " + table + "),0)>0)",
                    (table,),
                )
