"""
Parse CEA / Grid-India monthly "Power Supply Position" PDF reports into a
clean, tidy CSV.

These reports are bilingual (Hindi/English) state-wise tables. pdfplumber
extracts each *region block* as a single table row, with every state's
name/number packed into one cell separated by "\n". This script:

  1. Locates the Power Supply Position table on the page (skips any Gross
     Generation table that may share the PDF).
  2. Detects which of the two known column layouts is in use:
       - "single"  : Requirement | Availability | Deficit(MU) | Deficit(%)
                     (seen in older reports, e.g. 2016)
       - "dual"    : the above, repeated once for the reporting month and
                     once for the year-to-date cumulative figure
                     (seen from ~2020 onward)
  3. Splits each packed cell back into one row per state, re-joining state
     names that wrapped onto a second line (a continuation line has no "/"
     separating Hindi/English).
  4. Extracts the reporting month/year from the filename (the PDF's own
     Hindi header text is unreliable to parse due to font/cid encoding
     issues in the source documents).

Usage:
    python parse_psp_pdfs.py <input_dir_or_files...> --out <output_csv>
"""

import argparse
import csv
import re
import sys
from pathlib import Path

import pdfplumber

MONTH_MAP = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}

# filenames look like: psp_energy_2016_04_xls.pdf  or  psp_energy_2020-10_xls.pdf
FILENAME_RE = re.compile(r"(\d{4})[_-](\d{2})")


def period_from_filename(path: Path):
    """Pull (year, month, month_name) out of the filename. Returns Nones if not found."""
    m = FILENAME_RE.search(path.stem)
    if not m:
        return None, None, None
    year, month = m.group(1), m.group(2)
    return int(year), int(month), MONTH_MAP.get(month, month)


def is_psp_table(table):
    """Heuristic: the Power Supply Position table has 'Requirement' (or the
    Hindi equivalent, which pdfplumber sometimes still renders legibly)
    somewhere in its header, and its data rows hold state names with '/'.
    Header depth varies by report era (some have an extra title/period row),
    so we scan the WHOLE table rather than just the first few rows.
    """
    full_text = " ".join(str(c) for row in table for c in (row or []) if c)
    if "Requirement" in full_text or "equirement" in full_text:
        return True
    return "Chandigarh" in full_text or "Delhi" in full_text


def detect_layout(table):
    """Return 'dual' or 'single' based on column count of the widest row."""
    ncols = max(len(row) for row in table)
    if ncols >= 8:
        return "dual"
    return "single"


def split_cell(cell):
    """Split a packed multi-line cell into a list of lines, dropping empties."""
    if cell is None:
        return []
    return [ln.strip() for ln in cell.split("\n") if ln.strip()]


STANDALONE_NO_SLASH = {"others"}  # rows with no Hindi/English "/" that are still their own entry, not a wrapped continuation


def merge_wrapped_names(name_lines, expected_count):
    """
    Some state names wrap onto a second physical line inside the cell
    (e.g. 'Dadra &' / 'Nagar Haveli'). A continuation line is one with no
    '/' separating Hindi and English. Merge it into the previous entry —
    unless it's a known standalone row (like the newer reports' "Others"
    catch-all line, which also has no '/' but is its own entry, not a wrap).
    """
    merged = []
    for line in name_lines:
        is_standalone_no_slash = line.strip().lower() in STANDALONE_NO_SLASH
        if "/" in line or is_standalone_no_slash or not merged:
            merged.append(line)
        else:
            merged[-1] = merged[-1] + " " + line
    if len(merged) != expected_count:
        # Best effort: if still mismatched, don't silently corrupt data —
        # signal it so the caller can log/skip the block.
        return None
    return merged


def english_name(raw):
    """Pull the English name out of 'हिंदी / English' text, strip footnote
    markers like '#', '*', '(#)', '(##)', trailing region-note codes."""
    part = raw.split("/")[-1]
    part = re.sub(r"\(#+\)|\(\*+\)|\(\$+\)|[#*$]", "", part)
    part = re.sub(r"\s+", " ", part).strip()
    return NAME_FIXES.get(part, part)

GRAND_TOTAL_NAMES = {"All India", "Grand Total"}

# The source PDFs' Hindi text layer occasionally drops trailing characters
# (a font/cid encoding issue in the reports themselves, not our parsing),
# which truncates a few English names. Known cases, patched here rather
# than silently left wrong:
NAME_FIXES = {
    "Andaman-": "Andaman & Nicobar",
    "Andaman-Nicobar": "Andaman & Nicobar",
    "Andaman- Nicobar": "Andaman & Nicobar",
    "North-Eastern": "North-Eastern Region",
}


def to_number(raw):
    if raw is None:
        return None
    raw = raw.strip().replace(",", "")
    if raw in ("", "-", "—"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_dual_block(name_col, cols, year, month, month_name, source_file):
    """cols = [req_m, sup_m, def_m_mu, def_m_pct, req_c, sup_c, def_c_mu, def_c_pct]"""
    name_lines = split_cell(name_col)
    n_expected = max(len(split_cell(c)) for c in cols)
    names = merge_wrapped_names(name_lines, n_expected)
    if names is None:
        return []
    split_cols = [split_cell(c) for c in cols]
    # pad short columns (occasional blank trailing cell) so zip doesn't truncate
    for sc in split_cols:
        while len(sc) < n_expected:
            sc.append(None)

    rows = []
    for i, raw_name in enumerate(names):
        state = english_name(raw_name)
        # Region blocks always end with that region's subtotal row; a
        # block of exactly one row is the standalone "All India" total.
        # Positional, so it doesn't depend on the source PDF's (sometimes
        # truncated) label text.
        is_grand_total = n_expected == 1 or state in GRAND_TOTAL_NAMES
        is_region_total = (not is_grand_total) and (i == n_expected - 1)
        vals = [split_cols[c][i] if i < len(split_cols[c]) else None for c in range(8)]
        base = dict(
            source_file=source_file, year=year, month=month, month_name=month_name,
            state=state, is_region_total=is_region_total, is_grand_total=is_grand_total,
        )
        rows.append({
            **base, "period_type": "monthly",
            "requirement_mu": to_number(vals[0]), "supplied_mu": to_number(vals[1]),
            "deficit_mu": to_number(vals[2]), "deficit_pct": to_number(vals[3]),
        })
        rows.append({
            **base, "period_type": "cumulative_fy",
            "requirement_mu": to_number(vals[4]), "supplied_mu": to_number(vals[5]),
            "deficit_mu": to_number(vals[6]), "deficit_pct": to_number(vals[7]),
        })
    return rows


def parse_single_block(name_col, cols, year, month, month_name, source_file):
    """cols = [req, avail, deficit_mu, deficit_pct]"""
    name_lines = split_cell(name_col)
    n_expected = max(len(split_cell(c)) for c in cols)
    names = merge_wrapped_names(name_lines, n_expected)
    if names is None:
        return []
    split_cols = [split_cell(c) for c in cols]
    for sc in split_cols:
        while len(sc) < n_expected:
            sc.append(None)

    rows = []
    for i, raw_name in enumerate(names):
        state = english_name(raw_name)
        is_grand_total = n_expected == 1 or state in GRAND_TOTAL_NAMES
        is_region_total = (not is_grand_total) and (i == n_expected - 1)
        vals = [split_cols[c][i] if i < len(split_cols[c]) else None for c in range(4)]
        rows.append(dict(
            source_file=source_file, year=year, month=month, month_name=month_name,
            state=state, is_region_total=is_region_total, is_grand_total=is_grand_total,
            period_type="monthly",
            requirement_mu=to_number(vals[0]), supplied_mu=to_number(vals[1]),
            deficit_mu=to_number(vals[2]), deficit_pct=to_number(vals[3]),
        ))
    return rows


def parse_pdf(path: Path):
    year, month, month_name = period_from_filename(path)
    all_rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                if not table or not is_psp_table(table):
                    continue
                layout = detect_layout(table)
                for row in table:
                    if not row or row[0] is None:
                        continue
                    name_col = row[0]
                    if "State" in name_col or "System" in name_col:
                        continue  # header row
                    if name_col.strip().startswith(("Note", "#", "*", "(#")):
                        continue  # footnote row
                    if layout == "dual":
                        # widest rows have 9 cols: name + 4 monthly + 4 cumulative
                        cols = row[1:9] if len(row) >= 9 else None
                        if cols is None or len(cols) != 8:
                            continue
                        all_rows.extend(
                            parse_dual_block(name_col, cols, year, month, month_name, path.name)
                        )
                    else:
                        cols = row[1:5]
                        if len(cols) != 4:
                            continue
                        all_rows.extend(
                            parse_single_block(name_col, cols, year, month, month_name, path.name)
                        )

    # De-duplicate: if the same (state, period_type) shows up more than once
    # in a file — e.g. a report page matched the PSP-table heuristic twice —
    # keep the first occurrence only, so counts don't silently double.
    seen = set()
    deduped = []
    dupes = 0
    for r in all_rows:
        key = (r["state"], r["period_type"])
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        deduped.append(r)
    if dupes:
        print(f"  ({path.name}: dropped {dupes} duplicate row(s))", file=sys.stderr)
    return deduped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+", help="PDF files or a directory of PDFs")
    ap.add_argument("--out", default="data/processed/psp_energy_clean.csv")
    args = ap.parse_args()

    files = []
    for inp in args.inputs:
        p = Path(inp)
        if p.is_dir():
            files.extend(sorted(p.glob("*.pdf")))
        else:
            files.append(p)

    all_rows = []
    for f in files:
        rows = parse_pdf(f)
        print(f"{f.name}: parsed {len(rows)} rows", file=sys.stderr)
        all_rows.extend(rows)

    if not all_rows:
        print("No rows parsed — check the PDFs match the expected layout.", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "state", "year", "month", "month_name", "period_type",
        "requirement_mu", "supplied_mu", "deficit_mu", "deficit_pct",
        "is_region_total", "is_grand_total", "source_file",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_rows:
            writer.writerow(r)

    print(f"Wrote {len(all_rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
