# =========================================================================
# Pasta: igz_sunpath/
# Arquivo: __init__.py
# Descrição: Ponto de entrada do plugin igz_sunpath.
# =========================================================================
import os

_HERE = os.path.dirname(os.path.abspath(__file__))

# Inicializa o pacote core (define _HERE e i18n).
# Os módulos usam imports relativos (``.core``), então não é preciso
# alterar ``sys.path`` — fazer isso colocaria ``igz_sunpath/core`` no
# lugar do pacote ``core`` do próprio IngeTrazo.
from .core import state
state.set_here(_HERE)

from .core import toolbar

__version__ = "1.1.0"

__all__ = ["setup", "__version__"]


def setup(app):
    """Ponto de entrada chamado pelo IngeTrazo ao carregar a extensão."""
    try:
        toolbar.setup(app)
    except Exception:
        import traceback
        traceback.print_exc()