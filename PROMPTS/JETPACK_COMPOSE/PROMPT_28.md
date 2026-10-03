# REMOÇÃO GRADUAL DA UI FLET


Depois de as telas Compose estarem funcionais, identificar a UI Flet que deixou de ser necessária.

Não apagar indiscriminadamente o Python.

Separar:
- código ainda necessário para serviços;
- código usado apenas para UI;
- código morto;
- bridges antigas.

Remover somente o que estiver comprovadamente obsoleto.

Garantir que build Android não dependa de componentes Flet apenas para desenhar a interface.