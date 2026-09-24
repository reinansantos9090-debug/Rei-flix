# Rei-Flix — Configurações avançadas

Esta fase seleciona configurações úteis observadas em CloudStream, Nova Video Player e Aniyomi/Animiru como referências de comportamento. A implementação continua própria e usa SettingsStore, LibraryService, ArtworkEngine e NativePlayerActivity existentes.

## Configurações implementadas

| Configuração | Categoria | Default | Efeito real |
|---|---|---:|---|
| Tamanho dos cards | Biblioteca | medium | altera dimensões dos cards da Home |
| Mostrar miniaturas | Biblioteca | true | evita carregamento/renderização de artwork na Home quando desativado |
| Ordenação padrão | Biblioteca | added_desc | define a ordenação inicial da Home |
| Densidade da grade | Biblioteca | medium | altera espaçamento/densidade visual da grade |
| Itens por página | Biblioteca | 36 | altera page_size da consulta paginada existente |
| Salto no double tap | Player/Gestos | 10 s | altera o seek do double tap; swipe horizontal continua desativado |
| Velocidade da pressão longa | Player/Gestos | 2.0x | aplica velocidade temporária durante long press |
| Resolução máxima | Vídeo | automática | aplica limite de seleção de vídeo ao TrackSelectionParameters |
| FPS máximo | Vídeo | automático | aplica limite de frame rate à seleção Media3 |
| Canais de áudio máximos | Áudio | automático | aplica limite de canais à seleção Media3 |
| Escala da legenda | Legendas | 100% | ajusta o tamanho via SubtitleView |
| Margem inferior da legenda | Legendas | 8% | ajusta o bottom padding via SubtitleView |
| Estilo embutido da legenda | Legendas | true | permite/desativa estilos declarados pela faixa |
| Usar AniList | Metadata | true | bloqueia/permite chamadas remotas do AniListClient |
| Auto-match AniList | Metadata | true | bloqueia novas buscas automáticas quando desativado |
| Artwork remoto | Artwork | true | bloqueia/permite downloads remotos pelo ArtworkEngine |
| Limite do cache de artwork | Artwork/Desempenho | 128 MB | altera o limite do cache do único ArtworkEngine |

## Configurações não mantidas

Foram removidas do SettingsStore por não terem aplicação real comprovada na arquitetura atual: app.start_screen, app.animations, appearance.show_badges, metadata.keep_local, artwork.offline_cache e privacy.external_sync.

Não foram adicionadas opções de streaming, provider, scraper, downloader, source remoto, Google Drive, mpv scripts ou outro motor de reprodução.

## Compatibilidade

O player continua usando a NativePlayerActivity existente e Media3 1.5.1. As opções de vídeo/áudio usam TrackSelectionParameters; legendas usam SubtitleView. Defaults preservam o comportamento anterior sempre que possível.

A exportação de Settings passou para schema 2. Imports schema 1 são aceitos e os campos removidos/desconhecidos são ignorados sem alterar outras preferências.

## Estado de validação desta fase

O documento descreve somente configurações implementadas no código desta fase. Resultado final de testes/build/APK/dispositivo deve ser lido do CI correspondente ao commit final.
