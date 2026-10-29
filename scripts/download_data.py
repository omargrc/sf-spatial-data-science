"""
download_data.py — fetch (or generate) the raw datasets for sf-spatial-data-science.

Run from the repo root with the environment active:

    conda activate spatial-ds
    python scripts/download_data.py              # everything not already downloaded
    python scripts/download_data.py --module 2   # only what Module 2 needs
    python scripts/download_data.py --force      # download again, replacing old copies
    python scripts/download_data.py --list       # show the catalogue and exit

Where the data comes from
-------------------------
* DataSF (data.sf.gov), San Francisco's open-data portal, through the Socrata
  "SODA" API. We ask for GeoJSON in pages of 50,000 rows and save ONE
  GeoPackage per dataset.                                   (Modules 1 and 3)
* USGS 3D Elevation Program (3DEP), the national bare-earth elevation model,
  through its public image service.                         (Module 2)
* SIMULATED training data, generated here with a fixed random seed, for the
  two exercises that have no public dataset: an air-quality sensor network
  (Module 3) and a pipeline inspection survey (Module 5). Every simulated file
  has "simulated" in its name and in its attributes. Never present them as
  real measurements.
* Module 4's street network and fire stations come from OpenStreetMap inside
  QGIS (QuickOSM plugin), so there is nothing to download for it here.

"Raw" means untouched: every row and column as published, in the publisher's
coordinate system (EPSG:4326, longitude/latitude). All cleaning happens later,
in QGIS or the notebooks, where you can see it.

data/raw/ is listed in .gitignore, so these files never go to GitHub.
download_manifest.json records where and when each file came from.

Optional: DataSF throttles anonymous users. If downloads stall, create a free
"app token" at data.sf.gov (Sign in > Developer settings) and set it first:
    set SODA_APP_TOKEN=your_token_here          (Windows cmd / Miniforge Prompt)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Catalogue of datasets
# ---------------------------------------------------------------------------
DATASETS: dict[str, dict] = {
    # ---- Module 1 ------------------------------------------------------------
    "sf_parcels": {
        "module": 1,
        "kind": "soda",
        "title": "Parcels – Active and Retired",
        "dataset_id": "acdm-wktn",
        "out": "data/raw/sf_parcels_raw.gpkg",
        "layer": "parcels",
    },
    "sf_zoning_districts": {
        "module": 1,
        "kind": "soda",
        "title": "Zoning Map – Zoning Districts",
        "dataset_id": "3i4a-hu95",
        "out": "data/raw/sf_zoning_districts_raw.gpkg",
        "layer": "zoning_districts",
    },
    # ---- Module 2 ------------------------------------------------------------
    "sf_dem": {
        "module": 2,
        "kind": "dem_3dep",
        "title": "USGS 3DEP bare-earth elevation, 1/3 arc-second (~10 m)",
        "out": "data/raw/sf_dem_3dep_raw.tif",
    },
    # ---- Module 3 ------------------------------------------------------------
    "sf_auto_thefts_2025": {
        "module": 3,
        "kind": "soda",
        "title": "SFPD Incident Reports: Motor Vehicle Theft, calendar year 2025",
        "dataset_id": "wg3w-h783",
        "where": (
            "incident_category = 'Motor Vehicle Theft' "
            "AND incident_date >= '2025-01-01T00:00:00' "
            "AND incident_date < '2026-01-01T00:00:00'"
        ),
        "select": (
            "incident_id, incident_number, incident_code, incident_datetime, incident_date, "
            "incident_time, incident_day_of_week, report_datetime, report_type_description, "
            "incident_category, incident_subcategory, incident_description, resolution, "
            "intersection, police_district, analysis_neighborhood, latitude, longitude, point"
        ),
        "out": "data/raw/sf_auto_thefts_2025_raw.gpkg",
        "layer": "incidents",
    },
    "sf_air_sensors_simulated": {
        "module": 3,
        "kind": "simulated_sensors",
        "title": "SIMULATED PM2.5 sensor network (training data, not real measurements)",
        "requires": "sf_parcels",
        "out": "data/raw/sf_air_sensors_simulated.gpkg",
        "layer": "sensors",
        "truth": "data/raw/sf_pm25_truth_simulated.tif",
    },
    # ---- Module 5 ------------------------------------------------------------
    "sf_pipeline_simulated": {
        "module": 5,
        "kind": "simulated_pipeline",
        "title": "SIMULATED trunk main and in-line inspection survey (training data)",
        "out": "data/raw/sf_pipeline_simulated.gpkg",
        "csv": "data/raw/sf_pipeline_inspection_simulated.csv",
    },
}

NOTHING_TO_DOWNLOAD = {
    4: "Module 4's streets and fire stations come from OpenStreetMap inside QGIS (QuickOSM plugin).",
}

DEFAULT_BASE_URL = "https://data.sf.gov"
DEM_SERVICE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
PAGE_SIZE = 50_000          # rows per SODA request
SOURCE_CRS = "EPSG:4326"    # SODA serves GeoJSON as WGS 84 lon/lat
MEASURE_CRS = "EPSG:7131"   # NAD83(2011) / San Francisco CS13, metres
SEED = 20261020             # fixed, so everyone gets the same simulated data
REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "data" / "raw" / "download_manifest.json"

# San Francisco, with a margin of ocean and bay (lon/lat). Includes Treasure Island.
SF_BBOX = (-122.53, 37.70, -122.35, 37.84)
DEM_RES_DEG = 1 / 10800     # 1/3 arc-second, the resolution of the national 3DEP product


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def make_session() -> requests.Session:
    """A requests session that retries politely on timeouts and server hiccups."""
    session = requests.Session()
    retry = Retry(
        total=6,
        backoff_factor=2,  # waits 2s, 4s, 8s, ... between attempts
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "sf-spatial-data-science-course/1.0"
    token = os.environ.get("SODA_APP_TOKEN")
    if token:
        session.headers["X-App-Token"] = token
    return session


# ---------------------------------------------------------------------------
# DataSF (SODA)
# ---------------------------------------------------------------------------
def row_count(session: requests.Session, base_url: str, spec: dict) -> int:
    """Ask the API how many rows match (so we can show progress)."""
    params = {"$select": "count(*)"}
    if spec.get("where"):
        params["$where"] = spec["where"]
    r = session.get(f"{base_url}/resource/{spec['dataset_id']}.json", params=params, timeout=(15, 120))
    r.raise_for_status()
    first_row = r.json()[0]
    return int(next(iter(first_row.values())))


def fetch_page(session: requests.Session, base_url: str, spec: dict, offset: int) -> list[dict]:
    """Download one page of GeoJSON features.

    `$order=:id` sorts by Socrata's internal row id so that pages never overlap
    or skip rows — paging without a stable sort order is a classic API bug.
    """
    params = {"$limit": PAGE_SIZE, "$offset": offset, "$order": ":id"}
    if spec.get("where"):
        params["$where"] = spec["where"]
    if spec.get("select"):
        params["$select"] = spec["select"]
    r = session.get(f"{base_url}/resource/{spec['dataset_id']}.geojson", params=params, timeout=(15, 600))
    r.raise_for_status()
    return r.json().get("features", [])


def normalise_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Give every attribute column one consistent type before writing.

    SODA sends numbers and dates as text and true/false as JSON booleans.
    We keep that: genuine boolean columns stay boolean, everything else is
    stored as text. Parsing numbers and dates is a cleaning decision, so it
    belongs in QGIS or the notebooks, not in the downloader.
    """
    for col in gdf.columns:
        if col == gdf.geometry.name:
            continue
        values = gdf[col]
        present = values.dropna()
        if len(present) == len(values) and len(present) > 0 and present.map(type).eq(bool).all():
            gdf[col] = values.astype(bool)
        else:
            gdf[col] = values.map(
                lambda v: None if v is None or (isinstance(v, float) and math.isnan(v)) else str(v)
            ).astype(object)
    return gdf


def download_soda(session: requests.Session, base_url: str, spec: dict) -> dict:
    """Download one DataSF dataset, page by page, and save it as a GeoPackage."""
    out_path = REPO_ROOT / spec["out"]
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n>> {spec['title']}  [{spec['dataset_id']}]")
    expected = row_count(session, base_url, spec)
    n_pages = max(1, math.ceil(expected / PAGE_SIZE))
    print(f"   {expected:,} rows reported by the API -> {n_pages} page(s) of up to {PAGE_SIZE:,}")

    frames: list[gpd.GeoDataFrame] = []
    offset, page = 0, 0
    t0 = time.perf_counter()
    while True:
        page += 1
        features = fetch_page(session, base_url, spec, offset)
        if not features:
            break
        frames.append(gpd.GeoDataFrame.from_features(features, crs=SOURCE_CRS))
        offset += len(features)
        print(f"   page {page}: {offset:,} / {expected:,} rows  ({time.perf_counter() - t0:,.0f}s)")
        if len(features) < PAGE_SIZE:
            break

    if not frames:
        raise RuntimeError(f"The API returned no rows for {spec['dataset_id']}.")

    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=SOURCE_CRS)
    gdf = normalise_columns(gdf)

    if len(gdf) != expected:
        # DataSF updates some layers daily; a small mismatch mid-download is normal.
        print(f"   note: got {len(gdf):,} rows vs {expected:,} expected (dataset may have updated)")

    if out_path.exists():
        out_path.unlink()  # start clean so no stale layers survive
    gdf.to_file(out_path, layer=spec["layer"], driver="GPKG", engine="pyogrio")
    size_mb = out_path.stat().st_size / 1e6
    print(f"   saved {out_path.relative_to(REPO_ROOT)}  (layer '{spec['layer']}', {size_mb:,.1f} MB)")

    return {
        "title": spec["title"],
        "dataset_id": spec["dataset_id"],
        "source": f"{base_url}/resource/{spec['dataset_id']}.geojson",
        "filter": spec.get("where"),
        "landing_page": f"{base_url}/d/{spec['dataset_id']}",
        "file": spec["out"],
        "layer": spec["layer"],
        "rows": int(len(gdf)),
        "crs": SOURCE_CRS,
        "downloaded_utc": now_utc(),
    }


# ---------------------------------------------------------------------------
# USGS 3DEP elevation
# ---------------------------------------------------------------------------
def download_dem(session: requests.Session, spec: dict, service: str = DEM_SERVICE) -> dict:
    """Export a 1/3 arc-second bare-earth DEM of San Francisco from the USGS 3DEP image service.

    We ask the service for raw elevation ("None" raster function, 32-bit float) on a
    longitude/latitude grid — the same grid as the national 1/3 arc-second product —
    and save it as a GeoTIFF in EPSG:4326. Elevation is in metres (NAVD88).
    """
    import warnings

    import rasterio
    from rasterio.errors import NotGeoreferencedWarning
    from rasterio.io import MemoryFile
    from rasterio.transform import from_bounds

    out_path = REPO_ROOT / spec["out"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    xmin, ymin, xmax, ymax = SF_BBOX
    width = round((xmax - xmin) / DEM_RES_DEG)
    height = round((ymax - ymin) / DEM_RES_DEG)

    print(f"\n>> {spec['title']}")
    print(f"   asking USGS for {width:,} x {height:,} cells over {SF_BBOX}")
    params = {
        "bbox": f"{xmin},{ymin},{xmax},{ymax}",
        "bboxSR": 4326,
        "imageSR": 4326,
        "size": f"{width},{height}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        "renderingRule": json.dumps({"rasterFunction": "None"}),  # raw elevation, no hillshade etc.
        "f": "json",                                               # metadata + a link to the file
    }
    r = session.get(service, params=params, timeout=(15, 300))
    r.raise_for_status()
    meta = r.json()
    if "href" not in meta:
        raise RuntimeError(f"USGS service did not return an image: {meta.get('error', meta)}")

    img = session.get(meta["href"], timeout=(15, 600))
    img.raise_for_status()

    # Georeference from the extent the service says it used — the TIFF's own tags are not
    # always present, and the service may round the extent slightly.
    ext = meta["extent"]
    w, h = int(meta["width"]), int(meta["height"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)  # we georeference it ourselves below
        with MemoryFile(img.content) as mem, mem.open() as src:
            data = src.read(1).astype("float32")
            src_nodata = src.nodata

    nodata = -9999.0
    bad = ~np.isfinite(data) | (data < -500) | (data > 5000)
    if src_nodata is not None:
        bad |= data == np.float32(src_nodata)
    data[bad] = nodata

    profile = {
        "driver": "GTiff", "width": w, "height": h, "count": 1, "dtype": "float32",
        "crs": "EPSG:4326", "transform": from_bounds(ext["xmin"], ext["ymin"], ext["xmax"], ext["ymax"], w, h),
        "nodata": nodata, "compress": "deflate", "tiled": True,
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(data, 1)
        dst.update_tags(SOURCE="USGS 3DEP 3DEPElevation ImageServer (bare earth)", UNITS="metres, NAVD88")

    valid = data[~bad]
    print(f"   elevation range {valid.min():.1f} to {valid.max():.1f} m over {valid.size:,} cells")
    if valid.size == 0 or valid.max() < 150 or valid.max() > 600:
        print("   WARNING: that range doesn't look like San Francisco (highest point ~280 m). Check the file.")
    print(f"   saved {out_path.relative_to(REPO_ROOT)}  ({out_path.stat().st_size / 1e6:,.1f} MB)")

    return {
        "title": spec["title"],
        "source": service,
        "request": {k: v for k, v in params.items() if k != "f"},
        "file": spec["out"],
        "cells": [w, h],
        "crs": "EPSG:4326",
        "units": "metres (NAVD88)",
        "downloaded_utc": now_utc(),
    }


# ---------------------------------------------------------------------------
# Simulated data (Modules 3 and 5)
# ---------------------------------------------------------------------------
def _to_xy(lon: float, lat: float) -> tuple[float, float]:
    from pyproj import Transformer

    t = Transformer.from_crs("EPSG:4326", MEASURE_CRS, always_xy=True)
    return t.transform(lon, lat)


def pm25_truth(x: np.ndarray, y: np.ndarray, x_west: float, x_east: float) -> np.ndarray:
    """The simulated 'true' annual-mean PM2.5 surface (µg/m³) at EPSG:7131 coordinates.

    A plausible shape, not a real one: cleaner on the ocean side, dirtier towards the bay,
    three local hotspots (a freeway interchange, an industrial waterfront, downtown), and a
    smooth random texture so that interpolation has something to get wrong.
    """
    rng = np.random.default_rng(SEED)
    east = np.clip((x - x_west) / (x_east - x_west), 0, 1)
    z = 5.5 + 2.2 * east
    for lon, lat, amp, sigma in [(-122.4040, 37.7700, 3.0, 700.0),    # freeway interchange
                                 (-122.3900, 37.7330, 2.4, 900.0),    # industrial waterfront
                                 (-122.4000, 37.7920, 1.5, 600.0)]:   # downtown
        hx, hy = _to_xy(lon, lat)
        z = z + amp * np.exp(-((x - hx) ** 2 + (y - hy) ** 2) / (2 * sigma ** 2))
    for _ in range(24):  # smooth random texture: a sum of long-wavelength waves
        wavelength = rng.uniform(2_000, 6_000)
        angle = rng.uniform(0, np.pi)
        kx, ky = np.cos(angle) * 2 * np.pi / wavelength, np.sin(angle) * 2 * np.pi / wavelength
        z = z + rng.normal(0, 0.22) * np.cos(kx * x + ky * y + rng.uniform(0, 2 * np.pi))
    return np.maximum(z, 2.0)


def make_simulated_sensors(spec: dict) -> dict:
    """72 simulated PM2.5 sensors on land (52 to fit models, 20 held back to check them),
    plus the 'true' surface as a 50 m GeoTIFF so interpolation errors can be measured."""
    import rasterio
    from rasterio.transform import from_origin

    parcels_path = REPO_ROOT / DATASETS[spec["requires"]]["out"]
    if not parcels_path.exists():
        raise RuntimeError("the sensors are placed on parcels: run  python scripts/download_data.py --module 1  first")

    print(f"\n>> {spec['title']}")
    parcels = gpd.read_file(parcels_path, layer="parcels", columns=["active"], engine="pyogrio")
    parcels = parcels[parcels["active"].astype(bool) & parcels.geometry.notna() & ~parcels.geometry.is_empty]
    sites = parcels.to_crs(MEASURE_CRS).geometry.representative_point()
    x_all, y_all = sites.x.to_numpy(), sites.y.to_numpy()

    # Spread the sensors out: take candidates in random order, keep one only if it is at
    # least `spacing` metres from every sensor kept so far (relaxing the spacing if needed).
    rng = np.random.default_rng(SEED)
    order = rng.permutation(len(x_all))
    for spacing in (800.0, 600.0, 450.0, 300.0):
        kept: list[int] = []
        for i in order:
            if not kept or np.min((x_all[kept] - x_all[i]) ** 2 + (y_all[kept] - y_all[i]) ** 2) >= spacing ** 2:
                kept.append(int(i))
                if len(kept) == 72:
                    break
        if len(kept) == 72:
            break
    kx, ky = x_all[kept], y_all[kept]

    x_west, x_east = float(np.percentile(x_all, 1)), float(np.percentile(x_all, 99))
    truth_at_sensor = pm25_truth(kx, ky, x_west, x_east)
    measured = np.round(truth_at_sensor + rng.normal(0, 0.3, len(kept)), 1)  # sensor noise
    n_fit = round(len(kept) * 52 / 72)
    roles = np.array(["fit"] * n_fit + ["check"] * (len(kept) - n_fit))
    rng.shuffle(roles)

    sensors = gpd.GeoDataFrame(
        {
            "sensor_id": [f"PM-{k + 1:02d}" for k in range(len(kept))],
            "role": roles,
            "pm25_ugm3": measured,
            "data_note": "SIMULATED training data - not real air-quality measurements",
        },
        geometry=gpd.points_from_xy(kx, ky),
        crs=MEASURE_CRS,
    ).to_crs(SOURCE_CRS)

    out_path = REPO_ROOT / spec["out"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    sensors.to_file(out_path, layer=spec["layer"], driver="GPKG", engine="pyogrio")

    # The 'true' surface on a 50 m grid in EPSG:7131.
    xmin, ymin, xmax, ymax = parcels.to_crs(MEASURE_CRS).total_bounds
    cell = 50.0
    xmin, ymin = math.floor(xmin / cell) * cell - 500, math.floor(ymin / cell) * cell - 500
    xmax, ymax = math.ceil(xmax / cell) * cell + 500, math.ceil(ymax / cell) * cell + 500
    ncol, nrow = int((xmax - xmin) / cell), int((ymax - ymin) / cell)
    gx, gy = np.meshgrid(xmin + cell * (np.arange(ncol) + 0.5), ymax - cell * (np.arange(nrow) + 0.5))
    truth = pm25_truth(gx, gy, x_west, x_east).astype("float32")
    truth_path = REPO_ROOT / spec["truth"]
    with rasterio.open(truth_path, "w", driver="GTiff", width=ncol, height=nrow, count=1, dtype="float32",
                       crs=MEASURE_CRS, transform=from_origin(xmin, ymax, cell, cell), nodata=-9999.0,
                       compress="deflate") as dst:
        dst.write(truth, 1)
        dst.update_tags(NOTE="SIMULATED 'true' PM2.5 surface (ug/m3) for the course - not real data")

    print(f"   {len(sensors)} sensors ({(roles == 'fit').sum()} fit / {(roles == 'check').sum()} check), "
          f"PM2.5 {measured.min():.1f}-{measured.max():.1f} µg/m³")
    print(f"   saved {out_path.relative_to(REPO_ROOT)} and {truth_path.relative_to(REPO_ROOT)}")
    return {
        "title": spec["title"], "source": "generated by scripts/download_data.py (simulated)", "seed": SEED,
        "file": spec["out"], "layer": spec["layer"], "truth_raster": spec["truth"], "rows": int(len(sensors)),
        "crs": SOURCE_CRS, "downloaded_utc": now_utc(),
    }


# A plausible route on land: north along Sunset Blvd, then east along Lincoln Way (lon, lat).
PIPE_ROUTE = [
    (-122.4930, 37.7275), (-122.4942, 37.7330), (-122.4946, 37.7400), (-122.4948, 37.7480),
    (-122.4950, 37.7560), (-122.4950, 37.7630), (-122.4948, 37.7648), (-122.4900, 37.7650),
    (-122.4820, 37.7652), (-122.4770, 37.7654), (-122.4700, 37.7656), (-122.4640, 37.7657),
    (-122.4580, 37.7658), (-122.4545, 37.7660),
]
TOOL_STRETCH = 1.0062   # the inspection tool's odometer over-reads distance by 0.62 %


def make_simulated_pipeline(spec: dict) -> dict:
    """A simulated trunk main, its above-ground reference markers, and an in-line
    inspection (ILI) anomaly list whose distances come from the tool's odometer."""
    from shapely.geometry import LineString

    print(f"\n>> {spec['title']}")
    rng = np.random.default_rng(SEED + 5)
    line_xy = LineString([_to_xy(lon, lat) for lon, lat in PIPE_ROUTE])
    length = line_xy.length

    pipe = gpd.GeoDataFrame(
        {"pipe_id": ["SIM-TM-01"], "name": ["Simulated Sunset trunk main"], "diameter_mm": [610],
         "material": ["steel"], "install_year": [1962],
         "data_note": ["SIMULATED training data - not a real utility asset"]},
        geometry=[line_xy], crs=MEASURE_CRS,
    )

    # Reference markers every 1,000 m plus the receiver at the far end.
    marker_s = [*np.arange(0, length, 1000.0), length]
    markers = gpd.GeoDataFrame(
        {"marker_id": [f"AGM-{k:02d}" for k in range(len(marker_s))],
         "pipe_id": "SIM-TM-01",
         "tool_distance_m": [round(s * TOOL_STRETCH + rng.normal(0, 0.3), 2) if s else 0.0 for s in marker_s]},
        geometry=[line_xy.interpolate(s) for s in marker_s], crs=MEASURE_CRS,
    )

    # Anomalies: background corrosion along the whole line, plus a corroded stretch near 5.2 km.
    n_bg, n_hot = 48, 16
    s_true = np.sort(np.concatenate([rng.uniform(20, length - 20, n_bg), rng.uniform(5_050, 5_400, n_hot)]))
    kinds = rng.choice(["metal loss", "dent", "girth weld anomaly"], size=len(s_true), p=[0.72, 0.14, 0.14])
    hot = (s_true >= 5_050) & (s_true <= 5_400)
    kinds[hot] = "metal loss"
    wall_loss = np.where(kinds == "metal loss", np.round(10 + 45 * rng.beta(1.6, 4.0, len(s_true)), 1), np.nan)
    wall_loss[hot] = np.round(np.clip(wall_loss[hot] + 26, 0, 78), 1)
    hours = rng.integers(1, 13, len(s_true))
    minutes = rng.choice([0, 15, 30, 45], len(s_true))
    anomalies = pd.DataFrame({
        "anomaly_id": [f"A{k + 1:03d}" for k in range(len(s_true))],
        "pipe_id": "SIM-TM-01",
        "tool_distance_m": np.round(s_true * TOOL_STRETCH + rng.normal(0, 0.4, len(s_true)), 2),
        "feature_type": kinds,
        "wall_loss_pct": wall_loss,
        "clock_position": [f"{h}:{m:02d}" for h, m in zip(hours, minutes)],
        "data_note": "SIMULATED training data",
    })

    out_path = REPO_ROOT / spec["out"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    pipe.to_crs(SOURCE_CRS).to_file(out_path, layer="pipeline", driver="GPKG", engine="pyogrio")
    markers.to_crs(SOURCE_CRS).to_file(out_path, layer="markers", driver="GPKG", engine="pyogrio")
    csv_path = REPO_ROOT / spec["csv"]
    anomalies.to_csv(csv_path, index=False)

    print(f"   pipeline {length:,.0f} m, {len(markers)} markers, {len(anomalies)} anomalies "
          f"({int((wall_loss >= 50).sum())} with wall loss >= 50%)")
    print(f"   saved {out_path.relative_to(REPO_ROOT)} (layers 'pipeline', 'markers') and "
          f"{csv_path.relative_to(REPO_ROOT)}")
    return {
        "title": spec["title"], "source": "generated by scripts/download_data.py (simulated)", "seed": SEED + 5,
        "file": spec["out"], "layers": ["pipeline", "markers"], "csv": spec["csv"], "crs": SOURCE_CRS,
        "downloaded_utc": now_utc(),
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download raw course data into data/raw/.")
    parser.add_argument("--module", type=int, help="only datasets used by this module number")
    parser.add_argument("--force", action="store_true", help="re-download files that already exist")
    parser.add_argument("--list", action="store_true", help="list the catalogue and exit")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)
    parser.add_argument("--dem-service", default=DEM_SERVICE, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.list:
        for key, spec in DATASETS.items():
            print(f"Module {spec['module']}: {key:<26} {spec['title']}")
        for module, note in NOTHING_TO_DOWNLOAD.items():
            print(f"Module {module}: {note}")
        return 0

    if args.module in NOTHING_TO_DOWNLOAD:
        print(NOTHING_TO_DOWNLOAD[args.module], "Nothing to download.")
        return 0
    wanted = {k: v for k, v in DATASETS.items() if args.module in (None, v["module"])}
    if not wanted:
        print(f"No datasets registered for module {args.module}.")
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    session = make_session()
    failures = []
    for key, spec in wanted.items():
        target = REPO_ROOT / spec["out"]
        if target.exists() and not args.force:
            print(f"\n>> {spec['title']}: already have {spec['out']} (use --force to refresh)")
            continue
        try:
            kind = spec["kind"]
            if kind == "soda":
                manifest[key] = download_soda(session, args.base_url.rstrip("/"), spec)
            elif kind == "dem_3dep":
                manifest[key] = download_dem(session, spec, args.dem_service)
            elif kind == "simulated_sensors":
                manifest[key] = make_simulated_sensors(spec)
            elif kind == "simulated_pipeline":
                manifest[key] = make_simulated_pipeline(spec)
            else:
                raise RuntimeError(f"unknown dataset kind {kind!r}")
            MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        except (requests.RequestException, RuntimeError, OSError) as exc:
            failures.append(key)
            print(f"   FAILED: {exc}")

    print()
    if failures:
        print(f"{len(failures)} download(s) failed: {', '.join(failures)}. Re-run the same command to retry.")
        return 1
    print("All requested datasets are in data/raw/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
