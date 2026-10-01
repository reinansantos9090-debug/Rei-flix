# PROMPT 44 — TESTE REAL E CERTIFICAÇÃO NO APK DO REIANIX

## REPOSITÓRIO OFICIAL

Trabalhe DIRETAMENTE no repositório:

https://github.com/reinansantos9090-debug/ReiAnix

Este prompt é a continuação direta de:

- PROMPT_42_AUDITORIA_FORENSE_E_CORRECAO_DEFINITIVA.md
- PROMPT_43_CORRECAO_DEFINITIVA_REIANIX.md

O objetivo desta etapa NÃO é criar funcionalidades novas.

O objetivo é provar, no APK real, se as correções do Prompt 43 realmente resolveram os problemas encontrados nos Prompts 42/43.

---

# 1. REGRA ABSOLUTA

NÃO reinicie o projeto.

NÃO crie outro projeto.

NÃO altere a arquitetura sem necessidade.

NÃO adicione funcionalidades.

NÃO inicie AniList.

NÃO faça novas otimizações apenas por preferência.

NÃO altere código somente para fazer um teste passar.

NÃO declare um problema resolvido sem evidência.

Esta etapa é de:

BUILD
→ INSTALAÇÃO
→ REPRODUÇÃO
→ TESTE REAL
→ EVIDÊNCIA
→ REGRESSÃO
→ CERTIFICAÇÃO

---

# 2. PRIMEIRO PASSO

Antes de testar:

1. Ler integralmente o Prompt 42.
2. Ler integralmente o Prompt 43.
3. Conferir o estado atual do Git.
4. Identificar exatamente quais alterações foram feitas pelo Prompt 43.
5. Confirmar o commit usado para gerar o APK.
6. Confirmar que o APK corresponde ao código que está sendo certificado.
7. Confirmar que o build oficial terminou sem erros críticos.

Não testar um APK diferente do código analisado.

---

# 3. OBJETIVO DA CERTIFICAÇÃO

Determinar, com evidência real, se os seguintes problemas foram eliminados:

1. fechamento inesperado do player;
2. falha de Next;
3. falha de Previous;
4. transições duplicadas;
5. callbacks stale;
6. erro de lifecycle;
7. botão Atualizar;
8. Pull-to-refresh;
9. refresh duplicado;
10. poster sendo substituído por episode thumbnail;
11. artwork stale;
12. race/generation/token;
13. regressões de navegação;
14. regressões de progress/resume;
15. regressões de scanner/biblioteca;
16. regressões de performance.

---

# 4. BUILD

Executar o workflow oficial de build do ReiAnix.

Confirmar:

- build concluído;
- APK gerado;
- APK íntegro;
- target SDK correto;
- ABI correta;
- manifest correto;
- permissões corretas;
- assinatura correta;
- payload Python correto;
- host Android correto;
- identidade da build correta.

Registrar:

- commit SHA;
- workflow run;
- APK gerado;
- SHA-256;
- tamanho do APK.

Se o build falhar, NÃO considerar a certificação concluída.

---

# 5. INSTALAÇÃO

Instalar exatamente o APK produzido pela build certificada.

Confirmar:

1. instalação sem erro;
2. aplicativo abre;
3. Home carrega;
4. não ocorre crash no startup;
5. system bars permanecem corretas;
6. navegação inicial funciona.

Registrar qualquer erro de instalação ou inicialização.

---

# 6. PREPARAÇÃO DO AMBIENTE

Usar uma biblioteca real contendo vídeos locais.

Confirmar:

- pasta selecionada;
- permissão preservada;
- scanner encontra os vídeos;
- biblioteca é populada;
- thumbnails são produzidas;
- posters são carregados;
- Details abre;
- episódios aparecem.

Não utilizar somente mocks para declarar certificação de runtime.

---

# 7. TESTE DO PLAYER

Executar o fluxo:

Home
→ Biblioteca
→ Anime
→ Details
→ Episódio
→ Player

Confirmar:

- Activity abre;
- player permanece aberto;
- Media3 inicializa;
- vídeo começa;
- first frame aparece;
- controles aparecem;
- áudio funciona;
- vídeo continua reproduzindo;
- Activity não desaparece sozinha.

Testar por tempo suficiente para reproduzir o problema original.

Como mínimo:

30 segundos de reprodução contínua quando o conteúdo permitir.

Se o bug original acontecia depois de alguns segundos, aguardar além desse período.

---

# 8. PLAYER — FECHAMENTO INESPERADO

Durante a reprodução observar:

- onCreate;
- onStart;
- onResume;
- onPause;
- onStop;
- onDestroy;
- finish;
- finishAndRemoveTask;
- player state;
- PlaybackException;
- Surface;
- decoder.

Se o player desaparecer:

NÃO declarar simplesmente "bug corrigido".

Determinar:

1. qual evento ocorreu primeiro;
2. qual callback aconteceu imediatamente antes;
3. se houve erro Media3;
4. se houve mudança de Surface;
5. se houve lifecycle inesperado;
6. se houve finish();
7. se houve callback stale;
8. se houve transição;
9. se houve intervenção do usuário.

Registrar a causa.

---

# 9. TESTE NEXT

Abrir um episódio e iniciar reprodução.

Executar:

Next

Confirmar:

1. comando chega;
2. episódio destino é correto;
3. target request é criado;
4. transition generation avança;
5. handoff é aceito;
6. player destino abre;
7. first frame aparece;
8. reprodução inicia;
9. player antigo não permanece controlando a sessão;
10. não há Activity duplicada.

Repetir pelo menos 3 vezes.

---

# 10. TESTE NEXT RÁPIDO

Executar:

Next
→ Next
→ Next

com intervalos curtos.

Confirmar:

- somente a transição válida permanece;
- não há fila antiga executando comandos atrasados;
- não há episódio incorreto;
- não há Activity órfã;
- não há callback antigo alterando o estado atual.

Registrar qualquer atraso anormal.

---

# 11. TESTE PREVIOUS

Executar:

Next
→ Previous

Confirmar que o episódio anterior abre corretamente.

Depois executar:

Previous
→ Previous
→ Previous

Confirmar:

- destino correto;
- handoff correto;
- generation correta;
- sessão correta;
- first frame;
- reprodução;
- ausência de Activity duplicada.

---

# 12. TESTE NEXT/PREVIOUS COM BACK

Testar:

Next
→ Back

Next
→ Next
→ Back

Previous
→ Back

Confirmar:

- Back encerra somente a sessão atual;
- Details permanece funcional;
- player não reabre sozinho;
- callback de sessão antiga não controla a Activity atual.

---

# 13. AUTOPLAY

Reproduzir um episódio próximo do final.

Permitir que o autoplay execute.

Confirmar:

- próxima mídia correta;
- mesma máquina de transição usada pelo Next;
- nenhum player duplicado;
- nenhuma Activity órfã;
- progress salvo corretamente;
- episódio atual não recebe progresso do próximo.

---

# 14. PROGRESS / RESUME

Executar:

1. abrir episódio;
2. reproduzir;
3. sair;
4. reabrir.

Confirmar:

- progresso salvo;
- episódio correto;
- resume correto.

Depois:

Next
→ sair
→ reabrir episódio anterior.

Confirmar que o progresso não foi gravado no episódio errado.

---

# 15. TESTE DE BACK

Testar:

- botão Voltar do player;
- botão físico/gesto Back do Android;
- retorno para Details;
- retorno para Home quando aplicável.

Confirmar que:

- Back funciona;
- player não fecha antes da hora;
- player não permanece ativo em background indevidamente;
- não ocorre reabertura automática;
- progress é preservado.

---

# 16. REFRESH — BOTÃO

Na Home:

1. tocar em Atualizar;
2. aguardar conclusão;
3. verificar biblioteca;
4. verificar UI;
5. tocar novamente.

Confirmar:

- scan executa;
- estado muda corretamente;
- UI atualiza;
- SUCCESS somente após conclusão real;
- novo refresh pode ser iniciado depois.

---

# 17. REFRESH DUPLICADO

Testar:

Atualizar
→ Atualizar
→ Atualizar

durante uma operação ativa.

Confirmar:

- não são iniciados scans duplicados desnecessários;
- existe uma única operação efetiva;
- estado não fica corrompido;
- UI não entra em loop;
- refresh posterior continua funcionando.

---

# 18. PULL-TO-REFRESH

Testar:

### Caso A

Scroll normal sem chegar ao topo.

Confirmar:

NÃO iniciar refresh.

### Caso B

Chegar ao topo e fazer pequeno overscroll abaixo do threshold.

Confirmar:

NÃO iniciar refresh.

### Caso C

Chegar ao topo e fazer overscroll acima do threshold.

Confirmar:

refresh é solicitado.

### Caso D

Fazer pull enquanto outro refresh está ativo.

Confirmar:

não iniciar concorrência indevida.

### Caso E

Fazer vários pulls rapidamente.

Confirmar:

coalescing correto.

---

# 19. REFRESH APÓS ERRO

Se for possível reproduzir um erro de refresh de forma segura:

1. provocar o erro;
2. verificar ERROR;
3. verificar limpeza do estado;
4. tentar atualizar novamente.

Confirmar:

- active não fica preso;
- UI não fica bloqueada;
- próximo refresh funciona.

Não provocar corrupção ou alterar dados apenas para fabricar um erro.

---

# 20. ARTWORK — TESTE REAL

Observar a Home durante:

1. carregamento inicial;
2. carregamento de posters;
3. geração de thumbnails;
4. atualização;
5. abertura de Details;
6. retorno;
7. novo refresh.

Confirmar:

- poster permanece poster;
- episode thumbnail permanece episode thumbnail;
- thumbnail de episódio nunca substitui poster;
- imagem de um episódio não aparece em outro;
- imagem antiga não volta depois da nova;
- resultado stale não sobrescreve resultado atual.

---

# 21. TESTE DE ARTWORK COM CONCORRÊNCIA

Quando possível, provocar carregamento simultâneo de várias imagens.

Observar:

- ordem de chegada diferente da ordem de solicitação;
- resultados antigos;
- resultados novos;
- troca rápida de telas.

Confirmar:

O último resultado válido para aquela identidade permanece.

Resultado stale deve ser ignorado.

---

# 22. CACHE

Fechar e reabrir o aplicativo.

Verificar:

- posters;
- thumbnails;
- Details;
- Home.

Confirmar que o cache não mistura:

poster
com
episode_thumbnail.

---

# 23. NAVEGAÇÃO

Testar:

Home
→ Biblioteca
→ Details
→ Player
→ Back
→ Details
→ Back
→ Home

Repetir algumas vezes.

Confirmar:

- nenhuma tela fica duplicada;
- nenhuma tela fica travada;
- player não reaparece;
- callbacks antigos não alteram telas atuais.

---

# 24. SYSTEM BARS

Durante:

- Home;
- Details;
- Player;
- Back;
- Next;
- Previous;
- retorno ao Details.

Confirmar:

- status bar correta;
- navigation bar correta;
- fullscreen correto;
- não há mudança inesperada;
- retorno restaura o estado esperado.

---

# 25. SCANNER E BIBLIOTECA

Sem modificar o scanner:

1. selecionar pasta;
2. reiniciar aplicativo;
3. confirmar permissão;
4. executar refresh;
5. confirmar vídeos;
6. abrir anime;
7. abrir episódio.

Confirmar que as correções não quebraram:

- SAF;
- MediaStore;
- broad storage quando aplicável;
- SQLite;
- library;
- metadata.

---

# 26. PERFORMANCE

Observar o comportamento durante:

- Home;
- refresh;
- carregamento de capas;
- thumbnails;
- Details;
- player;
- Next;
- Previous.

Quando disponível, usar:

- Logcat;
- Android Profiler;
- Perfetto;
- dumpsys;
- métricas de tempo existentes no projeto.

Não transformar esta etapa em uma nova otimização.

O objetivo é detectar regressões ou gargalos relevantes introduzidos pelas correções.

---

# 27. LOGCAT

Capturar os cenários problemáticos.

Procurar especialmente:

- NativePlayerActivity;
- Media3;
- ExoPlayer;
- Surface;
- decoder;
- NativeMailbox;
- AndroidBridge;
- handoff;
- transition;
- generation;
- stale;
- refresh;
- artwork;
- exceptions;
- ANR;
- crash.

Se o player fechar, localizar o PRIMEIRO evento inesperado.

---

# 28. COMPARAÇÃO COM O BUG ORIGINAL

Para cada bug relatado anteriormente, registrar:

### Antes

O que acontecia.

### Depois

O que acontece agora.

### Evidência

Log, vídeo, teste, comportamento observado ou resultado de build.

Exemplo:

| Problema | Antes | Depois | Evidência |
|---|---|---|---|
| Player fecha | ... | ... | ... |
| Next | ... | ... | ... |
| Previous | ... | ... | ... |
| Refresh | ... | ... | ... |
| Pull | ... | ... | ... |
| Poster/thumbnail | ... | ... | ... |

---

# 29. REGRESSÃO

Depois dos testes específicos, executar novamente:

- pytest;
- testes Kotlin;
- testes Android disponíveis;
- build oficial.

Nenhum teste existente deve ser removido.

Se um teste falhar:

1. identificar a causa;
2. determinar se é regressão;
3. corrigir o código se necessário;
4. somente alterar teste quando o contrato correto realmente mudou.

---

# 30. CRITÉRIO PARA CORREÇÃO DURANTE A CERTIFICAÇÃO

Se um problema for encontrado:

NÃO iniciar uma nova rodada arbitrária de funcionalidades.

Classificar:

- regressão introduzida pelo Prompt 43;
- bug antigo ainda presente;
- falha de ambiente;
- falha de teste;
- problema de hardware;
- problema não reproduzível.

Se for uma correção pequena e diretamente necessária para a certificação, corrigir.

Se exigir uma alteração arquitetural nova, NÃO mascarar como certificação concluída. Registrar como pendência.

---

# 31. NÃO CONSIDERAR TESTE ESTÁTICO COMO CERTIFICAÇÃO DE RUNTIME

Os seguintes itens sozinhos NÃO comprovam que o bug foi resolvido:

- pytest verde;
- teste Kotlin verde;
- grep;
- análise estática;
- build verde;
- APK gerado.

Eles comprovam apenas suas respectivas camadas.

Para problemas de runtime, é necessária evidência do APK real quando houver aparelho disponível.

---

# 32. APARELHO NÃO DISPONÍVEL

Se não houver dispositivo físico disponível:

NÃO inventar teste.

Marcar:

CORRIGIDO NO CÓDIGO, RUNTIME NÃO VALIDADO

ou

NÃO VALIDADO

e informar exatamente o que faltou testar.

---

# 33. CRITÉRIOS DE APROVAÇÃO

Um problema somente pode ser marcado:

RESOLVIDO E VALIDADO

quando:

1. código corrigido;
2. testes relevantes passam;
3. APK correspondente foi gerado;
4. cenário real foi reproduzido;
5. comportamento esperado foi observado;
6. não surgiu regressão relacionada.

Caso contrário, usar:

CORRIGIDO NO CÓDIGO, RUNTIME NÃO VALIDADO

AINDA NÃO RESOLVIDO

ou

NÃO COMPROVADO.

---

# 34. CERTIFICAÇÃO FINAL

Gerar uma tabela:

| Área | Status | Evidência |
|---|---|---|
| Build | ... | ... |
| Instalação | ... | ... |
| Startup | ... | ... |
| Player | ... | ... |
| Next | ... | ... |
| Previous | ... | ... |
| Autoplay | ... | ... |
| Progress | ... | ... |
| Back | ... | ... |
| Refresh button | ... | ... |
| Pull-to-refresh | ... | ... |
| Artwork | ... | ... |
| Cache | ... | ... |
| Navigation | ... | ... |
| System bars | ... | ... |
| Scanner | ... | ... |
| Library | ... | ... |
| Performance | ... | ... |
| Regression | ... | ... |

---

# 35. ARQUIVOS

Informar:

## Adicionados

## Modificados

## Removidos

Se não houver alteração:

Nenhum arquivo alterado.

---

# 36. COMMITS

Informar:

- SHA;
- mensagem;
- finalidade.

Não esconder commits de correção feitos durante a certificação.

---

# 37. APK

Informar:

- commit do APK;
- workflow run;
- versão/build;
- SHA-256;
- tamanho;
- resultado da instalação;
- resultado dos testes reais.

---

# 38. RESULTADO FINAL

O relatório deve terminar com exatamente uma destas classificações:

## CERTIFICADO

Somente se os cenários críticos tiverem sido realmente testados e aprovados.

## PARCIALMENTE CERTIFICADO

Quando o código e os testes estão corretos, mas algum runtime necessário não pôde ser validado.

## NÃO CERTIFICADO

Quando existe falha crítica reproduzível ou evidência insuficiente para considerar a etapa concluída.

Não usar linguagem ambígua.

---

# 39. REGRA FINAL

Não confundir:

IMPLEMENTADO
com
VALIDADO.

Não confundir:

TESTE PASSOU
com
BUG RESOLVIDO.

Não confundir:

APK GERADO
com
APK CERTIFICADO.

A sequência obrigatória é:

BUILD
↓
INSTALAÇÃO
↓
REPRODUÇÃO
↓
OBSERVAÇÃO
↓
EVIDÊNCIA
↓
REGRESSÃO
↓
CERTIFICAÇÃO

Se qualquer etapa falhar, registrar exatamente onde falhou.

O objetivo desta etapa é descobrir a verdade sobre o APK real, não produzir um relatório positivo.

NÃO adicionar funcionalidades novas.

NÃO reiniciar o projeto.

NÃO mascarar bugs.

NÃO inventar resultados.
