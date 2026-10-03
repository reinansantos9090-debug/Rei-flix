# 23 — NEXT PREVIOUS AUTOPLAY

## CONTRATO
ReiAnix continua sendo biblioteca/reprodutor LOCAL. Leia o código real. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download, catálogo remoto, banco paralelo ou dados fictícios. Não duplicar regras no Compose. Use IDs estáveis. Considere lifecycle, cancelamento e estado obsoleto. Preserve correções anteriores.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Auditar e estabilizar Next, Previous e Autoplay.

## IMPLEMENTAÇÃO
Usar sequência canônica de episódios. Definir limites de temporada. Cancelar comandos antigos e impedir duplo clique concorrente. Persistir progresso antes da troca quando necessário. Impedir episódio incorreto por race condition. Preservar autoplay. Atualizar Details/Home após transição válida. Testar troca rápida, back, recreation e arquivo ausente. Instrumentar apenas o necessário.

## NÃO FAZER
Não resolver latência com timeouts arbitrários. Não aceitar callbacks stale. Não mudar ordem canônica para mascarar bug.

## CRITÉRIOS DE ACEITAÇÃO
- [ ] Integração usa dados reais.
- [ ] Estado persiste.
- [ ] IDs estáveis.
- [ ] Lifecycle e cancelamento corretos.
- [ ] Nenhuma funcionalidade local removida.
- [ ] Compilação validada.
- [ ] Testes relevantes executados e registrados.

## RELATÓRIO FINAL
Descrever diff de arquivos/pastas, componentes reutilizados, funcionalidades preservadas, testes, resultado da compilação e limitações de ambiente.