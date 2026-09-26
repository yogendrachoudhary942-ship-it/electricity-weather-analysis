# Electricity Demand vs. Weather Analysis

A data analysis project examining electricity demand patterns across Indian states from 2016–2026, using the Central Electricity Authority's (CEA) monthly Power Supply Position reports as the primary data source, paired with weather data to explore how temperature and seasonality drive demand.

## What this project does

Answers: **how much does weather drive electricity demand across Indian states, and can that relationship be used to understand or predict demand patterns?**

## Data source

[Central Electricity Authority (CEA), Government of India](https://cea.nic.in) — monthly "Power Supply Position" reports, published as PDFs. Raw PDFs aren't tracked in this repo (126 files, too large) — regenerate them locally with the downloader script below, or re-download manually from CEA's site.

## Pipeline

1. **`scripts/download_psp_pdfs.py`** — semi-automated downloader for CEA's monthly reports (2016–2026)
2. **`scripts/parse_psp_pdfs.py`** — custom PDF parser. CEA changed the report's table layout multiple times over the decade (state groupings, column structure, and an added "Others" catch-all row all shifted across years) — this parser detects and handles each variant
3. **`scripts/validate_parsed_data.py`** — sanity-checks the parsed output for row-count anomalies per file, catching unrecognized layouts before they corrupt downstream analysis
4. **`scripts/load_to_sqlite.py`** — loads the cleaned CSV into a queryable SQLite database
5. **`scripts/clean_junk_rows.py`** — removes known parsing artifacts (e.g. stray label rows with no real data)

## Repo structure

```
psp_project/
├── data/
│   ├── raw/            (not tracked — regenerate via download script)
│   └── processed/      (cleaned CSV + SQLite database)
├── scripts/             (Python pipeline: download, parse, validate, load)
├── sql/                 (analysis queries)
├── powerbi/             (dashboard .pbix)
└── README.md
```

## Setup

```bash
pip install pdfplumber requests

# 1. Download raw reports
python scripts/download_psp_pdfs.py --start 2016-04 --end 2026-09 --out data/raw

# 2. Parse into clean CSV
python scripts/parse_psp_pdfs.py data/raw --out data/processed/psp_energy_clean.csv

# 3. Validate
python scripts/validate_parsed_data.py data/processed/psp_energy_clean.csv

# 4. Load into SQLite
python scripts/load_to_sqlite.py data/processed/psp_energy_clean.csv --db data/processed/psp.db
```

## Notes on data quality

CEA's report format isn't consistent across the 10-year span — this was one of the more interesting parts of the project. Handling real-world government data meant dealing with:
- Column layout changes (single-period vs. monthly+cumulative dual-period reports)
- State/UT groupings shifting over time (e.g. Daman & Diu and Dadra & Nagar Haveli merging into one UT; J&K and Ladakh becoming separate)
- A new "Others" catch-all row introduced in more recent reports
- Occasional duplicate table detection on some pages

The parser and validation scripts were built iteratively against these inconsistencies rather than assuming a single clean format.
