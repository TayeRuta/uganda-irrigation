# Uganda Irrigation: Where It Is Needed and Where Water Is Within Reach

District-by-district analysis of irrigation need and water access across Uganda's 135 districts. It measures how often dry spells and failed seasons hit the growing season (1991–2025), whether they show up in crop condition, and whether rivers, lakes or groundwater lie within reach of the cropland that needs them. Built entirely from public satellite and survey data.

**Read the report: [Where Uganda needs irrigation, and where water is within reach](https://tayeruta.github.io/uganda-irrigation/reports/irrigation_report.html)**

## Key findings

- **Karamoja faces dry spells far more often than anywhere else.** Moroto has a dry spell of 14 days or more in 73% of growing windows, Kaabong 66%, Karenga 57% and Amudat 49%. Across most of Central and Western Uganda it is under 10%.
- **Dry spells cost crops in the North and East, not in the wetter South and West.** In the North and East a two-week dry spell lowers peak crop greenness (NDVI) by about 0.016, roughly half a typical year-to-year swing. In the West it makes no difference; in Central Uganda greenness is slightly higher after a dry spell.
- **Dry-spell risk has not clearly changed since 1991** (+0.4 percentage points a decade, not significant). It fell in Central and rose slightly in the East.
- **29 districts combine high need with water within reach**, mostly in Teso, Busoga's lakeshore, Elgon's foothills and around Lake Kyoga, plus the South-west cattle corridor through groundwater. They hold 22% of mapped cropland and 7.6 million people.
- **34 high-need districts have no easy water**, including almost all of Karamoja: little cropland lies near permanent water and the basement rock gives low-yielding boreholes. Water harvesting and drought-tolerant crops fit better there than pump irrigation.
- **The need ranking is robust** to how dry spells, dry days, seasons and failed seasons are defined (rank correlation 0.82–0.96). The size of the priority list depends on what counts as "within reach": 16 districts under strict rules, 41 under loose ones; all 16 are on the main list.

## Repository structure

```
├── data/
│   ├── raw/
│   │   ├── boundaries/              # district shapefile for Earth Engine, lakes for maps
│   │   └── earth_engine/            # outputs of scripts/gee/*.js (daily rain compressed)
│   └── processed/                   # district results exported by the notebook
├── notebooks/
│   └── 01_irrigation_need_and_potential.ipynb
├── reports/
│   └── irrigation_report.html       # the write-up, published on GitHub Pages
├── scripts/
│   ├── gee/uganda_irrigation_districts_gee.js    # Earth Engine: monthly water balance, NDVI, water access, population
│   ├── gee/uganda_irrigation_rain_daily_gee.js   # Earth Engine: daily rainfall by district
│   ├── fetch_data.py                # downloads boundaries, groundwater maps, FAO irrigation map, lakes
│   ├── irrigation.py                # shared loading and scoring code
│   ├── build_notebooks.py           # generates the notebook from source
│   └── build_report_data.py         # injects the notebook's results into the report
└── requirements.txt
```

## Data and methods

- **Districts.** Uganda's 135 districts (2020 boundaries, OCHA/UBOS). The shapefile is uploaded to Earth Engine as an asset; the scripts summarise every dataset by district.
- **Seasons.** A district has two seasons when its June–August rainfall dip falls below 60% of the smaller of its two peaks (1991–2020), otherwise one long season. Every district is measured over two three-month growing windows (March–May and September–November, or April–June and July–September) so that districts compare fairly.
- **Need.** From daily CHIRPS rainfall: the share of windows with a dry spell of 14 or more days under 2 mm, and the share with under 75% of the window's 1991–2020 median rain. From TerraClimate: the climatic water deficit over the growing windows. The need score averages the three percentile ranks.
- **Crop response.** Peak NDVI over cropland (MODIS Terra and Aqua) in each window, detrended per district, regressed on window rain or a long dry spell, with errors clustered by year.
- **Water within reach.** At least 10% of cropland within 1 km of permanent water (JRC) or a river with mean flow of 1 m³/s or more (HydroSHEDS), or at least half the district where boreholes can yield 1 litre a second or more (British Geological Survey).
- **Robustness.** Ten alternative definitions (season cut-off, dry-day threshold, dry-spell length, failed-window threshold, water thresholds), each fully recomputed.

## Reproducing the analysis

```bash
pip install -r requirements.txt
python scripts/fetch_data.py                 # public downloads; copies Earth Engine CSVs from ~/Downloads
# Earth Engine: upload data/raw/boundaries/uga_districts_2020_shp.zip as an asset, then run both
# scripts in scripts/gee/ and download their CSV exports (instructions at the top of each script)
python scripts/build_notebooks.py
jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb
python scripts/build_report_data.py          # refresh the numbers in the report
```

## Data sources

| Dataset | Provider |
|---|---|
| [CHIRPS daily rainfall](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY) | UC Santa Barbara Climate Hazards Center |
| [TerraClimate](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_TERRACLIMATE) | University of Idaho |
| [MODIS NDVI, MOD13Q1 and MYD13Q1](https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13Q1) | NASA |
| [WorldCover 2021](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200) | European Space Agency |
| [Global Surface Water](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater) | European Commission Joint Research Centre |
| [Free-flowing rivers](https://developers.google.com/earth-engine/datasets/catalog/WWF_HydroSHEDS_v1_FreeFlowingRivers) | WWF HydroSHEDS |
| [SRTM elevation](https://developers.google.com/earth-engine/datasets/catalog/USGS_SRTMGL1_003) | NASA / USGS |
| [WorldPop population 2020](https://developers.google.com/earth-engine/datasets/catalog/WorldPop_GP_100m_pop) | WorldPop |
| [Quantitative groundwater maps of Africa](https://doi.org/10.5285/e37d09e7-6388-494b-99c8-10958d6d78c4) | British Geological Survey. Contains data supplied by permission of the Natural Environment Research Council (Open Government Licence) |
| [Global Map of Irrigation Areas v5](https://www.fao.org/aquastat/en/geospatial-information/global-maps-irrigated-areas/latest-version/) | FAO AQUASTAT |
| [District boundaries](https://data.humdata.org/dataset/cod-ab-uga) | OCHA and UBOS, via HDX |
| [Lakes](https://www.naturalearthdata.com/) | Natural Earth |

## Limitations

- **Cropland.** ESA WorldCover maps most banana and coffee gardens as tree cover, so cropland is undercounted, especially in the South and West. Ten districts have too little mapped cropland to score.
- **Surface water.** Small streams and seasonal swamps are not mapped, so cropland near water is a lower bound.
- **Groundwater.** The BGS maps are continental (5 km); local aquifers can differ, and a site survey is needed before drilling.
- **Rainfall.** District averages smooth local showers; satellite rainfall misses some local storms.
- **Existing irrigation.** FAO's irrigation map dates from about 2005, and there is no public district-level data on the government's micro-scale irrigation programme.

## Related projects

- [Uganda rainfall analysis](https://github.com/TayeRuta/uganda-rainfall-analysis): national, regional and Indian Ocean Dipole analysis of Uganda's rainfall
- [Uganda food prices](https://github.com/TayeRuta/uganda-food-prices): rainfall shocks and food prices
- [Uganda coffee](https://github.com/TayeRuta/uganda-coffee): exports, prices, climate exposure and a global benchmark

## License

Code is released under the MIT License. Data remain under the terms of their original providers.
