"""Common plumbing for catalog edit operations."""

from django import forms
from sqlalchemy import and_, delete, select, text
from sqlalchemy.dialects.postgresql import insert

from .. import catalog as c
from ..clean import Bad, F, Posted, cleaned, jsonable, stale


# Framework

OPS = {}
ACTIONS = ("create", "update", "delete", "link", "unlink")


def get(name):
    op = OPS.get(name)
    if not op:
        raise Bad("Unknown change type.")
    return op


class Op:
    """One catalog edit: read the old row, validate the form, apply the change."""

    def __init__(
        self,
        name,
        form=None,
        domain="catalog",
        snapshot=None,
        validate=None,
        apply=None,
        changelog_sql=None,
        keep=None,
        optional_pk=True,
    ):
        self.name, self.domain, self.form = name, domain, form
        self.fields = tuple(form.base_fields) if form else ()
        self.keep, self.optional_pk = keep, optional_pk
        self._snap, self._val, self._apply = snapshot, validate, apply
        self._changelog = changelog_sql
        OPS[name] = self

    def parse(self, post):
        return Posted(
            ((field, post.get(field, "")) for field in self.fields),
            (field for field in self.fields if field.startswith("was_") and field in post),
        )

    def snapshot(self, session, data):
        return self._snap(session, data) if self._snap else None

    def validate(self, session, action, data, before):
        bound = cleaned(self.form, data, action, keep=self.keep, optional_pk=self.optional_pk)
        after = jsonable(self._val(session, action, bound, before))
        return {key: value for key, value in after.items() if not key.startswith("was_")}

    def apply(self, session, action, before, after):
        return self._apply(session, action, before, after)

    def changelog_sql(self, action, before, after):
        """SQL for this edit, when the op has a hand-written builder."""
        return self._changelog(action, before, after) if self._changelog else None


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


def _model_exists(model_name, cast=None):
    """An existence check for add_link, by model name and optional pk cast."""
    def exists(session, value):
        return session.get(getattr(_m(), model_name), cast(value) if cast else value) is not None

    return exists


def refresh_book_title(session, book_pk):
    """Recompute books.title/nonfiling from MARC 240/245/246.

    The catalogue database derives books.title with a trigger, so touching the
    row is how a changed MARC title becomes visible.
    """
    session.execute(text("update books set title = title where pk = :pk"), {"pk": book_pk})


# Factories

def add_link(name, table_name, field, other_name, exists, other_field=None):
    """Register a link op between one book and one other entity."""
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
        row = c.linked(session, getattr(_m(), table_name), bound["fk_books"], field, bound[field])
        return None if row is None else {"fk_books": bound["fk_books"], field: bound[field]}

    def validate(session, action, data, before):
        if not c.exists_book(session, data["fk_books"]):
            raise Bad("No such ebook.")
        if not exists(session, data[field]):
            raise Bad("That %s is not in the catalog." % other_name)
        exists_state(action, before, other_name)
        return {"fk_books": data["fk_books"], field: data[field]}

    def apply(session, action, before, after):
        link_apply(
            session,
            getattr(_m(), table_name),
            action == "link",
            {"fk_books": after["fk_books"], field: after[field]},
        )
        return after

    Op(
        name,
        form=form,
        snapshot=snapshot,
        validate=validate,
        apply=apply,
    )


def add_entity(name, model, pk_name, label_field, form, str_pk=False, in_use=None, in_use_msg=None):
    """Register create/update/delete for a simple labelled entity."""
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
