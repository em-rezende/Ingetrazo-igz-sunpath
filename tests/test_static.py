# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Ezequiel M. Rezende
"""Static tests — standard library only, no Qt required.

Run with::

    python -m unittest discover -s tests -v

They check syntax, the package entry point, translation catalogs, icon
references, version consistency, the catalog entry and the deterministic
archive built by ``packaging/build_extension.py``.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import string
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "igz_sunpath"
PACKAGE_DIR = ROOT / PACKAGE
ENTRY = PACKAGE_DIR / "__init__.py"
CATALOG = ROOT / "packaging" / f"{PACKAGE}.toml"
SCREENSHOTS = ROOT / "screenshots"

LANGS = ("de", "en", "es", "fr", "it", "pt-BR", "zh-CN")
# Icons whose absence is handled by a documented fallback in the code.
OPTIONAL_ICONS = {"sunpath_cursor", "sunpath_target"}
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
REQUIRED_ARCHIVE_MEMBERS = (
    f"{PACKAGE}/__init__.py",
    f"{PACKAGE}/README.md",
    f"{PACKAGE}/CHANGELOG.md",
    f"{PACKAGE}/PUBLISHING.md",
    f"{PACKAGE}/LICENSE",
    f"{PACKAGE}/THIRD-PARTY.md",
    f"{PACKAGE}/core/__init__.py",
    f"{PACKAGE}/core/toolbar.py",
    f"{PACKAGE}/core/i18n_loader.py",
    f"{PACKAGE}/i18n/en.json",
    f"{PACKAGE}/i18n/zh-CN.json",
    f"{PACKAGE}/icons/sunpath_dome.svg",
    f"{PACKAGE}/screenshots/igz_sunpath.png",
)
METADATA_KEYS = {"_comment", "_language"}


def build_module():
    path = ROOT / "packaging" / "build_extension.py"
    spec = importlib.util.spec_from_file_location("igz_build_extension", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_version() -> str:
    tree = ast.parse(ENTRY.read_text(encoding="utf-8"), filename=str(ENTRY))
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


def package_python_files():
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path


class TestSources(unittest.TestCase):
    def test_python_sources_compile(self):
        for path in sorted(ROOT.rglob("*.py")):
            if any(part in {".git", "dist", "__pycache__", ".venv"}
                   for part in path.parts):
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_package_defines_setup_in_init(self):
        tree = ast.parse(ENTRY.read_text(encoding="utf-8"))
        funcs = [n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "setup"]
        self.assertEqual(len(funcs), 1, "setup(app) must be defined in __init__.py")
        self.assertEqual([a.arg for a in funcs[0].args.args], ["app"])

    def test_init_does_not_touch_sys_path(self):
        text = ENTRY.read_text(encoding="utf-8")
        self.assertNotIn("sys.path.insert", text)
        self.assertNotIn("import sys", text)

    def test_package_modules_are_present(self):
        expected = {
            "state", "toolbar", "panel", "overlay", "overlay_paint",
            "dome_geometry", "solar_math", "shadows", "georef",
            "scene_state", "sun_animator", "export_dialog", "ffmpeg",
            "capture", "i18n_loader",
        }
        present = {p.stem for p in (PACKAGE_DIR / "core").glob("*.py")}
        self.assertEqual(present - {"__init__"}, expected)

    def test_no_absolute_import_of_local_modules(self):
        local = {p.stem for p in package_python_files()}
        local.discard("__init__")
        for path in package_python_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    top = (node.module or "").split(".")[0]
                    with self.subTest(path=path.name, module=top):
                        self.assertNotIn(top, local,
                                         f"{path.name} must import siblings "
                                         f"relatively")

    def test_debug_is_off(self):
        text = (PACKAGE_DIR / "core" / "state.py").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^DEBUG = False$")


class TestTranslations(unittest.TestCase):
    def load(self, lang: str) -> dict:
        path = PACKAGE_DIR / "i18n" / f"{lang}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_catalogs_are_valid_and_complete(self):
        en = self.load("en")
        en_keys = set(en) - METADATA_KEYS
        self.assertGreater(len(en_keys), 80)
        for lang in LANGS:
            with self.subTest(lang=lang):
                path = PACKAGE_DIR / "i18n" / f"{lang}.json"
                self.assertTrue(path.is_file(), f"missing {path.name}")
                data = self.load(lang)
                keys = set(data) - METADATA_KEYS
                self.assertEqual(keys, en_keys,
                                 f"{path.name} keys differ from en.json")
                for key in en_keys:
                    self.assertTrue(str(data[key]).strip(),
                                    f"{path.name}: empty value for {key!r}")

    def test_placeholders_match_english(self):
        en = self.load("en")
        for lang in LANGS:
            data = self.load(lang)
            for key, value in en.items():
                if key in METADATA_KEYS:
                    continue
                with self.subTest(lang=lang, key=key):
                    self.assertEqual(format_fields(str(data[key])),
                                     format_fields(value))

    def test_language_codes(self):
        self.assertEqual(self.load("zh-CN")["_language"], "zh-CN")
        self.assertEqual(self.load("pt-BR")["_language"], "pt-BR")

    def test_loader_accepts_every_shipped_language(self):
        loader = PACKAGE_DIR / "core" / "i18n_loader.py"
        text = loader.read_text(encoding="utf-8")
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertIn(f'"{lang}"', text)


class TestIcons(unittest.TestCase):
    def test_referenced_icons_exist(self):
        used = set()
        for path in package_python_files():
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                    r"load_(?:themed_icon|custom_cursor)\(\s*\"([a-z0-9_]+)\"",
                    text):
                used.add(match.group(1))
            for line in text.splitlines():
                if "make_action(" in line:
                    used.update(re.findall(r'"(sunpath_[a-z0-9_]+)"', line))
        icons = PACKAGE_DIR / "icons"
        for name in sorted(used - OPTIONAL_ICONS):
            with self.subTest(icon=name):
                self.assertTrue((icons / f"{name}.svg").is_file(),
                                f"missing icon {name}.svg")

    def test_icons_are_valid_svg(self):
        for path in sorted((PACKAGE_DIR / "icons").glob("*.svg")):
            with self.subTest(icon=path.name):
                head = path.read_text(encoding="utf-8")[:400].lower()
                self.assertIn("<svg", head)


class TestDocumentation(unittest.TestCase):
    def test_version_is_consistent(self):
        version = read_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        self.assertIn(f"**Version:** {version}",
                      (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(f"**Versão:** {version}",
                      (ROOT / "README_ptBR.md").read_text(encoding="utf-8"))
        self.assertIn(f"## [{version}]",
                      (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_local_markdown_links_exist(self):
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for name in ("README.md", "README_ptBR.md", "PUBLISHING.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            for target in pattern.findall(text):
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                clean = target.split("#", 1)[0]
                if not clean:
                    continue
                with self.subTest(doc=name, target=target):
                    self.assertTrue((ROOT / clean).exists(),
                                    f"{name}: broken link {target}")



class TestCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with CATALOG.open("rb") as fh:
            cls.entry = tomllib.load(fh)

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
        self.assertEqual(entry["version"], read_version())

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
            out = Path(tmp) / "igz_sunpath.zip"
            _, sha, size = module.build(out)
            sidecar = module.sha256_file(out)
            self.assertTrue(sidecar.is_file())
            self.assertEqual(sidecar.read_text(encoding="ascii").split()[0], sha)
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
                for member in REQUIRED_ARCHIVE_MEMBERS:
                    self.assertIn(member, names)
                self.assertNotIn(f"{PACKAGE}/igz_sunpath.py", names)
                for name in names:
                    self.assertNotIn("..", Path(name).parts)
                    self.assertNotIn("__pycache__", name)
                    self.assertFalse(name.endswith((".pyc", ".pyo", ".cdr")))
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

