"""
Fetch historical daily weather for a state (via a representative city's
coordinates) from Open-Meteo's free Archive API — no key required — then
aggregate it to monthly figures matching the electricity data's grain.

Starting with Maharashtra (Mumbai coordinates) to keep the first pass
simple; swap COORDS below (or pass --lat/--lon/--label) to add more states
once this one works end-to-end.

Run this on your own machine — same network restriction as the PDF
downloader, this chat's sandbox can't reach external APIs.

Usage:
    pip install requests
    python fetch_weather.py --start 2016-01-01 --end 2026-09-25 \
        --out-daily data/raw/weather_maharashtra_daily.csv \
        --out-monthly data/processed/weather_maharashtra_monthly.csv
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

import requests

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Representative city coordinates per state. Add more here as you scale up
# beyond one state — state-level electricity figures don't have a single
# "true" coordinate, so using the largest city (or capital) as a proxy is
# the standard approach for this kind of analysis.
COORDS = {
    "Maharashtra": (19.0760, 72.8777),   # Mumbai
    "Uttarakhand": (30.3165, 78.0322),   # Dehradun
}

DAILY_VARS = "temperature_2m_max,temperature_2m_min,precipitation_sum"


def fetch_daily_weather(lat, lon, start_date, end_date):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date,
        "end_date": end_date,
        "daily": DAILY_VARS,
        "timezone": "Asia/Kolkata",
    }
    resp = requests.get(ARCHIVE_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    daily = data["daily"]
    rows = []
    for i, date in enumerate(daily["time"]):
        rows.append({
            "date": date,
            "temp_max_c": daily["temperature_2m_max"][i],
            "temp_min_c": daily["temperature_2m_min"][i],
            "precipitation_mm": daily["precipitation_sum"][i],
        })
    return rows


def aggregate_monthly(daily_rows):
    buckets = defaultdict(list)
    for r in daily_rows:
        year, month, _ = r["date"].split("-")
        buckets[(int(year), int(month))].append(r)

    monthly = []
    for (year, month), rows in sorted(buckets.items()):
        temp_maxes = [r["temp_max_c"] for r in rows if r["temp_max_c"] is not None]
        temp_mins = [r["temp_min_c"] for r in rows if r["temp_min_c"] is not None]
        precips = [r["precipitation_mm"] for r in rows if r["precipitation_mm"] is not None]
        monthly.append({
            "year": year,
            "month": month,
            "avg_temp_max_c": round(sum(temp_maxes) / len(temp_maxes), 2) if temp_maxes else None,
            "avg_temp_min_c": round(sum(temp_mins) / len(temp_mins), 2) if temp_mins else None,
            "total_precipitation_mm": round(sum(precips), 2) if precips else None,
            "days_in_month": len(rows),
        })
    return monthly


def write_csv(rows, path: Path, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="Maharashtra", help="Must match a key in COORDS, or pass --lat/--lon/--label")
    ap.add_argument("--lat", type=float, help="Override latitude (skips COORDS lookup)")
    ap.add_argument("--lon", type=float, help="Override longitude (skips COORDS lookup)")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD (Open-Meteo archive has a few days' lag from today)")
    ap.add_argument("--out-daily", default="data/raw/weather_daily.csv")
    ap.add_argument("--out-monthly", default="data/processed/weather_monthly.csv")
    args = ap.parse_args()

    if args.lat is not None and args.lon is not None:
        lat, lon = args.lat, args.lon
    elif args.state in COORDS:
        lat, lon = COORDS[args.state]
    else:
        raise SystemExit(
            f"'{args.state}' not in COORDS. Add it to the COORDS dict, or pass --lat/--lon directly."
        )

    print(f"Fetching {args.state} weather ({lat}, {lon}) from {args.start} to {args.end}...")
    daily_rows = fetch_daily_weather(lat, lon, args.start, args.end)
    print(f"Got {len(daily_rows)} daily records.")

    write_csv(daily_rows, Path(args.out_daily), ["date", "temp_max_c", "temp_min_c", "precipitation_mm"])
    print(f"Wrote daily data to {args.out_daily}")

    monthly_rows = aggregate_monthly(daily_rows)
    write_csv(
        monthly_rows, Path(args.out_monthly),
        ["year", "month", "avg_temp_max_c", "avg_temp_min_c", "total_precipitation_mm", "days_in_month"],
    )
    print(f"Wrote {len(monthly_rows)} monthly records to {args.out_monthly}")


if __name__ == "__main__":
    main()
