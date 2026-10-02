
# PROMPT 5.2 — CORREÇÃO DEFINITIVA DO CONTINUE WATCHING PARA MÚLTIPLOS EPISÓDIOS

## Repositório
https://github.com/reinansantos9090-debug/ReiAnix

## Contexto

Continuação direta do PROMPT 5.1.

A implementação atual de Continue Watching foi identificada como uma projeção que pode usar ROW_NUMBER/PARTITION BY anime_id e, depois, manter apenas resume_rank=1. Isso limita a representação a um episódio por anime.

O usuário precisa que episódios diferentes do mesmo anime, quando possuem progresso independente, continuem disponíveis para retomada.

Exemplo:

Anime A:
E01 20%
E02 30%
E03 40%
E04 10%
E05 5%

Depois de fechar/reabrir, esses episódios devem continuar registrados como retomáveis, respeitando o limite configurado da seção.

## OBJETIVO

Fazer Continue Watching representar episódios, não apenas animes.

Deve:
- permitir múltiplos episódios do mesmo anime;
- ordenar por last_played_at/atividade real;
- respeitar limite da seção;
- excluir concluídos;
- excluir missing;
- excluir sem progresso;
- preservar episode_id, progress e last_played_at;
- não duplicar episódio;
- continuar funcionando após restart;
- não quebrar Home ou Details.

## 1. AUDITORIA

Inspecionar:
- core/library_store.py
- core/library_service.py
- views/home_view.py
- views/details_view.py
- todas as implementações de continue_watching/current_episode/resume
- SQL de progress/watched/missing/last_played_at
- consumption_state, is_in_progress, is_completed.

Não assumir que existe somente uma consulta.

## 2. DEFINIÇÃO DE EM ANDAMENTO

Reutilizar os contratos existentes.

Exemplos:

progress=0 + watched=false → NÃO Continue.
progress>0 + watched=false → SIM.
watched=true → NÃO.
missing=true → NÃO.

Respeitar exatamente o completion threshold existente. Não inventar novo threshold.

## 3. REMOVER A RESTRIÇÃO POR ANIME

A projeção NÃO deve eliminar episódios distintos usando PARTITION BY anime_id.

O item da projeção é o episódio.

Exemplo esperado:

E05 Anime A 5%
E03 Anime B 70%
E02 Anime A 30%
E01 Anime C 20%

A ordenação deve refletir atividade real.

## 4. LIMITE

Se Home possui limite N, aplicar LIMIT N aos episódios após ordenar.

Não transformar N em N animes × 1 episódio.

## 5. IDENTIDADE E DUPLICIDADE

Usar o identificador canônico do episódio.

Não deduplicar apenas por nome/título/anime.

## 6. DISPONIBILIDADE

Não mostrar como Continue um episódio missing ou inexistente.

Não marcar missing artificialmente somente para esconder a entrada.

## 7. CONCLUÍDOS

Preservar a definição atual de concluído. Não mostrar concluídos como retomáveis.

## 8. CASOS OBRIGATÓRIOS

A) Mesmo anime:
E01 10%, E02 20%, E03 30% → os três podem aparecer.

B) Vários animes:
A/E01 10%, A/E02 20%, B/E01 30% → os três podem aparecer.

C) Concluído:
A/E01 completed, A/E02 20% → somente E02.

D) Missing:
A/E01 20% missing, A/E02 30% disponível → somente E02.

E) Ordenação:
E01 t=100, E02 t=200, E03 t=150 → E02, E03, E01.

F) Limite=3 → somente os três episódios mais recentes.

G) Restart:
persistir → recriar Store/processo → consultar → mesmo resultado.

## 9. NÃO CONFUNDIR CONCEITOS

Continue Watching:
episódios que já começaram e ainda podem ser retomados.

Current Episode:
pode representar o próximo episódio a assistir.

Não substituir uma função pela outra apenas para reduzir código.

## 10. HOME E DETAILS

Preservar:
- artwork;
- título;
- temporada;
- episódio;
- progresso;
- clique;
- navegação;
- refresh;
- catalog changed.

Auditar consumidores antes de alterar o retorno.

## 11. PERFORMANCE

Não criar:
- N+1 queries;
- uma query por card;
- carregamento de toda biblioteca apenas para filtrar;
- polling;
- rebuild global desnecessário.

Preferir SQL eficiente.

Verificar índices existentes. Criar índice somente se necessário.

## 12. COMPATIBILIDADE

Não apagar progressos, last_played_at ou watched.

Não recriar banco.

Funcionar sobre dados já existentes.

## 13. TESTE REAL DO BUG

Criar/fortalecer teste:

abrir E01 → 20%
abrir E02 → 30%
abrir E03 → 40%
fechar/reabrir
→ E01, E02 e E03 continuam representados.

## 14. INTEGRAÇÃO COM 5.1

Validar:

player
→ mailbox
→ main.py
→ SQLite
→ Continue Watching
→ Home

Não assumir que persistência no SQLite significa automaticamente projeção correta.

## 15. NÃO FAZER

Não:
- voltar a limitar por anime;
- mudar completion threshold;
- apagar dados;
- criar nova tabela sem necessidade;
- duplicar lógica de progress;
- esconder itens somente na UI;
- usar sleep/timeout;
- alterar Media3;
- alterar lifecycle do player sem necessidade.

## 16. VALIDAÇÃO

Executar:
- testes LibraryStore;
- Continue Watching;
- progress;
- restart;
- Home/Details;
- compileall;
- git diff --check;
- build;
- CI.

Classificar:
EXECUTADO — PASSOU / EXECUTADO — FALHOU / VALIDADO ESTATICAMENTE / NÃO EXECUTADO / NÃO DISPONÍVEL.

Runtime somente se realmente executado.

## 17. ENTREGA FINAL

Informar:
- causa da limitação;
- correção;
- compatibilidade com dados antigos;
- testes;
- build;
- CI;
- runtime;
- diff de adicionados/modificados/removidos;
- não implementado/não validado.

Conclusão:
1. CORRIGIDO E VALIDADO EM RUNTIME
2. CORREÇÃO ESTRUTURAL VALIDADA, RUNTIME PENDENTE
3. PROBLEMA AINDA PRESENTE — NOVA CORREÇÃO NECESSÁRIA
4. EVIDÊNCIA INSUFICIENTE — NÃO É POSSÍVEL CONCLUIR
