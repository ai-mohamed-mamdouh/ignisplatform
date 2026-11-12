# Wildfire Intelligence Platform

Satellite Thermal Activity & Historical Geospatial Analytics

A public historical explorer for Australia, Brazil, Indonesia and South Africa, 2020–2025. The desktop workspace places the MapLibre map on the left and the analytics panel on the right. The production data directory is empty on delivery.

## Start with Docker

Place each release in `data/releases/<Country>/<Year>/FINAL_EXPORT/`. Use the exact country directories `Australia`, `Brazil`, `Indonesia`, and `South_Africa`.

Every release directory requires these files:

- `01_FIRE_DETECTIONS.parquet`
- `02_FIRE_EVENTS.parquet`
- `03_DETECTION_EVENT_RELATIONSHIPS.parquet`
- `04_FIRE_ANALYTICS_FEATURES.zip`
- `05_VALIDATION_REPORT.zip`

Keep all releases separate. Partial installation is supported. Missing years appear as unavailable. A present but incomplete release is listed as invalid.

```sh
docker compose up --build
```

Open [http://localhost:3000](http://localhost:3000). The application displays preparation status while discovering and processing releases. To pick up newly copied releases, run `docker compose restart backend`. The host data mount is read-only. Generated Parquet and extracted archives live under `runtime/`.

## Run locally

In the first terminal:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

In the second terminal:

```sh
cd frontend
npm ci
npm run dev
```

To validate and prepare releases without starting the server, run `python -m app.cli prepare-data` from `backend/`. Stop the running backend before invoking this command against the same runtime directory. Interactive API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs) for local development.

## Query behavior

- **Scope.** Detection and candidate IDs are qualified by country and year in requests. Dates use UTC and include both endpoints. Selecting a calendar day changes the date filter. The calendar itself always shows the full selected year. Historical comparisons use full years with the same sensor and geographic selection.
- **Map.** Zoom below 8 renders aggregated density. At zoom 8 and above, the detections layer sends viewport points. Responses default to 4,000 rows and permit up to 6,000. A truncation indicator appears when more rows match. Country-scale density bins can include observations in a grid cell intersecting the viewport edge. User-selected geographic filters use exact point membership, including polygon boundaries. Custom polygons that cross the antimeridian are rejected.
- **Tracks.** A candidate is included if any linked detection matches the current scope. The ranked table shows scoped counts and observed spans. Click a candidate for paginated, release-wide members and sensor counts. The map shows approximate release-level centers and can highlight the members on the current detail page.
- **Sensor metrics.** Counts describe observations. MODIS and VIIRS have different nominal resolutions, revisit schedules and confidence conventions. The app groups common MODIS, VIIRS S-NPP and VIIRS NOAA-20 naming variants. Unknown source labels remain visible in unfiltered results. FRP percentiles are approximate and use finite FRP values.
- **Science.** These are historical satellite thermal anomalies and algorithmically linked candidate tracks. Observation density is a count per geographic cell. The application does not establish individual wildfire incidents, burned areas, fire spread, wildfire risk or current emergency conditions. Source context is available from [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/map/).

## Data validation and boundaries

The loader checks required products and core Parquet columns, opens archive entries and checks for required analytical members, and checks detection identity and unambiguous track membership. Optional measurement columns are exposed as unavailable when missing. The quality tab shows original row counts, normalized coverage, and the engineering reports as previews or downloads. The actual archive's validation conclusions are preserved in those reports.

Each immutable cache version uses country, year, source file names, byte sizes, modification times and a preparation schema revision. Content changed while preserving all sizes and modification times requires removing the affected runtime version before restarting. Old generated versions can be removed when the backend is stopped. DuckDB uses selected release paths, projected columns and row-group filters. It uses small derived Parquet summaries for overview, dates and density, and reconciles the supplied daily calendar against detection totals before serving it. The seven supplied feature files are preserved and indexed. Additional feature-table adapters require the real release schemas.

ADM1 geometry for all four countries is bundled from geoBoundaries gbOpen. See [boundary attribution](docs/boundary-attribution.md). Each country has a `*.source.json` with source, vintage, URL and license metadata. Map outlines are simplified for rendering. Regional membership uses the full-resolution geometry after validity repair where needed. Region comparisons count boundary points in each covering region. Administrative boundaries are a common cross-year reference, and may differ from the legal boundaries applicable in a particular observation year. The offline country basemap uses Natural Earth via world-atlas. Set `VITE_MAP_STYLE` at frontend build time to use a custom MapLibre style.

To refresh geography, run `python -m app.cli fetch-boundaries` with network access. For a custom country catalog, install a FeatureCollection at `assets/boundaries/<ISO2>.geojson` and remove the corresponding packed directory. Feature IDs or `shapeID` must be stable and unique. Use `shapeName` for display names.

## Troubleshooting and tuning

| Symptom | Check |
| --- | --- |
| No datasets installed | Check case-sensitive paths and make sure files are inside `FINAL_EXPORT`. Restart the backend after copying. |
| Release invalid | Read the specific issue in the analytics panel or run `prepare-data` for a JSON inventory. |
| Preparing for a long time | Inspect `docker compose logs backend`. Keep the project and `runtime/` on WSL's Linux filesystem for faster local disk I/O. |
| Map unavailable | Chromium or Firefox needs WebGL and hardware acceleration. The default basemap and packaged administrative geometry work offline. |
| Request fails under load | Reduce query concurrency, give DuckDB a larger disk spill location through the runtime mount, or use narrower filters. |
| Port 3000 is occupied | Set `PORT` in the root `.env` and recreate the frontend service. |

`DUCKDB_MEMORY` defaults to 256 MB per active connection, with one DuckDB thread per connection. `QUERY_CONCURRENCY` defaults to two. DuckDB can spill to `runtime/spill/`. Process memory also includes Python, caches, ingestion, native code and response buffers. For public deployment use a TLS reverse proxy and set rate and request limits appropriate to available resources. The included Nginx configuration caps request bodies at 32 KB.

## Verify

```sh
cd backend
python -m pip install -r requirements-dev.txt
python -m unittest discover -v
python -m tests.benchmark --rows 1000002
cd ../frontend
npm ci
npm run build
cd ../backend
CHROMIUM_PATH=/usr/bin/chromium python -m tests.browser_check
```

See [performance notes](docs/performance.md) for benchmark scope and results. For release acceptance, install Australia 2022 and check its API totals against 1,791,533 detections, 160,278 MODIS, 826,535 VIIRS JPSS-1, 804,720 VIIRS SNPP, 3,326 source candidate tracks and 1,791,533 relationship rows. The overview candidate count is based on linked detections and the quality tab exposes the source event count independently.
