"""
Merge a state's monthly electricity demand (from the SQLite database built
earlier) with its monthly weather data (from fetch_weather.py) into one
analysis-ready CSV — the actual dataset this whole project is about.

Usage:
    python merge_electricity_weather.py \
        --db data/processed/psp.db \
        --state Maharashtra \
        --weather data/processed/weather_maharashtra_monthly.csv \
        --out data/processed/merged_maharashtra.csv
"""
import argparse
import csv
import sqlite3
from pathlib import Path


def load_electricity(db_path, state):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """SELECT year, month, month_name, requirement_mu, supplied_mu,
                  deficit_mu, deficit_pct
           FROM electricity_demand
           WHERE state = ? AND period_type = 'monthly'
           ORDER BY year, month""",
        (state,),
    ).fetchall()
    conn.close()
    return {(r[0], r[1]): {
        "month_name": r[2], "requirement_mu": r[3], "supplied_mu": r[4],
        "deficit_mu": r[5], "deficit_pct": r[6],
    } for r in rows}


def load_weather(csv_path):
    weather = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (int(row["year"]), int(row["month"]))
            weather[key] = row
    return weather


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/processed/psp.db")
    ap.add_argument("--state", required=True)
    ap.add_argument("--weather", required=True, help="Monthly weather CSV from fetch_weather.py")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    elec = load_electricity(args.db, args.state)
    weather = load_weather(args.weather)

    matched_keys = sorted(set(elec) & set(weather))
    elec_only = sorted(set(elec) - set(weather))
    weather_only = sorted(set(weather) - set(elec))

    print(f"Electricity months: {len(elec)}, weather months: {len(weather)}")
    print(f"Matched (in both): {len(matched_keys)}")
    if elec_only:
        print(f"  {len(elec_only)} month(s) have electricity data but no weather match "
              f"(e.g. {elec_only[:3]}) — check the weather date range covers them.")
    if weather_only:
        print(f"  {len(weather_only)} month(s) have weather data but no electricity match "
              f"(e.g. {weather_only[:3]}).")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "state", "year", "month", "month_name",
        "requirement_mu", "supplied_mu", "deficit_mu", "deficit_pct",
        "avg_temp_max_c", "avg_temp_min_c", "total_precipitation_mm",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for key in matched_keys:
            year, month = key
            e = elec[key]
            wx = weather[key]
            w.writerow({
                "state": args.state, "year": year, "month": month,
                "month_name": e["month_name"],
                "requirement_mu": e["requirement_mu"], "supplied_mu": e["supplied_mu"],
                "deficit_mu": e["deficit_mu"], "deficit_pct": e["deficit_pct"],
                "avg_temp_max_c": wx.get("avg_temp_max_c"),
                "avg_temp_min_c": wx.get("avg_temp_min_c"),
                "total_precipitation_mm": wx.get("total_precipitation_mm"),
            })

    print(f"\nWrote {len(matched_keys)} merged rows to {out_path}")


if __name__ == "__main__":
    main()
