// web-next (the /tv-test interface): language preferences, Sports broadcaster order, Film hero
// rotation and Series shuffle. Pure modules, real provider names as fixtures.
//   node --test tests/test_next.mjs
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { feedLang, feedRegion, orderFeeds, versionTier, versionCode, applyLangPref, titleKey, TIER } from '../web-next/static/js/lang.js';
import { windowOf, candidates, eligible, recentIds, remember, rng, stem } from '../web-next/static/js/hero.js';
import { pickEpisode } from '../web-next/static/js/shuffle.js';
import { film, parse, teams, caps, twinLabel, cardTitle, eventStatus } from '../web-next/static/js/names.js';
import { versionsOf, label, foreignPlot, englishVersion, matchTitle } from '../web-next/static/js/versions.js';
import { sides } from '../web-next/static/js/sportsart.js';

// ------------------------------------------------------------------ broadcaster language
test('feed language: country prefixes, packages, name words, unknown', () => {
  const L = (n, c = '') => feedLang(n, c).lang;
  assert.equal(L('UK: TALK SPORT ᴿᴬᵂ', 'UK| SPORT ᴴᴰ ⱽᴵᴾ'), 'en');
  assert.equal(L('VIP: SKY SPORTS MAIN EVENT HD', 'UK| SPORT VIP'), 'en');            // package -> category
  assert.equal(L('NOW: SKY SPORTS MAIN EVENT ᴴᴰ', 'UK| NOW TV'), 'en');
  assert.equal(L('US: BEIN SPORTS 2 HD', 'US| SPORT ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ'), 'en');
  assert.equal(L('GR: COSMOTE SPORTS 2 ᴿᴬᵂ', '8K| SPORT ON AIR ⁸ᴷ'), 'xx');              // own prefix beats an 8K category
  assert.equal(L('WOW: SKY SPORT F1 ᴴᴰ ◉', 'DE| WOW SPORT ᴴᴰ'), 'xx');                   // package WOW -> DE
  assert.equal(L('M+: M.DEPORTES ᴿᴬᵂ', 'ES| MOVISTAR ᴿᴬᵂ'), 'xx');
  assert.equal(L('UK: BEIN SP⚽RTS 1 ENGLISH ᴴᴰ ◉', 'UK| SPORT ᴴᴰ'), 'en');
  assert.equal(L('◉: beIN Sp⚽rts 1 ENGLISH 4K', 'AR| BEIN SPORTS ◉ ⚽'), 'en');          // name says English
  assert.equal(L('8K: beIN SP⚽RTS 2 FRANCE ᴿᴬᵂ', 'AR| BEIN SPORTS'), 'xx');             // name says France
  assert.equal(L('8K: beIN SP⚽RTS 1 SD', 'AR| BEIN SPORTS ⁸ᴷ & SD ⚽'), 'xx');           // Arabic category
  assert.equal(L('DSTV: SUPERSPORT PL HD', 'AFR| DSTV VIP HD/4K'), 'en');
  assert.equal(L('SG: HUB beIN SPORTS 1 ᴿᴬᵂ', '8K| SPORT ON AIR'), '');                  // mixed region: unknown
  assert.equal(L('CH: BLUE SPORT 1', 'CH| SWITZERLAND HD/4K'), '');
  assert.equal(L('CH: BLUE SPORT 2 LIVE D ᴿᴬᵂ', '8K| SPORT ON AIR'), 'xx');               // Swiss German feed
  assert.equal(L('CH: BLUE ZOOM FR ᴿᴬᵂ', '8K| SPORT ON AIR'), 'xx');
  assert.equal(L('SPORTS 24', ''), '');                                                  // nothing to go on
  assert.equal(L('US: TUDN ᴴᴰ', 'US| SPORT'), 'xx');                                     // Spanish-language US
  assert.equal(feedRegion('ENG: X', ''), 'UK');
});

const F = (id, lang, ok = 2) => ({ id, lang, ok });

test('broadcaster order: All keeps the server (quality) order', () => {
  const feeds = [F('gr', 'xx'), F('uk', 'en'), F('sg', '')];
  assert.deepEqual(orderFeeds(feeds, 'all').map((f) => f.id), ['gr', 'uk', 'sg']);
});

test('broadcaster order: English first, unknown next, foreign last, quality kept inside', () => {
  const feeds = [F('gr4k', 'xx'), F('uk1080', 'en'), F('sg', ''), F('uk720', 'en'), F('hr', 'xx')];
  assert.deepEqual(orderFeeds(feeds, 'en').map((f) => f.id), ['uk1080', 'uk720', 'sg', 'gr4k', 'hr']);
});

test('broadcaster order: International picks the best foreign feed, not just the first', () => {
  const feeds = [F('uk', 'en'), F('gr-bad', 'xx', 0), F('hr', 'xx', 2), F('sg', '')];
  assert.deepEqual(orderFeeds(feeds, 'intl').map((f) => f.id), ['hr', 'sg', 'uk', 'gr-bad']);
});

test('broadcaster order: only English / only foreign / unknown-only events still have a default', () => {
  assert.equal(orderFeeds([F('a', 'en'), F('b', 'en')], 'intl')[0].id, 'a');
  assert.equal(orderFeeds([F('a', 'xx'), F('b', 'xx')], 'en')[0].id, 'a');
  assert.equal(orderFeeds([F('a', ''), F('b', '')], 'en')[0].id, 'a');
  const feeds = [F('a', 'xx'), F('b', 'en'), F('c', '')];
  assert.equal(orderFeeds(feeds, 'en').length, 3, 'nothing dropped: one event, every broadcaster');
});

test('broadcaster order: an unsmooth preferred feed never outranks a smooth one', () => {
  const feeds = [F('uk-unsmooth', 'en', 0), F('gr', 'xx', 2)];
  assert.deepEqual(orderFeeds(feeds, 'en').map((f) => f.id), ['gr', 'uk-unsmooth']);
});

// ------------------------------------------------------------------ catalogue language
test('version tiers from provider prefixes', () => {
  assert.equal(versionTier('EN - The Machinist (2004)'), TIER.EN);
  assert.equal(versionTier('4K-EN - Tupac (2005)'), TIER.EN);
  assert.equal(versionTier('DE - Strung (2026)'), TIER.DUB);
  assert.equal(versionTier('4K-FR-HDR - Retour à Zombieland (2019)'), TIER.DUB);
  assert.equal(versionTier('DE-DO - Dominion (2005)'), TIER.DUB);
  assert.equal(versionTier('IN-EN - UNABOMBER (2026)'), TIER.DUB);                       // Hindi-dubbed English films
  assert.equal(versionTier('GR - Practical Magic 2 (2026)'), TIER.SUB);
  assert.equal(versionTier('AR-SUBS - Dune'), TIER.SUB);
  assert.equal(versionTier('NF - The Family (2017)'), TIER.UNKNOWN);
  assert.equal(versionTier('TOP - Practical Magic 2 (2026)'), TIER.UNKNOWN);
  assert.equal(versionTier('Plain Title'), TIER.UNKNOWN);
  assert.equal(versionCode('4K-ES-HDR'), 'ES');
  assert.equal(versionTier('GR - Peter Pan (GR AUDIO) (1953)'), TIER.DUB);                // the title says dubbed
  assert.equal(versionTier('IR - Practical Magic 2 (2026) جادوی عملی ۲ - دوبله'), TIER.DUB);
  assert.equal(versionTier('IR - Practical Magic 2 (2026) جادوی عملی 2'), TIER.SUB);
  assert.equal(versionTier('AR-CAM - Practical Magic 2 (2026)'), TIER.SUB);
});

const cat = (names) => names.map((n, i) => ({ id: String(i), name: n }));
const infoOf = (it) => { const f = film(it.name); return { tier: versionTier(it.name), key: titleKey(f.title, f.year) }; };
const ids = (xs) => xs.map((x) => x.name);

test('language preference All: unchanged', () => {
  const items = cat(['GR - Ballerina (2025)', 'EN - Ballerina (2025)', 'DE - Ballerina (2025)']);
  assert.deepEqual(applyLangPref(items, 'all', infoOf), items);
});

test('English first: versions gather at the first one, English leading; other titles keep their place', () => {
  const items = cat(['GR - Ballerina (2025)', 'EN - Dune (2021)', 'DE - Ballerina (2025)', 'EN - Ballerina (2025)', 'NF - Ballerina (2025)']);
  assert.deepEqual(ids(applyLangPref(items, 'first', infoOf)),
    ['EN - Ballerina (2025)', 'NF - Ballerina (2025)', 'GR - Ballerina (2025)', 'DE - Ballerina (2025)', 'EN - Dune (2021)']);
});

test('English only: drops dubbed, drops subtitled only when an English/unknown version exists, keeps unknown', () => {
  const items = cat(['GR - Ballerina (2025)', 'EN - Ballerina (2025)', 'DE - Ballerina (2025)',
    'GR - Kapodistrias: The Governor (2025)', 'DE - Strung (2026)', 'NF - Bros (IL)', 'TOP - Goat (2026)']);
  assert.deepEqual(ids(applyLangPref(items, 'only', infoOf)),
    ['EN - Ballerina (2025)', 'GR - Kapodistrias: The Governor (2025)', 'NF - Bros (IL)', 'TOP - Goat (2026)']);
});

test('items without a year never group (weekly shows stay separate)', () => {
  const items = cat(['EN - WWE SmackDown', 'DE - Film (2020)', 'EN - WWE SmackDown']);
  assert.equal(titleKey(film('EN - WWE SmackDown').title, film('EN - WWE SmackDown').year), '');
  assert.deepEqual(ids(applyLangPref(items, 'first', infoOf)), ['EN - WWE SmackDown', 'DE - Film (2020)', 'EN - WWE SmackDown']);
});

// ------------------------------------------------------------------ hero rotation
function catalogue() {
  const items = [];
  const add = (name, year, rating, added, img = 'x') => items.push({ id: `m${items.length}`, name, year, rating, added, img });
  const word = (i) => String.fromCharCode(97 + (i % 26)) + String.fromCharCode(97 + Math.floor(i / 26)) + 'ville';   // distinct titles
  for (let i = 0; i < 60; i++) add(`EN - New Film ${word(i)} (2026)`, 2026, 6 + (i % 4), 2_000_000 - i);
  for (let i = 0; i < 60; i++) add(`EN - Classic ${word(i + 60)} (${1990 + (i % 25)})`, 1990 + (i % 25), 7.3 + (i % 15) / 10, 1_000 + i);
  add('DE - Neu (2026)', 2026, 7.5, 3_000_000);                                // newest of all, but German
  add('SOC - Winnipeg Jets at Chicago Blackhawks 31.03.20', 2020, 8, 2_500_000);  // sports replay
  add('EN - No Poster (2026)', 2026, 8, 2_400_000, '');                          // no artwork
  const byId = new Map(items.map((i) => [i.id, i]));
  const sorted = { added: [...items].sort((a, b) => b.added - a.added), rating: [...items].sort((a, b) => b.rating - a.rating), year: [...items].sort((a, b) => b.year - a.year) };
  return { items, byId, sortedBy: (s) => sorted[s] };
}
const info = (it) => { const f = film(it.name); return { clean: f.title, prefix: f.prefix, tier: versionTier(it.name) }; };
const ctx = (c, window, extra = {}) => ({ kind: 'movies', window, items: c.items, byId: c.byId, sortedBy: c.sortedBy, info,
  progress: [], favs: [], recent: new Set(), langPref: 'first', nowYear: 2026, ...extra });

test('hero: five distinct slots, eligible titles only, not simply the newest', () => {
  const c = catalogue();
  const slots = candidates(ctx(c, 100, { progress: ['m70'] }));
  assert.deepEqual(slots.map((s) => s.slot), ['new', 'top', 'continue', 'rediscover', 'new2']);
  const all = slots.flatMap((s) => s.ids);
  assert.equal(new Set(all).size, all.length, 'no title in two slots');
  for (const id of all) assert.ok(eligible(c.byId.get(id), info(c.byId.get(id)), 'first'), `${c.byId.get(id).name} eligible`);
  const names = all.map((id) => c.byId.get(id).name);
  assert.ok(!names.some((n) => /^DE -|^SOC -|No Poster/.test(n)), 'German version, sports replay and missing art excluded');
  assert.notEqual(c.byId.get(slots[0].ids[0]).name, `EN - New Film aaville (2026)`, 'not just the newest');
});

test('hero: stable inside a window, different in the next', () => {
  const c = catalogue();
  const a = JSON.stringify(candidates(ctx(c, 200)));
  assert.equal(JSON.stringify(candidates(ctx(c, 200))), a);
  assert.notEqual(JSON.stringify(candidates(ctx(c, 201))), a);
  const t = Date.UTC(2026, 9, 13, 10, 0) ;
  assert.equal(windowOf(t), windowOf(t + 3600_000), 'an hour later: same window');
  assert.notEqual(windowOf(t), windowOf(t + 6 * 3600_000), 'six hours later: next window');
});

test('hero: titles featured in the last two windows are not repeated', () => {
  const c = catalogue();
  const first = candidates(ctx(c, 300)).map((s) => s.ids[0]);
  let hist = remember([], 300, first);
  const next = candidates(ctx(c, 301, { recent: recentIds(hist, 301) })).flatMap((s) => s.ids);
  assert.ok(!first.some((id) => next.includes(id)));
  hist = remember(hist, 301, next.slice(0, 5));
  hist = remember(hist, 302, ['zz']);
  assert.ok(!recentIds(hist, 303).has(first[0]), 'three windows later it may come back');
});

test('hero: with no language preference, English/unlabelled versions still come first', () => {
  const c = catalogue();
  c.items.forEach((it, i) => { if (/New Film/.test(it.name) && i % 3 === 0) it.name = it.name.replace(/^EN/, 'GR'); });
  const first = candidates(ctx(c, 500, { langPref: 'all' })).find((s) => s.slot === 'new').ids;
  assert.ok(first.every((id) => !/^GR/.test(c.byId.get(id).name)), 'English versions exist, so no Greek-catalogue hero');
  c.items.forEach((it) => { it.name = it.name.replace(/^EN/, 'GR'); });
  const only = candidates(ctx(c, 500, { langPref: 'all' })).flatMap((s) => s.ids);
  assert.ok(only.length, 'nothing English at all: Greek-catalogue versions may stand in');
  assert.equal(candidates(ctx(c, 500, { langPref: 'first' })).length, 0, 'but not when English is preferred');
});

test('hero: one franchise (or one film\'s versions) at most once per set', () => {
  assert.equal(stem('Practical Magic 2'), stem('Practical Magic'));
  assert.equal(stem('John Wick: Chapter 4'), stem('John Wick'));
  assert.equal(stem('Rocky IV'), 'rocky');
  assert.notEqual(stem('The Matrix'), stem('The Mummy'));
  const c = catalogue();
  c.items.forEach((it, i) => { if (/New Film/.test(it.name)) it.name = `EN - Saga ${i % 3 ? 'Returns' : ''} ${i % 5 + 1} (2026)`; });
  const slots = candidates(ctx(c, 600));
  const firsts = slots.map((s) => stem(film(c.byId.get(s.ids[0]).name).title));
  assert.equal(new Set(firsts).size, firsts.length, firsts.join(' / '));
});

test('hero: English only never features a non-English version', () => {
  const c = catalogue();
  c.items.forEach((it, i) => { if (i % 2) it.name = it.name.replace(/^EN/, 'FR'); });
  const all = candidates(ctx(c, 400, { langPref: 'only' })).flatMap((s) => s.ids);
  assert.ok(all.length >= 4);
  assert.ok(all.every((id) => /^EN/.test(c.byId.get(id).name)));
});

// ------------------------------------------------------------------ shuffle
const show = (sizes) => sizes.map((n, si) => ({ n: si + 1, episodes: Array.from({ length: n }, (_, e) => ({ id: `s${si + 1}e${e + 1}` })) }));

test('shuffle: whole series draws from every season', () => {
  const seen = new Set();
  const r = rng('a');
  for (let i = 0; i < 300; i++) seen.add(pickEpisode(show([10, 10, 10]), { rng: r }).s.n);
  assert.deepEqual([...seen].sort(), [1, 2, 3]);
});

test('shuffle: a chosen season stays inside that season', () => {
  const r = rng('b');
  for (let i = 0; i < 100; i++) assert.equal(pickEpisode(show([5, 8, 3, 12]), { season: 4, rng: r }).s.n, 4);
});

test('shuffle: never the episode playing or just watched when there is a choice', () => {
  const r = rng('c');
  for (let i = 0; i < 200; i++) {
    const p = pickEpisode(show([3]), { avoid: ['s1e1', 's1e2'], rng: r });
    assert.equal(p.ep.id, 's1e3');
  }
});

test('shuffle: one-episode series and all-avoided pools still play something', () => {
  assert.equal(pickEpisode(show([1]), { avoid: ['s1e1'] }).ep.id, 's1e1');
  assert.equal(pickEpisode(show([2]), { avoid: ['s1e1', 's1e2'], rng: () => 0 }).ep.id, 's1e1');
  assert.equal(pickEpisode([], {}), null);
  assert.equal(pickEpisode(show([0, 2]), { season: 1, rng: () => 0 }).ep.id, 's2e1', 'empty season: whole show');
});

test('shuffle: a filter (future "unwatched only") narrows the pool, never empties it', () => {
  const watched = new Set(['s1e1', 's1e2']);
  assert.equal(pickEpisode(show([3]), { filter: (s, ep) => !watched.has(ep.id), rng: () => 0.9 }).ep.id, 's1e3');
  assert.ok(pickEpisode(show([2]), { filter: () => false }));
});

test('shuffle: episodes seen lately are left out; when all were, the longest-unseen are drawn from', () => {
  const now = 1_800_000_000_000;
  const day = 86400e3;
  const seen = { s1e1: now - 5 * 60e3, s1e2: now - 60e3, s1e4: now - 40 * day };
  const r = rng('e');
  const got = new Set();
  for (let i = 0; i < 300; i++) got.add(pickEpisode(show([5]), { avoid: ['s1e2'], seenAt: (id) => seen[id] || 0, now, rng: r }).ep.id);
  assert.deepEqual([...got].sort(), ['s1e3', 's1e4', 's1e5'], 'minutes-ago s1e1 never comes back; a month-old one may');
  const all = { s1e1: now - 3 * day, s1e2: now - 2 * day, s1e3: now - 60e3 };
  for (let i = 0; i < 50; i++) assert.equal(pickEpisode(show([3]), { seenAt: (id) => all[id], now, rng: r }).ep.id, 's1e1', 'the oldest third');
  assert.equal(pickEpisode(show([1]), { seenAt: () => now, now }).ep.id, 's1e1', 'one episode still plays');
});

test('shuffle: a series with 100+ episodes stays uniform-ish', () => {
  const r = rng('d');
  const counts = new Map();
  for (let i = 0; i < 6000; i++) { const id = pickEpisode(show([60, 60]), { rng: r }).ep.id; counts.set(id, (counts.get(id) || 0) + 1); }
  assert.equal(counts.size, 120);
  assert.ok(Math.max(...counts.values()) < 110, 'no episode dominates');
});

// ------------------------------------------------------------------ names (presentation only)
test('names: provider decorations become title / prefix / tags', () => {
  assert.deepEqual(parse('YP: 9X JALWA ᴿᴬᵂ'), { title: '9X JALWA', prefix: 'YP', tags: ['RAW'], sep: false });
  assert.equal(parse('##### YUPP TV PREMIUM ᴿᴬᵂ #####').sep, true);
  assert.equal(film('4K-FR-HDR - La Course des animaux (2026)').title, 'La Course des animaux');
  assert.deepEqual(teams('Liverpool vs Atlético Madrid'), ['Liverpool', 'Atlético Madrid']);
  assert.equal(teams('Formula 1: Practice 1'), null);
});

test('capitals follow each script: Greek drops stress marks, Turkish keeps its i, accents elsewhere stay', () => {
  const C = (t) => caps(t).text;
  assert.equal(C('Ρεάλ Μαδρίτης'), 'ΡΕΑΛ ΜΑΔΡΙΤΗΣ');
  assert.equal(C('Ολυμπιακός'), 'ΟΛΥΜΠΙΑΚΟΣ');
  assert.equal(C('Χόφενχαϊμ'), 'ΧΟΦΕΝΧΑΪΜ');                     // diaeresis kept
  assert.equal(C('Παναθηναϊκός – ΑΕΚ'), 'ΠΑΝΑΘΗΝΑΪΚΟΣ – ΑΕΚ');
  assert.equal(caps('Ρεάλ').lang, 'el');
  assert.equal(C('Beşiktaş'), 'BEŞİKTAŞ');
  assert.equal(C('Fenerbahçe'), 'FENERBAHÇE');
  assert.equal(C('Śląsk Wrocław'), 'ŚLĄSK WROCŁAW');
  assert.equal(C('Čukarički · Hajduk Split · Željezničar'), 'ČUKARIČKI · HAJDUK SPLIT · ŽELJEZNIČAR');
  assert.equal(C('Saint-Étienne'), 'SAINT-ÉTIENNE');
  assert.equal(C('Borussia Mönchengladbach'), 'BORUSSIA MÖNCHENGLADBACH');
  assert.equal(C('Grêmio · São Paulo · Atlético'), 'GRÊMIO · SÃO PAULO · ATLÉTICO');
  assert.equal(C('Зенит Санкт-Петербург'), 'ЗЕНИТ САНКТ-ПЕТЕРБУРГ');
  assert.equal(caps('Зенит').lang, 'ru');
  assert.equal(C('FK Bodø/Glimt'), 'FK BODØ/GLIMT');
});

// ------------------------------------------------------------------ versions (linked, never merged)
const GOODFELLAS = [   // the provider's 14 versions, as listed (Oct 2026)
  ['m1', 'EN-TOP - 17. GoodFellas (1990)', 'c1'], ['m2', 'EN - GoodFellas (1990)', 'c2'], ['m3', 'DE-TOP - 07. GoodFellas (1990)', 'c3'],
  ['m4', '4K-DE - GoodFellas (1990)', 'c4'], ['m5', 'NL - GoodFellas (1990)', 'c5'], ['m6', '4K-NL - GoodFellas', 'c6'],
  ['m7', '4K-PL - GoodFellas (1990)', 'c7'], ['m8', 'GR - GoodFellas (1990)', 'c8'], ['m9', 'SC - GoodFellas (1990)', 'c9'],
  ['m10', 'IS - GoodFellas (1990)', 'c10'], ['m11', 'IR - GoodFellas (1990) رفقای خوب - زیرنویس فارسی', 'c11'],
  ['m12', '4K-AR - GoodFellas (1990)', 'c12'], ['m13', 'AR-SUBS - GoodFellas (1990)', 'c13'], ['m14', 'AR-SUBS - GoodFellas (1990)', 'c14'],
];
const listOf = (rows, extra = []) => [...rows, ...extra].map(([id, name, c, year]) => ({ id, name, cat: c, year: year || film(name).year, key: name.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '') }));
const CATS = new Map([['c1', 'EN - IMDB TOP 250'], ['c2', 'EN - DRAMA'], ['c13', 'أفلام أجنبية قديمه'], ['c14', 'AR - OLD']]);

test('versions: every version of the same film, English first, chart numbers ignored', () => {
  const items = listOf(GOODFELLAS, [['x1', 'EN - Goodfellas Reunion (2020)', 'c2'], ['x2', 'EN - The GoodFellas Story (1990)', 'c2']]);
  const vs = versionsOf(items.find((i) => i.id === 'm11'), items, CATS);
  assert.equal(vs.length, 13, 'the 13 others; look-alike titles are not versions');
  assert.deepEqual(vs.slice(0, 2).map((v) => v.item.id).sort(), ['m1', 'm2'], 'English (incl. the EN-TOP chart list) first');
  assert.ok(vs.some((v) => v.item.id === 'm6'), 'an undated version counts when every dated one agrees on the year');
  assert.equal(label('4K-DE - GoodFellas (1990)'), 'German 4K');
  assert.equal(label('IR - GoodFellas (1990) رفقای خوب'), 'Persian');
  assert.equal(label('Some Film (2020)'), 'Other');
  assert.equal(label('4K-NF - East of Eden (2026) (US)'), 'Netflix 4K');
  assert.equal(label('AR-TR-S - Kuruluş Osman (2019)'), 'Arabic subtitles');
  assert.equal(label('D+ - Andor (2022)'), 'Disney+');
  const en = vs.filter((v) => v.label.startsWith('English')).map((v) => v.label).sort();
  assert.deepEqual(en, ['English · DRAMA', 'English · IMDB TOP 250'], 'same label: the category tells them apart');
  assert.equal(matchTitle('DE-TOP - 07. GoodFellas (1990)').title, 'GoodFellas');
  const twin = new Map([...CATS, ['c14', 'أفلام أجنبية قديمه']]);           // both Arabic versions in one-named categories
  const ar = versionsOf(items.find((i) => i.id === 'm11'), items, twin).filter((v) => v.label.startsWith('Arabic subtitles')).map((v) => v.label);
  assert.equal(new Set(ar).size, 2, `labels stay distinct: ${ar}`);
});

test('versions: remakes and same-named films of another year stay apart', () => {
  const items = listOf([['d1', 'EN - Dune (1984)', 'a'], ['d2', 'EN - Dune (2021)', 'a'], ['d3', 'DE - Dune (2021)', 'b'], ['d4', 'NL - Dune', 'c']]);
  const vs = versionsOf(items[1], items);
  assert.deepEqual(vs.map((v) => v.item.id), ['d3'], 'the 1984 film is not a version; an undated one is ambiguous, so left out');
});

test('versions: non-Latin titles match exactly, not by substring', () => {
  const items = listOf([['a1', 'AR - العراب (1972)', 'a'], ['a2', 'AR-SUBS - العراب (1972)', 'b'], ['a3', 'AR - العراب الجزء الثاني (1972)', 'a']]);
  assert.deepEqual(versionsOf(items[0], items).map((v) => v.item.id), ['a2']);
});

test('versions: which descriptions are not English, and which version to borrow from', () => {
  assert.ok(foreignPlot('IR - GoodFellas (1990)', 'هنری کودکی است که دلش می خواهد گانگستر شود'));
  assert.ok(foreignPlot('DE-TOP - 07. GoodFellas (1990)', 'Jimmy und Tommy können machen, was sie wollen.'), 'a German catalogue');
  assert.ok(!foreignPlot('EN - GoodFellas (1990)', 'The true story of Henry Hill'));
  assert.ok(!foreignPlot('Some Film (2020)', 'Ein Film über etwas.'), 'unlabelled Latin text: cannot tell, left alone');
  assert.ok(foreignPlot('Some Film (2020)', 'Фильм о чём-то важном и интересном'), 'unlabelled, but Cyrillic');
  assert.ok(!foreignPlot('IR - X (1990)', ''), 'no description: nothing to replace');
  const items = listOf(GOODFELLAS);
  const pick = englishVersion(versionsOf(items.find((i) => i.id === 'm11'), items));
  assert.ok(['m1', 'm2'].includes(pick.item.id));
  assert.equal(englishVersion([]), null);
  assert.equal(versionCode('EN-TOP'), 'EN');
  assert.equal(versionTier('DE-TOP - 07. GoodFellas (1990)'), TIER.DUB, 'chart lists are their language');
});

// ------------------------------------------------------------------ which crest goes on which side
test('sides: a lone known team only goes where its name fits, never by position', () => {
  const pair = ['Viking', 'Bayern Munich'];
  const fits = (id, label) => id === 'team:bayern-munich' && /bayern/i.test(label);
  const nofits = () => false;                                       // the Sports team list not loaded yet
  assert.deepEqual(sides(pair, ['team:bayern-munich'], ['', ''], fits), ['', 'team:bayern-munich'], 'the reported bug: Viking got Bayern');
  assert.deepEqual(sides(pair, ['team:bayern-munich'], ['', ''], nofits), ['', ''], 'unknown which side: neither, until the Pi says');
  assert.deepEqual(sides(pair, ['team:bayern-munich'], ['team:viking', 'team:bayern-munich'], nofits), ['team:viking', 'team:bayern-munich'],
    'the Pi\'s per-name answer settles both');
  assert.deepEqual(sides(['Bayern Munich', 'Viking'], ['team:bayern-munich'], ['', ''], fits), ['team:bayern-munich', '']);
});

test('sides: two ids keep the order their names give', () => {
  const fits = (id, label) => (id === 'team:a' && label === 'Alpha') || (id === 'team:b' && label === 'Beta');
  assert.deepEqual(sides(['Alpha', 'Beta'], ['team:b', 'team:a'], ['', ''], fits), ['team:a', 'team:b']);
  assert.deepEqual(sides(['Alpha', 'Beta'], ['team:a', 'team:b'], ['', ''], () => false), ['team:a', 'team:b']);
});

// ------------------------------------------------------------------ channels sharing a name
test('twin channels: the first real difference, else the provider channel number; unique names get nothing', () => {
  const cats = new Map([['br', 'BR| BRAZIL ᴴᴰ/ᴿᴬᵂ'], ['now', 'UK| NOW TV SPORT ᴴᴰ/ᴿᴬᵂ'], ['8k', '8K| SPORT ON AIR ⁸ᴷ'], ['ch', 'CH| SWITZERLAND HD/4K']]);
  const ch = (id, name, cat, num) => ({ id, name, cat, num, key: name.toLowerCase() });
  const items = [ch('g1', 'BR: GLOBO SP HD', 'br', 47761), ch('g2', 'BR: GLOBO SP HD', 'br', 47772),
    ch('s1', 'NOW: SKY SPORTS MAIN EVENT ᴿᴬᵂ', 'now', 16527), ch('s2', 'UK: SKY SPORTS MAIN EVENT ᴿᴬᵂ', '8k', 14580),
    ch('s3', 'UK: SKY SPORTS MAIN EVENT ᴴᴰ', '8k', 14581), ch('b1', 'CH: BLUE SPORT 1', 'ch', 31445)];
  assert.equal(twinLabel(items[0], items, cats), 'Ch 47761', 'identical in every respect: the provider number');
  assert.equal(twinLabel(items[1], items, cats), 'Ch 47772');
  assert.equal(twinLabel(items[2], items, cats), 'NOW', 'its region is its own');
  assert.equal(twinLabel(items[3], items, cats), 'UK · RAW', 'region and quality are each shared, together they are not');
  assert.equal(twinLabel(items[4], items, cats), 'HD');
  assert.equal(twinLabel(items[5], items, cats), '', 'a unique name gets no extra line');
});

test('card titles: event channels show the event, ordinary names with a bar are left alone', () => {
  const t = (raw, want) => assert.equal(cardTitle(raw), want, raw);
  t('(Fanatiz 064) | Alianza vs Inter Bogotá (2026-10-24 17:05:00)', 'Alianza vs Inter Bogotá');
  t('End | Palmeiras vs. Corinthians | all | 11-10-2026 | 22:00 (GMT) | 8K EXCLUSIVE | BR: SOCCER PPV 11', 'Palmeiras vs. Corinthians');
  t('US (ESPN+ 106) | Soccer: Duquesne vs. #10 Pitt (2026-10-13 19:02:25)', 'Soccer: Duquesne vs. #10 Pitt');
  t('(US) (BTN+ 029) | Ice Hockey (W): Ohio State at St. Thomas (2026-10-03 14:50:05)', 'Ice Hockey (W): Ohio State at St. Thomas');
  t('NEXT | COSTA RICA U16 VS. GUATEMALA U16 | Tue 13 Oct 19:30 EDT (US) | 8K EXCLUSIVE | US: FIFA+ PPV 3', 'COSTA RICA U16 VS. GUATEMALA U16');
  t('- NO EVENT STREAMING - | 8K EXCLUSIVE | US: ESPN+ PPV 836', 'NO EVENT STREAMING');
  t('NO EVENT STREAMING NOW - | 8K EXCLUSIVE | US: SOCCER PPV 72', 'NO EVENT STREAMING NOW');
  t('AT&T: FOX 4 LOCAL DALLAS | FORT WORTH ᴿᴬᵂ', 'FOX 4 LOCAL DALLAS | FORT WORTH');
  t('F1: LEWIS HAMILTON | FERRARI | HAM', 'LEWIS HAMILTON | FERRARI | HAM');
  t('IN-PREM: FEMALE SINGER HD | 1', 'IN-PREM: FEMALE SINGER HD | 1');
  t('UK: PREMIER SPORTS 1 IRELAND HEVC 4K', 'PREMIER SPORTS 1 IRELAND');
});

test('event status: the word the provider puts first, for the line under the card title', () => {
  assert.equal(eventStatus('End | Palmeiras vs. Corinthians | all | 11-10-2026 | 22:00 (GMT) | 8K EXCLUSIVE | BR: SOCCER PPV 11'), 'Ended');
  assert.equal(eventStatus('NEXT | COSTA RICA U16 VS. GUATEMALA U16 | Tue 13 Oct 19:30 EDT (US) | 8K EXCLUSIVE | US: FIFA+ PPV 3'), 'Up next');
  assert.equal(eventStatus('Live | Cavaliers vs. Magic | all | 8K EXCLUSIVE | US: SOCCER PPV 55'), 'Live now');
  assert.equal(eventStatus('(Fanatiz 064) | Alianza vs Inter Bogotá (2026-10-24 17:05:00)'), '');
  assert.equal(eventStatus('UK: SKY SPORTS MAIN EVENT ᴿᴬᵂ'), '');
  assert.equal(eventStatus('LIVE TV'), '');
});
