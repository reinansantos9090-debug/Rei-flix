# ReiFlix Local

ReiFlix é uma biblioteca para vídeos de anime que o usuário já possui no
Android. Os arquivos não são enviados para servidor algum; AniList é usado
somente para metadados/capas.

## Execução Python

```bash
python -m pip install -r requirements.txt
flet run main.py
python -m unittest discover -s tests -v
```

O banco SQLite e o cache de capas ficam no diretório privado definido por
`FLET_APP_STORAGE_DATA` (ou `.reiflix-data/` no desenvolvimento).

## Bridge Android: SAF, player e Google

O diretório [`android/`](android/README.md) contém a implementação nativa que
deve ser mesclada ao template Android usado pelo Flet:

* `MainActivity` abre `ACTION_OPEN_DOCUMENT_TREE` e pede as flags de leitura,
  escrita, prefixo e persistência; `SafScanner` chama
  `takePersistableUriPermission()` e enumera recursivamente `DocumentFile`.
  O resultado conserva URI, nome, MIME type, tamanho e data, sem criar caminho
  `/storage/...` fictício.
* `NativePlayerActivity` usa **Media3 ExoPlayer** diretamente sobre a URI SAF.
  Ele usa controles nativos sobrepostos, seek, play/pause, duração, timeout de
  controles, orientação horizontal e barras imersivas. Erro de codec/container
  resulta em mensagem amigável; arquivos não são copiados.
* `GoogleIdentity` usa **Credential Manager / Google Identity** com
  `GetGoogleIdOption`, sem Gmail API e sem escopos de caixa de entrada,
  contatos ou Drive. Tokens não são persistidos; apenas id, nome, email e foto
  retornam para o armazenamento privado.

A comunicação é feita pelo `reiflix://native` e por uma fila JSON privada
(`NativeMailbox`/`AndroidBridge`). O Python insere documentos recebidos no
SQLite e salva o progresso emitido pelo player. Consulte a integração de
template e dependências em [`android/README.md`](android/README.md).

> **Estado de build:** os fontes nativos foram implementados, mas o workflow
> atual ainda invoca o cliente Android padrão do Flet. Antes de distribuir um
> APK, configure o template Flet para mesclar `android/app` e substituir a
> activity gerada por `com.reiflix.reiflix_local.MainActivity`; sem isso o
> cliente stock não conhecerá a bridge. Não há como uma aplicação Python
> injetar `ContentResolver`/Credential Manager/ExoPlayer em um APK já gerado.

## Google Cloud

Copie `.env.example` para o ambiente e forneça somente IDs públicos:

```bash
REIFLIX_GOOGLE_WEB_CLIENT_ID='...apps.googleusercontent.com'
REIFLIX_GOOGLE_CLIENT_ID='...apps.googleusercontent.com' # fallback OAuth desktop
REIFLIX_GOOGLE_REDIRECT_URL='https://redirect-autorizado.example/callback'
```

No Google Cloud Console configure a tela de consentimento, o **Web client ID**
passado a `REIFLIX_GOOGLE_WEB_CLIENT_ID`, e um Android client para o package
`com.reiflix.reiflix_local` com SHA-1/SHA-256 do certificado de assinatura. Não
inclua client secret no APK.

## AniList, scanner e organização

O scanner Python atende caminhos reais em desktop. No Android, a camada SAF
entrega documentos autorizados e `LibraryService.ingest_documents()` os agrupa
por anime/temporada/episódio, persistindo a URI em vez de caminho POSIX.
AniList GraphQL pesquisa o título e mantém título, gêneros, sinopse e cache
local de capas. Sem internet, a biblioteca/URI e capas cacheadas permanecem
utilizáveis. A Home filtra os títulos por gêneros devolvidos pelo AniList.

## Permissões

Somente `INTERNET` é declarada para AniList/OAuth. O acesso a vídeos é a
concessão por pasta do SAF, não `READ_MEDIA_VIDEO` amplo. Não são solicitadas
permissões de notificações, contatos, SMS, telefone, localização, câmera,
microfone, Gmail ou Drive.

## Build

```bash
flet build apk --yes
```

O build requer Java 17, Flutter e dependências Android acessíveis. Depois de
configurar a mesclagem do overlay, valide em aparelho a seleção SAF, a conta
Google e arquivos/codec reais, especialmente MKV.
