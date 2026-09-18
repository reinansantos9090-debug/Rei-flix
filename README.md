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

## Android e APK

O projeto fixa `flet==0.86.5`. A própria distribuição instalada declara
**Flutter 3.44.8**; Java 17 e Android SDK 35 são o contrato de build. O código
em [`android/`](android/README.md) é um overlay do host Flutter gerado pelo
Flet, não um aplicativo Android independente.

```bash
python -m unittest discover -s tests -v
python -m compileall -q main.py app_config.py core views
git diff --check
flet build apk --yes
python scripts/verify_android_host.py build/apk/<arquivo>.apk
```

A última verificação é obrigatória: ela procura no DEX as classes
`MainActivity`, `NativeMailbox`, `SafScanner` e `NativePlayerActivity`. Caso
elas não estejam presentes, o APK é o cliente Flet stock e **não** deve ser
distribuído, pois a bridge `reiflix://native`, SAF e Media3 não estarão
integrados. O workflow GitHub Actions reproduz essas etapas, configura Python,
Java 17, Flutter 3.44.8 e Android SDK 35, e publica apenas o APK verificado.

Não há APK comitado no repositório e não são incluídos secrets de Google. O
acesso aos vídeos continua exclusivamente pela concessão SAF da pasta escolhida
pelo usuário; não se solicita permissão ampla de armazenamento.

## Google Cloud

Copie `.env.example` para o ambiente e forneça somente IDs públicos:

```bash
REIFLIX_GOOGLE_WEB_CLIENT_ID='...apps.googleusercontent.com'
REIFLIX_GOOGLE_CLIENT_ID='...apps.googleusercontent.com' # fallback OAuth desktop
REIFLIX_GOOGLE_REDIRECT_URL='https://redirect-autorizado.example/callback'
```

### Login Google no APK Android

O APK usa **Credential Manager + Google Identity** apenas para identificar uma
conta localmente. Configure o identificador público do **OAuth 2.0 Web client**
em `app_config.py`, no campo `GOOGLE_WEB_CLIENT_ID`, ou forneça
`REIFLIX_GOOGLE_WEB_CLIENT_ID` durante o build. Não adicione client secret.

No Google Cloud Console, crie também um OAuth client do tipo **Android** para o
package `com.reiflix.reiflix_local` e cadastre os SHA-1 e SHA-256 do certificado
que assina o APK distribuído (por exemplo, o certificado de release/Play App
Signing). O Web Client ID é o valor passado ao Credential Manager; ele deve ser
do mesmo projeto Cloud. Sem essas credenciais públicas externas o app mostra a
mensagem de configuração necessária e não simula login.

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
