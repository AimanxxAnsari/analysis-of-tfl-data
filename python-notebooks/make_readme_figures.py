"""Build the README charts from the CSVs in results/ (run after the notebooks).

Writes figures/<name>-light.png and figures/<name>-dark.png; the README picks
the one matching the reader's GitHub theme.

    python make_readme_figures.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"

# Validated default palette (light / dark steps of the same hues)
THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781",
                  grid="#e1e0d9", axis="#c3c2b7",
                  s1="#2a78d6", s2="#eb6834", s3="#1baf7a", pos="#2a78d6", neg="#e34948", violet="#6250d6"),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", axis="#383835",
                 s1="#3987e5", s2="#d95926", s3="#199e70", pos="#3987e5", neg="#e66767", violet="#9085e9"),
}


def style(ax, t, grid_axis="y"):
    ax.set_facecolor(t["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(t["axis"])
    ax.tick_params(colors=t["muted"], labelcolor=t["ink2"], length=0, labelsize=10)
    ax.grid(axis=grid_axis, color=t["grid"], linewidth=0.8)
    ax.set_axisbelow(True)


def new_fig(t, w, h):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(t["surface"])
    style(ax, t)
    return fig, ax


def title(fig, ax, t, text, sub):
    ax.set_title(text, loc="left", color=t["ink"], fontsize=13, fontweight="bold", pad=26)
    ax.text(0, 1.02, sub, transform=ax.transAxes, color=t["ink2"], fontsize=10, va="bottom")


def legend(ax, t, **kw):
    leg = ax.legend(frameon=False, fontsize=10, labelcolor=t["ink2"], **kw)
    return leg


def save(fig, name, mode):
    FIGURES.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES / f"{name}-{mode}.png", facecolor=fig.get_facecolor())
    plt.close(fig)


# -- 1. Overlap of 2024 top-5 lists with 2014 -------------------------------
def fig_overlap(t, mode):
    comp = pd.read_csv(RESULTS / "centrality_top5_comparison.csv")
    lists = comp.set_index(["network", "measure"])["top_stations"].str.split("; ")
    measures = ["degree", "betweenness", "closeness", "katz", "pagerank", "overall"]
    variants = [("2024 comparable (no trams)", "2024 network", t["s1"]),
                ("2024 without Elizabeth line", "2024 without the Elizabeth line", t["s2"])]
    fig, ax = new_fig(t, 9, 4.6)
    w = 0.36
    for i, (net, label, color) in enumerate(variants):
        vals = [len(set(lists[("2014", m)]) & set(lists[(net, m)])) for m in measures]
        xs = [j + (i - 0.5) * (w + 0.04) for j in range(len(measures))]
        bars = ax.bar(xs, vals, w, color=color, label=label, edgecolor=t["surface"], linewidth=1.5)
        ax.bar_label(bars, color=t["ink2"], fontsize=9, padding=2)
    ax.set_xticks(range(len(measures)), [m.capitalize() for m in measures])
    ax.set_ylim(0, 6.6)
    ax.set_yticks(range(6))
    ax.set_ylabel("Stations shared with 2014 top 5", color=t["ink2"], fontsize=10)
    title(fig, ax, t, "Removing the Elizabeth line restores the 2014 rankings",
          "Top-5 stations per centrality measure that also appear in the 2014 top 5 (out of 5)")
    legend(ax, t, loc="upper left", bbox_to_anchor=(0, 1.0), ncol=2)
    save(fig, "centrality-overlap", mode)


# -- 2. Betweenness rank of key stations -------------------------------------
def fig_ranks(t, mode):
    r = pd.read_csv(RESULTS / "betweenness_rank_key_stations.csv", index_col=0)
    cols = [("2014", "2014", t["s1"], "o"),
            ("2024 comparable (no trams)", "2024", t["s2"], "s"),
            ("2024 without Elizabeth line", "2024 without Elizabeth line", t["s3"], "D")]
    order = ["Farringdon", "Tottenham Court Road", "Whitechapel", "Bond Street", "Liverpool Street",
             "Stratford", "King's Cross St. Pancras", "Waterloo", "Green Park", "Bank and Monument"]
    r = r.loc[order[::-1]]
    fig, ax = new_fig(t, 9, 5.2)
    style(ax, t, grid_axis="x")
    y = range(len(r))
    for yi, (_, row) in zip(y, r.iterrows()):
        ax.plot([row.min(), row.max()], [yi, yi], color=t["axis"], linewidth=2, zorder=1)
    for col, label, color, marker in cols[1:]:
        ax.scatter(r[col], y, s=64, color=color, marker=marker, label=label, zorder=3,
                   edgecolor=t["surface"], linewidth=1.5)
    # 2014 as an open ring drawn on top, so it stays visible where it equals another rank
    col, label, color, _ = cols[0]
    ax.scatter(r[col], y, s=150, facecolor="none", edgecolor=color, linewidth=2,
               label=label, zorder=4)
    handles, labels = ax.get_legend_handles_labels()
    order_idx = [labels.index(c[1]) for c in cols]
    ax.legend([handles[i] for i in order_idx], [labels[i] for i in order_idx], frameon=False,
              fontsize=10, labelcolor=t["ink2"], loc="upper left", bbox_to_anchor=(0, 1.0), ncol=3)
    for yi, v in zip(y, r["2024 comparable (no trams)"]):
        ax.annotate(f"#{v}", (v, yi), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=8, color=t["ink2"])
    ax.set_xscale("log")
    ax.set_xlim(300, 0.7)  # rank 1 on the right
    ax.xaxis.set_major_locator(LogLocator(base=10, subs=(1, 3)))
    ax.xaxis.set_minor_formatter(NullFormatter())
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.set_yticks(list(y), r.index)
    ax.set_xlabel("Betweenness rank (log scale, 1 = most central)", color=t["ink2"], fontsize=10)
    title(fig, ax, t, "Elizabeth line stations jump to the top of the network",
          "Betweenness rank of selected stations; labels show the 2024 rank")
    ax.set_ylim(-0.6, len(r) + 0.4)
    save(fig, "betweenness-ranks", mode)


# -- 3. LU entries + exits per year -----------------------------------------
def fig_totals(t, mode):
    s = pd.read_csv(RESULTS / "lu_entry_exit_by_station.csv", index_col=0).sum() / 1e9
    fig, ax = new_fig(t, 9, 4.2)
    bars = ax.bar(s.index, s.values, 0.6, color=t["s1"], edgecolor=t["surface"], linewidth=1.5)
    ax.bar_label(bars, labels=[f"{v:.2f}bn" for v in s.values], color=t["ink2"], fontsize=9, padding=2)
    ax.set_ylim(0, 3.3)
    ax.set_yticks([0, 1, 2, 3])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}bn"))
    title(fig, ax, t, "London Underground station entries + exits, 2017-2022",
          "Gate counts at LU stations; 2022 is still 24.5% below 2019")
    save(fig, "lu-totals", mode)


# -- 4. Change in share of network traffic, 2017 -> 2022 --------------------
def fig_share(t, mode):
    df = pd.read_csv(RESULTS / "station_change_2017_2022.csv", index_col=0)
    s = df["change vs network %"].sort_values()
    fig, ax = new_fig(t, 9, 5.0)
    style(ax, t, grid_axis="x")
    colors = [t["pos"] if v >= 0 else t["neg"] for v in s]
    bars = ax.barh(s.index, s.values, 0.62, color=colors, edgecolor=t["surface"], linewidth=1.5)
    ax.bar_label(bars, labels=[f"{v:+.0f}%" for v in s.values], color=t["ink2"], fontsize=9, padding=3)
    ax.axvline(0, color=t["axis"], linewidth=1)
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(s.min() - 18, s.max() + 18)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    title(fig, ax, t, "Farringdon doubled its share of Underground traffic",
          "Change in each station's share of all LU entries + exits, 2017 to 2022")
    save(fig, "station-share-change", mode)


# -- 5. Weekday share of the day by time period ------------------------------
def fig_profile(t, mode):
    p = pd.read_csv(RESULTS / "lu_typical_day_profile.csv", index_col=[0, 1])
    share = p.div(p.sum(axis=1), axis=0) * 100
    years = [(2019, t["s1"]), (2020, t["s2"]), (2021, t["s3"])]
    periods = list(p.columns)
    fig, ax = new_fig(t, 9, 4.4)
    w = 0.26
    for i, (y, color) in enumerate(years):
        vals = share.loc[(y, "Weekday")].values
        xs = [j + (i - 1) * (w + 0.03) for j in range(len(periods))]
        bars = ax.bar(xs, vals, w, color=color, label=str(y), edgecolor=t["surface"], linewidth=1.5)
        ax.bar_label(bars, labels=[f"{v:.0f}" for v in vals], color=t["ink2"], fontsize=8, padding=2)
    ax.set_xticks(range(len(periods)), periods)
    ax.set_ylim(0, 33)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    title(fig, ax, t, "Weekday travel shifted away from the morning peak",
          "Share of a typical weekday's LU entries + exits in each time period, 2019-2021")
    legend(ax, t, loc="upper right", ncol=3)
    save(fig, "weekday-profile", mode)


# -- 6. Map of the 2024 network with corrected coordinates -------------------
def fig_map(t, mode):
    import tfl_analysis as T
    pos = T.positions_2024()
    edges = T.load_edges_2024()
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    fig.patch.set_facecolor(t["surface"])
    ax.set_facecolor(t["surface"])
    ax.set_axis_off()
    el_color = t["violet"]
    for is_el in (False, True):
        sub = edges[(edges["Line"] == "Elizabeth Line") == is_el]
        for a, b in sub[["From Station", "To Station"]].itertuples(index=False):
            (x1, y1), (x2, y2) = pos[a], pos[b]
            ax.plot([x1, x2], [y1, y2], color=el_color if is_el else t["muted"],
                    linewidth=2.2 if is_el else 0.9, alpha=1 if is_el else 0.7,
                    solid_capstyle="round", zorder=2 if is_el else 1)
    xs, ys = zip(*pos.values())
    ax.scatter(xs, ys, s=5, color=t["ink2"], zorder=3, linewidths=0)
    for s in ["Reading", "Shenfield", "Heathrow Terminal 5", "Abbey Wood"]:
        x, y = pos[s]
        ax.annotate(s, (x, y), xytext=(4, 4), textcoords="offset points", fontsize=8, color=t["ink2"])
    ax.set_aspect(1 / np.cos(np.radians(51.5)))
    ax.plot([], [], color=el_color, linewidth=2.2, label="Elizabeth line")
    ax.plot([], [], color=t["muted"], linewidth=0.9, label="Tube, Overground, DLR, Trams")
    ax.legend(frameon=False, fontsize=9, labelcolor=t["ink2"], loc="lower right")
    ax.set_title("The 2024 network on TfL's official station locations", loc="left",
                 color=t["ink"], fontsize=13, fontweight="bold", pad=22)
    ax.text(0, 1.01, f"{len(pos)} stations; coordinates from the TfL Unified API", transform=ax.transAxes,
            color=t["ink2"], fontsize=10, va="bottom")
    save(fig, "network-map", mode)


# -- 7. Centrality vs ridership ----------------------------------------------
def fig_corr(t, mode):
    c = pd.read_csv(RESULTS / "centrality_vs_ridership.csv")
    measures = ["closeness", "katz", "degree", "betweenness", "pagerank"]
    series = [("2014 network vs 2019 ridership", "2014 network vs 2019 ridership", t["s1"]),
              ("2024 network vs 2023 ridership", "2024 network vs 2023 ridership", t["s2"])]
    fig, ax = new_fig(t, 9, 4.4)
    w = 0.36
    for i, (comp, label, color) in enumerate(series):
        vals = c[c.comparison == comp].set_index("measure").loc[measures, "spearman_rho"].values
        xs = [j + (i - 0.5) * (w + 0.04) for j in range(len(measures))]
        bars = ax.bar(xs, vals, w, color=color, label=label, edgecolor=t["surface"], linewidth=1.5)
        ax.bar_label(bars, labels=[f"{v:.2f}" for v in vals], color=t["ink2"], fontsize=9, padding=2)
    ax.set_xticks(range(len(measures)), [m.capitalize() for m in measures])
    ax.set_ylim(0, 0.95)
    ax.set_ylabel("Spearman correlation with entries + exits", color=t["ink2"], fontsize=10)
    title(fig, ax, t, "Closeness predicts how busy a station is; betweenness much less",
          "Rank correlation between each centrality measure and annual LU entries + exits")
    legend(ax, t, loc="upper right", ncol=1)
    save(fig, "centrality-vs-ridership", mode)


# -- 8. Elizabeth line difference-in-differences by year ----------------------
def fig_did(t, mode):
    e = pd.read_csv(RESULTS / "elizabeth_line_did_by_year.csv", index_col=0)
    fig, ax = new_fig(t, 9, 4.6)
    ax.axvspan(2021.6, 2025.4, color=t["violet"], alpha=0.10, linewidth=0)
    ax.text(2021.7, 104, "Elizabeth line open (May 2022)", color=t["ink2"], fontsize=9, va="top")
    ax.axhline(0, color=t["axis"], linewidth=1)
    for col, label, color, marker in [("central control (%)", "vs central-London stations", t["s1"], "o"),
                                      ("all-LU control (%)", "vs all other LU stations", t["s2"], "s")]:
        ax.plot(e.index, e[col], color=color, linewidth=2, marker=marker, markersize=6,
                markeredgecolor=t["surface"], markeredgewidth=1.5, label=label)
    for y in (2023, 2025):
        v = e.loc[y, "central control (%)"]
        ax.annotate(f"+{v:.0f}%", (y, v), xytext=(0, 9), textcoords="offset points",
                    ha="center", fontsize=9, color=t["ink2"])
    ax.set_xticks(e.index)
    ax.set_ylim(-50, 110)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:+.0f}%"))
    title(fig, ax, t, "New Elizabeth line stations grew ~84% more than comparable stations",
          "Extra growth since 2019 at Bond St, Tottenham Ct Rd, Farringdon, Whitechapel (LU counts)")
    legend(ax, t, loc="lower left")
    save(fig, "elizabeth-line-did", mode)


# -- 9. Resilience under targeted closures ------------------------------------
def fig_resilience(t, mode):
    c = pd.read_csv(RESULTS / "resilience_curves.csv")
    fig, ax = new_fig(t, 9, 4.6)
    for name, color, marker, dx, dy in [("2014", t["s1"], "o", -34, -14), ("2024", t["s2"], "s", 9, 0),
                                        ("2024 without Elizabeth line", t["s3"], "D", 9, 7)]:
        y = 100 * c[f"{name} | targeted"]
        ax.plot(c.stations_removed, y, color=color, linewidth=2, label=name)
        ax.plot(10, y[10], marker=marker, color=color, markersize=7,
                markeredgecolor=t["surface"], markeredgewidth=1.5)
        ax.annotate(f"{y[10]:.0f}%", (10, y[10]), xytext=(dx, dy), textcoords="offset points",
                    va="center", fontsize=9, color=t["ink2"])
    ax.set_xlim(0, 40)
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    ax.set_xlabel("Most central stations closed (recomputed after each closure)", color=t["ink2"], fontsize=10)
    title(fig, ax, t, "The Elizabeth line makes the network harder to break",
          "Network efficiency remaining as the most central stations close one by one")
    legend(ax, t, loc="upper right")
    save(fig, "resilience", mode)


if __name__ == "__main__":
    plt.rcParams["font.family"] = "DejaVu Sans"
    for mode, t in THEMES.items():
        for f in (fig_overlap, fig_ranks, fig_totals, fig_share, fig_profile,
                  fig_map, fig_corr, fig_did, fig_resilience):
            f(t, mode)
    print("wrote", sorted(p.name for p in FIGURES.glob("*.png")))
