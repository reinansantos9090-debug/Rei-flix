# 25 — ESTADOS DE LOADING E ERRO

## CONTRATO
ReiAnix é uma biblioteca/reprodutor LOCAL. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming/download remoto, banco paralelo ou dados fictícios. Leia o código real antes de alterar. Preserve o bugfix dos episódios desaparecendo. Use IDs estáveis e considere lifecycle/cancelamento.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Padronizar loading, vazio, erro e indisponibilidade em toda a UI.

## IMPLEMENTAÇÃO
Criar componentes reutilizáveis para loading, biblioteca vazia, scanner em andamento, fonte sem permissão, arquivo removido, artwork ausente e erro recuperável. Cada estado deve permitir ação quando houver recuperação real, como tentar novamente ou escolher fonte. Mensagens devem ser claras e em português quando idioma configurado for português. Diferenciar ausência de conteúdo de erro. Evitar tela preta sem explicação.

## NÃO FAZER
Não engolir exceções silenciosamente. Não criar botões de retry que não executam nada. Não tratar falta de internet como erro quando a tela é puramente local.

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