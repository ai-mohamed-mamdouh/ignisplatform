"""Synthetic releases generated exclusively in temporary test directories."""
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile

import pyarrow as pa
import pyarrow.parquet as pq

from app.catalog import FEATURES, PRODUCTS


def release(data, country="Australia", year=2024, copies=1):
    folder = data / "releases" / country / str(year) / "FINAL_EXPORT"
    folder.mkdir(parents=True)
    first = datetime(year, 2, 29 if year % 4 == 0 else 28, 23, tzinfo=timezone.utc)
    second = datetime(year, 3, 1, 2, tzinfo=timezone.utc)
    template = [
        {"source_dataset": "MODIS", "longitude": 140.1, "latitude": -30.1,
         "acquisition_datetime_utc": first, "frp": 5.0, "daynight": "D"},
        {"source_dataset": "VIIRS_NOAA20", "longitude": 140.8, "latitude": -30.1,
         "acquisition_datetime_utc": second, "frp": 15.0, "daynight": "N"},
        {"source_dataset": "VIIRS_SNPP", "longitude": 141.1, "latitude": -30.1,
         "acquisition_datetime_utc": second, "frp": None, "daynight": "D"},
    ]
    schema = pa.Table.from_pylist([row | {"detection_id": str(i)} for i, row in enumerate(template)]).schema
    relationship_schema = pa.schema([("detection_id", pa.string()), ("candidate_event_id", pa.string())])
    with pq.ParquetWriter(folder / PRODUCTS[0], schema) as detections, pq.ParquetWriter(
            folder / PRODUCTS[2], relationship_schema) as relationships:
        for start in range(0, copies, 10000):
            stop = min(start + 10000, copies)
            ids = [f"d{i}-{j}" for i in range(start, stop) for j in range(3)]
            detections.write_table(pa.Table.from_pylist([
                row | {"detection_id": ids[(i-start)*3+j]} for i in range(start, stop)
                for j, row in enumerate(template)], schema=schema))
            relationships.write_table(pa.table({
                "detection_id": ids, "candidate_event_id": ["track-1", "track-1", None] * (stop-start),
            }, schema=relationship_schema))
    pq.write_table(pa.table({"candidate_event_id": ["track-1"], "approx_center_longitude": [140.4],
                             "approx_center_latitude": [-30.1], "algorithm_version": ["test"]}), folder / PRODUCTS[1])
    with ZipFile(folder / PRODUCTS[3], "w") as archive:
        for feature in FEATURES:
            data = BytesIO()
            summary = pa.table({"day_utc": [first.date(), second.date()],
                                "detection_count": [copies, 2 * copies]})
            pq.write_table(summary if feature == FEATURES[0] else pa.table({"test_fixture": [1]}), data)
            archive.writestr(feature, data.getvalue())
    with ZipFile(folder / PRODUCTS[4], "w") as archive:
        archive.writestr("validation.json", '{"status":"synthetic fixture"}')
    return folder
