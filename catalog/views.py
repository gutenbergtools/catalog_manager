import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from . import catalog as c
from . import changes as ch
from .clean import Bad
from .models import can_use_app


def _num(raw, default):
    return int(raw) if re.fullmatch(r"[+-]?\d+", str(raw).strip()) else default


def _page_number(request, key="page"):
    return max(1, _num(request.GET.get(key) or 1, 1))


def _pager_context(total, page, size=None, qs="", param="page"):
    size = size or settings.PAGE_SIZE
    pages = max(1, -(-total // size))
    page = min(max(1, page), pages)
    return {
        "page": page,
        "pages": pages,
        "total": total,
        "previous": page - 1,
        "next": page + 1,
        "has_previous": page > 1,
        "has_next": page < pages,
        "qs": qs,
        "param": param,
    }


def _qs(request, *drop):
    query = request.GET.copy()
    for key in drop:
        query.pop(key, None)
    return query.urlencode()


def _paged_rows(fetch, page, qs="", param="page", size=None):
    rows, total = fetch(page)
    pager = _pager_context(total, page, size=size, qs=qs, param=param)
    if pager["page"] != page:
        rows, total = fetch(pager["page"])
        pager = _pager_context(total, pager["page"], size=size, qs=qs, param=param)
    return rows, pager


def _back(request, fallback):
    target = request.POST.get("next") or request.GET.get("next") or ""
    return (
        target
        if target and url_has_allowed_host_and_scheme(target, {request.get_host()}, request.is_secure())
        else fallback
    )


def _or404(value, message):
    if value is None:
        raise Http404(message)
    return value


def _cat(view):
    def guarded(request, *args, **kwargs):
        if not can_use_app(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return login_required(guarded)


BOOK_SORTS = [
    ("newest", "Newest ebook"),
    ("oldest", "Oldest ebook"),
    ("downloads", "Most downloaded"),
    ("title", "Title A–Z"),
]
AUTHOR_SORTS = [
    ("name", "Name A–Z"),
    ("newest", "Newest added"),
    ("downloads", "Most downloaded"),
]


def _listing(request, fetch, template, key, extra=None, sorts=None):
    query = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "").strip()
    rows, pager = _paged_rows(lambda p: fetch(query, p, sort), _page_number(request), _qs(request, "page"))
    context = {key: rows, "q": query, "sort": sort, "sorts": sorts or [], "pager": pager}
    context.update(extra or {})
    return render(request, template, context)


class AllowedLoginView(auth.LoginView):
    template_name = "registration/login.html"
    form_valid = lambda self, form: (
        auth.LoginView.form_valid(self, form)
        if can_use_app(form.get_user())
        else (form.add_error(None, "This account cannot use this site."), self.form_invalid(form))[1]
    )


def home(request):
    return redirect("books")


_MESSAGES = {"applied": "Saved.", "same": "Nothing to change."}


def _flash(request, result):
    (messages.info if result == "same" else messages.success)(request, _MESSAGES[result])


def change_propose(request):
    fallback = _back(request, reverse("home"))
    op_name = request.POST.get("op", "")
    action = request.POST.get("action", "")
    try:
        result, after = ch.commit(request.user, op_name, action, request.POST)
        pk = after.get("pk") if result == "applied" and op_name == "book" and action == "create" else None
        fallback = reverse("book", args=[pk]) if pk else fallback
        _flash(request, result)
    except Bad as exc:
        messages.error(request, str(exc))
    return redirect(fallback)


def books(request):
    return _listing(
        request,
        lambda q, p, sort: c.search_books(q, p, sort=sort) if q else c.recent_books(p, sort=sort),
        "books.html",
        "books",
        sorts=BOOK_SORTS,
    )


def book_detail(request, pk):
    data = _or404(c.book_page(pk), "No such ebook.")
    data.update(lookups=c.lookups())
    return render(request, "book.html", data)


def authors(request):
    return _listing(
        request,
        lambda q, p, sort: c.search_authors(q, p, sort=sort),
        "authors.html",
        "authors",
        sorts=AUTHOR_SORTS,
    )


def author_detail(request, pk):
    data = _or404(c.author_page(pk), "No such author.")
    data.update(lookups=c.lookups())
    return render(request, "author.html", data)


_ENTITY = {
    "subject": {
        "title": "Subjects", "kind": "Subject", "model": "Subject",
        "pk_attr": "id", "label_attr": "subject", "search": c.search_subjects,
        "fields": [("subject", "Subject", "text", 240)],
        "list": "subjects", "detail": "subject", "path": "/subjects/",
    },
    "category": {
        "title": "Categories", "kind": "Category", "model": "Category",
        "pk_attr": "pk", "label_attr": "category", "search": c.search_categories,
        "fields": [("category", "Category", "text", 240)],
        "list": "categories", "detail": "category", "path": "/categories/",
    },
    "lang": {
        "title": "Languages", "kind": "Language", "model": "Lang",
        "pk_attr": "id", "label_attr": "language", "search": c.search_langs,
        "str_pk": True, "fields": [("pk", "Code", "text", 10), ("lang", "Language", "text", 80)],
        "list": "langs", "detail": "lang", "path": "/languages/", "url": "language",
    },
    "locc": {
        "title": "LoC Classes", "kind": "LoC Class", "model": "Locc",
        "pk_attr": "id", "label_attr": "locc", "search": c.search_loccs,
        "str_pk": True, "fields": [("pk", "Code", "text", 10), ("locc", "Class name", "text", 240)],
        "list": "loccs", "detail": "locc", "path": "/loccs/",
    },
}


def entity(request, name, pk=None):
    meta = _ENTITY[name]
    context = {
        "title": meta["title"], "op": name, "kind": meta["kind"],
        "fields": meta["fields"], "list_url": meta["list"], "detail": meta["detail"],
        "list_path": meta["path"], "str_pk": meta.get("str_pk", False),
    }
    if pk is None:
        return _listing(request, lambda q, p, sort: meta["search"](q, p), "entities.html", "rows", context)
    row = _or404(
        c.simple_entity(meta["model"], meta["pk_attr"], meta["label_attr"], pk, meta.get("str_pk", False)),
        "No such %s." % meta["kind"].lower(),
    )
    context.update(kind=meta["kind"], row=row)
    return render(request, "entity.html", context)


home = login_required(home)
change_propose = login_required(
    require_POST(ratelimit(key="user", rate=settings.RATE_POST, method="POST", block=True)(change_propose))
)
books, book_detail, authors, author_detail = map(_cat, (books, book_detail, authors, author_detail))
