/**
 * Агрегаты для https://psyteeth.github.io/schedule/ (data/stats.json).
 *
 * Читает две таблицы (эфиры и бот саморегуляций) и отдаёт по ссылке
 * веб-приложения ТОЛЬКО числа и имена тренеров. Имена и ники участников
 * используются внутри для подсчёта и наружу не уходят.
 *
 * Установка: apps_script/README.md. ID таблиц вписываются только в копию
 * скрипта в Google, в репозитории остаются заглушки.
 */
var CONFIG = {
  EFIRY_ID: 'ВСТАВЬТЕ_ID_ТАБЛИЦЫ_ЭФИРОВ',
  SR_ID: 'ВСТАВЬТЕ_ID_ТАБЛИЦЫ_СР',
  TZ: 'Europe/Moscow',
  // true: минуты студентов + тренеров (тренеры из листа «Чемпионат_лог»);
  // false: только студенты.
  INCLUDE_TRAINER_SR: true,
  SR_WINDOW_DAYS: 30,
  // метка в колонке B листа эфиров → имя на сайте
  TRAINERS: { 'АНТОН': 'Антон', 'ТАНЯ': 'Таня', 'ЯНА': 'Яна', 'ГУЛЬНАЗ': 'Гульназ' },
  TRAINER_ORDER: ['Антон', 'Таня', 'Яна', 'Гульназ'],
  SR_DAY_SHEET: 'СР_День',
  SR_CHAMP_SHEET: 'Чемпионат_лог'
};

var DAYS = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'];
var MONTHS = ['ЯНВАРЬ', 'ФЕВРАЛЬ', 'МАРТ', 'АПРЕЛЬ', 'МАЙ', 'ИЮНЬ', 'ИЮЛЬ', 'АВГУСТ', 'СЕНТЯБРЬ', 'ОКТЯБРЬ', 'НОЯБРЬ', 'ДЕКАБРЬ'];

function doGet() {
  var body;
  try {
    body = buildStats_(new Date());
  } catch (err) {
    body = { error: String((err && err.message) || err) };
  }
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}

/** Запустите вручную в редакторе, чтобы увидеть результат в журнале. */
function testStats() {
  Logger.log(JSON.stringify(buildStats_(new Date()), null, 2));
}

function buildStats_(now) {
  var today = Utilities.formatDate(now, CONFIG.TZ, 'yyyy-MM-dd');

  var efiry = SpreadsheetApp.openById(CONFIG.EFIRY_ID);
  var sheet = monthSheet_(efiry, today);
  var range = sheet.getDataRange();
  var e = efiryStats_(range.getValues(), range.getDisplayValues(), today);

  var sr = SpreadsheetApp.openById(CONFIG.SR_ID);
  var dayRows = sr.getSheetByName(CONFIG.SR_DAY_SHEET).getDataRange().getValues();
  var champSheet = sr.getSheetByName(CONFIG.SR_CHAMP_SHEET);
  var champRows = champSheet ? champSheet.getDataRange().getValues() : [];
  var s = srStats_(dayRows, champRows, today, CONFIG.INCLUDE_TRAINER_SR);

  return {
    updated: today,
    source: 'apps_script',
    slots_total: e.slots_total,
    slots_past: e.slots_past,
    slots_upcoming: e.slots_upcoming,
    participants_active: e.participants_active,
    streams_per_week: e.streams_per_week,
    trainers: e.trainers,
    limbic_unload_30d: s,
    heat: e.heat
  };
}

/** Лист текущего месяца: «НОЯБРЬ 2026» (пробелы по краям не важны). */
function monthSheet_(ss, today) {
  var y = today.slice(0, 4), m = +today.slice(5, 7) - 1;
  var want = MONTHS[m] + ' ' + y;
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getName().replace(/\s+/g, ' ').trim().toUpperCase() === want) return sheets[i];
  }
  throw new Error('Не найден лист «' + want + '» в таблице эфиров');
}

// ---------- Эфиры ----------

function trainerOf_(label) {
  var m = /^\s*([А-ЯЁ]+)/.exec(String(label || ''));
  return m ? (CONFIG.TRAINERS[m[1]] || null) : null;
}

function minutesOf_(s) {
  var m = /^\s*(\d{1,2}):(\d{2})/.exec(String(s || ''));
  return m ? (+m[1]) * 60 + (+m[2]) : null;
}

function ymdOf_(v, disp) {
  if (v instanceof Date && v.getFullYear() > 1900) return Utilities.formatDate(v, CONFIG.TZ, 'yyyy-MM-dd');
  var s = String(disp == null ? v : disp);
  var m = /(\d{4})-(\d{2})-(\d{2})/.exec(s);
  if (m) return m[1] + '-' + m[2] + '-' + m[3];
  m = /(\d{1,2})\.(\d{1,2})\.(\d{4})/.exec(s);
  if (m) return m[3] + '-' + ('0' + m[2]).slice(-2) + '-' + ('0' + m[1]).slice(-2);
  return null;
}

/** Люди в ячейке: «Янина, Аня Х» → 2. Эмодзи и пометки убираются. */
function peopleOf_(s) {
  var clean = String(s || '').replace(/[^\p{L}\p{N}\s,.\-]/gu, '').trim();
  if (!clean) return [];
  return clean.split(',').map(function (p) { return p.replace(/^[\s.]+|[\s.]+$/g, '').toLowerCase(); })
    .filter(function (p) { return p; });
}

function efiryStats_(values, display, today) {
  var header = display[0] || [];
  var end = header.length;
  for (var h = 2; h < header.length; h++) {
    if (String(header[h]).toUpperCase().indexOf('ТРЕНЕРЫ') >= 0) { end = h; break; }
  }
  var cols = [];
  for (var c = 2; c + 2 < end; c += 3) cols.push(c); // тройки «дата, время, кто» по неделям

  // 1. Блоки эфиров: строка с меткой тренера в колонке B начинает эфир.
  var streams = [], day = null, cur = null;
  for (var r = 1; r < display.length; r++) {
    var a = String(display[r][0] || '').trim();
    if (DAYS.indexOf(a) >= 0) day = a;
    var b = String(display[r][1] || '').trim();
    var t = trainerOf_(b);
    if (t) { cur = { day: day, trainer: t, rows: [] }; streams.push(cur); }
    else if (b) cur = null; // пояснения под сеткой
    if (cur) cur.rows.push(r);
  }

  // 2. Проведения эфира по неделям.
  var lastDate = {}, slotsTotal = 0, slotsPast = 0, people = {};
  streams.forEach(function (s) {
    s.occ = [];
    cols.forEach(function (c) {
      var date = null, start = null, n = 0, cells = 0;
      s.rows.forEach(function (r) {
        var d = ymdOf_(values[r][c], display[r][c]);
        if (d) date = d;
        var mm = minutesOf_(display[r][c + 1]);
        if (mm === null) return;
        if (start === null) start = mm;
        var ps = peopleOf_(display[r][c + 2]);
        if (ps.length) cells++;
        n += ps.length;
        ps.forEach(function (p) { if (p !== 'занято') people[p] = 1; });
      });
      var key = s.day + '|' + c;
      if (date) lastDate[key] = date; else date = lastDate[key] || null;
      if (n > 0) {
        s.occ.push({ date: date, start: start, n: n });
        slotsTotal += cells;
        if (date && date <= today) slotsPast += cells;
      }
    });
  });

  // 3. Постоянные эфиры (минимум 2 проведения за месяц) → тепловая карта.
  var heat = [], trainers = {};
  streams.forEach(function (s) {
    if (s.occ.length < 2) return;
    var cnt = {}, best = null;
    s.occ.forEach(function (o) { cnt[o.start] = (cnt[o.start] || 0) + 1; if (best === null || cnt[o.start] > cnt[best]) best = o.start; });
    var sum = s.occ.reduce(function (acc, o) { return acc + o.n; }, 0);
    var item = { day: s.day, row: Math.floor(best / 60) + ':00', trainer: s.trainer, avg: Math.round(sum / s.occ.length * 10) / 10 };
    if (best % 60) item.time = Math.floor(best / 60) + ':' + ('0' + (best % 60)).slice(-2);
    heat.push(item);
    trainers[s.trainer] = 1;
  });
  heat.sort(function (x, y) { return parseInt(x.row, 10) - parseInt(y.row, 10) || DAYS.indexOf(x.day) - DAYS.indexOf(y.day); });

  return {
    slots_total: slotsTotal,
    slots_past: slotsPast,
    slots_upcoming: slotsTotal - slotsPast,
    participants_active: Object.keys(people).length,
    streams_per_week: heat.length,
    trainers: CONFIG.TRAINER_ORDER.filter(function (t) { return trainers[t]; }),
    heat: heat
  };
}

// ---------- Саморегуляции ----------

function colIndex_(headerRow, name) {
  for (var i = 0; i < headerRow.length; i++) {
    if (String(headerRow[i]).trim().toLowerCase() === name.toLowerCase()) return i;
  }
  throw new Error('Нет колонки «' + name + '»');
}

function num_(v) {
  if (typeof v === 'number') return v;
  var n = parseFloat(String(v || '').replace(/\s/g, '').replace(',', '.'));
  return isNaN(n) ? 0 : n;
}

function addDays_(ymd, k) {
  var d = new Date(Date.UTC(+ymd.slice(0, 4), +ymd.slice(5, 7) - 1, +ymd.slice(8, 10) + k));
  return d.toISOString().slice(0, 10);
}

function srStats_(dayRows, champRows, today, includeTrainers) {
  var from = addDays_(today, -(CONFIG.SR_WINDOW_DAYS - 1));
  var inWin = function (d) { return d && d >= from && d <= today; };

  // тренеры: из лога чемпионата (каждая строка = одна СР)
  var trainerUsers = {}, tCount = 0, tSec = 0;
  if (champRows.length) {
    var h = champRows[0];
    var cT = colIndex_(h, 'Время (МСК)'), cU = colIndex_(h, 'Username'), cR = colIndex_(h, 'Роль'), cS = colIndex_(h, 'Секунды');
    for (var i = 1; i < champRows.length; i++) {
      var row = champRows[i];
      if (String(row[cR]).trim().toLowerCase() !== 'тренер') continue;
      trainerUsers[String(row[cU]).trim().toLowerCase()] = 1;
      if (inWin(ymdOf_(row[cT]))) { tCount++; tSec += num_(row[cS]); }
    }
  }

  // студенты: дневной учёт (тренерские ники исключены, чтобы не было двойного счёта)
  var hd = dayRows[0];
  var dD = colIndex_(hd, 'Дата'), dU = colIndex_(hd, 'Username'), dC = colIndex_(hd, 'СР'), dS = colIndex_(hd, 'Секунды');
  var sCount = 0, sSec = 0;
  for (var j = 1; j < dayRows.length; j++) {
    var r = dayRows[j];
    if (trainerUsers[String(r[dU]).trim().toLowerCase()]) continue;
    if (!inWin(ymdOf_(r[dD]))) continue;
    sCount += num_(r[dC]);
    sSec += num_(r[dS]);
  }

  var count = sCount + (includeTrainers ? tCount : 0);
  var minutes = Math.floor((sSec + (includeTrainers ? tSec : 0)) / 60);
  return {
    hours: Math.floor(minutes / 60),
    minutes: minutes % 60,
    sr_count: count,
    window: from + '/' + today,
    includes_trainers: !!includeTrainers
  };
}
