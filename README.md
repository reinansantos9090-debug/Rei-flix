# ReiFlix Local

ReiFlix é um catálogo para **arquivos de anime que já estão no dispositivo**. Ele não pesquisa streams, não contém plugins de fontes externas e não usa o AniList para episódios: o AniList fornece somente capa e metadados.

## Requisitos e execução

* Python 3.10+ (o CI Android usa 3.10).
* Flet `0.86.5`, fixado em `requirements.txt`.

```bash
python -m pip install -r requirements.txt
flet run main.py
```

Os dados ficam no diretório privado indicado por `FLET_APP_STORAGE_DATA` quando o Flet o disponibiliza (SQLite em `library.sqlite3`, cache em `covers/` e histórico em `history.json`). Em desenvolvimento local, o fallback é `.reiflix-data/`, que não deve ser versionado.

## Biblioteca local e Android

Em **Configurações → Adicionar pasta**, o `FilePicker.get_directory_path()` do Flet abre o seletor de diretório nativo. A pasta retornada é armazenada no SQLite e é varrida recursivamente para `.mp4`, `.mkv`, `.webm`, `.avi`, `.mov` e `.m4v`. Não há acesso automático a `/storage/emulated/0` e o app não solicita permissão ampla de armazenamento.

O Flet 0.86 expõe um caminho, mas não expõe uma API Python para persistir uma URI de *Storage Access Framework* (document tree). Por isso, o acesso persistente a diretórios que o Android não traduz para caminho acessível depende do seletor/implementação Flutter do Flet. Para suporte SAF integral em todas as versões Android, é necessária uma extensão Flutter Android pequena que devolva e retenha a URI de árvore; esta extensão não foi inventada neste repositório porque não há infraestrutura de plugin nativo existente. O aplicativo apresenta o erro do seletor de forma amigável em vez de afirmar que a autorização foi concedida.

## AniList

Não é necessária chave de API. O cliente usa `https://graphql.anilist.co` e consulta título, títulos alternativos, sinopse, capa/banner, gêneros, ano, temporada, status, episódios, duração e estúdio. Falhas de rede deixam o anime na biblioteca, com placeholder, e a atualização posterior tenta novamente. Capas bem-sucedidas são cacheadas pelo hash da URL.

## Google Login

O login é OAuth/OpenID Connect oficial pelo provedor de autenticação do Flet, com somente `openid`, `email` e `profile`; não há Gmail API nem escopo de e-mail. Antes de habilitá-lo, crie um cliente OAuth no Google Cloud, registre a URL de redirecionamento usada pelo Flet e forneça em tempo de execução:

```bash
# Para desenvolvimento:
export REIFLIX_GOOGLE_CLIENT_ID='...apps.googleusercontent.com'
export REIFLIX_GOOGLE_REDIRECT_URL='https://seu-redirecionamento-autorizado'
# Para o APK: preencha os mesmos valores públicos em app_config.py antes do build.
```

Não coloque um client secret no APK: clientes móveis são públicos. Para validação de tokens no servidor, crie um backend próprio posteriormente e valide `id_token` lá; este projeto não inventa um backend. O fluxo configurado abre o provedor oficial e persiste somente id, nome, e-mail e foto no SQLite privado. Em Android, uma experiência nativa Credential Manager exige uma extensão Flutter específica; enquanto ela não existir, o fluxo OAuth do Flet é usado apenas depois que os valores acima forem configurados.

## Organizador inteligente local

O organizador compara de forma local e explicável o título encontrado no arquivo com títulos romaji, inglês e nativos devolvidos pelo AniList. Correspondências fortes são associadas automaticamente; quando a confiança não é suficiente, a tela **Configurações → Organizador inteligente** apresenta os candidatos e permite salvar a escolha. Não há envio de nomes de arquivos para uma IA de terceiros além da pesquisa AniList já necessária para metadados.

## APK

```bash
flet build apk --yes
```

O workflow `.github/workflows/build_apk.yml` instala as dependências fixadas e publica `build/apk/*.apk`.

## Limitação conhecida do player

O controle `ft.Video` usado pelo projeto antigo não existe no Flet 0.86.5. Para evitar um crash ao abrir um episódio, a tela preserva a navegação/estado e envia o arquivo `file://` ao resolvedor de mídia local do dispositivo. Uma reprodução embutida requer adicionar uma extensão de vídeo compatível com a versão atual do Flet e validá-la no APK; o projeto não declara uma dependência de vídeo não verificada.
