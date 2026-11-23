"""Shared helpers for the TfL bus analysis.

Data is downloaded by data-prep/download_tfl_bus.py (see data/bus/README.md):

* BUSTO demand (Parquet) is queried in place with DuckDB: `busto_con()` returns a
  connection with two views, `qhr` (total demand by route, direction, stop and
  quarter hour; all years and day types) and `maxhr` (max demand hour by timeband).
  BUSTO's `year` column is the first year of the financial year (2025 = 2025-26).
* Bus stops come from TfL's bus-stops feed, keyed by the LBSL stop code that BUSTO
  uses (`stopcode`), with coordinates converted from British National Grid.
* Rail stations are the nodes of the 2024 rail network used in the rail analysis
  (tfl_analysis), so bus-rail links join directly onto that network.
"""

from __future__ import annotations

import functools

import duckdb
import numpy as np
import pandas as pd

import tfl_analysis as T

DATA = T.ROOT / "data"
RAW = DATA / "raw"
PROCESSED = DATA / "processed"
RESULTS = T.RESULTS / "bus"

BUSTO_YEARS = {2023: "2023-2024", 2024: "2024-2025", 2025: "2025-2026"}
DAY_TYPES = ["Weekday", "Saturday", "Sunday"]
WALK_RADII_M = [200, 400, 800]   # sensitivity range for "bus stop serves a rail station"
WALK_M = 400                      # default: about a 5-minute walk


# --------------------------------------------------------------------------
# Coordinates
# --------------------------------------------------------------------------

def osgb_to_wgs84(easting, northing):
    """British National Grid (OSGB36) easting/northing -> WGS84 (lat, lon) in degrees.

    Ordnance Survey's inverse transverse Mercator projection followed by a 7-parameter
    Helmert transformation (OS 'A guide to coordinate systems in Great Britain').
    Accurate to about 5 m, which is ample for walking-distance links; checked in the
    routes-and-stops notebook against TfL's own WGS84 stop coordinates."""
    E = np.asarray(easting, dtype=float)
    N = np.asarray(northing, dtype=float)
    a, b = 6377563.396, 6356256.909                     # Airy 1830
    F0, lat0, lon0 = 0.9996012717, np.radians(49), np.radians(-2)
    N0, E0 = -100000.0, 400000.0
    e2 = 1 - b**2 / a**2
    n = (a - b) / (a + b)

    lat, M = np.full_like(N, lat0), np.zeros_like(N)
    for _ in range(50):
        lat = (N - N0 - M) / (a * F0) + lat
        dl, sl = lat - lat0, lat + lat0
        M = b * F0 * ((1 + n + 1.25 * n**2 + 1.25 * n**3) * dl
                      - (3 * n + 3 * n**2 + 21 / 8 * n**3) * np.sin(dl) * np.cos(sl)
                      + (15 / 8 * n**2 + 15 / 8 * n**3) * np.sin(2 * dl) * np.cos(2 * sl)
                      - 35 / 24 * n**3 * np.sin(3 * dl) * np.cos(3 * sl))
        if np.all(np.abs(N - N0 - M) < 1e-5):
            break

    s, c, t = np.sin(lat), np.cos(lat), np.tan(lat)
    nu = a * F0 / np.sqrt(1 - e2 * s**2)
    rho = a * F0 * (1 - e2) / (1 - e2 * s**2) ** 1.5
    eta2 = nu / rho - 1
    VII = t / (2 * rho * nu)
    VIII = t / (24 * rho * nu**3) * (5 + 3 * t**2 + eta2 - 9 * t**2 * eta2)
    IX = t / (720 * rho * nu**5) * (61 + 90 * t**2 + 45 * t**4)
    X = 1 / (c * nu)
    XI = 1 / (c * 6 * nu**3) * (nu / rho + 2 * t**2)
    XII = 1 / (c * 120 * nu**5) * (5 + 28 * t**2 + 24 * t**4)
    XIIA = 1 / (c * 5040 * nu**7) * (61 + 662 * t**2 + 1320 * t**4 + 720 * t**6)
    dE = E - E0
    lat = lat - VII * dE**2 + VIII * dE**4 - IX * dE**6
    lon = lon0 + X * dE - XI * dE**3 + XII * dE**5 - XIIA * dE**7

    # OSGB36 geodetic -> cartesian -> Helmert -> GRS80/WGS84 geodetic
    nu = a / np.sqrt(1 - e2 * np.sin(lat) ** 2)
    x = nu * np.cos(lat) * np.cos(lon)
    y = nu * np.cos(lat) * np.sin(lon)
    z = (1 - e2) * nu * np.sin(lat)
    tx, ty, tz, sc = 446.448, -125.157, 542.060, -20.4894e-6
    rx, ry, rz = (np.radians(v / 3600) for v in (0.1502, 0.2470, 0.8421))
    x2 = tx + (1 + sc) * x - rz * y + ry * z
    y2 = ty + rz * x + (1 + sc) * y - rx * z
    z2 = tz - ry * x + rx * y + (1 + sc) * z

    a2, b2 = 6378137.0, 6356752.3141                     # GRS80
    e2w = 1 - b2**2 / a2**2
    p = np.hypot(x2, y2)
    lat = np.arctan2(z2, p * (1 - e2w))
    for _ in range(10):
        nu = a2 / np.sqrt(1 - e2w * np.sin(lat) ** 2)
        lat = np.arctan2(z2 + e2w * nu * np.sin(lat), p)
    return np.degrees(lat), np.degrees(np.arctan2(y2, x2))


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres; inputs broadcast (e.g. column vs row vectors)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    h = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000 * np.arcsin(np.sqrt(h))


# --------------------------------------------------------------------------
# Bus stops and routes
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def load_stops() -> pd.DataFrame:
    """TfL bus-stops feed: one row per stop, keyed by LBSL code (= BUSTO `stopcode`).

    `virtual` stops are timing points rather than places where passengers board."""
    st = pd.read_csv(RAW / "bus-feeds" / "bus-stops.csv", dtype=str)
    st = st.rename(columns={"Stop_Code_LBSL": "stopcode", "Bus_Stop_Code": "sms_code",
                            "Naptan_Atco": "naptan_id", "Stop_Name": "stop_name",
                            "Location_Easting": "easting", "Location_Northing": "northing",
                            "Heading": "heading", "Stop_Area": "stop_area",
                            "Virtual_Bus_Stop": "virtual"})
    st[["easting", "northing"]] = st[["easting", "northing"]].astype(float)
    st["virtual"] = st["virtual"] == "1"
    st["lat"], st["lon"] = osgb_to_wgs84(st["easting"], st["northing"])
    return st.set_index("stopcode")


def load_api_routes() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "bus-routes" / "routes.csv", dtype={"route_id": str})


def load_api_sequences() -> pd.DataFrame:
    """Current route stop sequences from the Unified API (snapshot on download date)."""
    return pd.read_csv(PROCESSED / "bus-routes" / "route_stop_sequences.csv",
                       dtype={"route_id": str, "branch_id": str})


def load_api_stops() -> pd.DataFrame:
    return pd.read_csv(PROCESSED / "bus-routes" / "stops.csv").set_index("naptan_id")


def load_feed_sequences() -> pd.DataFrame:
    """TfL bus-sequences feed (Run 1/2 = direction), keyed by LBSL stop code."""
    sq = pd.read_csv(RAW / "bus-feeds" / "bus-sequences.csv", dtype=str)
    sq = sq.rename(columns={"Route": "route", "Run": "direction", "Sequence": "sequence",
                            "Stop_Code_LBSL": "stopcode", "Naptan_Atco": "naptan_id",
                            "Stop_Name": "stop_name", "Virtual_Bus_Stop": "virtual"})
    sq[["direction", "sequence"]] = sq[["direction", "sequence"]].astype(int)
    sq["virtual"] = sq["virtual"] == "1"
    return sq[["route", "direction", "sequence", "stopcode", "naptan_id", "stop_name", "virtual"]]


def route_type(route: str) -> str:
    """Rough route class from the route name (TfL numbering conventions)."""
    r = str(route).upper()
    if r.startswith("N"):
        return "night"
    if r.isdigit() and 600 <= int(r) <= 699:
        return "school"
    if r.isdigit():
        return "numbered"
    if r.startswith("SL"):
        return "superloop"
    return "letter prefix"


# --------------------------------------------------------------------------
# BUSTO demand
# --------------------------------------------------------------------------

def busto_con() -> duckdb.DuckDBPyConnection:
    """DuckDB connection with views `qhr` and `maxhr` over all BUSTO years.
    Query with e.g. con.execute("SELECT ... FROM qhr WHERE year = 2025").df()."""
    base = PROCESSED / "busto"
    con = duckdb.connect()
    con.execute(f"CREATE VIEW qhr AS SELECT * FROM read_parquet("
                f"'{base}/*/*quarter_hour*.parquet', union_by_name=true)")
    con.execute(f"CREATE VIEW maxhr AS SELECT * FROM read_parquet("
                f"'{base}/*/*max_demand*.parquet', union_by_name=true)")
    return con


# --------------------------------------------------------------------------
# Rail stations and bus-rail links
# --------------------------------------------------------------------------

def rail_stations(include_trams: bool = False) -> pd.DataFrame:
    """Stations of the 2024 rail network (node names as in tfl_analysis), with their
    lines and TfL's official location (mean over a station's line rows).
    Trams are excluded by default, as in the rail analysis. National Rail-only
    stations are not in the network, so 'rail' here means TfL rail."""
    st = pd.read_csv(DATA / "tfl_stations_2022_with_coordinates.csv")
    st["station"] = st["Station Name"].map(T.harmonise_2024_name)
    if not include_trams:
        st = st[st["Line"] != "London Trams"]
    out = st.groupby("station").agg(lat=("Latitude", "mean"), lon=("Longitude", "mean"),
                                    lines=("Line", lambda s: "; ".join(sorted(set(s)))),
                                    n_lines=("Line", "nunique"))
    return out


def nearest_rail(stops: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """For each stop (needs lat/lon): nearest rail station and the distance to it (m)."""
    D = haversine_m(stops["lat"].values[:, None], stops["lon"].values[:, None],
                    stations["lat"].values[None, :], stations["lon"].values[None, :])
    i = D.argmin(axis=1)
    return pd.DataFrame({"nearest_station": stations.index.values[i],
                         "dist_m": D[np.arange(len(i)), i].round(1)}, index=stops.index)


def bus_rail_links(stops: pd.DataFrame, stations: pd.DataFrame,
                   radius_m: float = WALK_M) -> pd.DataFrame:
    """Every (stop, station) pair within radius_m straight-line distance.
    A stop can serve several stations, and a station is served by many stops."""
    D = haversine_m(stops["lat"].values[:, None], stops["lon"].values[:, None],
                    stations["lat"].values[None, :], stations["lon"].values[None, :])
    si, ri = np.nonzero(D <= radius_m)
    return pd.DataFrame({"stopcode": stops.index.values[si],
                         "station": stations.index.values[ri],
                         "dist_m": D[si, ri].round(1)})
