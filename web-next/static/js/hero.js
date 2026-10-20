// Featured hero for Films / Series: a small, deliberate rotation instead of "newest forever".
//
// - The set changes every WINDOW_H hours (local time) and is the same for every load inside a
//   window: candidates are drawn with a PRNG seeded by the window number, not Math.random().
// - Five slots, each with its own pool: new, highly rated, continue watching, rediscovery (older
//   good titles and your favourites), and a second new one. Each slot lists a few fallbacks; the
//   page tries them in order until one has a real backdrop (no backdrop -> not a hero).
// - Titles featured in the previous two windows are skipped, so consecutive windows differ.
// - Junk is never eligible: no poster, no year, sports replays, "|"-separated listings, titles
//   with dates, and (by the catalogue language preference) non-English versions.
// Pure functions: the caller supplies the catalogue, progress, favourites and history.

export const WINDOW_H = 6;

export function windowOf(nowMs, tzOffsetMin = 0) {
  return Math.floor((nowMs / 60000 - tzOffsetMin) / (WINDOW_H * 60));
}

function hash(str) {                    // FNV-1a
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return h >>> 0;
}

export function rng(seed) {             // mulberry32
  let a = hash(String(seed));
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function sample(arr, n, rand) {         // n distinct items, seeded
  const a = arr.slice();
  const out = [];
  while (a.length && out.length < n) out.push(a.splice(Math.floor(rand() * a.length), 1)[0]);
  return out;
}

const JUNK = /\||\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b|\bS\d{1,2}\s?E\d{1,3}\b/i;

// "Practical Magic 2", "Practical Magic", "Practical Magic: The Return" -> "practical magic": a set never
// features two of one franchise (or two versions of one film).
export function stem(clean) {
  let s = String(clean || '').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g, '');
  s = s.split(/\s[:\-–—]\s|:\s/)[0];
  s = s.replace(/\b(part|chapter|vol(ume)?|episode)\s+\w+$/, '').replace(/\s+(\d+|[ivx]+)$/, '');
  return s.replace(/[^a-z0-9]+/g, ' ').trim().split(' ').slice(0, 3).join(' ');
}

// item: {id, name, img, year, rating}; info: {clean, prefix, tier}
export function eligible(item, info, langPref, relaxed = false) {
  if (!item || !item.img || !item.year || item.year < 1930) return false;
  if (!info.clean || info.clean.length < 2 || JUNK.test(item.name)) return false;
  if (/^(SOC|SPORT|WWE|UFC|NBA|NFL)\b/.test(info.prefix || '')) return false;
  // English or unlabelled versions; with no language preference ('all') a slot that has none may
  // fall back to a foreign-catalogue version - never a dubbed one
  if (info.tier <= 1) return true;
  return relaxed && langPref !== 'only' && langPref !== 'first' && info.tier <= 2;
}

// -> [{slot, ids: [id, ...fallbacks]}] in slot order; ids never repeat across slots.
// ctx: { kind, window, items, byId, sortedBy(sort) -> items, info(item), progress: [ids recent first],
//        favs: [ids], recent: Set of ids featured lately, langPref, nowYear }
export function candidates(ctx) {
  const { kind, window, info, langPref, recent = new Set(), nowYear = new Date().getFullYear() } = ctx;
  const used = new Set();
  const stems = new Set();
  const ok = (it, relaxed = false) => it && !used.has(it.id) && !recent.has(it.id) && !stems.has(stem(info(it).clean))
    && eligible(it, info(it), langPref, relaxed);
  const mark = (it) => { used.add(it.id); stems.add(stem(info(it).clean)); };
  const out = [];
  const take = (slot, pool, n = 4) => {
    const rand = rng(`${kind}|${window}|${slot}`);
    let fit = pool.filter((it) => ok(it));
    if (!fit.length) fit = pool.filter((it) => ok(it, true));
    // fallbacks for one slot may share a franchise with each other, never with another slot
    const picked = [];
    for (const it of sample(fit, fit.length > 400 ? 400 : fit.length, rand)) {
      if (picked.length >= n) break;
      if (!picked.some((p) => stem(info(p).clean) === stem(info(it).clean))) picked.push(it);
    }
    if (picked.length) { picked.forEach(mark); out.push({ slot, ids: picked.map((it) => it.id) }); }
  };
  const rated = (lo, hi, y0, y1) => ctx.sortedBy('rating').slice(0, 6000)
    .filter((it) => it.rating >= lo && it.rating <= hi && it.year >= y0 && it.year <= y1);
  const cont = ctx.progress.map((id) => ctx.byId.get(id)).filter(Boolean);
  if (kind === 'movies') {
    const fresh = ctx.sortedBy('added').slice(0, 160);
    take('new', fresh);
    take('top', rated(7.2, 9.3, 1995, nowYear));
    if (cont.length) { const c = cont.filter((it) => ok(it)).slice(0, 2); if (c.length) { c.forEach(mark); out.push({ slot: 'continue', ids: c.map((it) => it.id) }); } }
    const favs = ctx.favs.map((id) => ctx.byId.get(id)).filter(Boolean);
    take('rediscover', favs.length >= 3 && rng(`${window}|fav`)() < 0.5 ? favs : rated(6.8, 9.3, 1970, nowYear - 3));
    take('new2', fresh);
  } else {
    if (cont.length) { const c = cont.filter((it) => ok(it)).slice(0, 2); if (c.length) { c.forEach(mark); out.push({ slot: 'continue', ids: c.map((it) => it.id) }); } }
    take('top', rated(7.6, 9.3, 2005, nowYear));
    const favs = ctx.favs.map((id) => ctx.byId.get(id)).filter(Boolean);
    if (favs.length) take('fav', favs, 3);
    take('new', ctx.sortedBy('year').slice(0, 1500).filter((it) => it.rating >= 6.8 && it.rating <= 9.3));
    take('rediscover', rated(7.0, 9.3, 1985, nowYear - 4));
  }
  return out;
}

// History of what was featured, per kind: [{w, ids}], newest first, at most 3 windows.
export function recentIds(history, window) {
  return new Set((history || []).filter((h) => h.w < window && h.w >= window - 2).flatMap((h) => h.ids));
}

export function remember(history, window, ids) {
  const rest = (history || []).filter((h) => h.w !== window);
  return [{ w: window, ids }, ...rest].sort((a, b) => b.w - a.w).slice(0, 3);
}
