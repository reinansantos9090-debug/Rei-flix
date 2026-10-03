# 29 — LIMPEZA DA ARQUITETURA ANDROID

## CONTRATO FINAL
ReiAnix continua sendo uma biblioteca/reprodutor LOCAL. Leia o código real. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download de anime, catálogo remoto, banco paralelo ou dados fictícios. Preserve o bugfix do episódio desaparecendo. Use IDs estáveis. Considere lifecycle, concorrência e cancelamento.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Organizar o módulo Android após a migração, sem criar abstrações excessivas.

## IMPLEMENTAÇÃO OBRIGATÓRIA
Separar de forma clara ui, navigation, viewmodel, data/domain quando necessário, player, storage, bridge e scanner. Reunir componentes duplicados. Garantir que NativePlayerActivity e serviços nativos tenham responsabilidades claras. Remover adapters temporários somente quando não houver consumidores. Atualizar documentação da arquitetura e dependências Gradle. Verificar imports, ciclos de dependência e source sets.

## NÃO FAZER
Não fazer uma reescrita arquitetural completa por preferência. Não mover arquivos sem necessidade. Não remover infraestrutura existente apenas para obter uma árvore de pastas bonita.

## CRITÉRIOS DE ACEITAÇÃO
- [ ] Código Android/Compose compila.
- [ ] Dados locais continuam preservados.
- [ ] Scanner/SAF/MediaStore continuam funcionais.
- [ ] Media3 e progresso continuam funcionais.
- [ ] Navegação e back funcionam.
- [ ] Episódios mantêm identidade e não desaparecem.
- [ ] Testes relevantes foram executados.
- [ ] Falhas de infraestrutura foram separadas de falhas de código.
- [ ] Não foram introduzidas funcionalidades fora do escopo.

## RELATÓRIO FINAL OBRIGATÓRIO
Apresente o diff completo: arquivos e pastas adicionados, modificados e removidos; o que já existia e foi reutilizado; funcionalidades preservadas; testes executados com resultado; comandos de build; limitações restantes e qualquer item que não pôde ser validado.