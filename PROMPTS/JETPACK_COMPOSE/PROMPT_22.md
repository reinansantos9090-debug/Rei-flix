# 22 — PLAYER MEDIA3 E COMPOSE

## CONTRATO
ReiAnix continua sendo biblioteca/reprodutor LOCAL. Leia o código real. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download, catálogo remoto, banco paralelo ou dados fictícios. Não duplicar regras no Compose. Use IDs estáveis. Considere lifecycle, cancelamento e estado obsoleto. Preserve correções anteriores.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Integrar navegação Compose ao player Media3 existente sem reescrevê-lo.

## IMPLEMENTAÇÃO
Passar ID/URI/episódio de forma estável para NativePlayerActivity. Garantir arquivo correto, resume, progresso, pause/exit/completed, next/previous/autoplay e retorno a Details/Home. Tratar URI inválida/arquivo removido. Cancelar callbacks ao destruir Activity. Evitar abertura duplicada por cliques rápidos. Testar background/foreground e back.

## NÃO FAZER
Não substituir Media3 por player experimental. Não mover toda lógica para Composable. Não remover NativePlayerActivity enquanto necessária.

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