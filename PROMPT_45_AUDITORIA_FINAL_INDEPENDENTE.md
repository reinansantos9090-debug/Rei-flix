# PROMPT 45 — AUDITORIA FINAL INDEPENDENTE DO REIANIX

## REPOSITÓRIO OFICIAL

Trabalhe DIRETAMENTE no repositório:

https://github.com/reinansantos9090-debug/ReiAnix

Este prompt é a etapa final da sequência:

- PROMPT 42 → descobrir e provar as causas;
- PROMPT 43 → corrigir as causas comprovadas;
- PROMPT 44 → testar e certificar no APK;
- PROMPT 45 → auditar independentemente se a etapa realmente terminou.

---

# 1. OBJETIVO

Realizar uma auditoria final, independente e crítica do ReiAnix depois da execução dos Prompts 42, 43 e 44.

O objetivo NÃO é adicionar funcionalidades.

O objetivo é verificar se:

1. as causas encontradas foram realmente corrigidas;
2. os bugs observados no APK deixaram de ocorrer;
3. não foram introduzidas regressões;
4. não houve gambiarra para mascarar sintomas;
5. não existem retries infinitos, sleeps artificiais ou tratamentos que escondam erros;
6. as correções preservam as funcionalidades existentes;
7. o aplicativo está realmente pronto para considerar esta etapa encerrada.

A auditoria deve tentar encontrar motivos para NÃO considerar a etapa concluída.

Não assumir que os Prompts 43 e 44 estão corretos apenas porque foram executados.

---

# 2. REGRA ABSOLUTA

NÃO reiniciar o projeto.

NÃO criar uma nova arquitetura sem necessidade.

NÃO adicionar funcionalidades novas.

NÃO iniciar AniList.

NÃO alterar o escopo funcional do aplicativo.

NÃO desfazer correções válidas dos Prompts anteriores.

NÃO modificar testes apenas para produzir PASS.

NÃO considerar um problema resolvido apenas porque existe um teste estático para ele.

NÃO considerar código correto como equivalente a runtime correto.

NÃO inventar resultados de teste físico.

Se o aparelho não estiver disponível, declarar claramente:

RUNTIME NÃO VALIDADO.

---

# 3. PRIMEIRO PASSO — RECONSTRUIR O ESTADO REAL

Antes de qualquer conclusão:

1. verificar o branch atual;
2. verificar o commit atual;
3. verificar commits dos Prompts 42, 43 e 44;
4. verificar arquivos modificados;
5. verificar se existem alterações não commitadas;
6. ler os prompts;
7. ler os relatórios produzidos;
8. comparar as mudanças com o comportamento esperado;
9. verificar se alguma correção foi parcialmente revertida posteriormente.

Não confiar somente nos relatórios dos agentes.

A fonte de verdade deve ser:

CÓDIGO + TESTES + BUILD + APK + EVIDÊNCIA DE RUNTIME.

---

# 4. AUDITORIA INDEPENDENTE

Para cada problema original, responder:

- qual era o sintoma;
- qual causa foi identificada;
- qual correção foi aplicada;
- qual evidência comprova a correção;
- qual teste foi executado;
- se houve reprodução no APK;
- se existe risco residual.

Não aceitar respostas genéricas como:

"foi corrigido".

Exigir evidência.

---

# 5. PLAYER

Auditar novamente o lifecycle completo:

onCreate
onStart
onResume
onPause
onStop
onDestroy

Verificar se o player pode desaparecer inesperadamente.

Verificar todas as chamadas de:

- finish();
- finishAndRemoveTask();
- ActivityResult;
- callbacks de erro;
- callbacks de lifecycle;
- callbacks de transição.

Cada fechamento deve possuir uma razão identificável.

Categorias mínimas:

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

Se houver fechamento UNKNOWN em cenário reproduzível, a auditoria NÃO está concluída.

---

# 6. MEDIA3

Verificar:

- PlaybackException;
- errorCode;
- errorCodeName;
- media URI;
- MediaItem;
- renderer;
- codec;
- MIME;
- estado do player;
- causa raiz.

Um erro Media3 não pode resultar em fechamento automático indevido.

Confirmar que erros são diagnosticáveis e que a Activity continua viva quando deveria.

Não fazer upgrade de Media3 apenas por existir versão nova.

Se uma versão nova tiver sido usada, registrar:

- versão anterior;
- versão atual;
- motivo;
- evidência;
- resultado dos testes.

---

# 7. SURFACE E PRIMEIRO FRAME

Verificar o comportamento da Surface.

Se houver A/B entre TextureView e SurfaceView, registrar o resultado real.

Verificar:

- criação da Surface;
- attach ao PlayerView;
- detach;
- recreate;
- rotação/lifecycle, quando aplicável;
- primeiro frame;
- buffering;
- saída do player.

Não concluir que Surface é causa sem evidência.

---

# 8. NEXT / PREVIOUS

Auditar a máquina de transição completa.

Validar:

- sessão atual;
- request atual;
- request de origem;
- request alvo;
- playerSessionId;
- originPlayerSessionId;
- activityInstanceId;
- transitionGeneration;
- originTransitionGeneration;
- direção da transição;
- lifecycle.

Testar:

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

Não pode existir:

- Activity duplicada;
- Activity órfã;
- sessão antiga controlando sessão nova;
- callback stale alterando o player;
- transição duplicada;
- player fechando durante handoff.

---

# 9. AUTOPLAY

Verificar se autoplay utiliza a mesma máquina de transição de Next.

Não deve existir um segundo mecanismo paralelo que possa produzir estados incompatíveis.

Testar:

episódio → fim → próximo episódio → first frame → reprodução.

---

# 10. PROGRESS / RESUME

Verificar que:

- episódio correto recebe progresso;
- sessão antiga não sobrescreve sessão nova;
- callback stale é ignorado;
- progress não cruza entre episódios;
- Next/Previous não salva progresso no item errado;
- timestamps/orderings continuam consistentes.

Testar fechar e reabrir episódio.

---

# 11. REFRESH

Auditar a existência de uma única autoridade de refresh.

Todas as fontes devem convergir para a mesma operação:

request_home_refresh(source)

Fontes:

- botão;
- pull;
- retry;
- system, quando aplicável.

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

durante uma operação ativa.

Confirmar que não são iniciados scans concorrentes idênticos.

---

# 12. PULL-TO-REFRESH

Confirmar que a implementação utiliza o contrato real do Flet instalado.

Não aceitar dependência em eventos inexistentes.

Verificar:

- scroll normal;
- overscroll;
- threshold;
- conclusão do gesto;
- refresh;
- recuperação após erro.

Um scroll normal não deve disparar refresh.

Um overscroll abaixo do threshold não deve disparar refresh.

---

# 13. BOTÃO ATUALIZAR

Confirmar que o botão:

1. inicia a mesma autoridade do pull;
2. não duplica scan;
3. não cria estado paralelo;
4. recupera corretamente após erro;
5. pode ser usado novamente após SUCCESS ou ERROR.

---

# 14. ARTWORK

Auditar de forma independente a separação:

poster != episode_thumbnail

Uma thumbnail de episódio jamais pode:

- virar poster;
- alterar cover_cache de anime;
- entrar em poster binding;
- ser persistida como poster;
- substituir poster remoto/local;
- contaminar cache de poster.

Verificar especialmente:

- update_thumbnail_in_place();
- register_generated_thumbnail();
- ArtworkEngine;
- Home;
- Details;
- artwork bindings;
- cache;
- SQLite.

---

# 15. ARTWORK STALE

Criar/validar cenário:

A começa
B começa
B termina
A termina depois

Resultado obrigatório:

B permanece.

A deve ser descartado se estiver stale.

Verificar:

- entity;
- entity_id;
- artwork_type;
- generation;
- request_token;
- source.

Nenhum resultado antigo pode voltar a UI para estado anterior.

---

# 16. CACHE

Verificar que poster e episode_thumbnail não compartilham identidade lógica de cache.

Auditar:

- chave;
- tipo;
- URI;
- media identity;
- modified time;
- resolução;
- invalidação;
- seleção;
- persistência.

Não apagar cache simplesmente para esconder o problema.

---

# 17. UI / PERFORMANCE

Verificar as otimizações existentes sem reintroduzir:

- page.update() global desnecessário;
- rebuild completo;
- sleeps artificiais;
- polling excessivo;
- workers sem limite;
- filas sem backpressure.

Preferir atualizações locais e batching quando apropriado.

Não alterar performance apenas por opinião.

Qualquer mudança adicional deve estar ligada a evidência.

---

# 18. CONCORRÊNCIA

Procurar especificamente por:

- race conditions;
- callbacks stale;
- generation mismatch;
- duplicate requests;
- duplicate transitions;
- queue saturation;
- executor saturation;
- cancellation incorreta.

Não aumentar timeouts para esconder race.

Não adicionar retries infinitos.

Não adicionar workers indiscriminadamente.

---

# 19. SQLITE

Confirmar que as correções não quebraram:

- library;
- artwork;
- progress;
- watched state;
- resume.

Não alterar schema sem necessidade.

---

# 20. SCANNER / STORAGE

Confirmar que:

- SAF continua funcionando;
- MediaStore continua funcionando;
- storage continua funcionando;
- permissões permanecem;
- biblioteca continua sendo populada;
- refresh não corrompe o catálogo.

Não modificar scanner apenas por suspeita.

---

# 21. REGRESSÃO DE NAVEGAÇÃO

Testar:

Home
→ Biblioteca
→ Details
→ Player
→ Back

Também:

Home
→ Details
→ Player
→ Next
→ Previous
→ Back

Confirmar:

- navegação;
- system bars;
- estado da Home;
- Details;
- player;
- retorno para a tela correta.

---

# 22. TESTES AUTOMÁTICOS

Executar os testes relevantes.

No mínimo:

pytest

Gradle

testes Android/instrumented disponíveis.

Registrar exatamente:

- total;
- passed;
- failed;
- skipped;
- erros.

Não omitir falhas.

Não usar:

|| true

para mascarar falhas.

Não remover testes para obter PASS.

---

# 23. BUILD FINAL

Executar o build oficial.

Confirmar:

- APK gerado;
- manifest;
- applicationId;
- target SDK;
- min SDK;
- ABI;
- permissões;
- Python payload;
- Android host;
- assinatura;
- integridade;
- ausência de artefatos de desenvolvimento indevidos.

Se o workflow oficial possuir validações, verificar o resultado delas.

---

# 24. TESTE REAL DO APK

Se houver aparelho disponível:

1. instalar APK;
2. abrir;
3. selecionar pasta;
4. confirmar persistência da permissão;
5. localizar vídeos;
6. importar biblioteca;
7. abrir Details;
8. reproduzir;
9. esperar pelo menos 15–30 segundos;
10. testar Next;
11. testar Previous;
12. testar autoplay;
13. testar Back;
14. testar botão Atualizar;
15. testar Pull-to-refresh;
16. testar artwork;
17. repetir os cenários que anteriormente falhavam.

Não testar somente o caminho feliz.

---

# 25. EVIDÊNCIA DE RUNTIME

Quando possível coletar:

- Logcat;
- logs do player;
- lifecycle;
- transições;
- refresh;
- artwork;
- Perfetto/Profiler quando necessário.

O objetivo é descobrir o primeiro evento inesperado, não somente o último sintoma.

---

# 26. FIRST UNEXPECTED EVENT

Para cada falha residual:

1. reproduzir;
2. localizar o primeiro evento inesperado;
3. reconstruir a sequência;
4. identificar a causa;
5. classificar:

CONFIRMADO
PROVÁVEL
HIPÓTESE
NÃO DETERMINADO

Não considerar o último sintoma como causa automaticamente.

---

# 27. ANTI-GAMBIARRA

Procurar explicitamente por:

- sleep usado para mascarar race;
- timeout artificial;
- retry infinito;
- catch vazio;
- exceção engolida;
- condição que simplesmente desativa funcionalidade;
- teste enfraquecido;
- código morto para esconder falha;
- logs removidos;
- erro convertido em sucesso.

Se encontrar qualquer um desses casos, investigar e corrigir quando relacionado às etapas 42–44.

---

# 28. COMPARAÇÃO ANTES × DEPOIS

Comparar os sintomas originais com o estado atual.

Para cada bug:

| Problema | Antes | Depois | Evidência |
|---|---|---|---|
| Player fecha | ... | ... | ... |
| Next | ... | ... | ... |
| Previous | ... | ... | ... |
| Refresh | ... | ... | ... |
| Pull | ... | ... | ... |
| Capas | ... | ... | ... |
| Stale artwork | ... | ... | ... |
| Performance | ... | ... | ... |

Não preencher com suposições.

---

# 29. CLASSIFICAÇÃO FINAL

Para cada problema usar somente:

RESOLVIDO E VALIDADO

CORRIGIDO NO CÓDIGO, RUNTIME NÃO VALIDADO

AINDA NÃO RESOLVIDO

NÃO COMPROVADO

Não usar:

- provavelmente resolvido;
- deve estar resolvido;
- aparentemente resolvido.

---

# 30. CRITÉRIO DE ENCERRAMENTO

Só considerar esta etapa encerrada se:

1. as causas comprovadas estiverem corrigidas;
2. os testes relevantes estiverem passando;
3. o build estiver correto;
4. o APK estiver disponível;
5. os cenários críticos tiverem sido reproduzidos quando houver aparelho;
6. não houver regressões conhecidas;
7. não houver gambiarra;
8. não houver retry infinito;
9. nenhuma funcionalidade existente tiver sido quebrada;
10. as limitações de runtime estiverem explicitamente documentadas.

Se qualquer requisito crítico falhar, a auditoria deve declarar:

ETAPA NÃO CERTIFICADA.

---

# 31. SE ENCONTRAR UM PROBLEMA

Se encontrar um problema durante a auditoria:

1. determinar se é regressão;
2. determinar se é consequência direta dos Prompts 42–44;
3. corrigir somente se for necessário para estabilidade/regressão;
4. adicionar ou corrigir o teste correspondente;
5. executar novamente os testes afetados;
6. reconstruir o APK se necessário;
7. repetir a validação.

Não iniciar uma nova funcionalidade.

---

# 32. RELATÓRIO FINAL OBRIGATÓRIO

Produzir:

## 1. ESTADO DO REPOSITÓRIO

- branch;
- commit;
- alterações pendentes.

## 2. CAUSAS ORIGINAIS

Lista das causas encontradas no Prompt 42.

## 3. CORREÇÕES

O que os Prompts 43 e 44 realmente alteraram.

## 4. AUDITORIA INDEPENDENTE

O que foi confirmado e o que não foi.

## 5. TESTES

- Python;
- Kotlin;
- Gradle;
- Android;
- APK;
- runtime.

## 6. REGRESSÕES

Listar todas as encontradas.

## 7. ARQUIVOS

### Adicionados
### Modificados
### Removidos

Se nenhum:

Nenhum arquivo removido.

## 8. COMMITS

Informar SHA e mensagem.

## 9. LIMITAÇÕES

Declarar explicitamente qualquer teste que não pôde ser executado.

## 10. STATUS FINAL

Escolher somente:

CERTIFICADO

ou

NÃO CERTIFICADO

Não usar uma conclusão intermediária.

---

# 33. REGRA FINAL

A sequência obrigatória desta auditoria é:

LER
↓
VERIFICAR
↓
REPRODUZIR
↓
QUESTIONAR AS CONCLUSÕES
↓
ENCONTRAR REGRESSÕES
↓
CORRIGIR SOMENTE O NECESSÁRIO
↓
TESTAR NOVAMENTE
↓
CERTIFICAR OU RECUSAR A CERTIFICAÇÃO

A função desta etapa é ser independente.

Não assumir que o trabalho anterior está correto.

Não assumir que um teste estático prova runtime.

Não assumir que um APK que compila estável em runtime.

Não declarar CERTIFICADO sem evidência suficiente.

O objetivo é terminar esta sequência somente quando houver evidência real de que as causas foram eliminadas e o ReiAnix permanece funcional e estável.
