# San Francisco Spatial Data Science

<!-- PORTFOLIO TEMPLATE: replace everything in [square brackets] and delete these comments as you go. -->

**An end-to-end, open-source spatial analytics portfolio on San Francisco** — from raw city parcel data to a live web dashboard, using QGIS, Python (GeoPandas, scikit-learn, OSMnx), deep learning (SAM-Geo), and Streamlit.

**Live dashboard:** [link — added in Module 8]  ·  **Author:** [Your Name] · [LinkedIn / email]

**How it was built.** Modules 1–5 were each done twice: first by hand in QGIS, then rebuilt as a tested Python pipeline whose results were checked against the QGIS output. Modules 6–8 build on that pipeline with machine learning, deep learning and a deployed web app.

![Commercially zoned parcels in San Francisco](outputs/maps/module1_commercial_parcels.png)

---

## What this project answers

| # | Question | Technique | Status |
|---|---|---|---|
| 1 | Where is San Francisco's commercially zoned land? | Vector data engineering, CRS management | ✅ |
| 2 | Which commercial parcels sit on flat ground (< 5° slope)? | Raster slope, reclassification, overlay | ⏳ |
| 3 | Where do auto thefts cluster, and how do interpolation methods compare? | Kernel density, DBSCAN, IDW vs. ordinary kriging | ⏳ |
| 4 | What can a fire station reach in 3, 5, 7 and 11 minutes? | Network analysis, drive-time isochrones | ⏳ |
| 5 | Where along a pipeline are the inspection anomalies? | Linear referencing | ⏳ |
| 6 | Do incidents cluster in space *and* time? | Spatio-temporal DBSCAN, space-time cube | ⏳ |
| 7 | Can we map land cover and infrastructure from imagery? | Unsupervised vs. supervised ML, zero-shot segmentation | ⏳ |
| 8 | How do decision-makers explore all of this? | Streamlit + Folium dashboard | ⏳ |

---

## Module 1 — Commercial parcel inventory

**Goal.** Build a clean, map-ready layer of every commercially zoned parcel in San Francisco.

**Data.** DataSF [Parcels – Active and Retired](https://data.sf.gov/d/acdm-wktn) and [Zoning Map – Zoning Districts](https://data.sf.gov/d/3i4a-hu95).

**Key decisions**
- **"Commercial"** = the Planning Department's general category *Commercial* (`gen` field). Neighborhood Commercial districts, which Planning classes as *Mixed Use*, are excluded. [Add your comparison from stretch exercise S1 here.]
- **Retired parcels** removed (the layer keeps history, so old and new parcels overlap).
- **Condominium stacks** collapsed to one row per ground footprint (`mapblklot`), keeping a lot count — otherwise one tower counts as hundreds of parcels.
- **Split-zoned parcels** kept if *any* of their zoning codes is commercial.
- **Invalid geometries** repaired with `make_valid` and forced to MultiPolygon.
- **Areas** measured in EPSG:7131 (San Francisco's low-distortion grid). The deliverable is stored in Web Mercator (EPSG:3857) for web mapping, which would overstate areas here by about 60%.

**Result.** [N] commercial footprints covering [N] acres. [Paste the summary table from the notebook.]

**QGIS cross-check.** [Did the QGIS and Python results agree? Give the footprint counts from each and explain any difference.]

**Notebook:** [`notebooks/01_vector_data_engineering.ipynb`](notebooks/01_vector_data_engineering.ipynb) · **QGIS project:** [`qgis/module1_vector.qgz`](qgis/module1_vector.qgz)

---

## Reproduce it

Requires [Miniforge](https://conda-forge.org/download/) (conda/mamba) and Git.

```bash
git clone https://github.com/[your-username]/sf-spatial-data-science.git
cd sf-spatial-data-science
mamba env create -f environment.yml
conda activate spatial-ds
python scripts/verify_install.py      # checks the environment
python scripts/download_data.py       # fetches raw data into data/raw/ (not tracked by git)
jupyter lab                           # then run the notebooks in order
```

## Repository layout

```
sf-spatial-data-science/
├── environment.yml        # conda environment (all packages from conda-forge)
├── scripts/
│   ├── download_data.py   # DataSF + USGS downloads, simulated data  →  data/raw/
│   └── verify_install.py  # environment health check
├── notebooks/             # one notebook per module — the technical write-up
├── data/
│   ├── raw/               # downloaded, untouched (git-ignored)
│   └── processed/         # cleaned outputs (git-ignored)
├── outputs/maps/          # static maps embedded in this README
├── qgis/                  # QGIS projects + pass1_log.md from the manual (QGIS) pass
└── app/                   # Streamlit dashboard (Module 8)
```

## Tools

QGIS 3.44 LTR · Python 3.12 · GeoPandas · Shapely · pyproj · Rasterio · scikit-learn · PyKrige · OSMnx · SAM-Geo · Plotly · Folium · Streamlit

## Data credits

City and County of San Francisco, [DataSF](https://data.sf.gov) (Open Data Commons PDDL). Elevation: U.S. Geological Survey [3D Elevation Program](https://www.usgs.gov/3d-elevation-program) (public domain). Streets and fire stations: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL). Basemap tiles © Esri and © OpenStreetMap contributors.

The air-quality sensors (Module 3) and the pipeline inspection (Module 5) are **simulated** training data generated by `scripts/download_data.py`; they are not real measurements.
