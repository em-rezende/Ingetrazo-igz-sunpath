# =========================================================================
# IngeTrazo — "Sun Path" plugin package
# =========================================================================
"""IngeTrazo extension package for the Sun Path toolbar.

IngeTrazo imports this package and calls :func:`setup` with the application
object.  ``setup`` is defined here (not merely imported) so that static
checkers such as the community catalog can find the entry point in
``__init__.py``.
"""
from .igz_sunpath import __version__, setup as _setup

__all__ = ["setup", "__version__"]


def setup(app):
    """Entry point called by IngeTrazo when the extension is loaded."""
    return _setup(app)

