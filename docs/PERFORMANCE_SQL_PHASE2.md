# Rei-Flix — Performance SQL Phase 2 Audit

## Escopo

Esta fase auditou o acesso ao SQLite usado por catálogo, Home, Organize, Search/filtros/ordenação, consumo/histórico, Details e backup/restore.

A fonte de verdade continua sendo o LibraryStore/SQLite existente. Não foi criado segundo banco, não houve migração geral de schema, e SCHEMA_VERSION permanece 29.

O ambiente desta execução não possui clone local funcional nem runtime Android. Portanto, tempos de execução do aplicativo, planos contra uma biblioteca real e testes locais permanecem NOT MEASURED / NOT VALIDATED.

## Mapa das consultas críticas

| Área | Arquivo / função | Uso | Frequência derivável do código | Linhas potencialmente afetadas |
| --- | --- | --- | --- | --- |
| Catálogo paginado | core/library_store.py::catalog_page | Home e Organize, busca, filtros e ordenação | 1 chamada por carregamento/recarregamento de página; pode repetir a cada filtro/ordenação | LIMITA a projeção a page_size; COUNT percorre o conjunto filtrado quando solicitado |
| Projeção de catálogo | core/library_store.py::catalog | Home/Details/compatibilidade e projeções por IDs | 1 chamada por materialização de catálogo/projeção | Retorna as linhas das entidades selecionadas |
| Home agregada | core/library_store.py::home_sections | Seções secundárias da Home | 1 chamada por atualização das seções | Cada seção permanece limitada por limit; projeção compartilhada evita repetir entidades |
| Resumo Organize | core/library_store.py::organize_summary | Contadores e gêneros do Organize | 1 chamada por atualização do overview | Agrega episódios por anime_id; resultado final é pequeno |
| Continue Watching | core/library_store.py::continue_watching | Home | 1 consulta por atualização da seção | LIMIT explícito |
| Próximo episódio | core/library_store.py::next_episode_items | Home | 1 consulta por atualização da seção | LIMIT explícito |
| Histórico | core/library_store.py::playback_history | Home/consumo | 1 consulta por atualização da seção | LIMIT explícito |
| Opções de busca | core/library_store.py::search_options | Filtros Home/Organize | Carregamento secundário | DISTINCTs de temporada/tipo/origem + tags persistidas |
| Search SQL | core/library_store.py::catalog_page | Busca local paginada atual | 1 página por busca/filtro | LIKE com wildcard inicial e normalização de texto |
| Search Python | core/search_engine.py::LibrarySearchEngine | Compatibilidade sobre catálogo já projetado | Depende do chamador | Trabalha somente sobre dados já materializados |
| Progresso/consumo | core/library_store.py::save_progress | Eventos do player | Um write por evento persistido | 1 linha de episodes por caminho |
| Backup | core/library_store.py | Backup/restore | Operação excepcional | Banco inteiro / snapshot |

As frequências acima são derivadas do fluxo do código, não de telemetria. Onde não há contador persistente, a frequência real em uso é NÃO MEDIDO.

## EXPLAIN QUERY PLAN

### Ordenação padrão

O schema já possui idx_anime_added_title, idx_anime_favorite_added, idx_episodes_resume, idx_episodes_season_number e idx_episodes_hierarchy.

O repositório contém um teste executável de EXPLAIN QUERY PLAN para a ordenação por added_at/title/id e verifica que o plano usa idx_anime_added_title em um banco de teste criado pela suíte. Esse é um contrato de plano em fixture, não uma medição do dispositivo do usuário.

Nenhum novo índice foi criado para a ordenação padrão.

### Ordenações por agregação

As opções Assistidos recentemente, Progresso, Episódio, Temporada + episódio, Modificação, Duração e Tamanho continuam baseadas em subconsultas correlacionadas sobre episodes.

Essas expressões podem exigir reavaliação por anime e ordenação em estrutura temporária dependendo do plano e do volume. Não foi criado índice experimental porque não existe benchmark do Rei-Flix real que demonstre que um índice novo compensa custo de escrita/manutenção.

### Search

A busca SQL normaliza texto com reiflix_normalize e usa LIKE com token entre wildcards em múltiplas colunas de anime e episodes. B-trees comuns não resolvem diretamente esse padrão.

O volume real e a latência real de Search não foram medidos neste ambiente. FTS5 foi avaliado e não implementado.

## Otimizações implementadas

### 1. Histórico redundante em catalog()

Antes, catalog() carregava episodes e em seguida executava outra consulta agrupada por anime_id para obter MAX(last_played_at). A mesma coluna já estava presente nas linhas de episodes carregadas para a mesma projeção.

Agora o maior last_played_at por anime é calculado enquanto as linhas já carregadas são projetadas. A fonte de dados e a semântica não mudam.

### 2. Home: IDs limitados + uma projeção compartilhada

As seis seções recently_added, favorites, pinned, series, movies e specials continuam usando exatamente seus filtros e ordenação originais.

A etapa secundária agora pede somente IDs limitados e sem COUNT. Os IDs únicos são projetados uma única vez por catalog(anime_ids=...), e cada seção é reconstruída na ordem original.

### 3. Home: enriquecimento de gêneros em lote

A camada de serviço anteriormente chamava GenreRegistry.enrich_catalog separadamente para sete seções.

Agora os IDs das sete seções são unidos e o enriquecimento é feito uma vez. recently_watched permanece fora desse agrupamento porque contém linhas de episódio, não entidades de anime.

### 4. Organize: 8 COUNTs correlacionados -> 1 agregação

Os oito estados do overview agora são derivados de um único CTE que agrega episodes por anime_id, seguido por uma agregação final.

Os critérios de Todos, Favoritos, Fixados, Assistidos, Não assistidos, Em andamento, Concluídos e Não iniciados foram preservados, inclusive a regra de Concluídos com itens disponíveis.

## Índices

Índices adicionados: nenhum.

Índices removidos: nenhum.

Motivo: o schema já possui cobertura relevante para as ordenações e relações do catálogo. Sem plano + benchmark do Rei-Flix real, criar novos índices seria especulativo.

## anime_stats / projeção agregada

Não implementado.

A ideia foi avaliada, mas exige medir frequência de leitura, frequência de escrita em episodes, custo de manutenção durante scanner/importação/restore/consumo e risco de divergência. As otimizações atuais eliminam repetições óbvias sem introduzir nova fonte persistida.

## Transações

A auditoria identificou uma oportunidade potencial no scanner/importação: operações lógicas de um item passam por chamadas separadas de LibraryStore, cada uma com sua própria conexão/transação.

Não foi criado um mega-transaction wrapper nesta fase porque isso exigiria refatoração do ciclo interno de conexões e validação específica de concorrência/rollback.

Classificação: PARTIAL / futura oportunidade.

## Conexões SQLite

LibraryStore._conn() abre uma conexão nova por operação e aplica foreign_keys=ON, row_factory e reiflix_normalize determinística.

Os usos observados estão protegidos por context managers, portanto não há conexão intencionalmente aberta entre chamadas. Não foi introduzido pooling.

O custo de abrir/fechar conexões no Android permanece NOT MEASURED.

## WAL

WAL foi explicitamente avaliado e não habilitado.

O projeto possui snapshots físicos do SQLite, ATTACH DATABASE no restore, BEGIN IMMEDIATE, cópia/restauração do arquivo, integrity_check, foreign_key_check e tratamento explícito de eventuais sidecars -wal e -shm no recovery.

Sem validação específica de todo esse ciclo no Android, habilitar WAL seria uma mudança de política de armazenamento. Portanto esta fase somente documenta a possibilidade futura.

## Backup / restore / migração

Nenhuma tabela nova e nenhum índice novo foram adicionados. SCHEMA_VERSION continua em 29.

Os fluxos de backup, restore, ATTACH, recovery e migração aditiva não foram alterados por esta fase.

Os testes existentes de backup/restore e migração permanecem como regressão principal; execução real da suíte ainda depende de CI.

## Paginação

A paginação existente com LIMIT/OFFSET continua usada por Home e Organize.

A API padrão de catalog_page() continua retornando items, total, page, page_size e has_more.

Foi adicionado um modo interno include_total=False, project_items=False para seções secundárias da Home que não precisam do total nem de projeção completa.

Não houve mudança de scroll, seleção ou desenho das telas.

## Search / FTS5

A busca local atual permanece baseada no SQL existente e em LibrarySearchEngine para compatibilidade.

FTS5 não foi criado porque não há medição real do tempo de Search, nem tamanho real da biblioteca, e a sincronização de um índice adicional exigiria nova cobertura de backup/restore.

Recomendação nesta fase: manter FTS5 como oportunidade futura e só implementar após benchmark real.

## Redução estrutural da Home

Na implementação auditada antes desta fase, uma execução cheia de Home fazia, por contagem estática do código, até 58 comandos de leitura: seis seções secundárias com COUNT + IDs + projeção de catálogo + consulta de histórico, três projeções independentes de consumo/histórico e sete enriquecimentos de gênero separados.

Após esta fase, a mesma composição estrutural fica em 15 comandos de leitura no caminho sem catálogo pré-carregado: seis consultas de IDs, uma projeção compartilhada de catálogo, três consultas de consumo/histórico e um enriquecimento de gênero em lote.

Esses 58 e 15 são contagens estruturais derivadas do código, não tempos ou contadores de produção. Os testes com set_trace_callback foram adicionados para validar a contagem no SQLite de teste quando a suíte for executada.

## Métricas e regressões adicionadas

Foram adicionados testes que usam sqlite3.set_trace_callback() em um store de teste para contar comandos SQL:

- catalog() não deve executar a antiga consulta agrupada de histórico;
- catalog_page() no modo interno de IDs deve usar uma única consulta de leitura;
- home_sections() deve compartilhar uma única projeção do catálogo;
- organize_summary() deve usar no máximo duas consultas de leitura principais;
- media_center_home() deve fazer enriquecimento de gêneros em lote.

Esses testes medem quantidade de comandos, não latência do dispositivo.

Latência real, CPU, I/O e energia: NOT MEASURED nesta execução.

## Resultado

A fase remove trabalho SQL repetido de forma conservadora sem alterar schema, fonte de verdade, consumo/progresso, backup/restore, Search ou paginação.

O trabalho restante para declarar ganho de performance comprovado é executar a suíte em CI e medir uma biblioteca real no Android, principalmente para ordenações agregadas, Search, custo de conexões, scanner/importação e backup/restore.