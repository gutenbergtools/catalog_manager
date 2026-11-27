"""Catalog edit operations, grouped by the page that uses them.

Importing this package registers every op in :data:`OPS`; callers only need
the small API re-exported here.
"""

from . import attributes, authors, books, entities  # noqa: F401  (register the ops)
from .helpers import ACTIONS, OPS, Op, add_entity, add_link, get

__all__ = ["ACTIONS", "OPS", "Op", "add_entity", "add_link", "get"]
