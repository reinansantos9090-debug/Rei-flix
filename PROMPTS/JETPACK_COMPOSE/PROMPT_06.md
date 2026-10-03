# 06 — PONTE KOTLIN COM BIBLIOTECA EXISTENTE

## CONTRATO
O ReiAnix continua local/offline. Preserve SQLite, scanner, SAF, MediaStore, artwork, progresso e Media3. Não criar streaming, download ou banco paralelo. Não duplicar regras no Compose. Leia as APIs reais antes de criar abstrações.

## OBJETIVO
Conectar Kotlin/Compose aos serviços reais da biblioteca.

## IMPLEMENTAÇÃO
Mapear library service/store/scanner/bridge existentes e criar fachada/repository Kotlin apenas onde necessário. A UI deve observar animes/episódios, consultar progresso, alterar favorito/estado assistido, solicitar refresh e abrir URI/arquivo local. IO deve ocorrer fora da main thread. Flow deve ser coletado com lifecycle adequado. Se Python/Flet ainda for necessário para alguma operação, criar fronteira clara e documentada, sem duplicar a lógica inteira em Kotlin.

Garantir que atualizações emitidas pelo scanner/player cheguem à UI. Definir tratamento para erro, biblioteca vazia e fonte indisponível. Não serializar objetos gigantes pela navegação.

## NÃO FAZER
Não migrar todo o domínio para Kotlin apenas por estética. Não remover bridge funcional antes de existir substituto real.

## ACEITAÇÃO
[ ] dados reais chegam à UI; [ ] alterações persistem; [ ] offline funciona; [ ] IO não bloqueia UI; [ ] integração existente permanece.

## VALIDAÇÃO
Testar leitura, atualização, refresh e abertura de arquivo local. Executar build/testes.

## RELATÓRIO
Informar diff, APIs reutilizadas, testes e limitações.