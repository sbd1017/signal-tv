// Country flags for national sides: static/flags/<code>.svg (flag-icons, MIT - LICENSE-flag-icons.txt).
// A side's label -> flag code ('au', 'gb-eng'), or '' when it isn't a country. Country names come
// from the browser itself (Intl.DisplayNames) in the languages the provider's guides use, so
// "Australia (W)", "Ισπανία", "Słowenia" and "Czechia" all find theirs without a hand-made list.

const CODES = ('ad ae af ag ai al am ao ar as at au aw az ba bb bd be bf bg bh bi bj bm bn bo br bs bt bw by bz ca cd cf cg ch ci ck '
  + 'cl cm cn co cr cu cv cw cy cz de dj dk dm do dz ec ee eg er es et fi fj fm fo fr ga gb gd ge gh gi gl gm gn gq gr gt gu gw gy hk '
  + 'hn hr ht hu id ie il in iq ir is it jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mg mh '
  + 'mk ml mm mn mo mr mt mu mv mw mx my mz na ne ng ni nl no np nr nz om pa pe pg ph pk pl pr ps pt pw py qa ro rs ru rw sa sb sc sd '
  + 'se sg si sk sl sm sn so sr ss st sv sy sz td tg th tj tl tm tn to tr tt tv tw tz ua ug us uy uz va vc ve vn vu ws xk ye za zm zw').split(' ');
// guides' own words for countries the browser names differently, and the home nations
const EXTRA = {
  'gb-eng': 'England', 'gb-sct': 'Scotland', 'gb-wls': 'Wales', 'gb-nir': 'Northern Ireland', gb: 'Great Britain|GB|Team GB',
  us: 'USA|United States of America|US', kr: 'Korea Republic|Republic of Korea|Korea', kp: 'Korea DPR|DPR Korea',
  cz: 'Czech Republic', sk: 'Slovak Republic', ci: 'Ivory Coast|Cote d Ivoire', tr: 'Turkey|Turkiye', nl: 'Holland',
  ie: 'Republic of Ireland|Ireland', ba: 'Bosnia and Herzegovina|Bosnia-Herzegovina|Bosnia', mk: 'Macedonia|FYR Macedonia',
  hk: 'Hong Kong|Hong Kong China', tw: 'Chinese Taipei|Taiwan', ps: 'Palestine', cd: 'DR Congo|Congo DR', cg: 'Congo',
  ae: 'UAE|United Arab Emirates', ru: 'Russia', ir: 'Iran|IR Iran', vn: 'Vietnam', cv: 'Cape Verde|Cabo Verde',
  sz: 'Swaziland|Eswatini', mm: 'Myanmar|Burma', la: 'Laos', sy: 'Syria', md: 'Moldova', bo: 'Bolivia', ve: 'Venezuela',
  tz: 'Tanzania', xk: 'Kosovo', va: 'Vatican', gr: 'Hellas', ch: 'Swiss',
};
const LOCALES = ['en', 'el', 'de', 'fr', 'es', 'it', 'pt', 'nl', 'pl', 'tr', 'ro', 'hr', 'sr-Latn', 'sl', 'cs', 'hu', 'sv', 'da',
  'nb', 'fi', 'ru', 'uk', 'bg', 'ar'];
// what a side carries besides its country: "Australia (W)", "England U21", "Brasil Femenino"
const MARKERS = /\b(w|women|womens|woman|ladies|femenino|feminino|femminile|feminine|frauen|damen|kobiety|zeny|u ?\d{2}|xi|a|b|ii)\b/g;

const fold = (s) => String(s || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '')
  .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
const bare = (label) => fold(label).replace(MARKERS, ' ').replace(/\s+/g, ' ').trim();

let NAMES = null;                               // folded name -> code
function names() {
  if (NAMES) return NAMES;
  NAMES = new Map();
  const add = (name, code) => { const k = fold(name); if (k && !NAMES.has(k)) NAMES.set(k, code); };
  for (const [code, list] of Object.entries(EXTRA)) for (const n of list.split('|')) add(n, code);
  for (const loc of LOCALES) {
    let dn;
    try { dn = new Intl.DisplayNames([loc], { type: 'region' }); } catch { continue; }
    for (const code of CODES) {
      try { const n = dn.of(code.toUpperCase()); if (n && n !== code.toUpperCase()) add(n, code); } catch { /* not a region here */ }
    }
  }
  return NAMES;
}

// 'Australia (W)' -> 'au'; '' when the label isn't a country
export function flagCode(label) {
  const k = bare(label);
  return (k && names().get(k)) || '';
}

// both sides of a match, only when both are countries ("Georgia vs Alabama" is college football)
export function pairFlags(labels) {
  const codes = labels.map(flagCode);
  return codes.every(Boolean) ? codes : labels.map(() => '');
}
