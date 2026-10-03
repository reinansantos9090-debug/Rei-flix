# 26 — DESEMPENHO COMPOSE

## CONTRATO
ReiAnix é uma biblioteca/reprodutor LOCAL. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming/download remoto, banco paralelo ou dados fictícios. Leia o código real antes de alterar. Preserve o bugfix dos episódios desaparecendo. Use IDs estáveis e considere lifecycle/cancelamento.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Otimizar Compose para Android real sem sacrificar legibilidade ou estabilidade.

## IMPLEMENTAÇÃO
Auditar recomposições, keys de LazyColumn/LazyGrid, remember, derivedStateOf, coleta de Flow, artwork, scroll, navegação, memória e jobs. Banco/filesystem não devem ser chamados diretamente por Composables. Usar lifecycle-aware collection. Evitar reconstruir telas inteiras por uma mudança de progresso. Medir antes/depois quando possível. Verificar vazamentos de Activity/context e jobs.

## NÃO FAZER
Não fazer micro-otimizações que compliquem a arquitetura. Não introduzir cache paralelo sem necessidade. Não remover atualizações necessárias só para reduzir recomposição.

## ACEITAÇÃO
- [ ] Estados e fluxos reais estão cobertos.
- [ ] Não há regressão em biblioteca/player.
- [ ] Não há operação pesada na main thread.
- [ ] Compilação validada.
- [ ] Testes relevantes executados.
- [ ] Mudanças obsoletas foram removidas somente com evidência.

## VALIDAÇÃO
Testar em Android real/emulador quando disponível. Se CI/emulador falhar por infraestrutura, registrar logs e diagnóstico. Não declarar sucesso sem execução.

## RELATÓRIO
Informar diff completo, arquivos adicionados/modificados/removidos, componentes preservados, testes e limitações.