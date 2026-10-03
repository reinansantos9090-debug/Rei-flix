# 27 — BARRAS DO SISTEMA E EDGE TO EDGE

## CONTRATO
ReiAnix é uma biblioteca/reprodutor LOCAL. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming/download remoto, banco paralelo ou dados fictícios. Leia o código real antes de alterar. Preserve o bugfix dos episódios desaparecendo. Use IDs estáveis e considere lifecycle/cancelamento.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Ajustar status bar, navigation bar e edge-to-edge para os diferentes aparelhos.

## IMPLEMENTAÇÃO
Configurar WindowInsets/edge-to-edge conforme Material 3 e API alvo. Garantir que conteúdo não fique escondido atrás das barras. Ajustar bottom navigation, player, dialogs, campos de busca e telas roláveis. Validar gesture navigation, navigation buttons, recortes e densidades. Manter aparência próxima aos screenshots.

## NÃO FAZER
Não aplicar padding fixo baseado em um único aparelho. Não quebrar o player ou SAF com configuração global de janela.

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