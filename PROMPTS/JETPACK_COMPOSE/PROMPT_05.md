# MODELO DE DADOS PARA UI


Criar uma camada Kotlin para representar os dados que a UI precisa consumir sem duplicar desnecessariamente o banco existente.

Mapear:
- anime/série;
- temporadas;
- episódios;
- caminho/URI local;
- progresso;
- favorito;
- status assistindo/completo;
- artwork;
- metadados disponíveis;
- gêneros;
- ano;
- duração.

Criar modelos UI e mapeadores somente onde necessário.

A fonte de verdade deve continuar sendo a infraestrutura de biblioteca existente. Não criar um segundo banco concorrente.

Usar StateFlow/Flow para atualizações observáveis quando fizer sentido.

Preparar a integração para Home, Biblioteca, Details e Busca.