# LIMPEZA DA ARQUITETURA ANDROID


Organizar o módulo Android para a arquitetura Compose.

Separar claramente:
- ui;
- navigation;
- viewmodel;
- data;
- domain quando necessário;
- player;
- storage;
- bridge;
- scanner.

Não criar abstrações excessivas.

Eliminar duplicações introduzidas durante a migração.

Manter NativePlayerActivity e serviços nativos em posições claras.

Atualizar documentação interna da arquitetura.