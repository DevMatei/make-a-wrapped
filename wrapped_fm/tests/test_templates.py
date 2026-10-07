"""Tests for the community template library."""

from __future__ import annotations

import os
import tempfile
import unittest
from secrets import token_urlsafe
from unittest import mock

from wrapped_fm import templates as store
from wrapped_fm.templates import (
    CreatorInvalidError,
    TemplateInvalidError,
    TemplateUnavailableError,
)


def _valid_template(slug: str = "test-slug", name: str = "Test Template") -> dict:
    return {
        "slug": slug,
        "name": name,
        "canvas": {"width": 1080, "height": 1920},
        "palette": {"label": "#ffffff", "value": "#000000"},
        "background": {"type": "gradient", "colors": ["#112233", "#445566"], "angle": 90},
        "artwork": {"enabled": True, "x": 268, "y": 244, "size": 544},
        "elements": [
            {"id": "heading", "kind": "text", "text": "Top Artists", "x": 112, "y": 1080, "font": {"weight": 700, "size": 48}, "color": "label"},
            {"id": "list", "kind": "list", "slot": "artists", "x": 112, "y": 1180, "font": {"weight": 700, "size": 40}, "color": "value", "lineHeight": 72, "maxWidth": 454},
        ],
    }


def _with(**changes) -> dict:
    template = _valid_template()
    for path, value in changes.items():
        target = template
        *parents, key = path.split("__")
        for parent in parents:
            target = target[int(parent)] if parent.isdigit() else target[parent]
        target[key] = value
    return template


class TemplateValidationTests(unittest.TestCase):
    def test_creator_ids(self):
        secret = token_urlsafe(24)
        creator_id = store.creator_id_for_secret(secret)

        self.assertEqual(creator_id, store.creator_id_for_secret(secret))
        self.assertTrue(creator_id.startswith("c"))
        self.assertEqual(len(creator_id), 13)
        with self.assertRaises(CreatorInvalidError):
            store.creator_id_for_secret("short")

    def test_rejects_invalid_templates(self):
        cases = {
            "bad slug": _with(slug="Bad Slug!"),
            "empty slug": _with(slug=""),
            "blank name": _with(name="  "),
            "no elements": _with(elements=[]),
            "bad slot": _with(elements__1__slot="notavalidslot"),
            "external background": _with(background={"type": "image", "src": "https://evil.example/x.png"}),
        }

        for name, template in cases.items():
            with self.subTest(name=name), self.assertRaises(TemplateInvalidError):
                store.validate_template(template)

    def test_strips_script_text(self):
        result = store.validate_template(_with(elements__0__text="<script>alert(1)</script>"))

        self.assertNotIn("<script", result["elements"][0]["text"])

    def test_official_baseline_distributes_total_to_weights(self):
        with mock.patch.object(store, "read_wrapped_count", return_value=1000):
            baseline = store._official_baseline_uses()

        self.assertEqual((baseline["black"], baseline["black_new"], baseline["white_new"]), (300, 120, 80))
        self.assertEqual(sum(baseline.values()), 1000)


class SubmissionAndReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for attr in ("TEMPLATE_LIBRARY_DIR", "TEMPLATE_SUBMISSION_DIR", "TEMPLATE_CREATOR_DIR", "TEMPLATE_ASSET_DIR", "TEMPLATE_OFFICIAL_DIR"):
            patch = mock.patch.object(store, attr, os.path.join(tmp.name, attr.lower()))
            patch.start()
            self.addCleanup(patch.stop)
        os.makedirs(store.TEMPLATE_OFFICIAL_DIR)

    def _submit(self, template=None, creator=None):
        creator = creator or {"id": "anything", "secret": token_urlsafe(24), "name": "Matei", "website": "https://devmatei.com"}
        return store.submit_template({"creator": creator, "template": template or _valid_template()})

    def _pending_ids(self):
        return [item["submission_id"] for item in store.get_pending_submissions()]

    def test_submit_approve_and_record_uses(self):
        submission = self._submit()
        self.assertEqual(submission["status"], "pending_review")
        self.assertIn(submission["submission_id"], self._pending_ids())
        self.assertNotIn("test-slug", [t["slug"] for t in store.list_templates()])

        store.approve_submission(submission["submission_id"])
        store.record_template_use("test-slug")
        store.record_template_use("test-slug")

        self.assertIn("test-slug", [t["slug"] for t in store.list_templates()])
        self.assertNotIn(submission["submission_id"], self._pending_ids())
        self.assertEqual(store.get_template_uses("test-slug"), 2)
        collision = self._submit(template=_valid_template(name="Collision"))
        with self.assertRaises(TemplateInvalidError):
            store.approve_submission(collision["submission_id"])

    def test_creator_identity_is_linked_and_cannot_be_impersonated(self):
        creator = {"id": "", "secret": token_urlsafe(24), "name": "Matei"}
        first = self._submit(creator=dict(creator))
        second = self._submit(template=_valid_template(slug="another"), creator=dict(creator))

        self.assertEqual(first["creator"]["id"], second["creator"]["id"])
        self.assertTrue(store.get_creator(first["creator"]["id"])["name"])
        with self.assertRaises(CreatorInvalidError):
            self._submit(creator={"id": first["creator"]["id"], "secret": token_urlsafe(24), "name": "Imposter"})

    def test_reject_and_missing_lookups(self):
        submission = self._submit()
        store.reject_submission(submission["submission_id"])

        self.assertNotIn(submission["submission_id"], self._pending_ids())
        for call in (
            lambda: store.reject_submission(submission["submission_id"]),
            lambda: store.approve_submission("doesnotexist"),
            lambda: store.get_template("nope"),
        ):
            with self.assertRaises(TemplateUnavailableError):
                call()

    def test_template_assets(self):
        result = store.store_template_asset("valid-slug", "my-art (1).jpg", b"x")

        self.assertEqual(result["filename"], "/template-assets/valid-slug/background.jpg")
        self.assertTrue(os.path.exists(os.path.join(store.TEMPLATE_ASSET_DIR, "valid-slug", "background.jpg")))
        with self.assertRaises(TemplateInvalidError):
            store.store_template_asset("valid-slug", "evil.txt", b"x")


if __name__ == "__main__":
    unittest.main()
