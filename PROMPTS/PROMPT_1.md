# PROMPT 1 — CORREÇÃO DEFINITIVA DO CRASH DO PLAYER DURANTE NEXT/AUTOPLAY E TRANSIÇÃO DE EPISÓDIOS

## Repositório
https://github.com/reinansantos9090-debug/ReiAnix

## Contexto
O ReiAnix é um aplicativo Android pessoal para reprodução de vídeos locais, com Flet/Python, Kotlin nativo, Media3/ExoPlayer, SQLite e comunicação Python ↔ Android por bridge/mailbox.

Problema observado:
1. Um episódio está reproduzindo normalmente.
2. Aparece “Próximo…”.
3. A NativePlayerActivity desaparece e o app retorna para Details.
4. Aproximadamente 1–2 segundos depois, o Android informa que “ReiAnix Local apresenta falhas contínuas”.

Trate isso como possível crash real do processo, não simplesmente como finish() normal da Activity.

A instrumentação normal de Player.Listener não registrou erro Media3 correspondente (player.last_error = null / player.recent_errors = []). Não assuma que o problema é capturado por onPlayerError.

## Objetivo
Descobrir e corrigir a causa técnica do crash durante a transição:

fim do episódio → autoplay/Next → transição → reutilização da NativePlayerActivity → troca do MediaItem/player → primeira frame do próximo episódio.

A correção deve ser estrutural e baseada no estado real do player. Não mascarar o problema.

## Áreas obrigatórias de investigação
- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt
- android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt
- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerRequest.kt
- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativeMailbox.kt
- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativeRequestState.kt
- core/android_bridge.py
- main.py
- android/app/src/main/res/layout/native_player_view.xml
- android/app/src/main/AndroidManifest.xml
- testes existentes de lifecycle/playback/transition/Media3/forensic
- histórico Git relacionado a player reuse, Next, Previous, watchdog, lifecycle e Media3.

Mapeie o fluxo Python → bridge → MainActivity → request → NativePlayerActivity → ExoPlayer/Media3 → PlayerView → TextureView/Surface.

Mapeie também STATE_ENDED → autoplay → requestEpisode → request/session/generation → MainActivity → singleTop/REORDER_TO_FRONT → onNewIntent → reutilização da Activity/player → novo episódio.

## Pontos críticos
Audite:
- reutilização da NativePlayerActivity;
- singleTop e REORDER_TO_FRONT;
- playerSessionId;
- requestId e origin request;
- transitionGeneration e gerações do player;
- callbacks antigos após nova transição;
- listeners antigos e substituição de listeners;
- troca de MediaItem;
- prepare(), playWhenReady, seek e estado do player;
- onNewIntent, onPause, onStop e onDestroy;
- PlayerView.player = null;
- player.release();
- lifecycle de TextureView/Surface;
- renderer/decoder/MediaCodec do Media3;
- autoplay, Next e Previous;
- watchdogs/timeouts;
- cancelamento de transições;
- player_exited;
- invalidação de sessão;
- MainActivity ao receber saída;
- atualização/rebuild de Details;
- bridge Python, timeouts e cancelamentos;
- persistência de progresso;
- possibilidade de crash nativo que não passe por Player.Listener.

## Hipótese técnica a investigar
Não aceite como prova. Valide no código e no histórico.

Uma possibilidade forte é uma condição de corrida entre a reutilização da Activity/player para o próximo episódio e o ciclo de vida do renderer/decoder/Surface/TextureView, permitindo que callbacks, recursos ou operações da geração anterior atuem enquanto o Media3 prepara o novo item ou enquanto o player é desmontado/religado.

Isso poderia explicar crash nativo/MediaCodec/Surface sem Player.Listener.onPlayerError.

Investigue também referências conhecidas do Media3/Android sobre troca de MediaItem, TextureView, Surface e lifecycle. Não conclua que apenas atualizar Media3 resolve.

## Modelo de estado desejado
Se necessário, corrija sem reescrever o projeto:
- uma única fonte de verdade para sessão, episódio, request, geração do player, geração da transição e direção;
- toda operação assíncrona relevante associada à geração/sessão correta;
- callbacks de gerações antigas ignorados/cancelados deterministicamente;
- transição anterior invalidada/cancelada antes de nova;
- lifecycle determinístico;
- Surface válida enquanto o player a utiliza;
- release() somente quando nenhuma operação válida da geração atual depender do player;
- reutilização da Activity somente quando o estado anterior estiver seguro.

Não introduza uma segunda fonte de verdade conflitante.

## NÃO fazer
Não usar como “solução”:
- try/catch para mascarar o crash;
- ignorar exceções;
- aumentar timeouts para esconder corrida;
- sleep/delay arbitrário;
- desativar autoplay, Next ou Previous;
- simplesmente desativar reutilização sem investigar;
- simplesmente finish() na Activity;
- retries cegos;
- suprimir callbacks sem corrigir geração/ownership;
- remover testes;
- grande reescrita arquitetural sem necessidade.

## Testes obrigatórios
Criar/atualizar testes para:
- fim → autoplay → Next;
- Next manual;
- múltiplos Next rápidos;
- Next → Previous;
- callback antigo A após B;
- timeout/watchdog A após B;
- reutilização Activity A → B;
- onStop durante transição;
- onDestroy + callback atrasado;
- progresso A antes de B;
- Next → primeira frame de B → confirmação da nova sessão;
- Previous;
- player_exited stale;
- invalidação/cancelamento;
- proteção contra dupla execução.

Preserve e execute os testes existentes de player/lifecycle/Media3/forensic.

## Validação final
- revisar diff completo;
- conferir todos os arquivos alterados;
- executar testes relevantes;
- executar compileall quando aplicável;
- executar git diff --check;
- executar build do APK quando possível;
- verificar host Android/DEX conforme contratos existentes;
- conferir alterações acidentais fora do escopo;
- remover debug temporário.

Não afirmar que algo foi executado se não foi realmente executado.

## Entrega do agente
Relatar:
- causa técnica encontrada;
- evidências no código/histórico;
- correção aplicada e por que elimina a condição de corrida/crash;
- testes adicionados/alterados;
- testes realmente executados e resultados;
- build realmente executado e resultado;
- arquivos/pastas adicionados;
- modificados;
- removidos;
- o que não pôde ser implementado/verificado;
- riscos residuais.

Regra final: somente correção de estabilidade. Não adicionar novas funcionalidades, AniList ou novos recursos do player. Preservar o ReiAnix existente.
