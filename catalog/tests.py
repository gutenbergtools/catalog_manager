import contextlib
import re
from datetime import date
from unittest import mock

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from . import catalog as c
from .clean import YEAR_MAX, Bad, BookForm, CodeField, FlagField, TextField, cleaned, stale
from .ops import _book_snap, _book_val, fallback_sql


class _Num(forms.Form):
    n = forms.IntegerField(min_value=1)


class _Year(forms.Form):
    born = forms.IntegerField(min_value=-4000, max_value=YEAR_MAX, required=False)


class CleanTests(SimpleTestCase):
    def test_integer(self):
        self.assertEqual(cleaned(_Num, {"n": "12"})["n"], 12)
        self.assertRaises(Bad, cleaned, _Num, {"n": "x"})
        self.assertRaises(Bad, cleaned, _Num, {"n": "0"})

    def test_text_and_year(self):
        self.assertEqual(TextField(max_length=240).clean("  Brontë  "), "Brontë")
        self.assertEqual(cleaned(_Year, {"born": ""})["born"], None)
        self.assertRaises(Bad, cleaned, _Year, {"born": "3000"})

    def test_book_release_date_optional(self):
        data = cleaned(BookForm, {"pk": "12345", "copyrighted": "", "updatemode": ""})
        self.assertIsNone(data["release_date"])
        self.assertEqual(data["copyrighted"], 0)
        self.assertEqual(data["updatemode"], 0)

    def test_flag_and_code(self):
        self.assertEqual(FlagField().clean("on"), 1)
        self.assertEqual(FlagField().clean(""), 0)
        self.assertEqual(CodeField(r"[a-z]{2,3}").clean("EN"), "en")
        self.assertRaises(ValidationError, CodeField(r"[a-z]{2,3}").clean, "english")


class HeaderTests(SimpleTestCase):
    def test_security_headers(self):
        response = self.client.get("/login/", secure=True)
        csp = response["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(response["Permissions-Policy"], "camera=(), microphone=(), geolocation=()")


PRIVATE_PAGES = [
    "/",
    "/books/",
    "/book/11/",
    "/authors/",
    "/author/9/",
    "/subjects/",
    "/subject/36578/",
    "/categories/",
    "/languages/",
    "/language/en/",
    "/loccs/",
    "/locc/AG/",
]


class AccessControlTests(TestCase):
    fixtures = ["cataloger"]

    @staticmethod
    def cataloger(username="cataloger", password=None):
        from django.contrib.auth.models import Group

        user = get_user_model().objects.filter(username=username).first()
        if user is None:
            kwargs = {"email": username + "@example.com"}
            if password:
                kwargs["password"] = password
            user = get_user_model().objects.create_user(username, **kwargs)
        elif password:
            user.set_password(password)
            user.save(update_fields=["password"])
        user.groups.add(Group.objects.get(name=settings.CATALOGUER_GROUP))
        return user

    def test_private_pages_require_login(self):
        for url in PRIVATE_PAGES:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/login/"))

    def test_non_cataloger_cannot_propose_changes(self):
        user = get_user_model().objects.create_user("outsider", email="outsider@example.com")
        self.client.force_login(user)
        response = self.client.post("/change/propose/", {"op": "book", "action": "create"})
        self.assertEqual(response.status_code, 403)

    def test_cataloger_can_propose_changes(self):
        self.client.force_login(self.cataloger())
        # The posted book has no data, so validation stops before any catalog
        # query; the stub keeps the test independent of the catalog database.
        with mock.patch("catalog.changes.c.session", return_value=contextlib.nullcontext()):
            response = self.client.post("/change/propose/", {"op": "book", "action": "create"})
        self.assertEqual(response.status_code, 302)  # invalid data: redirected with a flash, not 403

    def test_login_refused_without_group(self):
        get_user_model().objects.create_user("outsider", email="outsider@example.com", password="long-password-1")
        response = self.client.post("/login/", {"username": "outsider", "password": "long-password-1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This account cannot use this site.")

        self.cataloger("member", password="long-password-1")
        response = self.client.post("/login/", {"username": "member", "password": "long-password-1"})
        self.assertEqual(response.status_code, 302)
class FallbackSqlTests(SimpleTestCase):
    def test_links(self):
        self.assertEqual(
            fallback_sql("book_subject", "link", None, {"fk_books": 12, "fk_subjects": 3}),
            "insert into mn_books_subjects (fk_books, fk_subjects) values (12, 3)",
        )
        self.assertEqual(
            fallback_sql("book_lang", "unlink", {"fk_books": 12}, {"fk_books": 12, "fk_langs": "en"}),
            "delete from mn_books_langs where fk_books = 12 and fk_langs = 'en'",
        )
        self.assertIsNone(fallback_sql("book_locc", "link", None, {"fk_loccs": "PR"}))

    def test_attribute(self):
        self.assertEqual(
            fallback_sql("attribute", "update", {"pk": 99, "fk_attriblist": 245}, {"pk": 99, "fk_attriblist": 245}),
            "update attributes set fk_attriblist = 245 where pk = 99",
        )
        self.assertEqual(
            fallback_sql(
                "attribute",
                "create",
                None,
                {"pk": 5, "fk_books": 5, "fk_attriblist": 700, "text": "A note", "nonfiling": 0, "indicators": "", "fk_langs": None},
            ),
            "insert into attributes (fk_books, fk_attriblist, text, nonfiling, indicators, fk_langs)"
            " values (5, 700, 'A note', 0, '', NULL)",
        )
        self.assertEqual(
            fallback_sql("attribute", "delete", {"pk": 5, "fk_attriblist": 700}, {"pk": 5, "fk_books": 5}),
            "delete from attributes where pk = 5",
        )

    def test_author_and_alias(self):
        self.assertEqual(
            fallback_sql("author", "update", {"pk": 3}, {"pk": 3, "author": "Brontë", "note": None}),
            "update authors set author = 'Brontë', note = NULL where pk = 3",
        )
        self.assertEqual(
            fallback_sql("author", "create", None, {"author": "Brontë", "born_floor": 1816}),
            "insert into authors (author, born_floor) values ('Brontë', 1816)",
        )
        self.assertEqual(
            fallback_sql("alias", "create", None, {"fk_authors": 3, "alias": "Bell, Ellis", "heading": 1}),
            "insert into aliases (fk_authors, alias, alias_heading) values (3, 'Bell, Ellis', 1)",
        )
        self.assertEqual(
            fallback_sql("alias", "update", {"pk": 8}, {"pk": 8, "alias": "Bell, Ellis", "heading": 1}),
            "update aliases set alias = 'Bell, Ellis', alias_heading = 1 where pk = 8",
        )
        self.assertEqual(
            fallback_sql("alias", "delete", {"pk": 8}, {"pk": 8, "fk_authors": 3}),
            "delete from aliases where pk = 8",
        )

    def test_entities(self):
        self.assertEqual(
            fallback_sql("subject", "update", {"pk": 3}, {"pk": 3, "subject": "Fiction"}),
            "update subjects set subject = 'Fiction' where pk = 3",
        )
        self.assertEqual(
            fallback_sql("subject", "create", None, {"subject": "Fiction"}),
            "insert into subjects (subject) values ('Fiction')",
        )
        self.assertEqual(
            fallback_sql("category", "delete", {"pk": 1}, {"pk": 1}),
            "delete from categories where pk = 1",
        )
        self.assertEqual(
            fallback_sql("lang", "update", {"pk": "en"}, {"pk": "en", "language": "English"}),
            "update langs set lang = 'English' where pk = 'en'",
        )
        self.assertEqual(
            fallback_sql("lang", "create", None, {"pk": "fr", "language": "French"}),
            "insert into langs (pk, lang) values ('fr', 'French')",
        )
        self.assertEqual(
            fallback_sql("locc", "delete", {"pk": "PR"}, {"pk": "PR"}),
            "delete from loccs where pk = 'PR'",
        )

    def test_ops_with_their_own_or_no_sql(self):
        self.assertIsNone(fallback_sql("book", "create", None, {"pk": 1}))
        self.assertIsNone(fallback_sql("book", "delete", {"pk": 1}, {"pk": 1}))
        self.assertIsNone(fallback_sql("book_author", "link", None, {"fk_books": 1, "fk_authors": 2}))
        self.assertIsNone(fallback_sql("nonesuch", "update", {}, {}))
class StaleTests(SimpleTestCase):
    def test_no_was_value_no_check(self):
        self.assertFalse(stale({"title": "New"}, {}, ("title",)))
        self.assertFalse(stale({"note": None}, {"was_note": ""}, ("note",)))

    def test_vanished_row_is_stale(self):
        self.assertTrue(stale(None, {"was_title": "Old"}, ("title",)))

    def test_matching_values_are_fresh(self):
        before = {"title": " Hamlet ", "copyrighted": 0, "release_date": date(2026, 11, 23), "note": None}
        was = {"was_title": "Hamlet", "was_copyrighted": "0", "was_release_date": "2026-11-23", "was_note": ""}
        self.assertFalse(stale(before, was, ("title", "copyrighted", "release_date", "note")))

    def test_changed_value_is_stale(self):
        self.assertTrue(stale({"title": "New title"}, {"was_title": "Old title"}, ("title",)))
        self.assertTrue(stale({"heading": 1}, {"was_heading": "0"}, ("heading",)))

    def test_normalization(self):
        self.assertFalse(stale({"text": "one\ntwo"}, {"was_text": "one\r\ntwo"}, ("text",)))
        self.assertFalse(stale({"indicators": "  "}, {"was_indicators": ""}, ("indicators",)))
        self.assertFalse(stale({"fk_langs": None}, {"was_fk_langs": ""}, ("fk_langs",)))


class BookSnapshotTests(SimpleTestCase):
    def test_snapshot_takes_the_posted_form_data(self):
        from sqlalchemy import column

        session = mock.Mock()
        session.scalar.return_value = 4
        model = mock.Mock()
        model.Attribute.nonfiling = column("nonfiling")
        row = {"pk": 11, "release_date": "2026-01-01", "title": "The Idiot", "copyrighted": 0, "updatemode": 0}
        with (
            mock.patch.object(c, "book_row", lambda s, pk: dict(row, pk=pk)),
            mock.patch("catalog.ops._m", lambda: model),
        ):
            snap = _book_snap(session, {"pk": "11"})
        self.assertEqual(snap["pk"], 11)
        self.assertEqual(snap["nonfiling"], 4)


class BookStaleTests(SimpleTestCase):
    BEFORE = {"pk": 11, "release_date": "2026-11-23", "title": "New", "copyrighted": 0, "updatemode": 0, "nonfiling": 0}

    @staticmethod
    def post(**extra):
        data = {"pk": "11", "title": "New", "release_date": "2026-11-23", "copyrighted": "1", "updatemode": "0"}
        data.update(extra)
        return data

    def test_stale_update_refused(self):
        data = cleaned(
            BookForm,
            self.post(was_title="Old", was_release_date="2026-11-23", was_copyrighted="0", was_updatemode="0"),
            action="update",
        )
        with self.assertRaisesMessage(Bad, "changed after you opened it"):
            _book_val(None, "update", data, self.BEFORE)

    def test_fresh_update_and_absent_was_both_pass(self):
        data = cleaned(
            BookForm,
            self.post(was_title="New", was_release_date="2026-11-23", was_copyrighted="0", was_updatemode="0"),
            action="update",
        )
        self.assertIs(_book_val(None, "update", data, self.BEFORE), data)
        legacy = cleaned(BookForm, self.post(), action="update")
        self.assertIs(_book_val(None, "update", legacy, self.BEFORE), legacy)

    def test_stale_nonfiling_refused(self):
        data = cleaned(BookForm, self.post(was_nonfiling="4"), action="update")
        with self.assertRaisesMessage(Bad, "changed after you opened it"):
            _book_val(None, "update", data, self.BEFORE)

    def test_nonfiling_over_title_refused(self):
        data = cleaned(BookForm, self.post(nonfiling="40"), action="update")
        with self.assertRaisesMessage(Bad, "cannot be longer than the title"):
            _book_val(None, "update", data, self.BEFORE)


class InviteTests(TestCase):
    """Accounts are created without a password; the user picks their own
    behind an emailed one-time link, so nothing travels in plain text."""

    def _admin_client(self):
        staff = get_user_model().objects.create_superuser("boss", "boss@example.org", "long-password-1")
        self.client.force_login(staff)

    @staticmethod
    def _link_from(message):
        return re.search(r"http://testserver(/\S+)", message.body).group(1)

    def test_admin_create_user_emails_a_password_link(self):
        group = Group.objects.get(name=settings.CATALOGUER_GROUP)
        self._admin_client()
        response = self.client.post(
            reverse("admin:auth_user_add"),
            {"username": "new", "email": "new@example.org", "groups": [group.pk]},
        )
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username="new")
        self.assertFalse(user.has_usable_password())
        self.assertIn(group, user.groups.all())
        self.assertEqual(len(mail.outbox), 1)

        self.client.logout()
        page = self.client.get(self._link_from(mail.outbox[0]), follow=True)
        self.assertEqual(page.status_code, 200)
        self.client.post(
            page.request["PATH_INFO"], {"new_password1": "long-password-1", "new_password2": "long-password-1"}
        )
        self.assertTrue(self.client.login(username="new", password="long-password-1"))

    def test_admin_action_resends_the_link(self):
        get_user_model().objects.create_user("some", email="some@example.org")
        self._admin_client()
        response = self.client.post(
            reverse("admin:auth_user_changelist"),
            {"action": "send_invite_action", "_selected_action": [get_user_model().objects.get(username="some").pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Password-set email sent", response.content.decode())

    def test_link_expires_after_the_configured_hours(self):
        from datetime import datetime as _dt

        user = get_user_model().objects.create_user("expiring", email="e@example.org", password="long-password-1")
        fresh = default_token_generator.make_token(user)
        self.assertTrue(default_token_generator.check_token(user, fresh))
        # a token minted just past the window must be refused
        seconds_since_2001 = int((_dt.now() - _dt(2001, 1, 1)).total_seconds())
        stale_ts = seconds_since_2001 - settings.PASSWORD_RESET_TIMEOUT - 60
        stale = default_token_generator._make_token_with_timestamp(user, stale_ts, default_token_generator.secret)
        self.assertFalse(default_token_generator.check_token(user, stale))

    def test_no_public_password_request(self):
        response = self.client.get("/password-reset/")
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse("password_reset_confirm", kwargs={"uidb64": "x", "token": "y"}))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ask an administrator", response.content.decode())


class ForwardedHostTests(SimpleTestCase):
    def test_links_use_the_public_host_behind_the_proxy(self):
        with override_settings(USE_X_FORWARDED_HOST=True, ALLOWED_HOSTS=["opds-test.pglaf.org"]):
            bad = self.client.get("/login/", HTTP_X_FORWARDED_HOST="bad.example.org")
            response = self.client.get("/login/", HTTP_X_FORWARDED_HOST="opds-test.pglaf.org")
        self.assertEqual(bad.status_code, 400)  # forwarded hosts are still validated
        self.assertEqual(response.status_code, 200)


class LoginUserRateTests(TestCase):
    def setUp(self):
        cache.clear()

    tearDown = setUp  # buckets live for a minute; keep runs independent

    def test_eleventh_try_for_one_username_is_blocked(self):
        for i in range(10):
            response = self.client.post(
                "/login/",
                {"username": "target", "password": "wrong"},
                REMOTE_ADDR="10.%d.%d.1" % (i // 256, i % 256),
            )
            self.assertIn(response.status_code, (200, 302))
        blocked = self.client.post(
            "/login/", {"username": "target", "password": "wrong"}, REMOTE_ADDR="10.9.9.9"
        )
        self.assertEqual(blocked.status_code, 403)
