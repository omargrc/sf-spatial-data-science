# Pass 1 log — QGIS

Record what QGIS tells you as you work through Pass 1. In Pass 2 you rebuild each module in Python,
weeks later, and check your code against the numbers and outputs written down here.

Fill in each blank as you reach that step, then commit this file along with your QGIS project.
The **Step** column is the step number in that module's PDF; rows like `5a` and `5b` are two values
from the same step. Type plain numbers (`1,234` or `0.82` are both fine) so the Pass 2 notebooks can
read them back.

---

## Module 1 · Vector data engineering

**Date completed:**
**QGIS version** (Help › About):
**Data downloaded on** (`downloaded_utc` in `data/raw/download_manifest.json`):

### Commercial zoning codes (step 16)

Codes in the zoning layer where `gen = 'Commercial'`:

```
(paste the list here)
```

### Feature counts

| Step | What | Count |
|---|---|---|
| 8  | `parcels` — all features | |
| 11 | retired parcels (`"active" = false`) | |
| 12 | `mapblklot` — Count / Count (distinct) | / |
| 13 | split-zoned parcels (`LIKE '%\|%'`) | |
| 14 | invalid geometries (*Invalid output*) | |
| 17 | `1_active_commercial` | |
| 18 | `2_footprints` | |
| 19 | `3_valid` | |
| 20 | `commercial_parcels_3857` (saved) | |
| 22 | typical `ratio` value | |

### Outputs

- [ ] `data/processed/sf_commercial_parcels_qgis.gpkg` → layer `commercial_parcels_3857`
- [ ] `qgis/module1_vector.qgz`
- [ ] `outputs/maps/module1_commercial_parcels_qgis.png`

### Notes

- What surprised me:
- Anything I'm not sure I did right (check it in Pass 2):

---

## Module 2 · Raster suitability

**Date completed:**
**Data downloaded on** (`downloaded_utc` for `sf_dem` in `data/raw/download_manifest.json`):

### Values

| Step | What | Value |
|---|---|---|
| 2a | lowest elevation the script printed (m) | |
| 2b | highest elevation the script printed (m) | |
| 5a | raw DEM — CRS | |
| 5b | raw DEM — dimensions (width × height, cells) | |
| 5c | raw DEM — pixel size (degrees) | |
| 5d | raw DEM — No-Data value | |
| 6 | highest elevation, *Actual* accuracy (m) | |
| 9 | wrong-way slope (degrees DEM) — typical value (°) | |
| 11 | `sf_dem_7131_qgis` — dimensions (width × height, cells) | |
| 13a | `sf_slope_7131_qgis` — mean slope (°) | |
| 13b | `sf_slope_7131_qgis` — maximum slope (°) | |
| 19 | parcels with `flat_mean` NULL (too small for a cell centre) | |
| 20 | parcels with `"flat_mean" >= 0.8` (suitable) | |
| 21 | parcels with `"slope_mean" < 5` | |
| 26a | flat commercial area, `flat_pieces` (acres) | |
| 26b | total commercial area, `parcels_7131` (acres) | |

### Outputs

- [ ] `data/processed/sf_dem_7131_qgis.tif`, `sf_slope_7131_qgis.tif`, `sf_flat_7131_qgis.tif`
- [ ] `data/processed/sf_commercial_flat_qgis.gpkg` → layers `commercial_slope_7131`, `suitable_parcels_3857`
- [ ] `qgis/module2_raster.qgz`
- [ ] `outputs/maps/module2_flat_commercial_qgis.png`

### Notes

- Share-of-flat-cells (step 20) or mean slope (step 21): which would I defend to a client, and why?
- What surprised me:
- Anything I'm not sure I did right (check it in Pass 2):

---

## Module 3 · Spatial statistics

**Date completed:**
**Data downloaded on** (`downloaded_utc` for `sf_auto_thefts_2025`):

### Values

| Step | What | Value |
|---|---|---|
| 2 | incident rows downloaded | |
| 4 | features in `sf_auto_thefts_2025_raw` | |
| 5 | reports with no location | |
| 6a | rows left after *Delete duplicates by attribute* | |
| 6b | duplicate rows removed | |
| 7 | rows with a location | |
| 8 | `thefts_7131` (saved) | |
| 9 | largest `n_same_spot` | |
| 15a | DBSCAN eps 150 m — clusters | |
| 15b | DBSCAN eps 150 m — noise points | |
| 17a | DBSCAN eps 100 m — clusters | |
| 17b | DBSCAN eps 100 m — noise points | |
| 17c | DBSCAN eps 300 m — clusters | |
| 17d | DBSCAN eps 300 m — noise points | |
| 20a | fit sensors | |
| 20b | check sensors | |
| 23 | RMSE, IDW P = 2 (µg/m³) | |
| 24a | RMSE, IDW P = 1 (µg/m³) | |
| 24b | RMSE, IDW P = 3 (µg/m³) | |
| 25a | RMSE, TIN linear (µg/m³) | |
| 25b | check sensors TIN left NULL | |

### Answers in words

- **Step 12** — neighbourhood of the strongest KDE peak:
- **Step 13** — radius for a patrol commander / for a city council, and one sentence why:
- **Step 18** — which eps run I saved as `clusters_7131`, and why:

### Outputs

- [ ] `data/processed/sf_thefts_2025_7131_qgis.gpkg` → layer `thefts_7131`
- [ ] `data/processed/sf_theft_kde_400_qgis.tif`
- [ ] `data/processed/sf_theft_clusters_qgis.gpkg` → layer `clusters_7131`
- [ ] `data/processed/sf_sensors_7131_qgis.gpkg` → layer `sensors_7131`
- [ ] `data/processed/sf_pm25_idw_p2_qgis.tif`, `sf_pm25_idw_error_qgis.tif`
- [ ] `qgis/module3_patterns.qgz`
- [ ] `outputs/maps/module3_theft_hotspots_qgis.png`, `module3_pm25_idw_qgis.png`

### Notes

- Where KDE and DBSCAN agree, and where they don't:
- What surprised me:
- Anything I'm not sure I did right (check it in Pass 2):

---

## Module 4 · Network analysis

**Date completed:**
**OpenStreetMap queried on** (date you ran QuickOSM):
**QNEAT3 version** (Plugins › Manage and Install Plugins › Installed):

### Values

| Step | What | Value |
|---|---|---|
| 5 | `highway_San Francisco` features | |
| 7 | drivable street features | |
| 10a | mean `speed_kmh` | |
| 10b | streets with a posted `maxspeed` (%) | |
| 15 | travel time from Station 7 to City Hall (s) | |
| 19a | 3-minute band area (km²) | |
| 19b | 5-minute band area (km²) | |
| 19c | 7-minute band area (km²) | |
| 19d | 11-minute band area (km²) | |
| 19e | area within 5 minutes, bands 3 + 5 (km²) | |
| 20 | 2.5 km circle area (km²) | |
| 23a | commercial parcels within 3 minutes | |
| 23b | commercial parcels within 5 minutes | |
| 23c | commercial parcels within 7 minutes | |
| 23d | commercial parcels within 11 minutes | |

### Answers in words

- **Step 10** — values that appear in `oneway`:
- **Step 13** — Station 7 start point, exactly as QNEAT3 filled the box:
- **Step 20** — where the circle and the network 5-minute area disagree most:

### Assumptions I made

- Road classes kept (step 7), and service roads left out:
- Speeds (step 9):
- Anything else (one-ways, turn restrictions, traffic):

### Outputs

- [ ] `data/processed/sf_roads_drive_qgis.gpkg` → layer `roads_drive_7131` (with `speed_kmh`) — keep it for Pass 2
- [ ] `data/processed/station7_traveltime_qgis.tif`
- [ ] `data/processed/station7_drivetime_qgis.gpkg` → layer `bands_7131`
- [ ] `qgis/module4_network.qgz`
- [ ] `outputs/maps/module4_station7_drivetime_qgis.png`

### Notes

- What surprised me:
- Anything I'm not sure I did right (check it in Pass 2):

---

## Module 5 · Linear referencing

**Date completed:**
**Data generated on** (`downloaded_utc` for `sf_pipeline_simulated`):

### Values

| Step | What | Value |
|---|---|---|
| 2a | pipeline length the script printed (m) | |
| 2b | markers | |
| 2c | anomalies | |
| 2d | anomalies with wall loss ≥ 50% | |
| 5 | rows in the `anomalies` table | |
| 7 | `length_m` of `pipeline` in EPSG:7131 (m) | |
| 8 | `ratio` at AGM-08 | |
| 12a | largest `err_raw` (m) | |
| 12b | largest `err_cal` (m) | |
| 14 | anomalies on the dig list (`"wall_loss_pct" >= 50`) | |
| 17a | worst segment — `from_m` (m) | |
| 17b | worst segment — `max_loss` (%) | |

### Answers in words

- **Step 14** — dig-list `anomaly_id`s:

### Outputs

- [ ] `data/processed/sf_pipeline_7131_qgis.gpkg` → layers `pipeline_7131`, `markers_7131`
- [ ] `data/processed/sf_pipeline_anomalies_qgis.gpkg` → layer `anomalies_7131`
- [ ] `qgis/module5_lrs.qgz`
- [ ] `outputs/maps/module5_pipeline_qgis.png`

### Notes

- What surprised me:
- Anything I'm not sure I did right (check it in Pass 2):

---

End of Pass 1. Before you start Pass 2, read this whole file once.
