"""Simple entity edits: subjects, categories, languages and LoC classes."""

from sqlalchemy import func, select

from ..clean import LOCC_RE, LangForm, entity_form
from .helpers import _m, add_entity


# Entities


def _in_use(table_name, fk):
    """Count link rows still pointing at an entity, for add_entity's delete check."""
    def in_use(session, pk):
        table = getattr(_m(), table_name)
        return session.scalar(select(func.count()).select_from(table).where(getattr(table.c, fk) == pk))
    return in_use


def _lang_in_use(session, pk):
    """A language is also in use while any MARC attribute still references it."""
    m = _m()
    if session.scalar(select(func.count()).select_from(m.t_mn_books_langs).where(m.t_mn_books_langs.c.fk_langs == pk)):
        return True
    return session.scalar(select(func.count()).select_from(m.Attribute).where(m.Attribute.fk_langs == pk))


add_entity("subject", "Subject", "id", "subject", entity_form("subject"), in_use=_in_use("t_mn_books_subjects", "fk_subjects"))
add_entity("category", "Category", "pk", "category", entity_form("category"), in_use=_in_use("t_mn_books_categories", "fk_categories"))
add_entity(
    "lang",
    "Lang",
    "id",
    "language",
    LangForm,
    str_pk=True,
    in_use=_lang_in_use,
    in_use_msg="Unlink this language from every book and MARC field before deleting.",
)
add_entity(
    "locc",
    "Locc",
    "id",
    "locc",
    entity_form("locc", str_pk=True, regex=LOCC_RE, case="upper"),
    str_pk=True,
    in_use=_in_use("t_mn_books_loccs", "fk_loccs"),
)
