# PROMPT 42 — AUDITORIA FORENSE DE RUNTIME E CORREÇÃO DEFINITIVA DO PLAYER, REFRESH E ARTWORK

## REPOSITÓRIO

Trabalhe diretamente no repositório oficial:

https://github.com/reinansantos9090-debug/ReiAnix

Branch de trabalho: `main`.

Este é o projeto ReiAnix existente. NÃO reinicie o projeto, NÃO crie outro projeto e NÃO trate a tarefa como uma implementação do zero.

---

# OBJETIVO

Executar uma auditoria forense de runtime e corrigir definitivamente os bugs que permanecem no APK real:

1. Player Android abre, fica preto/carregando e depois fecha sozinho/volta para a tela de Details.
2. Next e Previous dentro do player continuam sem funcionamento confiável.
3. Botão Atualizar da Home apresenta comportamento inconsistente.
4. Pull-to-refresh não funciona como deveria.
5. Capas dos animes ficam trocando, carregando, desaparecendo ou sendo substituídas por outras imagens durante a própria sessão.
6. O aplicativo apresenta lag/jank perceptível durante essas operações.

A regra desta tarefa é:

> NÃO considerar um teste estático, um teste Python, um APK que apenas compila ou um conjunto de asserts de código como prova de correção do runtime.

A correção somente será considerada concluída quando o fluxo real tiver sido reproduzido, a causa tiver sido identificada com evidência de runtime e o APK tiver passado pelos testes end-to-end descritos abaixo.

---

# CONTEXTO CRÍTICO

As tentativas anteriores corrigiram vários contratos e pontos de infraestrutura, mas o comportamento observado no APK ainda é incorreto.

A causa desse paradoxo precisa ficar registrada:

- grande parte das correções anteriores foi validada por testes estáticos/Python e build;
- não houve uma captura forense do ciclo real do NativePlayerActivity no aparelho que apresenta o problema;
- portanto ainda não existia evidência suficiente para distinguir:
  - erro Media3/decoder;
  - superfície de vídeo;
  - URI/preflight;
  - Activity finish/back;
  - lifecycle/task reordering;
  - transição stale;
  - race Python ↔ Android;
  - ou combinação de mais de um desses fatores.

Esta tarefa deve fechar essa lacuna.

---

# EVIDÊNCIA DO VÍDEO DE REPRODUÇÃO

Foi fornecida uma gravação de tela do APK real.

Características do arquivo analisado:

- 1080 × 2340
- ~37,78 fps
- 8434 frames
- ~223,24 s

Comportamento observado:

### Repro 1 — Rising Impact

Por volta de 116 s:

- o NativePlayerActivity aparece;
- tela predominantemente preta;
- controles do player aparecem;
- o vídeo não apresenta uma imagem estável imediatamente.

Por volta de 120–122 s:

- a tela continua no player;
- há alterações na área central do vídeo;
- os controles continuam presentes.

Entre aproximadamente 123,0 e 124,0 s:

- o player começa a desaparecer;
- a tela de Details aparece por baixo;
- o player sai da frente com uma transição de Activity;
- em seguida a tela de Details fica totalmente visível.

Isso é importante: não é simplesmente “o vídeo ficou preto”.

Há evidência visual de que a Activity do player deixa de ocupar a tela.

### Repro 2 — outro anime

Por volta de 181 s:

- o player mostra conteúdo de vídeo real.

Por volta de 184–186 s:

- o player desaparece novamente;
- a tela de Details volta a ficar visível.

### Repro 3 — novo lançamento

Por volta de 196 s:

- o player abre novamente.

Poucos segundos depois:

- volta a desaparecer.

Portanto o problema não é limitado a um único título.

---

# ACHADOS FORENSES JÁ CONFIRMADOS NO CÓDIGO

## 1. PULL-TO-REFRESH POSSUI UM ERRO CONCRETO DE CONTRATO COM FLET

Arquivo:

`views/home_view.py`

O código atual tenta dirigir a máquina de estados usando:

- `START`
- `OVERSCROLL`
- `UPDATE`
- `USER`
- `END`

Porém a documentação oficial atual do Flet para `OnScrollEvent` descreve `event_type` com:

- `ScrollType.UPDATE`
- `ScrollType.USER`
- `ScrollType.OVERSCROLL`

e documenta `overscroll` especificamente para `OVERSCROLL`.

Fonte oficial:

https://flet.dev/docs/types/onscrollevent/

Assim, a implementação atual está esperando notificações `START` e `END` que não fazem parte do contrato documentado do `OnScrollEvent`.

Isso é um achado de causa, não uma hipótese.

### Consequência

A máquina de pull-to-refresh não possui um ciclo real de início/fim compatível com o contrato do Flet.

Não é aceitável apenas alterar strings ou adicionar mais condições.

A implementação deve ser refeita em torno das notificações realmente emitidas pelo Flet 0.86.5:

- USER
- UPDATE
- OVERSCROLL

e de propriedades documentadas:

- `pixels`
- `min_scroll_extent`
- `extent_before`
- `overscroll`
- `velocity`
- `out_of_range`
- `at_edge`.

Não inventar novos tipos de evento.

---

# 2. O PIPELINE DE REFRESH TEM DUPLICAÇÃO DE AUTORIDADE

Atualmente existem várias camadas:

- `HomeView.handle_manual_refresh()`
- `main.py: refresh_home_library()`
- `main.py: refresh_library()`
- `ScanCoordinator`
- callbacks de conclusão do catálogo
- `_home_refresh_ui_updated()`
- `_fail_home_refresh()`

Isso precisa continuar tendo apenas uma autoridade para decidir:

- request;
- in-flight;
- success;
- error;
- completion.

Em particular, quando Home já está em `REFRESHING`, hoje o código ainda pode encaminhar outro pedido para o callback/coordinator em vez de tratar a ação como no-op controlado.

Corrigir isso.

### Regra

Um toque no botão ou um gesto de pull deve produzir:

`USER_INTENT -> refresh_id -> coordinator.request -> scan -> catalog/db update -> UI commit -> SUCCESS/ERROR`

Nunca:

`USER_INTENT -> múltiplos requests -> dedupe implícito -> estados concorrentes`

---

# 3. O PROBLEMA DAS CAPAS TEM UM CROSS-WIRE CONCRETO ENTRE THUMBNAIL DE EPISÓDIO E POSTER DO ANIME

Este é um dos achados mais importantes.

Arquivo:

`views/home_view.py`

Função:

`update_thumbnail_in_place()`

O código recebe uma miniatura gerada para um episódio e depois:

- encontra o anime afetado;
- altera `anime.meta["cover_cache"]`;
- percorre `artwork_bindings[(entity, anime_id, "poster")]`;
- substitui diretamente o conteúdo desses holders por `ft.Image(src=thumbnail_path)`.

Em outras palavras:

> uma thumbnail de episódio está sendo usada para alterar a capa/poster do anime.

Isso mistura dois domínios que devem ser independentes:

- `episode_thumbnail`
- `poster`

Isso explica diretamente um padrão do tipo:

1. capa normal começa a ser carregada;
2. thumbnail de episódio termina;
3. thumbnail vira “capa” do anime;
4. metadata/artwork poster termina;
5. capa normal aparece novamente;
6. outro thumbnail termina;
7. capa troca novamente.

Isso é exatamente o tipo de comportamento de “as capas ficam mudando sozinhas” relatado no APK.

### CORREÇÃO OBRIGATÓRIA

`episode_thumbnail` NUNCA pode:

- escrever `anime.cover_cache`;
- escrever `anime.meta.cover_cache`;
- atualizar binding `poster`;
- substituir visual de `poster`.

Uma thumbnail de episódio pode atualizar somente:

- o holder de thumbnail do episódio correspondente;
- o registro `artwork_type=episode_thumbnail`.

---

# 4. EXISTE UM SEGUNDO CROSS-WIRE NO ArtworkEngine

Arquivo:

`core/artwork.py`

Função:

`register_generated_thumbnail()`

O fluxo atual pode:

- registrar `episode_thumbnail`;
- verificar se existe poster “protegido”;
- apagar poster `source='generated'`;
- e criar uma entrada de `poster` com `local_path=thumbnail_path`.

Isso também mistura os tipos.

Uma miniatura de vídeo não deve ser promovida automaticamente para o papel de poster do anime.

### CORREÇÃO OBRIGATÓRIA

Separar semanticamente:

- poster;
- backdrop;
- thumbnail;
- episode_thumbnail;
- season_poster.

Não permitir que `register_generated_thumbnail()` crie/substitua um poster do anime.

Caso exista uma decisão de fallback visual, ela deve ser somente de apresentação, nunca persistir a thumbnail como `poster`.

---

# 5. A APRESENTAÇÃO DA CAPA TEM MAIS DE UMA FONTE DE VERDADE

Há atualmente:

- `anime.cover_cache`;
- `meta.cover_cache`;
- `meta.cover_url`;
- ArtworkEngine;
- artwork rows;
- thumbnail generated;
- bindings dos holders;
- hydration assíncrona;
- prefetch assíncrono.

O Home ainda lê diretamente:

`item.get("cover") or meta.get("cover_cache")`

enquanto também dispara resolução do ArtworkEngine.

Isso permite que duas fontes diferentes tentem determinar a imagem exibida.

### CORREÇÃO OBRIGATÓRIA

Para apresentação de poster no Home:

> existir uma única função/resolvedor autoritativo de poster.

Essa função deve retornar:

- caminho local validado;
- identidade da arte;
- source;
- version/generation;
- request token.

A UI não deve escolher entre `cover_cache`, `cover_url` e ArtworkEngine por conta própria.

---

# 6. ArtworkEngine PERMITE MÚLTIPLOS REGISTROS PARA A MESMA ARTE

O ArtworkEngine usa `artwork_key` e pode manter múltiplas entradas para a mesma entidade/tipo provenientes de fontes/URLs diferentes.

Isso não é necessariamente errado por si só.

O problema é que a seleção atual pode depender de:

- priority;
- updated_at;
- id;
- URL diferente;
- hydration posterior.

Se a metadata for atualizada e gerar uma nova referência para a mesma capa, o resolvedor pode passar a enxergar outra entrada como candidata.

### CORREÇÃO OBRIGATÓRIA

Implementar identidade canônica de poster:

`entity + artwork_type + logical_variant + provider_identity`

e uma política de substituição determinística.

Uma nova imagem NÃO pode substituir a imagem atualmente exibida simplesmente porque terminou depois.

Ela só pode substituir quando:

1. pertence ao mesmo item lógico;
2. possui request generation atual;
3. é validada;
4. está pronta;
5. foi aceita pelo resolvedor como nova versão canônica.

---

# 7. HOME NÃO ESTÁ USANDO O RESULTADO DE ARTWORK COM UMA IDENTIDADE DE REQUEST

Atualmente o Home trabalha com:

- `render_generation`;
- `artwork_tasks`;
- `artwork_bindings`.

Isso protege parte dos resultados antigos, mas não impede que várias fontes válidas concorram sobre o mesmo holder.

A proteção precisa ser por item + tipo + generation/version, não somente por geração global da view.

### OBRIGATÓRIO

Adicionar pelo menos:

`artwork_resolution_token = (entity, entity_id, artwork_type, request_generation)`

e atualizar o holder somente se o token retornado ainda for o token ativo daquele item.

---

# 8. FLET TEM HISTÓRICO REAL DE PROBLEMAS DE FLICKER/UPDATE EM IMAGENS

Foram pesquisados:

- documentação oficial;
- GitHub Issues;
- GitHub Discussions;
- Media3/AndroidX;
- Stack Overflow;
- mecanismos de busca;
- comunidades e artigos técnicos.

Casos relevantes no Flet:

### Flet #6231

“UI Flickering When Updating Image Control...”

O relato mostra desaparecimento/re-renderização de imagens ao chamar `update()`, especialmente após mudanças de versão.

https://github.com/flet-dev/flet/issues/6231

### Flet #4435

“Real-time update of image control breaks socket connection”

O problema aparece quando atualizações de imagens são enviadas em excesso; limitar a frequência de updates melhora o comportamento.

https://github.com/flet-dev/flet/issues/4435

### Flet #5048

“Flickering and slow image load in ft.Container”

Outro caso de flicker e atualização visual de imagem.

https://github.com/flet-dev/flet/issues/5048

Portanto:

> não fazer uma atualização de UI para cada pequena mudança de arte.

Agrupar updates é obrigatório.

---

# 9. PLAYER: O VÍDEO PROVA QUE A ACTIVITY DO PLAYER ESTÁ SAINDO DE CENA

No código atual de `NativePlayerActivity.kt`, as chamadas diretas a `finish()` estão concentradas em:

1. rejeição de handoff sucessor considerado inválido;
2. `finishPlayer()`.

`finishPlayer()` é usado em:

- botão Voltar;
- Android Back;
- botão “Voltar ao ReiAnix” no painel de erro.

O método `onPlayerError()` não deveria fechar a Activity diretamente.

Isso é importante porque o vídeo mostra uma saída visual de Activity.

### O QUE AINDA NÃO ESTÁ PROVADO

Sem logcat/runtime não é possível afirmar honestamente se o fechamento observado foi:

- Android Back/edge gesture;
- `finishPlayer()`;
- handoff classificado como stale;
- task/lifecycle externo;
- processo/Activity destruído por exceção;
- ou outra condição do sistema.

Portanto esta tarefa deve produzir a prova.

---

# 10. O PLAYER USA TextureView

O layout atual usa:

`surface_type="texture_view"`

Media3 documenta SurfaceView e TextureView como opções diferentes.

A documentação e vários problemas públicos do AndroidX Media mostram que a camada de Surface pode produzir:

- black screen;
- flicker;
- problemas de lifecycle;
- problemas ao substituir/desanexar a Surface;
- problemas dependentes de dispositivo/versão Android.

Referências:

https://developer.android.com/media/media3/ui/player-view

https://github.com/androidx/media/issues/3011

https://github.com/androidx/media/issues/3285

https://github.com/androidx/media/issues/2493

https://github.com/androidx/media/issues/2035

O issue #3011 documenta uma classe de falha em que uma TextureView já destruída/desanexada pode gerar erro ao tentar configurar a Surface.

O issue #3285 mostra comportamento dependente de SurfaceView/TextureView em dispositivos Android diferentes.

Isso NÃO prova que `TextureView` é a causa deste aplicativo.

Mas é uma hipótese técnica prioritária e deve ser testada em A/B.

---

# 11. Media3 ESTÁ FIXADO EM 1.11.1

O projeto usa Media3 ExoPlayer/UI 1.11.1.

As release notes oficiais de 1.11.1, publicada em 10/09/2026, registram correções de playback e renderer/surface.

https://github.com/androidx/media/blob/release/RELEASENOTES.md

A tarefa deve verificar se:

1. 1.11.1 é realmente a versão apropriada para a build atual;
2. existe correção posterior relevante;
3. o problema ocorre em 1.11.1 e também no último release estável;
4. o comportamento muda ao trocar somente Media3;
5. o comportamento muda ao trocar somente SurfaceView/TextureView.

Não atualizar “por atualizar”.

Toda mudança de versão deve ser uma experiência controlada.

---

# 12. NEXT/PREVIOUS TEM UMA LACUNA DE VALIDAÇÃO

Arquivo:

`MainActivity.kt`

A função `isCurrentPlayerHandoff()` valida:

- request;
- origin request;
- session;
- timestamps;
- revoke state.

Porém NÃO valida explicitamente:

`originTransitionGeneration`

contra a geração de transição atual.

Isso é uma lacuna real no contrato de sucessores.

### CORREÇÃO OBRIGATÓRIA

Um handoff NEXT/PREVIOUS somente pode ser aceito se coincidir:

- originRequestId;
- targetRequestId;
- playerSessionId;
- originPlayerSessionId;
- originTransitionGeneration;
- transitionDirection;
- activityInstance/session atual;
- generation atual.

Um callback antigo nunca pode confirmar um episódio novo.

---

# 13. NEXT/PREVIOUS PRECISA DE TESTE E2E REAL

Não considerar o botão corrigido apenas porque:

- a função existe;
- `NativeMailbox.write()` é chamado;
- existe teste de string;
- existe teste unitário.

O teste definitivo deve:

1. abrir episódio;
2. aguardar `STATE_READY`;
3. aguardar primeiro frame;
4. pressionar NEXT;
5. confirmar novo episódio;
6. confirmar primeiro frame;
7. repetir NEXT;
8. repetir PREVIOUS;
9. fazer taps rápidos;
10. garantir uma única transição por intenção;
11. garantir que a Activity não desaparece;
12. garantir que o episódio anterior não retoma depois que o seguinte já abriu;
13. testar autoplay;
14. testar erro no episódio seguinte;
15. testar Back depois da transição.

---

# 14. A EXPLICAÇÃO DE POR QUE OS BUGS SOBREVIVERAM ÀS PROMPTS ANTERIORES

Este é um requisito do diagnóstico final.

Não dizer simplesmente “faltaram testes”.

Explicar tecnicamente:

- quais camadas foram alteradas;
- quais camadas não foram realmente exercitadas no hardware;
- quais problemas são de runtime e não são detectáveis apenas por pytest;
- quais problemas são de integração entre Flet, Kotlin e Media3;
- quais problemas são races assíncronos;
- quais problemas são de contrato incorreto entre bibliotecas.

A análise deve separar:

### confirmado pelo código
### confirmado pelo vídeo
### confirmado por documentação/issue externo
### ainda precisa de logcat/perfetto para prova final

---

# FASE 0 — NÃO ALTERAR PRODUÇÃO ATÉ INSTRUMENTAR O RUNTIME CRÍTICO

Antes de reescrever player ou artwork, criar instrumentação de diagnóstico.

Cada sessão do player deve possuir:

- traceId;
- requestId;
- playerSessionId;
- activityInstanceId;
- episodeId;
- animeId;
- URI normalizada;
- transitionGeneration;
- playerGeneration.

Registrar com timestamp monotônico e wall-clock:

- PLAY_REQUEST_CREATED
- NATIVE_COMMAND_SENT
- PLAYER_HANDOFF_DISPATCHED
- PLAYER_ACTIVITY_ON_CREATE
- PLAYER_ACTIVITY_ON_START
- PLAYER_ACTIVITY_ON_RESUME
- PLAYER_ACTIVITY_ACTIVE
- URI_PREFLIGHT_STARTED
- URI_PREFLIGHT_RESULT
- MEDIA_ITEM_SET
- PLAYER_PREPARE
- STATE_IDLE
- STATE_BUFFERING
- STATE_READY
- FIRST_FRAME
- PLAYER_ERROR
- PLAYER_ON_PAUSE
- PLAYER_ON_STOP
- USER_LEAVE_HINT
- BACK_DISPATCHED
- FINISH_PLAYER_REQUESTED
- FINISH_PLAYER_REASON
- SET_RESULT
- PLAYER_ON_DESTROY
- PLAYER_EXITED

### OBRIGATÓRIO

Em qualquer fechamento inesperado, o log deve dizer claramente:

`PLAYER_EXIT_CLASSIFICATION=<reason>`

Exemplos:

- BACK_GESTURE
- BACK_BUTTON
- ERROR_PANEL_BACK
- STALE_HANDOFF_REJECTED
- SYSTEM_TASK_REMOVAL
- ACTIVITY_STOP_UNEXPECTED
- PROCESS_DEATH
- UNKNOWN

Sem isso, não considerar o problema investigado.

---

# FASE 1 — PLAYER RUNTIME FORENSICS

Implementar também um listener/AnalyticsListener Media3 para registrar:

- playbackState;
- playWhenReady;
- playbackSuppressionReason;
- isPlaying;
- playerError.errorCode;
- playerError.errorCodeName;
- message;
- cause class;
- cause message;
- full cause chain;
- renderer index;
- renderer type;
- media format;
- MIME;
- codec quando disponível;
- decoder initialization;
- decoder error;
- video size;
- dropped frames;
- first frame rendered;
- surface events.

Registrar especialmente:

- `onPlayerError`;
- `onPlaybackStateChanged`;
- `onRenderedFirstFrame`;
- `onVideoSizeChanged`;
- decoder/renderer callbacks apropriados.

Não esconder `PlaybackException`.

---

# FASE 2 — TESTE A/B DA SURFACE

Executar duas variantes controladas:

### Variante A
TextureView atual.

### Variante B
SurfaceView.

Não alterar qualquer outra coisa.

Medir:

- primeiro frame;
- tempo até READY;
- black screen;
- decoder errors;
- Activity close;
- Surface attach/detach;
- codec init;
- playback duration.

Se SurfaceView resolver o problema, registrar a evidência e adotar a solução somente depois do teste.

Se não resolver, não atribuir o problema à Surface.

---

# FASE 3 — TESTE DO ARQUIVO REAL

Não usar apenas vídeo sintético.

Reproduzir:

1. um MP4/H.264 simples;
2. um arquivo real da biblioteca que falhou;
3. arquivos MKV se existirem;
4. arquivos com áudio/subtitle;
5. arquivo que falhou imediatamente;
6. arquivo que no vídeo reproduz por alguns segundos antes de a Activity sair.

Registrar MIME, tamanho, duração e codecs.

O issue público do Media3 #3250 mostra que existem casos em que MKV pode abrir e permanecer preto por problemas de tracks no container:

https://github.com/androidx/media/issues/3250

Isso deve ser testado sem assumir que o bug do ReiAnix seja esse.

---

# FASE 4 — IMPEDIR FECHAMENTO SILENCIOSO

Depois de descobrir a classificação do fechamento:

- eliminar qualquer `finish()` indireto não intencional;
- não converter `player_error` em encerramento de Activity;
- não permitir stale callback derrubar uma sessão válida;
- não permitir request antigo encerrar o player atual;
- manter o painel de erro visível quando o problema for de reprodução;
- fornecer ao usuário ação explícita “Voltar ao ReiAnix” somente para fechar o player.

Se o sistema realmente estiver enviando Back, registrar isso em vez de mascarar.

---

# FASE 5 — CORRIGIR NEXT/PREVIOUS

Refatorar para uma máquina de estado explícita:

`IDLE`
→ `REQUESTED`
→ `HANDOFF_DISPATCHED`
→ `TARGET_ACTIVITY_ACTIVE`
→ `PREPARING`
→ `READY`
→ `FIRST_FRAME`
→ `COMMITTED`

Em caso de erro:

`REQUESTED/PREPARING -> FAILED`

Nunca:

`REQUESTED -> FINISH_CURRENT -> hope_new_activity_opens`

A Activity atual só pode deixar de ser a atividade controladora quando a sucessora tiver sido validada.

Corrigir a validação de `originTransitionGeneration`.

Adicionar timeout explícito para cada fase e diagnosticar exatamente qual fase ficou parada.

---

# FASE 6 — REFAZER PULL-TO-REFRESH USANDO O CONTRATO REAL DO FLET

Não manter a lógica `START/END` atual.

Usar os eventos suportados pelo `OnScrollEvent`.

Requisitos:

- detectar que o gesto está no topo;
- detectar `OVERSCROLL` negativo;
- acumular o deslocamento corretamente;
- usar o estado `USER`/direção para saber que há gesto real;
- usar um mecanismo de conclusão suportado pelo Flet em vez de esperar `END`;
- disparar no máximo uma atualização por gesto;
- impedir refresh duplicado enquanto uma atualização está ativa;
- resetar corretamente após sucesso/erro/cancelamento;
- preservar posição de scroll;
- não iniciar scan enquanto a pasta está sendo selecionada;
- não deixar a UI permanentemente presa em REFRESHING.

Adicionar logs:

- PULL_GESTURE_START
- PULL_OVERSCROLL
- PULL_THRESHOLD_REACHED
- PULL_REFRESH_TRIGGERED
- PULL_REFRESH_COMPLETED
- PULL_REFRESH_CANCELLED
- PULL_REFRESH_REJECTED

Os testes devem usar os nomes/documentação reais do Flet.

---

# FASE 7 — SIMPLIFICAR O REFRESH BUTTON

O botão e o pull-to-refresh devem chamar a mesma função de intenção:

`request_home_refresh(source)`

Essa função deve ser a única porta de entrada da Home.

Não criar outro request se já existir um refresh ativo.

Usar:

- refreshId;
- requestId;
- scanId;
- terminal state.

Somente a mesma operação pode publicar SUCCESS.

Um evento de uma operação antiga não pode completar o refresh atual.

---

# FASE 8 — CORRIGIR ARTWORK DEFINITIVAMENTE

### REGRA DE DOMÍNIO

`poster != episode_thumbnail`

Sempre.

Remover:

- atualização de poster a partir de thumbnail;
- gravação de thumbnail em `anime.cover_cache`;
- criação de `poster` pelo fluxo de `register_generated_thumbnail()`.

### Poster

Pode vir de:

- manual;
- local;
- cache remoto validado;
- metadata provider.

### Episode thumbnail

Pode vir somente de:

- VideoThumbnailExtractor / thumbnail engine.

Não misturar os dois.

---

# FASE 9 — RESOLVER POSTER DE FORMA CANÔNICA

Criar uma única API, por exemplo:

`resolve_poster(entity_type, entity_id, view_generation, request_token)`

que:

1. verifica cache local validado;
2. verifica artwork row canônica;
3. agenda download somente se necessário;
4. retorna a imagem atual;
5. carrega nova imagem em background;
6. substitui somente quando validada;
7. nunca manda uma imagem antiga de volta para a UI.

Nenhum código de Home deve escolher manualmente entre:

- cover;
- cover_cache;
- cover_url;
- thumbnail;
- artwork row concorrente.

---

# FASE 10 — FIXAR A UI POR TOKEN

Cada binding de poster deve guardar:

- entity;
- entity_id;
- artwork_type;
- view_generation;
- resolution_token.

Ao receber resultado assíncrono:

`if token != current_token: IGNORE`

Ao destruir/rebuildar a Home:

- invalidar bindings;
- remover holders antigos;
- cancelar requests antigos quando possível.

---

# FASE 11 — REDUZIR IMAGE UPDATE STORM

Um batch de arte deve produzir:

- zero ou um update de UI por ciclo de lote.

Não:

- update por arquivo;
- update por thumbnail;
- update por metadata;
- update por retry;
- update por hydration.

O código deve agrupar as alterações.

Considerar os problemas documentados nas issues do Flet #6231 e #4435.

---

# FASE 12 — TESTES OBRIGATÓRIOS

## Testes Python

Criar/atualizar testes para:

- refresh state machine;
- pull event types reais;
- duplicate refresh;
- stale refresh completion;
- artwork source isolation;
- poster != episode_thumbnail;
- generation/token isolation;
- image replacement ordering;
- stale artwork result ignored.

## Testes Kotlin/Android

Criar testes para:

- initial player launch has no successor origin request;
- stale successor rejected;
- valid successor accepted;
- originTransitionGeneration validated;
- no finish on player error;
- finish reason always classified;
- activity lifecycle trace;
- next/previous generation;
- player session/activity identity.

## Instrumented E2E

Executar:

### Player
- abrir episódio;
- esperar 15 segundos;
- confirmar Activity continua ativa;
- confirmar READY;
- confirmar first frame;
- salvar progresso;
- Back;
- abrir novamente;
- NEXT;
- PREVIOUS;
- autoplay.

### Refresh
- abrir Home;
- tocar atualizar;
- tocar várias vezes;
- puxar para atualizar;
- puxar abaixo do limite;
- puxar acima do limite;
- fazer scroll normal;
- repetir;
- confirmar apenas um scan por gesto.

### Artwork
- abrir Home com várias capas;
- assistir a imagens chegando progressivamente;
- gerar thumbnails;
- navegar;
- voltar;
- atualizar biblioteca;
- confirmar que poster nunca vira frame de episódio;
- confirmar que uma capa pronta nunca é substituída por outra mais antiga.

---

# FASE 13 — LOGCAT/PERFETTO/PROFILER

Quando o aparelho estiver disponível, coletar:

### Logcat

Filtrar:

- ReiAnix;
- ActivityTaskManager;
- WindowManager;
- MediaCodec;
- Codec2Client;
- ExoPlayer;
- AndroidRuntime;
- Flet;
- Flutter.

Também capturar:

`adb logcat -b all -v threadtime`

durante exatamente a reprodução.

### Perfetto

Capturar pelo menos:

- sched;
- gfx;
- view;
- binder_driver;
- am;
- wm;
- freq;
- idle;
- memory;
- surfaceflinger.

Pergunta principal:

> existe stall/stop/finish no mesmo instante em que o player abandona a tela?

### Android Profiler

Observar:

- CPU spike;
- memória;
- threads;
- GC;
- network;
- process death;
- main-thread stalls.

Não usar profiler como substituto de logcat.

---

# FASE 14 — CRITÉRIO DE CAUSA RAIZ

Para cada bug, entregar uma tabela:

| Bug | Causa raiz | Evidência no código | Evidência no runtime | Evidência externa | Correção |
|---|---|---|---|---|---|
| Player fecha | obrigatório preencher | ... | ... | ... | ... |
| Next | obrigatório preencher | ... | ... | ... | ... |
| Previous | obrigatório preencher | ... | ... | ... | ... |
| Refresh button | obrigatório preencher | ... | ... | ... | ... |
| Pull-to-refresh | contrato START/END incorreto + causa final | ... | ... | ... | ... |
| Covers | cross-wire episode_thumbnail → poster | ... | ... | ... | ... |
| Lag | obrigatoriamente medir | ... | ... | ... | ... |

Não usar “provavelmente” quando existir evidência suficiente.

Quando não for possível provar algo sem o aparelho, registrar explicitamente:

`UNPROVEN — NEEDS DEVICE TRACE`

e implementar a instrumentação necessária para provar.

---

# FASE 15 — REGRA ESPECIAL PARA O PLAYER

Não encerrar a investigação com:

- “onPlayerError já trata o erro”;
- “testes passaram”;
- “Media3 foi inicializado”;
- “APK compilou”.

O problema observado é um problema de runtime.

O teste final precisa provar:

### 1.
Player abre.

### 2.
Player permanece aberto.

### 3.
Primeiro frame aparece.

### 4.
Playback continua por pelo menos 15 s.

### 5.
Next abre o próximo episódio.

### 6.
Previous abre o anterior.

### 7.
Back fecha somente quando o usuário solicita.

### 8.
Erro de mídia mostra erro sem matar a Activity.

---

# FASE 16 — REGRA ESPECIAL PARA ARTWORK

O teste final deve ser visual e de dados.

Para qualquer anime:

1. registrar o poster atual;
2. provocar geração de thumbnails;
3. aguardar download de capas;
4. atualizar a Home;
5. navegar para Details;
6. voltar;
7. refresh;
8. verificar novamente.

O poster deve permanecer o poster.

Uma thumbnail de episódio nunca pode aparecer como poster persistido.

---

# FASE 17 — NÃO QUEBRAR O QUE JÁ FUNCIONA

Preservar:

- storage;
- SAF;
- MediaStore;
- importação;
- biblioteca;
- SQLite;
- detalhes;
- progresso;
- back;
- barras do sistema;
- artwork local;
- scanner;
- build;
- Release;
- Actions APK.

Não iniciar AniList como nova funcionalidade.

Não adicionar funcionalidades não relacionadas.

Não trocar Flet por outro framework.

Não reescrever o projeto.

---

# FASE 18 — BUILD E CERTIFICAÇÃO

Depois das correções:

1. Python regression;
2. compileall;
3. Kotlin/Gradle;
4. APK;
5. manifest;
6. native host verification;
7. instrumented tests;
8. APK instalado em Android;
9. testes E2E do player;
10. testes E2E de refresh;
11. testes E2E de artwork.

O build sozinho não é certificação.

---

# FASE 19 — RESULTADO FINAL OBRIGATÓRIO

No final do trabalho apresentar:

## Causa raiz

O que realmente causava cada bug.

## Correções

Arquivo por arquivo.

## Testes

Quantidade executada e resultado real.

## Runtime

- dispositivo/Android;
- Media3;
- Flet;
- player;
- codec;
- SurfaceView/TextureView;
- resultados.

## Performance

- tempo de abertura;
- tempo até READY;
- tempo até primeiro frame;
- refresh;
- quantidade de updates;
- CPU/memória quando disponível.

## Diff

Informar:

- arquivos adicionados;
- arquivos modificados;
- arquivos removidos;
- testes adicionados;
- scripts adicionados.

## Pendências

Somente aquilo que realmente não pôde ser testado.

---

# PROIBIÇÕES

NÃO:

- mascarar erro;
- aumentar timeout sem descobrir a causa;
- colocar `sleep()` para “fazer funcionar”;
- adicionar retries infinitos;
- ignorar exceptions;
- usar `|| true` para esconder falha;
- transformar thumbnail em poster;
- corrigir pull-to-refresh inventando tipos de evento;
- considerar pytest verde como prova de Android runtime;
- declarar “resolvido” sem reprodução pós-correção;
- remover logs essenciais;
- desligar diagnostics para fazer o teste passar.

---

# FONTES EXTERNAS PRIORITÁRIAS PARA A IMPLEMENTAÇÃO

## Flet

OnScrollEvent:

https://flet.dev/docs/types/onscrollevent/

Issue #6231:

https://github.com/flet-dev/flet/issues/6231

Issue #4435:

https://github.com/flet-dev/flet/issues/4435

Issue #5048:

https://github.com/flet-dev/flet/issues/5048

Discussão #6818:

https://github.com/flet-dev/flet/discussions/6818

Changelog Flet 0.86.5:

https://github.com/flet-dev/flet/blob/main/CHANGELOG.md

## Android / Media3

PlayerView:

https://developer.android.com/media/media3/ui/player-view

Release notes Media3:

https://github.com/androidx/media/blob/release/RELEASENOTES.md

Issue #3011 — TextureView/surface lifecycle:

https://github.com/androidx/media/issues/3011

Issue #3285 — SurfaceView/TextureView differences:

https://github.com/androidx/media/issues/3285

Issue #2493 — black screen:

https://github.com/androidx/media/issues/2493

Issue #2035 — black flicker:

https://github.com/androidx/media/issues/2035

Issue #3250 — MKV playback black screen:

https://github.com/androidx/media/issues/3250

Issue #1293 — surface/lifecycle:

https://github.com/androidx/media/issues/1293

Issue #1842 — Activity lifecycle/finish regression history:

https://github.com/androidx/media/issues/1842

---

# DEFINIÇÃO DE “CONCLUÍDO”

A tarefa NÃO está concluída enquanto qualquer um dos seguintes continuar:

- player fecha sozinho;
- player fica preto sem diagnóstico;
- NEXT não troca episódio;
- PREVIOUS não troca episódio;
- Pull-to-refresh não dispara corretamente;
- botão Atualizar inicia requests duplicados;
- refresh fica preso em REFRESHING;
- poster troca para thumbnail de episódio;
- artwork antigo sobrescreve artwork novo;
- UI continua com jank evitável;
- a causa raiz do fechamento do player continua desconhecida.

O objetivo desta tarefa não é produzir mais um “patch”.

O objetivo é:

> reproduzir → observar → identificar causa → corrigir causa → testar novamente → certificar no runtime real.

Só declarar resolução depois de completar esse ciclo.
