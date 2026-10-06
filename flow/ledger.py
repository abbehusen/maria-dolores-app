"""Reconstrói o custo médio pelas datas reais, dentro da transação do lançamento.

Entradas documentais vêm primeiro no mesmo dia. Os demais movimentos empatados
seguem seu id (ordem de cadastro). Sem horários, essa é a convenção explícita.
Quantidade faltante nunca é precificada com uma compra futura: propaga custo
pendente até a origem ser regularizada e o histórico ser reconstruído.
"""
import json
from decimal import Decimal
from .money import RuleError, rounded

ORDER = "occurred_on, CASE WHEN kind IN ('OPENING','PURCHASE') THEN 0 ELSE 1 END, id"


def rebuild_history(conn, product_ids=None, *, strict=False):
    ids = sorted(set(product_ids)) if product_ids is not None else [r[0] for r in conn.execute('SELECT id FROM products')]
    touched_sales = set()
    changes = []
    for pid in ids:
        product = conn.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
        if product is None:
            raise RuleError('Produto não encontrado.')
        conn.execute('DELETE FROM history_issues WHERE product_id=?', (pid,))
        quantity, value = 0, 0
        costs = {}
        uncertain = False
        for row in conn.execute('SELECT * FROM movements WHERE product_id=? ORDER BY ' + ORDER, (pid,)).fetchall():
            delta, amount = row['quantity'], row['cost_cents']
            pending = False
            if row['kind'] in {'OPENING', 'PURCHASE'}:
                if delta <= 0 or amount < 0:
                    raise RuleError('Entrada de estoque inválida no histórico.')
            elif row['kind'] == 'SALE':
                sid = int(row['source'])
                item = conn.execute('SELECT * FROM sale_items WHERE sale_id=? AND product_id=?', (sid, pid)).fetchone()
                if item is None or delta != -item['quantity']:
                    raise RuleError('A saída de estoque não corresponde ao item da venda.')
                if quantity < -delta:
                    missing = -delta - quantity
                    detail = (f"{product['sku']}: faltam {missing} peça(s) em {row['occurred_on']} para a venda #{sid}. "
                              'Confira as compras anteriores e a quantidade vendida.')
                    conn.execute('INSERT INTO history_issues(product_id,movement_id,occurred_on,missing_quantity,detail) '
                                 'VALUES (?,?,?,?,?)', (pid, row['id'], row['occurred_on'], missing, detail))
                    uncertain = True
                pending = uncertain
                amount = 0 if pending else -rounded(Decimal(value) * -delta / quantity)
                costs[sid] = (amount, pending)
                touched_sales.add(sid)
                status = 'pending' if pending else 'confirmed'
                if item['cost_cents'] != -amount or item['cost_status'] != status:
                    changes.append({'item': item['id'], 'before': item['cost_cents'], 'after': -amount, 'status': status})
                conn.execute('UPDATE sale_items SET cost_cents=?,cost_status=? WHERE id=?', (-amount, status, item['id']))
            elif row['kind'] == 'CANCELLATION':
                sid = int(row['source'])
                if sid not in costs:
                    raise RuleError('Há cancelamento anterior à venda ou sem venda correspondente.')
                sale_cost, pending = costs[sid]
                item = conn.execute('SELECT quantity FROM sale_items WHERE sale_id=? AND product_id=?', (sid, pid)).fetchone()
                if delta != item['quantity']:
                    raise RuleError('Quantidade do cancelamento inconsistente com a venda.')
                amount = -sale_cost
                uncertain = uncertain or pending
                touched_sales.add(sid)
            elif row['kind'] == 'LOSS':
                if uncertain or quantity < -delta:
                    raise RuleError('Complete o histórico de estoque antes de registrar ou recalcular uma perda.')
                amount=-rounded(Decimal(value)*-delta/quantity)
            elif row['kind'] == 'LOSS_CANCEL':
                original=conn.execute("SELECT cost_cents,quantity FROM movements WHERE kind='LOSS' AND source=? AND product_id=?",(row['source'],pid)).fetchone()
                if not original or delta!=-original['quantity']:
                    raise RuleError('Perda de origem não encontrada.')
                amount=-original['cost_cents']
            elif row['kind'] == 'ADJUSTMENT':
                if row['counted_quantity'] is None or row['input_unit_cost_cents'] is None:
                    raise RuleError('Conferência sem contagem ou custo de entrada; revise o histórico.')
                # A conferência é uma contagem física absoluta, não um delta fixo.
                delta = row['counted_quantity'] - quantity
                pending = uncertain
                amount = (0 if pending else
                          -rounded(Decimal(value) * -delta / quantity) if delta < 0 else
                          delta * row['input_unit_cost_cents'])
            else:
                raise RuleError('Tipo de movimentação desconhecido no histórico.')
            quantity += delta
            value += amount
            status = 'pending' if pending else 'confirmed'
            conn.execute('UPDATE movements SET quantity=?,cost_cents=?,cost_status=? WHERE id=?',
                         (delta, amount, status, row['id']))
            if not uncertain and (quantity < 0 or value < 0 or (quantity == 0 and value != 0)):
                raise RuleError('A reconstrução produziria um custo de estoque inconsistente.')
        if strict and uncertain:
            raise RuleError('Estoque histórico insuficiente ou em conferência para ' + product['name'] +
                            '. Confira a data e as compras, ou marque a venda como lançamento histórico.')
        conn.execute('UPDATE products SET history_status=? WHERE id=?',
                     ('pending' if uncertain else 'confirmed', pid))
    for sid in touched_sales:
        cost, pending = conn.execute("SELECT COALESCE(SUM(cost_cents),0),COALESCE(SUM(cost_status='pending'),0) "
                                     'FROM sale_items WHERE sale_id=?', (sid,)).fetchone()
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='consignment_sale_items'").fetchone():
            cost += conn.execute('SELECT COALESCE(SUM(cost_cents),0) FROM consignment_sale_items WHERE sale_id=?', (sid,)).fetchone()[0]
        conn.execute('UPDATE sales SET cost_cents=?,cost_status=?,net_cents='
                     'revenue_cents-?-fee_cents-tax_cents-seller_cents-store_cents WHERE id=?',
                     (cost, 'pending' if pending else 'confirmed', cost, sid))
    if any(r[1]=='operation' for r in conn.execute('PRAGMA table_info(sales)')):
        conn.execute("UPDATE sales SET net_cents=0 WHERE operation='personal'")
    if changes:
        conn.execute('INSERT INTO audit(action,entity,entity_id,detail) VALUES (?,?,?,?)',
                     ('recalculate_costs', 'history', ','.join(map(str, ids)), json.dumps(changes, ensure_ascii=False)))
