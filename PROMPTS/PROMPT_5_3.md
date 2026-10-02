
# PROMPT 5.3 — CORREÇÃO DA SEMÂNTICA DO CONTINUAR + CERTIFICAÇÃO INTEGRADA DO PROBLEMA 5

## Repositório
https://github.com/reinansantos9090-debug/ReiAnix

## Contexto

Terceira e última etapa do Problema 5.

O PROMPT 5.1 trata persistência/recovery.
O PROMPT 5.2 trata Continue Watching para múltiplos episódios.

Agora corrigir a semântica da tela Details e certificar o fluxo completo.

Foi observado um estado visual em que Details pode mostrar algo equivalente a:

CONTINUAR
Temporada 1 • Episódio 1
0% assistido

Isso ocorre quando a lógica de "episódio atual/próximo" é confundida com "episódio realmente em andamento".

## OBJETIVO

Diferenciar corretamente:
- CONTINUAR;
- PRÓXIMO EPISÓDIO;
- ASSISTIR;
- REASSISTIR, se já existir;
- episódio em progresso;
- episódio concluído.

Depois, certificar o Problema 5 inteiro sem adicionar funcionalidades novas.

## 1. DEFINIÇÕES

CONTINUAR:
somente quando há episódio realmente iniciado e ainda não concluído segundo o contrato de consumo existente.

PRÓXIMO EPISÓDIO:
quando não há retomada real, mas existe episódio não iniciado.

ASSISTIR:
episódio sem progresso.

CONCLUÍDO:
não tratar como Continue.

Não inventar novas regras de completion.

## 2. AUDITAR DETAILS

Inspecionar:
- views/details_view.py;
- current_episode;
- continue/resume;
- progress;
- watched;
- consumption_state;
- botão principal;
- seção CONTINUAR;
- lista de episódios.

Mapear:
SQLite → LibraryStore → service → Details → botão → player.

## 3. CORRIGIR FALSO CONTINUAR

Se progress=0 e watched=false:
não mostrar CONTINUAR/0% como se fosse retomada.

Se progress>0 e watched=false:
mostrar retomada real.

Se watched=true:
não mostrar como retomada.

Current Episode pode continuar decidindo o próximo episódio, mas não deve ser usado como prova de que existe progresso.

## 4. PRESERVAR RESUME

Ao clicar em CONTINUAR:
Details → player → episode_id correto → progress correto → seek após READY.

Não começar do zero.

Não alterar o mecanismo de resume sem necessidade.

## 5. CERTIFICAÇÃO REAL

### Cenário 1
E01 parcial → sair → reabrir → E01 aparece como retomável.

### Cenário 2
E01 10%, E02 20%, E03 30%, E04 40%, E05 50%
→ fechar/reabrir
→ episódios continuam registrados conforme limite.

### Cenário 3
E01 concluído, E02 30%
→ E01 não aparece como Continue; E02 aparece.

### Cenário 4
E01=0, E02=0
→ nenhum falso Continue.

### Cenário 5
E01/E02/E03 do mesmo anime possuem progressos
→ podem aparecer independentemente.

### Cenário 6
arquivo de episódio com progresso é removido
→ não deve aparecer como retomável disponível.

## 6. CERTIFICAÇÃO DO FLUXO COMPLETO

Details/Home
→ abrir episódio
→ NativePlayerActivity
→ reprodução
→ player_progress/player_paused
→ NativeMailbox
→ main.py
→ LibraryStore.save_progress
→ SQLite
→ reinicialização
→ Continue Watching
→ Details
→ resume
→ posição correta.

Esse fluxo precisa funcionar como uma cadeia.

## 7. RACE CONDITIONS

Verificar:

Evento 50% seguido de evento atrasado 30% → permanece 50%.

Sessão A 20% seguida de sessão B 70% e evento A atrasado → permanece 70%.

Mesmo evento replayado duas vezes → resultado idempotente.

Evento persistido antes do restart → recuperado após restart.

## 8. MÚLTIPLOS EPISÓDIOS

Com:
A/E01 10%
A/E02 20%
A/E03 30%
B/E01 40%
B/E02 50%

a projeção deve representar episódios individuais conforme timestamps e limite.

Não reduzir automaticamente para um episódio por anime.

## 9. DETAILS

Sem progresso:
botão principal não deve se chamar Continuar episódio.

Com progresso:
botão deve apontar para episódio correto.

Concluído:
não usar como retomada.

Próximo episódio:
pode ser calculado por current_episode, mas não confundido com Continue.

## 10. PLAYER

Não reescrever a arquitetura do player.

Verificar:
- episode_id correto;
- progress correto;
- resume após READY;
- session válida;
- Next/Previous;
- autoplay;
- player exit;
- lifecycle.

Se 5.1/5.2 introduzirem regressão, corrigir somente o necessário.

## 11. PERFORMANCE

Não introduzir:
- N+1 queries;
- leitura repetida do banco por card;
- polling agressivo;
- rebuild global;
- chamadas duplicadas ao player.

## 12. TESTES

Executar/atualizar:
- progress;
- LibraryStore;
- Continue Watching;
- Details;
- player resume;
- mailbox replay;
- session fencing;
- lifecycle;
- player consumption cycle.

Adicionar contrato de integração se a arquitetura permitir.

Não criar teste artificial que não represente o fluxo real.

## 13. BUILD E CI

Executar:
- testes Python;
- compileall;
- git diff --check;
- build APK;
- Android tests;
- CI.

Verificar o commit realmente executado.

Classificar:
EXECUTADO — PASSOU
EXECUTADO — FALHOU
VALIDADO ESTATICAMENTE
NÃO EXECUTADO
NÃO DISPONÍVEL

## 14. RUNTIME ANDROID

Se houver ambiente real:
1. abrir E01;
2. assistir parcialmente;
3. sair;
4. reabrir;
5. verificar Continue;
6. abrir e verificar seek;
7. repetir E02–E05;
8. fechar/reabrir;
9. verificar múltiplos episódios;
10. concluir um episódio;
11. verificar remoção de Continue;
12. verificar próximo episódio;
13. Next/Previous;
14. autoplay;
15. saída do player;
16. retorno ao app.

Se não houver:
RUNTIME ANDROID: NÃO VALIDADO

Não inventar resultado.

## 15. NÃO FAZER

Não:
- criar novas funcionalidades;
- alterar AniList;
- alterar scanner;
- alterar Media3;
- reescrever player;
- apagar progressos;
- recriar SQLite;
- remover session fencing;
- esconder problema apenas na UI;
- usar sleep;
- aumentar timeout;
- mascarar erro;
- remover testes.

## 16. PESQUISA EXTERNA

Quando necessário para lifecycle/persistência, consultar documentação oficial Android:

https://developer.android.com/reference/android/app/Activity
https://developer.android.com/guide/components/activities/process-lifecycle
https://developer.android.com/topic/performance/vitals/anr

Fontes externas servem para esclarecer comportamento da plataforma. A causa do ReiAnix deve ser demonstrada pelo código/testes/runtime.

## 17. ENTREGA FINAL

Relatório obrigatório:

1. Problema original.
2. Causa.
3. Persistência antes/depois.
4. Continue Watching antes/depois.
5. Semântica de Details antes/depois.
6. Alterações por arquivo.
7. Testes e resultados.
8. Build.
9. CI.
10. Runtime.
11. Regressões verificadas:
   - Next;
   - Previous;
   - autoplay;
   - resume;
   - player exit;
   - lifecycle;
   - Home;
   - Details.
12. Diff:
   - adicionados;
   - modificados;
   - removidos;
   - o que já existia;
   - o que não pôde ser implementado.

Conclusão usando exatamente:
1. CORRIGIDO E VALIDADO EM RUNTIME
2. CORREÇÃO ESTRUTURAL VALIDADA, RUNTIME PENDENTE
3. PROBLEMA AINDA PRESENTE — NOVA CORREÇÃO NECESSÁRIA
4. EVIDÊNCIA INSUFICIENTE — NÃO É POSSÍVEL CONCLUIR

Não declarar "definitivamente resolvido" sem validação suficiente.
