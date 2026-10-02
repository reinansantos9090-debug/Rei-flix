
# PROMPT 5.1 — CORREÇÃO DEFINITIVA DA PERSISTÊNCIA E RECUPERAÇÃO DO PROGRESSO

## Repositório
https://github.com/reinansantos9090-debug/ReiAnix

## Contexto obrigatório

Esta é uma etapa de estabilização do ReiAnix existente. NÃO reinicie o projeto, NÃO recrie a arquitetura e NÃO trate a tarefa como projeto novo. Preserve funcionalidades já existentes e faça a menor correção estrutural necessária.

Problema observado:

1. o usuário abre um episódio;
2. assiste parcialmente;
3. sai/fecha o aplicativo;
4. abre novamente;
5. o episódio deixa de aparecer corretamente como retomável;
6. quando vários episódios foram assistidos parcialmente, vários podem desaparecer da retomada.

O fluxo existente é:

NativePlayerActivity
→ player_progress / player_paused / player_completed
→ NativeMailbox
→ main.py
→ LibraryStore.save_progress()
→ SQLite
→ Continue Watching / Details

O código já possui persistência periódica, persistência em lifecycle, episode_id, timestamps e proteção contra eventos fora de ordem. NÃO remova essas proteções.

Há uma hipótese forte de que eventos persistentes válidos estejam sendo confundidos com callbacks de uma sessão de player viva. Confirme isso no código atual antes de alterar.

## OBJETIVO

Garantir que:

- progresso salvo antes da saída sobreviva à reinicialização;
- eventos duráveis possam ser recuperados sem exigir player ativo;
- evento antigo não sobrescreva estado novo;
- sessão antiga não sobrescreva sessão nova;
- episode_id/path continuem sendo validados;
- vários episódios mantenham progressos independentes;
- resume continue funcionando;
- Next/Previous/autoplay/lifecycle não sejam quebrados.

## REGRA PRINCIPAL

NÃO simplesmente remova session fencing.

Diferencie:

A) callback de controle de player vivo:
player ativo + sessão/request/generation compatíveis → aceitar.

B) evento de consumo persistente recuperado após restart:
não há player ativo + evento durável válido + episode_id/identidade/timestamp válidos → permitir replay seguro.

C) evento realmente stale:
identidade inválida, timestamp antigo, sessão incompatível com player vivo, request/generation antiga ou conflito de identidade → rejeitar.

A ausência de player ativo, sozinha, NÃO deve invalidar um evento persistente que já foi gravado e precisa sobreviver à reinicialização.

## 1. AUDITORIA OBRIGATÓRIA

Inspecionar diretamente a main atual:

### Android
- NativePlayerActivity.kt
- NativeMailbox.kt
- NativePlayerRequest.kt
- NativeRequestState.kt
- MainActivity.kt

### Python
- main.py
- core/android_bridge.py
- core/library_store.py
- core/library_service.py
- código Home/Details/Continue Watching

Pesquisar:
player_progress, player_paused, player_completed, player_exited,
session_id, playerSessionId, requestId, originRequestId,
transitionGeneration, playerGeneration, event_created_at,
last_played_at, save_progress, active_playback_session,
stale_session, stale, player_session_active.

Mapear evento criado → persistido → lido → validado → aplicado/rejeitado → SQLite.

## 2. ENCONTRAR A CAUSA REAL

Não assumir a hipótese.

Determine:

- onde o progresso é salvo;
- quando é salvo;
- se NativeMailbox é durável;
- como o evento é recuperado após restart;
- qual é o estado de sessão após restart;
- se main.py exige player ativo;
- se essa exigência descarta evento válido;
- se SQLite já contém o progresso e somente a projeção está errada;
- se algum reconciliation/cleanup apaga o progresso;
- se o problema é nativo, mailbox, dispatcher, SQLite ou projeção.

Separe causa comprovada, causa provável e hipótese.

## 3. CONTRATO DE EVENTOS DURÁVEIS

player_progress, player_paused e player_completed são eventos de consumo persistente. Devem carregar informação suficiente para replay seguro, preferencialmente:

- episode_id;
- identidade canônica do arquivo;
- session_id;
- event_created_at;
- position;
- duration;
- watched.

Eventos de controle como Next/Previous/handoff continuam sujeitos a fencing forte.

Não aceitar identidade por título quando episode_id canônico já existe.

## 4. CORREÇÃO

Implementar a menor alteração necessária para:

player ativo
→ evento normal
→ save_progress()

player não ativo
→ evento persistente recuperado
→ validação persistente
→ save_progress()

Mas manter:

sessão A ativa → sessão B ativa → evento atrasado A
→ NÃO sobrescrever B.

Não remover last_played_at/event_created_at ou mecanismos equivalentes sem evidência.

## 5. IDENTIDADE E ORDERING

Validar:

- episode_id existe;
- path/URI corresponde ao episode_id quando fornecido;
- URI/path é normalizado;
- duração/posição são finitas e válidas;
- posição não ultrapassa duração;
- evento mais antigo não sobrescreve evento mais novo.

Casos:

20% → 50% → evento atrasado de 20% → permanece 50%.

Sessão A 20% → sessão B 70% → evento atrasado A → permanece 70%.

## 6. REABERTURA

Criar/fortalecer testes:

### Um episódio
E01 → 20% → fecha → abre → E01 ainda retomável e posição preservada.

### Cinco episódios
E01 10%, E02 20%, E03 30%, E04 40%, E05 50%
→ fecha → abre → todos os progressos continuam no banco/projeção.

### Replay idempotente
Mesmo evento processado duas vezes → não duplica nem regrede estado.

### Evento antigo
Evento antigo chega depois → não sobrescreve.

### Identidade inválida
episode_id/path incompatíveis → rejeitar.

## 7. LIFECYCLE

Verificar onPause, onStop, onDestroy, Back, PiP, troca de Activity e encerramento do processo.

Não depender exclusivamente de onDestroy. A documentação Android deixa claro que o processo pode ser encerrado sem um onDestroy final; persistência precisa acontecer em pontos apropriados do lifecycle:

https://developer.android.com/reference/android/app/Activity

## 8. NÃO QUEBRAR O PLAYER

Não alterar Media3, ExoPlayer, PlayerView, TextureView, detach/reattach do Prompt 1 ou ownership do player sem necessidade.

Se for necessária alteração nativa, faça somente a mínima para garantir persistência antes da saída.

## 9. TESTES E VALIDAÇÃO

Executar quando disponível:
- testes Python;
- testes específicos de progress/mailbox/session;
- compileall;
- git diff --check;
- build Android;
- CI.

Classificar cada resultado:
- EXECUTADO — PASSOU
- EXECUTADO — FALHOU
- VALIDADO ESTATICAMENTE
- NÃO EXECUTADO
- NÃO DISPONÍVEL

Não declarar runtime validado sem runtime.

## 10. NÃO FAZER

Não:
- apagar progressos;
- recriar SQLite;
- remover session fencing;
- aceitar qualquer evento sem validação;
- desabilitar Continue Watching;
- usar sleep;
- aumentar timeout como solução;
- engolir exceções;
- remover testes;
- reescrever toda a camada de dados.

## 11. ENTREGA FINAL

Informar:
- causa exata;
- correção;
- fluxo persistente antes/depois;
- proteção contra stale/race;
- arquivos adicionados/modificados/removidos;
- testes;
- build;
- CI;
- runtime;
- o que não pôde ser validado.

Se runtime não existir:
RUNTIME ANDROID: NÃO VALIDADO

Conclusão usando exatamente:
1. CORRIGIDO E VALIDADO EM RUNTIME
2. CORREÇÃO ESTRUTURAL VALIDADA, RUNTIME PENDENTE
3. PROBLEMA AINDA PRESENTE — NOVA CORREÇÃO NECESSÁRIA
4. EVIDÊNCIA INSUFICIENTE — NÃO É POSSÍVEL CONCLUIR
