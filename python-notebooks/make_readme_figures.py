"""Build the README charts from the CSVs in results/ (run after the notebooks).

Writes figures/<name>-light.png and figures/<name>-dark.png; the README picks
the one matching the reader's GitHub theme.

    python make_readme_figures.py
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"

# Validated default palette (light / dark steps of the same hues)
THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781",
                  grid="#e1e0d9", axis="#c3c2b7",
                  s1="#2a78d6", s2="#eb6834", s3="#1baf7a", pos="#2a78d6", neg="#e34948"),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781",
                 grid="#2c2c2a", axis="#383835",
                 s1="#3987e5", s2="#d95926", s3="#199e70", pos="#3987e5", neg="#e66767"),
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


if __name__ == "__main__":
    plt.rcParams["font.family"] = "DejaVu Sans"
    for mode, t in THEMES.items():
        for f in (fig_overlap, fig_ranks, fig_totals, fig_share, fig_profile):
            f(t, mode)
    print("wrote", sorted(p.name for p in FIGURES.glob("*.png")))
