# 24 — DETAILS E EPISÓDIOS SEM DESAPARECIMENTO

## CONTRATO
ReiAnix continua sendo biblioteca/reprodutor LOCAL. Leia o código real. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download, catálogo remoto, banco paralelo ou dados fictícios. Não duplicar regras no Compose. Use IDs estáveis. Considere lifecycle, cancelamento e estado obsoleto. Preserve correções anteriores.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Fazer regressão dedicada ao bug histórico de episódio que desaparecia visualmente.

## IMPLEMENTAÇÃO
Reproduzir: dez ou mais episódios → Details → EP07 → cerca de 18% → sair → Details. Confirmar EP06, EP07 e EP08 presentes, ordem correta, Continue apontando para EP07 e progresso persistente. Reabrir Details repetidamente. Garantir identidade estável, lista derivada de fonte estável e nenhuma reconstrução imperativa insegura. Criar testes unitários/ViewModel/Compose/instrumentados conforme possível.

## NÃO FAZER
Não esconder episódio, trocar o atual por outro ou congelar a lista. Não colocar side effects de atualização dentro do caminho de composição.

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