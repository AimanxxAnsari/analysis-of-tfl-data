# Data

| File | What it is | Produced by / used by |
|---|---|---|
| `2022-TFL-Links.csv` | TfL link list (station-to-station links per line) | Input to `data-prep/01-build-network-from-numbat.ipynb` |
| `NBT20FRI-new.csv` (`.numbers` is the same table in Apple Numbers format) | TfL NUMBAT link loads, Friday 2020: passengers on each link by time band | Input to `01-build-network-from-numbat.ipynb` |
| `2022-tfl-edges.csv` | **2024 network edges** (line, from station, to station) | Built by `01-...`; used by all 2024 analysis |
| `2022-tfl-stations.csv` | Station list per line | Built by `01-...` |
| `station-with-no-coordinates.csv` | Stations awaiting geocoding | Built by `01-...`; input to `02-...` |
| `tfl_stations_2022_with_coordinates.csv` | **Station list with coordinates** (one row per station per line) | Built by `02-geocode-stations-google.ipynb`; coordinates replaced with TfL's official ones by `data-prep/fix_station_coordinates.py` |
| `tfl-station-stoppoints.csv` | Station-level StopPoints from the TfL Unified API (Tube, DLR, Overground, Elizabeth line, Trams) | Downloaded by `fix_station_coordinates.py --refresh` |
| `coordinate-fixes.csv` | Every station row's old (geocoded) vs new (TfL) position and the distance moved | Written by `fix_station_coordinates.py` |
| `tfl_stations_with_coordinates.csv`, `station-coordinates.csv`, `stations-with-coordinates.csv`, `dataset20.csv` | Earlier intermediate files | Used only by notebooks in `python-notebooks/archive/` |
| `yearly-counts-tube/AnnualisedEntryExit_<year>.xlsx` | TfL annual station entry/exit counts, 2017-2022 | `tfl-passenger-flow.ipynb`, `extended-analysis.ipynb` |
| `yearly-counts-tube/ByQhrEntryExit_<year>.xlsx` | TfL quarter-hourly entry/exit profiles for a typical day, 2017-2021 | `tfl-passenger-flow.ipynb` |

The 2014 network is in `References/London_Multiplex_Transport/` (De Domenico et al., 2014; ODbL/DbCL licences included there).

Station counts and NUMBAT data are © Transport for London, published as open data under the
[TfL open data terms](https://tfl.gov.uk/info-for/open-data-users/). Station locations come from the
[TfL Unified API](https://api.tfl.gov.uk/). *Powered by TfL Open Data.*
