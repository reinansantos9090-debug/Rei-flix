
# PROMPT 43 — CORREÇÃO DEFINITIVA DOS BUGS DO REIANIX COM BASE NA AUDITORIA FORENSE

## REPOSITÓRIO OFICIAL

Trabalhe DIRETAMENTE no repositório:

https://github.com/reinansantos9090-debug/ReiAnix

Este prompt é a continuação direta do:
PROMPT_42_AUDITORIA_FORENSE_E_CORRECAO_DEFINITIVA.md

---

# 1. REGRA ABSOLUTA

NÃO reinicie o projeto.
NÃO crie outro projeto.
NÃO transforme o ReiAnix em uma nova arquitetura sem necessidade.
NÃO reverta os Prompts anteriores.
NÃO apague funcionalidades que já funcionam.
NÃO faça alterações cosméticas para esconder bugs.
NÃO altere testes apenas para fazê-los passar.
NÃO declare um problema resolvido sem evidência.

Agora o objetivo é pegar as causas CONFIRMADAS e os problemas REPRODUZIDOS no Prompt 42 e corrigi-los diretamente no código.

---

# 2. PRIMEIRO PASSO

Antes de alterar qualquer arquivo:

1. Ler integralmente o Prompt 42.
2. Ler o relatório e todas as evidências produzidas pelo Prompt 42.
3. Conferir o estado atual do Git.
4. Conferir os commits posteriores ao Prompt 42.
5. Confirmar que as causas descritas ainda correspondem ao código atual.
6. Corrigir somente depois disso.

Se uma conclusão do Prompt 42 estiver marcada como hipótese, NÃO tratá-la como fato.

---

# 3. OBJETIVOS

Corrigir, sem alterar o escopo do aplicativo:

1. fechamento inesperado do player;
2. lifecycle incorreto do player;
3. Next;
4. Previous;
5. handoff e transitions;
6. callbacks stale;
7. botão Atualizar;
8. Pull-to-refresh;
9. refresh duplicado;
10. poster sendo substituído por episode thumbnail;
11. artwork stale;
12. resultados antigos sobrescrevendo resultados novos;
13. excesso de page.update;
14. gargalos comprovados de performance.

Preservar:

- SQLite;
- scanner;
- SAF;
- MediaStore;
- storage;
- biblioteca;
- Details;
- progress/resume;
- navigation;
- system bars;
- artwork;
- player;
- build;
- Actions;
- Releases.

NÃO iniciar AniList.
NÃO adicionar funcionalidades novas.

---

# 4. CLASSIFICAÇÃO DAS CAUSAS

Para cada problema do Prompt 42:

CONFIRMADO:
Corrigir diretamente.

PROVÁVEL:
Só corrigir se a alteração for segura, local e compatível, ou obter evidência adicional mínima.

HIPÓTESE:
Não fazer alteração estrutural baseada somente nisso.

NÃO DETERMINADO:
Não inventar solução. Implementar apenas a instrumentação necessária e documentar a dependência de teste físico.

---

# 5. PLAYER — CORREÇÃO PRINCIPAL

O player não pode fechar sozinho.

Um erro Media3 não deve automaticamente executar finish() ou finishAndRemoveTask().

Toda chamada de finish() deve ser classificada.

As categorias mínimas são:

USER_BACK
USER_BUTTON
ANDROID_BACK
ERROR_PANEL_BACK
VALID_PLAYER_TRANSITION
STALE_HANDOFF
INVALID_HANDOFF
PLAYER_ERROR
ACTIVITY_LIFECYCLE
SYSTEM_TASK
PROCESS_DEATH
UNKNOWN

Não remover finish() legítimos. Porém qualquer fechamento causado por callback stale, race, handoff antigo, erro de mídia ou lifecycle interpretado incorretamente deve ser corrigido.

---

# 6. PLAYER ERROR

Quando Media3 gerar PlaybackException:

1. preservar a Activity;
2. registrar o erro completo;
3. preservar diagnóstico;
4. apresentar estado de erro apropriado;
5. permitir saída manual;
6. impedir fechamento automático indevido;
7. não reiniciar infinitamente.

Registrar, quando disponível:

- errorCode;
- errorCodeName;
- message;
- cause;
- cause class;
- cause chain;
- media URI;
- media item;
- player state;
- renderer;
- MIME;
- codec.

Não substituir o erro real por uma mensagem genérica sem preservar a causa.

---

# 7. MEDIA3

Usar a versão atual do projeto, salvo evidência concreta no Prompt 42 de que uma versão específica corrige o problema encontrado.

Não atualizar Media3 apenas porque existe versão mais nova.

Se atualização for necessária:

1. relacionar a atualização à evidência;
2. consultar release notes/issues oficiais;
3. atualizar de forma controlada;
4. atualizar testes;
5. compilar;
6. testar runtime.

---

# 8. URI E MEDIA SOURCE

Se o Prompt 42 identificou problema de URI, corrigir a origem.

Verificar:

- file://;
- content://;
- SAF;
- MediaStore;
- path absoluto;
- permissão;
- FileDescriptor;
- MIME;
- seek;
- leitura real pelo processo Android.

Não converter URI somente para fazer um teste passar.

---

# 9. SURFACE

Se o Prompt 42 comprovar problema na Surface atual, corrigir de forma controlada.

Se a evidência favorecer SurfaceView em vez de TextureView, fazer a troca somente nos pontos necessários e preservar:

- PlayerView;
- controles;
- fullscreen;
- system bars;
- lifecycle;
- transições.

Se não houver evidência suficiente, não transformar uma hipótese em alteração permanente.

---

# 10. LIFECYCLE

Auditar e corrigir:

onCreate
onStart
onResume
onPause
onStop
onDestroy

Um onPause/onStop/onDestroy inesperado deve produzir diagnóstico.

Não interpretar qualquer callback como pedido de saída.

---

# 11. IDENTIDADE DA SESSÃO

Toda Activity do player deve permanecer vinculada à sessão correta.

Validar:

- playerSessionId;
- activityInstanceId;
- requestId;
- originRequestId;
- transitionGeneration.

Callback de sessão antiga deve ser ignorado.

Ignorar callback antigo NÃO pode destruir a Activity atual.

---

# 12. NEXT E PREVIOUS

Implementar Next e Previous como transições explícitas e simétricas.

Fluxo esperado:

REQUEST
→ VALIDATE CURRENT SESSION
→ VALIDATE TARGET
→ CREATE TRANSITION
→ CREATE TARGET REQUEST
→ DISPATCH TARGET
→ VALIDATE HANDOFF
→ ACTIVATE TARGET
→ RETIRE OLD INSTANCE

Não usar uma sequência frágil de finish antigo seguido de abertura sem validação.

---

# 13. HANDOFF

Validar obrigatoriamente:

- originRequestId;
- targetRequestId;
- playerSessionId;
- originPlayerSessionId;
- originTransitionGeneration;
- target/current transition generation;
- transition direction;
- activityInstanceId;
- lifecycle state;
- current active request.

Se houver inconsistência:

1. rejeitar como stale/invalid;
2. registrar motivo;
3. não destruir a Activity válida;
4. não matar a sessão atual;
5. não interferir no player atual.

---

# 14. TRANSITION GENERATION

Usar generation monotônica.

Exemplo conceitual:

G10 → G11 → G12

Resposta de G10 chegando durante G12 deve ser ignorada.

Ela não pode:

- trocar episódio;
- fechar player;
- substituir sessão;
- atualizar Details;
- sobrescrever estado atual.

---

# 15. TESTES DE TRANSIÇÃO

Validar:

Next
Next
Next

Next
Previous
Next

Next
Back

Next
Next
Back

Previous
Previous
Previous

Previous
Next
Previous

Também testar taps rápidos.

Não pode haver:

- player duplicado;
- Activity órfã;
- callback cruzado;
- transição duplicada;
- sessão antiga controlando a sessão atual.

---

# 16. AUTOPLAY

Autoplay deve usar a mesma máquina de transição de Next.

Não criar terceiro mecanismo de handoff.

A diferença pode ser apenas a origem do comando.

---

# 17. PROGRESS

Preservar progress/resume.

Uma sessão encerrada não pode salvar progresso depois de uma sessão mais nova.

Validar:

- episode identity;
- playerSessionId;
- event ordering;
- timestamp monotônico;
- generation.

Não permitir que Next/Previous salve progresso no episódio errado.

---

# 18. REFRESH — UMA ÚNICA AUTORIDADE

Todas as formas de refresh devem convergir para uma única operação equivalente a:

request_home_refresh(source)

Fontes:

- button;
- pull;
- retry;
- system.

Nenhuma dessas fontes deve iniciar diretamente um scan independente.

---

# 19. REFRESH STATE MACHINE

Usar estado explícito:

IDLE
REQUESTED
RUNNING
CATALOG_UPDATING
UI_COMMIT
SUCCESS
ERROR
CANCELLED

Uma operação já em RUNNING não deve iniciar outro scan idêntico.

---

# 20. DUPLICAÇÃO DE REFRESH

Testar:

button
button
button

pull
pull
pull

button
pull
button
pull

Durante uma operação ativa deve existir uma única operação efetiva.

Se uma segunda intenção precisar ser preservada, coalescer corretamente em vez de iniciar concorrência desnecessária.

---

# 21. FINALIZAÇÃO DO REFRESH

O refresh só deve publicar SUCCESS quando as condições reais de conclusão estiverem satisfeitas.

Não declarar sucesso apenas porque:

- scan iniciou;
- callback parcial chegou;
- UI foi atualizada.

Preservar a garantia de scan terminal + database atualizado quando essa for a condição correta da arquitetura.

---

# 22. ERRO DE REFRESH

Em erro:

- registrar exceção;
- limpar estado ativo;
- liberar recursos;
- permitir novo refresh;
- não deixar active=True permanentemente;
- não bloquear a Home.

---

# 23. PULL-TO-REFRESH

Corrigir usando o contrato real da versão instalada do Flet.

Não usar eventos fictícios.

A documentação do OnScrollEvent deve ser considerada:

https://flet.dev/docs/types/onscrollevent/

Eventos documentados incluem UPDATE, USER e OVERSCROLL e a implementação deve trabalhar com os dados realmente fornecidos pela versão usada.

Se o código atual depender de START/END que não fazem parte do contrato real, remover essa dependência.

---

# 24. FLUXO DO PULL

O comportamento esperado é:

scroll no topo
→ overscroll
→ acumular deslocamento
→ threshold
→ indicador
→ conclusão do gesto
→ request_home_refresh("pull")
→ scan
→ database
→ UI
→ SUCCESS

Não disparar refresh em scroll normal ou em overscroll abaixo do threshold.

---

# 25. BOTÃO ATUALIZAR

O botão deve chamar a mesma autoridade:

request_home_refresh("button")

Não duplicar lógica de scan.

---

# 26. ARTWORK — REGRA ABSOLUTA

Manter:

poster != episode_thumbnail

Uma thumbnail de episódio nunca pode virar poster do anime.

Isso inclui caminhos diretos e indiretos.

---

# 27. CORRIGIR update_thumbnail_in_place()

A função deve atualizar somente o episódio relacionado à thumbnail.

Ela NÃO pode:

- alterar anime.meta["cover_cache"] para thumbnail;
- alterar cover do anime;
- alterar poster binding;
- colocar thumbnail_path em holder de poster;
- registrar thumbnail como poster.

Se a thumbnail estiver sendo exibida numa lista de episódios, atualizar somente aquele item.

---

# 28. CORRIGIR register_generated_thumbnail()

O resultado de VideoThumbnailExtractor deve permanecer como:

artwork_type = episode_thumbnail

e associado ao media_identity correto.

Não criar registro de poster usando a thumbnail.

Não usar fallback persistente que transforme frame de vídeo em poster.

---

# 29. POSTER RESOLVER

Consolidar uma única resolução de poster.

Fontes válidas:

- poster local;
- poster manual;
- poster remoto;
- cache legítimo de poster.

Fontes inválidas:

- episode thumbnail;
- frame de vídeo;
- thumbnail de outro episódio.

Home e Details devem respeitar a mesma regra.

---

# 30. ARTWORK TOKEN

Toda operação assíncrona de artwork deve ter identidade suficiente para validar:

- entity;
- entity_id;
- artwork_type;
- generation;
- request_token;
- source.

Ao terminar, comparar com o token atual.

Se estiver stale:

não aplicar.

Registrar:

STALE_ARTWORK_IGNORED

---

# 31. ORDERING DE ARTWORK

Se A e B forem solicitados e B terminar antes:

B deve permanecer.

Quando A terminar depois:

A deve ser descartado.

Não permitir que uma resposta antiga faça a UI voltar para uma imagem anterior.

---

# 32. CACHE

Não destruir o cache existente para esconder o bug.

Corrigir:

- chave;
- tipo;
- identidade;
- generation;
- invalidation;
- validação.

Poster e episode thumbnail não podem compartilhar identidade lógica de cache.

---

# 33. THUMBNAIL CACHE

A chave deve distinguir, quando relevante:

- URI;
- media identity;
- modified time;
- tamanho/resolução;
- artwork type.

Não reutilizar thumbnail como poster.

---

# 34. UI E PERFORMANCE

Preservar as otimizações anteriores.

Não voltar para page.update() global a cada imagem.

Preferir:

- holder.update();
- batch;
- coalescing;
- atualizações locais.

Se várias imagens terminarem juntas, agrupar atualizações quando seguro.

Não usar sleep para “dar tempo para a UI”.

---

# 35. CONCORRÊNCIA

Auditar somente os pontos que o Prompt 42 relacionou ao problema.

Não criar workers adicionais indiscriminadamente.

Preservar os limites atuais de:

- artwork;
- thumbnail;
- mailbox;
- progress;
- scanner.

Se houver saturação comprovada, corrigir backpressure.

---

# 36. SQLITE

Não mudar schema sem necessidade.

Preservar library, artwork e progress.

Corrigir apenas races comprovadas.

---

# 37. SCANNER

Não modificar scanner somente porque existe lag.

Só alterar se a evidência mostrar que scanner está causando diretamente:

- player failure;
- refresh duplication;
- artwork corruption;
- UI starvation.

---

# 38. TESTES PYTHON

Criar/atualizar testes para:

### Refresh
- button;
- pull;
- duplicate;
- concurrent;
- error;
- recovery.

### Artwork
- poster isolation;
- episode thumbnail isolation;
- stale result;
- generation;
- ordering;
- cache.

### Player contracts
- session;
- request;
- generation;
- handoff;
- stale callback.

---

# 39. TESTES KOTLIN

Cobrir:

- valid handoff;
- invalid handoff;
- stale generation;
- stale request;
- stale activity;
- Next;
- Previous;
- autoplay;
- player error;
- finish reason;
- lifecycle.

---

# 40. REGRESSÃO

Não remover testes existentes.

Executar:

pytest

Gradle

testes Android disponíveis.

Se um teste antigo estiver incompatível com uma mudança correta, atualizar o teste somente quando a mudança estiver comprovada.

Nunca alterar teste apenas para mascarar bug.

---

# 41. BUILD

Executar o build oficial.

Confirmar:

- APK;
- manifest;
- target SDK;
- ABI;
- Python payload;
- Android host;
- permissões;
- assinatura;
- integridade.

Não alterar workflow sem necessidade.

---

# 42. TESTE REAL DO APK

Se houver aparelho disponível, instalar e testar.

## PLAYER

1. Home.
2. Anime.
3. Details.
4. Episódio.
5. Player.
6. First frame.
7. 15–30 segundos.
8. confirmar ausência de fechamento inesperado.

## NEXT

1. Player.
2. Next.
3. First frame.
4. reprodução.

## PREVIOUS

1. Next.
2. Previous.
3. First frame.

## AUTOPLAY

Testar.

## BACK

Testar.

---

# 43. REFRESH REAL

Testar no APK:

1. botão Atualizar;
2. esperar conclusão;
3. botão novamente;
4. pull abaixo do threshold;
5. pull acima;
6. pull durante refresh;
7. botão durante refresh;
8. verificar estado final.

---

# 44. ARTWORK REAL

Testar:

1. abrir Home;
2. esperar capas;
3. esperar thumbnails;
4. abrir Details;
5. voltar;
6. atualizar;
7. observar novamente.

Nenhuma episode thumbnail pode aparecer como poster.

---

# 45. LOGCAT PÓS-CORREÇÃO

Reproduzir o mesmo cenário que falhava antes.

Capturar novamente:

- Activity lifecycle;
- Media3;
- Surface;
- decoder;
- finish reason;
- handoff;
- stale callbacks;
- refresh;
- artwork.

Comparar ANTES x DEPOIS.

---

# 46. FIRST UNEXPECTED EVENT

Para qualquer bug ainda existente, localizar o primeiro evento inesperado.

Exemplo:

esperado:
Activity → player → READY → FIRST_FRAME

real:
Activity → player → BUFFERING → onStop

O foco deve ser descobrir por que onStop aconteceu.

Não aplicar patch somente no último sintoma.

---

# 47. ROOT CAUSE

Exemplo:

Se:
stale handoff → finish()

a correção deve tratar o stale handoff e a regra de fechamento.

Não apenas trocar finish() por return.

Se:
episode thumbnail → poster

a correção deve ser feita na origem do tipo/binding/cache/resolver.

Não apenas esconder a imagem na UI.

---

# 48. PROIBIÇÕES

É proibido:

- usar sleep para mascarar race;
- adicionar retry infinito;
- engolir exceções;
- usar catch vazio;
- usar || true em testes;
- aumentar timeout sem justificativa;
- apagar testes;
- desabilitar artwork;
- desabilitar scanner;
- desabilitar refresh;
- desabilitar Next/Previous;
- desabilitar autoplay;
- remover progress;
- remover logs necessários para diagnóstico.

---

# 49. GIT

Manter commits semanticamente claros quando possível.

Exemplos:

fix: stabilize player lifecycle
fix: harden player handoff
fix: unify home refresh state
fix: isolate episode thumbnails from posters
test: add runtime regression contracts

Não misturar mudanças sem relação.

---

# 50. RELATÓRIO FINAL

Produzir:

## CAUSAS CORRIGIDAS

| Problema | Causa | Correção | Evidência |
|---|---|---|---|
| Player | ... | ... | ... |
| Next | ... | ... | ... |
| Previous | ... | ... | ... |
| Refresh | ... | ... | ... |
| Pull | ... | ... | ... |
| Artwork | ... | ... | ... |

## ARQUIVOS

### Adicionados
### Modificados
### Removidos

Se não houver remoções:

Nenhum arquivo removido.

## TESTES

Informar exatamente:

- pytest;
- Kotlin;
- Gradle;
- instrumented;
- APK;
- runtime.

## COMMITS

Informar SHA e mensagem.

---

# 51. STATUS REAL

Para cada problema usar somente uma destas categorias:

RESOLVIDO E VALIDADO

CORRIGIDO NO CÓDIGO, RUNTIME NÃO VALIDADO

AINDA NÃO RESOLVIDO

NÃO COMPROVADO

Não usar “provavelmente resolvido” como conclusão.

---

# 52. DEFINIÇÃO DE PRONTO

Esta etapa está concluída quando as causas confirmadas do Prompt 42 estiverem corrigidas, os testes de regressão existirem e o APK estiver pronto para certificação.

A etapa seguinte será dedicada à:

TESTE REAL
→ REGRESSÃO
→ PERFORMANCE
→ CERTIFICAÇÃO

Não adicionar funcionalidades novas.

---

# 53. REGRA FINAL

A sequência obrigatória é:

REPRODUÇÃO
↓
EVIDÊNCIA
↓
CAUSA RAIZ
↓
CORREÇÃO
↓
TESTE
↓
APK
↓
REPRODUÇÃO NOVAMENTE
↓
CONFIRMAÇÃO

Se não houver aparelho disponível, declarar explicitamente que o runtime não foi validado.

Não inventar resultados.

Não declarar sucesso sem evidência.

Trabalhe diretamente no repositório e implemente as correções.
