"""Tests for the versioned Wrapped image API."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from wrapped_fm import api, catalog
from wrapped_fm.app import create_app

SAMPLE_PNG = (Path(__file__).resolve().parents[2] / "static" / "favicon-lavender-16.png").read_bytes()
SAMPLE_DATA_URL = "data:image/png;base64," + base64.b64encode(SAMPLE_PNG).decode("ascii")


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        self.client = self.app.test_client()

    def patch(self, target, attribute, **kwargs):
        patcher = mock.patch.object(target, attribute, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()


class WrappedApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.increment_count = self.patch(api, "increment_wrapped_count")
        self.record_template_use = self.patch(api.template_store, "record_template_use")

    def post(self, payload):
        return self.client.post("/api/v1/wrapped", data=json.dumps(payload), content_type="application/json")

    def mock_listenbrainz(self, count=1):
        return (
            self.patch(api, "get_top_artists_payload", return_value=[{"artist_name": str(i)} for i in range(count)]),
            self.patch(api, "get_top_tracks_payload", return_value=[{"track_name": str(i)} for i in range(count)]),
            self.patch(api, "estimate_total_listen_minutes", return_value="42"),
            self.patch(api, "get_top_genre", return_value="Rock"),
        )

    def test_renders_png_svg_and_custom_artwork(self):
        cases = [
            ("png", {"data": {"artists": ["  Alpha   Artist  "], "tracks": ["One"], "minutes": 1234, "genre": "Pop"}, "template": "black"}, "image/png"),
            ("svg", {"data": {"artists": ["Artist One"], "genre": "Rock"}, "format": "svg"}, "image/svg+xml"),
            ("artwork", {"data": {"artists": ["Artist One"], "artwork": SAMPLE_DATA_URL}}, "image/png"),
        ]

        for name, payload, mimetype in cases:
            with self.subTest(name=name):
                response = self.post(payload)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, mimetype)
                if mimetype == "image/png":
                    self.assertEqual(response.data[:8], b"\x89PNG\r\n\x1a\n")
                else:
                    svg = response.get_data(as_text=True)
                    self.assertIn("<path", svg)
                    self.assertNotIn("<text", svg)

        self.assertEqual(self.post(cases[0][1]).headers["Content-Disposition"], 'attachment; filename="wrapped-black.png"')
        self.increment_count.assert_called()
        self.record_template_use.assert_called_with("black")

    def test_provider_source_uses_listenbrainz_and_limit(self):
        artists, tracks, _, _ = self.mock_listenbrainz(count=10)
        artwork = self.patch(api, "_provider_artwork", return_value=None)

        for limit, expected in ((None, 5), (8, 8)):
            with self.subTest(limit=limit):
                source = {"type": "provider", "provider": "listenbrainz", "username": "fan", "range": {"preset": "last_year"}}
                if limit:
                    source["limit"] = limit
                response = self.post({"source": source})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(artists.call_args.args[1], expected)
                self.assertEqual(tracks.call_args.args[1], expected)
                self.assertEqual(artwork.call_args.args[1], api.resolve_preset("last_year"))

    def test_artwork_options(self):
        self.mock_listenbrainz()
        fetch_art = self.patch(api, "fetch_top_artist_image", return_value=SimpleNamespace(content=SAMPLE_PNG))
        render = self.patch(api, "_render_image", return_value=b"generated image")
        cases = [
            ("other provider release", {"source": {"type": "provider", "provider": "listenbrainz", "username": "fan"}, "artwork": {"provider": "lastfm", "source": "release"}}, False),
            ("custom data lookup", {"data": {"artists": ["A"]}, "artwork": {"provider": "listenbrainz", "username": "fan", "fit": "cover"}}, False),
            ("inline contain", {"data": {"artists": ["A"], "artwork": SAMPLE_DATA_URL}, "artwork": {"fit": "contain"}}, True),
        ]

        for name, payload, contain in cases:
            with self.subTest(name=name):
                response = self.post(payload)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(render.call_args.args[0]["artwork"]["contain"], contain)

        self.assertEqual(fetch_art.call_args_list[0].kwargs["service"], "lastfm")
        self.assertEqual(fetch_art.call_args_list[0].kwargs["preferred_source"], "release")

    def test_rejects_invalid_requests(self):
        oversized_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (5000).to_bytes(4, "big") * 2
        oversized_artwork = "data:image/png;base64," + base64.b64encode(oversized_png).decode("ascii")
        provider = {"type": "provider", "provider": "listenbrainz", "username": "fan"}
        post_raw = lambda body, content_type="application/json": lambda: self.client.post("/api/v1/wrapped", data=body, content_type=content_type)
        cases = [
            ("unknown field", {"data": {"artists": ["A"], "plays": 10}}, 400, "Unsupported data fields"),
            ("too many artists", {"data": {"artists": [str(n) for n in range(11)]}}, 400, "at most 10"),
            ("negative minutes", {"data": {"artists": ["A"], "minutes": "-10"}}, 400, "non-negative"),
            ("oversized artwork", {"data": {"artists": ["A"], "artwork": oversized_artwork}}, 400, "pixel image limit"),
            ("invalid period", {"source": {**provider, "range": {"preset": "specific_month", "month": 13, "year": 2025}}}, 400, "not a valid period"),
            ("missing template", {"data": {"artists": ["A"]}, "template": "missing-template"}, 404, "Template not found"),
            ("navidrome", {"source": {**provider, "provider": "navidrome"}}, 400, "browser-only"),
            ("provider limit", {"source": {**provider, "limit": 11}}, 400, "source.limit"),
            ("artwork source", {"data": {"artists": ["A"]}, "artwork": {"provider": "listenbrainz", "username": "fan", "source": "cover"}}, 400, "artwork.source"),
            ("format", {"data": {"artists": ["A"]}, "format": "html"}, 400, "format must be png or svg"),
            ("oversized body", post_raw(b"{" + b" " * api.MAX_API_REQUEST_BYTES + b"}"), 413, "64 KiB"),
            ("wrong content type", post_raw("{}", "text/plain"), 415, "application/json"),
            ("invalid JSON", post_raw("{"), 400, "valid JSON"),
        ]

        for name, payload, status, message in cases:
            with self.subTest(name=name):
                response = payload() if callable(payload) else self.post(payload)

                self.assertEqual(response.status_code, status)
                self.assertIn(message, response.get_json()["error"]["message"])

    def test_errors_are_json_with_cors(self):
        missing = self.client.get("/api/v1/unknown")
        preflight = self.client.options("/api/v1/wrapped")
        with mock.patch.object(api, "_render_image", side_effect=RuntimeError("private detail")):
            crashed = self.post({"data": {"artists": ["A"]}})

        self.assertEqual((missing.status_code, missing.get_json()["error"]["code"]), (404, "not_found"))
        self.assertEqual(missing.headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(preflight.status_code, 204)
        self.assertEqual((crashed.status_code, crashed.get_json()["error"]["code"]), (500, "internal_error"))
        self.assertNotIn("private detail", crashed.get_data(as_text=True))

    def test_render_queue_waits_then_gives_up(self):
        slots = self.patch(api, "_render_slots")
        self.patch(api, "_render_image", return_value=b"generated image")
        slots.acquire.return_value = False
        busy = self.post({"data": {"artists": ["A"]}})
        slots.acquire.side_effect = [False, True]
        waited = self.post({"data": {"artists": ["A"]}})

        self.assertEqual(busy.status_code, 503)
        self.assertIn("queue", busy.get_json()["error"]["message"])
        self.assertEqual(waited.status_code, 200)

    def test_rate_limit_blocks_the_sixteenth_request(self):
        self.app.config["RATELIMIT_ENABLED"] = True
        responses = [self.client.post("/api/v1/wrapped", data="{}", content_type="application/json") for _ in range(16)]
        self.assertEqual(responses[14].status_code, 400)
        self.assertEqual(responses[15].status_code, 429)
        self.assertEqual(responses[15].get_json()["error"]["code"], "too_many_requests")
        self.assertTrue(responses[15].headers.get("Retry-After"))


class TemplateCatalogApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        library = Path(tmp.name) / "library"
        library.mkdir()
        base = json.loads((Path(api.template_store.TEMPLATE_OFFICIAL_DIR) / "black.json").read_text())
        for index, slug in enumerate(["neon-dream", "soft-paper", "retro-wave"]):
            template = {**base, "slug": slug, "name": slug.replace("-", " ").title()}
            template["meta"] = {"category": "retro" if slug == "retro-wave" else "soft", "tags": ["test"], "featured": False}
            (library / f"{slug}.json").write_text(json.dumps({
                "slug": slug,
                "template": template,
                "creator": {"id": "cabc", "name": "tester", "website": "javascript:alert(1)"},
                "created_at": f"2026-0{index + 1}-01T00:00:00Z",
            }))
        self.patch(api.template_store, "TEMPLATE_LIBRARY_DIR", new=library)
        self.patch(api.template_store, "read_uses_map", return_value={"retro-wave": 7})
        self.patch(api.template_store, "read_wrapped_count", return_value=0)
        self.patch(api, "TEMPLATE_PREVIEW_DIR", new=Path(tmp.name) / "previews")
        catalog.clear_cache()
        self.addCleanup(catalog.clear_cache)

    def get_json(self, url):
        response = self.client.get(url)
        return response, response.get_json()

    def slugs(self, url):
        return [item["slug"] for item in self.get_json(url)[1]["templates"]]

    def test_cursor_pages_cover_every_template_once(self):
        total = self.get_json("/api/v1/templates")[1]["page"]["total"]

        for sort in catalog.SORTS:
            with self.subTest(sort=sort):
                slugs, cursor = [], None
                while True:
                    _, body = self.get_json(f"/api/v1/templates?limit=2&sort={sort}" + (f"&cursor={cursor}" if cursor else ""))
                    slugs += [item["slug"] for item in body["templates"]]
                    cursor = body["page"]["next_cursor"]
                    self.assertEqual(body["page"]["has_more"], cursor is not None)
                    if not cursor:
                        break
                self.assertEqual(sorted(set(slugs)), sorted(slugs))
                self.assertEqual(len(slugs), total)

    def test_sorting_filters_and_entry_shape(self):
        entry = self.get_json("/api/v1/templates?q=neon")[1]["templates"][0]

        self.assertEqual(self.slugs("/api/v1/templates?origin=community&sort=newest"), ["retro-wave", "soft-paper", "neon-dream"])
        self.assertEqual(self.slugs("/api/v1/templates?origin=community")[0], "retro-wave")
        self.assertEqual(self.slugs("/api/v1/templates?category=retro"), ["retro-wave"])
        self.assertEqual(self.slugs("/api/v1/templates?q=soft%20PAPER"), ["soft-paper"])
        self.assertEqual(entry["creator"], {"name": "tester", "id": "cabc"})
        self.assertIn(f"/neon-dream/preview.png?v={entry['version']}", entry["links"]["preview"])
        self.assertTrue(entry["links"]["use"].endswith("/?template=neon-dream"))

    def test_rejects_invalid_catalog_queries(self):
        cursor = self.get_json("/api/v1/templates?limit=1")[1]["page"]["next_cursor"]
        cases = [
            ("/api/v1/templates?page=2", "Unsupported query parameters"),
            ("/api/v1/templates?limit=51", "limit"),
            ("/api/v1/templates?sort=random", "sort"),
            ("/api/v1/templates?category=loud", "category"),
            ("/api/v1/templates?featured=yes", "featured"),
            ("/api/v1/templates?cursor=%%%", "cursor is invalid"),
            (f"/api/v1/templates?sort=name&cursor={cursor}", "different query"),
            ("/api/v1/templates/neon-dream/preview.png?size=xl", "size"),
        ]

        for url, message in cases:
            with self.subTest(url=url):
                response, body = self.get_json(url)

                self.assertEqual(response.status_code, 400)
                self.assertIn(message, body["error"]["message"])

    def test_detail_and_conditional_requests(self):
        listing = self.client.get("/api/v1/templates")
        unchanged = self.client.get("/api/v1/templates", headers={"If-None-Match": listing.headers["ETag"]})
        detail, body = self.get_json("/api/v1/templates/neon-dream")
        missing = self.client.get("/api/v1/templates/not-a-template")

        self.assertIn("public", listing.headers["Cache-Control"])
        self.assertIn("ETag", listing.headers["Access-Control-Expose-Headers"])
        self.assertEqual(unchanged.status_code, 304)
        self.assertEqual(detail.status_code, 200)
        self.assertIn("elements", body["template"]["definition"])
        self.assertNotIn("creator", body["template"]["definition"])
        self.assertEqual(missing.status_code, 404)

    def test_preview_is_rendered_once_and_cached(self):
        version = self.get_json("/api/v1/templates/neon-dream")[1]["template"]["version"]
        with mock.patch.object(api, "_acquire_render_slot", return_value=False):
            busy = self.client.get("/api/v1/templates/neon-dream/preview.png")
        render = self.patch(api, "_render_image", return_value=b"\x89PNG preview")
        first = self.client.get(f"/api/v1/templates/neon-dream/preview.png?size=sm&v={version}")
        second = self.client.get("/api/v1/templates/neon-dream/preview.png?size=sm")
        unchanged = self.client.get("/api/v1/templates/neon-dream/preview.png?size=sm", headers={"If-None-Match": second.headers["ETag"]})

        self.assertEqual(busy.status_code, 503)
        self.assertTrue(busy.headers.get("Retry-After"))
        render.assert_called_once()
        self.assertEqual(render.call_args.kwargs, {"sample_art": True, "output_width": catalog.PREVIEW_SIZES["sm"]})
        self.assertEqual((first.mimetype, second.data), ("image/png", b"\x89PNG preview"))
        self.assertIn("immutable", first.headers["Cache-Control"])
        self.assertNotIn("immutable", second.headers["Cache-Control"])
        self.assertEqual(unchanged.status_code, 304)


if __name__ == "__main__":
    unittest.main()
