"""Tests for the versioned Wrapped image API."""

from __future__ import annotations

import base64
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from wrapped_fm import api
from wrapped_fm.app import create_app


class WrappedApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        self.client = self.app.test_client()
        self.count_patch = mock.patch.object(api, "increment_wrapped_count")
        self.template_use_patch = mock.patch.object(api.template_store, "record_template_use")
        self.increment_count = self.count_patch.start()
        self.record_template_use = self.template_use_patch.start()
        self.addCleanup(self.count_patch.stop)
        self.addCleanup(self.template_use_patch.stop)

    def post(self, payload, **headers):
        return self.client.post(
            "/api/v1/wrapped",
            data=json.dumps(payload),
            content_type="application/json",
            headers=headers,
        )

    def test_custom_data_returns_a_png_file(self):
        response = self.post({
            "data": {
                "artists": ["  Alpha   Artist  "],
                "tracks": ["Track One"],
                "minutes": 1234,
                "genre": "Indie pop",
            },
            "template": "black",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="wrapped-black.png"')

    def test_svg_format_returns_a_rendered_svg_file(self):
        response = self.post({
            "data": {"artists": ["Artist One"], "genre": "Rock"},
            "format": "svg",
        })
        svg = response.data.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/svg+xml")
        self.assertIn("<svg", svg)
        self.assertIn("<image", svg)
        self.assertIn("<path", svg)
        self.assertNotIn("<text", svg)

    def test_custom_artwork_is_drawn_by_the_server_renderer(self):
        image_path = Path(__file__).resolve().parents[2] / "static" / "favicon-lavender-16.png"
        artwork = "data:image/png;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")
        response = self.post({
            "data": {"artists": ["Artist One"], "artwork": artwork},
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(response.data[:8], b"\x89PNG\r\n\x1a\n")

    def test_provider_source_reuses_listenbrainz_functions(self):
        range_obj = api.resolve_preset("last_year")
        with (
            mock.patch.object(api, "get_top_artists_payload", return_value=[{"artist_name": "Alpha"}]) as artists,
            mock.patch.object(api, "get_top_tracks_payload", return_value=[{"track_name": "One"}]),
            mock.patch.object(api, "estimate_total_listen_minutes", return_value="42"),
            mock.patch.object(api, "get_top_genre", return_value="Rock"),
            mock.patch.object(api, "_provider_artwork", return_value=None) as artwork,
        ):
            response = self.post({
                "source": {
                    "type": "provider",
                    "provider": "listenbrainz",
                    "username": "music-fan",
                    "range": {"preset": "last_year"},
                },
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertEqual(artists.call_args.args[1], 5)
        artwork.assert_called_once()
        self.assertEqual(artwork.call_args.args[1], range_obj)

    def test_provider_limit_can_be_selected(self):
        with (
            mock.patch.object(api, "get_top_artists_payload", return_value=[{"artist_name": str(i)} for i in range(10)]) as artists,
            mock.patch.object(api, "get_top_tracks_payload", return_value=[{"track_name": str(i)} for i in range(10)]) as tracks,
            mock.patch.object(api, "estimate_total_listen_minutes", return_value="42"),
            mock.patch.object(api, "get_top_genre", return_value="Rock"),
            mock.patch.object(api, "_provider_artwork", return_value=None),
        ):
            response = self.post({
                "source": {"type": "provider", "provider": "listenbrainz", "username": "music-fan", "limit": 8},
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(artists.call_args.args[1], 8)
        self.assertEqual(tracks.call_args.args[1], 8)

    def test_artwork_can_use_a_different_provider_and_release_covers(self):
        image_path = Path(__file__).resolve().parents[2] / "static" / "favicon-lavender-16.png"
        with (
            mock.patch.object(api, "get_top_artists_payload", return_value=[{"artist_name": "Alpha"}]),
            mock.patch.object(api, "get_top_tracks_payload", return_value=[{"track_name": "One"}]),
            mock.patch.object(api, "estimate_total_listen_minutes", return_value="42"),
            mock.patch.object(api, "get_top_genre", return_value="Rock"),
            mock.patch.object(api, "fetch_top_artist_image", return_value=SimpleNamespace(content=image_path.read_bytes())) as fetch_art,
        ):
            response = self.post({
                "source": {"type": "provider", "provider": "listenbrainz", "username": "music-fan"},
                "artwork": {"provider": "lastfm", "source": "release"},
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fetch_art.call_args.kwargs["service"], "lastfm")
        self.assertEqual(fetch_art.call_args.kwargs["preferred_source"], "release")

    def test_custom_json_can_pull_artwork_and_defaults_to_cover_crop(self):
        image_path = Path(__file__).resolve().parents[2] / "static" / "favicon-lavender-16.png"
        with (
            mock.patch.object(api, "fetch_top_artist_image", return_value=SimpleNamespace(content=image_path.read_bytes())),
            mock.patch.object(api, "_render_image", return_value=b"generated image") as render,
        ):
            response = self.post({
                "data": {"artists": ["Artist One"]},
                "artwork": {"provider": "listenbrainz", "username": "music-fan", "fit": "cover"},
            })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(render.call_args.args[0]["artwork"]["contain"])

    def test_custom_artwork_can_preserve_its_full_image(self):
        image_path = Path(__file__).resolve().parents[2] / "static" / "favicon-lavender-16.png"
        artwork_data = "data:image/png;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")
        with mock.patch.object(api, "_render_image", return_value=b"generated image") as render:
            response = self.post({
                "data": {"artists": ["Artist One"], "artwork": artwork_data},
                "artwork": {"fit": "contain"},
            })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(render.call_args.args[0]["artwork"]["contain"])

    def test_api_render_updates_wrapped_and_template_counters(self):
        with mock.patch.object(api, "_render_image", return_value=b"generated image"):
            response = self.post({"data": {"artists": ["Artist One"]}, "template": "black"})

        self.assertEqual(response.status_code, 200)
        self.increment_count.assert_called_once_with()
        self.record_template_use.assert_called_once_with("black")

    def test_rejects_invalid_custom_data(self):
        oversized_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (5000).to_bytes(4, "big") + (5000).to_bytes(4, "big")
        oversized_artwork = "data:image/png;base64," + base64.b64encode(oversized_png).decode("ascii")
        cases = [
            ("unknown field", {"artists": ["A"], "plays": 10}, "Unsupported data fields"),
            ("too many artists", {"artists": [f"Artist {n}" for n in range(11)]}, "at most 10"),
            ("negative minutes", {"artists": ["A"], "minutes": "-10"}, "non-negative"),
            ("oversized artwork", {"artists": ["A"], "artwork": oversized_artwork}, "pixel image limit"),
        ]

        for name, data, message in cases:
            with self.subTest(name=name):
                response = self.post({"data": data})

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"]["code"], "bad_request")
                self.assertIn(message, response.get_json()["error"]["message"])

    def test_api_unknown_route_returns_json_error(self):
        response = self.client.get("/api/v1/unknown")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(response.get_json()["error"]["code"], "not_found")
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")

    def test_unexpected_render_errors_return_safe_json(self):
        with mock.patch.object(api, "_render_image", side_effect=RuntimeError("private detail")):
            response = self.post({"data": {"artists": ["Artist One"]}})

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.mimetype, "application/json")
        self.assertEqual(response.get_json()["error"]["code"], "internal_error")
        self.assertNotIn("private detail", response.get_data(as_text=True))

    def test_rejects_invalid_source_template_and_output_options(self):
        cases = [
            ("invalid period", {"source": {"type": "provider", "provider": "listenbrainz", "username": "fan", "range": {"preset": "specific_month", "month": 13, "year": 2025}}}, 400, "source.range is not a valid period"),
            ("missing template", {"data": {"artists": ["A"]}, "template": "missing-template"}, 404, "Template not found"),
            ("Navidrome provider", {"source": {"type": "provider", "provider": "navidrome", "username": "fan"}}, 400, "browser-only"),
            ("provider limit", {"source": {"type": "provider", "provider": "listenbrainz", "username": "fan", "limit": 11}}, 400, "source.limit"),
            ("artwork source", {"data": {"artists": ["A"]}, "artwork": {"provider": "listenbrainz", "username": "fan", "source": "cover"}}, 400, "artwork.source"),
        ]

        for name, payload, status, message in cases:
            with self.subTest(name=name):
                response = self.post(payload)

                self.assertEqual(response.status_code, status)
                self.assertIn(message, response.get_json()["error"]["message"])

    def test_rejects_malformed_request_bodies_and_formats(self):
        oversized_body = b"{" + b" " * api.MAX_API_REQUEST_BYTES + b"}"
        cases = [
            ("oversized body", lambda: self.client.post("/api/v1/wrapped", data=oversized_body, content_type="application/json"), 413, "code", "request_entity_too_large"),
            ("wrong content type", lambda: self.client.post("/api/v1/wrapped", data="{}", content_type="text/plain"), 415, "code", "unsupported_media_type"),
            ("invalid JSON", lambda: self.client.post("/api/v1/wrapped", data="{", content_type="application/json"), 400, "code", "bad_request"),
            ("browser format", lambda: self.post({"data": {"artists": ["A"]}, "format": "html"}), 400, "message", "format must be png or svg"),
        ]

        for name, send, status, field, expected in cases:
            with self.subTest(name=name):
                response = send()

                self.assertEqual(response.status_code, status)
                self.assertIn(expected, response.get_json()["error"][field])

    def test_render_queue_handles_full_and_waiting_slots(self):
        with mock.patch.object(api, "_render_slots") as slots:
            slots.acquire.return_value = False
            busy_response = self.post({"data": {"artists": ["A"]}})

        self.assertEqual(busy_response.status_code, 503)
        self.assertIn("queue", busy_response.get_json()["error"]["message"])

        with (
            mock.patch.object(api, "_render_slots") as slots,
            mock.patch.object(api, "_render_image", return_value=b"generated image"),
        ):
            slots.acquire.side_effect = [False, True]
            waiting_response = self.post({"data": {"artists": ["A"]}})

        self.assertEqual(waiting_response.status_code, 200)

    def test_api_rate_limit_blocks_the_sixteenth_request(self):
        self.app.config["RATELIMIT_ENABLED"] = True
        responses = [
            self.client.post("/api/v1/wrapped", data="{}", content_type="application/json")
            for _ in range(16)
        ]

        self.assertEqual(responses[14].status_code, 400)
        self.assertEqual(responses[15].status_code, 429)
        self.assertEqual(responses[15].mimetype, "application/json")
        self.assertEqual(responses[15].get_json()["error"]["code"], "too_many_requests")
        self.assertTrue(responses[15].headers.get("Retry-After"))

    def test_supports_cross_origin_preflight_for_web_apps(self):
        response = self.client.options("/api/v1/wrapped")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")


if __name__ == "__main__":
    unittest.main()
