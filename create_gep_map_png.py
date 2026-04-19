"""Create a static polygon choropleth map of 2019 GEP levels by country."""

import os
import sys

import pandas as pd

try:
    import geopandas as gpd
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print("Installing required packages...")
    import subprocess

    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-q", "geopandas", "matplotlib", "numpy"]
    )
    import geopandas as gpd
    import matplotlib.pyplot as plt
    import numpy as np

os.chdir(r"e:\GEP\gep_own_consumption")

WORLD_URL = "https://naciscdn.org/naturalearth/50m/cultural/ne_50m_admin_0_countries.zip"
MANUAL_ISO_MAP = {
    "United Republic of Tanzania": "TZA",
    "Bolivia (Plurinational State of)": "BOL",
}


df_avg = pd.read_csv("results/gep-average-by-country.csv")
iso_lookup = pd.read_csv("input/ISO-3-codes.csv")[['name', 'alpha-3']].rename(
    columns={"name": "Country", "alpha-3": "iso_a3"}
)

df_avg = df_avg.merge(iso_lookup, on="Country", how="left")
df_avg["iso_a3"] = df_avg["iso_a3"].fillna(df_avg["Country"].map(MANUAL_ISO_MAP))
df_avg["gep_plot"] = np.log10(df_avg["avg_gep_2019usd"].clip(lower=0) + 1)

print(f"Loaded {len(df_avg)} countries with 2019 GEP data")

world = gpd.read_file(WORLD_URL)
world = world[~world["CONTINENT"].isin(["Antarctica", "Seven seas (open ocean)"])].copy()
world = world.rename(columns={"ISO_A3": "iso_a3", "NAME": "country_name"})

world_merged = world.merge(df_avg[["Country", "iso_a3", "avg_gep_2019usd", "gep_plot"]], on="iso_a3", how="left")

matched = int(world_merged["avg_gep_2019usd"].notna().sum())
unmatched = df_avg.loc[~df_avg["iso_a3"].isin(set(world_merged["iso_a3"].dropna())), ["Country", "iso_a3"]]
if not unmatched.empty:
    print("Unmatched countries:")
    print(unmatched.to_string(index=False))

fig, ax = plt.subplots(1, 1, figsize=(18, 10), facecolor="white")

plot_kwargs = {
    "ax": ax,
    "column": "gep_plot",
    "cmap": "YlGn",
    "linewidth": 0.25,
    "edgecolor": "#f7f7f7",
    "legend": True,
    "missing_kwds": {
        "color": "#d9d9d9",
        "edgecolor": "#ffffff",
        "linewidth": 0.25,
        "label": "No data",
    },
    "legend_kwds": {
        "label": "2019 GEP (2019 USD)",
        "orientation": "horizontal",
        "pad": 0.02,
        "shrink": 0.72,
    },
}

world_merged.plot(**plot_kwargs)

ax.set_axis_off()
ax.set_title(
    "Global Subsistence-Crop GEP by Country, 2019",
    fontsize=18,
    fontweight="bold",
    pad=14,
)

colorbar_axis = fig.axes[-1]
values_with_data = world_merged.loc[world_merged["gep_plot"].notna(), "gep_plot"]
tick_values = [0, 100, 10_000, 1_000_000, 100_000_000, 1_000_000_000]
tick_positions = [np.log10(value + 1) for value in tick_values]
tick_pairs = [
    (position, label)
    for position, label in zip(tick_positions, ["$0", "$100", "$10K", "$1M", "$100M", "$1B"])
    if values_with_data.min() <= position <= values_with_data.max()
]
tick_positions = [position for position, _label in tick_pairs]
tick_labels = [_label for _position, _label in tick_pairs]
colorbar_axis.set_xticks(tick_positions)
colorbar_axis.set_xticklabels(tick_labels)
colorbar_axis.tick_params(labelsize=10)
colorbar_axis.xaxis.label.set_size(11)
colorbar_axis.set_xlim(values_with_data.min(), values_with_data.max())

fig.text(
    0.5,
    0.04,
    f"Countries with missing 2019 GEP values are shown in gray. The map includes {matched} matched country polygons.",
    ha="center",
    fontsize=10,
)

for output_file in ["output/gep_2019_map.png", "output/gep_2019_map.pdf"]:
    plt.savefig(output_file, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    file_size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"Saved {output_file} ({file_size_mb:.2f} MB)")

plt.close(fig)
print(f"Map includes {matched} countries with matched 2019 GEP data")
