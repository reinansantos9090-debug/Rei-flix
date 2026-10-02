# PROMPT 3 — CORREÇÃO DEFINITIVA DO CONFLITO MAINACTIVITY(singleTask) × NATIVEPLAYERACTIVITY × THUMBNAILS × NEXT/PREVIOUS

## Repositório

https://github.com/reinansantos9090-debug/ReiAnix

## Contexto obrigatório

O ReiAnix é um aplicativo Android pessoal composto por Flet/Python + código nativo Kotlin + Media3/ExoPlayer.

O problema investigado ocorre em dois cenários relacionados:

1. Enquanto a tela de detalhes ainda está gerando/baixando thumbnails dos episódios, o usuário entra em um episódio e o NativePlayerActivity pode desaparecer sozinho.
2. Dentro do player, ao pressionar **Próximo** ou **Anterior**, o player pode desaparecer/retornar para Details e, em seguida, o processo pode apresentar falha.

A investigação atual encontrou uma causa arquitetural concreta que precisa ser corrigida.

## CAUSA ARQUITETURAL IDENTIFICADA

O AndroidManifest atual registra a MainActivity como:

`android:launchMode="singleTask"`

e o protocolo `reiflix://native` é recebido pela MainActivity.

O fluxo atual usa esse protocolo não apenas para abrir a aplicação, mas também para operações internas, incluindo:

- `play`;
- `extract_thumbnail`;
- outros comandos nativos relacionados ao bridge.

Isso cria o seguinte problema:

```
MainActivity (singleTask)
        ↓
NativePlayerActivity
        ↓
player está no topo da task
```

Se, enquanto NativePlayerActivity está no topo, uma nova Intent `reiflix://native` chega para MainActivity:

```
Intent → MainActivity(singleTask)
        ↓
Android encontra MainActivity existente
        ↓
Activities acima dela são destruídas
        ↓
NativePlayerActivity.onDestroy()
        ↓
PlayerView detach
        ↓
ExoPlayer.release()
        ↓
player desaparece
```

Esse comportamento é compatível com o contrato documentado do Android para `singleTask`.

### Caminho identificado para thumbnails

```
Details
  ↓
thumbnail ainda não existe
  ↓
request_thumbnail
  ↓
core/android_bridge.py
  ↓
reiflix://native?action=extract_thumbnail
  ↓
MainActivity(singleTask)
  ↓
NativePlayerActivity acima da MainActivity é destruída
```

Isso explica a correlação observada no vídeo:

- thumbnails ainda estão sendo geradas → player pode fechar;
- todas as thumbnails terminam → novas Intents de thumbnail deixam de ocorrer → player permanece funcionando.

### Caminho identificado para Next/Previous

```
NativePlayerActivity
  ↓
requestEpisode()
  ↓
NativeMailbox
  ↓
Python main.py
  ↓
start_native_player()
  ↓
bridge.play()
  ↓
reiflix://native?action=play
  ↓
MainActivity(singleTask)
  ↓
NativePlayerActivity é destruída
```

Portanto, o problema de Next/Previous não deve ser tratado somente como um bug de Media3.

O problema fundamental é que uma operação interna de transição do player está usando um mecanismo de Intent que volta para a MainActivity `singleTask`, colocando a própria Activity do player em uma posição incompatível com o fluxo desejado.

## EVIDÊNCIA EXTERNA JÁ PESQUISADA

A documentação oficial do Android descreve que `singleTask` pode remover Activities acima da Activity existente e entregar a nova Intent através de `onNewIntent()`.

Referências relevantes para a auditoria:

- Android — Tasks and Back Stack:
  https://developer.android.com/guide/components/activities/tasks-and-back-stack
- Android — Intents and Intent Filters:
  https://developer.android.com/guide/components/intents-filters
- Android Media3 release/issues:
  https://developer.android.com/jetpack/androidx/releases/media3
- Media3 Issues:
  https://github.com/androidx/media/issues
- Stack Overflow — comportamento de singleTask:
  https://stackoverflow.com/questions/2417468/android-bug-in-launchmode-singletask-activity-stack-not-preserved

Também foram encontrados relatos públicos envolvendo Activity launch modes, deep links, `onNewIntent()`, TextureView/Media3 e troca de MediaItem.

IMPORTANTE:
essas fontes servem para confirmar o comportamento das plataformas e contextualizar riscos. Não atribuir automaticamente o crash a uma Issue externa sem evidência no código/runtime do ReiAnix.

---

# OBJETIVO PRINCIPAL

Corrigir definitivamente a arquitetura de comunicação para que:

1. operações de thumbnail NÃO possam destruir/rebaixar NativePlayerActivity;
2. Next NÃO precise voltar para MainActivity para trocar o episódio;
3. Previous NÃO precise voltar para MainActivity para trocar o episódio;
4. autoplay NÃO precise voltar para MainActivity para trocar o episódio;
5. uma transição do player permaneça dentro do ownership correto do NativePlayerActivity;
6. MainActivity continue funcionando como host principal da aplicação;
7. o comportamento de Back continue correto;
8. o estado de playerSessionId/requestId/transitionGeneration continue correto;
9. o fluxo Python → Kotlin continue funcionando;
10. o scanner, biblioteca, Details, thumbnails e demais funcionalidades existentes continuem funcionando;
11. a correção não seja um workaround de timing;
12. a correção elimine a possibilidade estrutural de uma operação interna do player derrubar a NativePlayerActivity por causa do `singleTask`.

---

# REGRA PRINCIPAL

## NÃO mascarar o problema

NÃO resolver com:

- `sleep()`;
- delays arbitrários;
- aumentar timeout;
- retry infinito;
- ignorar exceção;
- `try/catch` que engole crash;
- desabilitar thumbnails enquanto o player está aberto;
- pausar o thumbnail dispatcher;
- desabilitar Next;
- desabilitar Previous;
- desabilitar autoplay;
- remover a navegação;
- fechar/reabrir o player como workaround;
- trocar Media3 apenas por tentativa;
- mudar TextureView para outra superfície sem demonstrar necessidade;
- remover `singleTask` sem analisar o impacto global;
- criar uma segunda MainActivity sem necessidade;
- criar uma nova Activity a cada transição;
- criar múltiplas instâncias do player para esconder a condição de corrida.

A correção deve resolver o problema de **ownership e roteamento das operações internas**.

---

# 1. AUDITORIA DO ESTADO ATUAL

Antes de editar, inspecionar obrigatoriamente:

### Android

- `AndroidManifest.xml`
- `MainActivity.kt`
- `NativePlayerActivity.kt`
- `NativePlayerRequest.kt`
- `NativeRequestState.kt`
- `NativeMailbox.kt`
- `native_player_view.xml`

### Python

- `core/android_bridge.py`
- `main.py`
- código de Details
- código de thumbnails
- fila/dispatcher de thumbnails
- navegação de episódios
- player session
- transições Next/Previous
- autoplay
- mailbox/event loop

### Testes

Pesquisar especialmente:

- `test_prompt13_native_player_lifecycle.py`
- `test_prompt18_transition_hardening.py`
- `test_prompt23_next_transition.py`
- `test_prompt24_previous_transition.py`
- `test_prompt25_session_hardening.py`
- `test_prompt28_media3_errors.py`
- `test_prompt41_forensic.py`
- testes de thumbnails;
- testes do bridge;
- testes de lifecycle;
- testes de mailbox.

NÃO assumir que a implementação atual é exatamente igual aos prompts anteriores. O código da branch atual é a autoridade.

---

# 2. MAPEAR TODAS AS INTENTS INTERNAS

Encontrar todas as ocorrências de:

- `reiflix://native`
- `ACTION_VIEW`
- `UrlLauncher`
- `externalNonBrowserApplication`
- `action=play`
- `action=extract_thumbnail`
- demais `action=`
- `intent-filter`
- `onNewIntent()`
- `startActivity()`
- `startActivityForResult()`
- `PendingIntent`, se existir.

Produzir internamente uma tabela:

| Ação | Origem | Destino atual | Activity envolvida | Pode destruir Player? | Deve permanecer fora da task do Player? |
|---|---|---|---|---|---|
| play inicial | Python/Details | ... | ... | ... | ... |
| play de Next | Python | ... | ... | ... | ... |
| play de Previous | Python | ... | ... | ... | ... |
| autoplay | Python/native | ... | ... | ... | ... |
| extract_thumbnail | Python | ... | ... | ... | ... |

O objetivo é descobrir TODAS as operações que atualmente passam pela MainActivity.

---

# 3. DEFINIR O NOVO CONTRATO DE IPC

A arquitetura final deve separar claramente:

## A. Comandos que realmente precisam abrir/reabrir a UI

Exemplo:

- abrir player pela primeira vez;
- abrir player a partir de Details;
- entrada inicial externa, se existir.

Esses comandos podem utilizar o mecanismo de Activity.

## B. Comandos internos que NÃO devem voltar para MainActivity

Exemplo:

- troca de episódio;
- Next;
- Previous;
- autoplay;
- atualização interna do player;
- thumbnail extraction;
- operações nativas auxiliares.

Esses comandos devem utilizar um mecanismo que NÃO provoque a resolução de uma Intent para a MainActivity `singleTask` enquanto NativePlayerActivity estiver no topo.

---

# 4. ESCOLHER A SOLUÇÃO ARQUITETURAL MAIS SEGURA

O agente deve avaliar as opções disponíveis no código atual e escolher a de menor risco.

Possíveis soluções aceitáveis incluem, conforme a arquitetura existente:

### Opção A — comunicação direta com NativePlayerActivity

Se for possível encaminhar o comando diretamente para a Activity do player sem passar pela MainActivity:

- usar Intent explícita;
- preservar `singleTop`;
- usar `onNewIntent()`;
- manter a mesma instância do player;
- validar session/request/generation;
- não criar nova Activity.

### Opção B — canal interno dedicado

Criar um canal interno separado do deep-link `reiflix://native`, desde que seja apropriado para a arquitetura Android atual.

Pode ser:

- mailbox;
- IPC interno;
- broadcast interno adequadamente protegido;
- outro mecanismo já utilizado pelo projeto.

Não introduzir um mecanismo complexo se um mecanismo existente puder ser reutilizado com segurança.

### Opção C — separar thumbnail extraction do Activity routing

A extração de thumbnail NÃO deve exigir que MainActivity seja trazida para frente.

Se a implementação atual usa uma Activity apenas para executar a extração, avaliar mover a operação para:

- serviço interno;
- worker;
- executor nativo;
- componente sem UI;
- ou outro mecanismo apropriado ao projeto.

A solução deve respeitar o ciclo de vida e não criar vazamento.

### Opção D — comando Python → player via mailbox

Se a arquitetura atual de mailbox for adequada, avaliar:

```
NativePlayerActivity
   ↓
player_next_request
   ↓
Python resolve SQLite
   ↓
Python publica comando de troca
   ↓
NativePlayerActivity recebe comando
   ↓
valida request/session/generation
   ↓
troca MediaItem
```

Esse modelo é aceitável se puder ser implementado sem polling agressivo, sem race e sem quebrar o lifecycle.

---

# 5. CRITÉRIO OBRIGATÓRIO PARA A SOLUÇÃO

Independentemente da opção escolhida:

## Next/Previous NÃO podem mais depender de:

```
bridge.play()
→ reiflix://native
→ MainActivity(singleTask)
```

durante uma sessão em que NativePlayerActivity já está aberta.

O fluxo deve ser:

```
NativePlayerActivity
      ↓
Next/Previous
      ↓
Python resolve episódio
      ↓
comando interno dedicado
      ↓
NativePlayerActivity existente
      ↓
validação de sessão/generation
      ↓
troca de mídia
```

ou uma arquitetura equivalente que preserve a mesma propriedade:

> **a NativePlayerActivity existente continua sendo a dona do player durante a transição.**

---

# 6. CORRIGIR THUMBNAILS

O processamento de thumbnail deve ser completamente independente da existência de NativePlayerActivity.

Enquanto o player estiver aberto:

```
thumbnail A
thumbnail B
thumbnail C
thumbnail D
...
```

podem continuar sendo geradas normalmente.

Nenhuma dessas operações pode:

- lançar MainActivity para frente;
- destruir NativePlayerActivity;
- chamar `onNewIntent()` da MainActivity;
- invalidar playerSession;
- provocar `player_exited`;
- alterar a transição do player.

Também deve continuar sendo possível gerar thumbnails com o player fechado.

---

# 7. CORRIGIR NEXT

O Next deve funcionar assim:

```
Botão Next
 ↓
requestEpisode("next")
 ↓
uma única transição
 ↓
salva progresso
 ↓
Python recebe pedido
 ↓
SQLite resolve próximo episódio
 ↓
comando interno para player
 ↓
NativePlayerActivity valida:
   requestId
   playerSessionId
   transitionGeneration
   playerGeneration
 ↓
detach/reattach correto se necessário
 ↓
setMediaItem()
 ↓
prepare()
 ↓
seek/resume
 ↓
READY
 ↓
primeira frame
 ↓
playback
```

Nenhuma etapa pode trazer MainActivity para frente.

---

# 8. CORRIGIR PREVIOUS

O Previous deve possuir a mesma propriedade.

Verificar:

- Previous normal;
- Previous com player buffering;
- Previous durante preparação;
- Previous imediatamente após Next;
- Previous repetido;
- Previous com callback antigo;
- Previous quando não existe episódio anterior.

Nenhuma transição pode depender de MainActivity(singleTask) para alcançar o player existente.

---

# 9. CORRIGIR AUTOPLAY

Autoplay é tratado como transição interna do player.

Portanto:

```
STATE_ENDED
 ↓
resolve next
 ↓
transição interna
 ↓
NativePlayerActivity existente
```

Não:

```
STATE_ENDED
 ↓
bridge.play()
 ↓
MainActivity
 ↓
destroy NativePlayerActivity
```

Preservar:

- configuração de autoplay;
- progresso;
- posição inicial;
- navigation snapshot;
- session;
- generation;
- listeners;
- first frame diagnostics.

---

# 10. PRESERVAR A CORREÇÃO DO PROMPT 1

A correção do Prompt 1 NÃO deve ser removida automaticamente.

Commit de referência:

`6c3f682f07fd1fdad6adda014b4b5251c5169cc7`

A sequência:

```
pause
↓
PlayerView.player = null
↓
setMediaItem
↓
PlayerView.player = player
↓
prepare
```

deve continuar se ainda for necessária.

Porém, verificar se depois da correção do roteamento existe algum caminho que:

- execute a troca duas vezes;
- reanexe o PlayerView depois de a Activity ter sido destruída;
- execute callback de geração antiga;
- execute prepare para URI antiga.

Se houver, corrigir.

---

# 11. OWNERSHIP FORMAL

Estabelecer claramente:

## MainActivity

Responsável por:

- UI principal;
- Details;
- Biblioteca;
- navegação;
- scanner;
- permissões;
- estado geral da aplicação.

## NativePlayerActivity

Responsável por:

- ExoPlayer;
- PlayerView;
- Media3;
- superfície de vídeo;
- troca de mídia;
- Next/Previous;
- autoplay;
- progresso durante reprodução;
- lifecycle do player.

## Thumbnail subsystem

Responsável por:

- gerar thumbnails;
- salvar cache;
- atualizar catálogo;
- trabalhar independentemente do player.

Nenhum desses subsistemas deve destruir outro apenas porque uma operação interna foi disparada.

---

# 12. SESSION / GENERATION / REQUEST FENCING

Depois da nova arquitetura, revisar:

- `playerSessionId`
- `requestId`
- `originRequestId`
- `transitionGeneration`
- `playerGeneration`
- `activityInstanceId`

Garantir:

### Transição nova

Pode substituir a mídia atual.

### Transição antiga

Não pode tocar no player novo.

### player_exited antigo

Não pode invalidar sessão nova.

### Activity antiga

Não pode limpar estado da Activity nova.

### callback antigo

Não pode:

- setMediaItem;
- prepare;
- play;
- pause;
- attach PlayerView;
- detach PlayerView;
- release;
- finish.

---

# 13. NÃO USAR MAINACTIVITY COMO "ROTEADOR" DO PLAYER

Esse é um requisito crítico.

Se o código final continuar fazendo:

```
Next
→ bridge.play()
→ reiflix://native
→ MainActivity(singleTask)
```

a correção NÃO está concluída.

O mesmo vale para:

- Previous;
- autoplay;
- comandos equivalentes.

---

# 14. BACK NAVIGATION

Depois da correção, validar:

```
Details
 ↓
Player
 ↓
Back
 ↓
Details
```

e:

```
Player
 ↓
Next
 ↓
novo episódio
 ↓
Back
 ↓
Details
```

O Back não pode:

- criar MainActivity duplicada;
- perder Details;
- encerrar o processo;
- publicar player_exited incorreto;
- invalidar sessão errada.

---

# 15. THUMBNAIL CONCURRENCY

Criar explicitamente uma regressão para este cenário:

```
N thumbnails pendentes
        +
NativePlayerActivity aberta
        +
thumbnails continuam sendo processadas
```

Garantir estaticamente, e em runtime se possível, que:

- thumbnail extraction não inicia MainActivity;
- não destrói NativePlayerActivity;
- não chama `player.release()`;
- não chama `finishPlayer()`;
- não modifica playerSession;
- não interfere na transição.

---

# 16. TESTES OBRIGATÓRIOS

Adicionar/corrigir testes para cobrir pelo menos:

### Teste 1
`extract_thumbnail` não usa mais o caminho que destrói NativePlayerActivity.

### Teste 2
Next não chama `bridge.play()` através do deep-link destinado à MainActivity quando o player já está ativo.

### Teste 3
Previous também não chama esse caminho.

### Teste 4
Autoplay também não chama esse caminho.

### Teste 5
A NativePlayerActivity existente continua sendo a dona do player durante Next.

### Teste 6
Thumbnail extraction simultânea ao player não invalida session.

### Teste 7
player_exited antigo não invalida nova sessão.

### Teste 8
callback de geração antiga não modifica o player novo.

### Teste 9
Back continua funcionando.

### Teste 10
A correção do Prompt 1 continua protegendo a troca de MediaItem/PlayerView.

### IMPORTANTE

Testes devem verificar comportamento real da arquitetura sempre que possível.

Não criar testes que apenas procuram strings no código para fingir que runtime foi validado.

Testes estáticos podem existir como complemento, mas devem ser identificados como estáticos.

---

# 17. BUILD E VALIDAÇÃO

Executar, quando disponível:

- testes Python completos;
- testes Android/Kotlin;
- `compileall`;
- `git diff --check`;
- build APK;
- testes instrumentados, se disponíveis;
- CI GitHub Actions;
- inspeção do Manifest final.

Se houver Android runtime disponível:

### Cenário A — thumbnails

1. abrir Details;
2. deixar thumbnails pendentes;
3. entrar no episódio imediatamente;
4. manter thumbnails sendo processadas;
5. reproduzir;
6. aguardar thumbnails terminarem;
7. confirmar que o player nunca fecha.

### Cenário B — Next

1. abrir episódio;
2. pressionar Next;
3. aguardar novo vídeo;
4. confirmar reprodução;
5. repetir várias vezes.

### Cenário C — Previous

1. abrir episódio;
2. Next;
3. Previous;
4. repetir.

### Cenário D — concorrência

Enquanto thumbnails estão sendo geradas:

- abrir player;
- Next;
- Previous;
- autoplay.

### Cenário E — repetição

Executar várias transições:

```
A → B → C → B → A → B → C
```

e procurar:

- fechamento;
- tela de Details inesperada;
- crash;
- player parado;
- frame congelado;
- sessão inválida;
- callback stale.

Se não houver runtime Android:

`RUNTIME ANDROID: NÃO VALIDADO`

Não inventar PASS.

---

# 18. LOGS / CRASH

Se houver acesso a logs, procurar especialmente:

- `ActivityTaskManager`;
- `AndroidRuntime`;
- `FATAL EXCEPTION`;
- `NativePlayerActivity.onDestroy`;
- `PLAYER_SESSION_EXIT`;
- `PLAYER_ACTIVITY_INSTANCE_INACTIVE`;
- `PLAYER_FINISH_REQUEST`;
- `player_exited`;
- `MediaCodec`;
- `Surface`;
- `TextureView`;
- `ExoPlayer`;
- `Media3`.

A investigação deve conseguir distinguir:

### Fechamento provocado por lifecycle/task

de:

### Crash real do processo.

Não misturar os dois.

---

# 19. DOCUMENTAÇÃO E PESQUISA EXTERNA

Durante a implementação, pesquisar quando necessário:

- Android Developers;
- AndroidX Media3;
- GitHub Issues;
- GitHub Discussions;
- Stack Overflow;
- Google Issue Tracker;
- documentação do Flet/UrlLauncher;
- documentação Android de Tasks/Back Stack;
- documentação Android de Intents;
- comunidades técnicas relevantes.

Pesquisar especificamente:

- `singleTask onNewIntent activity above destroyed`;
- `Android deep link singleTask Activity stack`;
- `Media3 TextureView Activity lifecycle`;
- `ExoPlayer setMediaItem Activity reuse`;
- `Media3 PlayerView TextureView release`;
- `Android Activity task back stack player`.

Não usar um artigo de blog ou comentário de fórum como autoridade maior que a documentação oficial.

---

# 20. CRITÉRIO DE ACEITAÇÃO

A correção somente será considerada estruturalmente concluída se:

- [ ] thumbnail extraction não passar pela MainActivity(singleTask);
- [ ] Next não passar pela MainActivity(singleTask) para trocar mídia em player existente;
- [ ] Previous não passar pela MainActivity(singleTask);
- [ ] autoplay não passar pela MainActivity(singleTask);
- [ ] NativePlayerActivity permanecer dona do ExoPlayer durante transições;
- [ ] nenhuma thumbnail puder destruir NativePlayerActivity;
- [ ] playerSession continuar íntegra;
- [ ] transitionGeneration continuar íntegra;
- [ ] playerGeneration continuar íntegra;
- [ ] callbacks stale forem rejeitados;
- [ ] player_exited antigo não invalidar sessão nova;
- [ ] Back continuar correto;
- [ ] Prompt 1 continuar protegido;
- [ ] testes de regressão existirem;
- [ ] build/testes forem executados quando possível;
- [ ] runtime seja declarado explicitamente como validado ou não validado.

---

# 21. NÃO REFAZER O PROJETO

Não reiniciar o ReiAnix.

Não substituir a arquitetura inteira.

Não apagar funcionalidades existentes.

Não fazer reset da main.

Não remover histórico.

Não fazer force push.

Não alterar partes sem relação com o problema.

A prioridade é:

1. estabilidade;
2. preservação das funcionalidades existentes;
3. correção do conflito de ownership/roteamento;
4. testes;
5. mínima alteração necessária.

---

# 22. ENTREGA FINAL OBRIGATÓRIA

Ao terminar, apresentar:

## A. CAUSA CONFIRMADA

Explicar:

- qual Intent causava o conflito;
- qual Activity recebia;
- por que `singleTask` destruía o player;
- como thumbnails participavam;
- como Next/Previous participavam.

## B. SOLUÇÃO

Explicar o novo caminho:

```
Antes:
Player → Python → MainActivity(singleTask) → Player destruído

Depois:
Player → Python → canal interno/direto → NativePlayerActivity existente
```

ou representar a arquitetura equivalente implementada.

## C. ARQUIVOS

Informar:

### Adicionados
- arquivo
- finalidade

### Modificados
- arquivo
- mudança

### Removidos
- arquivo
- motivo

### Já existentes
Informar os arquivos que foram reutilizados sem criação.

### Não implementado
Informar qualquer parte que não pôde ser implementada e por quê.

## D. TESTES

Para cada teste:

- nome;
- executado ou não;
- PASS/FAIL;
- estático ou runtime.

## E. BUILD

Informar:

- executado;
- resultado;
- APK gerado;
- localização/nome do artefato, se disponível.

## F. CI

Informar:

- workflow;
- commit;
- execução;
- resultado.

## G. RUNTIME

Informar:

- disponível/não disponível;
- cenário executado;
- resultado.

## H. REGRESSÃO

Confirmar explicitamente:

- Details;
- thumbnails;
- player;
- Next;
- Previous;
- autoplay;
- progresso;
- Back;
- lifecycle;
- scanner/biblioteca.

## I. CONCLUSÃO

Usar exatamente uma classificação:

1. CORRIGIDO E VALIDADO EM RUNTIME
2. CORREÇÃO ESTRUTURAL VALIDADA, RUNTIME PENDENTE
3. PROBLEMA AINDA PRESENTE — NOVA CORREÇÃO NECESSÁRIA
4. EVIDÊNCIA INSUFICIENTE — NÃO É POSSÍVEL CONCLUIR

Nunca usar “resolvido definitivamente” sem validação de runtime.

---

# REGRA FINAL

Este Prompt 3 é de IMPLEMENTAÇÃO DA CORREÇÃO.

Diferentemente de um prompt apenas de auditoria, aqui o agente deve:

1. investigar o estado atual;
2. implementar a correção arquitetural;
3. criar/corrigir testes;
4. executar validações;
5. revisar o diff;
6. confirmar que nenhuma operação interna de player continua roteando pela MainActivity(singleTask) de forma capaz de destruir NativePlayerActivity.

O objetivo é eliminar a causa estrutural identificada, e não apenas reduzir a frequência do problema.

Preservar o ReiAnix existente.
