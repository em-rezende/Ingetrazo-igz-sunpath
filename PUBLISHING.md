# Publicação / Publishing

**Português** · [English](#english)

---

## Português

Este documento cobre duas publicações distintas:

1. **O repositório no GitHub** — código-fonte, documentação e releases.
2. **A ficha no catálogo de extensões do IngeTrazo** — o que faz a
   extensão aparecer em <https://ingetrazo.com/extensiones>.

### 1. Publicar o repositório no GitHub

Repositório: <https://github.com/em-rezende/Ingetrazo-igz-sunpath>

Pré-requisitos: `git`, `gh` autenticado (`gh auth status`) e Python 3.11+
para gerar o pacote.

```powershell
# Na pasta do projeto
git init -b main
git add .
git commit -m "igz_sunpath 1.0.0 — Sun Path toolbar for IngeTrazo"

# Se o repositório remoto já existir e estiver vazio:
git remote add origin https://github.com/em-rezende/Ingetrazo-igz-sunpath.git
git push -u origin main
```

Se o remoto ainda não existir:

```powershell
gh repo create em-rezende/Ingetrazo-igz-sunpath --public `
  --description "Sun Path toolbar for IngeTrazo: shadows, 3D sun vector, solar dome, location and PNG export" `
  --source . --remote origin --push
```

### 2. Gerar o pacote e a release

O arquivo que os usuários instalam é **um `.zip` com uma única pasta
`igz_sunpath/` contendo `__init__.py`** — exatamente o formato aceito pelo
catálogo e pelo gerenciador de extensões.

```powershell
# Gera dist/igz_sunpath.zip, imprime o SHA-256 e atualiza
# packaging/igz_sunpath.toml com a versão e a impressão digital.
.\packaging\build_extension.ps1 -WriteCatalog

# Qualquer plataforma:
python packaging/build_extension.py --write-catalog
```

O build é **determinístico**: os mesmos arquivos geram sempre o mesmo
SHA-256. Ele também grava `dist/igz_sunpath.zip.sha256` (formato
`sha256sum`). Confira antes de publicar:

```powershell
python packaging/build_extension.py --check
```

Crie a etiqueta e a release com o asset:

```powershell
git add packaging/igz_sunpath.toml
git commit -m "Release v1.0.0"
git tag -a v1.0.0 -m "igz_sunpath 1.0.0"
git push origin main --tags

gh release create v1.0.0 dist/igz_sunpath.zip `
  --title "igz_sunpath 1.0.0" `
  --notes-file CHANGELOG.md
```

A URL de download usada pelo catálogo fica:

```text
https://github.com/em-rezende/Ingetrazo-igz-sunpath/releases/download/v1.0.0/igz_sunpath.zip
```

### 3. Publicar no catálogo de extensões

Repositório do catálogo:
<https://github.com/ingelibre/ingetrazo-extensions>

O arquivo `packaging/igz_sunpath.toml` já está preenchido no formato
`extensions/<id>.toml`, com nome, resumo e descrição em **espanhol,
inglês e português**, licença livre, versão do IngeTrazo testada
(0.5.8), tags, captura de tela e SHA-256 do ZIP.

Passos:

1. Faça um fork de `ingelibre/ingetrazo-extensions` (ou use o botão
   **Add file ▸ Create new file** pelo navegador).
2. Copie `packaging/igz_sunpath.toml` para `extensions/igz_sunpath.toml`.
3. Copie `screenshots/igz_sunpath.png` para `screenshots/igz_sunpath.png`
   no catálogo (PNG, menos de 600 KB, ~1200×750).
4. Abra um pull request.
5. O robô do catálogo baixa o ZIP, confere o SHA-256 e lê o código com
   `ast` (sem executar). Ele também verifica se há `setup(app)` em um
   arquivo de topo do pacote — por isso `igz_sunpath/__init__.py` define
   `setup(app)` explicitamente.
6. Um mantenedor aprova a ficha; a página é atualizada em alguns
   minutos. A entrada aparece como **Comunidade** até alguém ler o
   arquivo; depois pode ser marcada como **Revisada** em `reviewed.toml`.

**Nova versão:** incremente `__version__` em `igz_sunpath.py`, rode o build
com `-WriteCatalog`, publique uma nova release (`v1.0.1`, …) e abra outra
pull request alterando `version`, `download` e `sha256`. Quando o PR vem
da conta que está em `author_url` (neste caso `em-rezende`) e altera
somente a própria ficha, ele é publicado automaticamente como
«Comunidade».

### Checklist de release

- [ ] `__version__` em `igz_sunpath.py` foi incrementado.
- [ ] `CHANGELOG.md` tem uma seção para a nova versão.
- [ ] `python -m unittest discover -s tests -v` passa.
- [ ] `python packaging/build_extension.py --check` passa.
- [ ] `dist/igz_sunpath.zip` foi anexado à release com o nome exato
      `igz_sunpath.zip`.
- [ ] `packaging/igz_sunpath.toml` tem a mesma versão e o mesmo SHA-256
      do asset publicado.
- [ ] A captura `screenshots/igz_sunpath.png` está atualizada e abaixo de
      600 KB.

---

## English

This document covers two separate publications:

1. **The GitHub repository** — source code, docs and releases.
2. **The IngeTrazo extension catalog entry** — what makes the extension
   appear at <https://ingetrazo.com/extensiones>.

### 1. Publish the GitHub repository

Repository: <https://github.com/em-rezende/Ingetrazo-igz-sunpath>

Requirements: `git`, an authenticated `gh` (`gh auth status`) and Python
3.11+ to build the archive.

```powershell
git init -b main
git add .
git commit -m "igz_sunpath 1.0.0 — Sun Path toolbar for IngeTrazo"

# If the remote exists and is empty:
git remote add origin https://github.com/em-rezende/Ingetrazo-igz-sunpath.git
git push -u origin main
```

If the remote does not exist yet:

```powershell
gh repo create em-rezende/Ingetrazo-igz-sunpath --public `
  --description "Sun Path toolbar for IngeTrazo: shadows, 3D sun vector, solar dome, location and PNG export" `
  --source . --remote origin --push
```

### 2. Build the archive and the release

The file users install is **a `.zip` holding one folder `igz_sunpath/`
with `__init__.py`** — exactly what the catalog and the extension manager
accept.

```powershell
.\packaging\build_extension.ps1 -WriteCatalog

# Any platform:
python packaging/build_extension.py --write-catalog
python packaging/build_extension.py --check
```

The build is **deterministic**: the same files always produce the same
SHA-256, and it also writes `dist/igz_sunpath.zip.sha256` (in
`sha256sum` format). Then tag and publish the release:

```powershell
git add packaging/igz_sunpath.toml
git commit -m "Release v1.0.0"
git tag -a v1.0.0 -m "igz_sunpath 1.0.0"
git push origin main --tags

gh release create v1.0.0 dist/igz_sunpath.zip `
  --title "igz_sunpath 1.0.0" `
  --notes-file CHANGELOG.md
```

The download URL used by the catalog is:

```text
https://github.com/em-rezende/Ingetrazo-igz-sunpath/releases/download/v1.0.0/igz_sunpath.zip
```

### 3. Submit to the extension catalog

`packaging/igz_sunpath.toml` is already in the `extensions/<id>.toml`
format, with Spanish, English and Portuguese name/summary/description, a
free licence, the tested IngeTrazo version (0.5.8), tags, screenshot and
the ZIP's SHA-256.

1. Fork `ingelibre/ingetrazo-extensions` (or use **Add file ▸ Create new
   file** in the browser).
2. Copy `packaging/igz_sunpath.toml` to `extensions/igz_sunpath.toml`.
3. Copy `screenshots/igz_sunpath.png` to `screenshots/igz_sunpath.png`
   in the catalog (PNG, under 600 KB, ~1200×750).
4. Open a pull request.
5. The catalog bot downloads the ZIP, checks the SHA-256 and reads the
   code with `ast` (it never executes it). It also requires a top-level
   `setup(app)` in the package — that is why `igz_sunpath/__init__.py`
   defines `setup(app)` explicitly.
6. A maintainer approves the entry and the page updates within minutes.
   It shows as **Community** until someone reads the file, after which it
   can be marked **Reviewed** in `reviewed.toml`.

**New version:** bump `__version__` in `igz_sunpath/__init__.py`, run the build with
`-WriteCatalog`, publish a new release (`v1.0.1`, …) and open another pull
request changing `version`, `download` and `sha256`. When it comes from the
account in `author_url` (`em-rezende`) and only touches its own entry, it
is published automatically as “Community”.

### Release checklist

- [ ] `__version__` in `igz_sunpath/__init__.py` was bumped.
- [ ] `CHANGELOG.md` has a section for the new version.
- [ ] `python -m unittest discover -s tests -v` passes.
- [ ] `python packaging/build_extension.py --check` passes.
- [ ] `dist/igz_sunpath.zip` is attached to the release with the exact
      name `igz_sunpath.zip`.
- [ ] `packaging/igz_sunpath.toml` has the same version and SHA-256 as the
      published asset.
- [ ] `screenshots/igz_sunpath.png` is current and under 600 KB.

