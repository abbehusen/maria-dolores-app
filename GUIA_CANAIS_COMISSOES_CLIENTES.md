# Canais, comissões, retiradas e clientes — versão 0.6.3

## Configuração inicial

Na aba **Comissões**, cadastre os beneficiários (quem tem direito à comissão), depois os canais e vincule as vendedoras. Você também pode começar pelo canal: clique em **Cadastrar beneficiário aqui** abaixo da seleção de quem recebe a comissão. O nome do canal vem preenchido, e, ao salvar o beneficiário, ele é selecionado automaticamente sem fechar o canal. Uma pessoa pode atuar em mais de um canal. Preencha os percentuais reais; o app não presume os acordos comerciais.

| Canal | Tipo | Configuração sugerida |
| --- | --- | --- |
| Direto · Nanda | Direto | Sem comissão; canal criado automaticamente |
| CASA FIAES | Loja | Parte para a loja e parte para a vendedora; cadastre a loja como beneficiária e vincule suas vendedoras |
| SU MISURA | Loja | Comissão somente para a loja; selecione a vendedora na venda para acompanhar sua atuação, sem gerar outra obrigação para Nanda |
| E-commerce | Site | Percentuais conforme o acordo; é um canal de registro, sem integração automática com uma plataforma |
| Feira ou evento | Evento | Crie um canal para cada evento e vincule a vendedora contratada |

O canal pode usar comissão zero, só da loja, só da vendedora ou dividida. Alterar os percentuais do canal vale para novos lançamentos; as vendas já salvas preservam seus valores e identificação histórica. O cálculo percentual usa a receita da venda após descontos. No formulário, confira os valores antes de salvar.

## Registrar vendas e administrar comissões

Em **Vendas**, selecione canal e vendedora nos campos de seleção. A lista de vendedoras depende do canal. Quando há comissão da vendedora, é obrigatório informar quem vendeu.

A comissão nasce na data da venda, mesmo quando o cliente ainda não pagou. A aba Comissões mostra valores gerados, liquidados e saldo por beneficiário. O pagamento em dinheiro pode ser parcial, com data e método próprios. Ele reduz a dívida e movimenta o caixa, sem descontar novamente a comissão do resultado da venda.

Para uma beneficiária pegar peças, registre uma venda pelo preço efetivo de venda, marque o uso de crédito de comissão e escolha a beneficiária e o valor utilizado. O app baixa o estoque, registra o custo e reduz o crédito. Esse valor não entra no caixa. Se a peça custar mais que o crédito usado, informe como será pago o restante (por exemplo, Pix). É possível usar todo o crédito ou só uma parte. O resgate não gera outra comissão.

Exemplo: uma peça vendida por R$ 500, com custo de R$ 220, quitada integralmente com crédito, registra R$ 500 de receita, R$ 220 de custo, R$ 500 de comissão liquidada e zero recebimento em dinheiro. A despesa de comissão já foi reconhecida na venda que originou o crédito; não deve ser lançada novamente no resgate. Tributos e outras taxas não estão incluídos nesse exemplo.

O saldo disponível considera a data da liquidação e os usos já registrados. Não é possível consumir crédito inexistente. Para corrigir uma venda cuja comissão já foi usada, desfaça primeiro a liquidação: pagamento em dinheiro pelo extrato de Comissões; resgate em peças corrigindo ou cancelando a venda de resgate. Correções ficam no histórico de auditoria.

Comissões antigas sem beneficiário aparecem para vinculação manual. Não cadastre a mesma comissão de novo. Ao vincular uma comissão antiga já paga, o app preserva o pagamento e o histórico financeiro.

## Retirada para uso pessoal

No formulário de Vendas, escolha **Retirada para uso pessoal**, informe quem retirou e selecione as peças. Não há receita, recebimento, cliente comprador ou comissão. O estoque é baixado ao custo; o relatório mostra o custo retirado separadamente da margem das vendas.

O app mantém margem do lançamento zerada internamente e apresenta margem comercial como não aplicável. Não cria uma venda fictícia pelo custo. O custo da retirada não é deduzido novamente do resultado comercial. Para peças consignadas, a retirada mantém a obrigação de repasse ao fornecedor, que deve ser paga normalmente.

Esse é o controle gerencial do app. A classificação na escrituração da empresa e a documentação fiscal da saída devem ser definidas com o contador conforme a situação da empresa.

## Clientes

Ao registrar uma venda com nome de cliente, o cadastro é criado automaticamente. Você também pode selecionar um cliente já cadastrado. A identificação automática usa nome e telefone normalizados; nomes ou telefones diferentes podem criar registros separados, por isso prefira selecionar o cadastro existente.

Na aba **Clientes**, complete telefone, e-mail, aniversário, endereço, cidade, preferências e observações. A lista mostra total comprado, quantidade de vendas e última compra; o histórico detalha os produtos. Vendas canceladas e retiradas pessoais não entram nas compras do cliente. O total comprado é o valor das vendas, não necessariamente o valor já recebido.

A autorização para comunicações comerciais começa desmarcada. O CSV para mala direta inclui somente os clientes com essa autorização registrada. O app exporta a lista, mas não envia mensagens ou campanhas.

## Relatórios

A análise por forma de pagamento separa vendido no período, recebido no período, taxas e compensações com crédito de comissão. Uma venda parcelada pode aparecer no vendido de um mês e no recebido dos meses seguintes. Crédito de comissão não é Pix, cartão nem entrada de dinheiro.

Também há resumo de vendas por canal e vendedora e uma seção própria para retiradas pessoais. Use as mesmas datas ao comparar relatórios. Custos ainda pendentes de conferência continuam identificados como pendentes.

## Atualização e backup

A atualização preserva a base e cria backup antes da migração. O backup inclui clientes, canais, vendedoras, comissões e liquidações. Restaurar substitui toda a base e não sincroniza dois computadores: mantenha uma base de referência quando transferir dados entre Nanda e Marcelo.

A importação dos CSVs do Base44 continua sendo uma etapa separada. Este pacote não inclui dados comerciais reais nem executa esse carregamento.

## Comissões simplificadas — 0.6.2

Beneficiário significa a pessoa ou empresa com direito à comissão. Na tabela de canais, a coluna agora se chama Quem recebe pelo canal. Não é necessariamente a vendedora: uma venda pode identificar a vendedora, enquanto o crédito pertence integralmente à loja.

Ao escolher Toda a comissão para a loja / canal ou comissão dividida, A própria loja / canal é o padrão. Basta informar nome e percentual e salvar: o vínculo de recebimento é criado automaticamente, sem cadastrar uma pessoa como vendedora. Para uma pessoa ou empresa diferente, selecione Outra pessoa / empresa. Cadastros existentes mantêm seus vínculos; nenhuma comissão histórica é redistribuída.

As orientações variam com a regra escolhida. A referência fixa à SU MISURA foi removida.

Em Comissões, filtre por canal, tipo ou nome de vendedora/recebedor. A coluna Canais de venda mostra vínculos atuais e canais com histórico de comissões. Cada recebedor aparece uma única vez mesmo atuando em várias lojas.

Total pago / utilizado, dinheiro, peças e saldo a pagar somam os recebedores exibidos, incluindo lojas e pessoas. Canal e tipo recortam os valores pela venda que originou cada comissão. Uma baixa que abrange várias origens é distribuída conforme seus vínculos efetivos, sem duplicação.

O total vendido por canal considera vendas após desconto, incluindo compensações em crédito de comissão; exclui retiradas pessoais e cancelamentos. Ao pesquisar uma pessoa, a tabela exibe seus canais e o total completo desses canais, não apenas as vendas realizadas por ela. Os valores cobrem o histórico registrado.

O pagamento e o extrato permanecem por recebedor e abrangem todos os seus canais; o diálogo de pagamento identifica expressamente o saldo total.

Validação: 123 testes automatizados. Não foi compilado o executável Windows neste ambiente.

## Canal e local vinculados automaticamente — 0.6.3

Ao salvar um canal novo, o aplicativo cria um local de estoque com o mesmo nome e o vincula. Isso vale para Direto, Loja, Site e Evento. Um local existente de nome equivalente é reaproveitado e ativado. Nenhuma peça é transferida automaticamente.

Um vínculo já configurado é preservado ao editar o canal, inclusive se ele aponta para Com Nanda. Renomear o canal não renomeia o local, que pode ser compartilhado com outros canais. Para canais antigos sem vínculo, abra Editar canal e salve para criar/reaproveitar o local. A coluna Local de estoque mostra a associação. O vínculo pode ser ajustado em Estoque → Peças por local → Locais e canais.

Validação: 128 testes automatizados. Preserve data ao atualizar e gere novamente o executável, se o utiliza. Compilação Windows não realizada neste ambiente.
