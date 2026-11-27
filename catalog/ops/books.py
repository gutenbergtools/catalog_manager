"""Book edits: the record, its authors and its simple links."""

from datetime import date

from django.utils.dateparse import parse_date
from sqlalchemy import and_, select, text

from .. import catalog as c
from ..changelog import book_author_changelog, book_changelog
from ..clean import LANG_RE, LOCC_RE, BAForm, BookForm, CodeField, Bad, cleaned
from .helpers import (
    Op,
    _ids,
    _m,
    _model_exists,
    _pick,
    _refuse_stale,
    add_link,
    apply_row,
    exists_state,
    link_apply,
    refresh_book_title,
    snap_pk,
)


# Book

def article_length(title):
    """Nonfiling seed for a new title: the length of a leading English article."""
    first, _, rest = (title or "").partition(" ")
    return len(first) + 1 if first.lower() in ("the", "an", "a") and rest else 0


def _book_get(session, pk):
    row = _pick(c.book_row(session, pk), ("pk", "release_date", "title", "copyrighted", "updatemode"))
    if row:
        a = _m().Attribute
        row["nonfiling"] = session.scalar(select(a.nonfiling).where(a.fk_books == pk, a.fk_attriblist == 245)) or 0
    return row


_book_snap = snap_pk(_book_get)


def _book_val(session, action, data, before):
    if action == "delete":
        raise Bad("Books cannot be deleted here.")
    exists_state(action, before, "ebook")
    _refuse_stale(before, data, ("release_date", "title", "nonfiling", "copyrighted", "updatemode"))
    data["release_date"] = data.get("release_date") or date.today().isoformat()
    data["copyrighted"] = data.get("copyrighted") or 0
    data["updatemode"] = data.get("updatemode") or 0
    data["nonfiling"] = data.get("nonfiling") or 0
    if not (data.get("title") or "").strip():
        raise Bad("Enter a title.")
    if data["nonfiling"] > len(data["title"]):
        raise Bad("Nonfiling characters cannot be longer than the title.")
    return data


def _book_apply(session, action, before, after):
    parsed = parse_date(str(after.get("release_date") or date.today().isoformat())[:10])
    if parsed is None:
        raise Bad("Enter the official release date.")
    row = apply_row(
        session,
        _m().Book,
        action,
        after,
        {
            "release_date": parsed,
            "title": after.get("title") or "",
            "copyrighted": after.get("copyrighted") or 0,
            "updatemode": after.get("updatemode") or 0,
        },
    )
    if action == "create" or (
        action == "update"
        and ((before or {}).get("title") != after.get("title") or (before or {}).get("nonfiling") != after.get("nonfiling"))
    ):
        # books.title is only a cache of the MARC 245 value, so edit the source
        # field too or the trigger would immediately restore the old title.
        result = session.execute(
            text(
                "update attributes set text = :t, nonfiling = :n "
                "where fk_books = :b and fk_attriblist = 245"
            ),
            {"t": after.get("title") or "", "n": after.get("nonfiling") or 0, "b": after["pk"]},
        )
        if not result.rowcount:
            session.execute(
                text(
                    "insert into attributes (fk_books, fk_attriblist, text, nonfiling) "
                    "values (:b, 245, :t, :n)"
                ),
                {
                    "b": after["pk"],
                    "t": after.get("title") or "",
                    "n": after.get("nonfiling") or article_length(after.get("title")),
                },
            )
        refresh_book_title(session, after["pk"])
    return row


Op(
    "book",
    form=BookForm,
    optional_pk=False,
    snapshot=_book_snap,
    validate=_book_val,
    apply=_book_apply,
    changelog_sql=book_changelog,
)


# Book links

add_link("book_subject", "t_mn_books_subjects", "fk_subjects", "subject", c.exists_subject)
add_link("book_lang", "t_mn_books_langs", "fk_langs", "language", _model_exists("Lang"), CodeField(LANG_RE))
add_link(
    "book_locc",
    "t_mn_books_loccs",
    "fk_loccs",
    "LoC class",
    _model_exists("Locc"),
    CodeField(LOCC_RE, case="upper"),
)
add_link("book_category", "t_mn_books_categories", "fk_categories", "category", _model_exists("Category", int))


# Book author

def _ba_snap(session, data):
    data = dict(data)
    data["fk_roles"] = data.get("fk_roles") or "cr"
    bound = cleaned(BAForm, data)
    role = bound.get("was_roles") or bound["fk_roles"]
    row = c.linked(
        session,
        _m().BookAuthor.__table__,
        bound["fk_books"],
        "fk_authors",
        bound["fk_authors"],
        {"fk_roles": role},
    )
    return (
        None
        if row is None
        else {
            "fk_books": bound["fk_books"],
            "fk_authors": bound["fk_authors"],
            "fk_roles": row["fk_roles"],
            "heading": row.get("heading"),
        }
    )


def _ba_val(session, action, data, before):
    if not c.exists_book(session, data["fk_books"]):
        raise Bad("No such ebook.")
    if not c.exists_author(session, data["fk_authors"]):
        raise Bad("That author is not in the catalog.")
    role = data.get("fk_roles") or (before or {}).get("fk_roles") or "cr"
    if role not in _ids(session, _m().Role.pk):
        raise Bad("That author role is not in the catalog.")
    if action == "link" and before:
        raise Bad("Already linked.")
    if action in ("unlink", "update") and not before:
        raise Bad("Not linked.")
    return {
        "fk_books": data["fk_books"],
        "fk_authors": data["fk_authors"],
        "fk_roles": role,
        "heading": data.get("heading") if data.get("heading") is not None else 1,
    }


def _ba_apply(session, action, before, after):
    table = _m().BookAuthor.__table__
    keys = {"fk_books": after["fk_books"], "fk_authors": after["fk_authors"], "fk_roles": after["fk_roles"]}
    if action == "update":
        where = and_(
            table.c.fk_books == after["fk_books"],
            table.c.fk_authors == after["fk_authors"],
            table.c.fk_roles == (before or after)["fk_roles"],
        )
        session.execute(table.update().where(where).values(fk_roles=after["fk_roles"], heading=after["heading"]))
    else:
        link_apply(session, table, action == "link", keys, {"heading": after["heading"]})
    return after


Op(
    "book_author",
    form=BAForm,
    snapshot=_ba_snap,
    validate=_ba_val,
    apply=_ba_apply,
    changelog_sql=book_author_changelog,
)
