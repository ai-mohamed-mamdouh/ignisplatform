"""Run with python -m tests.benchmark --rows 1000002 from backend/."""
import argparse
import json
import os
from pathlib import Path
import platform
import resource
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter

from fastapi.testclient import TestClient

from app import catalog, main
from .fixtures import release


def measure(client, method, route, payload=None):
    samples = []
    for _ in range(5):
        start = perf_counter()
        response = client.request(method, "/api/" + route, json=payload)
        response.raise_for_status()
        samples.append(round((perf_counter() - start) * 1000, 1))
    return {"cold_ms": samples[0], "warm_median_ms": median(samples[1:]),
            "json_bytes": len(response.content)}


def benchmark(rows):
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        catalog.DATA = root / "data"
        catalog.RUNTIME = root / "runtime"
        release(catalog.DATA, copies=rows // 3)
        for year in [2020, 2021, 2022, 2023, 2025]:
            release(catalog.DATA, year=year)
        start = perf_counter()
        main.update(catalog.prepare(), None)
        prepared = perf_counter() - start
        base = {"country": "AU", "year": 2024}
        bounds = {"bbox": [139,-31,142,-30], "zoom": 9, "limit": 4000}
        polygon = [[139,-31],[140.4,-31],[140.4,-30],[139,-30]]
        routes = {
            "overview": ("analytics/overview", base),
            "calendar": ("analytics/calendar", base),
            "six_year_comparison": ("analytics/year-comparison", base),
            "sensor_statistics": ("analytics/sensors", base),
            "custom_polygon": ("analytics/overview", base | {"polygon": polygon}),
            "point_viewport": ("map/detections", base | bounds),
            "density_viewport": ("map/detections", base | bounds | {"zoom": 4}),
        }
        client = TestClient(main.app)
        results = {key: measure(client, "POST", route, filters)
                   for key, (route, filters) in routes.items()}
        results["large_response_truncated"] = client.post("/api/map/detections", json=base | bounds).json()["truncated"]
        print(json.dumps({"platform": platform.platform(), "logical_cpus": os.cpu_count(),
                          "rows": rows // 3 * 3, "preparation_seconds": round(prepared, 2),
                          "peak_process_rss_mib_linux": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
                          "routes": results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1000002)
    benchmark(parser.parse_args().rows)
