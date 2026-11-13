
"""IGNIS standalone scientific HTML report.

Uses real IGNIS analytics and embeds vector SVG charts.
The exported HTML requires no external assets or CDN.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
import json
import math


COLORS = (
    "#f28b50",
    "#42c9b4",
    "#7da9f6",
    "#c79af2",
    "#e2c56a",
    "#ed86aa",
)

SENSOR_COLORS = {
    "MODIS": COLORS[0],
    "VIIRS JPSS-1": COLORS[1],
    "VIIRS SNPP": COLORS[2],
}

COUNTRIES = {
    "AU": "Australia",
    "BR": "Brazil",
    "ID": "Indonesia",
    "ZA": "South Africa",
}

MONTHS = (
    "Jan", "Feb", "Mar", "Apr",
    "May", "Jun", "Jul", "Aug",
    "Sep", "Oct", "Nov", "Dec",
)


def esc(value):
    return escape(
        str(value if value is not None else "Unavailable"),
        quote=True,
    )


def number(value, digits=0):
    if value is None:
        return "Unavailable"

    try:
        value = float(value)

        if not math.isfinite(value):
            return "Unavailable"

        return f"{value:,.{digits}f}"

    except (ValueError, TypeError):
        return str(value)


def paragraphs(value):
    text = str(value or "Unavailable")

    return "".join(
        "<p>"
        + esc(part).replace("\n", "<br>")
        + "</p>"
        for part in text.split("\n\n")
    )


def card(title, content, note=None):
    result = (
        '<article class="card">'
        f"<h3>{esc(title)}</h3>"
        f"{content}"
    )

    if note:
        result += f'<p class="caption">{esc(note)}</p>'

    return result + "</article>"


def make_table(columns, rows, limit=100):
    if not rows:
        return '<p class="muted">No data available.</p>'

    header = "".join(
        f"<th>{esc(label)}</th>"
        for label, _ in columns
    )

    body = ""

    for row in rows[:limit]:
        cells = "".join(
            f"<td>{esc(row.get(key))}</td>"
            for _, key in columns
        )

        body += f"<tr>{cells}</tr>"

    return (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table></div>"
    )


def bar_chart(items, limit=20):
    """Generate an inline horizontal SVG chart."""

    valid = []

    for item in items[:limit]:
        label, value = item[:2]

        if value is None:
            continue

        value = float(value)

        if not math.isfinite(value):
            continue

        color = item[2] if len(item) > 2 else COLORS[0]

        valid.append((str(label), value, color))

    if not valid:
        return '<p class="muted">No chart data.</p>'

    width = 920
    left = 195
    plot_width = 630
    row_height = 34
    height = 28 + len(valid) * row_height

    maximum = max(
        1,
        max(value for _, value, _ in valid),
    )

    elements = []

    for index, (label, value, color) in enumerate(valid):
        y = 16 + index * row_height
        bar_width = max(0, value) / maximum * plot_width

        short_label = (
            label[:29] + "…"
            if len(label) > 29
            else label
        )

        elements.append(
            f'<text x="{left-10}" y="{y+15}" '
            'text-anchor="end" class="svg-label">'
            f"{esc(short_label)}</text>"
        )

        elements.append(
            f'<rect x="{left}" y="{y+2}" '
            f'width="{plot_width}" height="19" '
            'rx="5" fill="#edf1f6"/>'
        )

        elements.append(
            f'<rect x="{left}" y="{y+2}" '
            f'width="{bar_width:.2f}" height="19" '
            f'rx="5" fill="{color}">'
            f"<title>{esc(label)}: {number(value, 2)}</title>"
            "</rect>"
        )

        elements.append(
            f'<text x="{left+plot_width+10}" '
            f'y="{y+15}" class="svg-value">'
            f"{esc(number(value))}</text>"
        )

    return (
        '<svg class="chart" role="img" '
        f'viewBox="0 0 {width} {height}">'
        + "".join(elements)
        + "</svg>"
    )


def line_chart(labels, series, ylabel="Detections"):
    """Generate a vector line chart with multiple series."""

    width = 940
    height = 305

    x0, y0 = 65, 30
    x1, y1 = 915, 245

    values = []

    for _, data, _ in series:
        values.extend(
            float(v)
            for v in data
            if v is not None and math.isfinite(float(v))
        )

    if not values or not labels:
        return '<p class="muted">No chart data.</p>'

    maximum = max(1, max(values))
    span = max(1, len(labels) - 1)

    elements = [
        f'<text x="65" y="18" class="svg-label">'
        f"{esc(ylabel)}</text>"
    ]

    for index in range(5):
        value = maximum * index / 4
        y = y1 - (y1-y0) * index / 4

        elements.append(
            f'<line x1="{x0}" x2="{x1}" '
            f'y1="{y:.1f}" y2="{y:.1f}" '
            'stroke="#dce3ec" stroke-dasharray="3,5"/>'
        )

        elements.append(
            f'<text x="{x0-8}" y="{y+4:.1f}" '
            'text-anchor="end" class="svg-label">'
            f"{esc(number(value))}</text>"
        )

    step = max(1, math.ceil(len(labels) / 12))

    for index in range(0, len(labels), step):
        x = x0 + (x1-x0) * index / span

        elements.append(
            f'<text x="{x:.1f}" y="{y1+20}" '
            'text-anchor="middle" class="svg-label">'
            f"{esc(labels[index])}</text>"
        )

    legend = []

    for name, data, color in series:
        points = []

        for index, value in enumerate(data[:len(labels)]):
            if value is None:
                if len(points) >= 2:
                    elements.append(
                        '<polyline fill="none" '
                        f'stroke="{color}" stroke-width="2.6" '
                        f'points="{" ".join(points)}"/>'
                    )

                points = []
                continue

            value = float(value)

            if not math.isfinite(value):
                continue

            x = x0 + (x1-x0) * index / span
            y = y1 - (y1-y0) * max(0, value) / maximum

            points.append(f"{x:.1f},{y:.1f}")

        if len(points) >= 2:
            elements.append(
                '<polyline fill="none" '
                f'stroke="{color}" stroke-width="2.6" '
                f'points="{" ".join(points)}"/>'
            )

        legend.append(
            '<span>'
            f'<i style="background:{color}"></i>'
            f"{esc(name)}</span>"
        )

    return (
        '<svg class="chart" role="img" '
        f'viewBox="0 0 {width} {height}">'
        + "".join(elements)
        + "</svg>"
        + '<div class="legend">'
        + "".join(legend)
        + "</div>"
    )


def calendar_chart(year, rows):
    """Full 365/366-day UTC calendar heatmap."""

    counts = {
        str(row["day"]): int(row["n"])
        for row in rows
    }

    first = date(year, 1, 1)
    next_year = date(year + 1, 1, 1)
    days = (next_year - first).days

    values = [
        counts.get(
            (first + timedelta(days=i)).isoformat(),
            0,
        )
        for i in range(days)
    ]

    maximum = max(values or [0])

    colors = (
        "#edf1f6",
        "#ffe6bb",
        "#f7c084",
        "#ef9554",
        "#c6572f",
    )

    shapes = []

    for month in range(1, 13):
        first_day = date(year, month, 1)

        index = (
            (first_day - first).days
            + first.weekday()
        )

        column = index // 7
        x = 61 + column * 16

        shapes.append(
            f'<text x="{x}" y="19" '
            'class="svg-label">'
            f"{MONTHS[month-1]}</text>"
        )

    for index, count in enumerate(values):
        current = first + timedelta(days=index)

        column, weekday = divmod(
            index + first.weekday(),
            7,
        )

        x = 61 + column * 16
        y = 33 + weekday * 16

        if count == 0:
            intensity = 0
        else:
            intensity = min(
                4,
                1 + int(
                    3 * math.log1p(count)
                    / math.log1p(max(maximum, 1))
                ),
            )

        shapes.append(
            f'<rect x="{x}" y="{y}" '
            'width="13" height="13" rx="2" '
            f'fill="{colors[intensity]}">'
            f"<title>{current}: {count:,} detections</title>"
            "</rect>"
        )

    return (
        '<div class="scroll-chart">'
        '<svg class="calendar" '
        'viewBox="0 0 945 158" role="img">'
        + "".join(shapes)
        + "</svg></div>"
        '<p class="caption">'
        "Daily thermal detections · UTC · logarithmic scale"
        "</p>"
    )


def metrics_html(metrics):
    labels = {
        "detections": "Thermal observations",
        "tracks": "Candidate tracks",
        "active_days": "Active observation days",
        "linked": "Linked detections",
        "unresolved": "Unresolved eligible",
        "outside_scope": "Outside tracking scope",
    }

    return (
        '<div class="kpi-grid">'
        + "".join(
            '<div class="kpi">'
            f"<small>{esc(label)}</small>"
            f"<strong>{number(metrics.get(key))}</strong>"
            "</div>"
            for key, label in labels.items()
        )
        + "</div>"
    )


def build_report_html(filters, ai_result):
    """Build the complete HTML document from IGNIS data."""

    # Import here to avoid circular imports with main.py.
    from . import main

    overview = main.analytical("overview", filters)
    temporal = main.analytical("temporal", filters)
        # Build calendar counts from the existing temporal analytics.
    # This avoids an unnecessary API query and aggregates sensors.
    calendar_counts = defaultdict(int)

    for row in temporal:
        if row.get("day") is not None:
            calendar_counts[str(row["day"])[:10]] += int(
                row.get("n") or 0
            )

    calendar = [
        {"day": day, "n": count}
        for day, count in sorted(calendar_counts.items())
    ]
    spatial = main.analytical("spatial", filters)
    sensors = main.analytical("sensors", filters)
    tracks = main.analytical("tracks", filters)

    comparison_request = main.Compare.model_validate({
        **filters.model_dump(mode="json"),
        "years": list(main.YEARS),
    })

    comparisons = main.compare(comparison_request)
    quality = main.quality(filters.country, filters.year)

    report = ai_result["report"]
    evidence = ai_result.get("evidence") or {}
    metrics = overview["metrics"]

    # Reconcile tracking accounting.
    total = int(metrics.get("detections") or 0)

    categories = sum(
        int(metrics.get(key) or 0)
        for key in (
            "linked",
            "unresolved",
            "outside_scope",
        )
    )

    if categories != total:
        raise ValueError(
            "Tracking categories do not reconcile."
        )

    daily = defaultdict(int)
    monthly = defaultdict(int)
    daynight = defaultdict(int)

    for row in temporal:
        current_day = str(row["day"])
        count = int(row["n"])

        daily[current_day] += count
        monthly[current_day[5:7]] += count
        daynight[row.get("daynight") or "Unknown"] += count

    start = (
        date.fromisoformat(str(filters.start)[:10])
        if filters.start
        else date(filters.year, 1, 1)
    )

    end = (
        date.fromisoformat(str(filters.end)[:10])
        if filters.end
        else date(filters.year, 12, 31)
    )

    dates = [
        start + timedelta(days=i)
        for i in range((end-start).days + 1)
    ]

    daily_values = [
        daily.get(day.isoformat(), 0)
        for day in dates
    ]

    daily_labels = [
        day.strftime("%d %b") if day.day == 1 else ""
        for day in dates
    ]

    monthly_values = [
        monthly.get(f"{month:02d}", 0)
        for month in range(1, 13)
    ]

    sensor_stats = sensors.get("stats") or []
    sensor_names = [
        row["sensor"]
        for row in sensor_stats
    ]

    sensor_bars = [
        (
            row["sensor"],
            row["n"],
            SENSOR_COLORS.get(
                row["sensor"],
                COLORS[3],
            ),
        )
        for row in sensor_stats
    ]

    daynight_bars = [
        (
            "Day" if flag == "D"
            else "Night" if flag == "N"
            else flag,
            count,
        )
        for flag, count in sorted(daynight.items())
    ]

    # Historical year comparison.
    annual_bars = [
        (
            str(row["year"]),
            row["total"],
        )
        for row in comparisons
        if row["available"]
    ]

    historical_series = []

    for index, row in enumerate(comparisons):
        if not row["available"]:
            continue

        counts = defaultdict(int)

        for item in row["monthly"]:
            counts[int(item["month"])] += int(item["n"])

        historical_series.append((
            str(row["year"]),
            [
                counts.get(month, 0)
                for month in range(1, 13)
            ],
            COLORS[index % len(COLORS)],
        ))

    annual_sensor_series = []

    for index, sensor in enumerate(sensor_names):
        values = []

        for row in comparisons:
            if not row["available"]:
                values.append(None)
                continue

            values.append(sum(
                int(item["n"])
                for item in row["monthly"]
                if item["sensor"] == sensor
            ))

        annual_sensor_series.append((
            sensor,
            values,
            SENSOR_COLORS.get(
                sensor,
                COLORS[index % len(COLORS)],
            ),
        ))

    # Sensor monthly and FRP analytics.
    sensor_monthly = defaultdict(int)
    frp = defaultdict(lambda: [0.0, 0])
    sensor_daynight = defaultdict(int)

    for row in sensors.get("monthly") or []:
        sensor = row["sensor"]
        month = str(row.get("month") or "")[-2:]
        count = int(row["n"])

        if month not in {
            f"{i:02d}" for i in range(1, 13)
        }:
            continue

        sensor_monthly[(sensor, month)] += count

        flag = row.get("daynight") or "Unknown"
        sensor_daynight[(sensor, flag)] += count

        samples = int(row.get("frp_n") or 0)
        mean = row.get("mean_frp")

        if samples and mean is not None:
            frp[(sensor, month)][0] += float(mean) * samples
            frp[(sensor, month)][1] += samples

    monthly_sensor_series = []
    monthly_frp_series = []

    for index, sensor in enumerate(sensor_names):
        color = SENSOR_COLORS.get(
            sensor,
            COLORS[index % len(COLORS)],
        )

        monthly_sensor_series.append((
            sensor,
            [
                sensor_monthly.get(
                    (sensor, f"{month:02d}"),
                    0,
                )
                for month in range(1, 13)
            ],
            color,
        ))

        frp_values = []

        for month in range(1, 13):
            weighted_sum, count = frp[
                (sensor, f"{month:02d}")
            ]

            frp_values.append(
                weighted_sum / count if count else None
            )

        monthly_frp_series.append((
            sensor,
            frp_values,
            color,
        ))

    # Spatial analysis.
    cells = spatial.get("cells") or []

    cell_bars = [
        (
            f'{float(row["y"])+0.125:.3f}, '
            f'{float(row["x"])+0.125:.3f}',
            row["n"],
        )
        for row in cells[:12]
    ]

    spatial_monthly = defaultdict(int)

    for row in spatial.get("monthly") or []:
        month = str(row.get("month") or "")[-2:]

        if month in {
            f"{i:02d}" for i in range(1, 13)
        }:
            spatial_monthly[
                (row["sensor"], month)
            ] += int(row["n"])

    spatial_names = sorted({
        key[0] for key in spatial_monthly
    })

    spatial_series = [
        (
            sensor,
            [
                spatial_monthly.get(
                    (sensor, f"{month:02d}"),
                    0,
                )
                for month in range(1, 13)
            ],
            SENSOR_COLORS.get(
                sensor,
                COLORS[index % len(COLORS)],
            ),
        )
        for index, sensor in enumerate(spatial_names)
    ]

    # Candidate tracks: ranked sample, not full population.
    track_bars = [
        (
            str(row["candidate_event_id"])[-20:],
            row["detections"],
        )
        for row in tracks[:12]
    ]

    track_day_bars = [
        ("1 day", sum(row["days"] == 1 for row in tracks)),
        ("2 days", sum(row["days"] == 2 for row in tracks)),
        ("3 days", sum(row["days"] == 3 for row in tracks)),
        ("4–7 days", sum(
            4 <= row["days"] <= 7
            for row in tracks
        )),
        ("8+ days", sum(
            row["days"] >= 8
            for row in tracks
        )),
    ]

    # Data tables.
    year_rows = [
        {
            "year": row["year"],
            "available": "Yes" if row["available"] else "No",
            "total": (
                number(row["total"])
                if row["available"]
                else "Unavailable"
            ),
            "yoy": (
                number(row["yoy_pct"], 2) + "%"
                if row.get("yoy_pct") is not None
                else "—"
            ),
        }
        for row in comparisons
    ]

    sensor_rows = [
        {
            "sensor": row["sensor"],
            "n": number(row["n"]),
            "mean_frp": number(row.get("mean_frp"), 2),
            "percentiles": " / ".join(
                number(value, 2)
                for value in (
                    row.get("frp_percentiles") or []
                )
            ),
            "brightness": number(
                row.get("brightness"), 2
            ),
        }
        for row in sensor_stats
    ]

    track_rows = [
        {
            "id": row["candidate_event_id"],
            "n": number(row["detections"]),
            "days": row["days"],
            "hours": number(row.get("hours"), 1),
        }
        for row in tracks[:30]
    ]

    quality_rows = [
        {
            "name": name,
            "value": number(value),
        }
        for name, value in (
            quality.get("rows") or {}
        ).items()
    ]

    # HTML document assembly.
    sections = []

    def add_section(index, title, content):
        sections.append(
            '<section class="section">'
            f'<div class="section-tag">SECTION {index:02d}</div>'
            f"<h2>{esc(title)}</h2>"
            f"{content}"
            "</section>"
        )

    # Cover.
    sections.append(
        '<div class="kicker">'
        "NASA FIRMS · HISTORICAL INTELLIGENCE"
        "</div>"
        "<h1>IGNIS"
        "<span>Scientific Intelligence Report</span></h1>"
        '<p class="subtitle">'
        f'{esc(COUNTRIES[filters.country])} · '
        f'{filters.year} · '
        f'{esc(filters.sensor or "All sensors")}'
        "</p>"
        '<p class="caption">'
        f"Selected date range: {esc(start)} to {esc(end)} UTC. "
        "Annual comparisons use complete calendar years."
        "</p>"
        + metrics_html(metrics)
    )

    # 1 — Executive Summary.
    add_section(
        1,
        "Executive Summary",
        card(
            "AI Executive Summary",
            paragraphs(report.get("executive_summary")),
        )
        + card(
            "Monthly Thermal Activity",
            bar_chart([
                (MONTHS[i], monthly_values[i])
                for i in range(12)
            ]),
        )
        + card(
            "Sensor Distribution",
            bar_chart(sensor_bars),
        )
        + card(
            "Day / Night Observations",
            bar_chart(daynight_bars),
        ),
    )

    # 2 — Temporal.
    add_section(
        2,
        "Temporal Analytics",
        card(
            f"Full-Year Calendar Heatmap · {filters.year}",
            calendar_chart(filters.year, calendar),
            "Zero detections do not necessarily mean "
            "that no fire occurred.",
        )
        + card(
            "Daily Thermal Activity",
            line_chart(
                daily_labels,
                [
                    (
                        "Observations",
                        daily_values,
                        COLORS[0],
                    )
                ],
            ),
        )
        + card(
            "Monthly Activity",
            line_chart(
                list(MONTHS),
                [
                    (
                        "Monthly detections",
                        monthly_values,
                        COLORS[0],
                    )
                ],
            ),
        ),
    )

    # 3 — Historical comparison.
    add_section(
        3,
        "Six-Year Historical Comparison",
        card(
            "Annual Detection Totals",
            bar_chart(annual_bars),
        )
        + card(
            "Monthly Trends Across Years",
            line_chart(
                list(MONTHS),
                historical_series,
            ),
        )
        + card(
            "Annual Activity by Sensor",
            line_chart(
                [str(r["year"]) for r in comparisons],
                annual_sensor_series,
            ),
        )
        + card(
            "Year-over-Year Statistics",
            make_table(
                [
                    ("Year", "year"),
                    ("Available", "available"),
                    ("Detections", "total"),
                    ("YoY Change", "yoy"),
                ],
                year_rows,
            ),
        ),
    )

    # 4 — Spatial.
    add_section(
        4,
        "Spatial Analytics",
        '<p class="notice">'
        "Observation density represents detection counts, "
        "not burned area or confirmed fire boundaries."
        "</p>"
        + card(
            "Monthly Spatial Activity by Sensor",
            line_chart(
                list(MONTHS),
                spatial_series,
            ),
        )
        + card(
            "Highest-Activity Grid Cells",
            bar_chart(cell_bars),
            "Coordinates represent 0.25-degree cell centers.",
        ),
    )

    # 5 — Sensors.
    frp_labels = (
        "<0",
        "0–<10",
        "10–<50",
        "50–<100",
        "100–<500",
        "≥500",
    )

    frp_bins = sensors.get("frp_bins") or []

    frp_bars = [
        (
            frp_labels[i],
            sum(
                int(row["n"])
                for row in frp_bins
                if row["bin"] == i
            ),
        )
        for i in range(6)
    ]

    sensor_daynight_bars = [
        (
            f"{sensor} / {flag}",
            sensor_daynight[(sensor, flag)],
        )
        for sensor in sensor_names
        for flag in ("D", "N")
    ]

    add_section(
        5,
        "Sensor and FRP Analysis",
        '<p class="notice">'
        "MODIS and VIIRS have different observation "
        "characteristics. Detection totals are not "
        "directly comparable measures of wildfire incidence."
        "</p>"
        + card(
            "Detections by Sensor",
            bar_chart(sensor_bars),
        )
        + card(
            "Monthly Sensor Activity",
            line_chart(
                list(MONTHS),
                monthly_sensor_series,
            ),
        )
        + card(
            "Day / Night by Sensor",
            bar_chart(sensor_daynight_bars),
        )
        + card(
            "Monthly Mean FRP (MW)",
            line_chart(
                list(MONTHS),
                monthly_frp_series,
                "Mean FRP (MW)",
            ),
        )
        + card(
            "FRP Distribution",
            bar_chart(frp_bars),
        )
        + card(
            "Sensor Measurement Summary",
            make_table(
                [
                    ("Sensor", "sensor"),
                    ("Detections", "n"),
                    ("Mean FRP", "mean_frp"),
                    ("FRP p10/p50/p90", "percentiles"),
                    ("Brightness (K)", "brightness"),
                ],
                sensor_rows,
            ),
        ),
    )

    # 6 — Candidate Tracks.
    add_section(
        6,
        "Candidate Track Analysis",
        '<p class="notice">'
        "Candidate tracks are not confirmed independent "
        "wildfire events. Charts below describe only the "
        "top-ranked returned tracks, not all tracks."
        "</p>"
        + card(
            "Top Candidate Tracks",
            bar_chart(track_bars),
        )
        + card(
            "Observed Days Distribution — Ranked Sample",
            bar_chart(track_day_bars),
        )
        + card(
            "Candidate Track Details",
            make_table(
                [
                    ("Candidate ID", "id"),
                    ("Detections", "n"),
                    ("Observed Days", "days"),
                    ("Span Hours", "hours"),
                ],
                track_rows,
            ),
        ),
    )

    # 7 — Quality.
    report_names = sorted(
        str(name)
        for name in (
            quality.get("reports") or {}
        )
    )

    add_section(
        7,
        "Data Quality and Provenance",
        card(
            "Release Metadata",
            f'<p>Country: {esc(filters.country)} · '
            f'Year: {filters.year} · '
            f'Version: {esc(quality.get("version"))}</p>'
            + make_table(
                [
                    ("Dataset", "name"),
                    ("Rows", "value"),
                ],
                quality_rows,
            ),
        )
        + card(
            "Available Validation Reports",
            "<ul>"
            + "".join(
                f"<li>{esc(name)}</li>"
                for name in report_names
            )
            + "</ul>",
        )
        + '<p class="notice">'
        "Engineering validation is not independent "
        "wildfire ground-truth verification."
        "</p>",
    )

    # 8 — AI Interpretations.
    ai_sections = (
        ("Temporal Interpretation", "temporal_analysis"),
        ("Spatial Interpretation", "spatial_analysis"),
        ("Sensor Interpretation", "sensor_analysis"),
        (
            "Candidate Tracks Interpretation",
            "candidate_tracks_analysis",
        ),
        ("Year Comparison", "year_comparison"),
        ("Data Quality", "data_quality"),
    )

    ai_content = "".join(
        card(title, paragraphs(report.get(key)))
        for title, key in ai_sections
    )

    findings = "<ol>"

    for item in report.get("key_findings", []):
        findings += (
            "<li>"
            f"<strong>{esc(item.get('title'))}</strong>"
            + paragraphs(item.get("explanation"))
            + '<p class="references">Evidence: '
            + esc(", ".join(item.get("evidence_ids") or []))
            + "</p></li>"
        )

    findings += "</ol>"

    add_section(
        8,
        "AI Scientific Interpretation",
        '<p class="notice">'
        f'Generated using {esc(ai_result.get("model"))}. '
        "AI-generated interpretations require human review."
        "</p>"
        + ai_content
        + card("Key Scientific Findings", findings),
    )

    # 9 — Recommended actions.
    actions = "<ol>"

    for item in report.get("recommended_actions", []):
        actions += (
            "<li>"
            f"<strong>{esc(item.get('action'))}</strong>"
            + paragraphs(item.get("rationale"))
            + f'<p>Priority: {esc(item.get("priority"))}</p>'
            + f'<p class="caption">Caution: '
            f'{esc(item.get("caution"))}</p>'
            + '<p class="references">Evidence: '
            + esc(", ".join(item.get("evidence_ids") or []))
            + "</p></li>"
        )

    actions += "</ol>"

    add_section(
        9,
        "Evidence-Based Recommended Actions",
        card("Suggested Actions", actions)
        + '<p class="notice">'
        "These suggestions are not emergency instructions "
        "or evidence of future wildfire risk."
        "</p>",
    )

    # 10 — Limitations.
    limits = "".join(
        f"<li>{esc(item)}</li>"
        for item in report.get("scientific_limitations", [])
    )

    add_section(
        10,
        "Scientific Limitations and Conclusion",
        card("Scientific Limitations", f"<ul>{limits}</ul>")
        + card(
            "Final Conclusion",
            paragraphs(report.get("conclusion")),
        ),
    )

    # 11 — Supporting evidence.
    evidence_html = ""

    for key, value in sorted(evidence.items()):
        evidence_html += (
            "<details>"
            f"<summary>{esc(key)}</summary>"
            "<pre>"
            + esc(json.dumps(value, ensure_ascii=False))
            + "</pre></details>"
        )

    add_section(
        11,
        "Supporting Evidence and Audit Trail",
        '<p class="caption">'
        "Evidence records referenced by the AI report."
        "</p>"
        + evidence_html,
    )

    # Standalone HTML design.
    css = """
        :root {
        color-scheme: light;
        --bg: #ffffff;
        --surface: #ffffff;
        --border: #dce3ec;
        --text: #172638;
        --muted: #5c6c7e;
        --accent: #d8662b;
        }

        * {
        box-sizing: border-box;
        }

        body {
        margin: 0;
        background: #ffffff;
        color: var(--text);
        font: 15px/1.7 Arial, Helvetica, sans-serif;
        }

        .report {
        max-width: 1120px;
        margin: 0 auto;
        padding: 50px 35px 80px;
        }

        h1 {
        font-size: 52px;
        line-height: 1.15;
        margin: 14px 0;
        color: #14243a;
        }

        h1 span {
        display: block;
        font-size: 29px;
        color: #56677d;
        font-weight: 400;
        }

        h2 {
        font-size: 28px;
        margin: 10px 0 24px;
        color: #18314e;
        }

        h3 {
        font-size: 17px;
        margin: 0 0 15px;
        color: #223b56;
        }

        p {
        line-height: 1.8;
        }

        .kicker,
        .section-tag {
        color: var(--accent);
        font-size: 11px;
        font-weight: 750;
        letter-spacing: 2px;
        text-transform: uppercase;
        }

        .subtitle {
        font-size: 19px;
        font-weight: 600;
        }

        .section {
        border-top: 2px solid #e3e9f0;
        padding: 42px 0 18px;
        }

        .card {
        background: #ffffff;
        border: 1px solid #dce3ec;
        border-radius: 10px;
        padding: 22px;
        margin: 16px 0;
        break-inside: avoid;
        }

        .kpi-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 13px;
        margin: 28px 0 40px;
        }

        .kpi {
        background: #f7f9fc;
        border: 1px solid #dce3ec;
        border-radius: 9px;
        padding: 17px;
        }

        .kpi small {
        display: block;
        color: var(--muted);
        font-size: 12px;
        }

        .kpi strong {
        display: block;
        font-size: 25px;
        color: #18314e;
        }

        .caption,
        .muted {
        color: var(--muted);
        font-size: 12px;
        }

        .notice {
        background: #fff7f0;
        border-left: 3px solid var(--accent);
        padding: 13px 16px;
        border-radius: 0 8px 8px 0;
        color: #513920;
        }

        .chart {
        max-width: 100%;
        height: auto;
        display: block;
        }

        .calendar {
        min-width: 800px;
        max-width: 100%;
        }

        .scroll-chart {
        overflow-x: auto;
        }

        .svg-label {
        fill: #526479;
        font-size: 12px;
        font-family: Arial, sans-serif;
        }

        .svg-value {
        fill: #20354c;
        font-size: 12px;
        font-weight: 700;
        }

        .legend {
        display: flex;
        flex-wrap: wrap;
        gap: 13px;
        color: var(--muted);
        font-size: 12px;
        margin-top: 12px;
        }

        .legend span {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        }

        .legend i {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 3px;
        }

        .table-wrap {
        overflow-x: auto;
        }

        table {
        width: 100%;
        border-collapse: collapse;
        text-align: left;
        font-size: 13px;
        }

        th,
        td {
        border-bottom: 1px solid #dce3ec;
        padding: 10px 12px;
        vertical-align: top;
        overflow-wrap: anywhere;
        }

        th {
        background: #f2f6fa;
        color: #42556b;
        font-size: 11px;
        text-transform: uppercase;
        }

        li {
        margin-bottom: 13px;
        }

        .references {
        color: #147d71;
        font-size: 12px;
        }

        details {
        border: 1px solid #dce3ec;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        }

        summary {
        cursor: pointer;
        }

        pre {
        white-space: pre-wrap;
        overflow-wrap: anywhere;
        font-size: 11px;
        }

        @page {
        size: A4;
        margin: 16mm;
        }

        @media (max-width: 700px) {
        .report {
            padding: 25px 15px;
        }

        h1 {
            font-size: 35px;
        }

        h1 span {
            font-size: 22px;
        }

        .kpi-grid {
            grid-template-columns: 1fr;
        }
        }

        @media print {
        html,
        body {
            background: #ffffff !important;
            color: #172638 !important;
        }

        .report {
            max-width: none;
            padding: 0;
        }

        .section {
            break-before: auto;
        }

        .card,
        .kpi,
        tr,
        svg {
            break-inside: avoid;
            page-break-inside: avoid;
        }

        h2,
        h3 {
            break-after: avoid;
        }

        .kpi {
            background: #f7f9fc;
        }

        .chart {
            width: 100%;
            max-height: 250mm;
        }

        .calendar {
            min-width: 0;
            width: 100%;
        }

        .svg-label {
            fill: #526479;
        }

        .svg-value {
            fill: #20354c;
        }

        details {
            break-inside: auto;
        }

        details:not([open]) > :not(summary) {
            display: block;
        }

        * {
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }
        }

    """

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")

    return (
        "<!doctype html>"
        '<html lang="en">'
        "<head>"
        '<meta charset="utf-8">'
        '<meta name="viewport" '
        'content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        "<title>IGNIS Scientific Intelligence Report</title>"
        f"<style>{css}</style>"
        "</head>"
        "<body>"
        '<main class="report">'
        + "".join(sections)
        + '<footer class="caption">'
        f"IGNIS · Generated {esc(timestamp)} · "
        "NASA FIRMS historical observations. "
        "Not an emergency warning system."
        "</footer>"
        "</main>"
        "</body>"
        "</html>"
    )
