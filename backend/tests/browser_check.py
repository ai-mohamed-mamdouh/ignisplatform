"""Run with Chromium, playwright and built npm dependencies installed."""
from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter, sleep
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

from .fixtures import release

PROJECT = Path(__file__).resolve().parents[2]


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def process(args, cwd, env):
    child = subprocess.Popen(args, cwd=cwd, env=os.environ | env)
    try:
        yield
    finally:
        child.terminate()
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def wait_for(url):
    for _ in range(180):
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            sleep(.15)
    raise RuntimeError(f"Timed out waiting for {url}")


def check():
    with TemporaryDirectory() as temporary, ExitStack() as stack, sync_playwright() as playwright:
        root = Path(temporary)
        api, web = port(), port()
        api_url = f"http://127.0.0.1:{api}"
        base = f"http://127.0.0.1:{web}"
        env = {"DATA_DIR": str(root / "data"), "RUNTIME_DIR": str(root / "runtime")}
        backend = lambda: process([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(api), "--no-access-log"],
                                  PROJECT / "backend", env)
        mode = [] if os.getenv("BROWSER_DEV") else ["preview"]
        stack.enter_context(process([str(PROJECT / "frontend/node_modules/.bin/vite"), *mode, "--host", "127.0.0.1",
                                     "--port", str(web), "--strictPort"], PROJECT / "frontend", {"WILDFIRE_API_PROXY": api_url}))
        chromium = playwright.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH", "/usr/bin/chromium"),
                                              headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
        page = chromium.new_page(viewport={"width": 1440, "height": 900})
        page.set_default_timeout(12000)
        js_errors = []
        page.on("pageerror", lambda error: js_errors.append(str(error)))
        with backend():
            wait_for(api_url + "/api/health")
            wait_for(base)
            start = perf_counter()
            page.goto(base, wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="No datasets installed")).to_be_visible(timeout=30000)
            empty_ms = (perf_counter() - start) * 1000
            expect(page.locator(".maplibregl-canvas")).to_be_visible(timeout=30000)
            expect(page.get_by_text("Loading basemap…")).to_have_count(0, timeout=30000)
            assert page.locator(".map-pane").bounding_box()["x"] < page.locator(".analytics-pane").bounding_box()["x"]
        release(root / "data")
        release(root / "data", year=2023)
        release(root / "data", country="Brazil")
        with backend():
            wait_for(api_url + "/api/health")
            start = perf_counter()
            page.reload(wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="Monthly activity", exact=True)).to_be_visible(timeout=30000)
            ready_ms = (perf_counter() - start) * 1000
            page.get_by_role("button", name="Expand panel").click()
            expect(page.locator(".workspace")).to_have_class(re.compile("expanded"))
            page.get_by_role("button", name="Collapse analytics").click()
            page.get_by_role("button", name="Open analytics").click()
            page.get_by_label("Country", exact=True).select_option("BR")
            expect(page.get_by_label("Region", exact=True).locator("option")).to_have_count(28, timeout=30000)
            page.get_by_label("Country", exact=True).select_option("AU")
            page.get_by_label("Year", exact=True).select_option("2024")
            page.get_by_label("Sensor", exact=True).select_option("MODIS")
            page.get_by_label("Region", exact=True).select_option(index=1)
            page.get_by_role("button", name="Reset filters").click()
            start = perf_counter()
            page.get_by_role("button", name="Temporal", exact=True).click()
            expect(page.locator(".calendar .day")).to_have_count(366, timeout=30000)
            calendar_ms = (perf_counter() - start) * 1000
            page.get_by_role("button", name="2024-02-29 · 1 detections").click()
            expect(page.get_by_label("From UTC")).to_have_value("2024-02-29")
            expect(page.locator(".calendar .day")).to_have_count(366)
            page.get_by_role("button", name="Reset dates").click()
            page.get_by_label("2022", exact=True).uncheck()
            expect(page.get_by_role("cell", name="2022", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Sensors", exact=True).click()
            expect(page.get_by_role("heading", name="Sensor measurements")).to_be_visible(timeout=30000)
            page.get_by_role("button", name="Candidate Tracks", exact=True).click()
            page.get_by_role("button", name="track-1", exact=True).click()
            expect(page.get_by_role("button", name="Focus observations")).to_be_visible(timeout=30000)
            page.get_by_role("button", name="Close details").click()
            page.get_by_label("Map layer").select_option("density")
            page.get_by_role("button", name="Draw rectangle").click()
            canvas=page.locator(".maplibregl-canvas")
            canvas.click(position={"x":250,"y":240})
            canvas.click(position={"x":390,"y":335})
            page.get_by_role("button", name="Apply", exact=True).click()
            expect(page.get_by_label("Region", exact=True)).to_have_value("@custom")
            page.get_by_role("button", name="Clear geographic selection").click()
            page.get_by_role("button", name="Draw polygon").click()
            for x,y in [(230,240),(420,240),(355,365)]:
                canvas.click(position={"x":x,"y":y})
            page.get_by_role("button", name="Apply", exact=True).click()
            expect(page.get_by_label("Region", exact=True)).to_have_value("@custom")
            page.get_by_role("button", name="Data Quality", exact=True).click()
            expect(page.get_by_role("heading", name="Validation archive")).to_be_visible()
            page.set_viewport_size({"width":390,"height":844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.locator(".map-pane").bounding_box()["y"] < page.locator(".analytics-pane").bounding_box()["y"]
            assert not js_errors, js_errors
        chromium.close()
        print(json.dumps({"empty_state_ms": round(empty_ms), "fixture_overview_ms": round(ready_ms),
                          "calendar_tab_ms": round(calendar_ms), "browser": "Chromium headless, 1440 × 900"}, indent=2))


if __name__ == "__main__":
    check()
