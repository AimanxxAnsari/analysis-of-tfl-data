"""Check that the numbers in README.md and docs/*.md match the analysis outputs in results/.

    python tools/check_docs.py            # fails (exit 1) on any mismatch or broken link
    python tools/check_docs.py --verbose  # also lists every claim checked

Each claim recomputes a statement from the CSVs in results/ and requires it to appear in the
named page, word for word (whitespace-insensitive). If an analysis is re-run and a number
changes, the check fails until the write-up is updated. It also checks that every link,
anchor and chart image resolves, and reports numbers in the pages that no claim covers.

Only pandas is needed: the CSVs are committed, so this runs without the raw data.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES, BUS = ROOT / "results", ROOT / "results" / "bus"
PAGES = {"README": ROOT / "README.md", "network": ROOT / "docs/network.md",
         "elizabeth": ROOT / "docs/elizabeth-line.md", "passengers": ROOT / "docs/passengers-and-buses.md",
         "corrections": ROOT / "docs/corrections.md"}

from decimal import ROUND_HALF_UP, Decimal

AMBIGUOUS: list[str] = []   # values stored exactly on a rounding boundary (precision too low)


def fx(x, nd: int, sign: str = "") -> str:
    """Round half up (as a reader would), from the value as stored in the CSV.
    A stored value exactly halfway at the shown precision (e.g. 1.15 shown to 1 dp) may hide
    the true direction, so it is recorded in AMBIGUOUS and reported."""
    d = Decimal(repr(float(x)))
    if -d.as_tuple().exponent == nd + 1 and d.as_tuple().digits[-1] == 5:
        AMBIGUOUS.append(f"{x} shown to {nd} dp")
    q = d.quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    if q == 0:
        q = abs(q)
    return (f"{q:+f}" if sign == "+" else f"{q:f}")


CLAIMS: list[tuple[str, str, str]] = []   # (page, label, expected text)


def claim(page: str, label: str, text: str) -> None:
    CLAIMS.append((page, label, text))


def r0(x) -> str:
    return fx(x, 0)


def r1(x) -> str:
    return fx(x, 1)


def s1(x) -> str:
    """Signed, one decimal: +42.3 / -0.2."""
    return fx(x, 1, "+")


def s0(x) -> str:
    return fx(x, 0, "+")


def short(name: str) -> str:
    return name.replace("King's Cross St. Pancras", "King's Cross")


# ============================================================================
# Network structure (results/centrality_*, betweenness_*, resilience_*)
# ============================================================================
top5 = pd.read_csv(RES / "centrality_top5_comparison.csv").set_index(["network", "measure"])["top_stations"]
lists = top5.str.split("; ")
measures = ["degree", "betweenness", "closeness", "katz", "pagerank", "overall"]
for m in measures:
    cells = [", ".join(short(s) for s in lists[(n, m)])
             for n in ["2014", "2024 comparable (no trams)", "2024 without Elizabeth line"]]
    label = "**Overall**" if m == "overall" else ("PageRank" if m == "pagerank" else m.capitalize())
    claim("network", f"top-5 table: {m}", f"| {label} | {cells[0]} | {cells[1]} | {cells[2]} |")
same_noel = sum(len(set(lists[("2014", m)]) & set(lists[("2024 without Elizabeth line", m)])) for m in measures)
same_el = sum(len(set(lists[("2014", m)]) & set(lists[("2024 comparable (no trams)", m)])) for m in measures)
claim("network", "positions restored", f"restores **{same_noel} of the 30**")
claim("network", "positions matching with line", f"only {same_el} of 30 match")
claim("elizabeth", "positions restored", f"restores **{same_noel} of the 30**")
claim("README", "positions restored", f"{same_noel} of the 30 top-5 centrality positions")

tied = pd.read_csv(RES / "centrality_top5_comparison.csv").query("network == '2014' and measure == 'degree'")
n_tied = int(tied["stations_tied_at_cutoff"].iloc[0]) + 1
words = {6: "six", 5: "five", 7: "seven"}
claim("corrections", "degree ties 2014", f"In 2014, {words.get(n_tied, n_tied)} stations")

br = pd.read_csv(RES / "betweenness_rank_key_stations.csv", index_col=0)
for st in ["Farringdon", "Tottenham Court Road", "Whitechapel", "Liverpool Street", "Bank and Monument", "Green Park"]:
    row = br.loc[st]
    claim("network", f"betweenness rank {st}",
          f"| {st} | {row['2014']} | {row['2024 comparable (no trams)']} | {row['2024 without Elizabeth line']} |")

cr = pd.read_csv(RES / "centrality_vs_ridership.csv").pivot(index="measure", columns="comparison", values="spearman_rho")
for m in ["closeness", "katz", "degree", "betweenness", "pagerank"]:
    a, b = cr.loc[m, "2014 network vs 2019 ridership"], cr.loc[m, "2024 network vs 2023 ridership"]
    label = "PageRank" if m == "pagerank" else m.capitalize()
    claim("network", f"ridership rho {m}", f"| {label} | {fx(a, 2, '')} | {fx(b, 2, '')} |")
lo_c, hi_c = sorted([cr.loc["closeness"].min(), cr.loc["closeness"].max()])
lo_b, hi_b = sorted([cr.loc["betweenness"].min(), cr.loc["betweenness"].max()])
claim("README", "closeness vs betweenness rho", f"(Spearman rho {fx(lo_c, 2, '')}-{fx(hi_c, 2, '')} vs {fx(lo_b, 2, '')}-{fx(hi_b, 2, '')})")
n_rid = pd.read_csv(RES / "centrality_vs_ridership.csv")["n_stations"]
claim("network", "ridership stations", f"({n_rid.min()}-{n_rid.max()} stations)")

rc = pd.read_csv(RES / "resilience_curves.csv").set_index("stations_removed")
t10 = {k: 100 * rc.loc[10, f"{k} | targeted"] for k in ["2014", "2024", "2024 without Elizabeth line"]}
claim("network", "targeted closures 2024", f"keeps **{r0(t10['2024'])}%** of its efficiency, against **{r0(t10['2014'])}%** in 2014 and")
claim("network", "targeted closures no EL", f"**{r0(t10['2024 without Elizabeth line'])}%** for 2024 without the Elizabeth line")
claim("README", "targeted closures", f"keeps {r0(t10['2024'])}% of its efficiency, against "
      f"{r0(min(t10['2014'], t10['2024 without Elizabeth line']))}-{r0(max(t10['2014'], t10['2024 without Elizabeth line']))}% without the line")
rand10 = [100 * (1 - rc.loc[10, f"{k} | random"]) for k in ["2014", "2024", "2024 without Elizabeth line"]]
rand40 = [1 - rc.loc[40, f"{k} | random"] for k in ["2014", "2024", "2024 without Elizabeth line"]]
assert all(8 <= v <= 10 for v in rand10), f"random closures after 10: {rand10} (docs say 'about 9%')"
assert all(0.28 <= v <= 0.38 for v in rand40), f"random closures after 40: {rand40} (docs say 'about a third')"
claim("network", "random closures (range checked)", "about 9% of efficiency lost after 10, and about a third after 40")
ss = pd.read_csv(RES / "resilience_single_station.csv", index_col=0)
claim("network", "Stratford single closure", f"({fx(ss.loc['Stratford', '2024'], 1, '')}% of\n  efficiency lost, up from {fx(ss.loc['Stratford', '2014'], 1, '')}% in 2014)")
worst = ss["2024"].nlargest(5).index.tolist()
assert worst[0] == "Stratford" and set(worst[1:]) == {"Euston", "Camden Town", "Leyton", "Leytonstone"}, worst
claim("network", "most damaging closures (order checked)", "Euston, Camden Town, Leyton and Leytonstone follow")

# ============================================================================
# Passenger counts 2017-2022 (results/lu_*, station_change_*, top5_*)
# ============================================================================
lu = pd.read_csv(RES / "lu_entry_exit_by_station.csv", index_col=0)
tot = lu.sum() / 1e9
claim("passengers", "LU totals", "| LU entries + exits (bn) | " + " | ".join(f"{fx(tot[str(y)], 3, '')}" for y in range(2017, 2023)) + " |")
net_fall = 100 * (1 - lu["2022"].sum() / lu["2017"].sum())
claim("elizabeth", "LU network fall 2017-2022", f"The whole LU network fell {fx(net_fall, 1, '')}% between 2017 and 2022")

t5 = pd.read_csv(RES / "top5_stations_by_year.csv", index_col=0)
strat = t5.loc[1, "2020"]
assert strat.startswith("Stratford"), strat
claim("passengers", "Stratford tops 2020", f"Stratford tops only 2020 ({strat.split('(')[1].rstrip(')')})")
pre = [re.sub(r" \(.*", "", t5.loc[i, "2019"]) for i in range(1, 6)]
assert set(pre) == {"King's Cross St. Pancras", "Victoria", "Waterloo", "Oxford Circus", "London Bridge"}, pre
claim("passengers", "top stations before COVID (set checked)", "King's Cross St. Pancras, Victoria,\nWaterloo, Oxford Circus and London Bridge")

prof = pd.read_csv(RES / "lu_typical_day_profile.csv").query("day_type == 'Weekday'").set_index("year")
share = prof.div(prof.drop(columns="day_type").sum(axis=1), axis=0, level=None) if False else \
    prof.drop(columns="day_type").pipe(lambda p: 100 * p.div(p.sum(axis=1), axis=0))
claim("passengers", "AM peak share", f"AM peak share fell from {fx(share.loc[2019, 'AM Peak'], 1, '')}% (2019) to {fx(share.loc[2021, 'AM Peak'], 1, '')}% (2021)")
claim("passengers", "inter-peak share", f"inter-peak rose from {fx(share.loc[2019, 'Inter Peak'], 1, '')}% to {fx(share.loc[2021, 'Inter Peak'], 1, '')}%")

sc = pd.read_csv(RES / "station_change_2017_2022.csv", index_col=0)


def mm(x):
    return f"{fx(x, 1, '')}M"


def sgn(x, nd=1):
    return fx(x, nd, "+").replace("-", "−")


for st in ["Farringdon", "Tottenham Court Road", "Whitechapel", "Bond Street", "Green Park"]:
    row = sc.loc[st]
    rel = f"{fx(row['change vs network %'], 0, '+')}%".replace("-", "−")
    if st == "Farringdon":
        rel = f"**{rel}** (share {fx(row['share 2017 %'], 2, '')}% → {fx(row['share 2022 %'], 2, '')}%)"
    claim("elizabeth", f"2017-2022 change {st}",
          f"| {st} | {mm(lu.loc[st, '2017'] / 1e6)} | {mm(lu.loc[st, '2022'] / 1e6)} | {sgn(row['raw change %'])}% | {rel} |")
claim("elizabeth", "Bank and Monument 2022", f"({sgn(sc.loc['Bank and Monument', 'change vs network %'], 0)}% relative to the network)")

# ============================================================================
# Elizabeth line, annual counts (results/elizabeth_line_*)
# ============================================================================
ds = pd.read_csv(RES / "elizabeth_line_did_summary.csv", index_col=0)["value"]
eff = float(ds["effect 2019->2023, % (central control)"])
ci = ds["regression 95% CI, %"].split(" to ")
claim("elizabeth", "DiD effect and CI", f"**+{r0(eff)}%** (95% CI +{ci[0]}% to +{ci[1]}%)")
claim("elizabeth", "placebo", f"largest +{r0(float(ds['largest placebo effect, %']))}%, p = {fx(float(ds['placebo p-value']), 4, '')}")
extra = float(ds["extra entries+exits 2023 at the 4 stations (millions)"])
claim("elizabeth", "extra entries (rounded to 10M)", f"about {fx(round(extra, -1), 0, '')} million")
claim("README", "DiD effect", f"about **{r0(eff)}% more**")
claim("README", "extra entries (rounded to 10M)", f"roughly {fx(round(extra, -1), 0, '')} million extra entries + exits a year")
dy = pd.read_csv(RES / "elizabeth_line_did_by_year.csv", index_col=0)["central control (%)"]
claim("elizabeth", "pre-trend 2018", f"(2018: {sgn(dy[2018], 0)}%; 2020-21 within {int(max(abs(dy[2020]), abs(dy[2021])) // 1 + 1)}%)")
claim("elizabeth", "2025 effect", f"holds through 2025 ({s0(dy[2025])}%)")
claim("elizabeth", "2017 effect", f"2017 sits lower ({sgn(dy[2017], 0)}%)")
se = pd.read_csv(RES / "elizabeth_line_station_effects.csv", index_col=0)
for st, it in [("Farringdon", False), ("Tottenham Court Road", False), ("Whitechapel", False), ("Bond Street", False),
               ("Paddington", True), ("Liverpool Street", True), ("Canary Wharf", True)]:
    row = se.loc[st]
    e = f"{fx(row['effect vs control 2019->2023 (%)'], 0, '+')}%".replace("-", "−")
    name = "Canary Wharf (LU station)" if st == "Canary Wharf" else st
    cell = (lambda x: f"*{x}*") if it else (lambda x: x)
    claim("elizabeth", f"station effect {st}",
          f"| {cell(name)} | {mm(row['2019 (M)'])} | {mm(row['2023 (M)'])} | {mm(row['2025 (M)'])} | {cell(e)} |")

# ============================================================================
# Elizabeth line, daily data (results/bus/elizabeth_line_daily_*)
# ============================================================================
de = pd.read_csv(BUS / "elizabeth_line_daily_effects.csv", index_col=0)
c3, bs = de.loc["central three (pooled)"], de.loc["Bond Street"]
rows = [("16 weeks before", "weeks -16 to -1 (before)", False), ("first 4 weeks", "first 4 weeks", True),
        ("weeks 27-52", "weeks 27-52", False), ("year 2", "year 2", False), ("year 3", "year 3", True)]
for lab, col, bold in rows:
    a = f"{fx(c3[col], 1, '')}%" if col.startswith("weeks -16") else f"+{r0(c3[col])}%"
    b = f"{fx(bs[col], 1, '+')}%" if col.startswith("weeks -16") else f"+{r0(bs[col])}%"
    a = f"**{a}**" if bold else a
    claim("elizabeth", f"daily effects {lab}", f"| {lab} | {a} | {b} |")
y3 = {s: de.loc[s, "year 3"] for s in ["Farringdon", "Tottenham Court Road", "Whitechapel", "Bond Street"]}
claim("elizabeth", "year-3 by station", f"Farringdon +{r0(y3['Farringdon'])}%, Tottenham\n  Court Road +{r0(y3['Tottenham Court Road'])}%, "
      f"Whitechapel +{r0(y3['Whitechapel'])}%, Bond Street +{r0(y3['Bond Street'])}%")
claim("elizabeth", "placebo p central", f"p = {fx(c3['first 4 weeks p'], 4, '')}")
claim("elizabeth", "placebo p Bond Street", f"p = {fx(de.loc['Bond Street', 'year 3 p'], 2, '')}, the smallest possible with 48 placebos")
claim("README", "daily first weeks / year 3", f"jumped about {r0(c3['first 4 weeks'])}% in the opening weeks and reached +{r0(c3['year 3'])}% after three")
dr = pd.read_csv(BUS / "elizabeth_line_daily_robustness.csv", index_col=0)
far = dr.loc[[i for i in dr.index if i.startswith("controls > 1 km")][0], "year 3"]
claim("elizabeth", "displacement robustness", f"gives +{r0(far)}% in year 3 instead of +{r0(c3['year 3'])}%")
assert "48 central controls" in dr.index[0], dr.index[0]
claim("elizabeth", "control stations (count checked)", "48 central Underground stations")
ac = pd.read_csv(BUS / "elizabeth_line_daily_annual_check.csv", index_col=0).iloc[:, 0]
claim("elizabeth", "daily vs annual cross-check",
      f"2019 to 2023 gives +{r0(ac['2019 -> 2023, daily footfall'])}% from daily weekday taps vs "
      f"+{r0(ac['2019 -> 2023, annual counts (extended analysis)'])}% from annual\n  counts, and 2019 to 2025 "
      f"+{r0(ac['2019 -> 2025, daily footfall'])}% vs +{r0(ac['2019 -> 2025, annual counts (extended analysis)'])}%")
assert abs(ac["2019 -> 2023, annual counts (extended analysis)"] - eff) < 0.05   # same source as the DiD summary
claim("elizabeth", "annual result quoted in daily section", f"grew about {r0(eff)}% more than nearby stations between 2019 and 2023")
near = pd.read_csv(BUS / "elizabeth_line_daily_nearby.csv", index_col=0).iloc[:, 0].drop("weeks -16 to -1 (before)")
claim("elizabeth", "displacement range", f"which fell {r0(abs(near.max()))}-{r0(abs(near.min()))}% relative to stations further\n  away")
n_sets = math.comb(48, 3)
claim("elizabeth", "placebo sets (48 choose 3)", f"over\n  all {n_sets:,} sets for the central three")
raw = pd.read_csv(BUS / "bus_change_near_el_raw.csv", index_col=0)["change (%)"]
claim("elizabeth", "raw gap near the line", f"gap ({fx(raw[True], 1)}% near the line vs {fx(raw[False], 1)}% elsewhere)")

# ============================================================================
# Bus vs Tube recovery (results/bus/recovery_*, atypical_days, bus_change_decomposition)
# ============================================================================
ry = pd.read_csv(BUS / "recovery_by_year.csv", index_col=0)
claim("passengers", "recovery table Tube", "| Tube (% of 2019) | " + " | ".join(
    "100" if y == 2019 else f"{fx(ry.loc[y, 'Tube (% of 2019)'], 1, '')}" for y in [2019, 2022, 2023, 2024, 2025, 2026]) + " |")
claim("passengers", "recovery table bus", "| Bus (% of 2019) | " + " | ".join(
    "100" if y == 2019 else f"{fx(ry.loc[y, 'bus (% of 2019)'], 1, '')}" for y in [2019, 2022, 2023, 2024, 2025, 2026]) + " |")
claim("passengers", "bus 2023-24 and 2026", f"Buses were at {r0(ry.loc[2023, 'bus (% of 2019)'])}% of 2019 in\n  2023-24 and {r0(ry.loc[2026, 'bus (% of 2019)'])}% in 2026")
claim("passengers", "2025 crossover", f"in 2025 they fell below the Tube ({r0(ry.loc[2025, 'bus (% of 2019)'])}% vs {r0(ry.loc[2025, 'Tube (% of 2019)'])}%)")
tr = pd.read_csv(BUS / "recovery_trend_since_2023.csv", index_col=[0, 1])
tt, tb = tr.loc[("all days", "Tube")], tr.loc[("all days", "Bus")]


def ci_txt(s):
    lo, hi = [float(v) for v in s.split(" to ")]
    return f"{fx(lo, 1, '+')}%", f"{fx(hi, 1, '+')}%"


claim("passengers", "Tube trend", f"(+{fx(tt['trend (% per year)'], 1, '')}% a year, 95% CI {ci_txt(tt['95% CI'])[0]} to\n  {ci_txt(tt['95% CI'])[1]})")
claim("passengers", "bus trend", f"**bus journeys have fallen {fx(abs(tb['trend (% per year)']), 1, '')}% a year** (CI {ci_txt(tb['95% CI'])[0]} to {ci_txt(tb['95% CI'])[1]})")
claim("README", "bus trend", f"bus journeys have fallen about\n  {fx(abs(tb['trend (% per year)']), 1, '')}% a year")
dw = pd.read_csv(BUS / "recovery_by_day_of_week.csv", index_col=0)
monfri = dw.loc[["Mon", "Fri"], "Tube 2025"]
mid = dw.loc[["Tue", "Wed", "Thu"], "Tube 2025"]
busw = dw.loc[["Mon", "Tue", "Wed", "Thu", "Fri"], "Bus 2025"]
buswe = dw.loc[["Sat", "Sun"], "Bus 2025"]
assert round(monfri.min()) == round(monfri.max()), monfri
claim("passengers", "Tube Mon/Fri vs mid-week", f"({r0(monfri.mean())}% of\n  2019, against {r0(mid.min())}-{r0(mid.max())}% mid-week)")
claim("passengers", "bus by day", f"Buses are {r0(busw.min())}-{r0(busw.max())}% of 2019 on every\n  weekday and below 2019 at weekends too ({r0(buswe.min())}-{r0(buswe.max())}%)")
assert dw.loc[["Sat", "Sun"], "Tube 2025"].min() >= 98.5, "docs say the Tube is back to 2019 at weekends"
ad = pd.read_csv(BUS / "atypical_days.csv", parse_dates=["date"])
strikes = ad[(ad.kind == "Tube strike") & (ad.date >= "2022-01-01")]
claim("passengers", "strike days", f"On the {len(strikes)} full Tube strike days since 2022, bus journeys rose only\n  "
      f"{r0(strikes.bus_vs_normal.min() - 100)}-{r0(strikes.bus_vs_normal.max() - 100)}%")
dc = pd.read_csv(BUS / "bus_change_decomposition.csv", index_col=0)
nb = json.loads((ROOT / "python-notebooks/bus-tube-recovery.ipynb").read_text())
elasticity = float(re.search(r"elasticity = ([\d.]+)", "".join("".join(c["source"]) for c in nb["cells"])).group(1))
cap, cont = dc.loc["Weekday", "capacity on continuing route-stops (%)"], dc.loc["Weekday", "continuing route-stops (%)"]
share_expl = elasticity * cap / cont
assert 0.2 <= share_expl <= 0.3, f"share explained by capacity {fx(share_expl, 2, '')} (docs say 'about a quarter')"
claim("passengers", "capacity cut and points explained",
      f"fell\n  {fx(abs(cap), 1, '')}% on weekdays between 2023-24 and 2025-26 (BUSTO); demand falls about {fx(elasticity, 1, '')}% for each 1% of capacity,\n  "
      f"which accounts for about {r0(abs(elasticity * cap))} of the {fx(abs(cont), 1, '')} points lost")
claim("README", "quarter explained (range checked)", "Service cuts explain about a quarter of the bus fall")

# ============================================================================
# Where bus demand fell (results/bus/bus_change_*)
# ============================================================================
claim("passengers", "decomposition totals", f"Weekday boardings fell {fx(abs(dc.loc['Weekday', 'total change (%)']), 1, '')}% from 2023-24 to\n  2025-26 "
      f"(Saturday {fx(abs(dc.loc['Saturday', 'total change (%)']), 1, '')}%, Sunday {fx(abs(dc.loc['Sunday', 'total change (%)']), 1, '')}%)")
claim("passengers", "continuing route-stops", f"On route-stops served in both years the fall was {fx(abs(cont), 1, '')}%")
gp = pd.read_csv(BUS / "bus_change_by_group.csv", index_col=[0, 1])
claim("passengers", "Superloop", f"mainly the Superloop ({s0(gp.loc[('route_type', 'superloop'), 'Weekday'])}%)")
claim("passengers", "3-6 km", f"largest 3-6 km from the centre ({fx(gp.loc[('from_centre', '3-6 km'), 'Weekday'], 1, '')}% on weekdays)")
bt = pd.read_csv(BUS / "bus_change_by_time.csv", index_col=0)
claim("passengers", "night", f"at night ({r0(bt.loc['00-05 night', 'Weekday'])}%)")
rb = pd.read_csv(BUS / "bus_change_near_el_robustness.csv", index_col=0)
c200 = rb.loc["within 200 m", "near EL central section"]
m = re.match(r"([+-][\d.]+)% \[([+-][\d.]+), ([+-][\d.]+)\]", c200)
claim("elizabeth", "within 200 m", f"**{fx(float(m.group(1)), 1, '')}% better within 200 m**\n  of a central-section station (95% CI {m.group(2)}% to {m.group(3)}%)")
c400 = [float(re.match(r"([+-][\d.]+)", rb.loc["main: weekday, 400 m, spec (5)", c]).group(1))
        for c in ["near EL central section", "near EL outer branches"]]
assert all(2 <= v < 3.5 for v in c400), c400
claim("elizabeth", "400 m (range checked)", "about 2-3% better than stops away from rail at 400 m (not significant)")

# ============================================================================
# Bus crowding (results/bus/crowding_*, crowded_routes_am_peak)
# ============================================================================
tbnd = pd.read_csv(BUS / "crowding_by_time_band.csv").set_index(["day_type", "band"])
am = tbnd.loc[("Weekday", "AM peak 07-10")]
claim("passengers", "AM peak standing", f"{fx(am['standing (%)'], 1, '')}% of route-stops have standing in their busiest AM-peak hour ({r0(am['passengers on standing route-stops (%)'])}% of\n  AM-peak passengers")
ip_pm = [tbnd.loc[("Weekday", b), "standing (%)"] for b in ["inter-peak 10-16", "PM peak 16-19"]]
assert all(abs(v - 1.4) < 0.05 for v in ip_pm), ip_pm
claim("passengers", "inter-peak/PM (range checked)", "against about 1.4% in the inter-peak and PM peak")
cy = pd.read_csv(BUS / "crowding_by_year.csv", header=[0, 1], index_col=0)
claim("passengers", "crowding trend", f"AM-peak standing went from {fx(cy.loc['AM peak 07-10', ('standing', '2023')], 1, '')}% of route-stops in 2023-24 to "
      f"{fx(cy.loc['AM peak 07-10', ('standing', '2025')], 1, '')}%\n  in 2025-26")
cc = pd.read_csv(BUS / "crowding_change_by_capacity.csv", index_col=0)
assert cc.loc["cut > 10%", "standing_change_pp"] > 0
claim("passengers", "cut routes", f"Routes whose capacity was cut by more than 10% lost {r0(abs(cc.loc['cut > 10%', 'load_change_pct']))}% of their\n  passengers yet became more crowded")
cr_ = pd.read_csv(BUS / "crowded_routes_am_peak.csv", dtype={"route": str})
top_routes = list(dict.fromkeys(cr_["route"]))[:7]
claim("passengers", "most crowded routes", f"The most crowded routes are {', '.join(top_routes[:-1])} and {top_routes[-1]}")
loc = pd.read_csv(BUS / "crowding_by_location.csv", index_col=[0, 1])

# ============================================================================
# Combined bus + rail network (results/bus/network_*)
# ============================================================================
srd = pd.read_csv(BUS / "network_single_route_dependency.csv", index_col=0)
bet = pd.read_csv(BUS / "network_rail_station_betweenness.csv", index_col=0)
claim("network", "network size", f"{int(srd['stop areas'].sum()):,} bus stop areas (stops on both sides of the road) and {len(bet)} rail stations, "
      f"joined by {int(bet['walking links to bus'].sum()):,} walking\nlinks")
rho = bet["bus + rail"].rank().corr(bet["rail only"].rank())
claim("network", "Spearman combined vs rail", f"(Spearman {fx(rho, 2, '')} with the rail-only ranking)")
top6 = bet.sort_values("rank, bus + rail").index[:6].tolist()
claim("network", "top stations", "The top\n  stations are those where large bus catchments meet fast rail: " + ", ".join(top6[:3]) + ",\n  " + ", ".join(top6[3:5]) + f", {top6[5]}")
jumps = bet.loc[["New Cross Gate", "Brockley", "Forest Hill"], "rank change"]
assert jumps.min() >= 100 and jumps.max() <= 160, jumps.to_dict()
claim("network", "Overground jump (range checked)", "by 100-160 places")
acc = pd.read_csv(BUS / "network_accessibility.csv", index_col=[0, 1])
claim("network", "outer London saving", f"Rail saves most in outer London ({r0(acc.loc[('from centre', '15+ km'), 'saved by rail'])} min)")
clo = pd.read_csv(BUS / "network_rail_closures.csv").set_index("stations closed")
r10, c10 = 100 * clo.loc[10, "rail only"], 100 * clo.loc[10, "bus + rail"]
claim("network", "closures with buses", f"keeps {r0(r10)}% of its efficiency on rail alone but {r0(c10)}% with buses")
claim("README", "closures with buses", f"keeps {r0(c10)}% of its efficiency with buses, against {r0(r10)}% on rail alone")
crit = pd.read_csv(BUS / "network_critical_bus_routes.csv", index_col=0)
claim("network", "max route loss", f"(at most {r0(crit['efficiency loss (%)'].max())}%\n  of efficiency)")
claim("network", "routes that are the only link", f"{(crit['stop areas cut off'] > 0).sum()} of {len(crit)} routes are the only link")
one = (srd["stop areas"] * srd["served by one route (%)"]).sum() / srd["stop areas"].sum()
claim("network", "single-route stop areas", f"{r0(one)}% of stop\n  areas are served by one route: {r0(srd.loc['< 400 m', 'served by one route (%)'])}% within 400 m of rail, "
      f"{r0(srd.loc['> 2 km', 'served by one route (%)'])}% more than 2 km away")
sens = pd.read_csv(BUS / "network_sensitivity.csv", index_col=0)["Spearman vs main"]
claim("network", "sensitivity range", f"(Spearman {fx(sens.min(), 2, '')}-{fx(sens.max(), 2, '')})")


ct = pd.read_csv(BUS / "crowding_timing.csv", index_col=0)["value"]
claim("passengers", "school timing", f"Morning crowding peaks in the hour from {ct.iloc[0]}, and "
      f"{r0(float(ct.iloc[1]))}% of\n  inter-peak crowding is in the hour starting 15:15-15:45")
lpm = pd.read_csv(BUS / "crowding_location_model.csv", index_col=0)["percentage points"]
far_pp = [lpm["to_rail_s: 800 m - 2 km"], lpm["to_rail_s: > 2 km"]]
assert 2.0 <= min(far_pp) and max(far_pp) < 2.55, far_pp
claim("passengers", "standing far from rail (range checked)", "Stops more than 800 m from rail are 2-2.5 percentage points more likely")
accm = BUS / "network_accessibility_mean.csv"
if accm.exists():
    am_ = pd.read_csv(accm, index_col=0).iloc[:, 0]
    claim("network", "accessibility means", f"{r0(am_['bus + rail'])} minutes from a typical stop area to all others\n  with rail, {r0(am_['bus only'])} by bus alone")
else:
    claim("network", "accessibility means (results file missing: re-run bus-rail-network)", "<missing results/bus/network_accessibility_mean.csv>")


# ============================================================================
# Run
# ============================================================================
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def anchor(h: str) -> str:
    h = re.sub(r"[^\w\- ]", "", h.strip().lower())
    return h.replace(" ", "-")


def check_links() -> list[str]:
    bad = []
    for page in PAGES.values():
        text, here = page.read_text(), page.parent
        targets = re.findall(r"\]\(([^)]+)\)", text) + re.findall(r'src(?:set)?="([^"]+)"', text)
        for t in targets:
            if t.startswith(("http", "../../tree")):
                continue
            path, _, frag = t.partition("#")
            target = (here / path).resolve() if path else page
            if path and not target.exists():
                bad.append(f"{page.relative_to(ROOT)}: missing file {t}")
            elif frag and frag not in [anchor(h) for h in re.findall(r"^#+ (.+)$", target.read_text(), re.M)]:
                bad.append(f"{page.relative_to(ROOT)}: missing anchor {t}")
    return bad


def coverage(found_spans: dict[str, list[tuple[int, int]]]) -> list[str]:
    """Numbers in the pages (outside headings, links, code and images) not inside any checked claim."""
    out = []
    for key, page in PAGES.items():
        text = norm(page.read_text())
        spans = found_spans.get(key, [])
        masked = re.sub(r"<picture>.*?</picture>|`[^`]*`|\]\([^)]*\)|#+ [^|*]*?(?= \S+:|$)", lambda m: " " * len(m.group()), text)
        for m in re.finditer(r"[−\-+]?\d[\d,.]*%?", masked):
            if not any(a <= m.start() < b for a, b in spans):
                ctx = text[max(0, m.start() - 40):m.end() + 20]
                out.append(f"{page.relative_to(ROOT)}: {m.group()}  …{ctx}…")
    return out


def main() -> int:
    verbose = "--verbose" in sys.argv
    texts = {k: norm(p.read_text()) for k, p in PAGES.items()}
    fails, spans = [], {}
    for page, label, expected in CLAIMS:
        e = norm(expected)
        i = texts[page].find(e)
        if i < 0:
            fails.append(f"{PAGES[page].relative_to(ROOT)}: [{label}] expected: {e}")
        else:
            spans.setdefault(page, []).append((i, i + len(e)))
            if verbose:
                print(f"ok  {PAGES[page].relative_to(ROOT)}: [{label}]")
    links = check_links()
    unchecked = coverage(spans)
    print(f"{len(CLAIMS) - len(fails)} of {len(CLAIMS)} claims match results/; {len(links)} broken links; "
          f"{len(unchecked)} numbers in the pages not covered by a claim")
    for f in fails + links:
        print("FAIL", f)
    for a in sorted(set(AMBIGUOUS)):
        print("WARN ambiguous rounding (store more decimals in results/):", a)
    if verbose and unchecked:
        print("\nNot covered (not a failure; these come from notebook output or text, not results/):")
        for u in unchecked:
            print("  ", u)
    return 1 if fails or links else 0


if __name__ == "__main__":
    sys.exit(main())
