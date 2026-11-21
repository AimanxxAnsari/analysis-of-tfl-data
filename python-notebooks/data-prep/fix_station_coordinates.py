"""Replace the geocoded station coordinates with TfL's official ones.

The coordinates in data/tfl_stations_2022_with_coordinates.csv were originally
geocoded with the Google Maps API by name, and some resolved to the wrong place
(Queensbury -> New York State; several stations -> a generic central-London
point). This script takes every station's location from TfL's own Unified API
(station-level StopPoints, matched by name *and* mode, so an Elizabeth line row
gets the Elizabeth line station and a DLR row the DLR station).

Outputs
  data/tfl-station-stoppoints.csv          compact extract of the TfL API (cached input)
  data/tfl_stations_2022_with_coordinates.csv   coordinates replaced in place
  data/coordinate-fixes.csv                every row's old vs new position and distance moved

Usage (from the repository root):
  python python-notebooks/data-prep/fix_station_coordinates.py            # use cached extract
  python python-notebooks/data-prep/fix_station_coordinates.py --refresh  # re-download from TfL
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
STATIONS = DATA / "tfl_stations_2022_with_coordinates.csv"
EXTRACT = DATA / "tfl-station-stoppoints.csv"
FIXES = DATA / "coordinate-fixes.csv"

API = "https://api.tfl.gov.uk/StopPoint/Mode/{mode}"
MODES = ["tube", "dlr", "overground", "elizabeth-line", "tram"]
STATION_TYPES = {"NaptanMetroStation", "NaptanRailStation"}

# Rows whose name differs from TfL's, or whose name is shared by two TfL stations.
# (line, station name) -> NaPTAN id; a line of None applies to every line.
OVERRIDES = {
    (None, "Bank and Monument"): "940GZZLUBNK",           # Bank Underground (Bank and Monument complex)
    ("DLR", "Bank and Monument"): "940GZZDLBNK",          # Bank DLR
    (None, "Heathrow Terminals 123"): "940GZZLUHRC",      # now 'Heathrow Terminals 2 & 3'
    ("LO East London", "New Cross"): "910GNWCRELL",
    ("LO Watford-Euston", "Euston"): "910GEUSTON",
    ("LO West Anglia", "Liverpool Street"): "910GLIVST",
    ("Bakerloo", "Edgware Road"): "940GZZLUERB",
    (None, "Edgware Road"): "940GZZLUERC",                # Circle / District / H&C station
    ("District", "Hammersmith"): "940GZZLUHSD",
    ("Piccadilly", "Hammersmith"): "940GZZLUHSD",
    (None, "Hammersmith"): "940GZZLUHSC",                 # H&C and Circle station
}


def line_mode(line: str) -> str:
    if line.startswith("LO "):
        return "overground"
    return {"DLR": "dlr", "Elizabeth Line": "elizabeth-line", "London Trams": "tram"}.get(line, "tube")


def key(name: str) -> str:
    name = re.sub(r" (Underground|DLR|Rail|Overground) Station$| Tram Stop$| \(.*?\)", "", name)
    name = re.sub(r" (DLR|Trams)$", "", name)
    return re.sub(r"[^a-z0-9]", "", name.replace("&", "and").replace("'", "").lower())


def download_extract() -> pd.DataFrame:
    rows = []
    for mode in MODES:
        req = urllib.request.Request(API.format(mode=mode), headers={"User-Agent": "python-urllib"})
        with urllib.request.urlopen(req, timeout=180) as r:
            for s in json.load(r)["stopPoints"]:
                if s["stopType"] in STATION_TYPES:
                    rows.append({"mode": mode, "naptan_id": s["naptanId"], "name": s["commonName"],
                                 "lat": round(s["lat"], 6), "lon": round(s["lon"], 6)})
    df = pd.DataFrame(rows).sort_values(["mode", "name", "naptan_id"])
    df.to_csv(EXTRACT, index=False)
    return df


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def main(refresh: bool) -> None:
    tfl = download_extract() if refresh or not EXTRACT.exists() else pd.read_csv(EXTRACT)
    by_id = tfl.drop_duplicates("naptan_id").set_index("naptan_id")
    by_key = tfl.assign(k=tfl["name"].map(key)).drop_duplicates(["k", "mode"]).set_index(["k", "mode"])

    stations = pd.read_csv(STATIONS)
    log = []
    for i, row in stations.iterrows():
        line, name = row["Line"], row["Station Name"]
        nid = OVERRIDES.get((line, name)) or OVERRIDES.get((None, name))
        if nid:
            match = by_id.loc[nid]
        elif (key(name), line_mode(line)) in by_key.index:
            match = by_key.loc[(key(name), line_mode(line))]
            nid = match["naptan_id"]
        else:
            raise SystemExit(f"No TfL station found for {line} / {name}: add it to OVERRIDES")
        moved = haversine_m(row["Latitude"], row["Longitude"], match["lat"], match["lon"])
        log.append({"Line": line, "Station Name": name, "tfl_naptan_id": nid, "tfl_name": match["name"],
                    "old_lat": row["Latitude"], "old_lon": row["Longitude"],
                    "new_lat": match["lat"], "new_lon": match["lon"], "moved_m": round(float(moved))})
        stations.loc[i, ["Latitude", "Longitude"]] = [match["lat"], match["lon"]]

    stations.to_csv(STATIONS, index=False)
    log = pd.DataFrame(log).sort_values("moved_m", ascending=False)
    log.to_csv(FIXES, index=False)

    per_station = log.groupby("Station Name")["moved_m"].max()
    print(f"{len(log)} rows / {per_station.size} stations updated from TfL")
    for threshold in (500, 1000):
        print(f"  stations moved > {threshold} m: {(per_station > threshold).sum()}")


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
