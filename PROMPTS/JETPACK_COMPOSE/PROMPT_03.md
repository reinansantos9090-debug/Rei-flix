# 03 — NAVEGAÇÃO NATIVA

## CONTRATO
ReiAnix continua sendo biblioteca/reprodutor LOCAL. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download, catálogo remoto ou banco paralelo. Leia a estrutura real antes de alterar e preserve o bugfix do episódio desaparecido.

## OBJETIVO
Implantar Navigation Compose e rotas que representem somente funções reais do ReiAnix.

## IMPLEMENTAÇÃO
Criar destinos principais para Início, Biblioteca, Buscar e Ajustes, além de Details e Player quando necessários. Definir argumentos estáveis, preferindo IDs canônicos para Details/Player em vez de posições, índices ou objetos serializados grandes. Implementar back stack previsível, retorno do botão voltar do sistema, restauração do estado das abas e retorno do Player para a origem. A bottom navigation deve aparecer somente nos destinos principais.

Garantir que navegação repetida não acumule cópias desnecessárias da mesma aba. Avaliar launchSingleTop, restoreState e popUpTo conforme a arquitetura real. Não perder estado de scroll sem motivo. Details deve saber de qual origem veio quando isso afetar o retorno.

## NÃO FAZER
Não criar aba Downloads só porque aparece em referências externas. Só criar um destino se houver funcionalidade real. Não manter duas navegações concorrentes sem uma estratégia clara de transição.

## ACEITAÇÃO
[ ] rotas estáveis; [ ] Details preserva origem; [ ] back funciona; [ ] Player retorna corretamente; [ ] estado das abas é preservado; [ ] navegação compila em Android real.

## VALIDAÇÃO
Testar navegação entre todas as rotas, back do sistema, abertura repetida de Details e retorno do Player. Executar testes e build.

## RELATÓRIO
Descrever diff, testes, estruturas reutilizadas e limitações.