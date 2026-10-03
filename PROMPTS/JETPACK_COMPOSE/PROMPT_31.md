# 31 — AUDITORIA VISUAL FINAL

## CONTRATO FINAL
ReiAnix continua sendo uma biblioteca/reprodutor LOCAL. Leia o código real. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download de anime, catálogo remoto, banco paralelo ou dados fictícios. Preserve o bugfix do episódio desaparecendo. Use IDs estáveis. Considere lifecycle, concorrência e cancelamento.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Comparar a UI implementada com os screenshots de referência e corrigir diferenças relevantes sem inventar funcionalidades.

## IMPLEMENTAÇÃO OBRIGATÓRIA
Auditar Home, Biblioteca, Details, Busca, Ajustes, conta quando real, listas e player integrado. Verificar cores, tipografia, espaçamento, raio, ícones, chips, botões, hero, grids, listas, bottom navigation, estados ativos e barras do sistema. Verificar diferentes tamanhos de tela. Usar componentes do Design System criado no Prompt 02. Corrigir inconsistências sistêmicas em vez de aplicar hacks tela a tela.

## NÃO FAZER
Não adicionar conteúdo fictício para preencher espaço. Não adicionar aba/feature ausente no produto. Não sacrificar acessibilidade, legibilidade ou comportamento real só para copiar pixels.

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