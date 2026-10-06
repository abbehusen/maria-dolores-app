def fixture_xml(*, number=9999, second_quantity='1', second_value='20.00', recipient='68120276000147', date='2025-01-15'):
    """NF-e inteiramente fictícia para testes, sem assinatura e sem validade fiscal."""
    prefix = '29' + date[2:4] + date[5:7] + '08450759000501' + '55' + '001' + str(number).zfill(9) + '1' + '12345678'
    total = sum(int(n) * (2 + i % 8) for i, n in enumerate(reversed(prefix)))
    digit = 11 - total % 11
    key = prefix + str(0 if digit >= 10 else digit)
    from decimal import Decimal
    total_value = Decimal('190.00') + Decimal(second_value)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- EXEMPLO FICTÍCIO DE TESTE, SEM VALIDADE FISCAL -->
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
<NFe><infNFe Id="NFe{key}" versao="4.00">
<ide><mod>55</mod><nNF>{number}</nNF><dhEmi>{date}T10:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>
<emit><CNPJ>08450759000501</CNPJ><xNome>FORNECEDOR FICTÍCIO PARA TESTE</xNome></emit>
<dest><CNPJ>{recipient}</CNPJ><xNome>DESTINATÁRIO DE TESTE</xNome></dest>
<det nItem="1"><prod><cProd>TESTE.001.FO</cProd><xProd>BRINCO EXEMPLO / QUARTZO</xProd>
<qCom>2</qCom><vUnCom>100.00</vUnCom><vProd>200.00</vProd><vDesc>20.00</vDesc><vFrete>10.00</vFrete><indTot>1</indTot></prod></det>
<det nItem="2"><prod><cProd>TESTE.002</cProd><xProd>EMBALAGEM EXEMPLO</xProd>
<qCom>{second_quantity}</qCom><vUnCom>{second_value}</vUnCom><vProd>{second_value}</vProd><indTot>1</indTot></prod></det>
<total><ICMSTot><vNF>{total_value}</vNF></ICMSTot></total>
</infNFe></NFe><protNFe><infProt><chNFe>{key}</chNFe><cStat>100</cStat></infProt></protNFe></nfeProc>'''.encode('utf-8')
