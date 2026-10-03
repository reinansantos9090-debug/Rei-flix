# 17 — ARMAZENAMENTO E PERMISSÕES

## CONTRATO DA ETAPA
ReiAnix é uma biblioteca/reprodutor LOCAL de vídeos já armazenados no aparelho. Leia o código real antes de alterar. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download de anime, catálogo remoto, banco paralelo ou dados fictícios. Não duplicar regras de negócio em Composables. Use IDs estáveis e considere lifecycle, cancelamento e estado obsoleto. Preserve a correção do episódio que desaparecia. Reutilize código existente e evite refatorações não relacionadas.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate. Não finalize apenas com recomendações.

## OBJETIVO
Levar os fluxos de armazenamento para a UI nativa sem quebrar permissões existentes.

## IMPLEMENTAÇÃO OBRIGATÓRIA
Mapear SAF, MediaStore, MANAGE_EXTERNAL_STORAGE e wrappers atuais. Mostrar fontes configuradas. Usar SAF quando apropriado e preservar flags persistentes de URI. Validar permissões ao reabrir o app. Disparar scanner pela camada de serviço. Mostrar estados de permissão, fonte indisponível e seleção. Preservar permissões amplas somente onde a arquitetura atual realmente exigir. Testar retorno do seletor após recreation.

## O QUE NÃO FAZER
Não substituir SAF por acesso direto indiscriminado. Não pedir permissões maiores por conveniência. Não apagar fontes configuradas por falha temporária.

## ACEITAÇÃO
- [ ] Usa fontes de verdade existentes.
- [ ] Persistência continua funcionando.
- [ ] Não há estado paralelo.
- [ ] UI não bloqueia a main thread.
- [ ] Navegação e lifecycle funcionam.
- [ ] Compilação foi executada.
- [ ] Testes relevantes foram executados ou a limitação foi registrada.

## RELATÓRIO
Informar arquivos adicionados, modificados e removidos; estruturas reutilizadas; funcionalidades preservadas; testes e resultado; limitações reais.