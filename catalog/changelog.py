"""Build the SQL recorded in the catalog changelog for each applied edit.

The rows describe the edit that was applied, in the style of the historical
changelog. They are a history only and are never replayed.
"""

# Link ops use a simple book/other table and column pair.
_LINK_TABLES = {
    # op: (table, other foreign-key column), using libgutenberg's real names.
    "book_subject": ("mn_books_subjects", "fk_subjects"),
    "book_lang": ("mn_books_langs", "fk_langs"),
    "book_locc": ("mn_books_loccs", "fk_loccs"),
    "book_category": ("mn_books_categories", "fk_categories"),
}

# Entity ops are one table with a label column and a numeric or string pk.
_ENTITY_TABLES = {
    # op: (table, label columns, string pk?), using libgutenberg's real names.
    "author": ("authors", ("author", "born_floor", "born_ceil", "died_floor", "died_ceil", "note"), False),
    "alias": ("aliases", ("fk_authors", "alias", "alias_heading"), False),
    "subject": ("subjects", ("subject",), False),
    "category": ("categories", ("category",), False),
    "lang": ("langs", ("lang",), True),
    "locc": ("loccs", ("locc",), True),
}


def _escape(value):
    """Escape a value for a single-quoted SQL string."""
    return str(value or "").replace("'", "''")


def _literal(value):
    """A value as SQL text: quoted strings, NULL, or a bare number."""
    if value is None:
        return "NULL"
    if isinstance(value, str):
        return "'%s'" % _escape(value)
    return str(value)


def _present(values, columns):
    return [column for column in columns if column in values]


def _assignments(values):
    return ", ".join("%s = %s" % (column, _literal(value)) for column, value in values.items())


def _conditions(where):
    return " and ".join("%s = %s" % (column, _literal(value)) for column, value in where.items())


def insert_sql(table, values, columns=None):
    columns = list(values) if columns is None else columns
    return "insert into %s (%s) values (%s)" % (
        table,
        ", ".join(columns),
        ", ".join(_literal(values[column]) for column in columns),
    )


def update_sql(table, values, where):
    return "update %s set %s where %s" % (table, _assignments(values), _conditions(where))


def delete_sql(table, where):
    return "delete from %s where %s" % (table, _conditions(where))


def book_changelog(action, before, after):
    """The books row as applied; book deletion is not offered here."""
    if action == "create":
        return insert_sql(
            "books",
            {
                "pk": after["pk"],
                "release_date": after["release_date"],
                "title": after.get("title") or "",
                "copyrighted": after["copyrighted"],
                "updatemode": after["updatemode"],
            },
        )
    if action == "update":
        return update_sql(
            "books",
            {
                "release_date": after["release_date"],
                "title": after.get("title") or "",
                "copyrighted": after["copyrighted"],
                "updatemode": after["updatemode"],
            },
            {"pk": after["pk"]},
        )
    return None


def book_author_changelog(action, before, after):
    """The mn_books_authors row as linked, re-roled or unlinked."""
    keys = {
        "fk_books": after["fk_books"],
        "fk_authors": after["fk_authors"],
        "fk_roles": after["fk_roles"],
    }
    if action == "link":
        return insert_sql("mn_books_authors", {**keys, "heading": after["heading"]})
    if action == "update":
        return update_sql(
            "mn_books_authors",
            {"fk_roles": after["fk_roles"], "heading": after["heading"]},
            {"fk_books": after["fk_books"], "fk_authors": after["fk_authors"]},
        )
    return delete_sql("mn_books_authors", keys)


def attribute_changelog(action, before, after):
    """Record the special-case 245 row, and let default_changelog_sql do the rest.

    The MARC title is edited through the book record, so a 245 attribute
    update is logged as the title-field touch that historical changelog rows
    use. Every other attribute change gets the full row statement.
    """
    if action == "delete" or after.get("fk_attriblist") != 245:
        return None
    return 'update attributes set  "fk_attriblist" = 245 where pk = %s' % after["pk"]


def default_changelog_sql(op_name, action, before, after):
    """Build the changelog statement for an op without its own builder.

    Links become an insert or delete. Attributes and entities become an
    insert, update or delete of the row that changed. ``before`` is accepted
    so every changelog builder has the same signature; the statement is
    built from the applied ``after`` values.
    """
    after = after or {}

    # The form and the table use different names for the same value.
    if op_name == "alias":
        after = {**after, "alias_heading": after.get("heading")}
    if op_name == "lang":
        after = {**after, "lang": after.get("language")}

    link = _LINK_TABLES.get(op_name)
    if link:
        table, column = link
        book, other = after.get("fk_books"), after.get(column)
        if book is None or other is None:
            return None
        keys = {"fk_books": book, column: other}
        return insert_sql(table, keys) if action == "link" else delete_sql(table, keys)

    if op_name == "attribute":
        pk = after.get("pk")
        if pk is None:
            return None
        if action == "delete":
            return delete_sql("attributes", {"pk": pk})
        columns = _present(
            after,
            ("fk_books", "fk_attriblist", "text", "nonfiling", "indicators", "fk_langs"),
        )
        if not columns:
            return None
        if action == "create":
            return insert_sql("attributes", after, columns)
        return update_sql("attributes", {column: after[column] for column in columns}, {"pk": pk})

    entity = _ENTITY_TABLES.get(op_name)
    if entity and action in ("create", "update", "delete") and (after.get("pk") is not None or action == "create"):
        table, columns, string_pk = entity
        pk = after.get("pk")
        if action == "delete":
            return delete_sql(table, {"pk": pk})
        names = _present(after, columns)
        if not names:
            return None
        if action == "update":
            return update_sql(table, {column: after[column] for column in names}, {"pk": pk})
        if string_pk:  # lang and locc carry their code as the pk
            names = ["pk"] + names
        return insert_sql(table, after, names)
    return None
