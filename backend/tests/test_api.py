from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import catalog, main
from .fixtures import release


class ApiTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.data, self.runtime, self.boundaries = root / "data", root / "runtime", root / "boundaries"
        for target in (patch.multiple(catalog, DATA=self.data, RUNTIME=self.runtime),
                       patch.object(main, "BOUNDARIES", self.boundaries)):
            target.start()
            self.addCleanup(target.stop)
        main.analytics_cached.cache_clear()
        self.filters = {"country": "AU", "year": 2024}

    def start(self):
        client = self.enterContext(TestClient(main.app))
        for _ in range(800):
            if client.get("/api/health").json()["ready"]:
                return client
            sleep(.025)
        self.fail(client.get("/api/datasets").text)

    def test_empty(self):
        client = self.start()
        self.assertEqual(client.get("/api/datasets").json()["releases"], [])
        self.assertEqual(client.get("/api/regions?country=AU").json()["features"], [])
        self.assertEqual(client.post("/api/analytics/overview", json=self.filters).status_code, 404)

    def test_ingestion_and_incremental_reuse(self):
        folder = release(self.data)
        broken = release(self.data, "Brazil")
        (broken / catalog.PRODUCTS[3]).write_text("broken")
        wrong = release(self.data, "Indonesia")
        (wrong / catalog.PRODUCTS[0]).write_bytes((folder / catalog.PRODUCTS[1]).read_bytes())
        before = {path.name: path.stat().st_mtime_ns for path in folder.iterdir()}
        first = catalog.prepare()
        self.assertEqual(first["AU", 2024]["status"], "ready")
        self.assertEqual(first["BR", 2024]["status"], "invalid")
        self.assertIn("missing", first["ID", 2024]["error"])
        self.assertTrue(first["AU", 2024]["calendar_from_archive"])
        self.assertEqual(first["AU", 2024]["rows"][catalog.PRODUCTS[0]], 3)
        path = first["AU", 2024]["cache"] / "observations.parquet"
        mtime = path.stat().st_mtime_ns
        release(self.data, year=2025)
        self.assertEqual(catalog.prepare()["AU", 2025]["status"], "ready")
        self.assertEqual(path.stat().st_mtime_ns, mtime)
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in folder.iterdir()}, before)

    def test_all_twenty_four_partitions(self):
        for code, (name, _) in catalog.COUNTRIES.items():
            for year in catalog.YEARS:
                release(self.data, name, year, copies=2 if (code, year) == ("ZA", 2025) else 1)
        client = self.start()
        items = client.get("/api/datasets").json()["releases"]
        self.assertEqual(len(items), 24)
        self.assertTrue(all(item["status"] == "ready" for item in items))
        comparison = client.post("/api/analytics/year-comparison", json={"country": "ZA", "year": 2025})
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual([row["total"] for row in comparison.json()], [3, 3, 3, 3, 3, 6])
        other = client.post("/api/analytics/year-comparison", json={"country": "BR", "year": 2025})
        self.assertEqual([row["total"] for row in other.json()], [3, 3, 3, 3, 3, 3])

    def test_analytics_spatial_calendar_and_tracks(self):
        release(self.data)
        release(self.data, year=2023)
        self.boundaries.mkdir()
        region = {"type": "Feature", "id": "test", "properties": {"shapeName": "Test region"},
                  "geometry": {"type": "Polygon", "coordinates": [[[139,-31],[140.2,-31],[140.2,-30],[139,-30],[139,-31]]]}}
        (self.boundaries / "AU.geojson").write_text(json.dumps({"features": [region]}))
        client = self.start()

        def post(route, **params):
            res = client.post("/api/" + route, json=self.filters | params)
            self.assertEqual(res.status_code, 200, res.text)
            return res.json()

        overview = post("analytics/overview")
        self.assertEqual(overview["metrics"]["detections"], 3)
        self.assertEqual(overview["metrics"]["tracks"], 1)
        self.assertEqual(overview["metrics"]["linked"], 2)
        self.assertEqual(overview["metrics"]["unresolved"], 1)
        calendar = post("analytics/calendar", start="2024-03-01", end="2024-03-01")
        self.assertEqual(len(calendar), 366)
        self.assertEqual(calendar[59], {"day": "2024-02-29", "n": 1})
        self.assertEqual(len(post("analytics/calendar", year=2023)), 365)
        self.assertEqual(sum(r["n"] for r in post("analytics/temporal", start="2024-03-01", sensor="VIIRS JPSS-1")), 1)
        polygon = [[139,-31],[140.1,-31],[140.1,-30],[139,-30]]
        self.assertEqual(post("analytics/overview", polygon=polygon)["metrics"]["detections"], 1)
        self.assertEqual(post("analytics/spatial", polygon=polygon)["cells"][0]["n"], 1)
        self.assertEqual(post("analytics/overview", region="test")["metrics"]["detections"], 1)
        self.assertEqual(post("analytics/regions")[0]["n"], 1)
        compare = post("analytics/year-comparison", years=[2022,2023,2024], sensor="MODIS")
        self.assertEqual([r["total"] for r in compare], [None,1,1])
        self.assertEqual(compare[-1]["yoy_pct"], 0)
        self.assertEqual(post("analytics/sensors")["stats"][0]["n"], 1)
        self.assertEqual(post("analytics/tracks")[0]["detections"], 2)
        self.assertEqual(post("map/tracks", bbox=[139,-31,142,-30], zoom=8)["rows"][0]["id"], "track-1")
        self.assertTrue(post("map/detections", bbox=[139,-31,142,-30], zoom=10, limit=1)["truncated"])
        self.assertEqual(post("map/detections", bbox=[139,-31,142,-30], zoom=4)["mode"], "density")
        self.assertEqual(client.get("/api/detections/d0-0?country=AU&year=2024").json()["candidate_event_id"], "track-1")
        self.assertEqual(len(client.get("/api/tracks/track-1?country=AU&year=2024").json()["members"]), 2)
        self.assertIn("synthetic fixture", client.get("/api/quality/report?country=AU&year=2024&name=validation.json").json()["text"])
        self.assertEqual(client.post("/api/analytics/calendar", json=self.filters | {"polygon": [[0,0],[1,1],[0,1],[1,0]]}).status_code, 422)
        self.assertEqual(client.post("/api/analytics/calendar", json=self.filters | {"start": "2023-12-30"}).status_code, 422)
        with ThreadPoolExecutor(max_workers=3) as pool:
            outputs = list(pool.map(lambda _: post("analytics/overview", sensor="MODIS"), range(3)))
        self.assertEqual([r["metrics"]["detections"] for r in outputs], [1,1,1])
