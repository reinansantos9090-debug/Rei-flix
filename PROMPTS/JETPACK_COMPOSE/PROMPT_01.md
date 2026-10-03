# 01 — FUNDAÇÃO KOTLIN E JETPACK COMPOSE

## CONTEXTO OBRIGATÓRIO

Você está trabalhando diretamente no repositório **ReiAnix**. Esta é uma migração arquitetural grande da interface existente para **Kotlin + Jetpack Compose**, mas o aplicativo continua sendo, estritamente, uma **biblioteca e reprodutor LOCAL** de vídeos/animes que o usuário já possui no aparelho.

Antes de alterar arquivos, leia a implementação real do repositório e adapte a solução ao que já existe. Não presuma que um arquivo, classe, módulo ou API exista com o nome usado neste documento. Se a estrutura real tiver outro nome, reutilize a estrutura equivalente.

### Regras que valem para todo este prompt
- NÃO apagar ou substituir desnecessariamente SQLite, biblioteca, scanner, SAF, MediaStore, permissões, artwork/cache, progresso ou Media3.
- NÃO criar streaming, catálogo remoto, download de anime ou qualquer funcionalidade que transforme o app em serviço de streaming.
- NÃO inventar dados para preencher a interface.
- NÃO criar um segundo banco para substituir a fonte de verdade existente.
- NÃO duplicar regras de negócio dentro de Composables.
- Preservar a correção do episódio que desaparecia visualmente após sair do player.
- Reutilizar código existente e evitar refatorações não relacionadas.
- Não remover arquivos antigos sem comprovar que ficaram sem consumidores.
- Não criar telas/abas artificiais.
- A UI deve funcionar offline para a biblioteca local.
- Toda alteração deve ser compatível com Android real.
- Considerar lifecycle, Flow, coroutines, callbacks, concorrência e cancelamento.
- IDs de anime, temporada e episódio devem permanecer estáveis; nunca usar índice como identidade.

### Forma de trabalho
1. Inspecione a arquitetura atual.
2. Identifique o ponto mínimo e seguro de integração.
3. Implemente diretamente as alterações.
4. Reaproveite serviços existentes.
5. Atualize testes/documentação quando necessário.
6. Compile e execute os testes relevantes.
7. Se um teste não puder ser executado por limitação de ambiente, registre exatamente a limitação.

### Relatório obrigatório
Informe arquivos adicionados, modificados e removidos; estruturas existentes reutilizadas; funcionalidades preservadas; testes e resultados; falhas de infraestrutura; riscos e pendências.

## OBJETIVO DESTA ETAPA
Estabelecer a fundação Android nativa para a futura UI Compose sem ainda migrar visualmente as telas.

## IMPLEMENTAÇÃO OBRIGATÓRIA
- Auditar Gradle, módulo(s) Android, source sets, Manifest, Activities e integração atual com Flet/Flutter.
- Determinar onde Compose deve entrar sem quebrar a aplicação atual.
- Configurar Kotlin/Compose/Material 3/Navigation Compose em versões compatíveis com o projeto.
- Criar/adaptar a entrada nativa conforme a arquitetura real.
- Criar estrutura inicial clara para ui, navigation, data/domain quando necessário, viewmodel e integração.
- Preparar StateFlow/Coroutines sem criar camada de dados duplicada.
- Manter NativePlayerActivity/Media3 e serviços existentes funcionando.
- Documentar a fronteira entre UI nativa e serviços Python/Flet que ainda forem necessários.

## O QUE NÃO FAZER
Não migrar Home, Biblioteca, Details, Busca ou Ajustes completos neste prompt. O resultado deve ser compilável e reversível.

## CRITÉRIOS DE ACEITAÇÃO
[ ] Android compila; [ ] dependências Compose resolvem; [ ] entrada continua funcionando; [ ] Media3 permanece; [ ] SQLite/scanner/SAF permanecem; [ ] não há banco paralelo; [ ] nenhuma função remota foi criada.

## VALIDAÇÃO
Executar build e testes unitários/Android/Compose relevantes. Diferenciar falha de código de falha de infraestrutura.

## ENCERRAMENTO
Não avançar para responsabilidades dos próximos prompts. Deixar a árvore consistente e relatar exatamente o que foi implementado.