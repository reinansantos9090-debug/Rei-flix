# 20 — AJUSTES PLAYER

## CONTRATO DA ETAPA
ReiAnix é uma biblioteca/reprodutor LOCAL de vídeos já armazenados no aparelho. Leia o código real antes de alterar. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download de anime, catálogo remoto, banco paralelo ou dados fictícios. Não duplicar regras de negócio em Composables. Use IDs estáveis e considere lifecycle, cancelamento e estado obsoleto. Preserve a correção do episódio que desaparecia. Reutilize código existente e evite refatorações não relacionadas.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate. Não finalize apenas com recomendações.

## OBJETIVO
Migrar preferências reais do player para Compose e garantir consumo pelo Media3.

## IMPLEMENTAÇÃO OBRIGATÓRIA
Auditar preferências existentes. Expor apenas opções implementadas, como autoplay, controles e legendas. Persistir na fonte atual. Garantir que NativePlayerActivity/Media3 leia valores corretos. Testar alteração antes de abrir e entre reproduções. Se uma opção não puder ser consumida ainda, não criar falso controle.

## O QUE NÃO FAZER
Não reconstruir o player. Não criar configuração paralela. Não alterar defaults sem justificativa e teste.

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