#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ezequiel M. Rezende
"""Build the installable ``igz_sunpath.zip`` and the catalog entry.

The archive holds exactly one Python package folder::

    igz_sunpath/
        __init__.py
        core/            all runtime modules
        icons/  i18n/  screenshots/
        README.md  README_ptBR.md  CHANGELOG.md  PUBLISHING.md
        LICENSE  THIRD-PARTY.md

That is the layout the IngeTrazo plugin loader and the community catalog
both expect (a ``.zip`` with one folder containing ``__init__.py``).

The build is deterministic: members are sorted, timestamps are fixed and
permissions are normalised.  Files are stored uncompressed, so the archive
bytes do not depend on the zlib version of the Python that built it:
building the same sources twice — or on another machine/Python — yields the
same SHA-256.  That lets the catalog entry commit a stable fingerprint.
A sidecar ``igz_sunpath.zip.sha256`` is written next to the archive.

Usage (any platform)::

    python packaging/build_extension.py
    python packaging/build_extension.py --write-catalog

Requires only the Python standard library (3.11+).
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "igz_sunpath"
PACKAGE_DIR = ROOT / PACKAGE
DIST = ROOT / "dist"
ARCHIVE_NAME = f"{PACKAGE}.zip"

# The IngeTrazo version this release was tested with.
INGETRAZO_VERSION = "0.5.8"

# Documentation copied from the repository root into the package folder.
DOC_FILES = (
    "README.md",
    "README_ptBR.md",
    "CHANGELOG.md",
    "PUBLISHING.md",
    "LICENSE",
    "THIRD-PARTY.md",
)

# Folders shipped inside the package folder (relative to igz_sunpath/).
PACKAGE_DIRS = ("core", "icons", "i18n")

# Folders copied from the repository root into the package folder.
EXTRA_DIRS = ("screenshots",)

# Fixed timestamp keeps the archive byte-for-byte reproducible.
FIXED_DATE = (2026, 1, 1, 0, 0, 0)

CATALOG_FILE = ROOT / "packaging" / f"{PACKAGE}.toml"
SCREENSHOT = "igz_sunpath.png"

CATALOG = {
    "id": PACKAGE,
    "version": None,  # filled from __version__
    "author": "Ezequiel M. Rezende",
    "author_url": "https://github.com/em-rezende",
    "license": "GPL-3.0-or-later",
    "repository": "https://github.com/em-rezende/Ingetrazo-igz-sunpath",
    "download": None,  # filled by build()
    "sha256": None,  # filled by build()
    "ingetrazo": INGETRAZO_VERSION,
    "tags": ["architecture", "analysis", "rendering", "terrain"],
    "screenshot": SCREENSHOT,
    "name": {
        "es": "igz_sunpath · Trayectoria solar",
        "en": "igz_sunpath · Sun Path",
        "pt": "igz_sunpath · Trajetória solar",
    },
    "summary": {
        "es": "Barra de estudio solar: sombras, fecha y hora, calendario, "
              "vector solar 3D, domo solar con analemas, ubicación y norte, "
              "y exportación PNG de la vista.",
        "en": "Solar-study toolbar: shadows, date and time, calendar, 3D sun "
              "vector, solar dome with analemmas, site location and north, "
              "and PNG export of the view.",
        "pt": "Barra de estudo solar: sombras, data e hora, calendário, "
              "vetor solar 3D, domo solar com analemas, localização e norte, "
              "e exportação PNG da vista.",
    },
    "description": {
        "es": "Añade a IngeTrazo una barra Sun Path completa: interruptor de "
              "sombras, brújula en pantalla con deslizadores de fecha y hora, "
              "vector solar 3D, cúpula solar 3D con arcos mensuales, analemas "
              "y celdas clicables; diálogo Ajustar Sol con rotación del norte "
              "y localización integrada en el panel Terreno; exportación PNG "
              "con fondo blanco o transparente. El estado se guarda en el "
              "modelo y sobrevive a guardar y reabrir el .igz. Interfaz en 7 "
              "idiomas.",
        "en": "Adds a complete Sun Path toolbar to IngeTrazo: shadow toggle, "
              "on-screen compass with date and time sliders, 3D sun vector, "
              "3D solar dome with monthly arcs, analemmas and clickable "
              "cells; a Set Sun dialog with north rotation and a location "
              "box integrated with the Terreno panel; and PNG export with a "
              "white or transparent background. State is stored in the "
              "document and survives saving and reopening the .igz. UI in 7 "
              "languages.",
        "pt": "Adiciona ao IngeTrazo uma barra Sun Path completa: botão de "
              "sombras, bússola em tela com sliders de data e hora, vetor "
              "solar 3D, domo solar 3D com arcos mensais, analemas e células "
              "clicáveis; diálogo Ajustar Sol com rotação do norte e "
              "localização integrada ao painel Terreno; e exportação PNG com "
              "fundo branco ou transparente. O estado fica no documento e "
              "sobrevive a salvar e reabrir o .igz. Interface em 7 idiomas.",
    },
}


def read_version() -> str:
    """Read ``__version__`` from the package entry point without importing it."""
    source = (PACKAGE_DIR / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename=f"{PACKAGE}/__init__.py")
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if (isinstance(target, ast.Name) and target.id == "__version__"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            return node.value.value
    raise SystemExit(f"__version__ not found in {PACKAGE}/__init__.py")


def _collect(folder: Path, prefix: str) -> list[tuple[str, Path]]:
    """Collect files under ``folder`` as ``(arcname, source)`` pairs."""
    if not folder.is_dir():
        raise SystemExit(f"missing package folder: {folder.relative_to(ROOT)}/")
    found: list[tuple[str, Path]] = []
    for src in sorted(folder.rglob("*")):
        if not src.is_file():
            continue
        if "__pycache__" in src.parts or src.suffix in (".pyc", ".pyo"):
            continue
        found.append((f"{prefix}/{src.relative_to(folder).as_posix()}", src))
    return found


def package_members() -> list[tuple[str, Path]]:
    """Return ``(archive name, source path)`` pairs, sorted by archive name."""
    entry = PACKAGE_DIR / "__init__.py"
    if not entry.is_file():
        raise SystemExit(f"missing package file: {PACKAGE}/__init__.py")
    members: list[tuple[str, Path]] = [(f"{PACKAGE}/__init__.py", entry)]

    for name in DOC_FILES:
        src = ROOT / name
        if not src.is_file():
            raise SystemExit(f"missing documentation file: {name}")
        members.append((f"{PACKAGE}/{name}", src))

    for folder in PACKAGE_DIRS:
        members.extend(_collect(PACKAGE_DIR / folder, f"{PACKAGE}/{folder}"))

    for folder in EXTRA_DIRS:
        members.extend(_collect(ROOT / folder, f"{PACKAGE}/{folder}"))

    members.sort(key=lambda item: item[0])
    return members


def sha256_file(output: Path) -> Path:
    """Sidecar with the fingerprint in ``sha256sum`` format."""
    return output.with_name(output.name + ".sha256")


def write_sha256_file(output: Path, sha: str) -> Path:
    sidecar = sha256_file(output)
    sidecar.write_text(f"{sha}  {output.name}\n", encoding="ascii",
                       newline="\n")
    return sidecar


def build(output: Path | None = None) -> tuple[Path, str, int]:
    """Build the archive and return ``(path, sha256, size_bytes)``."""
    version = read_version()
    output = output or (DIST / ARCHIVE_NAME)
    output.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as zf:
        for arcname, src in package_members():
            info = zipfile.ZipInfo(arcname, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3          # Unix, so external_attr is used
            info.external_attr = 0o100644 << 16
            zf.writestr(info, src.read_bytes())

    data = output.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    write_sha256_file(output, sha)
    CATALOG["version"] = version
    CATALOG["sha256"] = sha
    CATALOG["download"] = (
        "https://github.com/em-rezende/Ingetrazo-igz-sunpath/releases/"
        f"download/v{version}/{ARCHIVE_NAME}")
    return output, sha, len(data)


def _toml_string(value: str) -> str:
    """A TOML basic string (JSON string syntax is a valid subset)."""
    return json.dumps(value, ensure_ascii=False)


def catalog_text(sha: str) -> str:
    """Render the catalog entry, ready to copy to extensions/<id>.toml."""
    version = read_version()
    lines = [
        "# Entry for the IngeTrazo community extension catalog",
        "# https://github.com/ingelibre/ingetrazo-extensions",
        "#",
        "# Generated by packaging/build_extension.py — copy it to",
        f"# extensions/{PACKAGE}.toml in a pull request.  The archive must be",
        f"# uploaded first as the v{version} GitHub Release asset named",
        f"# {ARCHIVE_NAME}.",
        "",
        f'id = {_toml_string(PACKAGE)}',
        f'version = {_toml_string(version)}',
        f'author = {_toml_string(CATALOG["author"])}',
        f'author_url = {_toml_string(CATALOG["author_url"])}',
        f'license = {_toml_string(CATALOG["license"])}',
        f'repository = {_toml_string(CATALOG["repository"])}',
        f'download = {_toml_string(CATALOG["download"])}',
        f'sha256 = {_toml_string(sha)}',
        f'ingetrazo = {_toml_string(CATALOG["ingetrazo"])}',
        "tags = [" + ", ".join(_toml_string(t) for t in CATALOG["tags"]) + "]",
        f'screenshot = {_toml_string(CATALOG["screenshot"])}',
        "",
    ]
    for section in ("name", "summary", "description"):
        lines.append(f"[{section}]")
        for lang in ("es", "en", "pt"):
            lines.append(f"{lang} = {_toml_string(CATALOG[section][lang])}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_catalog(sha: str) -> Path:
    CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_FILE.write_text(catalog_text(sha), encoding="utf-8", newline="\n")
    return CATALOG_FILE



def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=None,
                        help=f"archive path (default: dist/{ARCHIVE_NAME})")
    parser.add_argument("--write-catalog", action="store_true",
                        help=f"also write packaging/{PACKAGE}.toml")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed catalog hash matches a "
                             "fresh build")
    args = parser.parse_args(argv)

    if args.check:
        tmpdir = Path(tempfile.mkdtemp())
        tmp = tmpdir / ARCHIVE_NAME
        try:
            _, sha, _ = build(tmp)
        finally:
            sha256_file(tmp).unlink(missing_ok=True)
            tmp.unlink(missing_ok=True)
            tmpdir.rmdir()
        text = CATALOG_FILE.read_text(encoding="utf-8")
        match = re.search(r'^sha256 = "([0-9a-f]{64})"', text, re.MULTILINE)
        if not match or match.group(1) != sha:
            print(f"catalog hash is stale: expected {sha}", file=sys.stderr)
            return 1
        print(f"catalog hash OK: {sha}")
        return 0

    path, sha, size = build(args.output)
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    sidecar = sha256_file(path)
    print(f"Built {shown} ({size / 1024:.1f} KB)")
    print(f"sha256 = {sha}")
    print(f"Wrote {sidecar.relative_to(ROOT) if sidecar.is_relative_to(ROOT) else sidecar}")
    if args.write_catalog:
        catalog = write_catalog(sha)
        print(f"Wrote {catalog.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

