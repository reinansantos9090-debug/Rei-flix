# 21 — AJUSTES CONTA GOOGLE

## CONTRATO
ReiAnix continua sendo biblioteca/reprodutor LOCAL. Leia o código real. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download, catálogo remoto, banco paralelo ou dados fictícios. Não duplicar regras no Compose. Use IDs estáveis. Considere lifecycle, cancelamento e estado obsoleto. Preserve correções anteriores.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Migrar a tela de conta Google somente se a integração existente for real.

## IMPLEMENTAÇÃO
Auditar autenticação atual. Exibir estado da conta sem vazar tokens. Integrar sincronização de progresso existente, troca de conta e saída somente por APIs reais. Mostrar erros e modo offline. A biblioteca local deve funcionar sem login. Preservar lifecycle e credenciais do SDK atual. Não bloquear scanner/player quando desconectado.

## NÃO FAZER
Não inventar autenticação. Não armazenar credenciais em texto. Não transformar Google em dependência da biblioteca local.

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