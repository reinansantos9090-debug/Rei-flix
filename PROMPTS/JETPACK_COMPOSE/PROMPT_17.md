# ARMAZENAMENTO E PERMISSÕES


Migrar para Compose os fluxos relacionados ao armazenamento.

A tela deve permitir:
- visualizar fontes configuradas;
- selecionar pasta via SAF quando necessário;
- manter permissões persistentes;
- iniciar varredura;
- mostrar estado da biblioteca;
- executar ações de limpeza/reconciliação somente quando já existirem.

Preservar MANAGE_EXTERNAL_STORAGE somente onde a arquitetura atual realmente exigir e sem ampliar permissões desnecessariamente.

Testar retorno do seletor de pasta e retomada do app.