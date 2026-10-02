# PROMPT 2 — VALIDAÇÃO FORENSE PÓS-CORREÇÃO DO CRASH DO PLAYER

## Repositório
https://github.com/reinansantos9090-debug/ReiAnix

## Estado inicial obrigatório

A correção do Prompt 1 já foi incorporada à main no commit:

6c3f682f07fd1fdad6adda014b4b5251c5169cc7

A correção aplicada no Prompt 1:
- durante o reuse do player, faz pause;
- desanexa PlayerView do ExoPlayer;
- substitui o MediaItem;
- reanexa o PlayerView;
- continua o prepare;
- mantém as proteções de geração/session/listeners/cancelamento/single-flight existentes.

Arquivos alterados no Prompt 1:
- android/app/src/main/kotlin/com/reiflix/reiflix_local/NativePlayerActivity.kt
- tests/test_prompt13_native_player_lifecycle.py

O Prompt 1 encontrou uma condição concreta de ownership entre PlayerView/TextureView e a troca de MediaItem, mas NÃO comprovou em runtime que essa era o FATAL EXCEPTION original.

Portanto, este Prompt 2 NÃO deve partir da premissa de que o crash foi definitivamente eliminado.

# OBJETIVO

Fazer uma validação forense pós-correção, procurando evidências de que:
1. a correção do Prompt 1 está correta;
2. não introduziu regressões;
3. não existe uma segunda condição de corrida no mesmo fluxo;
4. não existem callbacks, watchdogs, listeners, preparações ou lifecycle paths que ainda possam atingir o player/surface da geração errada;
5. o build/testes/CI possam ser realmente comprovados;
6. se houver ambiente Android disponível ao agente, o fluxo real seja validado;
7. se não houver runtime Android, deixar isso explicitamente registrado sem inventar validação.

A prioridade é investigar e provar, não alterar código por alterar.

# REGRA PRINCIPAL

## NÃO FAZER CORREÇÕES AUTOMATICAMENTE

Neste Prompt 2, o agente deve primeiro fazer uma auditoria pós-correção completa.

Só alterar código se encontrar:
- um bug concreto;
- uma corrida concreta;
- uma inconsistência de ownership;
- uma regressão introduzida pelo Prompt 1;
- ou uma condição comprovadamente capaz de invalidar a segurança da transição.

Não fazer refatoração preventiva, limpeza estética ou mudanças arquiteturais especulativas.

Se o código estiver correto, NÃO alterar o código apenas para “melhorar”.

# 1. AUDITORIA DO COMMIT DO PROMPT 1

Comece comparando o commit 6c3f682f07fd1fdad6adda014b4b5251c5169cc7 com o commit imediatamente anterior.

Confirme:
- exatamente quais arquivos foram alterados;
- sequência detach → setMediaItem → reattach;
- se PlayerView.player = null realmente ocorre antes da troca;
- se o reattach ocorre depois da troca;
- se existe algum caminho de erro entre detach e reattach que deixe o PlayerView permanentemente desanexado;
- se player.prepare() acontece somente depois da sequência;
- se playWhenReady continua sendo aplicado corretamente;
- se seek/resume continua correto;
- se os listeners continuam associados à geração correta;
- se a correção funciona tanto para autoplay quanto para Next manual;
- se prepareCurrentMedia() possui múltiplos caminhos que podem trocar MediaItem e algum deles ficou sem a proteção.

Não assumir que existe apenas um caminho de troca de MediaItem.

# 2. AUDITORIA COMPLETA DE OWNERSHIP DO PLAYER

Mapear todas as atribuições de:
- playerView.player
- player
- player.release()
- player.setMediaItem(...)
- player.prepare()
- player.play()
- player.pause()
- player.stop()
- listeners adicionados/removidos;
- callbacks associados ao player;
- Surface/TextureView;
- lifecycle da Activity.

Criar uma tabela interna do fluxo:

EVENTO | GERAÇÃO | PLAYER | PLAYER VIEW | SURFACE | SESSÃO | AÇÃO

Verificar especialmente:
- Activity criada;
- Activity reutilizada;
- onNewIntent;
- Next;
- Previous;
- autoplay;
- onStop;
- onPause;
- onResume;
- onDestroy;
- mudança de configuração;
- PiP se aplicável;
- saída normal;
- erro de reprodução;
- cancelamento de preparação;
- timeout;
- player_exited.

Objetivo: não permitir que duas gerações tenham ownership simultâneo do mesmo player/surface.

# 3. AUDITORIA DE PREPARAÇÃO ASSÍNCRONA

Investigar completamente:
- pendingPreparation;
- cancelamento;
- executor/worker;
- handler.post;
- isCurrentPreparation(...);
- playerGeneration;
- transitionGeneration;
- playerSessionId;
- URI atual;
- requestId.

Para cada callback assíncrono, responder:
1. Qual geração criou?
2. Qual sessão criou?
3. Qual episódio/URI criou?
4. O que acontece se chegar depois de uma nova transição?
5. O callback consegue tocar no player?
6. O callback consegue tocar no PlayerView?
7. O callback consegue disparar prepare?
8. O callback consegue chamar release/finish?
9. Existe fence explícita?

Qualquer callback que possa tocar no player sem fence deve ser tratado como suspeito.

# 4. AUDITORIA DE NEXT/AUTOPLAY

Mapear exatamente:

STATE_ENDED
→ requestEpisode()
→ NativePlayerRequest
→ MainActivity
→ openPlayer()
→ SINGLE_TOP/REORDER_TO_FRONT
→ onNewIntent()
→ prepareCurrentMedia()
→ novo MediaItem
→ prepare()
→ READY
→ primeira frame.

Verificar:
- se Next automático e manual usam exatamente o mesmo contrato;
- se existe alguma diferença perigosa entre os dois;
- se dois Next podem coexistir;
- se Next pode acontecer enquanto prepareCurrentMedia() ainda está em andamento;
- se Previous pode acontecer durante esse intervalo;
- se um request antigo pode ser aceito pelo MainActivity;
- se player_exited pode invalidar a sessão correta no meio da transição;
- se watchdog antigo pode cancelar a nova transição.

# 5. AUDITORIA DE PREVIOUS

Mesmo que o crash observado tenha ocorrido no Next, verificar:
- Previous durante reprodução;
- Previous durante preparação;
- Previous logo após Next;
- Previous após reuse;
- Previous com callback atrasado do episódio anterior.

Não alterar Previous se estiver correto.

# 6. AUDITORIA DE PLAYER EXIT

Investigar:
- finishPlayer();
- reportPlayerExit();
- notePlayerExit();
- player_exited;
- onDestroy();
- isFinishing;
- suppressExitEvent;
- isChangingConfigurations;
- invalidação de playerSession;
- activePlayerRequestId;
- activePlayerActivityInstanceId.

Objetivo:
Um player_exited antigo NÃO pode invalidar a sessão nova.
Um onDestroy antigo NÃO pode limpar o estado do player novo.
Um callback atrasado NÃO pode fazer MainActivity voltar para Details ou reconstruir a tela de forma indevida durante a transição.

# 7. AUDITORIA DE MEDIA3 / TEXTUREVIEW / SURFACE

Investigar especificamente:
- PlayerView com surface_type = texture_view;
- lifecycle do TextureView;
- criação/destruição da Surface;
- troca de MediaItem;
- renderer;
- decoder;
- MediaCodec;
- detach/reattach;
- release;
- Activity reuse.

Pesquisar documentação oficial atual do Android/Media3 e issues públicas relevantes quando necessário.

Separar claramente:
FATO DOCUMENTADO
vs
INFERÊNCIA
vs
HIPÓTESE.

Não afirmar que uma issue externa é a causa do crash sem evidência no código/runtime.

Verificar se a solução do Prompt 1 segue um ownership/lifecycle suportado pelo Media3.

# 8. VERIFICAR POSSÍVEIS CAMINHOS DE CRASH NÃO CAPTURADOS POR Player.Listener

Procurar:
- exceções lançadas fora do callback de Player.Listener;
- chamadas Kotlin potencialmente fatais;
- check(...);
- require(...);
- error(...);
- !!;
- acesso a objetos destruídos;
- lifecycle race;
- Surface inválida;
- player já liberado;
- callbacks após destroy;
- MediaCodec/Surface;
- Handler callbacks atrasados;
- executor callbacks;
- concorrência entre Main Thread e worker.

Não transformar toda ocorrência de !! em bug automaticamente. Demonstrar o caminho concreto.

# 9. AUDITORIA DOS TESTES

Verificar se os testes atuais realmente cobrem:
- criação única do ExoPlayer;
- release;
- detach/reattach;
- listener generation;
- preparação stale;
- Next;
- Previous;
- autoplay;
- reuse;
- lifecycle;
- first frame;
- player_exited;
- watchdog;
- cancelamento;
- sessão;
- transitionGeneration.

Identificar testes que são somente análise textual/estática e diferenciá-los de testes comportamentais.

Não remover testes existentes.

Se faltar uma regressão essencial e houver uma forma coerente de testá-la na arquitetura atual, adicionar o teste.

Não criar testes falsos que apenas procurem strings para afirmar comportamento runtime.

# 10. EXECUTAR VALIDAÇÕES REAIS

Quando o ambiente permitir, executar:
- suíte Python completa;
- testes específicos do player;
- compileall;
- git diff --check;
- build APK;
- verificações do host Android;
- verificações de manifesto/DEX;
- workflow CI, quando disponível.

Se houver acesso ao GitHub Actions, verificar a execução associada ao commit atual.

IMPORTANTE:

Não escrever “PASS” se somente houve inspeção estática.

Classificar cada item como:
- EXECUTADO — PASSOU
- EXECUTADO — FALHOU
- NÃO EXECUTADO
- VALIDADO ESTATICAMENTE
- NÃO DISPONÍVEL

# 11. RUNTIME ANDROID

Se houver dispositivo/emulador e capacidade real de executar o APK, reproduzir:

A → reprodução
→ fim
→ Próximo/autoplay
→ B
→ primeira frame
→ continuar reproduzindo
→ repetir a transição.

Também testar:
- Next manual;
- Next rápido;
- Previous;
- Next → Previous;
- retorno ao Details;
- reabrir player;
- progresso.

Se não houver Android runtime disponível:

RUNTIME ANDROID: NÃO VALIDADO.

Não inventar resultado.

# 12. LOGCAT / CRASH FORENSE

Se houver acesso a logs/bugreport/logcat fornecidos pelo ambiente, procurar:
- FATAL EXCEPTION;
- AndroidRuntime;
- MediaCodec;
- Surface;
- TextureView;
- ExoPlayer;
- Media3;
- native crash;
- SIGSEGV;
- SIGABRT;
- IllegalStateException;
- DeadObjectException;
- BufferQueue;
- CodecException.

Se não houver logs, não afirmar que o crash original foi identificado definitivamente.

# 13. CRITÉRIO PARA NOVA CORREÇÃO

Só modificar o código se houver evidência concreta.

Se encontrar um problema:
1. explicar o caminho;
2. explicar a condição;
3. explicar por que pode causar crash/regressão;
4. fazer a menor alteração possível;
5. adicionar teste;
6. executar validações;
7. revisar diff.

Se não encontrar problema:

NÃO alterar o código.

Nesse caso, produzir um relatório de auditoria dizendo que o estado pós-Prompt 1 foi considerado estruturalmente consistente, mas runtime permanece não comprovado caso não exista ambiente Android.

# 14. NÃO FAZER

Não:
- resetar a main;
- reverter o Prompt 1 sem evidência;
- reescrever NativePlayerActivity;
- trocar toda a arquitetura do player;
- atualizar Media3 apenas por tentativa;
- remover TextureView sem justificativa;
- desativar autoplay;
- desativar Next;
- desativar Previous;
- eliminar reuse apenas para evitar o problema;
- colocar sleeps;
- aumentar timeouts;
- mascarar exceptions;
- remover testes;
- declarar runtime PASS sem executar;
- declarar APK PASS sem build;
- declarar CI PASS sem execução comprovada.

# 15. ENTREGA FINAL OBRIGATÓRIA

Produzir relatório final contendo:

## A. Estado do Prompt 1
- o que foi confirmado;
- o que não foi confirmado.

## B. Auditoria de ownership
- player;
- PlayerView;
- Surface;
- session;
- generation.

## C. Auditoria de concorrência
- preparação;
- callbacks;
- watchdog;
- Next;
- Previous;
- player_exited.

## D. Evidências
Separar:
- fatos;
- evidências de código;
- documentação externa;
- inferências;
- hipóteses.

## E. Alterações
Se houver:
- arquivos modificados;
- arquivos adicionados;
- arquivos removidos;
- motivo de cada mudança.

Se não houver:
“Nenhuma alteração adicional necessária.”

## F. Testes
Para cada teste:
- executado ou não;
- resultado;
- tipo de validação.

## G. Build
- executado ou não;
- resultado;
- APK gerado ou não.

## H. CI
- workflow;
- commit;
- execução;
- resultado.

## I. Runtime
- validado ou não;
- cenário reproduzido;
- resultado.

## J. Conclusão

Usar exatamente uma destas classificações:

1. CORRIGIDO E VALIDADO EM RUNTIME
2. CORREÇÃO ESTRUTURAL VALIDADA, RUNTIME PENDENTE
3. PROBLEMA AINDA PRESENTE — NOVA CORREÇÃO NECESSÁRIA
4. EVIDÊNCIA INSUFICIENTE — NÃO É POSSÍVEL CONCLUIR

Não usar “resolvido definitivamente” sem evidência runtime.

## Regra final

Este Prompt 2 é de auditoria e validação pós-correção.

A prioridade é descobrir se o estado atual realmente está seguro.

Não fazer mudanças apenas para produzir um diff.

Preservar todo o ReiAnix existente.
