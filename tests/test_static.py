# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ezequiel M. Rezende
"""Static tests — standard library only, no Qt required.

Run with::

    python -m unittest discover -s tests -v

They check syntax, the plugin entry point, translation catalogs, icons,
documentation links, the catalog entry and the deterministic archive.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import string
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "igz_sunpath"
MAIN = ROOT / f"{PACKAGE}.py"
CATALOG = ROOT / "packaging" / f"{PACKAGE}.toml"
SCREENSHOTS = ROOT / "screenshots"

LANGS = ("de", "en", "es", "fr", "it", "pt-BR", "zh-CN")
ICONS = (
    "sunpath_arrow", "sunpath_calendar", "sunpath_center", "sunpath_dome",
    "sunpath_map", "sunpath_screenshot", "sunpath_shadows", "sunpath_tool",
    "sunpath_vector",
)
FREE_LICENCES = {
    "GPL-3.0-only", "GPL-3.0-or-later", "GPL-2.0-or-later",
    "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",
    "AGPL-3.0-only", "AGPL-3.0-or-later", "MIT", "BSD-2-Clause",
    "BSD-3-Clause", "Apache-2.0", "MPL-2.0", "ISC", "Zlib", "0BSD",
    "Unlicense", "CC0-1.0",
}
TAGS = {
    "architecture", "bim", "structures", "terrain", "drawing", "analysis",
    "import-export", "rendering", "fabrication", "productivity",
    "education", "other",
}


def build_module():
    path = ROOT / "packaging" / "build_extension.py"
    spec = importlib.util.spec_from_file_location("igz_build_extension", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_version() -> str:
    tree = ast.parse(MAIN.read_text(encoding="utf-8"), filename=MAIN.name)
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__version__"
                and isinstance(node.value, ast.Constant)):
            return str(node.value.value)
    raise AssertionError("__version__ not found")


def format_fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text)
            if name}


class TestSources(unittest.TestCase):
    def test_python_sources_compile(self):
        for path in sorted(ROOT.rglob("*.py")):
            if any(part in {".git", "dist", "__pycache__"} for part in path.parts):
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_package_defines_setup_in_init(self):
        tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf-8"))
        funcs = [n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "setup"]
        self.assertEqual(len(funcs), 1, "setup(app) must be defined in __init__.py")
        self.assertEqual([a.arg for a in funcs[0].args.args], ["app"])

    def test_main_module_defines_setup(self):
        tree = ast.parse(MAIN.read_text(encoding="utf-8"))
        self.assertTrue(any(isinstance(n, ast.FunctionDef) and n.name == "setup"
                            for n in tree.body))

    def test_debug_is_off(self):
        text = MAIN.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^DEBUG = False$")

    def test_version_is_consistent(self):
        version = read_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn(f"**Version:** {version}", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f"**Versão:** {version}", (ROOT / "README_ptBR.md").read_text(encoding="utf-8"))
        self.assertIn(f"## [{version}]", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
        with CATALOG.open("rb") as fh:
            entry = tomllib.load(fh)
        self.assertEqual(entry["version"], version)
        self.assertIn(f"v{version}", entry["download"])

    def test_source_translation_keys_exist(self):
        tree = ast.parse(MAIN.read_text(encoding="utf-8"))
        keys = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "_t" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                keys.add(node.args[0].value)
        with (ROOT / "i18n" / "en.json").open(encoding="utf-8") as fh:
            catalog = json.load(fh)
        self.assertEqual(sorted(keys - set(catalog)), [])

    def test_no_hardcoded_windows_temp(self):
        text = MAIN.read_text(encoding="utf-8")
        self.assertNotIn(r"C:\Temp", text)
        self.assertIn("tempfile.gettempdir()", text)


class TestI18n(unittest.TestCase):
    def _load(self, code: str):
        duplicates = []

        def hook(pairs):
            seen = set()
            for key, _ in pairs:
                if key in seen:
                    duplicates.append(key)
                seen.add(key)
            return dict(pairs)

        path = ROOT / "i18n" / f"{code}.json"
        data = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=hook)
        self.assertEqual(duplicates, [], f"duplicate keys in {path.name}")
        return data

    def test_all_catalogs_have_the_same_keys(self):
        base = self._load("en")
        for code in LANGS:
            with self.subTest(lang=code):
                data = self._load(code)
                self.assertEqual(sorted(set(base) - set(data)), [])
                self.assertEqual(sorted(set(data) - set(base)), [])
                self.assertTrue(all(isinstance(v, str) and v.strip()
                                    for v in data.values()))

    def test_placeholders_are_preserved(self):
        base = self._load("en")
        for code in LANGS:
            data = self._load(code)
            for key, value in base.items():
                if key == "_language":
                    continue
                with self.subTest(lang=code, key=key[:40]):
                    self.assertEqual(format_fields(value), format_fields(data[key]))

    def test_expected_languages(self):
        found = {p.stem for p in (ROOT / "i18n").glob("*.json")}
        self.assertEqual(found, set(LANGS))


class TestIcons(unittest.TestCase):
    def test_dark_and_light_variants_exist(self):
        for base in ICONS:
            for suffix in ("", "_light"):
                path = ROOT / "icons" / f"{base}{suffix}.svg"
                with self.subTest(icon=path.name):
                    self.assertTrue(path.is_file())
                    self.assertIn("<svg", path.read_text(encoding="utf-8")[:500])


class TestDocs(unittest.TestCase):
    def test_markdown_fences_are_balanced(self):
        for name in ("README.md", "README_ptBR.md", "PUBLISHING.md",
                     "CHANGELOG.md", "THIRD-PARTY.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            fences = sum(1 for line in text.splitlines()
                         if line.strip().startswith("```"))
            with self.subTest(file=name):
                self.assertEqual(fences % 2, 0, "unbalanced code fences")

    def test_local_links_and_images_exist(self):
        pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
        for name in ("README.md", "README_ptBR.md", "PUBLISHING.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for target in pattern.findall(text):
                target = target.strip().split("#", 1)[0]
                if not target or target.startswith(("http://", "https://",
                                                     "mailto:", "#")):
                    continue
                with self.subTest(file=name, target=target):
                    self.assertTrue((ROOT / target).exists(),
                                    f"{name}: missing {target}")

    def test_repository_url_is_documented(self):
        url = "https://github.com/em-rezende/Ingetrazo-igz-sunpath"
        for name in ("README.md", "README_ptBR.md", "PUBLISHING.md"):
            with self.subTest(file=name):
                self.assertIn(url, (ROOT / name).read_text(encoding="utf-8"))



class TestCatalog(unittest.TestCase):
    def setUp(self):
        with CATALOG.open("rb") as fh:
            self.entry = tomllib.load(fh)

    def test_required_fields_and_values(self):
        entry = self.entry
        for key in ("id", "name", "summary", "author", "license",
                    "repository", "version", "download", "sha256",
                    "ingetrazo", "tags"):
            self.assertIn(key, entry)
        self.assertRegex(entry["id"], r"^[a-z][a-z0-9_]{1,47}$")
        self.assertEqual(entry["id"], PACKAGE)
        self.assertIn(entry["license"], FREE_LICENCES)
        self.assertRegex(entry["version"], r"^\d+(\.\d+){0,3}([.-]?[a-z0-9]+)?$")
        self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(entry["ingetrazo"], r"^\d+\.\d+(\.\d+){0,2}$")
        self.assertTrue(1 <= len(entry["tags"]) <= 4)
        self.assertEqual(sorted(set(entry["tags"]) - TAGS), [])
        self.assertTrue(entry["download"].startswith("https://"))
        self.assertTrue(entry["download"].endswith(".zip"))
        self.assertNotRegex(entry["download"], r"/(main|master|develop|dev)/")

    def test_translations(self):
        for section in ("name", "summary", "description"):
            self.assertIn(section, self.entry)
            for lang in ("es", "en", "pt"):
                with self.subTest(section=section, lang=lang):
                    self.assertTrue(self.entry[section].get(lang, "").strip())
        for lang in ("es", "en", "pt"):
            self.assertLessEqual(len(self.entry["summary"][lang]), 240)

    def test_screenshot(self):
        shot = SCREENSHOTS / self.entry["screenshot"]
        self.assertTrue(shot.is_file())
        self.assertLessEqual(shot.stat().st_size, 600 * 1024)
        self.assertTrue(shot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))

    def test_hash_matches_a_fresh_build(self):
        module = build_module()
        with tempfile.TemporaryDirectory() as tmp:
            _, sha, size = module.build(Path(tmp) / "igz_sunpath.zip")
        self.assertEqual(sha, self.entry["sha256"])
        self.assertLess(size, 5 * 1024 * 1024)


class TestArchive(unittest.TestCase):
    def test_layout_and_determinism(self):
        module = build_module()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "igz_sunpath.zip"
            _, sha1, _ = module.build(out)
            data1 = out.read_bytes()
            _, sha2, _ = module.build(out)
            data2 = out.read_bytes()
            self.assertEqual(sha1, sha2)
            self.assertEqual(data1, data2)
            with zipfile.ZipFile(out) as zf:
                names = [n for n in zf.namelist() if not n.endswith("/")]
                tops = {n.split("/", 1)[0] for n in names}
                self.assertEqual(tops, {PACKAGE})
                self.assertIn(f"{PACKAGE}/__init__.py", names)
                self.assertIn(f"{PACKAGE}/igz_sunpath.py", names)
                self.assertIn(f"{PACKAGE}/i18n/en.json", names)
                self.assertIn(f"{PACKAGE}/icons/sunpath_dome.svg", names)
                for name in names:
                    self.assertNotIn("..", Path(name).parts)
                    self.assertNotIn("__pycache__", name)
                    self.assertFalse(name.endswith((".pyc", ".pyo")))
                total = sum(info.file_size for info in zf.infolist())
                self.assertLess(total, 5 * 1024 * 1024)

    def test_zip_entry_point_is_readable_by_the_catalog(self):
        module = build_module()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "igz_sunpath.zip"
            module.build(out)
            with zipfile.ZipFile(out) as zf:
                source = zf.read(f"{PACKAGE}/__init__.py").decode("utf-8")
        tree = ast.parse(source)
        self.assertTrue(any(isinstance(node, ast.FunctionDef)
                            and node.name == "setup" for node in tree.body))


if __name__ == "__main__":
    unittest.main(verbosity=2)

