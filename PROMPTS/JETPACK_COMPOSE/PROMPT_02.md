# 02 — TEMA VISUAL BASE

## CONTEXTO OBRIGATÓRIO
Você está trabalhando no ReiAnix, biblioteca/reprodutor LOCAL. Leia o código real antes de alterar. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download, catálogo remoto, banco paralelo ou dados fictícios. Preserve a correção do episódio que desaparecia. Use IDs estáveis, considere lifecycle/cancelamento e evite refatorações não relacionadas.

## OBJETIVO
Construir o Design System nativo compartilhado pelas telas futuras, usando os screenshots como referência visual.

## IMPLEMENTAÇÃO
Criar fonte única de cores, tipografia, dimensões, shapes, elevações, espaçamentos e componentes reutilizáveis. Direção: fundo preto/quase preto; superfícies azul-marinho muito escuras; azul elétrico como primária; textos brancos/cinza-claro; cards e chips arredondados; botões grandes; navegação inferior escura; estados ativos em azul. Integrar Material 3 e WindowInsets/status/navigation bars. Criar tokens para evitar valores espalhados. Componentes base podem incluir card, chip, botão primário/secundário, título de seção, artwork com placeholder e indicador de progresso quando realmente reutilizáveis.

Os screenshots são referência de linguagem visual, não autorização para inventar funcionalidades. O tema deve funcionar em Android real e permanecer coerente em diferentes densidades.

## NÃO FAZER
Não construir telas completas. Não alterar banco, scanner ou player. Não criar componentes que existam apenas para uma tela sem necessidade de reutilização.

## ACEITAÇÃO
[ ] tema centralizado; [ ] tokens reutilizáveis; [ ] Material 3 integrado; [ ] barras do sistema compatíveis; [ ] componentes base compilam; [ ] infraestrutura existente intacta.

## VALIDAÇÃO
Compilar o módulo Android e executar testes relevantes. Registrar limitações de ambiente.

## RELATÓRIO
Informar diff, arquivos/pastas adicionados/modificados/removidos, componentes criados/reutilizados, testes e limitações.