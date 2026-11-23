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
# Network Demand (daily journeys, daily station footfall)
# --------------------------------------------------------------------------

def _network_demand(prefix: str, keys: list[str]) -> pd.DataFrame:
    """Concatenate TfL's overlapping yearly files; for each key, keep the row from the
    most recently published file (TfL revises a few recent values between releases)."""
    man = pd.read_csv(DATA / "bus" / "manifest.csv")
    man = man[(man["dataset"] == "network-demand")
              & man["raw_path"].str.contains(f"/{prefix}_")].sort_values("tfl_last_modified")
    frames = []
    for _, r in man.iterrows():
        df = pd.read_csv(T.ROOT / r["raw_path"], encoding="utf-8-sig")
        df.columns = [c.lower() for c in df.columns]
        df["published"] = r["tfl_last_modified"]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["traveldate"].astype(str), format="%Y%m%d")
    df = df.sort_values("published").drop_duplicates(keys, keep="last")
    return df.drop(columns=["traveldate", "published"]).sort_values(keys).reset_index(drop=True)


def load_journeys() -> pd.DataFrame:
    """Daily total Tube and bus journeys, 2019 onwards (indexed by date)."""
    df = _network_demand("journeys", ["date"])
    df = df.rename(columns={"tubejourneycount": "tube", "busjourneycount": "bus"})
    return df.set_index("date")[["dayofweek", "tube", "bus"]]


def load_footfall() -> pd.DataFrame:
    """Daily entry and exit taps per rail station, 2019 onwards.

    TfL renamed three Elizabeth line stations on 28 May 2025 ('Canary Wharf EL' ->
    'Canary Wharf Elizabeth Line'); both names are mapped to '... EL'."""
    df = _network_demand("stationfootfall", ["date", "station"])
    df["station"] = df["station"].str.replace(r" Elizabeth Line$", " EL", regex=True)
    df = df.rename(columns={"entrytapcount": "entries", "exittapcount": "exits"})
    df["entries_exits"] = df["entries"] + df["exits"]
    return df[["date", "dayofweek", "station", "entries", "exits", "entries_exits"]]


def atypical_days(journeys: pd.DataFrame | None = None) -> pd.DataFrame:
    """Classify days whose Tube or bus journeys are far below normal.

    Normal = rolling 29-day median of the same day type (weekday / weekend). Classes:
    'Tube strike' (Tube < 50% of normal, buses >= 90%), 'Tube partly disrupted'
    (Tube < 75%, buses >= 90%), 'bus strike' / 'buses partly disrupted' (the reverse),
    'holiday / other' (either below 75% otherwise: bank holidays, snow, ...) and
    'Christmas / New Year' (24 Dec - 1 Jan). Returns one row per atypical day."""
    j = load_journeys() if journeys is None else journeys
    weekend = j.index.dayofweek >= 5
    norm = pd.concat([j[weekend == w][["tube", "bus"]].rolling(29, center=True, min_periods=8).median()
                      for w in (False, True)]).sort_index()
    ratio = j[["tube", "bus"]] / norm
    christmas = (j.index.month == 12) & (j.index.day >= 24) | (j.index.month == 1) & (j.index.day == 1)
    kind = pd.Series(None, index=j.index, dtype=object)
    kind[(ratio.tube < .5) & (ratio.bus >= .9)] = "Tube strike"
    kind[kind.isna() & (ratio.tube < .75) & (ratio.bus >= .9)] = "Tube partly disrupted"
    kind[(ratio.bus < .5) & (ratio.tube >= .9)] = "bus strike"
    kind[kind.isna() & (ratio.bus < .75) & (ratio.tube >= .9)] = "buses partly disrupted"
    kind[kind.isna() & ((ratio.tube < .75) | (ratio.bus < .75))] = "holiday / other"
    kind[christmas] = "Christmas / New Year"
    kind = kind.dropna()
    return j.loc[kind.index, ["dayofweek", "tube", "bus"]].assign(
        kind=kind, tube_vs_normal=(100 * ratio.tube[kind.index]).round(0),
        bus_vs_normal=(100 * ratio.bus[kind.index]).round(0))


# Footfall series that are one station complex in the rail network
FOOTFALL_TO_NETWORK = {
    "Bank": "Bank and Monument", "Monument": "Bank and Monument",
    "Edgware Road B": "Edgware Road", "Edgware Road C&H": "Edgware Road",
    "Hammersmith C&H": "Hammersmith", "Hammersmith D&P": "Hammersmith",
    "Kensington Olympia": "Kensington", "Watford Met": "Watford",
}
MODE_SUFFIX = r" (?:DLR|LO|NR|EL|SR|TfL Rail/HEx)$"


def footfall_panel(underground_only: bool = True, weekdays_only: bool = True,
                   drop_atypical: bool = True) -> pd.DataFrame:
    """Date x network-station table of daily entries + exits.

    With underground_only, series with a mode suffix ('Canary Wharf DLR', 'Liverpool St NR',
    'Paddington EL', ...) are left out and only stations on an Underground line are kept,
    matching the LU gate counts of the annual analysis. Split complexes (Bank / Monument,
    the two Edgware Road and Hammersmith stations) are summed into one network node."""
    f = load_footfall()
    if weekdays_only:
        f = f[f["date"].dt.dayofweek < 5]
    if drop_atypical:
        f = f[~f["date"].isin(atypical_days().index)]
    if underground_only:
        f = f[~f["station"].str.contains(MODE_SUFFIX, regex=True)]
    f = f.assign(node=f["station"].map(lambda s: FOOTFALL_TO_NETWORK.get(s, T.network_name(s))))
    panel = f.pivot_table(index="date", columns="node", values="entries_exits", aggfunc="sum")
    if underground_only:
        rail = rail_stations()
        lu_lines = {"Bakerloo", "Central", "District", "H&C and Circle", "Jubilee", "Metropolitan",
                    "Northern", "Piccadilly", "Victoria", "Waterloo & City"}
        lu = [s for s in rail.index if lu_lines & set(rail.loc[s, "lines"].split("; "))]
        panel = panel[[c for c in panel.columns if c in lu]]
    return panel


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


# --------------------------------------------------------------------------
# Combined bus + rail network
# --------------------------------------------------------------------------

# Travel-time assumptions for edge weights (minutes). Sensitivity is tested in the notebook.
BUS_KMH, BUS_DETOUR = 15.0, 1.3      # average London bus speed incl. stops; road vs straight line
RAIL_KMH = 30.0                       # average TfL rail speed incl. stops
WALK_KMH, WALK_DETOUR = 4.8, 1.3
CHANGE_MIN = 5.0                      # wait / interchange penalty when changing mode


def bus_edges(year: int = 2025, day_type: str = "Weekday") -> pd.DataFrame:
    """Consecutive stop-area pairs on every BUSTO route-direction, with the routes serving them.

    Nodes are TfL stop areas (stops on both sides of the road). Virtual stops (timing
    points) and stops missing from the bus-stops feed are skipped, joining their
    neighbours; route-directions that mix two variants in one sequence are left out."""
    st = load_stops()
    con = busto_con()
    seq = con.execute(f"""SELECT DISTINCT route, direction, stopsequence, stopcode FROM qhr
                          WHERE year = {year} AND day_type = '{day_type}'""").df()
    seq = seq[seq["stopcode"].isin(st.index)].join(st[["stop_area", "virtual"]], on="stopcode")
    seq = seq[~seq["virtual"]].sort_values(["route", "direction", "stopsequence"])
    mixed = seq.groupby(["route", "direction"])["stopsequence"].transform(lambda s: s.duplicated().any())
    seq = seq[~mixed.astype(bool)]
    seq["node"] = "bus:" + seq["stop_area"]
    nxt = seq.groupby(["route", "direction"])["node"].shift(-1)
    e = pd.DataFrame({"a": seq["node"], "b": nxt, "route": seq["route"]}).dropna()
    e = e[e["a"] != e["b"]]
    e[["a", "b"]] = np.sort(e[["a", "b"]].values, axis=1)          # undirected
    return e.groupby(["a", "b"])["route"].agg(lambda s: frozenset(s)).rename("routes").reset_index()


def stop_area_positions() -> pd.DataFrame:
    st = load_stops()
    g = st.assign(node="bus:" + st["stop_area"]).groupby("node")
    return g.agg(lat=("lat", "mean"), lon=("lon", "mean"),
                 name=("stop_name", lambda s: s.mode().iloc[0]))


def build_bus_rail_graph(year: int = 2025, walk_m: float = WALK_M, include_bus: bool = True,
                         include_rail: bool = True, exclude_lines=("London Trams",),
                         bus_kmh: float = BUS_KMH, rail_kmh: float = RAIL_KMH,
                         change_min: float = CHANGE_MIN):
    """Undirected graph of bus stop areas ('bus:<area>') and TfL rail stations ('rail:<name>').

    Edge attribute `minutes` is the estimated travel time: bus and rail edges from
    straight-line distance and average speeds, walking links between a stop area and a
    station within walk_m, plus a change penalty. Edge attribute `mode` is bus / rail / walk;
    bus edges carry the set of `routes` serving them. Nodes carry lat, lon, name, mode."""
    import networkx as nx
    G = nx.Graph()
    pos = stop_area_positions()
    rail = rail_stations(include_trams="London Trams" not in exclude_lines)
    if include_bus:
        for a, b, routes in bus_edges(year).itertuples(index=False):
            d = haversine_m(pos.at[a, "lat"], pos.at[a, "lon"], pos.at[b, "lat"], pos.at[b, "lon"])
            G.add_edge(a, b, mode="bus", routes=routes,
                       minutes=max(BUS_DETOUR * d / 1000 / bus_kmh * 60, 0.5))
    if include_rail:
        R = T.build_graph(T.load_edges_2024(exclude_lines=list(exclude_lines)))
        for a, b in R.edges:
            d = haversine_m(rail.at[a, "lat"], rail.at[a, "lon"], rail.at[b, "lat"], rail.at[b, "lon"])
            G.add_edge("rail:" + a, "rail:" + b, mode="rail", minutes=max(d / 1000 / rail_kmh * 60, 1.0))
    if include_bus and include_rail:
        bn = [n for n in G if n.startswith("bus:")]
        P = pos.loc[bn]
        D = haversine_m(P["lat"].values[:, None], P["lon"].values[:, None],
                        rail["lat"].values[None, :], rail["lon"].values[None, :])
        i, k = np.nonzero(D <= walk_m)
        for a, s, d in zip(np.array(bn)[i], rail.index[k], D[i, k]):
            G.add_edge(a, "rail:" + s, mode="walk",
                       minutes=WALK_DETOUR * d / 1000 / WALK_KMH * 60 + change_min)
    for n in G:
        if n.startswith("bus:"):
            G.nodes[n].update(mode="bus", lat=pos.at[n, "lat"], lon=pos.at[n, "lon"], name=pos.at[n, "name"])
        else:
            s = n[5:]
            G.nodes[n].update(mode="rail", lat=rail.at[s, "lat"], lon=rail.at[s, "lon"], name=s)
    return G


def efficiency_minutes(G, sources=None, weight: str = "minutes") -> float:
    """Mean of 1 / travel time over ordered pairs (source in `sources`, any target).
    Unreachable pairs count as 0, so the measure stays meaningful when the graph splits."""
    import networkx as nx
    from scipy.sparse.csgraph import dijkstra
    nodes = list(G)
    if len(nodes) < 2:
        return 0.0
    idx = {n: i for i, n in enumerate(nodes)}
    A = nx.to_scipy_sparse_array(G, nodelist=nodes, weight=weight, format="csr")
    src = np.arange(len(nodes)) if sources is None else np.array([idx[s] for s in sources if s in idx])
    total = 0.0
    for chunk in np.array_split(src, max(1, len(src) // 500)):
        D = dijkstra(A, directed=False, indices=chunk)
        D[D == 0] = np.inf
        total += (1.0 / D).sum()
    return total / (len(src) * (len(nodes) - 1))
