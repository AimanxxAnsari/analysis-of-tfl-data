# Bus analysis data

Data for the TfL bus analysis is **not stored in git**. It is downloaded by
[`python-notebooks/data-prep/download_tfl_bus.py`](../../python-notebooks/data-prep/download_tfl_bus.py),
and every file is recorded in [`manifest.csv`](manifest.csv) with its source URL, TfL version
(ETag / last-modified), size, SHA-256 and download date. Files that were deleted after conversion
can be fetched again from `source_url` (direct download) or found on TfL's site via `browse_url`.

```bash
python python-notebooks/data-prep/download_tfl_bus.py all          # everything (~3.7 GB download, ~15 min API)
python python-notebooks/data-prep/download_tfl_bus.py busto --years 2025-2026
```

Re-running skips files whose TfL ETag is unchanged and whose output still exists.

## Datasets

| Dataset | Source | Local copy | Raw kept? |
|---|---|---|---|
| Network Demand: daily Tube and bus journeys, 2019-2026 | [crowding.data.tfl.gov.uk](https://crowding.data.tfl.gov.uk/#!Network%20Demand/) | `data/raw/network-demand/journeys_*.csv` | yes |
| Network Demand: daily entry/exit taps per rail station, 2019-2026 | same | `data/raw/network-demand/stationfootfall_*.csv` | yes |
| BUSTO bus demand, 2023-24 to 2025-26 (39 CSVs, 3.7 GB) | [crowding.data.tfl.gov.uk](https://crowding.data.tfl.gov.uk/#!BUSTO/) | `data/processed/busto/<year>/*.parquet` (580 MB) | **no**: converted to Parquet, then deleted |
| BUSTO user guide and data dictionary v1.2 | same | `data/raw/busto/` | yes |
| Bus stops and route sequences feeds (`bus-stops.csv`, `bus-sequences.csv`): LBSL stop codes as used by BUSTO, NaPTAN ids, grid coordinates. TfL last updated them on 29 Aug 2024 | [tfl.gov.uk/tfl/syndication/feeds](https://tfl.gov.uk/info-for/open-data-users/our-open-data) | `data/raw/bus-feeds/` | yes |
| Bus routes, ordered stop sequences, stop coordinates | [TfL Unified API](https://api.tfl.gov.uk/) `/Line/Mode/bus/Route`, `/Line/{id}/Route/Sequence/{direction}` | `data/processed/bus-routes/{routes,route_stop_sequences,stops}.csv`; raw responses in `data/raw/bus-routes/` | yes |

The API data is a snapshot of the network on the download date, not a historical record.

## BUSTO files

Per year: 3 day types (Weekday, Saturday, Sunday) x 4 route groups (1-149, 150-299, 300-5xx,
letter-prefix) of **total demand by route, direction, stop and quarter hour**, plus one
**max demand hour by route by timeband** file. Values are averages for a typical day of that type,
not counts for individual dates.

Parquet columns are the CSV columns in snake_case (`V/C` becomes `v_c`, load / capacity).
`route` and `stopcode` are stored as text in every file.

## Known quirks (found while downloading)

* **Overlapping Network Demand files.** `*_2024`, `*_2024_2025` and `*_2025_2026` overlap. 2024 is
  identical in the first two; the last two differ on 6 days of journeys (by at most 1,000) and on
  66 of 154,452 station-days of footfall. Use the most recently published file for each date.
* **File names.** Some TfL names have a space before `.csv`; local copies use snake_case names.
* **Routes.** 2025-26 BUSTO has 606 routes. 4 of them (283, 349, 472, 533) are not in the current API
  list, and 75 API routes (mostly 6xx school routes, plus route 10) have no BUSTO data.

*Powered by TfL Open Data.* Contains OS data © Crown copyright and database rights.
