# =========================================================================
# Pasta: igz_sunpath/core/
# Arquivo: i18n_loader.py
# Descrição: Carregamento de traduções via JSON com cache.
# =========================================================================
import json
import os
import traceback

from . import state

_TRANSLATIONS_CACHE = {}

_LOCAL_MONTHS = {
    "en":    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "es":    ["ene", "feb", "mar", "abr", "may", "jun",
              "jul", "ago", "sep", "oct", "nov", "dic"],
    "id":    ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
              "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
    "it":    ["gen", "feb", "mar", "apr", "mag", "giu",
              "lug", "ago", "set", "ott", "nov", "dic"],
    "pt-BR": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
              "Jul", "Ago", "Set", "Out", "Nov", "Dez"],
    "de":    ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
              "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
    "fr":    ["jan", "fév", "mar", "avr", "mai", "jun",
              "jul", "aoû", "sep", "oct", "nov", "déc"],
    "zh-CN": ["1月", "2月", "3月", "4月", "5月", "6月",
              "7月", "8月", "9月", "10月", "11月", "12月"],
}

try:
    from core.i18n import current_language as _it_language
except Exception:
    def _it_language():
        return "en"


def _i18n_dir():
    return os.path.join(state.get_here(), "i18n")


def _load_translation_file(lang_code: str) -> dict:
    if lang_code in _TRANSLATIONS_CACHE:
        return _TRANSLATIONS_CACHE[lang_code]
    file_path = os.path.join(_i18n_dir(), f"{lang_code}.json")
    if os.path.isfile(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _TRANSLATIONS_CACHE[lang_code] = data
                return data
        except Exception:
            traceback.print_exc()
    _TRANSLATIONS_CACHE[lang_code] = {}
    return {}


def _t(text: str) -> str:
    lang = _it_language()
    trans = _load_translation_file(lang)
    if text in trans:
        return trans[text]
    if lang != "en":
        en = _load_translation_file("en")
        if text in en:
            return en[text]
    return text


def _months():
    return _LOCAL_MONTHS.get(_it_language(), _LOCAL_MONTHS["en"])