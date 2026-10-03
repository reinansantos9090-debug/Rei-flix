# 30 — TESTES E CI

## CONTRATO FINAL
ReiAnix continua sendo uma biblioteca/reprodutor LOCAL. Leia o código real. Preserve SQLite, scanner, SAF, MediaStore, permissões, artwork/cache, progresso e Media3. Não criar streaming, download de anime, catálogo remoto, banco paralelo ou dados fictícios. Preserve o bugfix do episódio desaparecendo. Use IDs estáveis. Considere lifecycle, concorrência e cancelamento.

## PROCESSO
Inspecione → implemente → integre → teste → compile → relate.

## OBJETIVO
Adequar a suíte e o GitHub Actions à nova arquitetura Compose.

## IMPLEMENTAÇÃO OBRIGATÓRIA
Criar/corrigir testes unitários de modelos/repositories/ViewModels, testes Compose de navegação e estados, testes instrumentados de biblioteca/player e regressão do episódio desaparecido. Atualizar workflow para compilar APK e executar testes. Preservar isolamento dos testes Android e staging de dependências existente. Quando emulator falhar, coletar diagnóstico como adb status, logcat e saída do Gradle antes do job terminar. Não esconder falhas com continue-on-error indiscriminado.

## NÃO FAZER
Não criar testes que só verificam que uma tela renderiza sem comportamento. Não mascarar falhas de infraestrutura como PASS. Não remover instrumentação só porque o emulador está instável.

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