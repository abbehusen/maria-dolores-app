"""Dinheiro em centavos; Decimal apenas nas fronteiras e nos rateios."""
import calendar
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo


class RuleError(ValueError):
    """Erro que pode ser apresentado diretamente à pessoa usando o sistema."""


def decimal(value):
    text = str(value if value is not None else '').strip().replace('R$', '').replace(' ', '')
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise RuleError('Informe um número válido, como 125,50.') from exc
    if not result.is_finite() or abs(result) > Decimal('1000000000000'):
        raise RuleError('Valor fora do intervalo permitido.')
    return result


def cents(value, *, signed=False):
    result = int((decimal(value) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if result < 0 and not signed:
        raise RuleError('O valor não pode ser negativo.')
    return result


def pieces(value, *, zero=False):
    number = decimal(value)
    if number != number.to_integral_value() or number < (0 if zero else 1) or number > 1000000:
        raise RuleError('A quantidade de peças deve ser um número inteiro válido.')
    return int(number)


def rounded(value):
    return int(Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def percent(amount_cents, rate):
    rate = decimal(rate)
    if not 0 <= rate <= 100:
        raise RuleError('O percentual deve ficar entre 0 e 100.')
    return rounded(Decimal(amount_cents) * rate / 100)


def brl(amount_cents):
    if amount_cents is None:
        return 'Em conferência'
    value = f'{abs(amount_cents) / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('−' if amount_cents < 0 else '') + 'R$ ' + value


def today():
    return datetime.now(ZoneInfo('America/Bahia')).date().isoformat()


def day(value, *, future=False):
    try:
        parsed = date.fromisoformat(str(value))
    except (ValueError, TypeError) as exc:
        raise RuleError('Informe uma data válida no formato AAAA-MM-DD.') from exc
    if parsed.year < 2000 or (not future and parsed.isoformat() > today()):
        raise RuleError('A data do lançamento deve estar entre 2000 e hoje.')
    return parsed.isoformat()


def add_months(value, months):
    parsed = date.fromisoformat(value)
    year, month = divmod(parsed.year * 12 + parsed.month - 1 + months, 12)
    month += 1
    return date(year, month, min(parsed.day, calendar.monthrange(year, month)[1])).isoformat()


def split_cents(total, count):
    """Parcelas cuja soma coincide exatamente com o total, inclusive centavos."""
    return [total // count + (1 if i < total % count else 0) for i in range(count)]
