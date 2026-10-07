"""
Download every public input for the irrigation project, and copy in the Earth Engine exports.

Usage (from anywhere):
    python scripts/fetch_data.py [--earth-engine DIR]

Outputs
  data/raw/boundaries/   Uganda district boundaries, 2020 (OCHA/UBOS via HDX): GeoJSON, and the
                         shapefile zipped for upload to Earth Engine
  data/raw/groundwater/  BGS quantitative groundwater maps of Africa (5 km): productivity, depth, storage
  data/raw/gmia/         FAO Global Map of Irrigation Areas v5 (about 2005, 5 arc-minutes): area equipped,
                         and the share equipped with groundwater
  data/raw/earth_engine/ outputs of scripts/gee/*.js, copied from DIR (default ~/Downloads)

Groundwater maps: contains data supplied by permission of the Natural Environment Research
Council (Open Government Licence).
"""
import argparse
import io
import json
import shutil
import zipfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'
HDX = 'https://data.humdata.org/dataset/6d6d1495-196b-49d0-86b9-dc9022cde8e7/resource/'
BOUNDARIES = {
    'geojson': HDX + '4a409743-e1b7-40d7-ad05-e08920f4b099/download/uga_admin_boundaries.geojson.zip',
    'shp': HDX + '7804b4f7-064c-4bb4-a95d-4439fd658090/download/uga_admin_boundaries.shp.zip',
}
BGS = 'https://webservices.bgs.ac.uk/accessions/download/182832?fileName='
BGS_FILES = ['DepthToGroundwater.zip', 'GroundwaterProductivity.zip', 'GroundwaterStorage.zip']
GMIA = 'https://firebasestorage.googleapis.com/v0/b/fao-aquastat.appspot.com/o/GIS%2F'
GMIA_FILES = {'gmia_v5_aei_ha_asc.zip': '416b27f5-fcb5-4178-ab49-1658d5c2c3ad',
              'gmia_v5_aeigw_pct_aei_asc.zip': 'ee5bd6d1-c8e2-44fd-a4cf-58d7563abbf6'}
LAKES = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_lakes.geojson'
EE_FILES = ['uga_district_rain_daily_wide.csv', 'uga_district_rain_daily.csv',
            'uga_district_monthly.csv', 'uga_district_static.csv']


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def main(ee_dir):
    b, gw, gm, ee = (RAW / k for k in ('boundaries', 'groundwater', 'gmia', 'earth_engine'))
    for d in (b, gw / 'extracted', gm, ee):
        d.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(get(BOUNDARIES['geojson']))) as z:
        z.extract('uga_admin2.geojson', b)
    with zipfile.ZipFile(io.BytesIO(get(BOUNDARIES['shp']))) as z, \
         zipfile.ZipFile(b / 'uga_districts_2020_shp.zip', 'w', zipfile.ZIP_DEFLATED) as out:
        for n in z.namelist():
            if n.startswith('uga_admin2.'):
                out.writestr(n, z.read(n))
    print('District boundaries saved')

    # Lakes for maps (Natural Earth, public domain): keep those touching Uganda
    lakes = json.loads(get(LAKES))
    def touches(f):
        xs = [c for ring in (f['geometry']['coordinates'] if f['geometry']['type'] == 'Polygon'
                            else [r for p in f['geometry']['coordinates'] for r in p]) for c in ring]
        return any(29.4 <= x <= 35.1 and -1.6 <= y <= 4.4 for x, y in xs)
    lakes['features'] = [f for f in lakes['features'] if touches(f)]
    (b / 'lakes_uganda.geojson').write_text(json.dumps(lakes))
    print('Lakes saved:', ', '.join(sorted({f['properties'].get('name') or '?' for f in lakes['features']})))

    for f in BGS_FILES:
        with zipfile.ZipFile(io.BytesIO(get(BGS + f))) as z:
            for n in z.namelist():
                if 'xyzASCII' in n:
                    (gw / 'extracted' / Path(n).name).write_bytes(z.read(n))
    print('BGS groundwater maps saved')

    for f, token in GMIA_FILES.items():
        with zipfile.ZipFile(io.BytesIO(get(f'{GMIA}{f}?alt=media&token={token}'))) as z:
            z.extractall(gm)
    print('FAO irrigation map saved')

    found = [f for f in EE_FILES if (Path(ee_dir) / f).exists()]
    for f in found:
        shutil.copy(Path(ee_dir) / f, ee / f)
    missing = [f for f in EE_FILES[2:] if not (ee / f).exists()]
    if not any((ee / f).exists() for f in EE_FILES[:2]):
        missing.insert(0, EE_FILES[0])
    print(f'Earth Engine exports copied: {found or "none"}')
    if missing:
        print('Still needed (run scripts/gee/*.js):', missing)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--earth-engine', default=str(Path.home() / 'Downloads'),
                    help='folder holding the Earth Engine CSV exports (default ~/Downloads)')
    main(ap.parse_args().earth_engine)
