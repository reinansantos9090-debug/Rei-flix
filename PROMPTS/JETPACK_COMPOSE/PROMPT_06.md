# PONTE KOTLIN COM BIBLIOTECA EXISTENTE


Criar a ponte entre a nova camada Compose/Kotlin e os serviços atuais de biblioteca local.

A UI precisa conseguir:
- obter animes;
- obter episódios;
- obter progresso;
- alterar favorito;
- marcar episódio/anime como visto;
- abrir arquivo local;
- atualizar a biblioteca.

Não duplicar regras de negócio no Compose.

Preservar SQLite e scanner existentes sempre que possível. Se alguma API Python/Flet for inadequada para consumo nativo, criar uma interface Kotlin limpa para ela ou migrar apenas a responsabilidade necessária.

Garantir que a biblioteca continue funcionando mesmo offline.