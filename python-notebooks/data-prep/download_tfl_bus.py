"""Download the TfL data for the bus analysis and record where every file came from.

Usage (from the repository root or anywhere):

    python python-notebooks/data-prep/download_tfl_bus.py network-demand
    python python-notebooks/data-prep/download_tfl_bus.py busto [--years 2025-2026 ...]
    python python-notebooks/data-prep/download_tfl_bus.py routes
    python python-notebooks/data-prep/download_tfl_bus.py all

What it does
------------
* network-demand: daily journeys (Tube/bus) and daily station footfall CSVs.
  Raw files are kept in data/raw/network-demand/ (small, ~60 MB in total).
* busto: BUSTO bus demand CSVs (~3.8 GB). Each file is downloaded, checked
  against TfL's MD5 ETag, converted to Parquet in data/processed/busto/, and
  the raw CSV is deleted. At most one raw file is on disk at a time.
* routes: every bus route with its ordered stops and stop coordinates, from the
  TfL Unified API. Written to data/processed/bus-routes/.
* feeds: TfL's bus-stops.csv and bus-sequences.csv, which link BUSTO's LBSL stop
  codes to NaPTAN stop ids and coordinates. Kept in data/raw/bus-feeds/.

Every file is recorded in data/bus/manifest.csv (committed to git) with its
source URL, TfL version (ETag / last-modified), size, SHA-256, download time,
whether the raw file was kept, and where the processed copy is. Anything that
was deleted can be fetched again from `source_url`. Re-running skips files
whose ETag already matches the manifest and whose output still exists.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MANIFEST = ROOT / "data" / "bus" / "manifest.csv"

BUCKET = "https://s3-eu-west-1.amazonaws.com/crowding.data.tfl.gov.uk"
BROWSE = "https://crowding.data.tfl.gov.uk/"
API = "https://api.tfl.gov.uk"
USER_AGENT = "tfl-analysis-research-script/1.0"
S3_NS = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}

MANIFEST_FIELDS = ["dataset", "file", "source_url", "browse_url", "tfl_etag", "tfl_last_modified",
                   "size_bytes", "sha256", "rows", "downloaded_at", "raw_kept", "raw_path",
                   "processed_path"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(p: Path | None) -> str:
    return "" if p is None else str(p.relative_to(ROOT))


def request(url: str, retries: int = 5) -> bytes:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt * 5)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 5)
                continue
            raise


def download(url: str, dest: Path) -> tuple[str, str, int]:
    """Stream url to dest; return (sha256, md5, size)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk); sha.update(chunk); md5.update(chunk); size += len(chunk)
    tmp.replace(dest)
    return sha.hexdigest(), md5.hexdigest(), size


def list_bucket(prefix: str) -> list[dict]:
    """All objects under prefix in the TfL crowding bucket (handles pagination)."""
    out, token = [], None
    while True:
        q = {"list-type": "2", "prefix": prefix}
        if token:
            q["continuation-token"] = token
        root = ET.fromstring(request(f"{BUCKET}/?{urllib.parse.urlencode(q)}"))
        for c in root.findall("s:Contents", S3_NS):
            size = int(c.find("s:Size", S3_NS).text)
            if size:
                out.append({"key": c.find("s:Key", S3_NS).text, "size": size,
                            "etag": c.find("s:ETag", S3_NS).text.strip('"'),
                            "last_modified": c.find("s:LastModified", S3_NS).text})
        if root.find("s:IsTruncated", S3_NS).text != "true":
            return out
        token = root.find("s:NextContinuationToken", S3_NS).text


def object_url(key: str) -> str:
    return f"{BUCKET}/{urllib.parse.quote(key)}"


def browse_url(key: str) -> str:
    return f"{BROWSE}#!{urllib.parse.quote(key.rsplit('/', 1)[0] + '/')}"


def local_name(key: str) -> str:
    """'BUSTO/2023-2024/2023_24 Weekday ... Routes 1-149.csv' -> '2023_24_weekday_..._routes_1-149.csv'
    (TfL file names contain spaces, and some have a space before '.csv')."""
    stem, _, ext = key.rsplit("/", 1)[-1].rpartition(".")
    return re.sub(r"[^a-z0-9-]+", "_", stem.strip().lower()).strip("_") + "." + ext.lower()


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------

def load_manifest() -> dict[str, dict]:
    if not MANIFEST.exists():
        return {}
    with open(MANIFEST, newline="") as f:
        return {r["source_url"]: r for r in csv.DictReader(f)}


def save_manifest(m: dict[str, dict]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(m.values(), key=lambda r: (r["dataset"], r["file"]))
    tmp = MANIFEST.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader(); w.writerows(rows)
    tmp.replace(MANIFEST)


def up_to_date(m: dict, url: str, etag: str) -> bool:
    r = m.get(url)
    if not r or r["tfl_etag"] != etag:
        return False
    path = r["processed_path"] or r["raw_path"]
    return bool(path) and (ROOT / path).exists()


def check_md5(etag: str, md5: str, key: str) -> None:
    # Single-part S3 uploads use the MD5 as ETag; multipart ones contain '-'.
    if "-" not in etag and etag != md5:
        raise RuntimeError(f"checksum mismatch for {key}: ETag {etag}, MD5 {md5}")


# --------------------------------------------------------------------------
# datasets
# --------------------------------------------------------------------------

def fetch_network_demand(m: dict) -> None:
    objects = list_bucket("Network Demand/")
    print(f"Network Demand: {len(objects)} files")
    for o in objects:
        url = object_url(o["key"])
        if up_to_date(m, url, o["etag"]):
            print(f"  skip (up to date) {o['key']}"); continue
        dest = RAW / "network-demand" / local_name(o["key"])
        sha, md5, size = download(url, dest)
        check_md5(o["etag"], md5, o["key"])
        rows = sum(1 for _ in open(dest, "rb")) - 1
        m[url] = {"dataset": "network-demand", "file": o["key"], "source_url": url,
                  "browse_url": browse_url(o["key"]), "tfl_etag": o["etag"],
                  "tfl_last_modified": o["last_modified"], "size_bytes": size, "sha256": sha,
                  "rows": rows, "downloaded_at": now(), "raw_kept": "yes",
                  "raw_path": rel(dest), "processed_path": ""}
        save_manifest(m)
        print(f"  {o['key']}: {size / 1e6:.1f} MB, {rows:,} rows")


def busto_to_parquet(src: Path, dest: Path) -> int:
    """CSV -> Parquet (zstd). Column names are made snake_case ('V/C' -> 'v_c');
    stop codes and route names stay text (stop codes can be alphanumeric, e.g. 'BP1353',
    and route '1' must match route 'N1' / the API's route ids)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    read = (f"read_csv('{src}', header=true, sample_size=-1, "
            f"types={{'STOPCODE': 'VARCHAR', 'ROUTE': 'VARCHAR'}})")
    cols = con.execute(f"DESCRIBE SELECT * FROM {read}").fetchall()
    select = ", ".join(f'"{c[0]}" AS {re.sub(r"[^a-z0-9]+", "_", c[0].lower()).strip("_")}'
                       for c in cols)
    tmp = dest.with_suffix(".parquet.part")
    con.execute(f"COPY (SELECT {select} FROM {read}) TO '{tmp}' (FORMAT parquet, COMPRESSION zstd)")
    rows = con.execute(f"SELECT count(*) FROM read_parquet('{tmp}')").fetchone()[0]
    con.close()
    tmp.replace(dest)
    return rows


def fetch_busto(m: dict, years: list[str] | None, keep_raw: bool) -> None:
    objects = list_bucket("BUSTO/")
    if years:
        objects = [o for o in objects if o["key"].endswith(".pdf") or o["key"].split("/")[1] in years]
    print(f"BUSTO: {len(objects)} files, {sum(o['size'] for o in objects) / 1e9:.2f} GB")
    for i, o in enumerate(objects, 1):
        url = object_url(o["key"])
        if up_to_date(m, url, o["etag"]):
            print(f"  [{i}/{len(objects)}] skip (up to date) {o['key']}"); continue
        parts = o["key"].split("/")
        sub = parts[1] if len(parts) > 2 else ""
        raw = RAW / "busto" / sub / local_name(o["key"])
        t0 = time.time()
        sha, md5, size = download(url, raw)
        check_md5(o["etag"], md5, o["key"])
        row = {"dataset": "busto", "file": o["key"], "source_url": url,
               "browse_url": browse_url(o["key"]), "tfl_etag": o["etag"],
               "tfl_last_modified": o["last_modified"], "size_bytes": size, "sha256": sha,
               "downloaded_at": now()}
        if raw.suffix == ".csv":
            pq = PROCESSED / "busto" / sub / (raw.stem + ".parquet")
            row["rows"] = busto_to_parquet(raw, pq)
            row["processed_path"] = rel(pq)
            if keep_raw:
                row.update(raw_kept="yes", raw_path=rel(raw))
            else:
                raw.unlink()
                row.update(raw_kept="no (deleted after conversion; re-download from source_url)",
                           raw_path="")
            note = f"{row['rows']:,} rows -> {pq.stat().st_size / 1e6:.0f} MB parquet"
        else:  # user guide PDF: small, keep it
            row.update(rows="", raw_kept="yes", raw_path=rel(raw), processed_path="")
            note = "kept"
        m[url] = row
        save_manifest(m)
        print(f"  [{i}/{len(objects)}] {o['key']}: {size / 1e6:.0f} MB, {note} ({time.time() - t0:.0f}s)",
              flush=True)


def fetch_routes(m: dict, delay: float = 0.6) -> None:
    """Bus routes and ordered stop sequences from the TfL Unified API (no key needed;
    requests are spaced out to stay within the anonymous rate limit)."""
    out_dir = PROCESSED / "bus-routes"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = json.loads(request(f"{API}/Line/Mode/bus/Route"))
    print(f"Unified API: {len(lines)} bus routes")
    raw_path = RAW / "bus-routes" / "route_sequences.jsonl.gz"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    routes, seq_rows, stops = [], [], {}
    with gzip.open(raw_path, "wt") as raw:
        for i, line in enumerate(lines, 1):
            routes.append({"route_id": line["id"], "route_name": line["name"],
                           "n_route_sections": len(line.get("routeSections", []))})
            for direction in ("outbound", "inbound"):
                try:
                    data = json.loads(request(f"{API}/Line/{line['id']}/Route/Sequence/{direction}"))
                except urllib.error.HTTPError as e:
                    if e.code == 404:  # one-way routes have no inbound sequence
                        print(f"  no {direction} sequence for route {line['id']}")
                        continue
                    raise
                raw.write(json.dumps(data) + "\n")
                for b, branch in enumerate(data.get("stopPointSequences", [])):
                    for s, sp in enumerate(branch.get("stopPoint", []), 1):
                        seq_rows.append({"route_id": line["id"], "direction": direction,
                                         "branch_id": branch.get("branchId", b), "sequence": s,
                                         "naptan_id": sp["id"], "stop_code": sp.get("stopLetter"),
                                         "stop_name": sp["name"]})
                        stops.setdefault(sp["id"], {
                            "naptan_id": sp["id"], "stop_name": sp["name"],
                            "stop_letter": sp.get("stopLetter"), "lat": sp["lat"], "lon": sp["lon"],
                            # stop area grouping the stops on both sides of the road (490G...)
                            "stop_area_id": sp.get("topMostParentId") or sp.get("parentId"),
                        })
                time.sleep(delay)
            if i % 50 == 0:
                print(f"  {i}/{len(lines)} routes", flush=True)

    files = {
        "routes.csv": pd.DataFrame(routes),
        "route_stop_sequences.csv": pd.DataFrame(seq_rows),
        "stops.csv": pd.DataFrame(stops.values()),
    }
    fetched = now()
    for name, df in files.items():
        path = out_dir / name
        df.to_csv(path, index=False)
        url = f"{API}/Line/Mode/bus/Route" if name == "routes.csv" else \
            f"{API}/Line/{{route_id}}/Route/Sequence/{{inbound|outbound}}"
        m[f"{url}#{name}"] = {
            "dataset": "bus-routes-api", "file": name, "source_url": f"{url}#{name}",
            "browse_url": "https://api.tfl.gov.uk/swagger/ui/index.html", "tfl_etag": "",
            "tfl_last_modified": fetched, "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "rows": len(df),
            "downloaded_at": fetched, "raw_kept": "yes (API responses)", "raw_path": rel(raw_path),
            "processed_path": rel(path)}
        print(f"  {name}: {len(df):,} rows")
    save_manifest(m)


FEEDS = "https://tfl.gov.uk/tfl/syndication/feeds"


def fetch_feeds(m: dict) -> None:
    """TfL's bus stop and route-sequence feeds. They carry the LBSL stop codes that
    BUSTO uses (Stop_Code_LBSL), linked to NaPTAN ids and British National Grid
    coordinates. TfL updates them irregularly; the version is recorded in the manifest."""
    for name in ("bus-stops.csv", "bus-sequences.csv"):
        url = f"{FEEDS}/{name}"
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            etag, modified = r.headers.get("ETag", ""), r.headers.get("Last-Modified", "")
        if up_to_date(m, url, etag):
            print(f"  skip (up to date) {name}"); continue
        dest = RAW / "bus-feeds" / name
        sha, _, size = download(url, dest)
        rows = sum(1 for _ in open(dest, "rb")) - 1
        m[url] = {"dataset": "bus-feeds", "file": name, "source_url": url,
                  "browse_url": "https://tfl.gov.uk/info-for/open-data-users/our-open-data",
                  "tfl_etag": etag, "tfl_last_modified": modified, "size_bytes": size,
                  "sha256": sha, "rows": rows, "downloaded_at": now(), "raw_kept": "yes",
                  "raw_path": rel(dest), "processed_path": ""}
        save_manifest(m)
        print(f"  {name}: {size / 1e6:.1f} MB, {rows:,} rows (TfL last modified {modified})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("what", choices=["network-demand", "busto", "routes", "feeds", "all"])
    p.add_argument("--years", nargs="*", help="BUSTO years, e.g. 2025-2026 (default: all)")
    p.add_argument("--keep-raw", action="store_true", help="keep BUSTO CSVs after conversion")
    a = p.parse_args()
    m = load_manifest()
    if a.what in ("network-demand", "all"):
        fetch_network_demand(m)
    if a.what in ("busto", "all"):
        fetch_busto(m, a.years, a.keep_raw)
    if a.what in ("routes", "all"):
        fetch_routes(m)
    if a.what in ("feeds", "all"):
        fetch_feeds(m)
    print(f"manifest: {rel(MANIFEST)} ({len(load_manifest())} files)")


if __name__ == "__main__":
    sys.exit(main())
