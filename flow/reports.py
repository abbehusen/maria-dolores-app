"""Resultado por competência e fluxo de caixa efetivo, sem truncar consultas."""
from contextlib import nullcontext
import csv
import io
import json
from datetime import date
from .money import add_months, day
from .commerce import commission_open


SALE_AMOUNTS = ['revenue_cents', 'cost_cents', 'fee_cents', 'tax_cents', 'seller_cents', 'store_cents']


def summary(db, start, end, *, _conn=None):
    start, end = day(start), day(end)
    if start > end:
        from .money import RuleError
        raise RuleError('A data inicial deve ser anterior ou igual à final.')
    # Uma única transação de leitura oferece uma fotografia consistente das tabelas.
    with (db.connect() if _conn is None else nullcontext(_conn)) as conn:
        if _conn is None:
            conn.execute('BEGIN')
        result = {key: 0 for key in SALE_AMOUNTS}
        result['sale_count'] = 0
        pending_cost = False
        for sale in conn.execute("SELECT * FROM sales WHERE operation='sale' AND sale_date<=?", (end,)):
            sign = int(start <= sale['sale_date'] <= end) - int(bool(sale['cancelled_on']) and start <= sale['cancelled_on'] <= end)
            for key in SALE_AMOUNTS:
                result[key] += sign * sale[key]
            result['sale_count'] += sign
            if sale['cost_status'] == 'pending' and sign:
                pending_cost = True
        operating = 0
        for exp in conn.execute('SELECT * FROM expenses WHERE occurred_on<=? AND affects_result=1', (end,)):
            sign = int(start <= exp['occurred_on'] <= end) - int(bool(exp['cancelled_on']) and start <= exp['cancelled_on'] <= end)
            operating += sign * exp['amount_cents']
        adjustments = conn.execute("SELECT COALESCE(SUM(cost_cents),0) FROM movements WHERE kind='ADJUSTMENT' "
                                   'AND occurred_on BETWEEN ? AND ?', (start, end)).fetchone()[0]
        result.update(operating_cents=operating, adjustment_cents=adjustments)
        from .locations import loss_report
        result['loss_cents']=sum(r['cost_cents'] for r in loss_report(conn,start,end))
        result['net_cents'] = (result['revenue_cents'] - sum(result[k] for k in SALE_AMOUNTS[1:])
                               - operating + adjustments - result['loss_cents'])
        result['cash_in_cents'] = conn.execute('SELECT COALESCE(SUM(gross_cents-fee_cents),0) FROM receivables '
                                              'WHERE cash_effect=1 AND paid_on BETWEEN ? AND ?', (start, end)).fetchone()[0]
        result['cash_out_cents'] = conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM expenses '
                                               'WHERE cash_effect=1 AND paid_on BETWEEN ? AND ?', (start, end)).fetchone()[0]
        result['cash_net_cents'] = result['cash_in_cents'] - result['cash_out_cents']
        balance = conn.execute('SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(cost_cents),0) FROM movements '
                               'WHERE occurred_on<=?', (end,)).fetchone()
        result.update(stock=balance[0], stock_cents=balance[1])
        result['history_pending'] = conn.execute('SELECT COUNT(*) FROM history_issues WHERE occurred_on<=?', (end,)).fetchone()[0]
        if result['history_pending']:
            result['stock_cents'] = None
        if conn.execute("SELECT 1 FROM movements WHERE kind='ADJUSTMENT' AND cost_status='pending' "
                        'AND occurred_on BETWEEN ? AND ? LIMIT 1', (start, end)).fetchone():
            result['adjustment_cents'] = None
            pending_cost = True
        if pending_cost:
            result['cost_cents'] = None
            result['net_cents'] = None
        result['receivable_cents'] = conn.execute('SELECT COALESCE(SUM(r.gross_cents-r.fee_cents),0) FROM receivables r '
                                                  'JOIN sales s ON s.id=r.sale_id WHERE s.sale_date<=? '
                                                  'AND (r.paid_on IS NULL OR r.paid_on>?) '
                                                  'AND (r.voided_on IS NULL OR r.voided_on>?)', (end, end, end)).fetchone()[0]
        result['payable_cents'] = conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE cash_effect=1 '
                                               'AND occurred_on<=? AND (paid_on IS NULL OR paid_on>?) '
                                               'AND (cancelled_on IS NULL OR cancelled_on>?)', (end, end, end)).fetchone()[0]
        result['payable_cents'] += sum(r['balance_cents'] for r in commission_open(conn,end))
        result['personal_cost_cents'] = conn.execute("SELECT COALESCE(SUM(cost_cents),0) FROM sales WHERE operation='personal' AND cancelled_on IS NULL AND sale_date BETWEEN ? AND ?",(start,end)).fetchone()[0]
        if conn.execute("SELECT 1 FROM sales WHERE operation='personal' AND cost_status='pending' AND cancelled_on IS NULL AND sale_date BETWEEN ? AND ?",(start,end)).fetchone():
            result['personal_cost_cents'] = None
        consigned = conn.execute('SELECT COALESCE(SUM(l.quantity+COALESCE(m.qty,0)),0),COALESCE(SUM((l.quantity+COALESCE(m.qty,0))*l.unit_cost_cents),0) FROM consignment_lots l LEFT JOIN (SELECT lot_id,SUM(quantity) qty FROM active_consignment_moves WHERE occurred_on<=? GROUP BY lot_id) m ON m.lot_id=l.id WHERE l.received_on<=?', (end, end)).fetchone()
        result.update(consigned_stock=consigned[0], consigned_stock_cents=consigned[1])
        result['consignment_payable_cents'] = conn.execute("SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE category='Repasse consignação' AND occurred_on<=? AND (paid_on IS NULL OR paid_on>?) AND (cancelled_on IS NULL OR cancelled_on>?)", (end,end,end)).fetchone()[0]
        for name, category in [('consignment_paid_cents', 'Repasse consignação'), ('own_purchase_paid_cents', 'Compra de estoque')]:
            result[name] = conn.execute('SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE category=? AND paid_on BETWEEN ? AND ?', (category,start,end)).fetchone()[0]
        if _conn is None:
            conn.rollback()
    return result


def monthly(db, start, end, *, _conn=None):
    """Meses do intervalo escolhido, respeitando dias parciais nas extremidades."""
    from datetime import timedelta
    start, end = day(start), day(end)
    if start > end:
        from .money import RuleError
        raise RuleError('A data inicial deve ser anterior ou igual à final.')
    first = start[:7] + '-01'
    rows = []
    while first <= end:
        next_month = add_months(first, 1)
        stop = min(end, (date.fromisoformat(next_month) - timedelta(days=1)).isoformat())
        rows.append({'month': first[:7], **summary(db, max(start, first), stop, _conn=_conn)})
        first = next_month
    return rows


def csv_bytes(rows, columns=None):
    """UTF-8 com BOM, separador brasileiro e células protegidas de fórmulas."""
    columns = columns or list(rows[0] if rows else {})
    file = io.StringIO(newline='')
    writer = csv.writer(file, delimiter=';')
    writer.writerow(columns)
    for row in rows:
        row = dict(row)
        if row.get('cost_status') == 'pending':
            for field in ['cost_cents', 'net_cents']:
                if field in row:
                    row[field] = 'Em conferência'
        values = []
        for column in columns:
            value = row.get(column, '')
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return ('\ufeff' + file.getvalue()).encode('utf-8')


def export_json(db):
    tables = ['metadata', 'products', 'invoices', 'invoice_items', 'sales', 'sale_items',
              'movements', 'receivables', 'expenses', 'audit', 'history_issues', 'deleted_sales', 'consignment_lots', 'consignment_sale_items', 'consignment_moves', 'consignment_return_cancellations','customers','channels','beneficiaries','channel_sellers','commission_settlements','locations','location_transfers','sale_locations','stock_losses']
    with db.connect() as conn:
        conn.execute('BEGIN')
        data = {}
        for table in tables:
            rows = [dict(row) for row in conn.execute('SELECT * FROM ' + table)]
            for row in rows:
                if row.get('cost_status') == 'pending':
                    for field in ['cost_cents', 'net_cents']:
                        if field in row:
                            row[field] = None
            if table == 'invoices':
                for row in rows:
                    # Os bytes originais permanecem no backup SQLite e no download individual.
                    del row['xml']
            data[table] = rows
        conn.rollback()
    return json.dumps({'format_version': 5, 'money_unit': 'BRL cents', 'tables': data},
                      ensure_ascii=False, indent=2).encode('utf-8')
