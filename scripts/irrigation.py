"""
Shared loading code for the irrigation project. Used by the notebooks and build_report_data.py.

District keys are the 2020 OCHA/UBOS district codes (adm2_pcode), the same ones the Earth Engine
script exports.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath

ROOT = Path(__file__).resolve().parent.parent
RAW, PROC = ROOT / 'data' / 'raw', ROOT / 'data' / 'processed'
BBOX = (29.4, 35.1, -1.6, 4.4)    # lon min, lon max, lat min, lat max

# BGS classes, low to high, with the midpoint used for district averages
GW_PRODUCTIVITY = {'VL': 0.05, 'L': 0.3, 'LM': 0.75, 'M': 3, 'H': 12.5, 'VH': 25}      # litres/second
GW_DEPTH = {'VS': 3.5, 'S': 16, 'SM': 37.5, 'M': 75, 'D': 175, 'VD': 300}             # metres below ground
GW_STORAGE = {'0': 0, 'L': 500, 'LM': 5500, 'M': 17500, 'H': 37500, 'VH': 60000}      # mm of water


def load_districts():
    """135 districts: code, name, region and polygon rings (outer rings only; Uganda's districts have no holes that matter at 5 km)."""
    g = json.loads((RAW / 'boundaries' / 'uga_admin2.geojson').read_text())
    rows = []
    for f in g['features']:
        p, geom = f['properties'], f['geometry']
        polys = geom['coordinates'] if geom['type'] == 'MultiPolygon' else [geom['coordinates']]
        rows.append({'pcode': p['adm2_pcode'], 'district': p['adm2_name'], 'region': p['adm1_name'],
                     'rings': [np.asarray(poly[0])[:, :2] for poly in polys]})
    return rows


def assign_points(lon, lat, districts=None):
    """District code for each point (None outside Uganda)."""
    districts = districts or load_districts()
    pts = np.column_stack([lon, lat])
    out = np.full(len(pts), None, dtype=object)
    for d in districts:
        for ring in d['rings']:
            lo, hi = ring.min(0), ring.max(0)
            cand = np.where((out == None) & (pts[:, 0] >= lo[0]) & (pts[:, 0] <= hi[0]) &   # noqa: E711
                            (pts[:, 1] >= lo[1]) & (pts[:, 1] <= hi[1]))[0]
            if len(cand):
                inside = MplPath(ring).contains_points(pts[cand])
                out[cand[inside]] = d['pcode']
    return out


def _bgs(name, col):
    path = RAW / 'groundwater' / 'extracted' / name
    d = pd.read_csv(path, sep='\t', dtype={col: str})
    d.columns = ['lon', 'lat', 'cls']
    return d[d['lon'].between(*BBOX[:2]) & d['lat'].between(*BBOX[2:])]


def load_groundwater():
    """BGS groundwater maps (5 km) by district: share of each district in each class, and a midpoint average."""
    districts = load_districts()
    out = []
    for key, name, col, scale in [('productivity', 'xyzASCII_gwprod_v1.txt', 'GWPROD_V2', GW_PRODUCTIVITY),
                                  ('depth', 'xyzASCII_dtwmap_v2.txt', 'DTWAFRICA_', GW_DEPTH),
                                  ('storage', 'xyzASCII_gwstor_v1.txt', 'GWSTOR_V2', GW_STORAGE)]:
        d = _bgs(name, col)
        d['pcode'] = assign_points(d['lon'].values, d['lat'].values, districts)
        d = d.dropna(subset=['pcode'])
        d = d[d['cls'].isin(scale)]
        share = pd.crosstab(d['pcode'], d['cls'], normalize='index').reindex(columns=list(scale), fill_value=0)
        share.columns = [f'gw_{key}_{c}' for c in share.columns]
        share[f'gw_{key}_mid'] = d.assign(v=d['cls'].map(scale)).groupby('pcode')['v'].median()
        out.append(share)
    gw = pd.concat(out, axis=1)
    # Shares used in the analysis: boreholes yielding at least 1 l/s (enough for a small solar pump
    # irrigating about 1–2 ha) and water within 25 m (reachable by a surface or shallow pump)
    gw['gw_yield_1ls'] = gw[['gw_productivity_M', 'gw_productivity_H', 'gw_productivity_VH']].sum(axis=1)
    gw['gw_shallow_25m'] = gw[['gw_depth_VS', 'gw_depth_S']].sum(axis=1)
    return gw


def _asc(path):
    with open(path) as f:
        meta = {}
        for _ in range(6):
            k, v = f.readline().split()
            meta[k.lower()] = float(v)
    a = np.loadtxt(path, skiprows=6)
    a[a == meta['nodata_value']] = np.nan
    n, c = int(meta['nrows']), meta['cellsize']
    lat = meta['yllcorner'] + c * (n - 1 - np.arange(n)) + c / 2
    lon = meta['xllcorner'] + c * np.arange(int(meta['ncols'])) + c / 2
    return lon, lat, a


def load_gmia():
    """FAO Global Map of Irrigation Areas v5 (about 2005, 9 km): hectares equipped for irrigation by district,
    and the share of that area equipped with groundwater."""
    lon, lat, ha = _asc(RAW / 'gmia' / 'gmia_v5_aei_ha.asc')
    _, _, gwp = _asc(RAW / 'gmia' / 'gmia_v5_aeigw_pct_aei.asc')
    i = (lat >= BBOX[2]) & (lat <= BBOX[3])
    j = (lon >= BBOX[0]) & (lon <= BBOX[1])
    LON, LAT = np.meshgrid(lon[j], lat[i])
    d = pd.DataFrame({'lon': LON.ravel(), 'lat': LAT.ravel(), 'ha': ha[np.ix_(i, j)].ravel(),
                      'gw_pct': gwp[np.ix_(i, j)].ravel()})
    d = d[d['ha'] > 0]
    d['pcode'] = assign_points(d['lon'].values, d['lat'].values)
    d = d.dropna(subset=['pcode'])
    g = d.assign(gw_ha=d['ha'] * d['gw_pct'].fillna(0) / 100).groupby('pcode')[['ha', 'gw_ha']].sum()
    return g.rename(columns={'ha': 'gmia_equipped_ha', 'gw_ha': 'gmia_groundwater_ha'})


def district_table():
    """One row per district: names and region, with the local (non-Earth Engine) layers joined."""
    base = pd.DataFrame([{k: d[k] for k in ('pcode', 'district', 'region')} for d in load_districts()]).set_index('pcode')
    return base.join(load_groundwater()).join(load_gmia())


# ------------------------------------------------------------------ Earth Engine exports
EE = RAW / 'earth_engine'
TERRACLIMATE_SCALE = {'pet': 0.1, 'aet': 0.1, 'def': 0.1, 'soil': 0.1, 'srad': 0.1}   # mm, mm, mm, mm, W/m²


def load_rain_daily():
    """Daily CHIRPS rainfall by district (mm), as a date × pcode table. Reads either export format:
    the wide one (pcode, year, d001…d366) or the long one (pcode, date, rain_mm)."""
    wide = EE / 'uga_district_rain_daily_wide.csv'
    if wide.exists():
        d = pd.read_csv(wide)
        d = d.melt(id_vars=['pcode', 'year'], var_name='doy', value_name='rain').dropna(subset=['rain'])
        d['date'] = pd.to_datetime(d['year'].astype(str) + '-01-01') + pd.to_timedelta(d['doy'].str[1:].astype(int) - 1, 'D')
    else:
        long = EE / 'uga_district_rain_daily.csv'
        long = long if long.exists() else long.with_suffix('.csv.gz')   # the repository keeps the compressed copy
        d = pd.read_csv(long, parse_dates=['date']).rename(columns={'rain_mm': 'rain'})
    return d.pivot_table(index='date', columns='pcode', values='rain').sort_index()


def load_monthly():
    """Monthly TerraClimate water balance and MODIS NDVI over each district's cropland.
    Returns a long table: pcode, date (month start), pet, aet, def, soil (mm), srad (W/m²), ndvi, ndvi_good."""
    d = pd.read_csv(EE / 'uga_district_monthly.csv')
    d['date'] = pd.to_datetime(d['date'])
    for c, s in TERRACLIMATE_SCALE.items():
        d[c] = d[c] * s
    return d


def load_static():
    """Per-district areas (km²), with cropland shares near water, on flat land, and population."""
    d = pd.read_csv(EE / 'uga_district_static.csv').rename(columns={'adm2_pcode': 'pcode'}).set_index('pcode')
    c = d['cropland_km2']
    d['cropland_share'] = c / d['area_km2']
    for col in ['crop_1km_water_km2', 'crop_5km_water_km2', 'crop_1km_river_km2', 'crop_flat_km2']:
        d[col.replace('_km2', '_share')] = (d[col] / c).where(c > 0)
    return d.drop(columns=['adm2_name', 'adm1_name'], errors='ignore')


# ------------------------------------------------------------------ seasons
DRY_MM = 2.0          # a "dry day" has less than this; district averages smear light showers, so 1 mm is too strict
LONG_DRY_SPELL = 14   # days; two weeks without rain during growth cuts maize and bean yields sharply
# Rain months and the months crops are greenest (for NDVI). Every window is three months long, so dry-spell
# odds are comparable across districts: one-season districts get the early and late halves of their season.
SEASONS = {
    'bimodal': {'first': {'rain': (3, 5), 'green': (4, 7)}, 'second': {'rain': (9, 11), 'green': (10, 12)}},
    'unimodal': {'early': {'rain': (4, 6), 'green': (5, 8)}, 'late': {'rain': (7, 9), 'green': (8, 10)}},
}


REGIME_CUTOFF = 0.6   # trough-to-peak ratio below which a district is bimodal; 0.6 keeps Busoga's two seasons


def rainfall_regime(rain, base=('1991', '2020'), cutoff=REGIME_CUTOFF):
    """Bimodal or unimodal for each district, from its 1991–2020 monthly climatology: bimodal when the
    June–August trough is below `cutoff` times the smaller of the two peaks (March–May and September–November)."""
    r = rain.loc[base[0]:base[1]]
    clim = r.groupby(r.index.month).sum() / r.index.year.nunique()
    trough = clim.loc[[6, 7, 8]].min()
    peaks = pd.concat([clim.loc[[3, 4, 5]].max(), clim.loc[[9, 10, 11]].max()], axis=1).min(axis=1)
    out = pd.DataFrame({'trough_to_peak': trough / peaks})
    out['regime'] = np.where(out['trough_to_peak'] < cutoff, 'bimodal', 'unimodal')
    return out, clim


def longest_run(mask):
    """Longest run of True values."""
    best = run = 0
    for v in mask:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def season_rain(rain, regime, dry_mm=DRY_MM):
    """One row per district, year and season: rain total (mm), longest dry spell (days) and dry days
    (days below `dry_mm`). Incomplete seasons are dropped."""
    rows = []
    for pcode in rain.columns:
        reg = regime.loc[pcode, 'regime']
        x = rain[pcode].dropna()
        for season, w in SEASONS[reg].items():
            m0, m1 = w['rain']
            s = x[(x.index.month >= m0) & (x.index.month <= m1)]
            for year, v in s.groupby(s.index.year):
                expected = (pd.Timestamp(year, m1, 1) + pd.offsets.MonthEnd(0) - pd.Timestamp(year, m0, 1)).days + 1
                if len(v) < expected:
                    continue
                rows.append({'pcode': pcode, 'year': year, 'season': season, 'rain': v.sum(),
                             'dry_spell': longest_run(v.values < dry_mm), 'dry_days': int((v < dry_mm).sum())})
    return pd.DataFrame(rows)


def season_monthly(monthly, regime):
    """Seasonal water deficit (TerraClimate, sum over the rain months, mm) and peak NDVI over the green months."""
    rows = []
    m = monthly.assign(year=monthly['date'].dt.year, month=monthly['date'].dt.month)
    for pcode, g in m.groupby('pcode'):
        if pcode not in regime.index:
            continue
        for season, w in SEASONS[regime.loc[pcode, 'regime']].items():
            r = g[g['month'].between(*w['rain'])].groupby('year')
            gr = g[g['month'].between(*w['green'])].groupby('year')
            df = pd.DataFrame({'deficit': r['def'].sum(min_count=w['rain'][1] - w['rain'][0] + 1),
                               'pet': r['pet'].sum(min_count=w['rain'][1] - w['rain'][0] + 1),
                               'ndvi_peak': gr['ndvi'].max(), 'ndvi_good': gr['ndvi_good'].mean()})
            rows.append(df.assign(pcode=pcode, season=season).reset_index())
    return pd.concat(rows, ignore_index=True)


def pct_rank(s, higher_is_more=True):
    """Percentile rank 0–100 across districts."""
    r = s.rank(pct=True) * 100
    return r if higher_is_more else 100 - r


# ------------------------------------------------------------------ need and feasibility
def need_metrics(seasons, long_spell=LONG_DRY_SPELL, fail_share=0.75, base=(1991, 2020)):
    """Per district: share of three-month growing windows with a dry spell of at least `long_spell` days,
    and share with rain below `fail_share` of that window's 1991–2020 median."""
    s = seasons.copy()
    b = s[s['year'].between(*base)].groupby(['pcode', 'season'])['rain'].median().rename('median')
    s = s.join(b, on=['pcode', 'season'])
    s['long_dry'] = s['dry_spell'] >= long_spell
    s['failed'] = s['rain'] < fail_share * s['median']
    return s.groupby('pcode').agg(p_long_dry=('long_dry', 'mean'), p_failed=('failed', 'mean'),
                                  mean_spell=('dry_spell', 'mean'), window_rain=('rain', 'median'))


SURFACE_MIN = 0.10    # share of cropland within 1 km of permanent water or a river
GROUNDWATER_MIN = 0.5  # share of the district where boreholes can yield at least 1 l/s


def need_feasibility(need, deficit, static, gw, surface_min=SURFACE_MIN, groundwater_min=GROUNDWATER_MIN):
    """Need score and water access for each district.

    Need (0–100) averages percentile ranks of dry-spell odds, failed-window odds and growing-window water
    deficit; "higher need" means the top half of districts. Water access uses fixed thresholds, because
    water is either within reach or it is not: at least `surface_min` of cropland within 1 km of permanent
    water or a river, or at least `groundwater_min` of the district where boreholes can yield 1 l/s or more.
    `water_score` is the better of the two as a multiple of its threshold (1 or more means within reach).
    Districts with under 10 km² of mapped cropland are left out."""
    d = need.join(deficit.rename('deficit')).join(static).join(gw[['gw_yield_1ls']])
    d['surface_access'] = d[['crop_1km_water_share', 'crop_1km_river_share']].max(axis=1)
    keep = d['cropland_km2'] >= 10
    r = d[keep]
    d.loc[keep, 'need'] = pd.concat([pct_rank(r['p_long_dry']), pct_rank(r['p_failed']), pct_rank(r['deficit'])], axis=1).mean(axis=1)
    d['water_score'] = pd.concat([d['surface_access'] / surface_min, d['gw_yield_1ls'] / groundwater_min], axis=1).max(axis=1)
    d['water_source'] = np.select([d['surface_access'] >= surface_min, d['gw_yield_1ls'] >= groundwater_min],
                                  ['surface water', 'groundwater'], 'neither')
    d.loc[(d['surface_access'] >= surface_min) & (d['gw_yield_1ls'] >= groundwater_min), 'water_source'] = 'both'
    hi, reach = d['need'] >= d.loc[keep, 'need'].median(), d['water_score'] >= 1
    d['group'] = np.select(
        [~keep, hi & reach, hi, reach],
        ['too little cropland mapped', 'high need, water within reach', 'high need, water hard to reach',
         'lower need, water within reach'], 'lower need, harder access')
    return d


# ------------------------------------------------------------------ maps
def district_map(ax, values, cmap='viridis', vmin=None, vmax=None, colors=None, edge='#ffffff', missing='#e6e4df',
                 lake='#dbe7f0'):
    """Choropleth of districts on a matplotlib axis. `values` is a Series by pcode (numbers) or, with
    `colors`, a Series by pcode of category labels mapped through the `colors` dict."""
    from matplotlib.collections import PolyCollection
    import matplotlib as mpl
    polys, fc = [], []
    vals = values.dropna()
    if colors is None:
        norm = mpl.colors.Normalize(vmin if vmin is not None else vals.min(), vmax if vmax is not None else vals.max())
        cm = mpl.colormaps[cmap] if isinstance(cmap, str) else cmap
    for d in load_districts():
        v = values.get(d['pcode'], np.nan)
        c = missing if pd.isna(v) else (colors[v] if colors is not None else cm(norm(v)))
        for ring in d['rings']:
            polys.append(ring)
            fc.append(c)
    ax.add_collection(PolyCollection(polys, facecolors=fc, edgecolors=edge, linewidths=0.3))
    lakes = RAW / 'boundaries' / 'lakes_uganda.geojson'
    if lakes.exists():
        rings = []
        for f in json.loads(lakes.read_text())['features']:
            g = f['geometry']
            for poly in (g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']]):
                rings.append(np.asarray(poly[0])[:, :2])
        ax.add_collection(PolyCollection(rings, facecolors=lake, edgecolors='none'))
    ax.set_xlim(29.5, 35.1); ax.set_ylim(-1.55, 4.3); ax.set_aspect('equal'); ax.axis('off')
    if colors is None:
        return mpl.cm.ScalarMappable(norm=norm, cmap=cm)
