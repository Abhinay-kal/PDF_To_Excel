"""Orchestrator for running multiple extraction methods and merging results.

This script can be used from the command line or imported as a module.  The
goal is to apply *all* of the available parsing strategies on a single PDF and
then combine the outputs, remove duplicates using a sensible set of rules, and
optionally write the intermediate and final Excel files to disk.

Example CLI usage::

    python pipeline.py input.pdf --output-dir results

The resulting directory will contain one Excel file per strategy (anchor, dual,
etc.) plus a ``merged.xlsx`` file with duplicates removed and validation
information added.

The methods available are determined by the modules in the repository; the
``PIPELINE_METHODS`` dictionary maps a short name to the corresponding
``process_pdf`` function.  You can supply a subset of the methods via the
``--methods`` argument if you only want to run particular strategies.
"""

import argparse
import os
from typing import Dict, List

import pandas as pd

# the various strategy modules.  each exports a ``process_pdf`` that returns a
# pandas.DataFrame (or an empty one on failure).
from anchor import process_pdf as anchor_process
from anchor_nameORepic import process_pdf as dual_process
from single_anchor_name import process_pdf as single_process
from cookie_cutter import process_pdf as cookie_process
from blob_detection import process_pdf as blob_process
from brute_id_anchored import process_pdf as brute_process
from grid_chop import process_pdf as grid_chop_process
from intelligent_parsing import process_pdf as intelligent_process
from gap_detection import process_pdf as gap_process
from double_anchor import process_pdf as double_process
from data_cleaning import clean_typos, validate_entry

PIPELINE_METHODS: Dict[str, callable] = {
    "anchor": anchor_process,
    "dual_anchor": dual_process,
    "single_anchor": single_process,
    "cookie_cutter": cookie_process,
    "blob_detection": blob_process,
    "brute_id_anchored": brute_process,
    "grid_chop": grid_chop_process,
    "intelligent_parsing": intelligent_process,
    "gap_detection": gap_process,
    "double_anchor": double_process,
}


# ---------- utility helpers ----------

def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Make a best-effort normalization of important columns."""
    df = df.copy()
    if "ID" in df.columns:
        df["ID"] = df["ID"].astype(str).str.upper().str.replace(" ", "")
    # strip whitespace from string columns
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def choose_better_row(a: pd.Series, b: pd.Series) -> pd.Series:
    """Return the row with more "good" data.

    Preference order:
    1. Row whose ``Status`` starts with "OK".
    2. Row with greater number of non-empty fields.
    """
    status_a = a.get("Status", "")
    status_b = b.get("Status", "")
    if status_a.startswith("OK") and not status_b.startswith("OK"):
        return a
    if status_b.startswith("OK") and not status_a.startswith("OK"):
        return b

    # compare number of non-null / non-empty values
    filled_a = sum(bool(v) for v in a.values())
    filled_b = sum(bool(v) for v in b.values())
    return a if filled_a >= filled_b else b


def dedup_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicates from a merged dataframe using sensible rules."""
    if df.empty:
        return df

    df = normalize_df(df)

    # apply cleaning/typo fixes if available
    if "ID" in df.columns:
        df["ID"] = df["ID"].apply(lambda x: clean_typos({"ID": x})["ID"])

    # add or refresh validation status
    df["Status"] = df.apply(lambda row: validate_entry(row.to_dict()), axis=1)

    # first pass: dedupe by ID
    if "ID" in df.columns:
        kept = {}
        rows = []
        for _, row in df.iterrows():
            key = row["ID"].strip()
            if key:
                if key in kept:
                    # decide which row is better
                    prev_idx = kept[key]
                    prev_row = rows[prev_idx]
                    winner = choose_better_row(prev_row, row)
                    if winner is row:
                        rows[prev_idx] = row
                else:
                    kept[key] = len(rows)
                    rows.append(row)
            else:
                rows.append(row)
        df = pd.DataFrame(rows).reset_index(drop=True)

    # second pass: dedupe entries without an ID using Name+HouseNo
    if "Name" in df.columns and "HouseNo" in df.columns:
        no_id = df[df["ID"] == ""].copy()
        no_id["_key"] = no_id["Name"].astype(str) + "|" + no_id["HouseNo"].astype(str)
        no_id = no_id.drop_duplicates(subset=["_key"]).drop(columns=["_key"])
        df = pd.concat([df[df["ID"] != ""], no_id], ignore_index=True, sort=False)

    return df


# ---------- pipeline functions ----------

def run_methods(pdf_path: str, methods: List[str] = None) -> Dict[str, pd.DataFrame]:
    """Execute each registered method on the PDF path.

    Returns a mapping from method name to resulting DataFrame.
    """
    to_run = methods or list(PIPELINE_METHODS.keys())
    results: Dict[str, pd.DataFrame] = {}

    for name in to_run:
        func = PIPELINE_METHODS.get(name)
        if func is None:
            print(f"[pipeline] method '{name}' not found; skipping")
            continue
        print(f"[pipeline] running '{name}'...")
        try:
            df = func(pdf_path)
            results[name] = df
        except Exception as exc:
            print(f"[pipeline] {name} failed: {exc}")
            results[name] = pd.DataFrame()
    return results


def merge_results(results: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Concatenate all non-empty DataFrames in the dictionary."""
    dfs = [df for df in results.values() if not df.empty]
    if not dfs:
        return pd.DataFrame()
    merged = pd.concat(dfs, ignore_index=True, sort=False)
    return merged


def pipeline(pdf_path: str, output_dir: str = None, methods: List[str] = None) -> pd.DataFrame:
    """Full run: apply methods, save individual exports, merge and dedup."""
    results = run_methods(pdf_path, methods)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        for name, df in results.items():
            df.to_excel(os.path.join(output_dir, f"{name}.xlsx"), index=False)

    merged = merge_results(results)
    cleaned = dedup_dataframe(merged)

    if output_dir:
        merged.to_excel(os.path.join(output_dir, "merged_raw.xlsx"), index=False)
        cleaned.to_excel(os.path.join(output_dir, "merged.xlsx"), index=False)
        print(f"[pipeline] merged files written to {output_dir}")

    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser(description="Run extraction pipeline on a PDF")
    parser.add_argument("pdf", help="path to the PDF file")
    parser.add_argument("--output-dir", help="directory to write results to")
    parser.add_argument(
        "--methods",
        help="comma-separated list of methods to run (defaults to all)",
    )
    args = parser.parse_args()

    methods = args.methods.split(",") if args.methods else None
    result = pipeline(args.pdf, args.output_dir, methods)
    print("Final dataset contains", len(result), "rows")


if __name__ == "__main__":
    main()
