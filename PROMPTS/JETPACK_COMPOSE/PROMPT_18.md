# 18 — AJUSTES PRINCIPAL

## CONTRATO DA ETAPA
ReiAnix é uma biblioteca/reprodutor LOCAL de vídeos já armazenados no aparelho. Leia o código real antes de alterar. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download de anime, catálogo remoto, banco paralelo ou dados fictícios. Não duplicar regras de negócio em Composables. Use IDs estáveis e considere lifecycle, cancelamento e estado obsoleto. Preserve a correção do episódio que desaparecia. Reutilize código existente e evite refatorações não relacionadas.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate. Não finalize apenas com recomendações.

## OBJETIVO
Reconstruir a tela principal de Ajustes em Compose preservando preferências reais.

## IMPLEMENTAÇÃO OBRIGATÓRIA
Criar cabeçalho e card de conta somente se houver integração real. Organizar Aparência, Geral, Player, Armazenamento, Segurança e Sobre somente quando existirem. Usar cards escuros, ícones, títulos, descrições e setas. Cada item deve navegar para tela real ou executar ação real. Mapear preferências para ViewModel/StateFlow e preservar valores/defaults.

## O QUE NÃO FAZER
Não criar opções fictícias. Não remover configurações existentes. Não guardar preferências críticas apenas em remember.

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