"""Tests for running several nodes: counters, artwork, badges and templates."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests

from wrapped_fm import badge_store, cluster, metrics, routes, temp_artwork
from wrapped_fm import templates as store
from wrapped_fm.app import create_app

AUTH = {"Authorization": "Bearer s3cret"}


def _response(status=200, body=None, content=b"", content_type="application/json"):
    response = mock.Mock(status_code=status, content=content, headers={"Content-Type": content_type})
    response.json.return_value = body if body is not None else {}
    response.raise_for_status.side_effect = None if status < 400 else requests.HTTPError(str(status))
    return response


class NodeTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "wrapped-count.txt").write_text("1200")
        (self.dir / "template-uses.json").write_text(json.dumps({"black": 40, "retro-wave": 3}))
        self.patch(metrics, "COUNTER_DB", self.dir / "counters.db")
        self.patch(metrics, "WRAPPED_COUNT_FILE", self.dir / "wrapped-count.txt")
        self.patch(metrics, "LEGACY_USES_FILE", self.dir / "template-uses.json")
        self.patch(metrics, "NODE_ID", "homelab")
        self.patch(cluster, "CLUSTER_STATE_DIR", self.dir / "cluster")
        self.patch(cluster, "CLUSTER_SECRET", "s3cret")
        self.patch(cluster, "CLUSTER_PEERS", [])
        self.patch(cluster, "CLUSTER_PRIMARY", "")
        self.patch(temp_artwork, "TEMP_ARTWORK_DIR", self.dir / "artwork")
        self.patch(badge_store, "BADGE_SNAPSHOT_DIR", str(self.dir / "badges"))
        for attr in ("TEMPLATE_LIBRARY_DIR", "TEMPLATE_ASSET_DIR", "TEMPLATE_SUBMISSION_DIR", "TEMPLATE_CREATOR_DIR"):
            self.patch(store, attr, str(self.dir / attr.lower()))

    def patch(self, target, attribute, value):
        patcher = mock.patch.object(target, attribute, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def client(self):
        app = create_app()
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        return app.test_client()


class CounterTests(NodeTestCase):
    def test_legacy_import_keeps_old_totals_once(self):
        self.assertEqual(metrics.read_wrapped_count(), 1200)
        self.assertEqual(metrics.read_totals(metrics.TEMPLATE_PREFIX), {"black": 40, "retro-wave": 3})

        metrics._initialised.clear()
        self.assertEqual(metrics.read_wrapped_count(), 1200)

    def test_increment_counts_total_and_service(self):
        metrics.increment_wrapped_count(service="lastfm")
        total = metrics.increment_wrapped_count(service="not-a-service")

        self.assertEqual(total, 1202)
        stats = metrics.read_stats()
        self.assertEqual(stats["services"]["lastfm"], 1)
        self.assertEqual(stats["days"][-1]["count"], 2)

    def test_merge_takes_max_per_row_without_double_counting(self):
        metrics.increment_wrapped_count()
        peer_rows = [["hetzner", "wrapped", "2026-10-25", 5], ["legacy", "wrapped", "", 1200]]

        metrics.merge_rows(peer_rows)
        metrics.merge_rows(peer_rows)
        metrics.merge_rows([["hetzner", "wrapped", "2026-10-25", 7]])

        self.assertEqual(metrics.read_wrapped_count(), 1200 + 1 + 7)

    def test_merge_drops_bad_rows(self):
        merged = metrics.merge_rows([
            ["x", "Bad Metric", "", 1],
            ["x", "wrapped", "yesterday", 1],
            ["x", "wrapped", "", -4],
            ["x", "wrapped", "", True],
            "nope",
            ["x", "wrapped", "", 2],
        ])

        self.assertEqual(merged, 1)

    def test_sync_survives_a_dead_peer(self):
        self.patch(cluster, "CLUSTER_PEERS", ["http://down", "http://up"])

        def fake_get(base, path, **kwargs):
            if base == "http://down":
                raise requests.ConnectionError("down")
            return _response(body={"rows": [["hetzner", "wrapped", "", 10]]})

        with mock.patch.object(cluster, "peer_get", side_effect=fake_get):
            results = metrics.sync_peers()

        self.assertEqual(results, {"http://down": False, "http://up": True})
        self.assertEqual(metrics.read_wrapped_count(), 1210)

    def test_background_jobs_run_once_per_interval(self):
        with mock.patch.object(cluster.time, "time", return_value=1000.0):
            self.assertTrue(cluster._claim("job", 60))
            self.assertFalse(cluster._claim("job", 60))
        with mock.patch.object(cluster.time, "time", return_value=1061.0):
            self.assertTrue(cluster._claim("job", 60))


class ArtworkAndBadgeTests(NodeTestCase):
    def test_artwork_is_shared_between_workers_via_disk(self):
        token = temp_artwork.store_artwork(b"png-bytes", "image/png")

        self.assertEqual(temp_artwork.fetch_artwork(token), (b"png-bytes", "image/png"))
        with self.assertRaises(temp_artwork.ArtworkMissingError):
            temp_artwork.fetch_artwork("../../etc/passwd")

    def test_missing_artwork_is_pulled_from_a_peer_and_kept(self):
        self.patch(cluster, "CLUSTER_PEERS", ["http://hetzner"])
        peer = _response(content=b"jpeg-bytes", content_type="image/jpeg")

        with mock.patch.object(cluster, "peer_get", return_value=peer) as peer_get:
            first = temp_artwork.fetch_artwork("tokenfromhetzner")
            second = temp_artwork.fetch_artwork("tokenfromhetzner")

        self.assertEqual(first, (b"jpeg-bytes", "image/jpeg"))
        self.assertEqual(second, first)
        peer_get.assert_called_once_with("http://hetzner", "/internal/artwork/tokenfromhetzner")

    def test_badges_push_on_publish_and_pull_on_miss(self):
        self.patch(cluster, "CLUSTER_PEERS", ["http://hetzner"])
        secret = "a" * 24
        with mock.patch.object(cluster, "push_to_peers") as push:
            badge_id = badge_store.store_snapshot(secret, {"artist": "Phoebe Bridgers"})
        push.assert_called_once_with(f"/internal/badges/{badge_id}", {"values": mock.ANY})

        other_id = "b" * 24
        peer = _response(body={"values": {"genre": "indie"}})
        with mock.patch.object(cluster, "peer_get", return_value=peer):
            snapshot = badge_store.fetch_snapshot(other_id)

        self.assertEqual(snapshot["genre"], "indie")
        self.assertEqual(badge_store.fetch_local_snapshot(other_id)["genre"], "indie")


class TemplateReplicationTests(NodeTestCase):
    def test_replica_mirrors_library_and_assets(self):
        primary = {
            "library": {"retro-wave.json": b'{"template": {}}'},
            "assets": {"retro-wave/background.png": b"png"},
        }
        manifest = {
            kind: {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
            for kind, files in primary.items()
        }
        manifest["library"]["../../escape.json"] = "x"
        os.makedirs(store.TEMPLATE_LIBRARY_DIR)
        Path(store.TEMPLATE_LIBRARY_DIR, "removed.json").write_text("{}")

        stats = store.apply_replication(manifest, lambda kind, name: primary[kind][name])

        self.assertEqual(stats, {"written": 2, "removed": 1})
        self.assertEqual(sorted(os.listdir(store.TEMPLATE_LIBRARY_DIR)), ["retro-wave.json"])
        local = store.replication_manifest()
        self.assertEqual(list(local["library"]), ["retro-wave.json"])
        self.assertEqual(local["assets"], manifest["assets"])

    def test_asset_paths_cannot_escape(self):
        self.assertIsNone(store.resolve_template_asset_path("/template-assets/x/../../../.env"))
        self.assertIsNone(store.replicated_path("assets", "x/../../.env"))
        self.assertIsNotNone(store.resolve_template_asset_path("/template-assets/x/background.png"))


class RouteTests(NodeTestCase):
    def test_internal_routes_need_the_secret(self):
        client = self.client()
        for path in ("/internal/counters", "/internal/templates/manifest", "/internal/badges/" + "c" * 24):
            with self.subTest(path=path):
                self.assertEqual(client.get(path).status_code, 404)
                self.assertEqual(client.get(path, headers={"Authorization": "Bearer nope"}).status_code, 404)

        response = client.get("/internal/counters", headers=AUTH)
        self.assertIn(["legacy", "wrapped", "", 1200], response.get_json()["rows"])

    def test_public_count_keeps_its_shape(self):
        client = self.client()
        client.post("/metrics/wrapped", json={"service": "navidrome"})

        body = client.get("/metrics/wrapped").get_json()

        self.assertEqual(set(body), {"count", "since"})
        self.assertEqual(body["count"], 1201)
        self.assertEqual(client.get("/metrics/stats").get_json()["services"]["navidrome"], 1)

    def test_replica_forwards_submissions_and_reports_a_down_primary(self):
        self.patch(cluster, "CLUSTER_PRIMARY", "http://homelab")
        client = self.client()

        with mock.patch.object(cluster, "peer_post", return_value=_response(body={"ok": True, "submission_id": "abc"})) as post:
            ok = client.post("/api/templates/submit", json={"template": {}})
        with mock.patch.object(cluster, "peer_post", return_value=_response(400, {"description": "Bad template."})):
            bad = client.post("/api/templates/submit", json={"template": {}})
        with mock.patch.object(cluster, "peer_post", side_effect=requests.ConnectionError("down")):
            down = client.post("/api/templates/submit", json={"template": {}})

        self.assertEqual(ok.get_json()["submission_id"], "abc")
        post.assert_called_once_with("http://homelab", "/internal/templates/submit", json={"template": {}})
        self.assertEqual(bad.status_code, 400)
        self.assertIn(b"Bad template.", bad.data)
        self.assertEqual(down.status_code, 503)

    def test_primary_handles_forwarded_submissions(self):
        response = self.client().post("/internal/templates/submit", json={"template": {}}, headers=AUTH)

        self.assertEqual(response.status_code, 400)
        self.assertIn("description", response.get_json())
