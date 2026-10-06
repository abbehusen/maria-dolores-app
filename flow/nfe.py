"""Leitura determinística; preserva XML e SKU completos, sem reescrever CNPJs."""
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from defusedxml import ElementTree as ET
from .money import RuleError, cents, day, decimal

NS = {'n': 'http://www.portalfiscal.inf.br/nfe'}
BUYERS = {'63167950000125', '68120276000147', '02194389512'}
DEFAULT_SUPPLIER = '08450759000501'
SUPPLIERS = {DEFAULT_SUPPLIER, '08450759000188'}
MAX_XML_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class InvoiceItem:
    number: str
    sku: str
    name: str
    quantity: Decimal
    cost_cents: int
    category: str
    material: str
    stone: str
    size: str


@dataclass(frozen=True)
class Invoice:
    key: str
    number: str
    issued_on: str
    issuer: str
    issuer_name: str
    recipient: str
    total_cents: int
    items: tuple[InvoiceItem, ...]
    raw: bytes
    sha256: str


def text(node, path, default=''):
    found = node.find('/'.join('n:' + part for part in path.split('/')), NS)
    return (found.text or '').strip() if found is not None else default


def parse_xml(raw: bytes, *, buyers=None, suppliers=None):
    if not raw:
        raise RuleError('O arquivo recebido está vazio. Selecione novamente o XML original salvo no computador.')
    if len(raw) > MAX_XML_BYTES:
        raise RuleError('O XML ultrapassa o limite de 10 MB.')
    try:
        root = ET.fromstring(raw, forbid_dtd=True)
    except Exception as exc:
        raise RuleError('O arquivo não é um XML NF-e válido ou contém estruturas não permitidas.') from exc
    nodes = root.findall('.//n:infNFe', NS)
    if len(nodes) != 1:
        raise RuleError('Envie uma única NF-e, com a estrutura e o namespace originais.')
    info = nodes[0]
    key = info.get('Id', '').removeprefix('NFe')
    if not re.fullmatch(r'\d{44}', key):
        raise RuleError('A NF-e não contém uma chave de acesso de 44 dígitos.')
    issuer, recipient = text(info, 'emit/CNPJ'), (text(info, 'dest/CNPJ') or text(info, 'dest/CPF'))
    if issuer not in (SUPPLIERS if suppliers is None else suppliers):
        raise RuleError(f'Emissor {issuer} não cadastrado. Revise a lista SUPPLIERS em flow/nfe.py.')
    if recipient not in (BUYERS if buyers is None else buyers):
        raise RuleError(f'Destinatário {recipient} não corresponde a um dos CPF/CNPJs cadastrados.')
    if key[6:20] != issuer or text(info, 'ide/mod') != '55' or text(info, 'ide/tpNF') != '1':
        raise RuleError('A chave/emissor ou o tipo de documento não corresponde a uma NF-e de saída do fornecedor.')
    protocol = root.find('.//n:protNFe/n:infProt', NS)
    if protocol is None or text(protocol, 'cStat') not in {'100', '150'} or text(protocol, 'chNFe') != key:
        raise RuleError('Envie o XML processado (nfeProc) com protocolo de autorização correspondente.')
    number = text(info, 'ide/nNF')
    if not number.isdigit() or int(key[25:34]) != int(number):
        raise RuleError('O número da nota diverge da chave de acesso.')
    issued = day((text(info, 'ide/dhEmi') or text(info, 'ide/dEmi'))[:10])
    items = []
    for node in info.findall('n:det', NS):
        sku, name = text(node, 'prod/cProd'), text(node, 'prod/xProd')
        if not sku or not name:
            raise RuleError('Há um item sem código ou descrição.')
        quantity = decimal(text(node, 'prod/qCom'))
        if quantity <= 0:
            raise RuleError(f'O item {sku} tem quantidade inválida.')
        if text(node, 'prod/indTot', '1') != '1':
            raise RuleError(f'O item {sku} não compõe o total da nota; este documento exige revisão manual.')
        # Custo gerencial de aquisição: componentes monetários explicitamente discriminados.
        value = cents(text(node, 'prod/vProd', '0')) - cents(text(node, 'prod/vDesc', '0'))
        for field in ['vFrete', 'vSeg', 'vOutro']:
            value += cents(text(node, 'prod/' + field, '0'))
        for field in ['vIPI', 'vICMSST', 'vFCPST']:
            value += sum(cents(n.text or '0') for n in node.findall('.//n:' + field, NS))
        if value < 0:
            raise RuleError(f'O custo do item {sku} ficou negativo.')
        category = name.split()[0].title()
        if category == 'Choker':
            category = 'Colar'
        bath = re.search(r'(FO|RN)', sku.upper())
        stone = name.split('/', 1)[1].strip() if '/' in name else ''
        size_match = re.search(r'\b(\d{2})\s*(?:UN)?$', name) if category == 'Anel' else None
        items.append(InvoiceItem(node.get('nItem', ''), sku, name, quantity, value,
                                 category, bath.group() if bath else '', stone,
                                 size_match.group(1) if size_match else ''))
    if not items or len({i.number for i in items}) != len(items) or any(not i.number for i in items):
        raise RuleError('A nota não tem itens válidos ou repete um número de item.')
    total = cents(text(info, 'total/ICMSTot/vNF'))
    if sum(i.cost_cents for i in items) != total:
        raise RuleError('Os componentes dos itens não fecham com o total da NF-e. '
                        'Esta nota exige revisão de frete, descontos ou tributos antes de importar.')
    return Invoice(key, number, issued, issuer, text(info, 'emit/xNome'), recipient,
                   total, tuple(items), raw, hashlib.sha256(raw).hexdigest())
