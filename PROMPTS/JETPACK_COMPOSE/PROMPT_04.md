# 04 — APP SHELL E BARRA INFERIOR

## CONTRATO
ReiAnix é uma biblioteca/reprodutor LOCAL. Preserve toda infraestrutura de dados, scanner, armazenamento, artwork, progresso e Media3. Não inventar funcionalidades. Leia o código real e preserve a correção do episódio desaparecido.

## OBJETIVO
Construir o shell persistente e a bottom navigation nativa.

## IMPLEMENTAÇÃO
Usar Scaffold ou equivalente, separando área de conteúdo e bottom navigation. A barra deve ter quatro destinos principais somente se todos existirem de verdade, ícone, rótulo, estado selecionado em azul e área segura para navigation bar. O conteúdo rolável não pode ficar sob a barra. Integrar o Design System do Prompt 02. Details e Player não devem exibir a barra quando forem destinos de tela inteira, salvo se a arquitetura real exigir o contrário.

Testar mudanças de aba, restauração de scroll/estado, abertura de Details a partir de cada aba e retorno. O shell deve permanecer leve e não recompor toda a aplicação por qualquer mudança de conteúdo.

## NÃO FAZER
Não implementar conteúdo definitivo de Home/Biblioteca/Busca/Ajustes neste prompt. Não adicionar abas artificiais.

## ACEITAÇÃO
[ ] barra estável; [ ] seleção correta; [ ] Insets corretos; [ ] scroll não é coberto; [ ] Details/Player respeitam shell; [ ] back funciona.

## VALIDAÇÃO
Executar testes Compose/navegação e build. Verificar gesture navigation quando possível.

## RELATÓRIO
Informar diff, testes, componentes reutilizados e limitações.