"""
verify_install.py — check that the `spatial-ds` environment is healthy.

Run it from the repo root with the environment active:

    conda activate spatial-ds
    python scripts/verify_install.py

It checks four things, in order of how often they go wrong on Windows:
  1. You are running the environment's Python (not some other Python on your PC).
  2. Every course package imports.
  3. The C libraries underneath (GDAL, GEOS, PROJ) actually work:
     a coordinate transform, a GeoPackage write/read round-trip, a geometry repair.
  4. You can reach the San Francisco open-data portal (needed to download data).

Every line prints PASS / WARN / FAIL. A FAIL tells you what to do next.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

ENV_NAME = "spatial-ds"
results: list[tuple[str, str]] = []  # (status, message)


def report(status: str, message: str) -> None:
    """Print one line and remember it for the summary at the end."""
    results.append((status, message))
    print(f"[{status:<4}] {message}")


# ---------------------------------------------------------------------------
# 1. Which Python is this?
# ---------------------------------------------------------------------------
print("\n1. Python interpreter")
exe = Path(sys.executable)
print(f"       {exe}")
if ENV_NAME in exe.parts or ENV_NAME in os.environ.get("CONDA_DEFAULT_ENV", ""):
    report("PASS", f"running inside the '{ENV_NAME}' environment")
else:
    report(
        "FAIL",
        f"this is not the '{ENV_NAME}' environment. Open 'Miniforge Prompt' and run: "
        f"conda activate {ENV_NAME}",
    )

if sys.version_info[:2] >= (3, 12):
    report("PASS", f"Python {sys.version.split()[0]}")
else:
    report("FAIL", f"Python {sys.version.split()[0]} is too old; the course expects 3.12")

# PROJ_LIB / GDAL_DATA set by some *other* program (PostGIS, an old OSGeo4W, ...)
# silently points pyproj at the wrong database and causes baffling errors.
prefix = Path(sys.prefix).resolve()
for var in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA"):
    value = os.environ.get(var)
    if value and prefix not in Path(value).resolve().parents and Path(value).resolve() != prefix:
        report(
            "WARN",
            f"{var} is set to {value} (outside this environment). If you see PROJ/GDAL "
            f"errors, remove that Windows environment variable — see Phase 0 troubleshooting.",
        )

# ---------------------------------------------------------------------------
# 2. Imports
# ---------------------------------------------------------------------------
print("\n2. Packages")
PACKAGES = [
    # (import name, what it's for[, conda package name if different])
    ("geopandas", "vector data frames"),
    ("pyogrio", "vector file I/O"),
    ("shapely", "geometry engine"),
    ("pyproj", "coordinate systems"),
    ("rasterio", "raster I/O"),
    ("rioxarray", "raster arrays"),
    ("numpy", "arrays"),
    ("pandas", "tables"),
    ("pyarrow", "fast I/O"),
    ("scipy", "science"),
    ("sklearn", "machine learning", "scikit-learn"),
    ("pykrige", "kriging"),
    ("networkx", "graphs"),
    ("osmnx", "street networks"),
    ("matplotlib", "static plots"),
    ("mapclassify", "map classification"),
    ("contextily", "basemaps"),
    ("folium", "web maps"),
    ("plotly", "interactive plots"),
    ("streamlit", "dashboards"),
    ("streamlit_folium", "maps in streamlit", "streamlit-folium"),
    ("jupyterlab", "notebooks"),
    ("requests", "HTTP downloads"),
]
modules = {}
for name, purpose, *conda_name in PACKAGES:
    conda_pkg = conda_name[0] if conda_name else name
    try:
        mod = importlib.import_module(name)
        modules[name] = mod
        version = getattr(mod, "__version__", "?")
        report("PASS", f"{name:<17} {version:<10} ({purpose})")
    except Exception as exc:  # noqa: BLE001 — we want to report *any* failure
        report("FAIL", f"{name:<17} would not import: {exc!r}. Fix: mamba install -c conda-forge {conda_pkg}")

# ---------------------------------------------------------------------------
# 3. The C libraries actually work
# ---------------------------------------------------------------------------
print("\n3. GDAL / GEOS / PROJ smoke tests")
try:
    import geopandas as gpd
    import pyogrio
    import pyproj
    import shapely
    from shapely.geometry import Point, Polygon

    print(
        f"       GDAL {pyogrio.__gdal_version_string__} | "
        f"GEOS {shapely.geos_version_string} | PROJ {pyproj.proj_version_str}"
    )

    # (a) Coordinate transform: Union Square, San Francisco -> Web Mercator.
    t = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x, y = t.transform(-122.4075, 37.7880)
    if abs(x - (-13_626_341)) < 50 and abs(y - 4_549_520) < 50:
        report("PASS", f"PROJ transform lon/lat -> Web Mercator = ({x:,.0f}, {y:,.0f})")
    else:
        report("FAIL", f"PROJ transform gave a strange answer ({x:,.0f}, {y:,.0f})")

    # (b) San Francisco's local coordinate system must be in the PROJ database.
    sf = pyproj.CRS.from_epsg(7131)
    report("PASS", f"EPSG:7131 found: {sf.name}")

    # (c) GeoPackage round trip (write, list layers, read back).
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "smoke_test.gpkg"
        gdf = gpd.GeoDataFrame(
            {"name": ["Union Square"], "is_test": [True]},
            geometry=[Point(-122.4075, 37.7880)],
            crs="EPSG:4326",
        )
        gdf.to_crs(3857).to_file(path, layer="points_3857", driver="GPKG")
        back = gpd.read_file(path, layer="points_3857")
        layers = [row[0] for row in pyogrio.list_layers(path)]
        if len(back) == 1 and back.crs.to_epsg() == 3857 and layers == ["points_3857"]:
            report("PASS", "GeoPackage write -> read round trip")
        else:
            report("FAIL", "GeoPackage round trip returned unexpected results")

    # (d) Geometry repair: a 'bow-tie' polygon is invalid; make_valid should fix it.
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    fixed = shapely.make_valid(bowtie)
    if not bowtie.is_valid and fixed.is_valid:
        report("PASS", "GEOS geometry validation + repair")
    else:
        report("FAIL", "GEOS make_valid did not behave as expected")
except Exception as exc:  # noqa: BLE001
    report("FAIL", f"smoke test crashed: {exc!r}")

# ---------------------------------------------------------------------------
# 4. Network access to DataSF (warning only — you may be offline right now)
# ---------------------------------------------------------------------------
print("\n4. Internet access to the data portal")
try:
    import requests

    r = requests.get(
        "https://data.sf.gov/resource/acdm-wktn.json",
        params={"$select": "count(*)"},
        timeout=20,
    )
    r.raise_for_status()
    n = int(next(iter(r.json()[0].values())))
    report("PASS", f"data.sf.gov reachable — the parcel dataset has {n:,} rows")
except Exception as exc:  # noqa: BLE001
    report("WARN", f"could not reach data.sf.gov ({exc.__class__.__name__}). Needed only for downloads.")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
fails = [m for s, m in results if s == "FAIL"]
warns = [m for s, m in results if s == "WARN"]
print("\n" + "=" * 72)
if fails:
    print(f"{len(fails)} problem(s) to fix before Module 1:")
    for m in fails:
        print(f"  - {m}")
    sys.exit(1)
print(f"Environment is ready.  ({len(warns)} warning(s))")
for m in warns:
    print(f"  - {m}")
