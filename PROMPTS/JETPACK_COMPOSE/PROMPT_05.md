# 05 — MODELOS DE DADOS PARA UI

## CONTRATO
ReiAnix é biblioteca/reprodutor LOCAL. A fonte de verdade permanece na infraestrutura existente. Preserve SQLite, scanner, SAF, MediaStore, artwork, progresso e Media3. Não criar banco paralelo, dados fictícios ou regras de negócio dentro de Composables. IDs são estáveis.

## OBJETIVO
Criar modelos Kotlin adequados para a UI sem duplicar o banco.

## IMPLEMENTAÇÃO
Mapear anime/série, temporada, episódio, URI/caminho local, progresso, duração, artwork, título, ano, gêneros, favorito, estado assistido/completo e metadata disponível. Criar UI/domain models somente onde houver benefício. Criar mapeadores explícitos entre a fonte existente e os modelos de UI. Representar ausência de metadata como null/estado explícito. Usar Flow/StateFlow para estados observáveis quando apropriado.

Testar mapeamentos com IDs, progresso zero/parcial/completo, episódio sem artwork, anime sem metadata e arquivos removidos. Garantir que conversões não mudem identidade nem ordem.

## NÃO FAZER
Não copiar entidades inteiras do banco indiscriminadamente. Não criar repository fake. Não inventar valores ausentes.

## ACEITAÇÃO
[ ] modelos compilam; [ ] mapeamentos testáveis; [ ] IDs preservados; [ ] progresso correto; [ ] nenhuma segunda fonte de verdade; [ ] null/empty seguros.

## VALIDAÇÃO
Executar testes unitários e build. Verificar integração com serviços existentes.

## RELATÓRIO
Listar diff e testes, incluindo estruturas existentes reutilizadas.