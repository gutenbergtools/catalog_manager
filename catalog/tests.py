from datetime import date

from django import forms
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from .clean import YEAR_MAX, Bad, BookForm, CodeField, FlagField, TextField, cleaned, stale
from .ops import _book_val, fallback_sql


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
    def test_private_pages_require_login(self):
        for url in PRIVATE_PAGES:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/login/"))

    @override_settings(CATALOG_CATALOGERS=["cataloger@example.com"])
    def test_non_cataloger_cannot_propose_changes(self):
        user = get_user_model().objects.create_user("outsider", email="outsider@example.com")
        self.client.force_login(user)
        response = self.client.post("/change/propose/", {"op": "book", "action": "create"})
        self.assertEqual(response.status_code, 403)
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
