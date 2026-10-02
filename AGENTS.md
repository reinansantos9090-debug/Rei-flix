# AGENTS.md — ReiAnix

## Objetivo
Este é um projeto existente e em estabilização. Trabalhe sobre o código atual do ReiAnix. Não reinicie, recrie ou substitua o projeto por uma implementação nova.

## Regras obrigatórias de preservação
- Preserve todas as funcionalidades existentes que já funcionam.
- Não remova arquivos, classes, funções, testes, proteções, integrações ou fluxos apenas porque parecem antigos, redundantes ou não utilizados.
- Antes de remover ou alterar algo, verifique referências, call sites, dependências, fluxo Python/Flet ↔ Kotlin/Android, testes e comportamento em runtime.
- Se houver dúvida sobre a necessidade de um código existente, NÃO remova.
- Não faça refatorações amplas ou mudanças arquiteturais fora do escopo da tarefa.
- Prefira mudanças mínimas, locais, reversíveis e compatíveis com a arquitetura existente.
- Não transforme uma correção de bug em uma nova funcionalidade.
- Não remova testes existentes para fazer a suíte passar.
- Não desative validações, tratamento de erros, concorrência, lifecycle, cache, armazenamento, player ou proteções existentes sem evidência técnica de que são incorretos e sem preservar o comportamento necessário.

## Fluxos críticos
Trate como áreas de alto risco:
- seleção e persistência de pasta/permissão;
- SAF, MediaStore e acesso ao armazenamento;
- ScanCoordinator e descoberta/importação de vídeos;
- SQLite, migrações e persistência;
- biblioteca, detalhes e navegação;
- reprodução local com Media3/Kotlin;
- Next/Previous e autoplay;
- progresso de reprodução;
- comunicação Python ↔ Kotlin/NativeMailbox;
- thumbnails, artwork e metadata;
- AniList e tradução/cache;
- lifecycle, Back, PiP e barras do sistema;
- concorrência, asyncio, callbacks assíncronos e prevenção de eventos duplicados/stale.

## Execução segura
- Primeiro entenda o código existente e o contexto da alteração.
- Altere somente o necessário para cumprir a tarefa.
- Mantenha compatibilidade com os fluxos já existentes.
- Não invente APIs, resultados de testes ou comportamento de runtime.
- Diferencie claramente análise estática, testes realmente executados, build executado e validação em dispositivo/emulador.
- Se uma validação não puder ser executada, informe isso em vez de afirmar que passou.

## Validação
Após alterações:
1. Revise o diff completo.
2. Confira todos os arquivos modificados.
3. Execute os testes relevantes.
4. Execute build/compilação quando aplicável.
5. Verifique regressões nos fluxos diretamente afetados.
6. Procure alterações acidentais fora do escopo.
7. Remova código temporário, debug e artefatos de teste antes de finalizar.

## Regra de remoção
Se a solução parecer exigir remover uma funcionalidade existente, pare e procure uma solução compatível primeiro. Não remova a funcionalidade sem evidência clara e sem verificar todos os consumidores.

## Git
- Não reescreva histórico.
- Não faça reset/checkout destrutivo.
- Não force push.
- Não altere commits anteriores para esconder mudanças.
- Preserve o estado atual do repositório e produza mudanças rastreáveis.

## Prioridade
A prioridade é: estabilidade e preservação do ReiAnix existente > correção precisa do problema solicitado > limpeza/refatoração.

Quando houver conflito entre "simplificar o código" e "preservar comportamento existente", preserve o comportamento existente.

## Tarefa pendente — Correção definitiva do crash do player durante Next/Autoplay

> **Instrução para o agente:** execute esta tarefa diretamente no repositório atual. Não trate o projeto como novo, não reinicie a arquitetura e não faça apenas recomendações. Preserve tudo que já funciona e faça as alterações necessárias no código, testes e integrações.

### Contexto

Repositório: https://github.com/reinansantos9090-debug/ReiAnix

O ReiAnix é um app Android pessoal para reprodução de vídeos locais, com Flet/Python, Kotlin nativo, Media3/ExoPlayer, SQLite e comunicação Python ↔ Android por bridge/mailbox.

Foi observado o seguinte problema no player:

1. Um episódio está reproduzindo normalmente.
2. Aparece o estado/mensagem “Próximo…”.
3. A NativePlayerActivity desaparece e o app retorna para Details.
4. Aproximadamente 1–2 segundos depois, o Android informa que “ReiAnix Local apresenta falhas contínuas”.

Isso deve ser tratado como possível **crash real do processo**, e não simplesmente como um finish() normal da Activity.

A instrumentação normal de Player.Listener não registrou um erro Media3 correspondente (player.last_error = null / player.recent_errors = []), portanto não assuma que o problema seja capturado por onPlayerError.

### Objetivo

Descobrir e corrigir a causa técnica do crash durante a transição de episódios, especialmente no fluxo:

**fim do episódio → autoplay/Next → transição → reutilização da NativePlayerActivity → troca do MediaItem/player → primeira frame do próximo episódio**.

A correção deve ser estrutural e baseada no estado real do player. Não mascarar o problema.

### Arquivos/áreas que devem ser investigados

Analise integralmente os fluxos relacionados, incluindo pelo menos:

- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt
- android/app/src/main/kotlin/com/reiflix/reiflix_local/MainActivity.kt
- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerRequest.kt
- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativeMailbox.kt
- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativeRequestState.kt
- core/android_bridge.py
- main.py
- android/app/src/main/res/layout/native_player_view.xml
- android/app/src/main/AndroidManifest.xml
- testes de lifecycle/playback/transition/Media3/forensic existentes
- histórico Git relevante de player reuse, Next, Previous, watchdog, lifecycle e Media3.

Mapeie explicitamente o fluxo:

**Python → android_bridge → MainActivity → NativePlayerRequest → NativePlayerActivity → ExoPlayer/Media3 → PlayerView → TextureView/Surface**

E o retorno/transição:

**STATE_ENDED → autoplay → requestEpisode → request/session/generation → MainActivity → singleTop/REORDER_TO_FRONT → onNewIntent → reutilização da Activity/player → novo episódio**.

### Pontos críticos obrigatórios

Audite cuidadosamente:

- reutilização da mesma NativePlayerActivity;
- singleTop e REORDER_TO_FRONT;
- playerSessionId;
- requestId/origin request;
- transitionGeneration e gerações do player;
- callbacks antigos chegando depois de uma nova transição;
- listeners antigos e substituição de listeners;
- troca de MediaItem;
- prepare(), playWhenReady, seek e estado do player;
- lifecycle onNewIntent, onPause, onStop, onDestroy;
- PlayerView.player = null;
- player.release();
- lifecycle da TextureView/Surface;
- renderer/decoder/MediaCodec do Media3;
- transição automática e botão Next manual;
- Previous durante ou logo após uma transição;
- watchdogs/timeouts de transição;
- cancelamento de transições;
- eventos player_exited;
- invalidação da sessão do player;
- MainActivity ao receber saída do player;
- atualização/rebuild da tela Details após player_exited;
- bridge Python e seus timeouts/cancelamentos;
- persistência de progresso durante a transição;
- tratamento de erros Media3 e possibilidade de crash nativo que não passa por Player.Listener.

### Hipótese técnica a investigar

Não aceite esta hipótese como prova; valide-a contra o código e o histórico.

Uma possibilidade forte é uma condição de corrida entre **reutilização da Activity/player para o próximo episódio** e o ciclo de vida do **renderer/decoder/Surface/TextureView**, permitindo que callbacks, recursos ou operações da geração anterior ainda atuem enquanto o Media3 prepara o novo item ou enquanto o player está sendo desmontado/religado.

Isso poderia explicar um crash nativo/MediaCodec/Surface que não aparece como Player.Listener.onPlayerError.

Investigue também referências conhecidas do Media3/Android relacionadas a troca de MediaItem, TextureView, Surface e lifecycle. Não conclua que apenas atualizar Media3 resolve o problema sem evidência.

### Modelo de estado desejado

Se a implementação atual não garantir isso, corrija-a sem reescrever o projeto inteiro:

- uma única fonte de verdade para sessão atual, episódio atual, request atual, geração atual do player, geração da transição e direção;
- toda operação assíncrona relevante deve estar associada à geração/sessão correta;
- callbacks de gerações antigas devem ser ignorados/cancelados de forma determinística;
- uma transição anterior deve ficar explicitamente inválida/cancelada antes de uma nova;
- o lifecycle do player deve ser determinístico;
- a superfície deve permanecer válida enquanto o player a utiliza;
- release() não pode ocorrer enquanto uma operação válida da geração atual ainda depende daquele player;
- reutilização da Activity só deve ocorrer quando o estado anterior estiver seguro para receber o próximo episódio.

Não introduza uma segunda fonte de verdade que entre em conflito com os contratos já existentes.

### O que NÃO fazer

Não considere como solução:

- simplesmente colocar try/catch em volta do crash;
- ignorar exceções;
- aumentar timeouts para esconder a corrida;
- adicionar sleep()/delay arbitrário;
- desativar autoplay;
- desativar Next;
- desativar Previous;
- desativar reutilização sem investigar o lifecycle;
- simplesmente dar finish() na Activity;
- adicionar retries cegos;
- suprimir callbacks sem corrigir sua geração/ownership;
- remover testes existentes;
- mascarar o erro para impedir que apareça;
- fazer uma grande reescrita arquitetural sem necessidade.

Se for necessário alterar a estratégia de reutilização, a alteração deve preservar o comportamento funcional e ser justificada pelo lifecycle correto.

### Testes/regressões obrigatórios

Crie ou atualize testes para cobrir, conforme a arquitetura existente:

- episódio termina → autoplay → Next;
- botão Next manual;
- múltiplos Next rápidos;
- Next seguido de Previous;
- callback antigo do episódio A chegando depois que B já está ativo;
- timeout/watchdog de A chegando depois que B já está ativo;
- reutilização da Activity A → B;
- onStop durante uma transição;
- onDestroy seguido de callback atrasado;
- persistência do progresso de A antes de B;
- Next → primeira frame de B → confirmação/commit da nova sessão;
- Previous;
- eventos player_exited antigos/stale;
- invalidação/cancelamento de transições;
- proteção contra dupla execução da mesma transição.

Preserve e execute os testes existentes de player/lifecycle/Media3/forensic, incluindo os contratos já presentes no projeto.

### Validação final

Depois das alterações:

1. Revise o diff completo.
2. Verifique todos os arquivos alterados.
3. Execute os testes Python relevantes e a suíte apropriada.
4. Execute compileall quando aplicável.
5. Execute git diff --check.
6. Execute o build do APK quando o ambiente permitir.
7. Verifique o host Android/DEX conforme os contratos existentes.
8. Confirme que não houve alterações acidentais em funcionalidades fora do escopo.
9. Remova debug temporário e código de diagnóstico que não seja parte da solução final.

Não afirme que um build, teste ou validação em dispositivo foi executado se não tiver sido realmente executado.

### Entrega obrigatória do agente

Ao terminar, informe:

- causa técnica encontrada;
- evidências no código/histórico que sustentam a causa;
- correção aplicada e por que ela elimina a condição de corrida/crash;
- testes adicionados/alterados;
- testes realmente executados e resultado;
- build realmente executado e resultado, se disponível;
- arquivos/pastas adicionados;
- arquivos/pastas modificados;
- arquivos/pastas removidos;
- qualquer parte que não pôde ser implementada/verificada;
- possíveis riscos residuais.

**Regra final:** esta é uma correção de estabilidade. Não adicionar novas funcionalidades, AniList, novos recursos do player ou mudanças não relacionadas. O objetivo é fazer o player completar a transição de episódios sem crash, preservando o ReiAnix existente.
