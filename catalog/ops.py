"""Catalog operations: forms, validation and persistence for every edit."""

from datetime import date

from django import forms
from django.utils.dateparse import parse_date
from sqlalchemy import and_, delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from . import catalog as c
from .clean import (
    LANG_RE,
    LOCC_RE,
    AliasForm,
    AttrForm,
    AuthorForm,
    Bad,
    BAForm,
    BookForm,
    CodeField,
    F,
    LangForm,
    cleaned,
    entity_form,
    jsonable,
    stale,
)

# Framework

OPS = {}
ACTIONS = ("create", "update", "delete", "link", "unlink")


def get(name):
    op = OPS.get(name)
    if not op:
        raise Bad("Unknown change type.")
    return op


class Op:
    def __init__(
        self,
        name,
        form=None,
        domain="catalog",
        snapshot=None,
        validate=None,
        apply=None,
        compat_sql=None,
        keep=None,
        optional_pk=True,
    ):
        self.name, self.domain, self.form = name, domain, form
        self.fields = tuple(form.base_fields) if form else ()
        self.keep, self.optional_pk = keep, optional_pk
        self._snap, self._val, self._apply = snapshot, validate, apply
        self._sql = compat_sql
        OPS[name] = self

    def parse(self, post):
        return dict((f, post.get(f, "")) for f in self.fields)

    def snapshot(self, session, data):
        return self._snap(session, data) if self._snap else None

    def validate(self, session, action, data, before):
        bound = cleaned(self.form, data, action, keep=self.keep, optional_pk=self.optional_pk)
        after = jsonable(self._val(session, action, bound, before))
        return {key: value for key, value in after.items() if not key.startswith("was_")}

    def apply(self, session, action, before, after):
        return self._apply(session, action, before, after)

    def compat_sql(self, action, before, after):
        return self._sql(action, before, after) if self._sql else None


# Helpers

_m = c._models


def _ids(session, column, where=None):
    return set(session.scalars(select(column) if where is None else select(column).where(where)).all())


def _pick(row, keys):
    return None if row is None else {key: row[key] for key in keys}


def _need(before, kind):
    if not before:
        raise Bad("No such %s." % kind)


def _refuse_stale(before, data, keys):
    if stale(before, data, keys):
        raise Bad("This record changed after you opened it. Reload, then save again.")


def _sql_str(value):
    return str(value or "").replace("'", "''")


def apply_row(session, model, action, after, values, pk_attr="pk"):
    if action == "delete":
        session.execute(delete(model).where(getattr(model, pk_attr) == after["pk"]))
        return after
    if action == "create":
        kwargs = dict(values)
        if after.get("pk") is not None:
            kwargs[pk_attr] = after["pk"]
        row = model(**kwargs)
        session.add(row)
        session.flush()
        after["pk"] = getattr(row, pk_attr)
        return after
    row = session.get(model, after["pk"])
    for key, value in values.items():
        setattr(row, key, value)
    return after


def link_apply(session, table, linking, keys, values=None):
    """Insert a link row (idempotent) or delete it by its key columns."""
    if linking:
        session.execute(insert(table).values(**keys, **(values or {})).on_conflict_do_nothing())
    else:
        session.execute(delete(table).where(and_(*(getattr(table.c, key) == value for key, value in keys.items()))))


def snap_pk(getter):
    def snapshot(session, data):
        raw = str(data.get("pk") or "").strip()
        if not raw:
            return None
        try:
            pk = int(raw)
        except ValueError:
            pk = raw
        return getter(session, pk)

    return snapshot


def exists_state(action, before, kind):
    if action in ("create", "link") and before:
        raise Bad("Already linked." if action == "link" else "That %s already exists." % kind)
    if action in ("update", "unlink", "delete") and not before:
        raise Bad("Not linked." if action == "unlink" else "No such %s." % kind)


def _child_val(session, action, data, before, kind, fk, fk_name, exists):
    if not exists(session, data[fk]):
        raise Bad("No such %s." % fk_name)
    if action == "delete":
        _need(before, kind)
        return {"pk": data["pk"], fk: data[fk]}
    return data


def refresh_book_title(session, book_pk):
    """Recompute books.title/nonfiling from MARC 240/245/246.

    The catalogue database derives books.title with a trigger, so touching the
    row is how a changed MARC title becomes visible.
    """
    session.execute(text("update books set title = title where pk = :pk"), {"pk": book_pk})


# Factories

def add_link(name, table_fn, field, other_name, exists, other_field=None):
    form = F(
        **{
            "fk_books": forms.IntegerField(min_value=1),
            field: other_field or forms.IntegerField(min_value=1),
        }
    )

    def snapshot(session, data):
        book, other = data.get("fk_books"), data.get(field)
        if book in (None, "") or other in (None, ""):
            return None
        bound = cleaned(form, data)
        row = c.linked(session, table_fn(), bound["fk_books"], field, bound[field])
        return None if row is None else {"fk_books": bound["fk_books"], field: bound[field]}

    def validate(session, action, data, before):
        if not c.exists_book(session, data["fk_books"]):
            raise Bad("No such ebook.")
        if not exists(session, data[field]):
            raise Bad("That %s is not in the catalog." % other_name)
        exists_state(action, before, other_name)
        return {"fk_books": data["fk_books"], field: data[field]}

    def apply(session, action, before, after):
        link_apply(session, table_fn(), action == "link", {"fk_books": after["fk_books"], field: after[field]})
        return after

    Op(
        name,
        form=form,
        snapshot=snapshot,
        validate=validate,
        apply=apply,
    )


def add_entity(name, model, pk_name, label_field, form, str_pk=False, in_use=None, in_use_msg=None):
    def snapshot(session, data):
        raw = data.get("pk")
        if raw in (None, ""):
            return None
        bound = cleaned(form, {"pk": raw}, action="delete")
        row = session.get(getattr(_m(), model), bound["pk"])
        return None if row is None else {"pk": getattr(row, pk_name), label_field: getattr(row, label_field)}

    def validate(session, action, data, before):
        if action == "delete":
            _need(before, name)
            if in_use and in_use(session, data["pk"]):
                raise Bad(in_use_msg or "Unlink this %s from every book before deleting." % name)
            return {"pk": data["pk"]}
        exists_state(action, before, name)
        _refuse_stale(before, data, (label_field,))
        return {"pk": data["pk"], label_field: data.get(label_field) or data.get(name)}

    def apply(session, action, before, after):
        return apply_row(
            session,
            getattr(_m(), model),
            action,
            after,
            {label_field: after[label_field]} if action != "delete" else {},
            pk_name,
        )

    Op(name, form=form, optional_pk=not str_pk, snapshot=snapshot, validate=validate, apply=apply)


# Book

def _book_val(session, action, data, before):
    if action == "delete":
        raise Bad("Books cannot be deleted here.")
    exists_state(action, before, "ebook")
    _refuse_stale(before, data, ("release_date", "title", "copyrighted", "updatemode"))
    data["release_date"] = data.get("release_date") or date.today().isoformat()
    data["copyrighted"] = data.get("copyrighted") or 0
    data["updatemode"] = data.get("updatemode") or 0
    if not (data.get("title") or "").strip():
        raise Bad("Enter a title.")
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
    if action == "create" or (action == "update" and (before or {}).get("title") != after.get("title")):
        # books.title is only a cache of the MARC 245 value, so edit the source
        # field too or the trigger would immediately restore the old title.
        result = session.execute(
            text(
                "update attributes set text = :t "
                "where fk_books = :b and fk_attriblist = 245"
            ),
            {"t": after.get("title") or "", "b": after["pk"]},
        )
        if not result.rowcount:
            session.execute(
                text(
                    "insert into attributes (fk_books, fk_attriblist, text, nonfiling) "
                    "values (:b, 245, :t, :n)"
                ),
                {"b": after["pk"], "t": after.get("title") or "", "n": _article_len(after.get("title"))},
            )
        refresh_book_title(session, after["pk"])
    return row


def _book_sql(action, before, after):
    if action == "create":
        return "insert into books (pk, release_date, title, copyrighted, updatemode) values (%s, '%s', '%s', %s, %s)" % (
            after["pk"],
            after["release_date"],
            _sql_str(after.get("title")),
            after["copyrighted"],
            after["updatemode"],
        )
    if action == "update":
        return "update books set release_date = '%s', title = '%s', copyrighted = %s, updatemode = %s where pk = %s" % (
            after["release_date"],
            _sql_str(after.get("title")),
            after["copyrighted"],
            after["updatemode"],
            after["pk"],
        )
    return None


Op(
    "book",
    form=BookForm,
    optional_pk=False,
    snapshot=snap_pk(lambda s, pk: _pick(c.book_row(s, pk), ("pk", "release_date", "title", "copyrighted", "updatemode"))),
    validate=_book_val,
    apply=_book_apply,
    compat_sql=_book_sql,
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


Op(
    "alias",
    form=AliasForm,
    snapshot=snap_pk(c.alias_row),
    validate=_alias_val,
    apply=lambda s, a, b, f: apply_row(
        s,
        _m().Alias,
        a,
        f,
        {"fk_authors": f["fk_authors"], "alias": f.get("alias"), "heading": f.get("heading")} if a != "delete" else {},
    ),
)


# Book links

add_link("book_subject", lambda: _m().t_mn_books_subjects, "fk_subjects", "subject", c.exists_subject)
add_link(
    "book_lang",
    lambda: _m().t_mn_books_langs,
    "fk_langs",
    "language",
    lambda s, v: s.get(_m().Lang, v) is not None,
    CodeField(LANG_RE),
)
add_link(
    "book_locc",
    lambda: _m().t_mn_books_loccs,
    "fk_loccs",
    "LoC class",
    lambda s, v: s.get(_m().Locc, v) is not None,
    CodeField(LOCC_RE, case="upper"),
)
add_link(
    "book_category",
    lambda: _m().t_mn_books_categories,
    "fk_categories",
    "category",
    lambda s, v: s.get(_m().Category, int(v)) is not None,
)


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


def _ba_sql(action, before, after):
    book = after["fk_books"]
    if action == "link":
        return "insert into mn_books_authors (fk_books, fk_authors, fk_roles, heading) values (%s, %s, '%s', %s)" % (
            book,
            after["fk_authors"],
            after["fk_roles"],
            after["heading"],
        )
    if action == "update":
        return "update mn_books_authors set fk_roles = '%s', heading = %s where fk_books = %s and fk_authors = %s" % (
            after["fk_roles"],
            after["heading"],
            book,
            after["fk_authors"],
        )
    return "delete from mn_books_authors where fk_books = %s and fk_authors = %s and fk_roles = '%s'" % (
        book,
        after["fk_authors"],
        after["fk_roles"],
    )


Op(
    "book_author",
    form=BAForm,
    snapshot=_ba_snap,
    validate=_ba_val,
    apply=_ba_apply,
    compat_sql=_ba_sql,
)


# Attributes

# MARC 21 fields that are repeatable (R) in the spec, plus PG's own local
# tags, which the spec does not govern. Every other tag is nonrepeatable
# (NR), so a second one is refused on create.
_REPEATABLE_TAGS = frozenset((
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

# MARC 21 fields filed under a leading article: their second indicator
# carries the nonfiling characters. No other field has any.
_NONFILING_TAGS = frozenset((
    100, 110, 111, 130, 240, 243, 245, 440, 630,
    700, 710, 711, 730, 740, 800, 810, 811, 830,
))


def _article_len(title):
    """Nonfiling seed for a new title: the length of a leading English article."""
    first, _, rest = (title or "").partition(" ")
    return len(first) + 1 if first.lower() in ("the", "an", "a") and rest else 0


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
    if action == "create" and after["fk_attriblist"] not in _REPEATABLE_TAGS:
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
    compat_sql=lambda a, b, f: (
        None
        if a == "delete" or f.get("fk_attriblist") != 245
        else 'update attributes set  "fk_attriblist" = 245 where pk = %s' % f["pk"]
    ),
)


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


# Fallback changelog SQL: the edit's own statement, in the style of the
# historical changelog rows. They record what was applied, and are never replayed.

_LINK_SQL = {
    # op: (table, fk column); real table and column names from the libgutenberg models.
    "book_subject": ("mn_books_subjects", "fk_subjects"),
    "book_lang": ("mn_books_langs", "fk_langs"),
    "book_locc": ("mn_books_loccs", "fk_loccs"),
    "book_category": ("mn_books_categories", "fk_categories"),
}
_ROW_SQL = {
    # op: (table, value columns, string pk); real table and column names from the libgutenberg models.
    "author": ("authors", ("author", "born_floor", "born_ceil", "died_floor", "died_ceil", "note"), False),
    "alias": ("aliases", ("fk_authors", "alias", "alias_heading"), False),
    "subject": ("subjects", ("subject",), False),
    "category": ("categories", ("category",), False),
    "lang": ("langs", ("lang",), True),
    "locc": ("loccs", ("locc",), True),
}


def _lit(value):
    return "NULL" if value is None else "'%s'" % _sql_str(value) if isinstance(value, str) else str(value)


def _cols(after, cols):
    return [col for col in cols if col in after]


def fallback_sql(op_name, action, before, after):
    """The edit's own SQL, for ops without compat_sql of their own."""
    before, after = before or {}, after or {}
    if op_name == "alias":
        after = {**after, "alias_heading": after.get("heading")}
    if op_name == "lang":
        after = {**after, "lang": after.get("language")}
    link = _LINK_SQL.get(op_name)
    if link:
        table, col = link
        book, other = after.get("fk_books"), after.get(col)
        if book is None or other is None:
            return None
        if action == "link":
            return "insert into %s (fk_books, %s) values (%s, %s)" % (table, col, book, _lit(other))
        return "delete from %s where fk_books = %s and %s = %s" % (table, book, col, _lit(other))
    if op_name == "attribute":
        pk = after.get("pk")
        if pk is None:
            return None
        if action == "delete":
            return "delete from attributes where pk = %s" % pk
        cols = _cols(after, ("fk_books", "fk_attriblist", "text", "nonfiling", "indicators", "fk_langs"))
        if not cols:
            return None
        if action == "create":
            return "insert into attributes (%s) values (%s)" % (", ".join(cols), ", ".join(_lit(after[c]) for c in cols))
        return "update attributes set %s where pk = %s" % (", ".join("%s = %s" % (c, _lit(after[c])) for c in cols), pk)
    row = _ROW_SQL.get(op_name)
    if row and action in ("create", "update", "delete") and (after.get("pk") is not None or action == "create"):
        table, cols, str_pk = row
        pk = "'%s'" % _sql_str(after.get("pk")) if str_pk else after.get("pk")
        if action == "delete":
            return "delete from %s where pk = %s" % (table, pk)
        names = _cols(after, cols)
        if not names:
            return None
        if action == "update":
            return "update %s set %s where pk = %s" % (table, ", ".join("%s = %s" % (c, _lit(after[c])) for c in names), pk)
        if str_pk:  # lang and locc carry their code as the pk
            names = ["pk"] + names
        return "insert into %s (%s) values (%s)" % (table, ", ".join(names), ", ".join(_lit(after.get(c)) for c in names))
    return None
