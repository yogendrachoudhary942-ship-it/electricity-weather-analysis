"""
Load the cleaned PSP energy CSV into a local SQLite database.

Usage:
    python load_to_sqlite.py data/processed/psp_energy_clean.csv --db data/processed/psp.db
"""
import argparse
import csv
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS electricity_demand (
    state TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    month_name TEXT,
    period_type TEXT NOT NULL,      -- 'monthly' or 'cumulative_fy'
    requirement_mu REAL,
    supplied_mu REAL,
    deficit_mu REAL,
    deficit_pct REAL,
    is_region_total INTEGER,        -- 0/1
    is_grand_total INTEGER,         -- 0/1
    source_file TEXT
);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--db", default="data/processed/psp.db")
    args = ap.parse_args()

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.execute(SCHEMA)
    conn.execute("DELETE FROM electricity_demand")  # rerun-safe: full reload each time

    with open(args.csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [
            (
                r["state"], int(r["year"]), int(r["month"]), r["month_name"],
                r["period_type"],
                float(r["requirement_mu"]) if r["requirement_mu"] else None,
                float(r["supplied_mu"]) if r["supplied_mu"] else None,
                float(r["deficit_mu"]) if r["deficit_mu"] else None,
                float(r["deficit_pct"]) if r["deficit_pct"] else None,
                1 if r["is_region_total"] == "True" else 0,
                1 if r["is_grand_total"] == "True" else 0,
                r["source_file"],
            )
            for r in reader
        ]

    conn.executemany(
        """INSERT INTO electricity_demand
           (state, year, month, month_name, period_type, requirement_mu,
            supplied_mu, deficit_mu, deficit_pct, is_region_total, is_grand_total, source_file)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM electricity_demand").fetchone()[0]
    print(f"Loaded {n} rows into {args.db}")
    conn.close()


if __name__ == "__main__":
    main()
