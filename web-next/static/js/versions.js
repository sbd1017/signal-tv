// Other versions of the same film or series in the catalogue (the provider lists one per language
// or quality: "EN - GoodFellas (1990)", "DE-TOP - 07. GoodFellas (1990)", "IR - GoodFellas (1990) …").
// Linked on a title's page, never merged: each stays its own item with its own progress.
//
// Same title = same cleaned title (chart numbers "17." dropped) and the same year. A version without
// a year only counts when every dated version of that title agrees on one year, so remakes ("Dune"
// 1984 / 2021) never mix. Pure functions; the catalogue lists come from api.js.

import { film, category } from './names.js?v=__V__';
import { versionTier, versionCode, titleKey, TIER } from './lang.js?v=__V__';

const fold = (s) => String(s || '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '');

// The title for matching: "17. GoodFellas" in a TOP list is GoodFellas.
export function matchTitle(raw) {
  const f = film(raw);
  const t = /(^|-)TOP(-|$)/.test(f.prefix) ? f.title.replace(/^\d{1,3}\.\s+/, '') : f.title;
  return { title: t, year: f.year, prefix: f.prefix, uhd: f.uhd };
}

// -> the other versions of `item` in `items`, the viewer's language first (`want`, English unless they
// chose another; then unknown, foreign-catalogue, dubbed), each { item, tier, label } - tier always as
// seen from English (englishVersion relies on it). `items`: catalogue list items ({ id, name, key, cat, year }).
export function versionsOf(item, items, cats = new Map(), want = 'en') {
  const me = matchTitle(item.name);
  const year = me.year || item.year || 0;
  const needle = fold(me.title).trim();
  if (!needle) return [];
  const cands = [];
  for (const it of items) {
    if (it.id === item.id || !it.key.includes(needle)) continue;
    const m = matchTitle(it.name);
    const k = titleKey(m.title, 1);                 // punctuation-blind; empty for non-Latin titles
    if (fold(m.title).trim() !== needle && !(k && k === titleKey(me.title, 1))) continue;
    cands.push({ it, m, y: m.year || it.year || 0 });
  }
  const years = new Set([year, ...cands.map((c) => c.y)].filter(Boolean));
  const out = [];
  for (const c of cands) {
    const sameYear = year && c.y ? c.y === year : years.size <= 1;   // undated: only when the dates agree
    if (!sameYear) continue;
    out.push({ item: c.it, tier: versionTier(c.it.name), rank: versionTier(c.it.name, want), label: label(c.it.name) });
  }
  out.sort((a, b) => a.rank - b.rank || a.label.localeCompare(b.label));
  disambiguate([{ item, label: label(item.name) }, ...out], cats);
  return out;
}

const NAMES = {
  EN: 'English', UK: 'English', US: 'English', DE: 'German', FR: 'French', ES: 'Spanish', IT: 'Italian', NL: 'Dutch',
  'BE-NL': 'Flemish', PL: 'Polish', PT: 'Portuguese', BR: 'Brazilian', TR: 'Turkish', GR: 'Greek', RU: 'Russian',
  SC: 'Nordic', SE: 'Swedish', DK: 'Danish', NO: 'Norwegian', FI: 'Finnish', IS: 'Icelandic', IR: 'Persian', AR: 'Arabic',
  'AR-SUBS': 'Arabic subtitles', 'AR-DUB': 'Arabic', IN: 'Indian', PK: 'Pakistani', AL: 'Albanian', RO: 'Romanian',
  BG: 'Bulgarian', HR: 'Croatian', SR: 'Serbian', SI: 'Slovenian', EX: 'Ex-Yu', IL: 'Hebrew', KU: 'Kurdish', CZ: 'Czech',
  HU: 'Hungarian', LA: 'Latin American', QC: 'Québécois', PH: 'Filipino', JP: 'Japanese', BN: 'Bengali', AF: 'African',
  'IN-EN': 'Indian · English', AS: 'Asian',
  // the provider's streaming-service catalogues (language not stated: usually the original)
  NF: 'Netflix', AMZ: 'Amazon', 'D+': 'Disney+', 'A+': 'Apple TV+', VP: 'Viaplay', PRMT: 'Paramount+', 'DSC+': 'Discovery+',
};

// "4K-DE - GoodFellas (1990)" -> "German 4K"; "EN-TOP - 17. GoodFellas" -> "English"; no prefix -> "Other".
export function label(raw) {
  const m = matchTitle(raw);
  const code = versionCode(m.prefix);
  const base = NAMES[code.split('-')[0]];
  const name = NAMES[code] || (base && /-S$/.test(code) ? `${base} subtitles` : base) || (code && code !== 'TOP' ? code : 'Other');
  return m.uhd ? `${name} 4K` : name;
}

// Two versions with the same label get their category after it: "English · IMDb Top 250", "English · Drama";
// any still alike (the same category listed twice) are numbered: "Arabic subtitles · … (2)".
function disambiguate(list, cats) {
  const count = (l) => { const m = new Map(); for (const v of l) m.set(v.label, (m.get(v.label) || 0) + 1); return m; };
  let seen = count(list);
  for (const v of list) {
    if (seen.get(v.label) > 1 && v.item.cat && cats.get(v.item.cat)) {
      const c = category(cats.get(v.item.cat));
      v.label = `${v.label} · ${c.title || cats.get(v.item.cat)}`;
    }
  }
  seen = count(list);
  const n = new Map();
  for (const v of list) {
    if (seen.get(v.label) < 2) continue;
    const k = (n.get(v.label) || 0) + 1;
    n.set(v.label, k);
    if (k > 1) v.label = `${v.label} (${k})`;
  }
}

// Is this version's description probably not in English? Its own label decides (a foreign or dubbed
// catalogue); an unlabelled version only when the text is in a non-Latin script.
const NON_LATIN = /[Ͱ-ϿЀ-ӿ֐-׿؀-ۿݐ-ݿऀ-෿฀-๿぀-ヿ一-鿿가-힯]/g;
export function foreignPlot(rawName, plot) {
  const t = versionTier(rawName);
  if (t === TIER.EN || !plot) return false;
  if (t === TIER.SUB || t === TIER.DUB) return true;
  const letters = (plot.match(/\p{L}/gu) || []).length;
  return letters > 0 && (plot.match(NON_LATIN) || []).length / letters > 0.3;
}

// The English version to borrow a description from: English audio first, a dated one, not 4K
// (4K catalogues are more often re-labelled), else the first English one.
export function englishVersion(versions) {
  const en = versions.filter((v) => v.tier === TIER.EN);
  return en.find((v) => !matchTitle(v.item.name).uhd) || en[0] || null;
}
