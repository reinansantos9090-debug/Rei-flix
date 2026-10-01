# PROMPT 44 — TESTE REAL E CERTIFICAÇÃO NO APK DO REIANIX

## REPOSITÓRIO OFICIAL

Trabalhe DIRETAMENTE no repositório:

https://github.com/reinansantos9090-debug/ReiAnix

Este prompt é a continuação direta do:

- PROMPT_42_AUDITORIA_FORENSE_E_CORRECAO_DEFINITIVA.md
- PROMPT_43_CORRECAO_DEFINITIVA_REIANIX.md

A sequência desta etapa é:

42 → descobrir/provar  
43 → corrigir  
44 → provar no APK  
45 → auditoria final independente

---

# 1. REGRA ABSOLUTA

NÃO reinicie o projeto.

NÃO crie outro projeto.

NÃO transforme o ReiAnix em uma nova arquitetura.

NÃO reverta correções anteriores.

NÃO adicione funcionalidades novas.

NÃO inicie AniList.

NÃO faça alterações cosméticas para esconder problemas.

NÃO considere um teste estático como prova de funcionamento no aparelho.

NÃO declare um bug resolvido somente porque o código compila ou os testes Python passam.

Nesta etapa o objetivo principal é:

**TESTAR O APLICATIVO REAL.**

---

# 2. OBJETIVO

Compilar o APK oficial, instalar no Android e reproduzir os cenários que anteriormente apresentavam problemas.

A certificação deve verificar, no mínimo:

- compilação;
- instalação;
- inicialização;
- seleção de pasta;
- persistência da permissão;
- descoberta dos vídeos;
- biblioteca;
- Details;
- player;
- reprodução;
- permanência do player;
- progress/resume;
- Next;
- Previous;
- autoplay;
- Back;
- Atualizar;
- Pull-to-refresh;
- capas/posters;
- episode thumbnails;
- regressões;
- lifecycle;
- system bars.

O objetivo não é criar nada novo.

O objetivo é provar se as correções do Prompt 43 realmente funcionam no APK.

---

# 3. PRIMEIRO PASSO

Antes do teste:

1. Ler integralmente o Prompt 42.
2. Ler integralmente o Prompt 43.
3. Conferir o estado atual do Git.
4. Conferir o commit que será certificado.
5. Confirmar que o código compilado corresponde ao código analisado.
6. Executar os testes automatizados disponíveis.
7. Gerar o APK oficial.
8. Registrar SHA-256 do APK.
9. Registrar versão/commit utilizado no teste.

Não testar um APK antigo e atribuir o resultado ao código atual.

---

# 4. BUILD

Executar o workflow/build oficial do ReiAnix.

Validar:

- build concluído;
- APK gerado;
- APK íntegro;
- assinatura;
- applicationId;
- target SDK;
- ABI;
- manifest;
- permissões;
- Python payload;
- Android host;
- recursos necessários.

Se o build falhar:

1. registrar o erro exato;
2. localizar a causa;
3. corrigir somente o necessário;
4. repetir o build;
5. não declarar certificação concluída.

---

# 5. IDENTIDADE DO APK

Registrar:

- commit SHA;
- branch;
- versão/build;
- nome do APK;
- SHA-256;
- data/hora do build.

O APK instalado deve ser exatamente o APK certificado.

Não usar APK antigo do Release ou de outro commit sem declarar explicitamente.

---

# 6. INSTALAÇÃO

Instalar o APK em aparelho Android disponível.

Registrar:

- versão do Android;
- modelo do aparelho;
- ABI;
- instalação limpa ou atualização;
- resultado da instalação.

Se for atualização:

também testar o comportamento das permissões e dados existentes.

Se for instalação limpa:

registrar esse fato.

---

# 7. PRIMEIRA EXECUÇÃO

Abrir o ReiAnix.

Verificar:

- Activity inicial;
- carregamento da UI;
- ausência de crash;
- system bars;
- navegação;
- Home;
- ausência de travamento prolongado;
- ausência de reconstrução contínua da interface.

Se ocorrer falha:

capturar Logcat e registrar o primeiro evento relevante.

---

# 8. STORAGE

Testar:

1. abrir seleção de pasta;
2. selecionar uma pasta real;
3. conceder permissão;
4. sair da tela;
5. voltar;
6. fechar o aplicativo;
7. abrir novamente;
8. verificar se a permissão continua válida.

Não considerar apenas a existência do registro de configuração.

Testar acesso real aos arquivos.

---

# 9. SCANNER

Após selecionar a pasta:

verificar:

- descoberta dos vídeos;
- identificação correta;
- ausência de duplicação;
- associação correta ao anime;
- episódios;
- títulos;
- caminhos/URIs;
- persistência no banco.

O scanner não deve bloquear a UI desnecessariamente.

Não modificar o scanner apenas para acelerar o teste.

---

# 10. BIBLIOTECA

Verificar:

- animes importados;
- quantidade correta;
- episódios corretos;
- ausência de duplicados;
- navegação;
- atualização após scan;
- persistência após reiniciar o aplicativo.

---

# 11. DETAILS

Abrir diferentes animes e episódios.

Verificar:

- capa/poster;
- informações;
- lista de episódios;
- progresso;
- navegação;
- thumbnails;
- retorno para Home/Biblioteca.

Nenhum callback antigo deve alterar Details depois que o usuário mudou de item.

---

# 12. TESTE PRINCIPAL DO PLAYER

Para cada cenário:

1. abrir Details;
2. selecionar episódio;
3. abrir player;
4. aguardar carregamento;
5. confirmar first frame;
6. iniciar reprodução;
7. deixar reproduzir por tempo suficiente;
8. observar se o player permanece aberto;
9. verificar áudio/vídeo;
10. verificar controles;
11. verificar progresso.

O teste deve ser suficientemente longo para detectar fechamento espontâneo.

Não considerar “abriu e mostrou um frame” como sucesso.

---

# 13. TESTE DE PERMANÊNCIA

Executar pelo menos:

- 15–30 segundos de reprodução contínua;
- se possível, um teste mais longo em um vídeo real.

Registrar:

- início da reprodução;
- READY;
- FIRST_FRAME;
- BUFFERING;
- PLAYING;
- PAUSED;
- STOP;
- ERROR;
- onPause;
- onStop;
- onDestroy;
- finish;
- retorno para Details.

Se o player fechar sozinho, identificar o primeiro evento que explica o fechamento.

---

# 14. PLAYER COM DIFERENTES VÍDEOS

Testar mais de um arquivo real.

Preferencialmente incluir arquivos com:

- codecs diferentes;
- resoluções diferentes;
- tamanhos diferentes;
- durações diferentes;
- caminhos/URIs diferentes.

Se somente um vídeo estiver disponível, declarar essa limitação.

---

# 15. NEXT

Executar:

1. abrir episódio;
2. iniciar reprodução;
3. tocar Next;
4. aguardar transição;
5. confirmar episódio correto;
6. confirmar first frame;
7. confirmar reprodução;
8. observar se o player permanece aberto.

Repetir várias vezes.

Testar:

Next → Next → Next

Não pode ocorrer:

- player fechado;
- Activity duplicada;
- episódio errado;
- tela de Details aparecendo;
- transição atrasada indefinidamente;
- sessão antiga assumindo o player.

---

# 16. PREVIOUS

Executar:

1. abrir episódio;
2. avançar para outro episódio;
3. tocar Previous;
4. confirmar episódio correto;
5. confirmar first frame;
6. confirmar reprodução.

Repetir:

Previous → Previous → Previous

Também testar:

Next → Previous → Next

---

# 17. TAPS RÁPIDOS

Testar:

- Next duas vezes rapidamente;
- Next três vezes;
- Previous duas vezes;
- Next → Previous rapidamente;
- Previous → Next rapidamente.

Verificar:

- apenas a transição válida permanece;
- não há Activity órfã;
- não há player duplicado;
- não há callback stale alterando o resultado.

---

# 18. AUTOPLAY

Testar autoplay usando a mesma máquina de transição do Next.

Verificar:

- episódio seguinte correto;
- transição;
- first frame;
- reprodução;
- progress;
- ausência de duplicação;
- ausência de fechamento do player.

---

# 19. BACK

Testar:

### Android Back

### botão de voltar da interface

### retorno normal do player

Depois:

- abrir outro episódio;
- voltar;
- abrir novamente.

Verificar que:

- o player fecha somente quando solicitado;
- Details permanece íntegro;
- a sessão antiga não interfere em uma nova sessão;
- não há Activity invisível/orfã.

---

# 20. PROGRESS / RESUME

Executar:

1. abrir episódio;
2. reproduzir;
3. sair;
4. voltar;
5. abrir novamente.

Verificar:

- progresso salvo;
- episódio correto;
- posição correta;
- sessão mais nova não é sobrescrita por callback antigo.

Também testar depois de:

- Next;
- Previous;
- Back;
- fechamento normal do player.

---

# 21. BOTÃO ATUALIZAR

Testar o botão Atualizar na Home.

Verificar:

1. tocar uma vez;
2. observar estado;
3. aguardar conclusão;
4. verificar biblioteca;
5. repetir;
6. verificar que não inicia scans duplicados.

Durante um refresh ativo:

- tocar novamente;
- observar comportamento;
- não deve criar concorrência desnecessária.

---

# 22. PULL-TO-REFRESH

Testar:

### Abaixo do threshold

Não deve iniciar refresh.

### Acima do threshold

Deve iniciar exatamente uma operação.

### Repetição

Pull → Pull → Pull

### Concorrência

Pull durante refresh.

### Mistura

Botão → Pull

Pull → Botão

Botão → Pull → Botão

Verificar estado final.

---

# 23. REFRESH

Para cada refresh registrar:

- origem;
- request;
- início;
- scan;
- atualização do banco;
- atualização da UI;
- SUCCESS ou ERROR;
- término.

Não aceitar sucesso falso.

O estado deve voltar corretamente para IDLE após conclusão ou erro.

---

# 24. ARTWORK / POSTER

Abrir Home e aguardar as capas.

Depois:

1. aguardar thumbnails;
2. abrir Details;
3. voltar;
4. atualizar;
5. observar novamente.

Confirmar:

**poster continua sendo poster.**

Uma episode thumbnail nunca pode aparecer como capa do anime.

---

# 25. ARTWORK / EPISODE THUMBNAIL

Verificar especificamente:

- thumbnail do episódio A;
- thumbnail do episódio B;
- poster do anime;
- Details;
- Home.

A thumbnail de A não pode aparecer no episódio B.

A thumbnail de A não pode virar poster.

A thumbnail de B não pode substituir o poster.

---

# 26. STALE RESULTS

Produzir situações em que resultados assíncronos possam terminar fora de ordem.

Exemplo:

1. abrir item A;
2. iniciar carregamento;
3. mudar rapidamente para B;
4. permitir que A termine depois.

Verificar:

A não sobrescreve B.

Fazer o mesmo para:

- artwork;
- thumbnails;
- Details;
- Home;
- refresh.

---

# 27. LIFECYCLE

Durante os testes registrar:

- onCreate;
- onStart;
- onResume;
- onPause;
- onStop;
- onDestroy.

Qualquer onStop/onDestroy inesperado deve ser correlacionado com:

- Back;
- transição;
- erro;
- sistema;
- processo.

Não assumir que o callback é normal sem verificar a causa.

---

# 28. LOGCAT

Capturar Logcat durante os cenários críticos.

Prioridade:

1. player fechando;
2. Next;
3. Previous;
4. refresh;
5. artwork.

Registrar:

- timestamp;
- Activity;
- session;
- request;
- generation;
- transition;
- Media3;
- Surface;
- decoder;
- refresh;
- artwork.

---

# 29. PRIMEIRO EVENTO INESPERADO

Para cada falha, identificar:

**qual foi o primeiro evento que saiu do fluxo esperado?**

Exemplo:

Esperado:

Activity → Player → READY → FIRST_FRAME → PLAYING

Observado:

Activity → Player → BUFFERING → onStop → finish

O diagnóstico deve começar em onStop/finish e não somente no sintoma visual.

---

# 30. EVIDÊNCIA

Para cada problema registrar:

- reproduziu? SIM/NÃO;
- cenário;
- commit;
- APK;
- aparelho;
- Android;
- logs;
- primeiro evento inesperado;
- causa;
- correção;
- resultado pós-correção.

Não utilizar linguagem como:

“parece resolvido”.

Usar somente:

- RESOLVIDO E VALIDADO;
- CORRIGIDO NO CÓDIGO, RUNTIME NÃO VALIDADO;
- AINDA NÃO RESOLVIDO;
- NÃO REPRODUZIDO.

---

# 31. REGRESSÃO

Depois dos testes específicos, executar novamente o fluxo completo:

1. abrir app;
2. Home;
3. Biblioteca;
4. Details;
5. episódio;
6. player;
7. Next;
8. Previous;
9. Back;
10. progress;
11. Home;
12. Atualizar;
13. Pull-to-refresh;
14. abrir Details novamente;
15. reproduzir outro episódio.

Verificar que uma correção não criou outro problema.

---

# 32. PERFORMANCE

Durante os testes observar:

- travamentos;
- ANR;
- quedas de FPS;
- UI bloqueada;
- consumo anormal de memória;
- fila excessiva;
- atualização excessiva da UI;
- atraso entre comando e resposta.

Não otimizar por percepção subjetiva.

Se possível utilizar:

- Logcat;
- Android Profiler;
- Perfetto;
- dumps;
- métricas de tempo.

Registrar somente dados efetivamente coletados.

---

# 33. MEMORY

Observar especialmente durante:

- Home com muitas capas;
- thumbnails;
- abrir/fechar Details;
- entrar/sair do player;
- Next/Previous repetidos;
- refresh repetido.

Verificar se existe crescimento contínuo de memória.

Não declarar memory leak sem evidência.

---

# 34. SURFACE / PLAYER VISUAL

Se o Prompt 43 tiver mantido a configuração atual de Surface, testar o comportamento real.

Se houver evidência de problema visual:

- registrar;
- correlacionar com lifecycle;
- Surface;
- Media3;
- decoder.

Não trocar SurfaceView/TextureView somente por preferência.

---

# 35. TESTES AUTOMATIZADOS

Executar todos os testes disponíveis relevantes.

Registrar:

- pytest;
- testes Kotlin;
- Gradle;
- instrumented;
- contratos;
- build.

Nenhum teste deve ser removido para obter aprovação.

---

# 36. BUILD FINAL

Depois dos testes/correções necessárias:

gerar o APK final certificado.

Registrar:

- commit;
- SHA-256;
- APK;
- versão;
- resultado do build.

O APK final deve ser o mesmo que foi usado na última validação.

---

# 37. CRITÉRIO DE CERTIFICAÇÃO

A etapa só pode ser considerada certificada se:

- APK compilou;
- APK instalou;
- app abriu;
- storage funcionou;
- biblioteca funcionou;
- Details funcionou;
- player funcionou;
- player permaneceu aberto durante o teste;
- Next funcionou;
- Previous funcionou;
- autoplay funcionou;
- Back funcionou;
- progress funcionou;
- Atualizar funcionou;
- Pull-to-refresh funcionou;
- posters permaneceram isolados das thumbnails;
- não houve regressão crítica.

Se algum item não puder ser testado por falta de aparelho, ferramenta ou cenário real:

marcar explicitamente como **NÃO VALIDADO**.

Não transformar ausência de teste em aprovação.

---

# 38. NÃO CORRIGIR SEM EVIDÊNCIA

Se durante a certificação surgir um problema novo:

1. reproduzir;
2. coletar evidência;
3. identificar causa;
4. corrigir somente se a causa estiver suficientemente estabelecida;
5. repetir o teste.

Não fazer uma sequência de patches especulativos.

Se a causa não puder ser determinada:

documentar como NÃO DETERMINADO e encaminhar para auditoria final.

---

# 39. PROIBIÇÕES

É proibido:

- adicionar funcionalidades;
- iniciar AniList;
- reescrever arquitetura;
- remover funcionalidades;
- desabilitar testes;
- usar sleeps para mascarar races;
- retry infinito;
- catch vazio;
- `|| true`;
- aumentar timeout sem causa;
- apagar logs diagnósticos;
- declarar sucesso sem teste;
- declarar correção baseada somente em teste estático.

---

# 40. RELATÓRIO FINAL

Produzir um relatório objetivo contendo:

## BUILD

- commit;
- APK;
- SHA-256;
- resultado.

## DISPOSITIVO

- modelo;
- Android;
- ABI;
- instalação limpa/atualização.

## CENÁRIOS

| Cenário | Resultado | Evidência |
|---|---|---|
| Inicialização | ... | ... |
| Storage | ... | ... |
| Biblioteca | ... | ... |
| Details | ... | ... |
| Player | ... | ... |
| Permanência | ... | ... |
| Next | ... | ... |
| Previous | ... | ... |
| Autoplay | ... | ... |
| Back | ... | ... |
| Progress | ... | ... |
| Atualizar | ... | ... |
| Pull-to-refresh | ... | ... |
| Artwork | ... | ... |
| Regressão | ... | ... |

## BUGS

### Resolvidos e validados

### Corrigidos no código, runtime não validado

### Ainda não resolvidos

### Não reproduzidos

### Não determinados

## LOGS

Informar quais evidências foram coletadas.

## REGRESSÃO

Informar se alguma funcionalidade anteriormente estável deixou de funcionar.

---

# 41. DIFF

Informar:

### Arquivos adicionados

### Arquivos modificados

### Arquivos removidos

Se não houver remoções:

Nenhum arquivo removido.

Também informar o que já existia e não precisou ser alterado.

---

# 42. COMMITS

Informar:

- SHA;
- mensagem;
- resumo.

Não esconder commits intermediários relevantes.

---

# 43. STATUS FINAL

Para cada item usar exatamente uma categoria:

**RESOLVIDO E VALIDADO**

**CORRIGIDO NO CÓDIGO, RUNTIME NÃO VALIDADO**

**AINDA NÃO RESOLVIDO**

**NÃO REPRODUZIDO**

**NÃO DETERMINADO**

---

# 44. REGRA FINAL

A sequência obrigatória é:

APK
↓
INSTALAR
↓
REPRODUZIR
↓
MEDIR
↓
COLETAR EVIDÊNCIA
↓
COMPARAR
↓
REGRESSÃO
↓
CERTIFICAR

O Prompt 43 corrigiu.

O Prompt 44 precisa provar.

Não confundir:

**código corrigido**

com

**problema realmente resolvido no aparelho**.

Somente depois desta etapa a auditoria independente do Prompt 45 poderá determinar se a etapa está realmente encerrada.

Trabalhe diretamente no repositório e não adicione funcionalidades novas.
