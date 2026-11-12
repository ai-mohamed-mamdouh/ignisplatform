"""Discover immutable releases and publish derived assets atomically."""
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

import duckdb
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.getenv("DATA_DIR", ROOT / "data"))
RUNTIME = Path(os.getenv("RUNTIME_DIR", ROOT / "runtime"))
BOUNDARIES = Path(os.getenv("BOUNDARY_DIR", ROOT / "assets/boundaries"))
COUNTRIES = {"AU": ("Australia", "AUS"), "BR": ("Brazil", "BRA"),
             "ID": ("Indonesia", "IDN"), "ZA": ("South_Africa", "ZAF")}
YEARS = range(2020, 2026)
PRODUCTS = ("01_FIRE_DETECTIONS.parquet", "02_FIRE_EVENTS.parquet",
            "03_DETECTION_EVENT_RELATIONSHIPS.parquet",
            "04_FIRE_ANALYTICS_FEATURES.zip", "05_VALIDATION_REPORT.zip")
FEATURES = tuple(name + ".parquet" for name in (
    "daily_activity_calendar", "daily_activity_by_sensor", "monthly_activity",
    "monthly_activity_by_sensor", "monthly_spatial_grid_025deg",
    "candidate_event_features", "candidate_event_sensor_features"))
REQUIRED = (
    {"detection_id", "source_dataset", "latitude", "longitude", "acquisition_datetime_utc"},
    {"candidate_event_id", "approx_center_latitude", "approx_center_longitude"},
    {"detection_id", "candidate_event_id"},
)
SENSOR = """CASE
 WHEN regexp_matches(lower(source_dataset::VARCHAR), 'modis|^mcd') THEN 'MODIS'
 WHEN regexp_matches(lower(source_dataset::VARCHAR), 'jpss.?1|noaa.?20|vnp?j1|vj114|(^|[^a-z])n20') THEN 'VIIRS JPSS-1'
 WHEN regexp_matches(lower(source_dataset::VARCHAR), 'snpp|s.?npp|vnp14|(^|[^a-z])npp') THEN 'VIIRS SNPP'
 ELSE coalesce(source_dataset::VARCHAR, 'Unknown') END"""
OPTIONAL = {"frp": "DOUBLE", "daynight": "VARCHAR", "type": "VARCHAR",
            "brightness_primary_k": "DOUBLE", "brightness_secondary_k": "DOUBLE",
            "confidence_raw": "VARCHAR", "tracking_eligible": "BOOLEAN",
            "ingestion_status": "VARCHAR", "scan": "DOUBLE", "track": "DOUBLE"}

METRICS = """count(*) AS detections, count(DISTINCT candidate_event_id) AS tracks,
    count(DISTINCT day) AS active_days, count(candidate_event_id) AS linked,
    count(*)-count(candidate_event_id) AS unresolved,
    count(*) FILTER (sensor='MODIS') AS modis,
    count(*) FILTER (sensor='VIIRS SNPP') AS snpp,
    count(*) FILTER (sensor='VIIRS JPSS-1') AS jpss1"""


@contextmanager
def connect():
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(config={"threads": "1", "memory_limit": os.getenv("DUCKDB_MEMORY", "256MB"),
                                "temp_directory": str(RUNTIME / "spill"),
                                "preserve_insertion_order": "false"}) as db:
        db.execute("SET TimeZone='UTC'")
        yield db


def sql_path(path):
    return "'" + str(path).replace("'", "''") + "'"


def unpack(path, target, expected=()):
    with ZipFile(path) as archive:
        entries = [item for item in archive.infolist() if not item.is_dir()]
        if sum(item.file_size for item in entries) > 4 * 1024**3 or len(entries) > 512:
            raise ValueError(f"Archive exceeds extraction budget: {path.name}")
        files = {}
        for item in entries:
            name = PurePosixPath(item.filename).name
            if name in files or name in {".", ".."} or "\\" in name:
                raise ValueError("Ambiguous archive member name")
            files[name] = item
        if not entries or set(expected) - files.keys():
            raise ValueError(f"Missing archive contents in {path.name}")
        for name, item in files.items():
            with archive.open(item) as source:
                if expected and name not in expected:
                    while source.read(1024 * 1024):
                        pass
                    continue
                with (target / name).open("wb") as dest:
                    shutil.copyfileobj(source, dest)
            if expected:
                pq.ParquetFile(target / name).close()
        return {name: item.file_size for name, item in files.items()}


def verified_calendar(db, stage):
    """Use delivered calendar totals when its documented fields reconcile."""
    path = stage / "features" / FEATURES[0]
    with pq.ParquetFile(path) as parquet:
        columns = set(parquet.schema_arrow.names)
    day = next((name for name in ("day_utc", "date_utc", "day", "date") if name in columns), None)
    count = next((name for name in ("detection_count", "total_detections", "detections", "n") if name in columns), None)
    if day is None or count is None:
        return False
    supplied = f"""SELECT TRY_CAST("{day}" AS DATE) AS day,
                  TRY_CAST("{count}" AS BIGINT) AS n FROM read_parquet({sql_path(path)})"""
    derived = f"""SELECT day,sum(n)::BIGINT AS n FROM read_parquet(
                  {sql_path(stage / 'daily.parquet')}) GROUP BY day"""
    mismatch = db.execute(f"""WITH supplied AS ({supplied}), derived AS ({derived})
        SELECT EXISTS (
            SELECT 1 FROM supplied FULL JOIN derived USING (day)
            WHERE supplied.day IS NULL OR supplied.n IS NULL OR supplied.n <> coalesce(derived.n,0)
               OR (supplied.day IS NULL AND derived.day IS NOT NULL))
        OR EXISTS (SELECT 1 FROM supplied GROUP BY day HAVING count(*) <> 1)""").fetchone()[0]
    if mismatch:
        return False
    db.execute(f"COPY ({supplied}) TO {sql_path(stage / 'verified_calendar.parquet')} (FORMAT PARQUET)")
    return True


def prepare_release(code, year, folder):
    paths = [folder / name for name in PRODUCTS]
    stats = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in paths]
    version = hashlib.sha256(repr((8, code, year, stats)).encode()).hexdigest()[:24]
    target = RUNTIME / version
    if not (target / "metadata.json").is_file():
        schemas = []
        rows = []
        for path, required in zip(paths, REQUIRED):
            with pq.ParquetFile(path) as parquet:
                columns = set(parquet.schema_arrow.names)
                missing = required - columns
                if missing:
                    raise ValueError(f"{path.name} missing {', '.join(sorted(missing))}")
                schemas.append(columns)
                rows.append(parquet.metadata.num_rows)
        with tempfile.TemporaryDirectory(dir=RUNTIME) as tmp:
            stage = Path(tmp) / version
            for name in ("features", "reports"):
                (stage / name).mkdir(parents=True)
            features = unpack(paths[3], stage / "features", FEATURES)
            reports = unpack(paths[4], stage / "reports")
            optional = ", ".join(
                f'TRY_CAST("{key}" AS {kind}) AS "{key}"' if key in schemas[0]
                else f'NULL::{kind} AS "{key}"' for key, kind in OPTIONAL.items())
            with connect() as db:
                db.execute(f"""CREATE TEMP VIEW observations AS SELECT
                    detection_id::VARCHAR AS detection_id, source_dataset::VARCHAR AS source_dataset,
                    {SENSOR} AS sensor, latitude::DOUBLE AS latitude, longitude::DOUBLE AS longitude,
                    acquisition_datetime_utc::TIMESTAMPTZ AS observed_at, {optional}
                    FROM read_parquet({sql_path(paths[0])})""")
                db.execute(f"""CREATE TEMP VIEW membership AS SELECT DISTINCT
                    detection_id::VARCHAR AS detection_id, candidate_event_id::VARCHAR AS candidate_event_id
                    FROM read_parquet({sql_path(paths[2])}) WHERE candidate_event_id IS NOT NULL""")
                if db.execute("""SELECT EXISTS (SELECT 1 FROM membership GROUP BY detection_id
                               HAVING count(*) > 1)""").fetchone()[0]:
                    raise ValueError("A detection is assigned to multiple candidate tracks")
                db.execute(f"""COPY (SELECT o.*, observed_at::DATE AS day, m.candidate_event_id
                    FROM observations o LEFT JOIN membership m USING (detection_id)
                    ORDER BY floor(longitude), floor(latitude), observed_at)
                    TO {sql_path(stage / 'observations.parquet')} (FORMAT PARQUET, ROW_GROUP_SIZE 32768)""")
                if db.execute("""SELECT EXISTS (SELECT 1 FROM observations GROUP BY detection_id
                               HAVING detection_id IS NULL OR count(*) > 1)""").fetchone()[0]:
                    raise ValueError("Detection IDs must be non-null and unique within a release")
                obs = sql_path(stage / "observations.parquet")
                for name, groups in {
                    "daily": "day,sensor,daynight",
                    "grid": "day,sensor,floor(longitude*4)/4 AS x,floor(latitude*4)/4 AS y",
                }.items():
                    db.execute(f"""COPY (SELECT {groups}, count(*) AS n FROM read_parquet({obs})
                        WHERE day IS NOT NULL AND {'TRUE' if name == 'daily' else 'longitude BETWEEN -180 AND 180 AND latitude BETWEEN -90 AND 90'}
                        GROUP BY ALL ORDER BY day)
                        TO {sql_path(stage / (name + '.parquet'))} (FORMAT PARQUET)""")
                db.execute(f"""COPY (SELECT sensor,{METRICS} FROM read_parquet({obs})
                    GROUP BY GROUPING SETS ((sensor),()))
                    TO {sql_path(stage / 'overview.parquet')} (FORMAT PARQUET)""")
                archived_calendar = verified_calendar(db, stage)
            metadata = {"calendar_from_archive": archived_calendar, "country": code, "year": year, "version": version,
                        "rows": dict(zip(PRODUCTS, rows)), "features": features, "reports": reports,
                        "schemas": {name: sorted(cols) for name, cols in zip(PRODUCTS, schemas)}}
            (stage / "metadata.json").write_text(json.dumps(metadata))
            stage.rename(target)
    return {**json.loads((target / "metadata.json").read_text()), "status": "ready",
            "cache": target, "source": folder}


def prepare(on_update=lambda *args: None):
    RUNTIME.mkdir(parents=True, exist_ok=True)
    results = {}
    for code, (country, _) in COUNTRIES.items():
        for year in YEARS:
            folder = DATA / "releases" / country / str(year) / "FINAL_EXPORT"
            if not folder.is_dir():
                continue
            on_update(results.copy(), f"Preparing {country.replace('_', ' ')} {year}")
            try:
                release = prepare_release(code, year, folder)
            except (OSError, RuntimeError, ValueError, BadZipFile, duckdb.Error) as error:
                release = {"country": code, "year": year, "status": "invalid", "error": str(error)}
            results[code, year] = release
    on_update(results.copy(), None)
    return results


def public(release):
    return {key: value for key, value in release.items() if key not in {"cache", "source", "schemas"}}
