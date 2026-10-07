"""
Collect every number shown in reports/irrigation_report.html and inject it into the page.

Results come from the tables notebook 01 exports to data/processed/; district outlines are simplified
here for the maps.

Usage (from anywhere, after running notebook 01):
    python scripts/build_report_data.py
"""
import json
import re
import numpy as np
import pandas as pd
from irrigation import ROOT, RAW, PROC, load_districts, load_rain_daily

REPORT = ROOT / 'reports' / 'irrigation_report.html'
TOLERANCE = 0.006    # degrees (about 650 m): enough detail for a page-width map


def simplify(ring, tol=TOLERANCE):
    """Douglas–Peucker simplification of a closed ring (n × 2 array)."""
    def dp(pts):
        if len(pts) < 3:
            return pts
        a, b = pts[0], pts[-1]
        ab = b - a
        n = np.hypot(*ab)
        d = np.abs(np.cross(ab, pts - a)) / n if n else np.hypot(*(pts - a).T)
        i = int(np.argmax(d))
        if d[i] <= tol:
            return np.array([a, b])
        return np.vstack([dp(pts[:i + 1])[:-1], dp(pts[i:])])
    out = dp(ring)
    return out if len(out) >= 4 else ring


def clockwise(ring):
    """d3 draws a polygon's exterior ring clockwise; GeoJSON stores it anticlockwise."""
    x, y = ring[:, 0], ring[:, 1]
    area = np.sum(x[:-1] * y[1:] - x[1:] * y[:-1])
    return ring[::-1] if area > 0 else ring


def geometry(rings):
    polys = []
    for r in rings:
        s = clockwise(simplify(r))
        if len(s) >= 4:
            polys.append([np.round(s, 3).tolist()])
    return {'type': 'MultiPolygon', 'coordinates': polys}


def lakes():
    feats = []
    for f in json.loads((RAW / 'boundaries' / 'lakes_uganda.geojson').read_text())['features']:
        g = f['geometry']
        rings = [np.asarray(p[0])[:, :2] for p in (g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']])]
        feats.append({'type': 'Feature', 'properties': {'name': f['properties'].get('name')}, 'geometry': geometry(rings)})
    return {'type': 'FeatureCollection', 'features': feats}


def r4(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 4)


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, float) and np.isnan(o):
        return None
    return o


def main():
    nf = pd.read_csv(PROC / 'district_need_feasibility.csv', index_col=0)
    reg = pd.read_csv(PROC / 'district_regime.csv', index_col=0)
    nd = pd.read_csv(PROC / 'district_need.csv', index_col=0)
    gw = pd.read_csv(PROC / 'district_groundwater.csv', index_col=0)
    crop = pd.read_csv(PROC / 'crop_response.csv')
    sens = pd.read_csv(PROC / 'sensitivity.csv')

    cols = {'p_long_dry': 'dry', 'p_failed': 'fail', 'mean_spell': 'spell', 'deficit': 'deficit',
            'surface_access': 'surface', 'gw_yield_1ls': 'gw', 'crop_flat_share': 'flat', 'cropland_km2': 'crop',
            'population': 'pop', 'need': 'need', 'water_score': 'ws', 'water_source': 'src', 'group': 'group',
            'gmia_equipped_ha': 'gmia'}
    feats = []
    for d in load_districts():
        p = d['pcode']
        props = {'id': p, 'name': d['district'], 'region': d['region'], 'regime': reg.loc[p, 'regime']}
        for c, k in cols.items():
            v = nf.loc[p, c] if c in nf.columns else np.nan
            props[k] = v if isinstance(v, str) else r4(v)
        if pd.isna(props['dry']):
            props['dry'], props['fail'], props['deficit'] = r4(nd.loc[p, 'p_long_dry']), r4(nd.loc[p, 'p_failed']), r4(nd.loc[p, 'deficit'])
        props['gw'] = r4(gw.loc[p, 'gw_yield_1ls'])
        feats.append({'type': 'Feature', 'properties': props, 'geometry': geometry(d['rings'])})

    # Monthly rainfall climatology, 1991–2020, by regime: median district and 10–90% band
    rain = load_rain_daily().loc['1991':'2020']
    mon = rain.groupby([rain.index.year, rain.index.month]).sum().groupby(level=1).mean()
    clim = {}
    for g in ['bimodal', 'unimodal']:
        m = mon[reg.index[reg['regime'] == g]]
        clim[g] = {'n': int(m.shape[1]), 'med': [r4(v) for v in m.median(axis=1)],
                   'lo': [r4(v) for v in m.quantile(.1, axis=1)], 'hi': [r4(v) for v in m.quantile(.9, axis=1)]}

    crop['se'] = crop['NDVI change (x1000)'] / crop['t']
    crop_rows = [{'who': r['districts'], 'measure': r['measure'], 'b': r4(r['NDVI change (x1000)']), 'se': r4(r['se']),
                  't': r4(r['t']), 'n': int(r['windows']), 'swing': r4(r['typical NDVI swing (x1000)'])} for _, r in crop.iterrows()]
    sens_rows = [{'variant': r['variant'], 'rho': r4(r['need rank correlation']), 'n': int(r['priority districts']),
                  'shared': int(r['shared with main list']), 'kept': r4(r['main list kept (%)'])} for _, r in sens.iterrows()]

    scored = nf.dropna(subset=['need'])
    groups = scored['group'].value_counts().to_dict()
    top = nf[nf['group'] == 'high need, water within reach']
    kpi = {
        'moroto_dry': r4(nd.loc[nd['district'] == 'Moroto', 'p_long_dry'].iloc[0]),
        'groups': {k: int(v) for k, v in nf['group'].value_counts().items()},
        'top_crop_share': r4(top['cropland_km2'].sum() / nf['cropland_km2'].sum()),
        'top_pop_m': r4(top['population'].sum() / 1e6),
        'gmia_total': r4(nf['gmia_equipped_ha'].sum()),
        'n_districts': int(len(nf)), 'n_scored': int(len(scored)),
        'need_median': r4(scored['need'].median()),
    }
    data = clean({'districts': {'type': 'FeatureCollection', 'features': feats}, 'lakes': lakes(), 'clim': clim,
                  'crop': crop_rows, 'sens': sens_rows, 'kpi': kpi, 'groups': groups})
    payload = json.dumps(data, separators=(',', ':'), allow_nan=False).replace('</', '<\\/')
    s = REPORT.read_text()
    s, n = re.subn(r'(<script id="report-data" type="application/json">)(.*?)(</script>)',
                   lambda m: m.group(1) + payload + m.group(3), s, flags=re.S)
    if n != 1:
        raise SystemExit(f'expected one report-data block, found {n}')
    REPORT.write_text(s)
    print(f'updated {REPORT.relative_to(ROOT)} ({len(payload) / 1024:.0f} KB of data)')


if __name__ == '__main__':
    main()
