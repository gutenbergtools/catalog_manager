"""MARC 21 attribute edits."""

from sqlalchemy import func, select

from .. import catalog as c
from ..changelog import attribute_changelog
from ..clean import AttrForm, Bad
from .helpers import (
    Op,
    _child_val,
    _ids,
    _m,
    _refuse_stale,
    apply_row,
    refresh_book_title,
    snap_pk,
)


# Attributes

# Fields that are repeatable (R) in the MARC 21 spec, plus Project Gutenberg's
# own local tags, which the spec does not govern. Every other tag is
# nonrepeatable (NR), so a second value is refused on create.
REPEATABLE_TAGS = frozenset((
    20, 41, 43, 246, 247, 250, 260, 264, 300, 362,
    440, 490, 500, 501, 504, 505, 506, 508, 510, 511, 513,
    520, 524, 525, 526, 530, 533, 538, 546, 547, 550, 555,
    561, 563, 580, 583, 586,
    700, 710, 711, 720, 730, 740, 752,
    760, 762, 765, 767, 770, 772, 773, 774, 775, 776, 777,
    780, 785, 786, 787,
    800, 810, 811, 830, 856,
    901, 904, 908,
))


def _attr_val(session, action, data, before):
    after = _child_val(session, action, data, before, "attribute", "fk_books", "ebook", c.exists_book)
    if action == "delete":
        if (before or {}).get("fk_attriblist") == 245:
            raise Bad("The title field cannot be deleted. Edit the record title instead.")
        return after
    _refuse_stale(before, data, ("text", "nonfiling", "indicators", "fk_langs"))
    if (before or {}).get("fk_attriblist") == 245 and (after.get("text") or "") != ((before or {}).get("text") or ""):
        raise Bad("The title is edited in the record above.")
    tags = _m().Attriblist
    where = (tags.type == "unc") & (tags.pk != 245) if action == "create" else None
    if after["fk_attriblist"] not in _ids(session, tags.pk, where):
        raise Bad("Choose a MARC tag from the list.")
    if action == "create" and after["fk_attriblist"] not in REPEATABLE_TAGS:
        a = _m().Attribute
        if session.scalar(select(func.count()).where(a.fk_books == after["fk_books"], a.fk_attriblist == after["fk_attriblist"])):
            raise Bad("That field already has a value for this book. Edit the existing row instead.")
    after["nonfiling"] = after.get("nonfiling") or 0
    if after["nonfiling"] > len(after["text"]):
        raise Bad("Nonfiling characters cannot be longer than the text.")
    lang = after.get("fk_langs") or None
    if lang in ("", "undefined"):
        lang = None
    if lang and session.get(_m().Lang, lang) is None:
        raise Bad("That language is not in the catalog.")
    after["fk_langs"] = lang
    return after


def _attr_apply(session, action, before, after):
    row = apply_row(
        session,
        _m().Attribute,
        action,
        after,
        dict((k, after[k]) for k in ("fk_books", "fk_attriblist", "text", "nonfiling", "indicators", "fk_langs"))
        if action != "delete"
        else {},
    )
    tag = after.get("fk_attriblist") if action != "delete" else (before or {}).get("fk_attriblist")
    book = after.get("fk_books") or (before or {}).get("fk_books")
    if book and tag in (240, 245, 246):
        refresh_book_title(session, book)
    return row


Op(
    "attribute",
    form=AttrForm,
    snapshot=snap_pk(c.attribute_row),
    validate=_attr_val,
    apply=_attr_apply,
    changelog_sql=attribute_changelog,
)
