# 15 — ARTWORK E THUMBNAILS COMPOSE


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
Integrar o ArtworkEngine/cache existente com Compose sem duplicar sistemas.

## IMPLEMENTAÇÃO OBRIGATÓRIA
- Auditar o mecanismo de artwork existente, seus limites de tamanho, concorrência e cache.
- Reutilizar cache de disco/memória já existente quando possível.
- Se Coil for usado, configurá-lo como camada de carregamento e não como motivo para criar um segundo cache de disco sem necessidade.
- Criar placeholders e estado de erro.
- Dimensionar imagens para o espaço real.
- Usar keys estáveis em listas.
- Cancelar carregamentos quando itens saem de composição/scroll.
- Preservar os limites anteriores de workers/pending tasks e tamanhos reduzidos.
- Evitar flicker quando o item é recomposto.

## O QUE NÃO FAZER
Não aumentar arbitrariamente resolução/concurrency. Não carregar posters enormes para thumbnails. Não remover ArtworkEngine apenas porque Compose tem biblioteca de imagem.

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