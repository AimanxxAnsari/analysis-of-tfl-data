# Analysis of TfL data

Code and data for my MSc Data Analytics dissertation at Queen Mary University of London
(MTHM038, 2023/24): *Analysis of TfL data, with special emphasis on network models*.

The project compares the structure of the London rail network in 2014 and 2024 using five
centrality measures, assesses what the Elizabeth line changed, and studies station
entry/exit counts from 2017 to 2022, including the effect of COVID-19. An extended analysis
added after submission uses counts up to 2025 to measure the Elizabeth line's effect on
ridership and the network's resilience to closures. A TfL bus analysis adds London's buses:
recovery after COVID, the Elizabeth line from daily data, crowding, and a combined bus + rail network.

> **Submitted version.** The code exactly as it was when the dissertation was submitted
> (1 September 2024) is preserved at the git tag
> [`dissertation-submitted`](../../tree/dissertation-submitted). The dissertation itself is
> unchanged. Everything after that tag is a post-submission revision of the code and results;
> see [Corrections after submission](docs/corrections.md).

## Key findings at a glance

* **The Elizabeth line reshaped the network's structure.** Remove it from the 2024 network and 29 of the
  30 top-5 centrality positions return to their 2014 values ([details](docs/network.md#network-structure-2014-vs-2024)).
* **It also moved passengers.** Its four new central stations grew about **84% more** than comparable
  central-London stations between 2019 and 2023, roughly 70 million extra entries + exits a year
  ([details](docs/elizabeth-line.md#effect-on-ridership-annual-counts)). Daily data confirms the effect:
  footfall at the new central stations jumped about 42% in the opening weeks and reached +88% after three
  years, relative to nearby stations ([details](docs/elizabeth-line.md#effect-on-ridership-daily-station-data)).
* **It made the network harder to break.** After the 10 most central stations close, the 2024 network keeps
  49% of its efficiency, against 33-34% without the line ([details](docs/network.md#resilience-to-station-closures)).
  Buses make the rail network much harder to break: after the 10 most central rail stations close,
  travel between the rest keeps 76% of its efficiency with buses, against 47% on rail alone
  ([details](docs/network.md#a-combined-bus--rail-network)).
* **Closeness, not betweenness, predicts how busy a station is** (Spearman rho 0.66-0.71 vs 0.28-0.36)
  ([details](docs/network.md#does-centrality-predict-ridership)).
* **Buses are losing passengers while the Tube holds steady.** Since mid-2023 bus journeys have fallen about
  2.2% a year; the Tube is flat. Service cuts explain about a quarter of the bus fall
  ([details](docs/passengers-and-buses.md#bus-vs-tube-recovery)).
* **Bus crowding is a suburban, school-time problem,** worst far from rail and rising as service is cut
  ([details](docs/passengers-and-buses.md#bus-crowding)).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/centrality-overlap-dark.png">
  <img alt="Bar chart: number of 2014 top-5 stations shared by each 2024 top-5 list, with and without the Elizabeth line" src="figures/centrality-overlap-light.png" width="800">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/elizabeth-line-did-dark.png">
  <img alt="Line chart: extra growth of four new Elizabeth line stations relative to control stations, 2017 to 2025" src="figures/elizabeth-line-did-light.png" width="800">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="figures/bus-tube-recovery-dark.png">
  <img alt="Line chart: Tube and bus journeys as a percentage of 2019, monthly, 2019 to 2026, with trend lines since July 2023" src="figures/bus-tube-recovery-light.png" width="800">
</picture>

## Results in full

| Page | What it covers |
|---|---|
| [Network structure and resilience](docs/network.md) | 2014 vs 2024 centrality, centrality vs ridership, resilience to closures, the combined bus + rail network |
| [The Elizabeth line](docs/elizabeth-line.md) | Its effect on the network, on station traffic (annual counts and daily data) and on nearby bus demand |
| [Passengers and buses](docs/passengers-and-buses.md) | Underground counts 2017-2022, bus vs Tube recovery, where bus demand fell, bus crowding |
| [Corrections after submission](docs/corrections.md) | What was corrected in the code and results after the dissertation was submitted |

## Notebooks and data

| Notebook (`python-notebooks/`) | What it covers | Data used |
|---|---|---|
| [`tfl-2014-centrality`](python-notebooks/tfl-2014-centrality.ipynb) | 2014 network (Tube, Overground, DLR) and its centrality measures | 2014 network |
| [`tfl-2024-centrality`](python-notebooks/tfl-2024-centrality.ipynb) | 2024 network, its centrality measures, and the like-for-like 2014 vs 2024 comparison | 2014 and 2024 networks |
| [`tfl-passenger-flow`](python-notebooks/tfl-passenger-flow.ipynb) | Annual and time-of-day station entry/exit analysis, 2017-2022 | Station counts |
| [`extended-analysis`](python-notebooks/extended-analysis.ipynb) | Centrality vs ridership, Elizabeth line difference-in-differences, network resilience | Station counts, both networks |
| [`bus-routes-stops`](python-notebooks/bus-routes-stops.ipynb) | Matches bus stops and routes across BUSTO, TfL's feeds and the API; links every bus stop to rail | BUSTO, bus stops and routes, 2024 network |
| [`bus-eda`](python-notebooks/bus-eda.ipynb) | First look at every dataset: recovery, strikes, footfall, what the BUSTO measures mean | Network Demand, BUSTO |
| [`bus-tube-recovery`](python-notebooks/bus-tube-recovery.ipynb) | Bus vs Tube recovery after COVID | Network Demand, BUSTO |
| [`elizabeth-line-daily`](python-notebooks/elizabeth-line-daily.ipynb) | The Elizabeth line's effect from daily station data | Network Demand, 2024 network |
| [`bus-demand-change`](python-notebooks/bus-demand-change.ipynb) | Where bus demand fell since 2023-24, and near the Elizabeth line | BUSTO, bus stops, 2024 network |
| [`bus-crowding`](python-notebooks/bus-crowding.ipynb) | When, where and on which routes buses are crowded | BUSTO, bus stops, 2024 network |
| [`bus-rail-network`](python-notebooks/bus-rail-network.ipynb) | Combined bus + rail network: accessibility, centrality, resilience | BUSTO, bus stops, 2024 network |

| Data | Contents | Coverage |
|---|---|---|
| 2024 network | `data/2022-tfl-edges.csv`, `data/tfl_stations_2022_with_coordinates.csv`: built for this project from TfL line and station information; station locations from the [TfL Unified API](https://api.tfl.gov.uk/) | 2024 |
| 2014 network | London multiplex transport dataset of M. De Domenico, A. Solé-Ribalta, S. Gómez and A. Arenas, *Navigability of interconnected networks under random failures*, PNAS 111 (2014) 8351-8356 (licences in `References/London_Multiplex_Transport/`) | 2013-era |
| [Station counts](https://crowding.data.tfl.gov.uk/) | Annual (`AnnualisedEntryExit_<year>.xlsx`) and quarter-hourly (`ByQhrEntryExit_<year>.xlsx`) station counts | 2017-2025; 2017-2021 |
| [Network Demand](https://crowding.data.tfl.gov.uk/#!Network%20Demand/) | Total Tube and bus journeys per day; daily entry and exit taps per rail station | Jan 2019 - Nov 2026 |
| [BUSTO](https://crowding.data.tfl.gov.uk/#!BUSTO/) | Bus boardings, alightings, load and capacity for every route, direction and stop by quarter hour, and each stop's busiest hour (typical weekday, Saturday, Sunday) | 2023-24 to 2025-26 |
| Bus stops and routes | [TfL bus stops and sequences feeds](https://tfl.gov.uk/info-for/open-data-users/our-open-data) (stop codes used by BUSTO, stop locations, route sequences); [TfL Unified API](https://api.tfl.gov.uk/) (677 current routes with ordered stops) | Aug 2024; snapshot at download |

*Powered by TfL Open Data.* The bus analysis data is **not stored in git** (BUSTO alone is 3.7 GB):
`python-notebooks/data-prep/download_tfl_bus.py` downloads everything, converts BUSTO to Parquet (580 MB) and
deletes the raw CSVs. Every file's source URL, TfL version, size and checksum is recorded in
[`data/bus/manifest.csv`](data/bus/manifest.csv), so anything deleted can be fetched again;
[`data/bus/README.md`](data/bus/README.md) describes the layout and the quirks found in the data.

**Other folders:** `python-notebooks/tfl_analysis.py` and `tfl_bus.py` hold logic shared by the notebooks;
`python-notebooks/data-prep/` shows how the 2024 network and station coordinates were built
(`fix_station_coordinates.py`); `data/` holds the 2024 network, station locations and counts
([`data/README.md`](data/README.md)); `results/` the CSV outputs (`results/bus/` for buses); `figures/` the charts,
built by `python-notebooks/make_readme_figures.py`; `docs/` the full results; `References/London_Multiplex_Transport/`
the 2014 dataset; `python-notebooks/archive/` exploratory notebooks from the dissertation period, not used for any result.

**Notes on the data**

* The 2014 network is the 2013-era multiplex dataset rather than an official TfL release.
* TfL's annual counts are modelled in 2017 (`Relate`), ticket-gate counts 2018-2023 (`Gateline`) and card
  taps from 2024 (`taps`). Richmond and Wimbledon join the LU series from 2024, and some stations close
  temporarily in some years. Comparisons across years use stations counted in every year.
* BUSTO gives **typical-day averages** for each financial year, not counts for individual days, and starts
  in 2023-24. The bus stop feed dates from August 2024; 0.5% of 2025-26 boardings are at newer stops.
* The combined network and the bus-near-rail measures use **TfL rail only**. National Rail, which serves
  much of south and outer London, is not included.

## Running

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd python-notebooks

# rail analysis
jupyter nbconvert --to notebook --execute --inplace tfl-2014-centrality.ipynb tfl-2024-centrality.ipynb \
    tfl-passenger-flow.ipynb extended-analysis.ipynb
python data-prep/fix_station_coordinates.py --refresh   # optional: re-download TfL station locations

# bus analysis: download the data (~3.7 GB, kept as ~650 MB locally), then run the notebooks in order
python data-prep/download_tfl_bus.py all
jupyter nbconvert --to notebook --execute --inplace bus-routes-stops.ipynb bus-eda.ipynb \
    bus-tube-recovery.ipynb elizabeth-line-daily.ipynb bus-demand-change.ipynb bus-crowding.ipynb \
    bus-rail-network.ipynb   # the last one takes about 20 minutes

python make_readme_figures.py   # rebuilds the charts in figures/ from results/
```

Each notebook runs top to bottom from a fresh kernel and writes its tables to `results/`.

## Licence

* **Code** (notebooks and Python scripts) is released under the [MIT License](LICENSE).
* **Data keeps its original licences** and is not covered by the MIT License:
  * TfL station counts, NUMBAT link loads, station locations and the bus analysis data (Network Demand,
    BUSTO, bus stop and route data) are © Transport for London, used under the
    [TfL open data terms](https://tfl.gov.uk/info-for/open-data-users/).
    *Powered by TfL Open Data.* Bus stop locations contain OS data © Crown copyright and database rights.
  * The 2014 London multiplex dataset (De Domenico et al., 2014) is licensed under the
    [Open Database License (ODbL)](References/London_Multiplex_Transport/LICENSE_odbl-10.txt),
    with its contents under the
    [Database Contents License (DbCL)](References/London_Multiplex_Transport/LICENSE_dbcl-10.txt).
    Data derived from it, such as the harmonised 2014 network and its results, falls under the same terms.
