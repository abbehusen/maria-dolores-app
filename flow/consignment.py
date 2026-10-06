"""Lotes consignados: custo fixo por peça e saldo independente do estoque próprio."""
from .money import RuleError


def validate_lots(conn, ids):
    for lot_id in set(ids):
        lot = conn.execute('SELECT * FROM consignment_lots WHERE id=?', (lot_id,)).fetchone()
        if not lot:
            raise RuleError('Lote consignado não encontrado.')
        balance = lot['quantity']
        for row in conn.execute('SELECT * FROM active_consignment_moves WHERE lot_id=? ORDER BY occurred_on,id', (lot_id,)):
            if row['occurred_on'] < lot['received_on']:
                raise RuleError('A operação não pode anteceder o recebimento do lote consignado.')
            balance += row['quantity']
            if balance < 0 or balance > lot['quantity']:
                raise RuleError(f"Saldo insuficiente no histórico do lote consignado #{lot_id} em {row['occurred_on']}.")


def recost_sale(conn, sale_id):
    own, pending = conn.execute("SELECT COALESCE(SUM(cost_cents),0),COALESCE(SUM(cost_status='pending'),0) FROM sale_items WHERE sale_id=?", (sale_id,)).fetchone()
    consigned = conn.execute('SELECT COALESCE(SUM(cost_cents),0) FROM consignment_sale_items WHERE sale_id=?', (sale_id,)).fetchone()[0]
    cost = own + consigned
    conn.execute('UPDATE sales SET cost_cents=?,cost_status=?,net_cents=revenue_cents-?-fee_cents-tax_cents-seller_cents-store_cents WHERE id=?',
                 (cost, 'pending' if pending else 'confirmed', cost, sale_id))

    conn.execute("UPDATE sales SET net_cents=0 WHERE id=? AND operation='personal'",(sale_id,))
