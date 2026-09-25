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

    def test_rejects_unknown_data_fields_with_json_error(self):
        response = self.post({"data": {"artists": ["A"], "plays": 10}})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "bad_request")
        self.assertIn("Unsupported data fields", response.get_json()["error"]["message"])

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

    def test_rejects_more_than_ten_ranked_items(self):
        response = self.post({"data": {"artists": [f"Artist {n}" for n in range(11)]}})

        self.assertEqual(response.status_code, 400)
        self.assertIn("at most 10", response.get_json()["error"]["message"])

    def test_rejects_negative_minutes(self):
        response = self.post({"data": {"artists": ["A"], "minutes": "-10"}})

        self.assertEqual(response.status_code, 400)
        self.assertIn("non-negative", response.get_json()["error"]["message"])

    def test_rejects_artwork_with_too_many_pixels(self):
        oversized_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + (5000).to_bytes(4, "big") + (5000).to_bytes(4, "big")
        artwork = "data:image/png;base64," + base64.b64encode(oversized_png).decode("ascii")
        response = self.post({"data": {"artists": ["Artist"], "artwork": artwork}})

        self.assertEqual(response.status_code, 400)
        self.assertIn("pixel image limit", response.get_json()["error"]["message"])

    def test_rejects_invalid_period_and_template(self):
        period_response = self.post({
            "source": {
                "type": "provider",
                "provider": "listenbrainz",
                "username": "fan",
                "range": {"preset": "specific_month", "month": 13, "year": 2025},
            },
        })
        template_response = self.post({"data": {"artists": ["A"]}, "template": "missing-template"})

        self.assertEqual(period_response.status_code, 400)
        self.assertEqual(template_response.status_code, 404)

    def test_navidrome_is_not_accepted_server_side(self):
        response = self.post({
            "source": {"type": "provider", "provider": "navidrome", "username": "fan"},
        })

        self.assertEqual(response.status_code, 400)
        self.assertIn("browser-only", response.get_json()["error"]["message"])

    def test_rejects_oversized_body(self):
        body = b"{" + b" " * api.MAX_API_REQUEST_BYTES + b"}"
        response = self.client.post("/api/v1/wrapped", data=body, content_type="application/json")

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.get_json()["error"]["code"], "request_entity_too_large")

    def test_rejects_invalid_content_type_and_json(self):
        type_response = self.client.post("/api/v1/wrapped", data="{}", content_type="text/plain")
        json_response = self.client.post("/api/v1/wrapped", data="{", content_type="application/json")

        self.assertEqual(type_response.status_code, 415)
        self.assertEqual(json_response.status_code, 400)

    def test_rejects_browser_render_formats(self):
        response = self.post({"data": {"artists": ["A"]}, "format": "html"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("png or svg", response.get_json()["error"]["message"])

    def test_rejects_invalid_provider_limit_and_artwork_options(self):
        count_response = self.post({"source": {"type": "provider", "provider": "listenbrainz", "username": "fan", "limit": 11}})
        source_response = self.post({
            "data": {"artists": ["A"]},
            "artwork": {"provider": "listenbrainz", "username": "fan", "source": "cover"},
        })

        self.assertEqual(count_response.status_code, 400)
        self.assertEqual(source_response.status_code, 400)

    def test_returns_busy_error_when_render_slots_are_full(self):
        with mock.patch.object(api, "_render_slots") as slots:
            slots.acquire.return_value = False
            response = self.post({"data": {"artists": ["A"]}})

        self.assertEqual(response.status_code, 503)
        self.assertIn("queue", response.get_json()["error"]["message"])

    def test_renderer_queue_waits_for_a_slot(self):
        with (
            mock.patch.object(api, "_render_slots") as slots,
            mock.patch.object(api, "_render_image", return_value=b"generated image"),
        ):
            slots.acquire.side_effect = [False, True]
            response = self.post({"data": {"artists": ["A"]}})

        self.assertEqual(response.status_code, 200)

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
