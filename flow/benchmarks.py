"""Comparador de capital hipotético; nunca confunde margem com retorno de investimento."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import asyncio
import httpx
from .money import RuleError, add_months, decimal

# SGS: CDI acumulado no mês (4391), IPCA mensal (433). Valores percentuais mensais.
SERIES = {'CDI': 4391, 'IPCA': 433}


def compound(observations, expected_months):
    values = {}
    for row in observations:
        when = datetime.strptime(row['data'], '%d/%m/%Y').date().isoformat()[:7]
        if when not in expected_months:
            continue
        if when in values:
            raise RuleError('A série recebida repete um mês.')
        rate = decimal(row['valor'])
        if rate <= -100 or rate > 1000:
            raise RuleError('A série recebida contém uma taxa fora do intervalo esperado.')
        values[when] = rate
    if set(values) != set(expected_months):
        raise RuleError('O Banco Central ainda não forneceu todos os meses do período. Nenhum mês foi estimado.')
    factor = Decimal(1)
    for month in sorted(values):
        factor *= 1 + values[month] / 100
    return factor - 1


async def fetch_benchmarks(start, end):
    """Período de meses completos, limitado a 120 meses para evitar consultas excessivas."""
    try:
        first = date.fromisoformat(start + '-01')
        last = date.fromisoformat(end + '-01')
    except ValueError as exc:
        raise RuleError('Informe meses no formato AAAA-MM.') from exc
    from .money import today
    if last >= date.fromisoformat(today()[:7] + '-01') or first > last or first.year < 2000:
        raise RuleError('Escolha um período de meses completos, anterior ao mês atual.')
    months, cursor = [], first.isoformat()
    while cursor[:7] <= last.isoformat()[:7]:
        months.append(cursor[:7])
        if len(months) > 120:
            raise RuleError('Escolha até 120 meses.')
        cursor = add_months(cursor, 1)
    stop = date.fromisoformat(add_months(last.isoformat(), 1)) - timedelta(days=1)
    params = {'formato': 'json', 'dataInicial': first.strftime('%d/%m/%Y'), 'dataFinal': stop.strftime('%d/%m/%Y')}
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        async def series(code):
            response = await client.get(f'https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados', params=params)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise RuleError('O Banco Central retornou um formato inesperado.')
            return compound(data, months)
        try:
            values = await asyncio.gather(*(series(code) for code in SERIES.values()))
        except RuleError:
            raise
        except Exception as exc:
            raise RuleError('Não foi possível consultar o Banco Central agora. Tente novamente; as taxas não foram substituídas por zero.') from exc
    return {'rates': dict(zip(SERIES, values)), 'start': start, 'end': end,
            'retrieved_at': datetime.now(timezone.utc).isoformat()}
