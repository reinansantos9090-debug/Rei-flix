# 07 — HOME ESTRUTURA

## CONTRATO
ReiAnix é biblioteca/reprodutor LOCAL. Não criar catálogo remoto ou dados fictícios. Preserve infraestrutura e a correção do episódio desaparecido. Leia o código real e use IDs estáveis.

## OBJETIVO
Construir Home em Compose conforme os screenshots, usando dados reais.

## IMPLEMENTAÇÃO
Criar cabeçalho com ReiAnix, busca, hero/destaque quando houver conteúdo, ação Assistir, Details/Minha Lista quando aplicável, Continuar assistindo e seções horizontais apenas quando houver conteúdo real. Usar LazyRow/LazyColumn com keys estáveis. O hero deve ser determinístico e baseado na biblioteca, sem rede. Para biblioteca vazia, mostrar estado apropriado. Para uma única obra, não criar carrossel vazio.

Garantir que ações usem Navigation Compose e IDs canônicos. Artwork deve usar cache existente. Evitar recompor toda Home por mudanças pequenas.

## NÃO FAZER
Não criar cinco seções vazias só para copiar screenshot. Não criar dados de exemplo em produção. Não adicionar funções remotas.

## ACEITAÇÃO
[ ] Home usa dados reais; [ ] artwork funciona; [ ] keys estáveis; [ ] scroll funciona; [ ] ações navegam; [ ] loading/vazio/erro tratados.

## VALIDAÇÃO
Testar biblioteca vazia, uma obra, múltiplas obras, scroll e abertura de Details. Executar build/testes.

## RELATÓRIO
Informar diff, componentes reutilizados, testes e limitações.