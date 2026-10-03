# 13 — DETAILS AÇÕES E PROGRESSO


## CONTEXTO OBRIGATÓRIO

Você está trabalhando diretamente no repositório **ReiAnix**. Esta é uma migração arquitetural da interface para **Kotlin + Jetpack Compose**, preservando o aplicativo como **biblioteca e reprodutor LOCAL** de vídeos/animes já armazenados no aparelho.

Leia a implementação real antes de alterar arquivos e adapte os nomes/locais à estrutura encontrada. Não presuma que uma classe ou arquivo exista com o nome deste documento.

### Regras obrigatórias
- NÃO apagar ou substituir desnecessariamente SQLite, library store/service, scanner, SAF, MediaStore, permissões, artwork/cache, progresso ou Media3.
- NÃO criar streaming, download de anime ou catálogo remoto.
- NÃO inventar dados para preencher telas.
- NÃO criar um segundo banco concorrente.
- NÃO duplicar regras de negócio em Composables.
- Preservar a correção histórica do episódio que desaparecia visualmente após sair do player.
- Reutilizar serviços existentes quando funcionais.
- Não fazer refatorações não relacionadas.
- Não criar abas artificiais.
- A biblioteca deve continuar utilizável offline.
- Usar IDs estáveis, nunca posição de lista como identidade.
- Considerar lifecycle, cancelamento e estados obsoletos.
- Não esconder problemas de dados apenas com lógica visual.

### Processo
1. Inspecione a implementação real.
2. Faça a alteração mínima e segura.
3. Integre com o que já existe.
4. Atualize testes.
5. Compile e execute validações.
6. Relate claramente falhas de código versus falhas de infraestrutura.

### Relatório
Ao terminar, informe arquivos adicionados/modificados/removidos, estruturas reutilizadas, funcionalidades preservadas, testes e limitações.

## OBJETIVO DESTA ETAPA
Conectar as ações de Details ao progresso e ao player real.

## IMPLEMENTAÇÃO OBRIGATÓRIA
- Implementar Assistir/Continuar usando o episódio correto.
- Favoritar/Minha Lista deve persistir.
- Marcar visto deve respeitar a semântica existente.
- Determinar o episódio de continuidade usando a mesma regra canônica do app.
- Após sair do player, Details deve refletir progresso sem depender de reinício.
- Se o usuário abrir outro episódio, a seleção deve ser explícita.
- Tratar episódio removido/inacessível sem quebrar a tela.
- Garantir que atualização de progresso não remova ou reordene itens indevidamente.

## O QUE NÃO FAZER
Não alterar a regra de identidade dos episódios sem testes. Não usar estado local de Composable como fonte de verdade para progresso. Não marcar toda a temporada como vista sem uma regra existente que determine isso.

## CRITÉRIOS DE ACEITAÇÃO
- [ ] A funcionalidade usa dados reais do ReiAnix.
- [ ] IDs e estados são estáveis.
- [ ] A UI não contém regras de negócio duplicadas.
- [ ] Loading, vazio e erro são tratados quando aplicável.
- [ ] Alterações persistem pela camada existente.
- [ ] Nenhuma funcionalidade local existente foi removida.
- [ ] O código compila.
- [ ] Testes relevantes foram executados e registrados.

## TESTES E VALIDAÇÃO
Execute testes unitários, Compose e/ou instrumentados adequados à etapa. Valide também manualmente, quando possível, o fluxo Android real afetado. Não marque como PASS algo que não foi executado. Se o CI/emulador falhar por infraestrutura, preserve o diagnóstico e diferencie isso de falha do código.

## RELATÓRIO FINAL
Informe o diff completo, arquivos adicionados/modificados/removidos, componentes existentes reutilizados, testes executados, resultado de compilação, limitações e qualquer ponto que precise ser tratado no prompt seguinte.