
"""Build scientific evidence for IGNIS AI Insights.

Uses existing validated analytical endpoints internally.
No LLM calls and no raw detection rows are sent to Groq.
"""

from collections import defaultdict
import math
from typing import Any

from .catalog import YEARS


COUNTRY_NAMES = {
    "AU": "Australia",
    "BR": "Brazil",
    "ID": "Indonesia",
    "ZA": "South Africa",
}


def safe_number(value: Any, digits: int = 2):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None

        if isinstance(value, int):
            return value

        return round(value, digits)

    return value


def build_ai_evidence(filters) -> dict[str, Any]:
    """Collect and summarize analytics for one selected scope."""

    # Imported here to avoid circular imports when main.py
    # imports this module for the future API endpoint.
    from . import main

    release = main.get_release(
        filters.country,
        filters.year,
    )

    # Reuse the same analytical engine as the dashboard.
    overview = main.analytical("overview", filters)
    temporal = main.analytical("temporal", filters)
    spatial = main.analytical("spatial", filters)
    sensors = main.analytical("sensors", filters)
    tracks = main.analytical("tracks", filters)

    # This comparison intentionally uses entire calendar years.
    comparison_request = main.Compare.model_validate({
        **filters.model_dump(mode="json"),
        "years": list(YEARS),
    })

    comparison = main.compare(comparison_request)

    metrics = overview["metrics"]

    # Scientific accounting validation.
    required = (
        "detections",
        "linked",
        "unresolved",
        "outside_scope",
    )

    if any(metrics.get(key) is None for key in required):
        raise ValueError(
            "Tracking metrics are incomplete. "
            "Reprepare the release before generating AI insights."
        )

    total = int(metrics["detections"])
    linked = int(metrics["linked"])
    unresolved = int(metrics["unresolved"])
    outside = int(metrics["outside_scope"])

    if linked + unresolved + outside != total:
        raise ValueError(
            "Tracking category totals do not reconcile "
            "with the total detection count."
        )

    # Temporal aggregation.
    daily_counts = defaultdict(int)
    monthly_counts = {
        f"{month:02d}": 0
        for month in range(1, 13)
    }

    daynight_counts = defaultdict(int)

    for row in temporal:
        day = row["day"]
        count = int(row["n"])

        daily_counts[day] += count
        monthly_counts[day[5:7]] += count

        flag = row.get("daynight") or "Unknown"
        daynight_counts[flag] += count

    highest_days = sorted(
        daily_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )[:7]

    highest_months = sorted(
        monthly_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )[:4]

    # Sensor measurements.
    sensor_stats = []

    for row in sensors["stats"]:
        sensor_stats.append({
            "sensor": row["sensor"],
            "detections": int(row["n"]),
            "mean_frp_mw": safe_number(
                row.get("mean_frp")
            ),
            "frp_percentiles_mw": [
                safe_number(value)
                for value in (
                    row.get("frp_percentiles") or []
                )
            ],
            "mean_brightness_k": safe_number(
                row.get("brightness")
            ),
        })

    sensor_types = [
        {
            "sensor": row["sensor"],
            "source_type": row.get("type"),
            "detections": int(row["n"]),
        }
        for row in sensors["types"]
    ]

    # Detailed monthly FRP comparisons.
    monthly_frp = defaultdict(
        lambda: {"weighted_sum": 0.0, "samples": 0}
    )

    for row in sensors["monthly"]:
        sample_count = int(row.get("frp_n") or 0)
        mean = row.get("mean_frp")

        if sample_count and mean is not None:
            key = (row["month"], row["sensor"])
            monthly_frp[key]["weighted_sum"] += (
                float(mean) * sample_count
            )
            monthly_frp[key]["samples"] += sample_count

    frp_trends = []

    for (month, sensor), values in sorted(monthly_frp.items()):
        count = values["samples"]

        if count:
            frp_trends.append({
                "month": month,
                "sensor": sensor,
                "mean_frp_mw": safe_number(
                    values["weighted_sum"] / count
                ),
                "valid_frp_observations": count,
            })

    # Spatial grids. Coordinates are 0.25-degree cell centers.
    top_cells = []

    for row in spatial["cells"][:8]:
        top_cells.append({
            "longitude": safe_number(
                float(row["x"]) + 0.125,
                3,
            ),
            "latitude": safe_number(
                float(row["y"]) + 0.125,
                3,
            ),
            "detections": int(row["n"]),
        })

    # The tracks API returns at most 100 ranked tracks.
    # Do not treat this subset as all candidate tracks.
    top_tracks = []

    for row in tracks[:8]:
        top_tracks.append({
            "id": row["candidate_event_id"],
            "matching_detections": int(
                row["detections"]
            ),
            "observed_days": int(row["days"]),
            "observation_span_hours": safe_number(
                row.get("hours")
            ),
        })

    track_day_distribution = {
        "1_day": sum(r["days"] == 1 for r in tracks),
        "2_days": sum(r["days"] == 2 for r in tracks),
        "3_days": sum(r["days"] == 3 for r in tracks),
        "4_to_7_days": sum(
            4 <= r["days"] <= 7
            for r in tracks
        ),
        "8_plus_days": sum(
            r["days"] >= 8
            for r in tracks
        ),
    }

    # Year-over-year comparison.
    annual_comparison = []

    for row in comparison:
        annual_comparison.append({
            "year": row["year"],
            "available": row["available"],
            "detections": row["total"],
            "detections_per_calendar_day": (
                safe_number(
                    row["total"] / row["days"]
                )
                if row["total"] is not None
                else None
            ),
            "year_over_year_change_pct": safe_number(
                row.get("yoy_pct")
            ),
        })

    # Release-wide quality metadata.
    report_names = sorted(
        str(name)
        for name in release.get("reports", {})
    )

    quality = {
        "release_version": str(
            release.get("version", "unknown")
        ),
        "release_status": release["status"],
        "calendar_from_validated_archive": bool(
            release.get("calendar_from_archive", False)
        ),
        "available_validation_reports": report_names[:12],
        "validation_report_count": len(report_names),
    }

    # Facts have stable IDs for AI evidence citations.
    facts = {
        "overview.activity": {
            "thermal_detections": total,
            "candidate_tracks": metrics.get("tracks"),
            "active_observation_days": metrics.get(
                "active_days"
            ),
            "daynight_detection_counts": dict(
                daynight_counts
            ),
        },

        "overview.tracking": {
            "linked_detections": linked,
            "unresolved_eligible_detections": unresolved,
            "outside_tracking_scope": outside,
            "category_counts_reconciled": True,
        },

        "temporal.monthly": monthly_counts,

        "temporal.highest_days": [
            {"day": day, "detections": n}
            for day, n in highest_days
        ],

        "temporal.highest_months": [
            {"month": month, "detections": n}
            for month, n in highest_months
        ],

        "sensors.measurements": sensor_stats,

        "sensors.source_types": sensor_types,

        "sensors.monthly_frp": frp_trends,

        "spatial.highest_cells": top_cells,

        "tracks.top_ranked": {
            "returned_tracks": len(tracks),
            "maximum_returned": 100,
            "ranking": "Matching detection count",
            "tracks": top_tracks,
        },

        "tracks.observed_days_sample": {
            "sample_size": len(tracks),
            "distribution": track_day_distribution,
            "warning": (
                "Distribution covers only returned "
                "top-ranked tracks, not all tracks."
            ),
        },

        "comparison.annual": annual_comparison,

        "quality.release": quality,
    }

    scope = {
        "country_code": filters.country,
        "country_name": COUNTRY_NAMES[filters.country],
        "selected_year": filters.year,
        "sensor": filters.sensor or "All sensors",
        "start_utc": (
            filters.start.isoformat()
            if filters.start else None
        ),
        "end_utc": (
            filters.end.isoformat()
            if filters.end else None
        ),
        "geographic_selection": (
            "Administrative region"
            if filters.region
            else "Custom polygon"
            if filters.polygon
            else "Entire country"
        ),
        "region_id": filters.region,
        "polygon_vertices": (
            len(filters.polygon)
            if filters.polygon else 0
        ),
        "comparison_years": list(YEARS),
        "comparison_date_scope": (
            "Full calendar years. The selected date "
            "range is not applied to year comparisons."
        ),
    }

    sections = {
        "overview": [
            "overview.activity",
            "overview.tracking",
        ],
        "temporal": [
            "temporal.monthly",
            "temporal.highest_days",
            "temporal.highest_months",
        ],
        "sensors": [
            "sensors.measurements",
            "sensors.source_types",
            "sensors.monthly_frp",
        ],
        "spatial": [
            "spatial.highest_cells",
        ],
        "candidate_tracks": [
            "overview.tracking",
            "tracks.top_ranked",
            "tracks.observed_days_sample",
        ],
        "year_comparison": [
            "comparison.annual",
        ],
        "data_quality": [
            "quality.release",
        ],
    }

    limitations = [
        (
            "NASA FIRMS thermal detections are satellite "
            "observations, not confirmed independent fires."
        ),
        (
            "Candidate tracks are algorithmic and have "
            "not been independently validated as fires."
        ),
        (
            "Observation density is not burned area "
            "or a verified fire perimeter."
        ),
        (
            "MODIS and VIIRS differ in spatial resolution, "
            "overpass timing and detection characteristics."
        ),
        (
            "Raw sensor counts are not normalized by "
            "satellite observation opportunities."
        ),
        (
            "The displayed top-track distribution "
            "represents at most 100 ranked tracks."
        ),
        (
            "Year comparisons use full calendar years "
            "with shared sensor and geographic filters."
        ),
        (
            "Historical activity alone does not establish "
            "future wildfire risk or emergency conditions."
        ),
        (
            "Missing satellite observations cannot be "
            "distinguished from zero detections by "
            "the calendar counts alone."
        ),
        (
            "Available validation reports document "
            "engineering checks and do not constitute "
            "independent wildfire ground-truth validation."
        ),
    ]

    return {
        "scope": scope,
        "facts": facts,
        "sections": sections,
        "limitations": limitations,
    }
