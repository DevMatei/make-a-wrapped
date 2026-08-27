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


class StoreIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._originals = {}
        for attr in ("TEMPLATE_LIBRARY_DIR", "TEMPLATE_SUBMISSION_DIR",
                     "TEMPLATE_CREATOR_DIR", "TEMPLATE_ASSET_DIR", "TEMPLATE_OFFICIAL_DIR"):
            self._originals[attr] = getattr(store, attr)
            setattr(store, attr, os.path.join(self.tmp, attr.replace("TEMPLATE_", "").lower()))
        os.makedirs(store.TEMPLATE_OFFICIAL_DIR, exist_ok=True)

    def tearDown(self):
        for attr, value in self._originals.items():
            setattr(store, attr, value)


class TemplateValidationTests(unittest.TestCase):
    def test_creator_id_deterministic(self):
        secret = token_urlsafe(24)
        first = store.creator_id_for_secret(secret)
        second = store.creator_id_for_secret(secret)
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("c"))
        self.assertEqual(len(first), 13)

    def test_creator_id_rejects_short_secret(self):
        with self.assertRaises(CreatorInvalidError):
            store.creator_id_for_secret("short")

    def test_validate_template_rejects_bad_slug(self):
        with self.assertRaises(TemplateInvalidError):
            store.validate_template(_valid_template(slug="Bad Slug!"))
        with self.assertRaises(TemplateInvalidError):
            store.validate_template(_valid_template(slug=""))

    def test_validate_template_rejects_missing_name(self):
        template = _valid_template()
        template["name"] = "  "
        with self.assertRaises(TemplateInvalidError):
            store.validate_template(template)

    def test_validate_template_requires_elements(self):
        template = _valid_template()
        template["elements"] = []
        with self.assertRaises(TemplateInvalidError):
            store.validate_template(template)

    def test_validate_template_rejects_bad_slot(self):
        template = _valid_template()
        template["elements"][1]["slot"] = "notavalidslot"
        with self.assertRaises(TemplateInvalidError):
            store.validate_template(template)

    def test_validate_template_rejects_external_background(self):
        template = _valid_template()
        template["background"] = {"type": "image", "src": "https://evil.example/x.png"}
        with self.assertRaises(TemplateInvalidError):
            store.validate_template(template)

    def test_validate_template_sanitises_xss_text(self):
        template = _valid_template()
        template["elements"][0]["text"] = "<script>alert(1)</script>"
        result = store.validate_template(template)
        self.assertNotIn("<script", result["elements"][0]["text"])


class BaselineUsesTests(unittest.TestCase):
    def test_official_baseline_distributes_total_to_weights(self):
        with mock.patch("wrapped_fm.templates.read_wrapped_count", return_value=1000):
            baseline = store._official_baseline_uses()
        self.assertEqual(baseline["black"], 300)
        self.assertEqual(baseline["black_new"], 120)
        self.assertEqual(baseline["white_new"], 80)
        self.assertEqual(sum(baseline.values()), 1000)


class SubmissionAndReviewTests(StoreIsolationTests):
    def _submit(self, template=None, creator=None):
        payload = {
            "creator": creator or {"id": "anything", "secret": token_urlsafe(24), "name": "Matei", "website": "https://devmatei.com"},
            "template": template or _valid_template(),
        }
        return store.submit_template(payload)

    def test_submit_enters_pending_review(self):
        submission = self._submit()
        self.assertEqual(submission["status"], "pending_review")
        self.assertIn(submission["submission_id"], [s["submission_id"] for s in store.get_pending_submissions()])
        self.assertNotIn(submission["template"]["slug"], [t["slug"] for t in store.list_templates()])

    def test_submit_links_same_creator(self):
        secret = token_urlsafe(24)
        creator = {"id": "", "secret": secret, "name": "Matei"}
        first = self._submit(creator=dict(creator))
        second = self._submit(template=_valid_template(slug="another", name="Another"), creator=dict(creator))
        self.assertEqual(first["creator"]["id"], second["creator"]["id"])
        self.assertTrue(store.get_creator(first["creator"]["id"])["name"])

    def test_submit_rejects_impersonation(self):
        real = self._submit()
        with self.assertRaises(CreatorInvalidError):
            self._submit(creator={"id": real["creator"]["id"], "secret": token_urlsafe(24), "name": "Imposter"})

    def test_approve_moves_to_library(self):
        submission = self._submit()
        library = store.approve_submission(submission["submission_id"])
        slugs = [t["slug"] for t in store.list_templates()]
        self.assertIn(library["slug"], slugs)
        self.assertNotIn(submission["submission_id"], [s["submission_id"] for s in store.get_pending_submissions()])

    def test_approve_rejects_slug_collision(self):
        submission = self._submit()
        store.approve_submission(submission["submission_id"])
        again = self._submit(template=_valid_template(slug="test-slug", name="Collision"))
        with self.assertRaises(TemplateInvalidError):
            store.approve_submission(again["submission_id"])

    def test_reject_removes_submission(self):
        submission = self._submit()
        store.reject_submission(submission["submission_id"])
        self.assertNotIn(submission["submission_id"], [s["submission_id"] for s in store.get_pending_submissions()])
        with self.assertRaises(TemplateUnavailableError):
            store.reject_submission(submission["submission_id"])

    def test_approve_missing_submission_raises(self):
        with self.assertRaises(TemplateUnavailableError):
            store.approve_submission("doesnotexist")

    def test_record_use_increments(self):
        submission = self._submit()
        store.approve_submission(submission["submission_id"])
        self.assertEqual(store.get_template_uses("test-slug"), 0)
        store.record_template_use("test-slug")
        store.record_template_use("test-slug")
        self.assertEqual(store.get_template_uses("test-slug"), 2)

    def test_get_template_rejects_missing(self):
        with self.assertRaises(TemplateUnavailableError):
            store.get_template("nope")

    def test_store_template_asset_validates_name(self):
        with self.assertRaises(TemplateInvalidError):
            store.store_template_asset("valid-slug", "evil.txt", b"x")

    def test_store_template_asset_normalises_extension(self):
        result = store.store_template_asset("valid-slug", "my-art (1).jpg", b"x")
        self.assertEqual(result["filename"], "/template-assets/valid-slug/background.jpg")
        self.assertTrue(os.path.exists(os.path.join(store.TEMPLATE_ASSET_DIR, "valid-slug", "background.jpg")))


if __name__ == "__main__":
    unittest.main()
