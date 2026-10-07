/**************************************************************************
 * Uganda daily rainfall by district, 1991 to the latest available day.
 *
 * Uses the same district asset as uganda_irrigation_districts_gee.js. Paste
 * your asset path below, press Run, then start the export from the Tasks tab.
 *
 * Each year's daily CHIRPS images are stacked into one image of 365 or 366
 * bands, so Earth Engine summarises a whole year for all districts in a
 * single pass. That is much faster than summarising each day separately.
 *
 * Output: uga_district_rain_daily_wide.csv, one row per district and year:
 *   pcode, year, d001 … d366
 *   dNNN  CHIRPS rainfall (mm) on day NNN of the year, averaged over the
 *         district; d366 is blank except in leap years, and days after the
 *         latest available date are blank.
 *
 * Feeds notebooks/01 in the uganda-irrigation project.
 **************************************************************************/

// ---------------------------------------------------------------- settings
var DISTRICT_ASSET = 'projects/YOUR-PROJECT/assets/uga_districts_2020';   // <- paste your asset path
var FIRST_YEAR = 1991;
// If the export fails with a memory or time error, raise TILE_SCALE to 8 or 16.
var TILE_SCALE = 4;

// ---------------------------------------------------------------- inputs
var districts = ee.FeatureCollection(DISTRICT_ASSET).select(['adm2_pcode']);
var chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/DAILY').select('precipitation');
var latest = ee.Date(chirps.aggregate_max('system:time_start'));
var lastYear = latest.get('year');

print('Districts (expect 135):', districts.size());
print('Latest CHIRPS day:', latest.format('YYYY-MM-dd'));

var DAYS = [];
for (var n = 1; n <= 366; n++) DAYS.push('d' + ('00' + n).slice(-3));

// One image per year, one band per day of year (d001, d002, ...)
function yearStack(year) {
  year = ee.Number(year);
  var days = chirps.filterDate(ee.Date.fromYMD(year, 1, 1), ee.Date.fromYMD(year.add(1), 1, 1));
  var names = days.aggregate_array('system:time_start').map(function (t) {
    return ee.String('d').cat(ee.Date(t).getRelative('day', 'year').add(1).format('%03d'));
  });
  return days.toBands().rename(names);
}

var rows = ee.FeatureCollection(ee.List.sequence(FIRST_YEAR, lastYear).map(function (year) {
  return yearStack(year).reduceRegions({
    collection: districts, reducer: ee.Reducer.mean(), scale: 5566, tileScale: TILE_SCALE
  }).map(function (f) {
    return f.setGeometry(null).set('pcode', f.get('adm2_pcode'), 'year', year);
  });
})).flatten();

print('Preview, one district-year:', rows.first());

// ---------------------------------------------------------------- export
Export.table.toDrive({
  collection: rows,
  description: 'uga_district_rain_daily_wide',
  fileNamePrefix: 'uga_district_rain_daily_wide',
  fileFormat: 'CSV',
  selectors: ['pcode', 'year'].concat(DAYS)
});
