"""
Sanity-check the output of parse_psp_pdfs.py before it goes anywhere near
SQL or Power BI. A normal month should yield roughly:
  - ~39 states/UTs + 5 region totals + 1 grand total = ~45 rows
  - x2 if period_type has both 'monthly' and 'cumulative_fy' (dual layout)
So each source file should show up 40-95 times in the CSV. Anything well
outside that range likely means a format variant the parser doesn't
recognize yet for that month, and got silently under/mis-parsed.

Usage:
    python validate_parsed_data.py data/processed/psp_energy_clean.csv
"""
import argparse
import csv
from collections import defaultdict

EXPECTED_MIN = 30   # rows per file below this = probably a parsing miss
EXPECTED_MAX = 100  # rows per file above this = probably duplicated/garbled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    args = ap.parse_args()

    counts = defaultdict(int)
    null_value_rows = defaultdict(int)
    states_by_file = defaultdict(set)

    with open(args.csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            src = row["source_file"]
            counts[src] += 1
            states_by_file[src].add(row["state"])
            if row["requirement_mu"] in ("", None) and row["supplied_mu"] in ("", None):
                null_value_rows[src] += 1

    print(f"{len(counts)} source files parsed.\n")

    suspicious = []
    for src, n in sorted(counts.items()):
        flag = ""
        if n < EXPECTED_MIN:
            flag = "TOO FEW ROWS — likely an unrecognized format"
        elif n > EXPECTED_MAX:
            flag = "TOO MANY ROWS — check for duplication"
        elif null_value_rows[src] > n * 0.3:
            flag = f"{null_value_rows[src]} rows with no numbers — check extraction"
        if flag:
            suspicious.append((src, n, flag))

    if suspicious:
        print(f"{len(suspicious)} file(s) need a manual look:\n")
        for src, n, flag in suspicious:
            print(f"  {src}: {n} rows — {flag}")
        print(
            "\nOpen these specific PDFs and compare their table structure to the "
            "3 samples the parser was built against. You may need to add a third "
            "layout branch to parse_psp_pdfs.py for these."
        )
    else:
        print("All files fall within the expected row-count range. Looks consistent.")

    # cross-file consistency: state name spelling drift breaks later joins/group-bys
    all_states = set()
    for s in states_by_file.values():
        all_states |= s
    rare = {st for st in all_states if sum(st in fs for fs in states_by_file.values()) <= 2}
    if rare:
        print(f"\n{len(rare)} state label(s) appear in 2 or fewer files — likely spelling "
              f"variants that will break a group-by later:")
        for st in sorted(rare):
            print(f"  {st!r}")


if __name__ == "__main__":
    main()
