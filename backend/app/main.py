from calendar import isleap
from contextlib import asynccontextmanager, contextmanager
from datetime import date, timedelta
from functools import lru_cache
import json
import logging
import math
import os
from threading import Semaphore, Thread
from typing import Literal

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
import pyarrow as pa
import shapely
from shapely.geometry import shape

from .boundaries import read_geometry, read_packed
from .catalog import BOUNDARIES, COUNTRIES, METRICS, PRODUCTS, YEARS, connect, prepare, public, sql_path

log = logging.getLogger(__name__)
releases = {}
status = "Discovering releases"
slots = Semaphore(max(1, int(os.getenv("QUERY_CONCURRENCY", "2"))))
Sensor = Literal["MODIS", "VIIRS SNPP", "VIIRS JPSS-1"]


def update(items, message):
    global releases, status
    releases, status = items, message


def prepare_worker():
    try:
        prepare(update)
    except Exception:
        log.exception("Preparation failed")
        update(releases, "Preparation failed. Check the service log.")


@asynccontextmanager
async def lifespan(_app):
    update({}, "Discovering releases")
    worker = Thread(target=prepare_worker, daemon=True)
    worker.start()
    yield


app = FastAPI(title="Wildfire Intelligence Platform", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)


class Filters(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    country: Literal["AU", "BR", "ID", "ZA"]
    year: int = Field(ge=2020, le=2025)
    sensor: Sensor | None = None
    start: date | None = None
    end: date | None = None
    region: str | None = Field(None, max_length=160)
    polygon: list[tuple[float, float]] | None = Field(None, min_length=3, max_length=256)

    @model_validator(mode="after")
    def validate_filters(self):
        if self.start and self.end and self.start > self.end:
            raise ValueError("Start must be on or before end")
        if any(value and value.year != self.year for value in (self.start, self.end)):
            raise ValueError("Dates must belong to the selected year")
        if self.region and self.polygon:
            raise ValueError("Choose one geographic filter")
        if self.polygon:
            if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in self.polygon):
                raise ValueError("Polygon coordinates out of range")
            polygon = shapely.Polygon(self.polygon)
            if not polygon.is_valid or not polygon.area or polygon.bounds[2] - polygon.bounds[0] > 180:
                raise ValueError("Use a valid polygon that does not cross the antimeridian")
        return self


class MapRequest(Filters):
    bbox: tuple[float, float, float, float]
    zoom: float = Field(ge=0, le=24)
    limit: int = Field(4000, ge=1, le=6000)

    @model_validator(mode="after")
    def validate_bbox(self):
        w, s, e, n = self.bbox
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise ValueError("Invalid viewport bounds")
        return self


class Compare(Filters):
    years: list[int] = Field(default_factory=lambda: list(YEARS), min_length=1, max_length=6)

    @model_validator(mode="after")
    def validate_years(self):
        if len(set(self.years)) != len(self.years) or any(y not in YEARS for y in self.years):
            raise ValueError("Select distinct years between 2020 and 2025")
        return self


def get_release(country, year):
    release = releases.get((country, year))
    if not release or release["status"] != "ready":
        raise HTTPException(404, "This release is unavailable")
    return release


@lru_cache(maxsize=8)
def load_regions(country, modified):
    path = BOUNDARIES / f"{country}.geojson"
    features = json.loads(path.read_text())["features"]
    items = {}
    for feature in features:
        properties = feature["properties"]
        key = str(properties.get("shapeID") or feature.get("id") or properties["shapeName"])
        geom = shapely.make_valid(shape(feature["geometry"]))
        items[key] = (properties.get("shapeName", key), geom)
    return items


def regions(country):
    if country not in COUNTRIES:
        raise HTTPException(404, "Unknown country")
    path = BOUNDARIES / f"{country}.geojson"
    return load_regions(country, path.stat().st_mtime_ns) if path.is_file() else {}


def packed_boundary(country):
    path = BOUNDARIES / country / "regions.json"
    return read_packed(path, path.stat().st_mtime_ns) if path.is_file() else None


def boundary_stamp(country):
    for path in (BOUNDARIES / country / "regions.json", BOUNDARIES / f"{country}.geojson"):
        if path.exists():
            return path.stat().st_mtime_ns
    return None


@app.get("/api/health")
def health():
    return {"ready": status is None, "preparation": status}


@app.get("/api/datasets")
def datasets():
    return {**health(), "releases": [public(item) for item in releases.values()]}


@app.get("/api/countries")
def countries():
    return [{"code": code, "name": value[0].replace("_", " ")} for code, value in COUNTRIES.items()]


@app.get("/api/years")
def years(country: str):
    return [{"year": y, "status": releases.get((country, y), {}).get("status", "missing")} for y in YEARS]


@app.get("/api/regions")
def region_endpoint(country: str):
    if country not in COUNTRIES:
        raise HTTPException(404, "Unknown country")
    packed = packed_boundary(country)
    if packed:
        return {"type": "FeatureCollection", "features": [
            {**item, "properties": {"name": item["properties"]["name"]}}
            for item in packed["features"]]}
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": key, "properties": {"name": name},
         "geometry": shapely.geometry.mapping(geom.simplify(0.008, preserve_topology=True))}
        for key, (name, geom) in regions(country).items()]}


@app.get("/api/quality")
def quality(country: str, year: int):
    release = get_release(country, year)
    filters = Filters(country=country, year=year)
    coverage = analytical("overview", filters)["metrics"]
    return {**public(release), "schemas": release["schemas"], "coverage": coverage}


@app.get("/api/quality/download")
def download_report(country: str, year: int, name: str = Query(max_length=240)):
    release = get_release(country, year)
    if name not in release["reports"]:
        raise HTTPException(404, "Report unavailable")
    return FileResponse(release["cache"] / "reports" / name, filename=name,
                        media_type="application/octet-stream",
                        headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/quality/report")
def report(country: str, year: int, name: str = Query(max_length=240)):
    release = get_release(country, year)
    size = release["reports"].get(name)
    if size is None or not name.lower().endswith((".txt", ".md", ".json", ".csv", ".yaml", ".yml")):
        raise HTTPException(404, "Text report unavailable")
    with (release["cache"] / "reports" / name).open("rb") as file:
        return {"text": file.read(64000).decode(errors="replace"), "truncated": size > 64000}


@contextmanager
def query_connection():
    if not slots.acquire(timeout=3):
        raise HTTPException(503, "Service is busy. Try again shortly.")
    try:
        with connect() as db:
            yield db
    except duckdb.Error as error:
        log.exception("Analytical query failed")
        raise HTTPException(503, "The analytical query could not finish. Try a narrower selection.") from error
    finally:
        slots.release()


def geography(filters):
    if filters.region:
        packed = packed_boundary(filters.country)
        if packed:
            for item in packed["features"]:
                if item["id"] == filters.region:
                    path = BOUNDARIES / filters.country / item["properties"]["file"]
                    return read_geometry(path, path.stat().st_mtime_ns)
            raise HTTPException(422, "Administrative region unavailable")
        item = regions(filters.country).get(filters.region)
        if not item:
            raise HTTPException(422, "Administrative region unavailable")
        return item[1]
    return shapely.Polygon(filters.polygon) if filters.polygon else None


def where(db, filters, *, omit_dates=False, bbox=None):
    expressions, params = [], []
    for column, op, value in (
        ("sensor", "=", filters.sensor),
        ("day", ">=", None if omit_dates else filters.start),
        ("day", "<=", None if omit_dates else filters.end),
    ):
        if value is not None:
            expressions.append(f"{column} {op} ?")
            params.append(value)

    def add_bounds(bounds):
        west, south, east, north = bounds
        expressions.extend(["longitude BETWEEN ? AND ?", "latitude BETWEEN ? AND ?"])
        params.extend([west, east, south, north])

    geom = geography(filters)
    if bbox:
        add_bounds(bbox)
    if geom is not None:
        add_bounds(geom.bounds)
        shapely.prepare(geom)

        def covers(longitude, latitude):
            return pa.array(shapely.intersects_xy(geom, longitude.to_numpy(), latitude.to_numpy()))

        db.create_function("in_selection", covers, ["DOUBLE", "DOUBLE"], "BOOLEAN", type="arrow")
        expressions.append("in_selection(longitude, latitude)")
    return (" WHERE " + " AND ".join(expressions) if expressions else ""), params


def json_value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    return value


def records(db, sql, params=()):
    cursor = db.execute(sql, params)
    names = [col[0] for col in cursor.description]
    return [dict(zip(names, map(json_value, row))) for row in cursor.fetchall()]


def table(release, name="observations"):
    return f"read_parquet({sql_path(release['cache'] / (name + '.parquet'))})"


def calendar_rows(db, release, filters, all_days=False):
    clause, params = where(db, filters, omit_dates=all_days)
    aggregate = not (filters.region or filters.polygon)
    metric = "sum(n)::BIGINT" if aggregate else "count(*)"
    return records(db, f"""SELECT day::VARCHAR AS day, sensor, daynight, {metric} AS n
                      FROM {table(release, 'daily' if aggregate else 'observations')}
                      {clause}{' AND' if clause else ' WHERE'} day IS NOT NULL
                      GROUP BY ALL ORDER BY day""", params)


def track_table(release):
    return f"read_parquet({sql_path(release['source'] / PRODUCTS[1])})"


@lru_cache(maxsize=192)
def analytics_cached(kind, version, boundary_version, payload):
    filters = Filters.model_validate_json(payload)
    release = get_release(filters.country, filters.year)
    with query_connection() as db:
        if kind in {"calendar", "temporal"}:
            if kind == "calendar" and release.get("calendar_from_archive") and not (
                filters.sensor or filters.region or filters.polygon
            ):
                rows = records(db, f"SELECT day::VARCHAR AS day,n FROM {table(release,'verified_calendar')}")
            else:
                rows = calendar_rows(db, release, filters, all_days=kind == "calendar")
            if kind == "temporal":
                return rows
            counts = {}
            for row in rows:
                counts[row["day"]] = counts.get(row["day"], 0) + row["n"]
            first = date(filters.year, 1, 1)
            return [{"day": day, "n": counts.get(day, 0)}
                    for i in range(365 + isleap(filters.year))
                    for day in [(first + timedelta(days=i)).isoformat()]]
        clause, params = where(db, filters)
        selected = f"SELECT * FROM {table(release)}{clause}"
        if kind == "overview":
            if not (filters.start or filters.end or filters.region or filters.polygon):
                cached_metrics = records(db, f"""SELECT * EXCLUDE (sensor) FROM {table(release,'overview')}
                    WHERE sensor IS NOT DISTINCT FROM ?""", [filters.sensor])
                metrics = cached_metrics[0] if cached_metrics else records(db, f"SELECT {METRICS} FROM ({selected})", params)[0]
            else:
                metrics = records(db, f"SELECT {METRICS} FROM ({selected})", params)[0]
            if filters.region or filters.polygon:
                db.remove_function("in_selection")
            return {"metrics": metrics, "daily": calendar_rows(db, release, filters)}
        if kind == "spatial":
            group = """floor(longitude*4)/4 AS x, floor(latitude*4)/4 AS y"""
            if not filters.region and not filters.polygon:
                cells = records(db, f"""SELECT x,y,sum(n)::BIGINT AS n FROM {table(release,'grid')}
                          {clause} GROUP BY ALL ORDER BY n DESC,x,y LIMIT 100""", params)
                monthly = records(db, f"""SELECT substr(day::VARCHAR,1,7) AS month,sensor,
                    sum(n)::BIGINT AS n,count(DISTINCT (x,y)) AS cells FROM {table(release,'grid')}
                    {clause} GROUP BY ALL ORDER BY month""", params)
            else:
                cells = records(db, f"""SELECT {group},count(*) AS n FROM ({selected})
                    GROUP BY ALL ORDER BY n DESC,x,y LIMIT 100""", params)
                monthly = records(db, f"""SELECT substr(day::VARCHAR,1,7) AS month,sensor,count(*) AS n,
                    count(DISTINCT (floor(longitude*4),floor(latitude*4))) AS cells
                    FROM ({selected}) GROUP BY ALL ORDER BY month""", params)
            return {"cells": cells, "monthly": monthly}
        if kind == "sensors":
            stats = records(db, f"""SELECT sensor,count(*) AS n,
                avg(frp) FILTER (isfinite(frp)) AS mean_frp,
                approx_quantile(frp,[0.1,0.5,0.9]) FILTER (isfinite(frp)) AS frp_percentiles,
                avg(brightness_primary_k) FILTER (isfinite(brightness_primary_k)) AS brightness
                FROM ({selected}) GROUP BY sensor ORDER BY n DESC""", params)
            monthly = records(db, f"""SELECT substr(day::VARCHAR,1,7) AS month,sensor,daynight,
                count(*) AS n,avg(frp) FILTER (isfinite(frp)) AS mean_frp,
                count(frp) FILTER (isfinite(frp)) AS frp_n FROM ({selected})
                GROUP BY ALL ORDER BY month""", params)
            types = records(db, f"""SELECT sensor,type,count(*) AS n FROM ({selected})
                GROUP BY ALL ORDER BY n DESC LIMIT 100""", params)
            frp_bins = records(db, f"""SELECT sensor, CASE WHEN frp < 0 THEN 0 WHEN frp < 10 THEN 1
                WHEN frp < 50 THEN 2 WHEN frp < 100 THEN 3 WHEN frp < 500 THEN 4 ELSE 5 END AS bin,
                count(*) AS n FROM ({selected}) WHERE isfinite(frp) GROUP BY ALL ORDER BY bin""", params)
            return {"stats": stats, "monthly": monthly, "types": types, "frp_bins": frp_bins}
        return records(db, f"""SELECT candidate_event_id,count(*) AS detections,
            count(DISTINCT day) AS days, date_diff('second',min(observed_at),max(observed_at))/3600.0 AS hours
            FROM ({selected}) WHERE candidate_event_id IS NOT NULL
            GROUP BY ALL ORDER BY detections DESC,candidate_event_id LIMIT 100""", params)


def analytical(kind, filters):
    version = get_release(filters.country, filters.year)["version"]
    stamp = boundary_stamp(filters.country) if filters.region else None
    return analytics_cached(kind, version, stamp, filters.model_dump_json())


@app.post("/api/analytics/year-comparison")
def compare(filters: Compare):
    result = []
    for year in sorted(filters.years):
        available = releases.get((filters.country, year), {}).get("status") == "ready"
        item = {"year": year, "available": available, "days": 365 + isleap(year), "total": None, "monthly": []}
        if available:
            yearly = Filters.model_validate(filters.model_dump(exclude={"years", "start", "end"}) | {"year": year})
            rows = analytical("temporal", yearly)
            totals = {}
            for row in rows:
                key = (row["day"][5:7], row["sensor"])
                totals[key] = totals.get(key, 0) + row["n"]
            item["monthly"] = [{"month": int(month), "sensor": sensor, "n": n}
                               for (month, sensor), n in sorted(totals.items())]
            item["total"] = sum(totals.values())
        result.append(item)
    for index, item in enumerate(result):
        previous = result[index - 1] if index else None
        item["yoy_pct"] = ((item["total"] / previous["total"] - 1) * 100
                           if previous and previous["year"] == item["year"] - 1
                           and previous["total"] and item["total"] is not None else None)
    return result


@app.post("/api/analytics/regions")
def region_comparison(filters: Filters):
    version = get_release(filters.country, filters.year)["version"]
    return region_comparison_cached(version, boundary_stamp(filters.country), filters.model_dump_json())


@lru_cache(maxsize=32)
def region_comparison_cached(version, stamp, payload):
    filters = Filters.model_validate_json(payload)

    if filters.region or filters.polygon:
        raise HTTPException(
            422,
            "Region comparison requires an entire-country selection"
        )

    release = get_release(filters.country, filters.year)

    packed = packed_boundary(filters.country)

    if packed:
        entries = []

        for item in packed["features"]:
            path = (
                BOUNDARIES
                / filters.country
                / item["properties"]["file"]
            )

            geometry = read_geometry(
                path,
                path.stat().st_mtime_ns
            )

            entries.append((
                str(item["id"]),
                item["properties"]["name"],
                geometry
            ))
    else:
        entries = [
            (str(key), name, geom)
            for key, (name, geom)
            in regions(filters.country).items()
        ]

    if not entries:
        return []

    region_ids = [item[0] for item in entries]

    tree = shapely.STRtree([
        item[2] for item in entries
    ])

    def region_for_point(longitudes, latitudes):
        points = shapely.points(
            longitudes.to_numpy(),
            latitudes.to_numpy()
        )

        matches = tree.query(
            points,
            predicate="intersects"
        )

        labels = [None] * len(points)

        for point_index, region_index in zip(
            matches[0],
            matches[1]
        ):
            p = int(point_index)
            r = int(region_index)

            candidate = region_ids[r]

            # Assign boundary points to one region.
            if labels[p] is None or candidate < labels[p]:
                labels[p] = candidate

        return pa.array(labels, type=pa.string())

    with query_connection() as db:
        db.create_function(
            "region_for_point",
            region_for_point,
            ["DOUBLE", "DOUBLE"],
            "VARCHAR",
            type="arrow"
        )

        clause, params = where(db, filters)

        clause += (
            " AND " if clause else " WHERE "
        ) + (
            "longitude IS NOT NULL "
            "AND latitude IS NOT NULL"
        )

        rows = records(
            db,
            f"""
            SELECT
                region_id,
                count(*)::BIGINT AS n
            FROM (
                SELECT
                    region_for_point(
                        longitude,
                        latitude
                    ) AS region_id
                FROM {table(release)}
                {clause}
            ) matched
            GROUP BY region_id
            """,
            params
        )

    counts = {
        str(row["region_id"]): row["n"]
        for row in rows
        if row["region_id"] is not None
    }

    output = [
        {
            "id": key,
            "name": name,
            "n": counts.get(key, 0)
        }
        for key, name, _ in entries
    ]

    return sorted(
        output,
        key=lambda row: (-row["n"], row["name"])
    )


@app.post("/api/analytics/{kind}")
def analytics(kind: Literal["overview", "calendar", "temporal", "spatial", "sensors", "tracks"], filters: Filters):
    return analytical(kind, filters)


@app.post("/api/map/{layer}")
def map_layer(layer: Literal["detections", "density", "tracks"], filters: MapRequest):
    version = get_release(filters.country, filters.year)["version"]
    stamp = boundary_stamp(filters.country) if filters.region else None
    return Response(map_cached(layer, version, stamp, filters.model_dump_json()), media_type="application/json")


@lru_cache(maxsize=16)
def map_cached(layer, version, stamp, payload):
    filters = MapRequest.model_validate_json(payload)
    release = get_release(filters.country, filters.year)
    with query_connection() as db:
        if layer == "tracks":
            clause, params = where(db, filters)

            w, s, e, n = filters.bbox

            rows = records(
                db,
                f"""
                WITH visible AS (
                    SELECT
                        candidate_event_id::VARCHAR AS id,
                        approx_center_longitude AS x,
                        approx_center_latitude AS y
                    FROM {track_table(release)}
                    WHERE
                        approx_center_longitude BETWEEN ? AND ?
                        AND approx_center_latitude BETWEEN ? AND ?
                ),
                matching AS (
                    SELECT
                        o.candidate_event_id,
                        count(*)::BIGINT AS n
                    FROM {table(release)} o
                    JOIN visible v
                        ON o.candidate_event_id = v.id
                    {clause}
                    GROUP BY o.candidate_event_id
                )
                SELECT
                    v.id,
                    v.x,
                    v.y,
                    m.n
                FROM visible v
                JOIN matching m
                    ON m.candidate_event_id = v.id
                ORDER BY m.n DESC, v.id
                LIMIT ?
                """,
                [w, e, s, n] + params + [filters.limit + 1]
            )
        elif layer == "density" or filters.zoom < 8:
            step = 2 if filters.zoom < 5 else 0.5 if filters.zoom < 8 else 0.25
            use_grid = not (filters.region or filters.polygon) and step >= 0.25
            if use_grid:
                clause, params = where(db, filters)
                w, s, e, n = filters.bbox
                rows = records(db, f"""SELECT floor(x/{step})*{step}+{step}/2 AS x,
                   floor(y/{step})*{step}+{step}/2 AS y,sum(n)::BIGINT AS n
                   FROM {table(release, 'grid')}{clause}{' AND' if clause else ' WHERE'}
                   x >= ? AND x < ? AND y >= ? AND y < ? GROUP BY ALL ORDER BY n DESC,x,y LIMIT ?""",
                   params + [w-0.25, e, s-0.25, n, filters.limit + 1])
            else:
                clause, params = where(db, filters, bbox=filters.bbox)
                rows = records(db, f"""SELECT floor(longitude/{step})*{step}+{step}/2 AS x,
                    floor(latitude/{step})*{step}+{step}/2 AS y,count(*) AS n FROM {table(release)}
                    {clause} GROUP BY ALL ORDER BY n DESC,x,y LIMIT ?""", params + [filters.limit + 1])
        else:
            clause, params = where(db, filters, bbox=filters.bbox)
            rows = records(db, f"""SELECT detection_id AS id,longitude AS x,latitude AS y,sensor
                FROM {table(release)}{clause} LIMIT ?""", params + [filters.limit + 1])
    payload = {"rows": rows[:filters.limit], "truncated": len(rows) > filters.limit,
               "mode": "density" if layer == "density" or (layer == "detections" and filters.zoom < 8) else layer}
    return json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()


@app.get("/api/detections/{id:path}")
def detection(id: str, country: str, year: int):
    release = get_release(country, year)
    with query_connection() as db:
        rows = records(db, f"SELECT * FROM {table(release)} WHERE detection_id=? LIMIT 1", [id])
    if not rows:
        raise HTTPException(404, "Detection unavailable")
    return rows[0]


@app.get("/api/tracks/{id:path}")
def track(id: str, country: str, year: int, offset: int = Query(0, ge=0, le=1000000)):
    release = get_release(country, year)
    with query_connection() as db:
        meta = records(db, f"""SELECT * FROM {track_table(release)}
                       WHERE candidate_event_id::VARCHAR=? LIMIT 1""", [id])
        if not meta:
            raise HTTPException(404, "Candidate track unavailable")
        members = records(db, f"""SELECT detection_id,latitude,longitude,sensor,observed_at
            FROM {table(release)} WHERE candidate_event_id=?
            ORDER BY observed_at,detection_id LIMIT 101 OFFSET ?""", [id, offset])
        sensors = records(db, f"""SELECT sensor,count(*) AS n FROM {table(release)}
                           WHERE candidate_event_id=? GROUP BY sensor""", [id])
    return {"metadata": meta[0], "members": members[:100], "sensors": sensors,
            "next": offset + 100 if len(members) > 100 else None}
