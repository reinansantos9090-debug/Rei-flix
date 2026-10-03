# DESEMPENHO COMPOSE


Otimizar a nova UI Compose para Android real.

Auditar:
- recomposições;
- LazyColumn/LazyGrid keys;
- remember;
- derivedStateOf;
- coleta de Flow;
- carregamento de artwork;
- scroll;
- navegação;
- memória;
- cancelamento de jobs.

Não chamar banco ou filesystem diretamente no composable.

Não reconstruir a tela inteira por qualquer mudança de progresso.

Manter 60 FPS como objetivo em aparelhos compatíveis.