"""Camera-setup app router.
Re-exports router from server.py for backwards compatibility.
"""
from __future__ import annotations

from .server import router, app

__all__ = ['router', 'app']
