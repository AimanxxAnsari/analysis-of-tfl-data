"""Shared helpers for the TfL network and passenger-flow notebooks.

Post-submission corrections (see README "Corrections after submission"):

* Both networks are built with the same interchange rule: one node per named
  station complex (e.g. Bank and Monument, Edgware Road, Hammersmith are one
  node in both years; DLR platforms are merged into their station).
* 2014 node labels are mapped onto the 2024 display names so the two years can
  be compared directly.
* All centrality measures use the same settings in both years, and the
  "overall" ranking uses one documented method (dissertation Eq. 4.2: number
  of top-5 appearances, ties broken by summed rank points).
* Passenger counts use London Underground station entry/exit gate counts only,
  which is the one measure published on the same basis for 2017-2022.
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

import networkx as nx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MULTIPLEX = ROOT / "References" / "London_Multiplex_Transport" / "Dataset"
RESULTS = ROOT / "results"

MEASURES = ["degree", "betweenness", "closeness", "katz", "pagerank"]
KATZ_ALPHA = 0.1  # must be < 1/lambda_max (0.26 for 2014, 0.23 for 2024)
TOP_N = 5

# --------------------------------------------------------------------------
# Station-name harmonisation
# --------------------------------------------------------------------------

# 2014 multiplex labels that are split per line, or named differently from
# the 2024 dataset. Everything else is matched automatically by `_key`.
HARMONISE_2014 = {
    "bank": "Bank and Monument",
    "monument": "Bank and Monument",
    "edgwareroad(bakerlooline)": "Edgware Road",
    "edgwareroad(circleline)": "Edgware Road",
    "edgwareroad(districtline)": "Edgware Road",
    "hammersmith(dist&piccline)": "Hammersmith",
    "hammersmith(h&cline)": "Hammersmith",
    "paddington(h&cline)": "Paddington",
    "kensington(olympia)": "Kensington",
    "cuttysarkformaritimegreenwich": "Cutty Sark",
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().replace("&", "and"))


def harmonise_2024_name(name: str) -> str:
    """Merge separately-listed DLR platforms into their station
    (e.g. 'Canary Wharf DLR' -> 'Canary Wharf'), matching the 2014 data."""
    return re.sub(r" DLR$", "", name)


# --------------------------------------------------------------------------
# Network loading
# --------------------------------------------------------------------------

def load_edges_2024(exclude_lines=()) -> pd.DataFrame:
    edges = pd.read_csv(DATA / "2022-tfl-edges.csv")
    edges = edges[~edges["Line"].isin(exclude_lines)].copy()
    for col in ("From Station", "To Station"):
        edges[col] = edges[col].map(harmonise_2024_name)
    return edges


def load_edges_2014() -> pd.DataFrame:
    edges = pd.read_csv(MULTIPLEX / "london_transport_raw.edges", sep=" ",
                        names=["Line", "From Station", "To Station"])
    names_2024 = {_key(n): n for n in pd.unique(
        load_edges_2024()[["From Station", "To Station"]].values.ravel())}

    def to_display(label):
        if label in HARMONISE_2014:
            return HARMONISE_2014[label]
        return names_2024.get(_key(label), label)

    for col in ("From Station", "To Station"):
        edges[col] = edges[col].map(to_display)
    return edges


def build_graph(edges: pd.DataFrame) -> nx.Graph:
    """Undirected simple graph; parallel edges from several lines collapse to one."""
    G = nx.Graph()
    for line, a, b in edges[["Line", "From Station", "To Station"]].itertuples(index=False):
        if a == b:  # can appear after merging interchange platforms
            continue
        if G.has_edge(a, b):
            G[a][b]["lines"].add(line)
        else:
            G.add_edge(a, b, lines={line})
    return G


def positions_2014() -> dict:
    """Geographic positions for the harmonised 2014 node names."""
    nodes = pd.read_csv(MULTIPLEX / "london_transport_nodes.txt", sep=" ")
    names_2024 = {_key(n): n for n in pd.unique(
        load_edges_2024()[["From Station", "To Station"]].values.ravel())}
    pos = {}
    for label, lon, lat in nodes[["nodeLabel", "nodeLong", "nodeLat"]].itertuples(index=False):
        name = HARMONISE_2014.get(label, names_2024.get(_key(label), label))
        pos.setdefault(name, (lon, lat))  # first platform's position for merged nodes
    return pos


# --------------------------------------------------------------------------
# Centrality
# --------------------------------------------------------------------------

def compute_centralities(G: nx.Graph) -> pd.DataFrame:
    """All five measures for every node, with the same settings for every graph.

    Closeness uses NetworkX's Wasserman-Faust scaling, so it stays comparable
    when a graph has more than one connected component (the 2024 tram network
    is not connected to the rest of the graph)."""
    df = pd.DataFrame({
        "degree": nx.degree_centrality(G),
        "betweenness": nx.betweenness_centrality(G),
        "closeness": nx.closeness_centrality(G, wf_improved=True),
        "katz": nx.katz_centrality(G, alpha=KATZ_ALPHA, beta=1.0, max_iter=5000),
        "pagerank": nx.pagerank(G),
    })
    df["raw_degree"] = pd.Series(dict(G.degree()))
    df.index.name = "station"
    return df


def top_n(cent: pd.DataFrame, measure: str, n: int = TOP_N) -> pd.DataFrame:
    """Top-n stations for one measure, sorted by value then name (deterministic).

    `tied_at_cutoff` lists how many other stations share the n-th value, i.e.
    whether the top-n list depends on an arbitrary tie-break."""
    s = cent[measure].round(12)  # avoid float noise creating false non-ties
    ordered = s.loc[sorted(s.index, key=lambda k: (-s[k], k))]
    top = ordered.head(n)
    cutoff = top.iloc[-1]
    n_equal = int((s == cutoff).sum())
    n_in_top = int((top == cutoff).sum())
    out = top.rename("value").reset_index()
    out.insert(0, "rank", range(1, len(out) + 1))
    out["tied_at_cutoff"] = n_equal - n_in_top  # stations left out with the same value
    return out


def combined_ranking(cent: pd.DataFrame, measures=MEASURES, n: int = TOP_N) -> pd.DataFrame:
    """Dissertation Eq. 4.2: S(v) = number of top-n lists containing v.

    Ties in S(v) are broken by summed rank points (n for 1st ... 1 for n-th),
    then by mean percentile rank across all nodes, so the result is fully
    determined by the data."""
    rows = {}
    for m in measures:
        for _, r in top_n(cent, m, n).iterrows():
            d = rows.setdefault(r["station"], {"appearances": 0, "rank_points": 0, "measures": []})
            d["appearances"] += 1
            d["rank_points"] += n + 1 - r["rank"]
            d["measures"].append(m)
    pct = cent[list(measures)].rank(pct=True).mean(axis=1)
    out = pd.DataFrame.from_dict(rows, orient="index")
    out["mean_percentile"] = pct.reindex(out.index).round(4)
    out["measures"] = out["measures"].map(", ".join)
    out = out.sort_values(["appearances", "rank_points", "mean_percentile"], ascending=False)
    out.index.name = "station"
    out = out.reset_index()
    out.insert(0, "rank", range(1, len(out) + 1))
    return out


def top_table(cent: pd.DataFrame, label: str, measures=MEASURES, n: int = TOP_N) -> pd.DataFrame:
    """One row per measure (plus 'overall') with the ordered top-n stations."""
    rows = []
    for m in measures:
        t = top_n(cent, m, n)
        rows.append({"network": label, "measure": m,
                     "top_stations": "; ".join(t["station"]),
                     "stations_tied_at_cutoff": int(t["tied_at_cutoff"].iloc[-1])})
    comb = combined_ranking(cent, measures, n)
    rows.append({"network": label, "measure": "overall",
                 "top_stations": "; ".join(comb["station"].head(n)),
                 "stations_tied_at_cutoff": None})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Passenger counts
# --------------------------------------------------------------------------

ANNUAL_SHEETS = {2017: "Annualised", 2018: "Annualised", 2019: "Annualised",
                 2020: "Annualised", 2021: "Annualised", 2022: "AC22"}
ANNUAL_YEARS = list(range(2017, 2026))
TIME_PERIODS = ["Early", "AM Peak", "Inter Peak", "PM Peak", "Evening", "Late"]


def load_annual_raw(year: int) -> pd.DataFrame:
    path = DATA / "yearly-counts-tube" / f"AnnualisedEntryExit_{year}.xlsx"
    if year >= 2023:
        # 2023+ files: header rows move between years, but the columns do not:
        # A-F = Mode, MNLC, MASC, Station, Coverage, Source; S = Annualised En/Ex.
        raw = pd.read_excel(path, sheet_name=0, header=None)
        raw = raw[raw[0].isin(["LU", "LO", "DLR", "EZL", "TfLRail", "TRM"])]
        return pd.DataFrame({
            "Mode": raw[0], "NLC": raw[1], "Station": raw[3].astype(str),
            "Coverage": raw[4].astype(str),
            "Entry/Exit": pd.to_numeric(raw[18], errors="coerce").fillna(0),
        })
    df = pd.read_excel(path, sheet_name=ANNUAL_SHEETS[year], skiprows=6)
    # the annual total is the last 'en/ex' column in every year's file
    ee_col = [c for c in df.columns if str(c).lower().startswith("en/ex")][-1]
    df = df.rename(columns={"MNLC": "NLC", "MASC": "ASC"})
    df["Entry/Exit"] = pd.to_numeric(df[ee_col], errors="coerce").fillna(0)
    df["Coverage"] = df["Coverage"].astype(str)
    return df[["Mode", "NLC", "Station", "Coverage", "Entry/Exit"]]


def load_annual_lu(year: int) -> pd.DataFrame:
    """Annual London Underground station entry/exit gate counts for one year.

    This is the only series TfL publishes on the same basis for every year
    2017-2022. Boarding/alighting counts for LO, DLR, TfL Rail/Elizabeth line
    are excluded: they count interchanges as well as station entries, and
    from 2022 those passengers are already inside the LU gate count at shared
    stations ('---see LU---' rows)."""
    df = load_annual_raw(year)
    lu = df[(df["Mode"] == "LU") & df["Coverage"].str.contains("entry", case=False)]
    lu = lu.assign(Station=lu["Station"]
                   .str.replace(r" (LU|TfL)$", "", regex=True)
                   # 2024+ files write "St Paul's"; earlier years and the network use "St. Paul's"
                   .str.replace(r"\bSt (?=[A-Z])", "St. ", regex=True))
    out = lu.groupby("Station", as_index=False)["Entry/Exit"].sum()
    out["year"] = year
    return out


def load_hourly_lu(year: int) -> pd.DataFrame:
    df = pd.read_excel(DATA / "yearly-counts-tube" / f"ByQhrEntryExit_{year}.xlsx",
                       sheet_name="ByQhr", skiprows=6).iloc[:, :15]
    df.columns = [str(c).strip() for c in df.columns]
    df = df[(df["Mode"] == "LU") & df["Coverage"].astype(str).str.contains("entry", case=False)]
    for c in ["Total"] + TIME_PERIODS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    # 2017 publishes one Mon-Fri profile ('MTF'); 2018+ split Mon-Thu ('MTT') and Fri.
    df["day_type"] = df["day"].map({"MTF": "Weekday", "MTT": "Weekday",
                                    "SAT": "Saturday", "SUN": "Sunday", "FRI": "Friday"})
    df["year"] = year
    return df


# --------------------------------------------------------------------------
# Linking counts to the network (extended analysis)
# --------------------------------------------------------------------------

# Count files keep these station pairs separate; the network merges each pair.
COUNT_TO_NETWORK = {
    "Edgware Road (Bak)": "Edgware Road", "Edgware Road (DIS)": "Edgware Road",
    "Hammersmith (DIS)": "Hammersmith", "Hammersmith (H&C)": "Hammersmith",
}


@functools.lru_cache(maxsize=1)
def _node_lookup() -> dict:
    return {_key(n.replace("St.", "St")): n for n in pd.unique(
        load_edges_2024()[["From Station", "To Station"]].values.ravel())}


def network_name(count_station: str) -> str:
    """Map an LU count-file station name onto the 2024 network's node name."""
    if count_station in COUNT_TO_NETWORK:
        return COUNT_TO_NETWORK[count_station]
    return _node_lookup().get(_key(count_station.replace("St.", "St")), count_station)


def positions_2024() -> dict:
    """{station: (lon, lat)} from TfL's official locations (mean over a station's line rows)."""
    st = pd.read_csv(DATA / "tfl_stations_2022_with_coordinates.csv")
    st["Station Name"] = st["Station Name"].map(harmonise_2024_name)
    mean = st.groupby("Station Name")[["Longitude", "Latitude"]].mean()
    return {s: (r.Longitude, r.Latitude) for s, r in mean.iterrows()}


def lu_counts_panel(years=ANNUAL_YEARS) -> pd.DataFrame:
    """Station x year table of LU entry/exit counts, keyed by network node name."""
    lu = pd.concat([load_annual_lu(y) for y in years])
    lu["station"] = lu["Station"].map(network_name)
    return lu.groupby(["station", "year"])["Entry/Exit"].sum().unstack()
