"""Author edits: the author record and its aliases."""

from sqlalchemy import delete

from .. import catalog as c
from ..clean import AliasForm, AuthorForm, Bad
from .helpers import (
    Op,
    _child_val,
    _m,
    _need,
    _refuse_stale,
    apply_row,
    exists_state,
    snap_pk,
)


# Author

def _author_val(session, action, data, before):
    if action == "delete":
        _need(before, "author")
        if c.author_book_count(session, data["pk"]):
            raise Bad("Unlink this author from every book before deleting.")
        return {"pk": data["pk"]}
    exists_state(action, before, "author")
    _refuse_stale(before, data, ("author", "born_floor", "born_ceil", "died_floor", "died_ceil", "note"))
    return data


def _author_apply(session, action, before, after):
    m = _m()
    if action == "delete":
        session.execute(delete(m.Alias).where(m.Alias.fk_authors == after["pk"]))
        session.execute(delete(m.AuthorUrl).where(m.AuthorUrl.fk_authors == after["pk"]))
        session.execute(delete(m.Author).where(m.Author.id == after["pk"]))
        return after
    return apply_row(
        session,
        m.Author,
        action,
        after,
        {
            "name": after["author"],
            "birthdate": after["born_floor"],
            "birthdate2": after["born_ceil"],
            "deathdate": after["died_floor"],
            "deathdate2": after["died_ceil"],
            "note": after["note"] or None,
        },
        "id",
    )


Op(
    "author",
    form=AuthorForm,
    snapshot=snap_pk(c.author_row),
    validate=_author_val,
    apply=_author_apply,
)

def _alias_val(session, action, data, before):
    after = _child_val(session, action, data, before, "alias", "fk_authors", "author", c.exists_author)
    if action == "delete":
        return after
    _refuse_stale(before, data, ("alias", "heading"))
    return after


def _alias_apply(session, action, before, after):
    values = (
        {"fk_authors": after["fk_authors"], "alias": after.get("alias"), "heading": after.get("heading")}
        if action != "delete"
        else {}
    )
    return apply_row(session, _m().Alias, action, after, values)


Op(
    "alias",
    form=AliasForm,
    snapshot=snap_pk(c.alias_row),
    validate=_alias_val,
    apply=_alias_apply,
)
