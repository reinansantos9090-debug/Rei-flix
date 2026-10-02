# PROMPT 42 — CORREÇÃO DEFINITIVA: EPISÓDIO DESAPARECE APÓS FECHAR E REABRIR O REIANIX

## Repositório

https://github.com/reinansantos9090-debug/ReiAnix

## Contexto

O ReiAnix é um aplicativo Android pessoal para organizar e reproduzir vídeos locais, com:

- Flet/Python;
- Kotlin nativo;
- Media3/ExoPlayer;
- SQLite;
- bridge Python ↔ Android;
- Mailbox/eventos;
- scanners MediaStore/SAF/broad storage;
- catálogo de biblioteca;
- tela Home;
- tela Details;
- persistência de progresso e retomada.

Existe um bug recorrente observado em testes reais no APK:

1. O usuário abre um episódio.
2. O episódio começa a reproduzir.
3. O progresso é salvo.
4. O usuário fecha o aplicativo.
5. O usuário abre o ReiAnix novamente.
6. O anime continua existindo na biblioteca.
7. O episódio que estava sendo assistido aparece em alguma projeção de "Continuar", ou o sistema conhece seu progresso, porém ele desaparece da lista normal de episódios da tela de detalhes.
8. Em outros testes, o episódio pode parecer desaparecer completamente até que alguma atualização/reconciliação aconteça.
9. O comportamento esperado é que o episódio continue aparecendo normalmente na temporada/lista de episódios e mantenha seu progresso.
10. Ao tocar novamente nele, o player deve retornar aproximadamente à posição em que o usuário parou.

O problema NÃO deve ser tratado como simples falha visual, travamento do Android ou erro genérico de lifecycle.

A hipótese inicial de que existe simplesmente um filtro `progress == 0` escondendo episódios é insuficiente para o estado atual do código e NÃO deve ser aceita sem prova.

## Evidência observada

Nos testes em vídeo foi observado o seguinte padrão:

- um episódio em andamento aparece em "CONTINUAR";
- simultaneamente, a lista normal de episódios da temporada começa no episódio seguinte;
- depois que outro episódio é iniciado, o novo episódio passa a aparecer em "CONTINUAR" e também deixa de aparecer na lista normal;
- isso indica uma divergência entre as diferentes projeções da mesma biblioteca.

Exemplo conceitual:

    Episódios reais:
    EP01
    EP02
    EP03
    EP04
    EP05

    Depois de assistir parcialmente EP01:

    CONTINUAR:
    EP01 37%

    Lista da temporada:
    EP02
    EP03
    EP04
    EP05

O comportamento correto é:

    CONTINUAR:
    EP01 37%

    Lista da temporada:
    EP01 37%
    EP02
    EP03
    EP04
    EP05

Depois de fechar/reabrir o aplicativo, o mesmo estado deve continuar existindo.

## Objetivo

Descobrir a causa técnica exata e corrigir DEFINITIVAMENTE o ciclo:

    reproduzir episódio
        ↓
    atualizar posição/progresso
        ↓
    persistir progresso
        ↓
    fechar processo/aplicativo
        ↓
    iniciar novamente
        ↓
    scanner/reconciliação
        ↓
    SQLite
        ↓
    catálogo
        ↓
    Home / Continuar
        ↓
    Details
        ↓
    lista de episódios
        ↓
    tocar episódio
        ↓
    restaurar posição no Media3

A correção deve garantir simultaneamente:

1. Episódio com progresso continua pertencendo à lista normal de episódios.
2. "Continuar" é apenas uma projeção adicional, não uma lista que remove itens da temporada.
3. O progresso é persistido de forma durável.
4. O registro do episódio mantém identidade estável.
5. Scanner/reconciliação não transforma um episódio existente em `missing` por causa de uma varredura parcial/incompleta.
6. Fechar e reabrir o aplicativo não apaga nem oculta o episódio.
7. O player consegue recuperar a posição salva.
8. Eventos antigos não sobrescrevem o progresso mais novo.
9. O mesmo episódio não é duplicado ou substituído por outro registro durante rescan.
10. A correção não quebra Next, Previous, Autoplay, Details, Home ou a biblioteca.

---

# 1. REGRA FUNDAMENTAL

A lista de episódios da tela Details deve representar os episódios existentes na biblioteca.

O progresso NÃO pode ser usado para determinar se um episódio pertence ou não à lista.

A semântica correta é:

    existência/identidade do episódio
        -> determina se ele aparece na lista

    progresso/estado de consumo
        -> determina estado visual e posição em "Continuar"

Portanto:

- `progress == 0`: aparece;
- `progress > 0`: aparece;
- `progress > 0` e incompleto: aparece + pode aparecer em Continuar;
- `watched/completed`: continua aparecendo na lista;
- `progress == duration`: continua aparecendo;
- episódio pausado: continua aparecendo;
- episódio recém-iniciado: continua aparecendo;
- episódio concluído: continua aparecendo;
- somente um registro realmente ausente/removido da biblioteca pode deixar de ser um episódio disponível.

NÃO implementar uma correção que simplesmente elimine uma condição específica sem verificar toda a origem dos dados.

---

# 2. PRIMEIRO: REPRODUZIR O BUG

Antes de modificar a lógica principal, crie/reutilize um teste determinístico que simule:

1. biblioteca com pelo menos 5 episódios;
2. abrir EP01;
3. persistir progresso, por exemplo 37%;
4. fechar player;
5. reconstruir/reabrir catálogo;
6. obter Details do anime;
7. verificar que EP01 ainda está na lista da temporada;
8. verificar que EP01 aparece em Continuar;
9. abrir EP01 novamente;
10. verificar que o playback target contém o mesmo `episode_id`;
11. verificar que `progress` continua próximo de 37%;
12. verificar que o player recebe a posição de retomada.

Depois repetir para EP02, EP03 e outros episódios.

O teste deve reproduzir o padrão do vídeo:

    episódio atual aparece em Continuar
    MAS NÃO PODE desaparecer da lista de episódios.

---

# 3. MAPEAR O FLUXO COMPLETO

Faça uma auditoria ponta a ponta.

Mapear obrigatoriamente:

## Python

- `main.py`
- `core/library_store.py`
- `core/library_service.py`
- `core/consumption.py`
- `core/android_bridge.py`
- `core/scan_coordinator.py`
- `views/details_view.py`
- `views/home_view.py`
- qualquer serviço responsável por playback target;
- qualquer serviço responsável por "Continuar";
- qualquer camada que hidrata catálogo;
- qualquer função que reconcilia episódios;
- qualquer função que marca `missing`;
- qualquer função que atualiza progresso.

## Android

Auditar pelo menos:

- `NativePlayerActivity.kt`
- `MainActivity.kt`
- `NativePlayerRequest.kt`
- `NativeMailbox.kt`
- `NativeRequestState.kt`
- scanner(s);
- qualquer componente que publica progresso;
- qualquer componente que publica `player_exited`;
- lifecycle da Activity;
- `onPause`;
- `onStop`;
- `onDestroy`;
- `onNewIntent`;
- encerramento/reuso do player.

## Banco

Auditar:

- schema de `anime`;
- schema de `episodes`;
- chaves;
- IDs;
- path;
- identidade do arquivo;
- source_folder;
- progress;
- duration;
- watched;
- last_played_at;
- modified_at;
- missing;
- qualquer coluna de identidade;
- migrations;
- UPSERT;
- UPDATE;
- DELETE;
- reconciliação;
- transações;
- concorrência.

---

# 4. INVESTIGAR A LISTA DE EPISÓDIOS

No código atual, `views/details_view.py` utiliza a estrutura de temporadas/episódios recebida no `anime_group`.

Não assuma que essa estrutura está completa.

Descobrir exatamente:

1. Quem constrói `anime_group`.
2. Quem seleciona a temporada.
3. Quem cria `season_items`.
4. Quem cria `regular_episodes`.
5. Quem cria `available`.
6. Quem cria `current`.
7. Quem cria `primary_target`.
8. Se algum deles é uma lista filtrada.
9. Se `current` ou `primary_target` estão sendo retirados de `regular_episodes`.
10. Se algum `list.remove()`, `pop()`, compreensão de lista ou filtro por estado está eliminando o episódio atual.
11. Se existe qualquer filtro indireto baseado em:
    - progress;
    - watched;
    - completed;
    - in_progress;
    - current;
    - next;
    - missing;
    - available;
    - playback target.
12. Se a lista recebida pela Details já chega incompleta.
13. Se a tela Details está usando uma projeção antiga em cache.
14. Se o objeto do anime vindo da Home/Continuar é diferente do catálogo canônico.

A correção deve separar claramente:

    canonical episode collection

de:

    continuation projection

e:

    playback target

Essas três coisas NÃO podem compartilhar uma semântica que remova o episódio da coleção canônica.

---

# 5. FONTE CANÔNICA DOS EPISÓDIOS

Definir e preservar uma única fonte canônica para os episódios locais de um anime.

O contrato desejado é:

    catalog(anime_id)
        -> todas as temporadas
        -> todos os episódios existentes
        -> identidade
        -> estado de disponibilidade
        -> progresso

Depois:

    continuation(catalog)
        -> somente uma projeção dos episódios incompletos

E:

    playback_target(catalog)
        -> episódio recomendado para reprodução

Nenhuma dessas projeções pode mutar/remover itens do catálogo.

Se o projeto atual tiver múltiplas fontes, corrigir a origem, não criar outra fonte conflitante.

---

# 6. IDENTIDADE DO EPISÓDIO

Investigar profundamente se o problema é causado por troca de identidade.

O mesmo arquivo deve continuar representando o mesmo episódio após:

- playback;
- restart;
- scanner;
- MediaStore;
- SAF;
- broad storage;
- reconciliation;
- metadata refresh;
- atualização de catálogo.

Auditar:

- `episode_id`;
- path;
- URI;
- normalized path;
- file name;
- source folder;
- tamanho;
- modified_at;
- identidade derivada;
- canonical lookup;
- UPSERT;
- conflitos.

Criar teste:

    EP01 id=123
    progress=37

    restart/rescan

    EP01 id deve continuar sendo 123

ou, se a arquitetura permitir nova identidade técnica, deve existir uma reconciliação explícita que preserve o progresso sem duplicar/remover o episódio.

Nunca permitir:

    EP01 antigo -> deletado
    EP01 novo -> criado sem progresso

sem uma transferência explícita e segura de estado.

---

# 7. PERSISTÊNCIA DO PROGRESSO

Auditar o fluxo:

    Media3 position
       ↓
    NativePlayerActivity
       ↓
    evento progress
       ↓
    bridge
       ↓
    Python
       ↓
    SQLite

Verificar:

- frequência de checkpoints;
- último checkpoint;
- flush;
- commit;
- thread;
- asyncio;
- transação;
- concorrência;
- ordem dos eventos;
- shutdown;
- player_exited;
- player_paused;
- onStop;
- onPause;
- processo morto;
- Activity destruída;
- aplicativo removido dos recentes.

Não depender exclusivamente de `onDestroy()` para persistir o progresso.

O progresso deve ser persistido continuamente durante reprodução e reforçado nos eventos apropriados de pausa/saída, sem depender de um único callback final.

---

# 8. PROTEÇÃO CONTRA EVENTOS ANTIGOS

Investigar se existe uma condição como:

    progress novo = 37%
    evento antigo = 2%
    evento antigo chega depois
    SQLite volta para 2%

Isso pode explicar parte dos sintomas.

Todo update de progresso deve respeitar a identidade da sessão/episódio e, quando necessário, timestamp/monotonic sequence/generation.

Auditar:

- playerSessionId;
- requestId;
- episodeId;
- transitionGeneration;
- player generation;
- event timestamp;
- sequence;
- stale event detection.

Um evento de episódio A nunca pode alterar o progresso do episódio B.

Um evento antigo da sessão A nunca pode sobrescrever o estado mais novo da sessão B.

---

# 9. SCANNER E MISSING

Auditar profundamente:

- STARTUP;
- PERMISSION_CHANGE;
- MediaStore;
- SAF;
- broad storage;
- scan generation;
- scan version;
- reconciliation;
- observations;
- missing;
- cleanup;
- source scope.

Regra obrigatória:

Uma varredura incompleta, parcial, interrompida ou que ainda não terminou NÃO pode ser interpretada como prova de que um episódio foi removido.

Só marcar `missing=1` quando houver evidência válida conforme o contrato atual do scanner/reconciliation.

Antes de alterar `missing`, verificar:

- scan completo?
- source correto?
- geração válida?
- permission válida?
- target correto?
- arquivo realmente não observado?
- resultado terminal?
- erro parcial?
- scanner interrompido?

Criar testes para:

1. scan completo encontra EP01;
2. scan parcial não remove EP01;
3. scan vazio por erro não remove EP01;
4. permission temporariamente indisponível não remove EP01;
5. restart com scanner atrasado não remove EP01;
6. arquivo realmente removido pode ser reconciliado como missing conforme o contrato existente.

Não desabilitar reconciliation como solução.

---

# 10. HOME / CONTINUAR

Auditar `views/home_view.py` e toda a origem de `continuing`.

A regra deve ser:

    CONTINUAR = subset derivado do catálogo

e não:

    catálogo = episódios restantes depois de CONTINUAR

Verificar se a construção de `continuing`:

- muta listas;
- remove itens;
- usa referências compartilhadas;
- altera `seasons`;
- altera `episodes`;
- altera objetos retornados pelo catálogo.

Evitar bugs de referência mutável em Python.

Se necessário, usar projeções independentes/cópias controladas, mas sem criar uma segunda fonte de verdade.

---

# 11. DETAILS DEVE SER RECARREGADO CORRETAMENTE

Quando o usuário entra em Details por:

- Home;
- Biblioteca;
- Continuar;
- busca;
- filtro;
- retorno do player;

garantir que Details tenha acesso ao catálogo canônico atual.

Se o objeto passado pela tela anterior for apenas uma projeção, fazer lookup canônico por `anime_id`.

Não usar um objeto parcial de "Continuar" como se fosse o catálogo completo do anime.

Especialmente investigar o caminho:

    Home
      -> Continuar
      -> Detalhes

porque esse caminho é crítico para o bug observado.

---

# 12. RETOMADA NO PLAYER

Quando o usuário toca novamente no episódio:

1. identificar o mesmo episódio;
2. obter progresso persistido;
3. abrir o mesmo arquivo;
4. preparar Media3;
5. aplicar a posição salva;
6. iniciar reprodução.

Não usar apenas:

    current episode

sem verificar:

    episode_id
    path
    progress
    duration

Validar limites:

    0 <= progress <= duration

Se o progresso for inválido, normalizar sem apagar o episódio.

Não zerar progresso válido durante hidratação.

---

# 13. CASOS DE TESTE OBRIGATÓRIOS

Criar ou atualizar testes automatizados para todos os casos abaixo.

## Caso A — episódio novo

EP01 progress=0

Resultado:

- EP01 aparece na lista;
- não aparece em Continuar.

## Caso B — episódio iniciado

EP01 progress=1 segundo

Resultado:

- EP01 aparece na lista;
- aparece em Continuar;
- fica clicável.

## Caso C — episódio parcialmente assistido

EP01 progress=37%

Resultado:

- EP01 aparece na lista;
- aparece em Continuar;
- porcentagem correta;
- pode ser reaberto.

## Caso D — episódio quase concluído

EP01 progress=95%

Resultado:

- EP01 continua na lista;
- comportamento de Continuar segue o contrato de consumo existente;
- não desaparece.

## Caso E — episódio concluído

EP01 watched/completed

Resultado:

- EP01 continua na lista;
- estado visual de concluído;
- não desaparece.

## Caso F — restart

EP01 progress=37%

Simular:

    persist
    close process
    recreate application
    load catalog

Resultado:

    EP01 continua na lista
    progress=37%
    mesmo episode_id

## Caso G — restart com scan

Repetir o caso F enquanto um STARTUP scan/reconciliation acontece.

Resultado:

- EP01 não desaparece;
- não vira missing incorretamente;
- progresso permanece.

## Caso H — Home → Continuar → Details

Resultado:

- Details recebe catálogo completo;
- EP01 aparece na lista;
- EP01 continua em andamento.

## Caso I — Details → player → back

Resultado:

- episódio continua na lista;
- progresso atualizado.

## Caso J — eventos atrasados

Simular:

    progress 37%
    evento antigo 2%

Resultado:

    progress final não pode regredir indevidamente.

## Caso K — episódio A/B

Simular:

    A progress=37
    B progress=12

Resultado:

- A mantém 37;
- B mantém 12;
- nenhum evento cruza identidades.

## Caso L — scanner parcial

Simular scan sem resultado completo.

Resultado:

- episódio existente não é removido.

## Caso M — scanner realmente encontra remoção

Somente neste caso aplicar a regra existente de missing/remoção.

---

# 14. TESTE DE REGRESSÃO ESPECÍFICO DO BUG DO VÍDEO

Criar um teste que reproduza literalmente:

1. 5 episódios;
2. tocar EP01;
3. avançar para uma posição intermediária;
4. sair do player;
5. fechar o aplicativo;
6. reabrir;
7. abrir Details;
8. verificar lista:
   - EP01
   - EP02
   - EP03
   - EP04
   - EP05
9. verificar Continuar:
   - EP01;
10. tocar EP01;
11. verificar retomada.

Depois:

1. tocar EP02;
2. fechar/reabrir;
3. verificar:
   - lista contém EP01..EP05;
   - Continuar contém EP02 conforme regra;
   - EP02 permanece na lista.

Repetir para EP03/EP04.

Esse teste deve falhar no estado bugado e passar após a correção.

---

# 15. NÃO ACEITAR FALSAS SOLUÇÕES

NÃO resolver com:

- esconder menos episódios;
- remover simplesmente um `filter()`;
- ignorar `missing`;
- nunca marcar missing;
- nunca limpar banco;
- nunca executar scanner;
- duplicar episódios;
- criar nova tabela paralela de progresso;
- criar nova fonte de verdade;
- aumentar timeout;
- adicionar sleep;
- retry cego;
- try/except que engole erro;
- reconstruir todo o projeto;
- remover Next;
- remover Previous;
- remover Autoplay;
- desabilitar Continue;
- desabilitar persistência;
- desabilitar reconciliation;
- simplesmente recarregar a tela infinitamente.

A solução deve corrigir a causa.

---

# 16. NÃO REESCREVER O PROJETO

Preservar a arquitetura existente.

Não fazer grande refatoração sem necessidade.

Alterar somente o que for necessário para:

- corrigir identidade;
- corrigir projeções;
- corrigir persistência;
- corrigir reconciliação;
- corrigir hidratação;
- corrigir retomada;
- adicionar testes;
- corrigir integração entre componentes.

Preservar todas as funcionalidades existentes.

Não adicionar:

- AniList;
- novos recursos de player;
- novos layouts;
- novas seções;
- novas funcionalidades não relacionadas.

Esta é uma correção de estabilidade/regressão.

---

# 17. INVESTIGAR O HISTÓRICO GIT

Antes da correção final, pesquisar o histórico relacionado a:

- progress;
- playback;
- details;
- continue watching;
- current episode;
- catalog;
- reconciliation;
- missing;
- scanner;
- episode identity;
- resume;
- restart;
- player_exited;
- player_progress.

Comparar commits anteriores quando necessário.

Não restaurar código antigo cegamente.

Se uma mudança histórica introduziu o problema, identificar o commit e explicar tecnicamente.

---

# 18. DOCUMENTAÇÃO EXTERNA

Quando houver dúvida técnica, consultar documentação atual e fontes confiáveis sobre:

- Android Activity lifecycle;
- Media3/ExoPlayer playback position;
- MediaStore generation/version;
- persistência SQLite;
- concorrência;
- lifecycle de processos Android.

Não usar documentação externa como substituto da análise do código do ReiAnix.

A causa final deve ser demonstrada pelo comportamento do próprio repositório.

---

# 19. INSTRUMENTAÇÃO TEMPORÁRIA

Se necessário, adicionar logs temporários para acompanhar:

    episodeId
    animeId
    path
    progress
    duration
    watched
    missing
    sessionId
    requestId
    generation
    scan generation
    catalog count
    season count
    episode count
    details episode count
    continuation count

Exemplo conceitual:

    BEFORE_PLAY
    PROGRESS_PERSIST
    PLAYER_EXIT
    DB_PROGRESS_COMMITTED
    STARTUP_SCAN
    RECONCILIATION
    CATALOG_LOAD
    DETAILS_LOAD
    DETAILS_EPISODES
    CONTINUATION_PROJECTION
    RESUME_TARGET
    RESUME_POSITION

Depois de encontrar a causa, remover debug desnecessário.

Não deixar instrumentação excessiva no release.

---

# 20. INVARIANTES OBRIGATÓRIOS APÓS A CORREÇÃO

As seguintes invariantes devem sempre ser verdadeiras:

### Invariante 1

Se o episódio existe localmente e pertence ao anime:

    episode ∈ catalog(anime)

independentemente de progress.

### Invariante 2

Se:

    progress > 0
    AND not completed

então o episódio pode estar em Continuar, mas continua em catalog.

### Invariante 3

Continuar não pode remover itens do catálogo.

### Invariante 4

Um episódio A não pode receber progresso de B.

### Invariante 5

Um evento antigo não pode sobrescrever estado mais novo sem uma regra explícita de versionamento.

### Invariante 6

Reabrir o aplicativo não pode mudar a identidade de um episódio sem preservar seu estado.

### Invariante 7

Scanner incompleto não pode produzir remoção definitiva.

### Invariante 8

Details deve exibir a coleção canônica de episódios.

### Invariante 9

Playback target deve apontar para um episódio que pertence ao catálogo.

### Invariante 10

Se o progresso persistido é válido, tocar novamente deve usar esse progresso para resume.

---

# 21. VALIDAÇÃO DO BANCO

Adicionar testes específicos de SQLite para:

- INSERT episode;
- UPDATE progress;
- UPDATE watched;
- UPSERT do mesmo episódio;
- rescan;
- reconciliation;
- missing;
- reload;
- reopen;
- identidade;
- transações concorrentes.

Verificar se existe algum UPDATE/UPSERT que inadvertidamente faça:

    progress = 0

durante:

- scanner;
- metadata refresh;
- hydration;
- startup;
- reconciliation.

Se existir, corrigir.

---

# 22. VALIDAÇÃO DE PERFORMANCE

A correção não deve introduzir:

- query N+1;
- reload completo desnecessário;
- rebuild excessivo do Flet;
- múltiplos scans;
- loops de refresh;
- page.update() excessivo.

Manter o pipeline atual eficiente.

---

# 23. BUILD E TESTES

Depois da correção:

1. executar testes unitários relevantes;
2. executar testes de integração relevantes;
3. executar testes de player/lifecycle;
4. executar testes de scanner/reconciliation;
5. executar compileall quando aplicável;
6. executar lint/validações existentes;
7. executar `git diff --check`;
8. executar build do APK quando possível;
9. executar testes Android instrumentados quando disponíveis;
10. revisar o diff completo.

Não afirmar que algo foi executado se não foi realmente executado.

---

# 24. VALIDAÇÃO MANUAL OBRIGATÓRIA

Se o ambiente permitir, instalar o APK e testar:

### Teste 1

- abrir biblioteca;
- abrir anime;
- verificar EP01..EP05.

### Teste 2

- abrir EP01;
- assistir alguns segundos;
- sair;
- voltar para Details;
- confirmar EP01 ainda aparece.

### Teste 3

- fechar aplicativo completamente;
- abrir novamente;
- abrir anime;
- confirmar EP01 ainda aparece.

### Teste 4

- tocar EP01;
- confirmar resume.

### Teste 5

- tocar EP02;
- fechar/reabrir;
- confirmar EP02 continua na lista.

### Teste 6

- repetir para vários episódios.

### Teste 7

- observar Home → Continuar;
- abrir Details;
- confirmar que a lista completa continua intacta.

### Teste 8

- testar scanner/reload;
- confirmar que nenhum episódio válido desaparece.

---

# 25. CRITÉRIO DE ACEITAÇÃO FINAL

A correção só está concluída se este cenário funcionar:

    EP01
    EP02
    EP03
    EP04
    EP05

Usuário:

    abre EP01
    assiste até 37%
    fecha o app
    abre novamente

Resultado obrigatório:

    EPISÓDIOS
    EP01 — Em andamento • 37%
    EP02
    EP03
    EP04
    EP05

E:

    CONTINUAR
    EP01 — 37%

Ao tocar EP01:

    mesmo episódio
    mesmo arquivo
    progresso persistido
    player inicia aproximadamente em 37%

Depois:

    abre EP02
    assiste até 20%
    fecha
    abre novamente

Resultado:

    EP01
    EP02 — Em andamento • 20%
    EP03
    EP04
    EP05

E Continuar deve refletir os episódios incompletos segundo a regra existente.

NENHUM episódio pode desaparecer da lista normal apenas porque ganhou progresso.

---

# 26. ENTREGA OBRIGATÓRIA

Ao terminar, informar:

## Causa raiz

Explicar exatamente:

- onde o episódio era perdido;
- qual condição causava o desaparecimento;
- se era UI, catálogo, SQLite, identidade, scanner, reconciliation, bridge, player ou combinação;
- por que o problema só aparecia claramente após fechar/reabrir.

## Evidências

Informar:

- arquivos;
- funções;
- queries;
- callbacks;
- eventos;
- histórico Git relevante;
- testes que demonstraram a causa.

## Correção

Explicar:

- arquivos modificados;
- lógica corrigida;
- invariantes adicionadas;
- proteção contra regressão.

## Testes

Listar:

- testes adicionados;
- testes modificados;
- testes executados;
- resultados reais.

## Build

Informar:

- se APK foi compilado;
- variante;
- resultado;
- erros, se houver.

## Diff

Informar claramente:

### Arquivos adicionados

### Arquivos modificados

### Arquivos removidos

### Pastas adicionadas/removidas

### Arquivos que já existiam e foram reutilizados

### O que não pôde ser implementado/verificado

### Riscos residuais

Não ocultar falhas.

---

# 27. REGRA FINAL

Não tratar o sintoma.

Não simplesmente fazer o episódio reaparecer na UI.

Corrigir a cadeia inteira:

    identidade
      ↓
    persistência
      ↓
    scanner
      ↓
    reconciliation
      ↓
    SQLite
      ↓
    catálogo canônico
      ↓
    Details
      ↓
    Continuar
      ↓
    playback target
      ↓
    Media3 resume

O resultado final deve ser estrutural:

> Um episódio que existe na biblioteca continua pertencendo à lista de episódios independentemente do progresso. O progresso é estado de consumo, não critério de existência. "Continuar" é uma projeção adicional. O estado deve sobreviver ao fechamento/reabertura do aplicativo e o mesmo episódio deve retomar da posição persistida.

Preservar o ReiAnix existente.

NÃO adicionar novas funcionalidades.

NÃO fazer reescrita arquitetural desnecessária.

Corrigir definitivamente a regressão.
