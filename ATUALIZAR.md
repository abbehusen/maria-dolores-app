# Atualizar para 0.6.7

Importação aceita também a matriz Maria Dolores (08.450.759/0001-88) e notas destinadas ao CPF cadastrado da Nanda. Os XMLs originais e a proteção contra notas repetidas são preservados. Outros fornecedores e destinatários continuam sujeitos ao cadastro permitido.

Sem mudança de banco ou dependências. Feche o app, preserve a pasta data e siga o procedimento abaixo. Se utiliza executável Windows, gere novamente.

# Atualizar para 0.6.6

O seletor XML agora distingue rejeição por tamanho, extensão e seleção duplicada. Arquivo vazio tem mensagem própria. A fila é limpa após a leitura, permitindo enviar a próxima nota ou tentar novamente, preservando a prévia e a proteção contra NF-e já importada.

Preserve a pasta data e siga o procedimento abaixo. Nenhuma mudança de banco ou dependências. Se utiliza executável Windows, gere novamente.

# Atualizar para 0.6.5

Estoque em modo Tabela permite seleção múltipla. Exportar seleção inclui somente os produtos marcados e avisa quando não há seleção. Marcar / Desmarcar tudo abrange todas as páginas do filtro atual. Ao mudar filtros ou atualizar, a seleção é limpa. Editar cadastro, Conferir estoque e Ver histórico continuam exigindo exatamente um produto. No Catálogo, Exportar lista filtrada mantém a exportação dos produtos exibidos pelo filtro.

Sem mudança de banco ou dependências. Preserve a pasta data e siga o procedimento de atualização abaixo. O executável Windows deve ser gerado novamente.

# Atualizar para 0.6.4

Validação desta versão: 132 testes automatizados aprovados. O pacote contém código Python e instruções para gerar o executável; o executável Windows não foi compilado neste ambiente.

- Percentuais na edição exibem duas casas decimais; salvar sem mudança financeira preserva os centavos originais.
- Importação XML sugere Com Nanda. Vendas novas abrem em Direto · Nanda com as comissões do canal aplicadas.
- Transferências ocultam variantes já adicionadas; Remover devolve a variante à lista.
- A coluna Contribuição da venda mostra receita após descontos menos custo, taxas, impostos e comissões, antes das despesas gerais.
- Estoque → Peças por local: selecione a peça e use Registrar peça perdida. A aba Peças perdidas mantém histórico e permite estornar quando encontrada. Perdas têm receita zero e custo no resultado gerencial; não são vendas. Perda consignada gera repasse não pago à matriz, conforme responsabilidade indicada no formulário.
- Banco migra para esquema 8 com backup automático. Preserve data e faça backup antes de atualizar. Nenhuma peça antiga é transferida automaticamente.

# Atualizar para 0.6.3

Novidades: exclusão de canais e vendedores/beneficiários sem histórico; nova aba **Canais e clientes** em Relatórios, com gráficos de quantidade de vendas por canal e vendedora e valor comprado por cliente. Há tabelas e exportação CSV.

Os filtros do topo valem para todas as abas: **Todo o histórico**, **Mês específico → Aplicar mês**, ou **De / Até → Atualizar relatório**. A contagem é de registros de venda, não peças. Retiradas pessoais não entram; cancelamentos históricos reduzem os valores na data do cancelamento. O valor comprado não equivale necessariamente a dinheiro já recebido.

Na aba Comissões, selecione o canal e clique **Excluir canal**, ou selecione a pessoa na tabela de saldos e clique **Excluir vendedor(a) / beneficiário**. Confirme no diálogo. A exclusão remove também vínculos de vendedoras do cadastro excluído, mas preserva os demais cadastros. Canais com vendas não podem ser excluídos: desative-os em Editar canal. Beneficiários usados em vendas, comissões ou como recebedores de canais ficam protegidos. A exclusão de uma vendedora é global, não apenas de um vínculo com um canal.

Feche o app, substitua os arquivos e preserve a pasta `data`. Não há nova migração de banco. Se usa executável, gere-o novamente com `GERAR_EXE.bat`.

---

# Atualizar para 0.5.1

Correção do cadastro de canais: o botão **Cadastrar beneficiário aqui**, junto ao campo de quem recebe a comissão, abre o cadastro com o nome do canal preenchido. Ao salvar, o beneficiário é selecionado automaticamente e o formulário do canal continua aberto, preservando seus campos. Também permite selecionar um beneficiário existente.

Feche o app e substitua os arquivos do programa, preservando a pasta `data`. Não há mudança no banco de dados nem necessidade de recadastrar informações. Se usa o executável, gere novamente com `GERAR_EXE.bat` e substitua o programa conforme `EXECUTAVEL_WINDOWS.md`.

Na versão 0.5.0, também é possível cadastrar a loja antes pelo botão **Cadastrar / vincular vendedora ou loja** na aba Comissões, sem vínculo de vendedora, e depois selecioná-la ao criar o canal.

---

# Atualizar para 0.5.0

1. Na versão atual, baixe um backup completo em Relatórios e encerre o app.
2. Extraia o novo pacote e substitua os arquivos do programa, preservando toda a pasta `data`. Não reimporte notas já existentes.
3. Execute normalmente. A base é atualizada para a estrutura 5, com backup automático antes da migração. Clientes das vendas antigas são cadastrados automaticamente.
4. Configure beneficiários, canais e vendedoras na aba Comissões. Percentuais e canais antigos não são adivinhados. Comissões antigas podem ser vinculadas explicitamente a um beneficiário nessa aba.
5. Confira estoque, contas e saldos. Leia `GUIA_CANAIS_COMISSOES_CLIENTES.md`.

Para usar o executável, gere-o com `GERAR_EXE.bat` e siga `EXECUTAVEL_WINDOWS.md`. O banco do executável fica em `LOCALAPPDATA\FeAbbehusenFlow\data`; atualizar o programa não substitui esse banco. Restaurar um backup substitui a base inteira, não combina bancos de computadores diferentes.

Não abra a base já migrada com versões anteriores do app. Para voltar à versão anterior, use também uma cópia do backup anterior à migração.

Validação desta entrega: 102 testes automatizados passaram, incluindo simulação de interface, retirada própria/consignada, resgate integral/misto, comissões antigas e restauração de base anterior. A geração e execução do `.exe` precisam ser feitas e conferidas no Windows; não foram executadas neste ambiente Linux.

---

# Atualizar para 0.4.1

Preserve sua pasta data. Para gerar o executável e transferir sua base atual, siga EXECUTAVEL_WINDOWS.md. A versão Python continua usando a pasta data original. O executável usa LOCALAPPDATA\FeAbbehusenFlow\data; use Restaurar backup para importar sua base.

# Atualizar para a versão 0.4.0 — Windows

Novidades da 0.4.0: dashboard em Relatórios com abas Resultado, Caixa, Vendas e Estoque e consignação; comparação com período anterior, gráficos mensais, detalhes e CSVs. Padrão de seis meses, atalhos e período personalizado. O filtro de origem aplica-se somente à análise de vendas. Não há nova migração ou dependência; preserve a pasta data e não reimporte notas.

Novidades da 0.3.6: Excluir nota importada em Compras e XML. Remove a nota, suas entradas e contas (inclusive baixas), com confirmação escrita e backup. Vendas, devoluções e conferências vinculadas bloqueiam a exclusão. Depois é possível reimportar o XML. Não há migração nova.

Novidades da 0.3.5: botão Corrigir importação em Compras e XML. Selecione uma nota, altere os destinos dos itens, informe o motivo e salve. Trocas Estoque ↔ Despesa preservam pagamentos; itens pagos não podem ser ignorados, e entradas com movimentações dependentes são bloqueadas. O XML original é preservado. Não há migração nova; não reimporte notas existentes.

Novidades da 0.3.4: edição completa de vendas, aplicação de markup ao preço e cancelamento para corrigir lançamentos errados mesmo com baixas. O botão Excluir teste cancelado foi removido. Não há nova migração para quem usa a 0.3.3.

Novidades da 0.3.3: valores unitários e totais das devoluções, totais gerais sem devoluções canceladas, e busca ampliada em Vendas com contagem de vendas e peças filtradas. Não há nova migração para quem já está na versão 0.3.2. Não reimporte XMLs já cadastrados.

Novidades da 0.3.2: saldos próprio/consignado na seleção da venda, seleção automática do único lote disponível e seção de devoluções com cancelamento para correção de erros. A base é atualizada automaticamente com backup antes da migração; devoluções antigas são preservadas.

Novidade da 0.3.1: produtos exclusivamente consignados ficam fora da tela Estoque; Consignação mostra totais gerais de quantidade e valor em mãos, além do subtotal filtrado. Não há nova migração para quem já usa a 0.3.0.

A versão 0.3.0 adiciona **compra própria e consignação**. Ao abrir sua base anterior, cria um backup e atualiza as tabelas automaticamente. Dados existentes permanecem na modalidade própria, com os mesmos saldos e pagamentos.

1. Na versão atual, use **Relatórios → Baixar backup completo** e guarde o arquivo.
2. Encerre o programa com **Ctrl+C** no terminal.
3. Extraia este ZIP em uma pasta temporária. Copie o conteúdo de `fe_flow` sobre a pasta `fe_flow` que você já usa, substituindo os arquivos de código. **Preserve sua pasta `data` inteira**. Não apague a pasta antiga para substituí-la pela nova. O ZIP não contém banco de dados.
4. No terminal, abra a pasta habitual, ative o ambiente e execute:

```powershell
conda activate fe-flow
python main.py
```

Continue usando o mesmo `--data-dir`, se você já usa um caminho personalizado. Não use `--demo` para abrir seus dados reais. Não é necessário recriar o ambiente: as dependências não mudaram.

Ao abrir a base da versão anterior, a atualização faz um backup em `data/backups`, atualiza as tabelas e reconstrói os custos. Compras, XMLs, vendas e recebimentos existentes são preservados. Confira os saldos após abrir. O backup automático fica dentro do diretório de dados escolhido.

## Compras e vendas antigas

Pode importar todos os XMLs e depois cadastrar as vendas antigas, uma a uma, em qualquer ordem. Informe a data real de cada venda e a data efetiva do recebimento. Uma compra futura não será usada para calcular o custo de uma venda anterior.

Se ainda faltar uma compra, marque **Lançamento histórico — permitir pendências de estoque**. A venda é registrada, mas seus custos e resultados afetados ficam **Em conferência** até regularizar as entradas. Se todas as compras anteriores já estiverem cadastradas, essa opção não é necessária.

Ao inserir operações antigas, os custos e lucros posteriores podem mudar. Preços de venda, taxas e recebimentos não são alterados pelo recálculo. No mesmo dia, entradas de compra/saldo inicial são consideradas antes das outras movimentações, que seguem a ordem de cadastro.

Não cadastre o estoque atual como saldo inicial e depois importe novamente as compras que o formaram: isso duplicaria as entradas.

## Corrigir ou cancelar uma venda

- Selecione a venda e clique **Editar venda**. O formulário abre preenchido. Para mudar uma peça, clique **Alterar peça**, ajuste quantidade, preço ou markup e clique **Adicionar à venda**. Confira o restante, informe o motivo e salve.
- As baixas anteriores são mantidas por padrão, com valores corrigidos. Para apagá-las também, marque **Desfazer baixas anteriores**; indique o novo recebimento integral ou faça as baixas posteriores nas telas correspondentes. Mudança de parcelamento com baixas existentes exige essa opção.
- Para desfazer todo o registro errado, selecione a venda e clique **Cancelar venda**. Informe o motivo e confirme. A venda sai da lista, e seus recebimentos, despesas e repasses são removidos, mesmo se marcados como pagos. Isso também permite limpar uma venda já cancelada na versão anterior.
- As peças retornam à origem própria ou consignada mediante recálculo histórico. Conferências físicas posteriores continuam valendo como contagens absolutas.
- Cada correção cria backup em `data/backups` e preserva trilha interna. Nenhuma dessas ações movimenta dinheiro no banco. Use o cancelamento para corrigir registros; ele não representa uma restituição financeira de venda real.

## Se precisar voltar à versão anterior

Não abra o banco atualizado com o código 0.1. Pare o programa e restaure uma cópia do backup anterior em outro diretório, conforme o README. Mantenha o banco atualizado guardado. Alterações feitas depois do backup não estarão na cópia restaurada.

## Usar consignação

1. Em **Compras e XML**, selecione **Consignação** na prévia e confira o custo unitário. A entrada não gera conta a pagar.
2. Consulte os lotes na nova aba **Consignação**.
3. Na venda, escolha o produto e sua **Origem da peça** (próprio ou lote consignado). Ajuste o preço efetivo normalmente.
4. O custo do lote gera uma conta de repasse à matriz. Pague em **Despesas**, usando a seleção em lote se desejar; busque por “consignação” para localizar as contas.
5. Para peças não vendidas, selecione o lote e use **Devolver peças à matriz**.

O markup não altera o custo do repasse. A atualização não converte notas antigas para consignado. Se uma remessa consignada já foi importada como compra própria, não importe de novo: essa correção exige tratar o histórico existente.

## Correção de comissões — 0.6.2

Ao desmarcar Usar crédito de comissão, o formulário restaura os percentuais anteriores. Na edição, Aplicar percentuais do canal permite corrigir valores antigos; um aviso identifica comissão zerada apesar do cadastro do canal. Nenhuma venda antiga é recalculada automaticamente.

Para corrigir a venda Su Misura: abra Editar venda, clique Aplicar percentuais do canal, confira 30% para loja e 0% para vendedora, informe o motivo e salve. Sobre R$ 1.325,47, a comissão é R$ 397,64.

Validação: 107 testes passaram. Executável Windows não compilado neste ambiente.

## Estoque por local — 0.6.2

Banco atualizado para esquema 6 com backup anterior automático. Todos os saldos antigos começam em Local a definir. Consulte GUIA_ESTOQUE_POR_LOCAL.md. Preserve data; não volte a uma versão anterior com o banco já migrado. Gere novamente o executável no Windows.

## Venda por item e local — 0.6.2

Banco atualizado para esquema 7. Filtro de local antes de Produto, busca em Todos os locais, disponibilidade descontando o carrinho e locais diferentes na mesma venda. Vendas antigas mantêm a localização original; a migração cria os vínculos de cada item. Preserve data e gere novamente o executável.

## Melhorias de comissões — 0.6.2
Cadastro automático da própria loja como recebedora, mensagens por regra, canais nos saldos, total vendido por canal, filtros e totais pagos em dinheiro/peças. Sem alteração do esquema do banco. Preserve data; gere novamente o executável se o utiliza.

## Canal e local vinculados automaticamente — 0.6.3

Ao salvar um canal novo, o aplicativo cria um local de estoque com o mesmo nome e o vincula. Isso vale para Direto, Loja, Site e Evento. Um local existente de nome equivalente é reaproveitado e ativado. Nenhuma peça é transferida automaticamente.

Um vínculo já configurado é preservado ao editar o canal, inclusive se ele aponta para Com Nanda. Renomear o canal não renomeia o local, que pode ser compartilhado com outros canais. Para canais antigos sem vínculo, abra Editar canal e salve para criar/reaproveitar o local. A coluna Local de estoque mostra a associação. O vínculo pode ser ajustado em Estoque → Peças por local → Locais e canais.

Validação: 128 testes automatizados. Preserve data ao atualizar e gere novamente o executável, se o utiliza. Compilação Windows não realizada neste ambiente.
