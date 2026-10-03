# 19 — AJUSTES APARÊNCIA E GERAL

## CONTRATO DA ETAPA
ReiAnix é uma biblioteca/reprodutor LOCAL de vídeos já armazenados no aparelho. Leia o código real antes de alterar. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download de anime, catálogo remoto, banco paralelo ou dados fictícios. Não duplicar regras de negócio em Composables. Use IDs estáveis e considere lifecycle, cancelamento e estado obsoleto. Preserve a correção do episódio que desaparecia. Reutilize código existente e evite refatorações não relacionadas.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate. Não finalize apenas com recomendações.

## OBJETIVO
Migrar Aparência e Geral conectando cada controle a uma configuração real.

## IMPLEMENTAÇÃO OBRIGATÓRIA
Auditar preferências atuais. Implementar tema, idioma, notificações e outras opções somente quando suportadas. Persistir pela fonte atual. Propagar mudanças via Flow/StateFlow. Aplicar tema sem reinício desnecessário. Tratar defaults e valores antigos.

## O QUE NÃO FAZER
Não criar toggles sem efeito. Não apagar preferências antigas. Não criar serviços só para preencher a tela.

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