# 28 — REMOÇÃO GRADUAL DA UI FLET

## CONTRATO
ReiAnix é uma biblioteca/reprodutor LOCAL. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming/download remoto, banco paralelo ou dados fictícios. Leia o código real antes de alterar. Preserve o bugfix dos episódios desaparecendo. Use IDs estáveis e considere lifecycle/cancelamento.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Remover somente a UI Flet que comprovadamente foi substituída por Compose.

## IMPLEMENTAÇÃO
Mapear imports, entrypoints, views, callbacks e bridges. Classificar Python/Flet em: ainda necessário para serviços; usado apenas por UI; morto; bridge necessária. Remover apenas código comprovadamente obsoleto. Garantir que build Android não dependa de Flet apenas para desenhar telas já migradas. Manter serviços Python se ainda forem fonte de dados ou compatibilidade. Atualizar testes e workflows afetados.

## NÃO FAZER
Não apagar Python indiscriminadamente. Não remover bridge só porque parece antiga. Não fazer limpeza estética sem comprovar consumidores.

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