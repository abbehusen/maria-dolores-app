# Fe Abbehusen Flow — versão 0.6.7

Aplicação local em **NiceGUI + SQLite**, com interface em português, para gerenciar o fluxo da revenda. O código do Base44 serviu de referência; esta versão não depende do Base44 e não acessa sua base antiga.

Já usa uma versão anterior? Leia **ATUALIZAR.md** antes de copiar os arquivos. Preserve a pasta `data`.

## Novidades da versão 0.6.3

Retiradas para uso pessoal, canais e vendedoras no registro de vendas, gestão de comissões em dinheiro ou peças, cadastro e histórico de clientes e relatórios por forma de pagamento. Leia **GUIA_CANAIS_COMISSOES_CLIENTES.md** para configurar a operação. A base anterior é migrada automaticamente, com backup.

## Começar pela demonstração

Extraia o ZIP e abra a pasta `fe_flow` no VS Code. Use Python 3.12.

Como você já usa Conda, no terminal:

```bash
conda create -n fe-flow python=3.12 -y
conda activate fe-flow
pip install -r requirements.txt -c constraints.txt
python main.py --demo
```

O navegador abrirá em **http://127.0.0.1:8080**. Se não abrir, acesse esse endereço manualmente. O terminal precisa continuar aberto. Para encerrar, pressione `Ctrl+C`.

Sem Conda, no Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -c constraints.txt
.venv\Scripts\python.exe main.py --demo
```

No Linux/macOS:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -c constraints.txt
.venv/bin/python main.py --demo
```

A instalação precisa de internet. Cadastros, estoque, XML, vendas e despesas funcionam localmente; a consulta ao Banco Central depende de internet.

## Demonstração e base real

| Comando | Banco usado | Conteúdo inicial |
| --- | --- | --- |
| `python main.py --demo` | `data/demonstracao.sqlite3` | Produtos, vendas e despesas inventados |
| `python main.py` | `data/flow.sqlite3` | Vazio |

As bases são independentes. Rodar a demonstração não preenche a base real. Nenhum dado comercial real foi incluído no pacote.

Se a porta estiver ocupada, use `python main.py --demo --port 8081`. Para outro diretório de dados, use `--data-dir CAMINHO`. `--no-open` evita a abertura automática do navegador.

Esta entrega escuta somente no próprio computador, em `127.0.0.1`. Tem layout adaptável, mas ainda não oferece acesso pelo celular na rede, hospedagem, login ou usuários com permissões. Essas configurações precisam ser acrescentadas antes de disponibilizar o sistema pela internet. Não coloque o arquivo SQLite ativo em uma pasta de sincronização ou compartilhamento de rede.

## O que experimentar primeiro

1. Abra o **Painel** e altere o período. O padrão é o mês atual até hoje e os cinco meses anteriores. Ao aplicar outras datas, o gráfico mensal cobre todo o intervalo escolhido, respeitando os dias inicial e final e incluindo meses sem movimento. Os indicadores do período são separados da posição do estoque e das contas na data final.
2. Em **Estoque**, selecione uma linha para editar o cadastro, conferir o saldo ou consultar as movimentações. A opção Catálogo mostra cartões; nesta versão as fotos ainda são representadas por um ícone.
3. Em **Vendas**, registre uma venda de várias peças. Informe o preço efetivo, descontos, taxas e comissões. Confira a baixa do estoque e as parcelas a receber.
4. Em **Despesas**, registre uma despesa avulsa ou selecione várias contas e clique em **Pagar selecionadas**. Confira a lista e o total, informe a data comum e confirme. O lote é validado por inteiro: se uma conta estiver paga, cancelada ou com data incompatível, nenhuma baixa é gravada. Compras e comissões antigas ainda sem beneficiário aparecem nessa lista. Comissões com beneficiário são geridas na aba Comissões.
5. Na base de demonstração, importe `examples/nfe_ficticia.xml` em **Compras e XML**. Escolha estoque para o primeiro item e despesa para o segundo. Tentar importar de novo deve ser bloqueado.
6. Em **Relatórios**, confira as linhas do resultado, o movimento de caixa, a exportação e o backup.

O XML de exemplo é **fictício, simplificado e sem validade fiscal**. Ele existe para testar o leitor, não para emissão ou transmissão à SEFAZ. Como é datado de janeiro de 2025, suas entradas e despesas aparecem nesse período.

## Regras implementadas

- **Dinheiro em centavos inteiros.** Conversões e rateios usam `Decimal`; a soma das parcelas fecha com o total.
- **Estoque com histórico.** Saldo inicial, compra, venda, cancelamento e conferência geram movimentações. O saldo não é um campo livre do cadastro.
- **Custo médio móvel.** Novas compras incorporam seu custo ao estoque. O custo de cada venda usa o estoque disponível na sua data. Uma compra ou venda inserida no passado recalcula os custos posteriores; alterar nome ou preço de catálogo não altera vendas passadas.
- **Operações atômicas.** A venda, seus itens, a saída de estoque e as contas são gravados juntos. Uma falha desfaz toda a operação. O SQLite serializa as alterações para impedir que duas operações vendam a mesma última peça.
- **Repetição controlada.** O envio repetido do mesmo formulário usa a mesma chave de operação. A chave da NF-e tem unicidade no banco, mesmo em importações apenas de despesas.
- **Quantidades inteiras.** O sistema não arredonda uma quantidade fracionária de joias. Um item fracionário pode ser classificado como despesa.
- **Cancelamento para correção.** O botão Cancelar venda remove o lançamento errado e seus recebimentos, despesas e repasses, inclusive baixas. Desfaz suas movimentações na origem e recalcula o histórico. Backup e trilha interna completa da correção são preservados; o número removido não é reutilizado.
- **Editar venda.** Abre o formulário preenchido para alterar peças, origem, quantidades, preço, markup aplicado ao preço, data, pagamento, parcelas, desconto e encargos. Mantém o número da venda. Use Alterar peça e depois Adicionar à venda para substituir uma linha. O markup não altera o custo de repasse nem o preço do cadastro.
- **Conferência física.** Uma diferença de estoque exige motivo. A diferença de custo entra como ganho ou perda gerencial; não simula uma compra nem um pagamento.
- **Cadastro fora de ordem.** Importe todas as compras e depois registre as vendas antigas na ordem que preferir. O sistema reconstrói os movimentos pelas datas reais. No mesmo dia, compras e saldos iniciais precedem os demais movimentos; estes seguem a ordem de cadastro.
- **Histórico incompleto.** A opção “Lançamento histórico — permitir pendências de estoque” permite registrar uma venda antes de completar suas compras anteriores. Custos e resultados afetados ficam “Em conferência”, sem lucro presumido. Importar a compra faltante recalcula o histórico. Vendas comuns continuam sujeitas à disponibilidade histórica.
- **Baixas na edição.** Por padrão, datas de baixas são preservadas por parcela e obrigação correspondente, com os valores recalculados. Marque Desfazer baixas anteriores para corrigir pagamentos/recebimentos errados; informe uma nova baixa integral no formulário ou baixe as novas parcelas em Vendas e obrigações em Despesas. Se mudar o número de parcelas ou remover uma obrigação paga, é necessário desfazer as baixas anteriores.

O teste de concorrência cobre dois pedidos pela última peça. Isso não é uma certificação para operação em grande escala ou para vários computadores compartilhando o arquivo do banco.

## XML e compras

O leitor usa `defusedxml`, sem IA. Preserva os bytes originais e o código completo do fornecedor. Os destinos de todos os itens, inclusive ignorados, ficam registrados.

Configuração inicial em `flow/nfe.py`:

- Emissor: `08450759000501`.
- Destinatários aceitos: `63167950000125` e `68120276000147`.

O importador **não troca o CNPJ da nota**. Mantém o destinatário histórico. Para adicionar fornecedores ou destinatários, revise os conjuntos `SUPPLIERS` e `BUYERS`.

Nesta versão, o documento precisa ser uma NF-e modelo 55 de saída do fornecedor, no formato `nfeProc`, com protocolo e chave correspondentes. O sistema confere os campos e o protocolo presentes no arquivo; **não verifica a assinatura digital nem consulta a situação atual na SEFAZ**. Uma nota autorizada no XML pode ter sido cancelada posteriormente fora do sistema.

O custo gerencial por item soma `vProd - vDesc + vFrete + vSeg + vOutro + vIPI + vICMSST + vFCPST`, quando discriminados. A soma precisa coincidir com `vNF`; caso contrário, a importação é interrompida para revisão. Isso não calcula créditos tributários nem cobre todos os regimes e layouts fiscais, devoluções, complementos ou eventos.

Produtos novos recebem o preço sugerido pelo multiplicador informado, inicialmente 2,3. Produtos já existentes mantêm seu preço de venda. O importador identifica o produto pelo fornecedor, SKU completo e variante; não elimina sufixos do código para buscar imagens.

Na modalidade Compra própria, as peças destinadas ao estoque geram estoque próprio e uma compra a pagar. Os itens destinados a despesa geram uma despesa e seu pagamento pendente. Itens ignorados não geram estoque nem contas; por isso, as contas geradas podem ser menores que o total documental. Confira a prévia antes de confirmar.

Não há exclusão ou reclassificação de nota já importada nesta primeira versão. Experimente o documento na demonstração antes da base real. O histórico de compras permite baixar o XML original.

## Compra própria e consignação

A tela Estoque oculta produtos exclusivamente consignados. Produtos com histórico próprio continuam nela, inclusive esgotados; quando há as duas modalidades, cada tela mostra seu saldo separado. Na aba Consignação, os indicadores de peças e valor em mãos são totais gerais a custo de repasse, independentes da busca. O subtotal da lista filtrada aparece separadamente. O valor em mãos não representa dívida já gerada.

Na prévia de **Compras e XML**, escolha **Compra própria** (padrão) ou **Consignação** antes de confirmar. As notas já importadas continuam como compras próprias. A atualização não tenta deduzir a modalidade pelos dados fiscais nem reclassifica notas existentes. Não reimporte uma nota existente para trocar sua modalidade.

Na consignação, cada item destinado ao estoque forma um lote associado à NF-e original. A entrada não gera pagamento, despesa ou obrigação com a matriz. Os destinos são estoque ou ignorar; despesas avulsas são lançadas separadamente. A aba **Consignação** mostra peças recebidas, vendidas líquidas de cancelamentos, devolvidas e ainda em mãos, além do custo de repasse e dos pagamentos vinculados às vendas.

O repasse unitário é o custo gerencial do item no XML dividido pela quantidade, arredondado para centavos, exibido na prévia. Esse custo inclui os componentes já discriminados pelo leitor (desconto, frete e tributos). Se a divisão não for exata, o valor unitário arredondado vezes a quantidade pode diferir alguns centavos do total documental, que permanece intacto no XML. Confira se esse valor corresponde ao combinado com a matriz antes de confirmar. O custo unitário do lote é fixo: compras posteriores e descontos ao cliente não o alteram.

Na lista de produtos da venda, os saldos próprio e consignado aparecem separados. Quando não há saldo próprio e existe apenas um lote consignado disponível, ele é selecionado automaticamente; havendo vários lotes, escolha a origem.

Ao registrar uma venda, escolha o produto e a **Origem da peça**: próprio ou um lote consignado identificado pela NF-e. A mesma venda pode conter estoque próprio e consignado, inclusive do mesmo produto, em linhas separadas. O preço sugerido de produtos novos é custo × markup (padrão 2,3); o preço efetivo e o desconto continuam livres. Produtos já cadastrados mantêm seu preço de catálogo.

A venda consignada gera o custo no resultado e uma conta **Repasse consignação** em Despesas, com vencimento informado no formulário (por padrão, data da venda). Dar baixa nessa conta, individualmente ou em lote, afeta apenas o caixa. O Painel e os Relatórios mostram o estoque próprio separado do consignado e os pagamentos de compras próprias separados dos repasses.

Para devolver peças não vendidas: **Consignação → selecionar lote → Devolver peças à matriz**, informar quantidade, data e motivo. Não gera venda, despesa ou documento fiscal. O saldo é validado em todas as datas do lote para impedir saída anterior à entrada ou quantidades insuficientes. Lançamentos históricos consignados exigem a entrada do lote já cadastrada; a opção de pendências aplica-se ao estoque próprio.

O cancelamento para correção pode remover vendas com repasse já marcado como pago; elimina também essa baixa local. Não realiza restituição bancária nem cria crédito com a matriz. A seção **Peças devolvidas à matriz**, na aba Consignação, mostra data, lote, peça, quantidade, motivo e situação. Para corrigir um lançamento errado, selecione a devolução e use **Cancelar devolução**, informando o motivo. O registro permanece como cancelado e deixa de reduzir os saldos, inclusive históricos; não há movimentação financeira. Esse recurso corrige um erro de registro, não registra uma nova remessa física da matriz. O histórico também permanece no backup.

## Resultado e caixa são medidas diferentes

**Resultado gerencial** = receita após descontos − custo das peças vendidas − taxa do cartão − impostos informados − comissões − despesas gerais + ganhos/perdas da conferência.

A compra de mercadoria forma estoque; seu custo entra no resultado quando a peça é vendida. A compra não é descontada novamente como despesa operacional.

**Movimento do caixa** = recebimentos efetivamente baixados, após a taxa do cartão, − pagamentos efetivamente baixados.

- Parcelas ficam pendentes até a baixa. O recebimento é integral por parcela; pagamentos parciais e adiantamentos ainda não estão implementados.
- Taxas de cartão e comissões percentuais são calculadas sobre a receita após o desconto adicional. O imposto é informado em reais.
- Comissões e impostos da venda já reduzem o resultado. Suas contas a pagar afetam somente o caixa quando quitadas.
- O sistema não calcula obrigações fiscais. Os valores de impostos são informados pelo usuário.
- O movimento de caixa não equivale ao saldo bancário: ainda não há saldo inicial financeiro, aportes e retiradas.
- Não lance outra despesa avulsa para a mesma taxa ou comissão já informada na venda.

O botão Cancelar venda corrige um registro errado: apaga seus efeitos desde a data original, sem criar reembolso ou despesa de taxa. Para uma venda real cujo dinheiro já circulou, esse botão não substitui o registro da devolução financeira. Cancelamentos antigos continuam no histórico até uma correção explícita. Conferências físicas posteriores permanecem como contagens absolutas e podem manter o saldo atual, mesmo após remover a venda. Devoluções comerciais parciais não estão implementadas.

Despesas avulsas ainda não pagas podem ser canceladas com motivo. Lançamentos vinculados a compra/venda e pagamentos já realizados não têm estorno direto nesta interface.

## CDI e IPCA

A tela de relatórios consulta o CDI mensal (SGS 4391) e o IPCA mensal (SGS 433), exigindo todos os meses do intervalo. Usa capitalização composta, admite IPCA negativo e não substitui indisponibilidade por taxa zero.

O comparador mostra o comportamento de um **capital hipotético**, antes de tributos/custos de aplicação. Não apresenta o lucro dividido pelo estoque restante como rentabilidade do negócio. Para medir corretamente o retorno do capital da operação, ainda precisamos modelar saldos financeiros, aportes, retiradas e o capital efetivamente empregado ao longo do tempo.

A integração de rede não pôde ser verificada neste ambiente. A composição das taxas, a exigência de cobertura completa e os erros foram tratados no código; confirme a consulta real na sua máquina. O último mês solicitado pode ainda não estar publicado.

Fontes de referência:

- [NiceGUI](https://github.com/zauberzeug/nicegui)
- [BCB — CDI acumulado no mês, série 4391](https://dadosabertos.bcb.gov.br/dataset/4391-taxa-de-juros---cdi-acumulada-no-mes)
- [BCB — IPCA, série 433](https://dadosabertos.bcb.gov.br/dataset/433-indice-nacional-de-precos-ao-consumidor-amplo-ipca)

## Como o código está organizado

| Arquivo | Responsabilidade |
| --- | --- |
| `main.py` | Opções de execução e inicialização |
| `flow/ui.py` | Telas e formulários NiceGUI |
| `flow/service.py` | Operações de produto, compra, venda, cancelamento e baixa |
| `flow/db.py` | Tabelas, migração, transações e backup SQLite |
| `flow/consignment.py` | Validação dos lotes consignados e custos das vendas mistas |
| `flow/ledger.py` | Reconstrução cronológica de quantidades e custos |
| `flow/nfe.py` | Leitura e validação local do XML |
| `flow/money.py` | Centavos, percentuais, rateios e datas |
| `flow/reports.py` | Resultado, caixa e exportações |
| `flow/benchmarks.py` | Séries mensais do Banco Central |
| `flow/demo.py` | Dados fictícios da demonstração |
| `tests/` | Testes das regras e da integração dos formulários |

Para mudar cores, espaçamentos ou a navegação, comece por `CSS` e `NAV` em `flow/ui.py`. Para alterar uma regra de venda, trabalhe em `Business.create_sale`, em `flow/service.py`, e mantenha os testes correspondentes.

Não há JavaScript de negócio para manter. O navegador usa os componentes do NiceGUI; as operações e a persistência ficam em Python.

## Testes e limites da verificação

```bash
pip install -r requirements-dev.txt -c constraints.txt
python -m pytest -q
```

Foram aprovados **83 testes** em Python 3.12/Linux: 71 verificações das regras e 12 cenários de integração do NiceGUI. Incluem importação repetida, rollback, concorrência, centavos, parcelas, cancelamento, lançamentos fora de ordem, recálculo de custos, pendências, exclusão de teste, migração da base anterior, backup e formulários.

A integração das telas foi executada pelo simulador oficial do NiceGUI, sem navegador gráfico. Não foi possível instalar o Chromium neste ambiente; portanto, aparência, rolagem em celular e comportamento visual precisam ser conferidos no navegador real. O Windows também não foi executado aqui. `constraints.txt` registra as versões das dependências usadas na verificação.

## Backup e recuperação

Use **Relatórios → Baixar backup completo**. O backup usa a API de snapshot do SQLite e inclui os XMLs. Os CSVs são exportações para consulta; os campos terminados em `_cents` estão em centavos. O JSON mantém os registros e IDs, mas não contém os bytes dos XMLs, que ficam no backup completo.

Para restaurar sem sobrescrever a base atual:

1. Encerre o aplicativo.
2. Crie uma pasta nova, por exemplo `restaurado`.
3. Copie o backup baixado para ela e renomeie a cópia como `flow.sqlite3`.
4. Execute `python main.py --data-dir restaurado`.
5. Confira os saldos e o histórico antes de continuar os lançamentos.

O backup contém informações comerciais e dados de clientes. Guarde-o em local apropriado. Não envie a pasta `data` para um repositório público.

## O que ainda falta em relação ao projeto completo

- Migração e reconciliação dos dados reais do Base44. Recebemos o código, não uma exportação completa das entidades. O total atual pode exigir contagem física devido às inconsistências anteriores.
- Importação de planilhas e imagens em lote, consulta de fotos/preços Maria Dolores/VTEX e manutenção dessas integrações.
- Emissão fiscal e integração com API de notas.
- Implantação online, autenticação e banco adequado ao uso compartilhado.
- Aportes/retiradas e retorno do capital da operação; conciliação bancária, estornos financeiros e devoluções parciais.
- Compras manuais de reposição de um produto já cadastrado e correção de importações confirmadas. A reposição existente nesta versão é por XML; a compra manual está disponível no cadastro de um produto novo.

Consignação está disponível por XML, com lotes, repasses vinculados às vendas e devolução das peças não vendidas.

Para começar a migração, escolha uma data de corte: cadastre somente o estoque físico conferido nessa data e passe a lançar as operações posteriores. Não importe todas as compras antigas sobre esse saldo, pois isso duplicaria as entradas. Para preservar todo o histórico, importe as compras originais e cadastre todas as vendas e ajustes nas suas datas reais, em qualquer ordem de cadastro. Não some um saldo inicial atual às compras que já originaram esse mesmo estoque. Durante a reconstrução, os saldos ainda incluem peças cujas vendas não foram cadastradas.

## Novidades da versão 0.3.3

Em Consignação, Peças devolvidas à matriz mostra valor por peça e valor total de cada devolução, além da quantidade e valor gerais devolvidos. Os valores usam o custo de repasse, e os totais excluem devoluções canceladas.

Em Vendas, a busca inclui cliente, evento, origem, produto, código, forma de pagamento e número da venda. Digite “consig”, “consignada” ou “consignação” para encontrar vendas com peças consignadas, inclusive vendas mistas. A busca ignora maiúsculas e acentos. O resumo conta vendas não canceladas e suas peças próprias/consignadas; vendas canceladas aparecem separadamente.

## Novidades da versão 0.3.4

Cancelamento para corrigir lançamentos incorretos, inclusive com baixas; edição completa da venda no mesmo formulário; aplicação de markup ao preço da peça; botão Excluir teste cancelado removido. As alterações são atômicas, com backup e trilha interna, e formulários desatualizados são recusados. Não há nova migração do banco em relação à 0.3.3.

## Corrigir a classificação de uma nota importada (0.3.5)

Em Compras e XML, selecione a nota em Compras importadas e clique **Corrigir importação**. O formulário abre com o destino atual de cada item. Altere entre Estoque, Despesa e Ignorar, informe o motivo e salve. XML original, data, modalidade, valores, identificadores e chave da nota não mudam. Não reimporte o XML.

Estoque ↔ Despesa preserva a conta existente, seu vencimento e pagamento. Despesa entra no resultado na data original. Um item antes ignorado gera uma conta em aberto na data da nota: confira o vencimento e registre a baixa em Despesas quando aplicável. Ignorar elimina somente a conta não paga; itens pagos não podem ser ignorados. A modalidade consignada continua permitindo Estoque ou Ignorar, sem conta na entrada.

A retirada de estoque próprio é bloqueada se o produto possui vendas ou conferências vinculadas. Para consignados, lotes com vendas ou devoluções são bloqueados, inclusive devoluções canceladas conservadas no histórico. A restrição é conservadora: corrige-se o histórico vinculado antes de reclassificar sua entrada. Cadastros que ficam sem nenhuma entrada ou vínculo são arquivados; podem ser consultados em Arquivados, e são reativados ao recolocar o item em estoque nesta correção.

A operação cria backup e trilha interna, valida tudo em uma transação e recusa formulário desatualizado. Qualquer erro desfaz a correção inteira. Não há nova migração do banco nesta versão.

## Excluir nota importada (0.3.6)

Em Compras e XML, selecione a nota e clique **Excluir nota importada**. Confira os itens, o total da nota, as contas e baixas afetadas. Informe o motivo, digite `EXCLUIR NOTA NUMERO` conforme o formulário e confirme.

A operação remove a nota e seu XML do banco ativo, itens, entradas de estoque ou lotes consignados e despesas vinculadas, incluindo baixas pagas. Não faz estorno bancário. Cria backup completo antes de excluir e guarda uma trilha interna da exclusão. O XML original permanece recuperável no backup. A chave fica livre para uma nova importação.

Vendas e conferências do produto próprio bloqueiam a exclusão de forma conservadora, mesmo que existam outras notas desse produto. Movimentações de venda ou devolução do lote consignado também bloqueiam, inclusive devoluções canceladas preservadas no histórico. A mensagem informa os registros vinculados. A exclusão não apaga essas operações automaticamente.

Produtos compartilhados com outras notas e suas entradas são preservados. Cadastros sem outros vínculos são arquivados; a reimportação os reativa. A exclusão inteira acontece em uma transação e revalida os vínculos e pagamentos antes de remover. Não há migração de banco nesta versão.

## Dashboard de Relatórios (0.4.0)

Relatórios tem quatro abas: Resultado, Caixa, Vendas e Estoque e consignação. O período padrão inclui o mês atual e os cinco anteriores. Use os atalhos de 6/12 meses ou Este ano, ou informe De/Até e clique Atualizar relatório. Gráficos e exportações usam o período aplicado, sem truncar em seis meses. A comparação usa o intervalo imediatamente anterior, de igual duração em dias. Meses nas extremidades podem ser parciais.

- **Resultado:** receita após descontos, resultado gerencial, margem e despesas gerais; diferenças em reais e percentuais quando a base anterior é positiva; evolução mensal; composição do resultado com valor antes do desconto, descontos, custos, taxas, impostos, comissões, despesas e conferências. Tabelas detalham despesas, ajustes e meses; o CSV exporta a composição.
- **Caixa:** recebimentos líquidos de taxas, pagamentos e variação efetiva; evolução mensal; posição a receber/a pagar na data final, vencidos e vencimentos da data final até 30 dias depois, somente para contas já registradas até o corte. Tabelas e CSV detalham os movimentos. A variação não é saldo bancário, pois não inclui saldo inicial, aportes e retiradas.
- **Vendas:** filtro de peças próprias, consignadas ou todas; vendas e peças líquidas, receita, ticket e contribuição após custos e encargos, antes das despesas gerais. Vendas mistas entram nas duas origens conforme suas peças; descontos e encargos são rateados pelo valor dos itens e fecham em centavos. Uma venda mista conta uma vez no total e uma vez em cada origem, portanto os contadores por origem não devem ser somados. Ranking Top 10, tabelas e CSV seguem o filtro. O filtro não altera Resultado nem Caixa.
- **Estoque e consignação:** posição na data final, não apenas as entradas do período; quantidades e valores próprios e consignados, repasses pendentes, pagamentos por compras próprias e repasses e devoluções ativas do período. Tabelas e CSV detalham os saldos. Custos próprios pendentes aparecem como Em conferência.

Cancelamentos antigos mantidos no banco aparecem como reversões em sua data. Correções e exclusões dos lançamentos recalculam o período original. Indicadores líquidos podem ficar negativos em um período de reversões. O ticket fica sem valor se a quantidade líquida de vendas não for positiva. A margem fica sem valor quando não há receita positiva ou o resultado está em conferência.

A leitura do dashboard usa uma fotografia consistente do banco. Não altera dados nem exige migração. CDI/IPCA, exportação JSON e backup completo continuam disponíveis abaixo das abas. Os testes de interface usam o simulador oficial NiceGUI; não representam validação visual no Windows.


## Novidades da versão 0.4.1

Restauração completa de backup em Relatórios, com validação, confirmação, encerramento e aplicação na próxima abertura. Backup automático do banco substituído. Gerador Windows `GERAR_EXE.bat`, dados persistentes fora do executável e bloqueio de segunda instância por pasta de dados. Consulte `EXECUTAVEL_WINDOWS.md`.

## Estoque por local

Consulte GUIA_ESTOQUE_POR_LOCAL.md para distribuição inicial, transferências, recebimento, vendas, conferência física e relatórios.
