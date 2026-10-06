# Fe Abbehusen Flow 0.6.3 — executável e restauração

## Gerar no Windows

1. Instale o Python 3.12 de 64 bits, incluindo o Python Launcher (`py`).
2. Extraia o ZIP em uma pasta gravável.
3. Dê dois cliques em `GERAR_EXE.bat`. A primeira execução precisa de internet para baixar as dependências.
4. O resultado fica em `dist\FeAbbehusenFlow\FeAbbehusenFlow.exe`.

Distribua **a pasta `FeAbbehusenFlow` inteira**, incluindo `_internal`. O executável depende desses arquivos. No computador de destino não é necessário instalar Python. Gere com Windows e Python de 64 bits para PCs Windows de 64 bits. A geração e execução finais devem ser verificadas no Windows.

## Abrir e fechar

Abra `FeAbbehusenFlow.exe`. O navegador abrirá a interface local. A janela de console fica aberta enquanto o servidor está funcionando; feche-a para encerrar o programa. Fechar apenas a aba do navegador não encerra o app. A porta padrão é 8080; para mudar, execute `FeAbbehusenFlow.exe --port 8081`.

Apenas uma instância por pasta de dados é permitida. Cada computador tem seu banco independente. Esta versão não sincroniza computadores.

## Dados e atualizações

O executável salva em `%LOCALAPPDATA%\FeAbbehusenFlow\data`, fora da pasta do programa. Para acessar, cole esse caminho no Explorador de Arquivos. A base principal é `flow.sqlite3`; a demonstração usa `demonstracao.sqlite3`.

Ao atualizar, baixe um backup, feche o app e substitua a pasta do programa inteira. Preserve a pasta de dados. Não misture arquivos `_internal` de versões diferentes. Migrações já previstas pelo app continuam sendo aplicadas com seus backups.

A execução pelo código (`python main.py`) mantém o caminho anterior, `data` ao lado de `main.py`. O parâmetro `--data-dir` continua permitindo escolher explicitamente outra pasta.

## Levar a base existente para o executável ou outro computador

1. Na instalação de origem, acesse **Relatórios → Seus dados, com você → Baixar backup completo**.
2. Abra o executável no computador de destino.
3. Em **Relatórios → Seus dados, com você → Restaurar backup**, selecione o `.sqlite3`.
4. Digite `RESTAURAR` e confirme. O app valida o arquivo e encerra.
5. Abra novamente. Antes de disponibilizar as telas, o programa guarda o banco atual em `data\backups\antes-restauracao-...sqlite3` e aplica o backup.

A restauração substitui todos os dados, incluindo XMLs, vendas, estoque, contas e histórico. Não mescla lançamentos. Combine quem está usando a cópia principal antes de transferir. JSON não serve para restauração completa. Limite do upload: 100 MB. Backups de estruturas futuras ou desconhecidas são recusados.

Se o app não conseguir concluir a restauração na inicialização, a mensagem aparece no console. Preserve os arquivos; o pedido fica em `flow.restore-pending` (ou `demonstracao.restore-pending`). Para cancelar um pedido pendente, com o app fechado, mova esse arquivo para fora da pasta de dados. O backup anterior permanece em `backups` quando já tiver sido criado.

Para voltar aos dados anteriores após uma restauração concluída, restaure o arquivo `antes-restauracao-...sqlite3` pela mesma interface.

## Verificação no seu Windows

Antes de usar dados reais: gere o pacote, abra em modo demonstração com `FeAbbehusenFlow.exe --demo`, baixe e restaure um backup, reabra e confira os registros. Teste também a cópia da pasta completa no PC da Nanda. Este pacote contém o código e o gerador; não contém um `.exe` já compilado.
