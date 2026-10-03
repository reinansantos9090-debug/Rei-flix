# FUNDAÇÃO KOTLIN E JETPACK COMPOSE


Você está trabalhando diretamente no repositório ReiAnix.

Objetivo: iniciar a migração da camada de interface do ReiAnix para Kotlin + Jetpack Compose, sem destruir a infraestrutura existente.

Regras:
- Não apagar SQLite, scanner, SAF, MediaStore, progresso ou Media3.
- Não introduzir streaming/download de anime.
- O aplicativo continua sendo uma biblioteca local de vídeos/animes já armazenados no aparelho.
- Criar uma arquitetura Android nativa preparada para Compose.
- Mapear o que hoje pertence ao Flet/Python e o que deverá ser consumido pelo Kotlin.
- Usar Kotlin, Jetpack Compose, Material 3, Navigation Compose, ViewModel e StateFlow quando apropriado.
- Preservar compatibilidade com o projeto Android atual.
- Não fazer ainda a migração visual completa das telas.

Implemente diretamente no repositório. Ajuste Gradle, módulos e estrutura Kotlin necessários. Faça o projeto compilar. Ao terminar, informe o diff completo e os testes executados.