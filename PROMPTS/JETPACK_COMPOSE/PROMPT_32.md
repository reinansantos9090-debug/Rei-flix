# 32 — CERTIFICAÇÃO FINAL DO NOVO REIANIX

## CONTRATO FINAL
ReiAnix continua sendo uma biblioteca/reprodutor LOCAL. Leia o código real. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download de anime, catálogo remoto, banco paralelo ou dados fictícios. Preserve o bugfix do episódio desaparecendo. Use IDs estáveis. Considere lifecycle, concorrência e cancelamento.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Executar a certificação final da migração Kotlin + Compose e corrigir diretamente os problemas encontrados.

## IMPLEMENTAÇÃO OBRIGATÓRIA
Validar compilação do APK, instalação, abertura, Home, Biblioteca, Busca, Details, Ajustes, seleção de pasta, permissões persistentes, scanner, importação, SQLite, artwork, reprodução local, progresso, Next/Previous, autoplay, back navigation, barras do sistema, lifecycle/recreation, memória e ausência do bug de episódio desaparecendo. Executar testes unitários, Compose e instrumentados disponíveis. Verificar que a UI é nativa em Compose, visualmente alinhada aos screenshots e que o app continua 100% local. Corrigir problemas reais encontrados antes de encerrar. Se algo depender de infraestrutura indisponível, registrar evidência e não declarar PASS falso.

## NÃO FAZER
Não adicionar novas funcionalidades durante a certificação. Não introduzir AniList, streaming, download ou novos recursos de player. Não apagar recursos importantes. Não encerrar apenas com uma lista de recomendações.

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