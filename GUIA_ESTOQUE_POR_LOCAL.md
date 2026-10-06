# Estoque por local — versão 0.6.3

## Começar
1. Faça backup, feche o aplicativo e atualize preservando a pasta data.
2. Entre em Estoque → Peças por local · distribuir e transferir.
3. Em Locais e canais, cadastre SU MISURA, Casa FIAES e outros locais. Com Nanda já existe.
4. Distribua o saldo atual de Local a definir para os locais reais, depois de uma conferência física. Não importe as mesmas compras novamente.
5. Vincule cada canal ao local que deve ser sugerido nas vendas. Canal e local são informações independentes.

## Consultar
Selecione um local e busque nome, código, material, pedra ou tamanho. Todos os locais permite consultar onde estão as unidades da mesma peça. A tabela separa estoque próprio de cada lote consignado. Fotos aparecem quando há URL de imagem no cadastro. Exporte a lista filtrada em CSV; ela contém valores internos, incluindo custos.

## Movimentar
Distribuir / transferir aceita várias peças, origem, destino, data e motivo. A operação é integral: se uma linha exceder o saldo, nada é gravado. Não altera custo, receita, caixa ou comissão. Para retorno entre lojas e Nanda, faça uma transferência inversa. O histórico permanece disponível.

Entradas manuais e XMLs permitem selecionar Local de recebimento. O padrão é Local a definir, para evitar atribuir peças a um lugar sem confirmação.

Em Vendas, selecione Local de saída das peças. O canal sugere o local vinculado; é possível alterar. Cada linha do carrinho mantém seu local: uma venda pode conter peças de lugares diferentes. A mesma peça em locais diferentes deve ter o mesmo preço unitário na venda. Retiradas pessoais também usam o local selecionado. Cancelamentos devolvem ao local da venda; correções recalculam os saldos. Vendas antigas continuam em Local a definir: não se inventa uma localização histórica.

## Conferência e proteção
Selecione uma linha própria e use Conferir quantidade no local. A contagem é registrada na data atual, altera o saldo total pelo desvio encontrado e exige motivo. Se houver unidades adicionais, informe seu custo. Se a peça apenas está em outro lugar, use transferência, não ajuste.

Consignados exigem correção documentada de entrada, venda ou devolução, sem inventar unidades ou custo de repasse. Para devolver à matriz pelo fluxo existente, transfira antes para Local a definir. Entradas vinculadas a transferências podem ter sua exclusão/correção bloqueada para preservar o histórico físico; confira a distribuição e o documento antes de alterar.

Locais com saldo não podem ser desativados. Não há exclusão de locais nem apagamento de transferências; use edição/desativação e transferências inversas. A validação verifica saldos por data (não hora) e impede que alterações retroativas tornem um local negativo.

## Relatórios
Relatórios → Estoque e consignação inclui unidades por local na data final do filtro, separando próprias e consignadas. A consulta detalhada de peças, custo e valor de venda em Estoque por local mostra o saldo atual. O custo das peças próprias segue o custo médio do cadastro, sem criar lotes de custo por loja.

## Validação
120 testes automatizados: migração v5 com dados, backups, distribuição, lote atômico, venda sem saldo, cancelamento, retirada pessoal, contagem local, consignação, datas retroativas e interface. Compilação e execução do .exe devem ser conferidas no Windows.

## Seleção inteligente na venda
O campo Local de saída das peças fica acima de Produto. Um local específico mostra somente peças com saldo nele, descontando o que já está no carrinho. Todos os locais permite pesquisar opções identificadas pelo local; selecionar uma opção preenche o local correspondente. Local a definir mostra somente peças ainda não distribuídas.

Origem da peça (Estoque próprio ou Consignado) identifica a propriedade e o lote, não o endereço físico. O canal pode sugerir o local, mas mudar o canal ou filtro não altera os locais já gravados no carrinho. Alterar peça permite removê-la temporariamente e ajustar local, origem, quantidade e preço.

Na reconstrução de histórico, a opção de permitir pendências continua disponível exclusivamente para estoque próprio em Local a definir. Demais locais e consignados exigem saldo. As vendas antigas recebem os vínculos de local na atualização, preservando saldos e custos.

## Canal e local vinculados automaticamente — 0.6.3

Ao salvar um canal novo, o aplicativo cria um local de estoque com o mesmo nome e o vincula. Isso vale para Direto, Loja, Site e Evento. Um local existente de nome equivalente é reaproveitado e ativado. Nenhuma peça é transferida automaticamente.

Um vínculo já configurado é preservado ao editar o canal, inclusive se ele aponta para Com Nanda. Renomear o canal não renomeia o local, que pode ser compartilhado com outros canais. Para canais antigos sem vínculo, abra Editar canal e salve para criar/reaproveitar o local. A coluna Local de estoque mostra a associação. O vínculo pode ser ajustado em Estoque → Peças por local → Locais e canais.

Validação: 128 testes automatizados. Preserve data ao atualizar e gere novamente o executável, se o utiliza. Compilação Windows não realizada neste ambiente.
