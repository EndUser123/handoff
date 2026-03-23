"""Core namespace package for import redirection."""

from __future__ import annotations

# Make this a namespace package
__path__ = __import__("pkgutil").extend_path(__path__, __name__)
