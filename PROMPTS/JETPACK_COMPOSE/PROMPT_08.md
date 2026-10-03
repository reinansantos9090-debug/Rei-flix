# 08 — HOME CONTINUAR ASSISTINDO

## CONTRATO
ReiAnix é biblioteca/reprodutor LOCAL. Preserve a fonte real de progresso, SQLite e Media3. Não criar armazenamento paralelo. Preserve o bugfix de episódios desaparecendo e use IDs estáveis.

## OBJETIVO
Integrar Continuar assistindo ao sistema real de progresso.

## IMPLEMENTAÇÃO
Consumir progresso salvo pelo app. Mostrar artwork, título, temporada/episódio atual e indicador visual quando disponíveis. A ação deve abrir o episódio correto. Após o player salvar progresso, Home deve atualizar via estado observável sem reiniciar Activity. Respeitar regras existentes para episódios concluídos e itens sem progresso. Usar ViewModel/StateFlow/repository em vez de estado local como fonte de verdade.

Evitar recompor toda a Home por uma alteração isolada. Testar progresso zero, parcial, próximo do fim e concluído. Testar saída do player, retorno, atualização e reabertura do app.

## NÃO FAZER
Não criar tabela/preferência paralela. Não calcular progresso a partir de valor visual antigo. Não marcar como assistido apenas porque foi aberto.

## ACEITAÇÃO
[ ] progresso real; [ ] episódio correto; [ ] atualização após player; [ ] persistência; [ ] sem duplicação; [ ] testes relevantes.

## VALIDAÇÃO
Executar testes de ViewModel/repository/Compose e build. Registrar limitações.

## RELATÓRIO
Informar diff completo, testes, preservações e pendências.