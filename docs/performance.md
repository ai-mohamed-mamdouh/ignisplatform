# Performance verification

The benchmark uses temporary synthetic Parquet. The largest release contains 1,000,002 detections, three coordinate locations, two observation dates and one candidate track. Five other releases have three detections each. The workload measures API handling, query execution, caching and response serialization through FastAPI TestClient. It excludes public network latency, TLS and a full real-data ingestion run.

| Operation | First request | Median of four repeated requests |
| --- | ---: | ---: |
| Overview | 47 ms | 9 ms |
| Annual calendar | 46 ms | 14 ms |
| Six-year comparison | 228 ms | 11 ms |
| Sensor analytics | 434 ms | 6 ms |
| Polygon-filtered overview | 670 ms | 9 ms |
| Point viewport | 87 ms | 23 ms |
| Density viewport | 30 ms | 5 ms |

Preparation took 4.97 seconds. Peak benchmark-process RSS was 457.1 MiB including fixture creation, preparation and query execution. The point response was capped at 4,000 rows, flagged as truncated and measured 218,945 bytes after decompression. Tests also sent three concurrent analytical requests and verified the results.

Local targets for a representative real release are under 2 seconds to a populated dashboard after preparation, under 500 ms for cold calendar and ordinary viewport queries, under 2 seconds for first-run polygon and comparison queries, and under 100 ms for repeated cached requests. These targets remain to be measured against the actual files and deployment hardware. The synthetic data has much lower geographic, temporal and candidate cardinality than the intended production dataset.

Reproduce with `python -m tests.benchmark --rows 1000002` from `backend/`. Run `python -m tests.browser_check` after building the frontend to measure browser timings. The initial JavaScript bundle includes the MapLibre renderer, around 377 KB gzip in the tested build. The ECharts analytics module loads separately when a release is available.

Headless Chromium verified the production bundle at 1440 × 900 and checked the stacked layout at 390 × 844. In one local run, the empty state appeared after 467 ms, the overview after 1,416 ms during startup with three tiny fixture releases, and the calendar appeared 615 ms after selecting Temporal. The check covered country, year, sensor and region changes, panel sizing, calendar selection and reset, comparison year selection, candidate inspection, and rectangle and polygon drawing.

Compose syntax and the read-only data mount were checked. The production bundle was served through Vite preview with its API proxy for this verification. Docker Compose startup remains to be exercised on a host with Docker.
