# ARTWORK E THUMBNAILS COMPOSE


Integrar o sistema de artwork existente à UI Compose.

Objetivos:
- reutilizar cache existente;
- evitar downloads redundantes;
- evitar picos de memória;
- thumbnails de episódios eficientes;
- placeholders;
- tratamento de imagem ausente;
- cancelamento correto durante scroll;
- evitar flicker.

Se Coil for adotado, integrá-lo sem duplicar o cache de disco já existente sem necessidade.

Preservar os limites de tamanho e concorrência definidos anteriormente.