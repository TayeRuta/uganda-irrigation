/**************************************************************************
 * Uganda irrigation need and potential, by district.
 *
 * Before running: upload the district boundaries as an asset.
 *   1. Unzip data/raw/boundaries/uga_districts_2020_shp.zip (135 districts,
 *      OCHA/UBOS 2020 boundaries).
 *   2. Code Editor > Assets > NEW > Shape files: select all five
 *      uga_admin2.* files, name the asset uga_districts_2020, UPLOAD.
 *   3. When the upload task finishes, paste the asset path below.
 *
 * Then press Run, check the printed numbers, and start the two exports
 * from the Tasks tab. Both take minutes. Daily rainfall comes from the
 * companion script, uganda_irrigation_rain_daily_gee.js.
 *
 * Outputs (all keyed by adm2_pcode, the district code):
 *   uga_district_monthly.csv          pcode, date, pet, aet, def, soil, srad,
 *                                        ndvi, ndvi_good
 *        TerraClimate monthly water balance over cropland (raw values; scale
 *        0.1 applied in Python), and MODIS NDVI over cropland from Terra and
 *        Aqua combined, with the share of cropland seen cloud-free.
 *   uga_district_static.csv           one row per district: area, cropland,
 *        cropland near permanent water and near rivers, flat cropland,
 *        population
 *
 * Feeds notebooks/01 in the uganda-irrigation project.
 **************************************************************************/

// ---------------------------------------------------------------- settings
var DISTRICT_ASSET = 'projects/YOUR-PROJECT/assets/uga_districts_2020';   // <- paste your asset path
var MONTHLY_START = '2000-03-01';
// If an export fails with a memory or time error, raise TILE_SCALE to 8 or 16.
var TILE_SCALE = 4;

// ---------------------------------------------------------------- inputs
var districts = ee.FeatureCollection(DISTRICT_ASSET).select(['adm2_pcode', 'adm2_name', 'adm1_name']);
var uganda = districts.geometry().dissolve(1000);
var cropland = ee.ImageCollection('ESA/WorldCover/v200').first().eq(40);   // 2021, 10 m

print('Districts (expect 135):', districts.size());

// ---------------------------------------------------------------- monthly
var terra = ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE').select(['pet', 'aet', 'def', 'soil', 'srad'])
  .filterDate(MONTHLY_START, ee.Date(Date.now()));
var modis = ee.ImageCollection('MODIS/061/MOD13Q1').merge(ee.ImageCollection('MODIS/061/MYD13Q1'));

// MODIS quality: keep pixels flagged good (SummaryQA 0) or marginal (1)
function cleanNdvi(img) {
  var ok = img.select('SummaryQA').lte(1);
  return img.select('NDVI').multiply(0.0001).updateMask(ok);
}

var latestTerra = ee.Date(terra.aggregate_max('system:time_start'));
var nMonths = latestTerra.difference(ee.Date(MONTHLY_START), 'month').round().add(1);
var months = ee.List.sequence(0, nMonths.subtract(1));

var monthly = ee.FeatureCollection(months.map(function (i) {
  var m0 = ee.Date(MONTHLY_START).advance(ee.Number(i), 'month');
  var m1 = m0.advance(1, 'month');
  var wb = ee.Image(terra.filterDate(m0, m1).first());
  var nd = modis.filterDate(m0, m1).map(cleanNdvi);
  var ndvi = nd.mean().rename('ndvi');
  var good = nd.count().gt(0).unmask(0).rename('ndvi_good');
  var img = wb.addBands(ndvi).addBands(good).updateMask(cropland);
  return img.reduceRegions({
    collection: districts, reducer: ee.Reducer.mean(), scale: 500, tileScale: TILE_SCALE
  }).map(function (f) {
    // Districts with no cropland pixel get empty values; the export keeps them as blanks
    return f.setGeometry(null).set('pcode', f.get('adm2_pcode'), 'date', m0.format('YYYY-MM'));
  });
})).flatten();

print('Months of water balance and NDVI:', nMonths, 'to', latestTerra.format('YYYY-MM'));

// ---------------------------------------------------------------- static
// Permanent surface water: water in at least 10 months of the year (JRC 1984–2021)
var permWater = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('seasonality').unmask(0).gte(10);
// Rivers with mean flow of at least 1 m³/s (HydroSHEDS)
var rivers = ee.FeatureCollection('WWF/HydroSHEDS/v1/FreeFlowingRivers')
  .filterBounds(uganda).filter(ee.Filter.gte('DIS_AV_CMS', 1));
var riverImg = ee.Image(0).byte().paint(rivers, 1).selfMask();

function near(mask, metres) {
  return mask.unmask(0).focalMax({radius: metres, units: 'meters', kernelType: 'circle'});
}
var slope = ee.Terrain.slope(ee.Image('USGS/SRTMGL1_003'));   // degrees
var pop = ee.ImageCollection('WorldPop/GP/100m/pop').filter(ee.Filter.eq('country', 'UGA'))
  .filter(ee.Filter.eq('year', 2020)).first();

var km2 = ee.Image.pixelArea().divide(1e6);
var areas = ee.Image.cat([
  km2.rename('area_km2'),
  km2.updateMask(cropland).rename('cropland_km2'),
  km2.updateMask(cropland.and(near(permWater, 1000))).rename('crop_1km_water_km2'),
  km2.updateMask(cropland.and(near(permWater, 5000))).rename('crop_5km_water_km2'),
  km2.updateMask(cropland.and(near(riverImg, 1000))).rename('crop_1km_river_km2'),
  km2.updateMask(cropland.and(slope.lte(3))).rename('crop_flat_km2')       // ≤3° ≈ ≤5% slope
]).unmask(0);

var stat = areas.reduceRegions({
  collection: districts, reducer: ee.Reducer.sum(), scale: 100, tileScale: TILE_SCALE
});
stat = pop.rename('population').reduceRegions({
  collection: stat, reducer: ee.Reducer.sum().setOutputs(['population']), scale: 100, tileScale: TILE_SCALE
});
print('Static table, first district:', stat.first());

// ---------------------------------------------------------------- map check
Map.centerObject(districts, 7);
Map.addLayer(cropland.selfMask(), {palette: ['d9a441']}, 'Cropland (WorldCover 2021)', false);
Map.addLayer(permWater.selfMask(), {palette: ['2b6cb0']}, 'Permanent water');
Map.addLayer(rivers, {color: '2b6cb0'}, 'Rivers ≥ 1 m³/s');
Map.addLayer(districts.style({color: '1a1a1a', fillColor: '00000000', width: 1}), {}, 'Districts');

// ---------------------------------------------------------------- exports
Export.table.toDrive({
  collection: monthly, description: 'uga_district_monthly', fileNamePrefix: 'uga_district_monthly',
  fileFormat: 'CSV', selectors: ['pcode', 'date', 'pet', 'aet', 'def', 'soil', 'srad', 'ndvi', 'ndvi_good']
});
Export.table.toDrive({
  collection: stat, description: 'uga_district_static', fileNamePrefix: 'uga_district_static',
  fileFormat: 'CSV', selectors: ['adm2_pcode', 'adm2_name', 'adm1_name', 'area_km2', 'cropland_km2',
    'crop_1km_water_km2', 'crop_5km_water_km2', 'crop_1km_river_km2', 'crop_flat_km2', 'population']
});
