"""Dados inventados, criados somente em demonstracao.sqlite3 quando --demo é usado."""
from .money import add_months, today


def seed(business):
    if business.db.rows('SELECT id FROM products LIMIT 1'):
        return
    base = add_months(today()[:7] + '-01', -5)
    descriptions = [('Brinco Aurora', 'Brinco', 'FO', 'Quartzo', 'Luz', '145.00', '349.00'),
                    ('Colar Horizonte', 'Colar', 'FO', 'Ágata', 'Luz', '220.00', '529.00'),
                    ('Anel Caminho', 'Anel', 'RN', 'Cristal', 'Essência', '130.00', '299.00'),
                    ('Pulseira Encontro', 'Pulseira', 'FO', '', 'Essência', '180.00', '429.00'),
                    ('Brinco Maré', 'Brinco', 'RN', 'Pérola', 'Água', '155.00', '379.00'),
                    ('Colar Origem', 'Colar', 'FO', 'Quartzo', 'Terra', '260.00', '629.00')]
    ids = []
    for i, (name, category, material, stone, collection, cost, price) in enumerate(descriptions):
        ids.append(business.create_product(dict(supplier='FORNECEDOR DEMONSTRAÇÃO', sku=f'DEMO-{i+1:03}', name=name,
                    category=category, material=material, stone=stone, collection=collection,
                    size='18' if category == 'Anel' else '', selling_price=price),
                    quantity=12, unit_cost=cost, when=base, key=f'demo-product-{i}'))
    for month in range(6):
        when = add_months(base, month)
        for n in range(3 + month):
            i = (month + n) % len(ids)
            # Mantém a ordem de lançamento das movimentações dentro de cada mês.
            day = when
            business.create_sale([{'product_id': ids[i], 'quantity': 1, 'unit_price': descriptions[i][6]}],
                dict(sale_date=day, customer=f'Cliente exemplo {month * 10 + n + 1:02}',
                     event='Encontro de clientes' if n % 3 == 0 else 'Venda direta', method='Pix' if n % 2 else 'Cartão de crédito',
                     fee='0' if n % 2 else '9.00', seller='12.00', tax='0', store='0',
                     first_due=add_months(day, 1) if month == 5 and n % 2 == 0 else day,
                     paid_on=None if month == 5 and n % 2 == 0 else day), key=f'demo-sale-{month}-{n}')
        business.create_expense(dict(occurred_on=when, due_on=when, paid_on=when,
                                    amount=str(180 + month * 25), category='Marketing',
                                    description='Divulgação · exemplo fictício', vendor='Fornecedor exemplo'), key=f'demo-expense-{month}')
