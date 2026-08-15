"""Public metadata for the NR RAN simulator foundation."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("nr-ran-sim")
except PackageNotFoundError:  # pragma: no cover - only possible outside an installed checkout
    __version__ = "0+unknown"

__all__ = ["__version__"]
