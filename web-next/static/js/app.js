// Signal TV "Signal" - app shell, router and views. No framework; all provider text is
// inserted with textContent (never innerHTML). Shares the API, sync store and player logic
// with the current interface (web/); only presentation and navigation differ.
import { BASE, FAMILY, LSK, api, catalogue, cached, dropCatalogue, epgNow, fold, search, searchGuide, sortedItems, usedCats, h, icon, setIcon, thumb,
  chunked, toast, fmtClock, fmtDuration, fmtTime, img, imgv, setImg, NEXT, STATIC, fmtDate, sameDay, tzOffset, timeMode, setTimeMode,
  piTimeZone, deviceTimeZone, setPiTimeZone } from './api.js?v=__V__';
import * as caps from './caps.js?v=__V__';
import * as store from './store.js?v=__V__';
import { Player } from './player.js?v=__V__';
import * as tracks from './tracks.js?v=__V__';
import * as names from './names.js?v=__V__';
import * as ambient from './ambient.js?v=__V__';
import * as lang from './lang.js?v=__V__';
import * as hero from './hero.js?v=__V__';
import * as shuffle from './shuffle.js?v=__V__';
import * as art from './sportsart.js?v=__V__';
import * as flags from './flags.js?v=__V__';
import * as versions from './versions.js?v=__V__';

const $ = (id) => document.getElementById(id);
const view = $('view');
const main = $('main');
const video = $('video');
const state = { section: '', cleanup: [], liveList: [], liveFilter: null, gridQuery: {}, seriesCache: new Map(), status: null, redraw: null,
  pageArt: '', sheetArt: '' };
const STORE_KIND = { live: 'live', movies: 'movie', series: 'series' };     // view name -> kind used for hidden categories
const TOUCH = matchMedia('(hover: none)').matches;

// ------------------------------------------------------------------ player
// Live: the stage is sized so the whole sticky column (picture, what's on, the guide strip) fits in the
// window - the space under the picture is measured, not guessed (it differs with fonts and wrapping).
function fitLiveColumn() {
  const col = document.getElementById('player');
  const stage = col && col.querySelector('.stage');
  if (!col || !stage || !('ResizeObserver' in window)) return;
  let last = 0;
  new ResizeObserver(() => {
    if (!document.querySelector('.main.live-mode')) return;
    const below = Math.ceil(col.offsetHeight - stage.offsetHeight) + 16;
    if (below > 40 && Math.abs(below - last) > 1) {
      last = below;
      document.documentElement.style.setProperty('--live-below', `${below}px`);
    }
  }).observe(col);
}

const player = new Player({
  onChannel: (d) => stepChannel(d),
  onLastChannel: () => lastChannel(),
  resumeIdle: () => { const c = player.idleChannel; if (c) playChannel(c); },
  nextEpisode: (item) => nextEpisode(item),
  onStarted: (item) => {
    if (item.kind === 'live') { markActiveChannel(item.id); renderLiveInfo(item); }
    playerCast(item);
    ambient.reset();
    updateAmbient();
  },
  onClosed: (item) => {
    playerCast(null);
    document.body.classList.remove('mini', 'on-air');
    if (item && item.kind === 'live') maybeIdle();
    if (['library', 'continue', 'favourites', 'recent'].includes(state.section)) render(true);
    refreshProgressBadges();
    updateAmbient();
  },
});

function playChannel(ch) {
  const item = { id: ch.id, kind: 'live', name: ch.name, img: ch.img, num: ch.num, sub: '' };
  const nn = guideData[ch.id];
  if (nn && nn.now) item.sub = nn.now[2];
  document.body.classList.remove('mini');
  player.open(item);
  if (state.section !== 'live') location.hash = '#/live';
}

function playVod(item, resume) {
  document.body.classList.remove('mini');
  player.open(item, { resume: resume || 0 });
  player.setTitles(ftitle(item.kind === 'episode' ? item.name : item.name), item.sub || '');
}

function stepChannel(delta) {
  const cur = player.item && player.item.kind === 'live' ? player.item.id : (player.idleChannel && player.idleChannel.id);
  let list = (state.liveList.length ? state.liveList : ((cached('live') || {}).items || [])).filter((c) => !names.parse(c.name).sep);
  if (!list.length) return;
  let i = list.findIndex((c) => c.id === cur);
  if (i < 0) { list = (cached('live') || {}).items || list; i = list.findIndex((c) => c.id === cur); }
  const next = list[(i + delta + list.length) % list.length];
  if (next) { playChannel(next); player.osd(`${next.num ? next.num + '   ' : ''}${names.parse(next.name).title}`); }
}

function lastChannel() {
  const prev = player.prevLive || store.lastChannel.previous();
  if (!prev) { toast('No previous channel yet.'); return; }
  const ch = ((cached('live') || {}).byId || new Map()).get(prev.id) || prev;
  playChannel(ch);
  player.osd(names.parse(ch.name).title);
}

// on-air tally + ambient follow the <video>
for (const ev of ['playing', 'pause', 'emptied', 'ended']) {
  video.addEventListener(ev, () => {
    document.body.classList.toggle('on-air', !!(player.isLive && !video.paused && !video.ended));
    updateAmbient();
  });
}

// The mini player: a live channel keeps playing while you look around the rest of the app.
const stage = $('stage');
stage.addEventListener('click', (e) => {
  if (!document.body.classList.contains('mini')) return;
  if (e.target.closest('#p-close')) return;
  e.stopPropagation();
  e.preventDefault();
  location.hash = '#/live';
}, true);
$('p-expand').addEventListener('click', () => { location.hash = '#/live'; });

// What lights the room: the picture while a video is on screen (live stage or cinema), else the
// page's artwork (details backdrop, film hero, idle channel logo), else nothing.
function updateAmbient() {
  const mini = document.body.classList.contains('mini');
  const sheetOpen = !$('sheet').hidden;
  const vod = player.mode === 'vod';
  const liveStage = player.mode === 'live' && state.section === 'live' && !mini && !sheetOpen;
  if ((vod || liveStage) && player.item) ambient.follow(video); else ambient.unfollow();
  let art = '';
  if (vod && player.item) art = imgv(player.item.img, 'poster-s');
  else if (sheetOpen) art = state.sheetArt;
  else if (liveStage) art = imgv((player.item || player.idleChannel || {}).img, 'logo');
  else art = state.pageArt;
  ambient.art(art || null);
}

// ------------------------------------------------------------------ router
const SECTIONS = ['live', 'sports', 'movies', 'series', 'search', 'library', 'continue', 'favourites', 'recent', 'settings'];

function parseHash() {
  const [sec, id] = location.hash.replace(/^#\/?/, '').split('/');
  return { sec: SECTIONS.includes(sec) ? sec : 'live', id: id || '' };
}

function route() {
  const { sec, id } = parseHash();
  if (sec !== state.section) {
    const leavingLive = state.section === 'live' && sec !== 'live';
    if (leavingLive && player.isLive) document.body.classList.add('mini');
    else if (leavingLive && player.mode === 'live') player.showMode('off');      // the idle "resume" card stays on Live
    if (sec === 'live') document.body.classList.remove('mini');
    state.section = sec;
    state.pageArt = '';
    render();
  }
  for (const a of document.querySelectorAll('[data-nav]')) {
    const on = a.dataset.nav === sec || (a.dataset.nav === 'library' && ['continue', 'favourites', 'recent'].includes(sec));
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  moveTabIndicator();
  if (id && (sec === 'movies' || sec === 'series')) openDetails(sec, id);
  else closeSheet(false);
  updateAmbient();
}

// ---- this device's layout (Settings › Layout): whether the Sports tab shows, and the page the app opens
// on. Per device, so a TV that never needs Sports can leave it out; every page stays the same.
const LAYOUT_SPORTS = `${LSK}showSports`;
const LAYOUT_START = `${LSK}start`;
const START_PAGES = [['live', 'Live TV'], ['movies', 'Films'], ['series', 'Series'], ['library', 'Library'], ['sports', 'Sports']];
const lsGet = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };
const sportsShown = () => lsGet(LAYOUT_SPORTS, '1') !== '0';
const startPage = () => {
  const v = lsGet(LAYOUT_START, 'live');
  return START_PAGES.some(([k]) => k === v) && (v !== 'sports' || sportsShown()) ? v : 'live';
};
function applyLayout() {
  for (const a of document.querySelectorAll('[data-nav="sports"]')) a.hidden = !sportsShown();
  for (const a of document.querySelectorAll('a.mark')) a.setAttribute('href', `#/${startPage()}`);
  requestAnimationFrame(moveTabIndicator);
}

function moveTabIndicator() {
  const ind = $('tab-ind');
  const a = $('tabs').querySelector('a[aria-current="page"]');
  if (!a) { ind.classList.remove('on'); return; }
  ind.style.width = `${a.offsetWidth}px`;
  ind.style.transform = `translateX(${a.offsetLeft}px)`;
  ind.classList.add('on');
}
window.addEventListener('resize', moveTabIndicator);

function render(keepScroll = false) {
  for (const fn of state.cleanup.splice(0)) { try { fn(); } catch { /* ignore */ } }
  main.classList.toggle('live-mode', state.section === 'live');
  if (!keepScroll) window.scrollTo(0, 0);
  const fn = { live: viewLive, sports: viewSports, movies: () => viewGrid('movies'), series: () => viewGrid('series'), search: viewSearch,
    library: viewLibrary, continue: viewLibrary, favourites: viewLibrary, recent: viewLibrary, settings: viewSettings }[state.section];
  fn();
  if (!keepScroll) { view.classList.remove('view-enter'); void view.offsetWidth; view.classList.add('view-enter'); }
  document.title = { live: 'Live', sports: 'Sports', movies: 'Films', series: 'Series', search: 'Search', settings: 'Settings' }[state.section] || 'Library';
  document.title += ' · TV';
}

// ------------------------------------------------------------------ shared bits
function skeletonRows(n, cls = 'sk-row') { return h('div', { class: 'skeleton', 'aria-hidden': 'true' }, Array.from({ length: n }, () => h('div', { class: cls }))); }
function skeletonGrid(n) { return h('div', { class: 'grid skeleton', 'aria-hidden': 'true' }, Array.from({ length: n }, () => h('div', { class: 'sk-card' }))); }

function errorBox(message, retry) {
  return h('div', { class: 'state', role: 'alert' },
    h('p', { class: 'state-title', text: 'Something went wrong' }),
    h('p', { text: message }),
    retry ? h('button', { class: 'btn primary', type: 'button', onclick: retry, text: 'Retry' }) : null);
}

function emptyBox(title, text, extra) {
  return h('div', { class: 'state' }, h('p', { class: 'state-title', text: title }), text ? h('p', { text }) : null, extra || null);
}

function providerHint() {
  const st = state.status;
  if (!st) return null;
  if (!st.configured) return h('p', { class: 'muted small', text: 'No provider is configured yet. On the Pi run: iptv set-playlist (or iptv set-xtream).' });
  if (st.error) return h('p', { class: 'muted small', text: `Last refresh problem: ${st.error}` });
  return null;
}

function head(title, sub, ...tools) {
  return h('header', { class: 'head' },
    h('div', { class: 'head-titles' }, h('h1', { text: title }), sub instanceof Node ? sub : h('span', { class: 'sub', text: sub || '' })),
    h('div', { class: 'head-tools' }, ...tools));
}

function seg(label, options, value, onpick) {
  const box = h('div', { class: 'seg', role: 'tablist', 'aria-label': label });
  for (const [v, t] of options) {
    const b = h('button', { type: 'button', role: 'tab', text: t, 'aria-selected': String(v === value), dataset: { v } });
    b.addEventListener('click', () => {
      for (const x of box.children) x.setAttribute('aria-selected', String(x === b));
      onpick(v);
    });
    box.append(b);
  }
  return box;
}

function searchField(placeholder, label) {
  const input = h('input', { class: 'input', type: 'search', placeholder, 'aria-label': label, enterkeyhint: 'search', autocomplete: 'off', spellcheck: 'false' });
  return [h('label', { class: 'field' }, icon('search'), input), input];
}

function paintFav(b) {
  const on = store.favs.has(b.dataset.favId);
  b.classList.toggle('on', on);
  b.setAttribute('aria-pressed', on ? 'true' : 'false');
  b.setAttribute('aria-label', on ? `Remove ${b.dataset.favName} from favourites` : `Add ${b.dataset.favName} to favourites`);
}

function favButton(id, meta, onChange) {
  const b = h('button', { class: 'fav-btn', type: 'button', dataset: { favId: id, favName: meta.name || '' } }, icon('star'));
  b.addEventListener('click', (e) => {
    e.stopPropagation();
    const on = store.favs.toggle(id, meta);
    paintFav(b);
    toast(on ? 'Added to favourites' : 'Removed from favourites', 1600);
    if (onChange) onChange(on);
  });
  paintFav(b);
  return b;
}

function progressBar(frac, cls = '') {
  const bar = h('span', { class: `pbar ${cls}` }, h('span'));
  bar.firstChild.style.width = `${Math.round(Math.max(0, Math.min(1, frac)) * 100)}%`;
  return bar;
}

// A channel's display name: prefix (faint mono), title, tags. Raw name kept for screen readers.
function chName(raw, { tags = 2, prefix = true } = {}) {
  const p = names.parse(raw);
  const out = [];
  if (prefix && p.prefix) out.push(h('span', { class: 'pfx', text: p.prefix }));
  out.push(h('span', { class: 'nm', text: p.title }));
  for (const t of p.tags.slice(0, tags)) out.push(h('span', { class: `tag ${/^(4K|8K|UHD|FHD|60fps|50fps)$/.test(t) ? 'hot' : ''}`, text: t }));
  return out;
}
const plain = (raw) => names.parse(raw).title;
const ftitle = (raw) => names.film(raw).title;
// Language/package prefix as a small tag (EN, 4K-FR-HDR...), year in mono: under posters and titles.
function filmMeta(raw, year, rating) {
  const f = names.film(raw);
  const y = year || f.year;
  return [f.prefix ? h('span', { class: `tag ${f.uhd ? 'hot' : ''}`, text: f.prefix }) : null, y ? h('span', { text: String(y) }) : null,
    rating ? h('span', { text: `★ ${Number(rating).toFixed(1)}` }) : null].filter(Boolean);
}

// One channel showing a programme: logo, name and the quality this device gets (search results,
// Sports). c: {id, label, est, ok, ch} (tvapp/epgsearch.py channel_groups).
function feedButton(c) {
  const ch = c.ch;
  const short = (c.label || '').split(' · ')[0];
  const tip = c.est ? 'Estimated from the channel name; the exact format is learned when it is played'
    : c.conv ? `Converted from ${c.conv} to ${c.label} on the Pi: this device can't decode the original`
    : c.ok === 2 ? `Best version for this device: ${c.label}` : c.ok === 1 ? `${c.label}: may not play smoothly here`
      : c.ok === 0 ? `${c.label}: not smooth on this device; another version will be offered` : '';
  const fl = c.lang !== undefined ? c : feedInfo(ch);
  const b = h('button', { class: 'feed', type: 'button', title: tip, 'aria-label': `Play ${ch.name}${short ? `, ${short}` : ''}` },
    thumb(ch.img, ch.name, 'logo sm'), h('span', { class: 'nm', text: plain(ch.name) }),
    fl.region ? h('span', { class: `reg ${fl.lang === 'en' ? 'en' : ''}`, text: fl.region, title: fl.lang === 'en' ? 'English commentary' : fl.lang === 'xx' ? 'Foreign-language feed' : 'Language not known' }) : null,
    qualityBadge(c));
  b.addEventListener('click', () => playChannel(ch));
  return b;
}

function qualityBadge(c) {
  const short = (c.label || '').split(' · ')[0];
  if (!short) return '';
  return h('span', { class: `q-badge ${c.est ? 'est' : ''} ${c.ok === 2 ? 'ok' : c.conv ? '' : c.ok >= 0 ? 'bad' : ''}`, text: c.est ? `~${short}` : short });
}

// A channel's commentary language and region (lang.js), from its name and category.
function feedInfo(ch) {
  const live = cached('live');
  return lang.feedLang(ch.name, live && live.cats ? live.cats.get(ch.cat) || '' : '');
}

// Channels the viewer hasn't hidden (channels or their categories), as in Live's "All" list, each with
// its language; then ordered for the Sports commentary preference (English / International / All).
function visibleFeeds(channels, list, pref = 'all') {
  const hch = store.hidden.channels();
  const hc = store.hidden.cats('live');
  const out = [];
  for (const c of channels) {
    const ids = c.ids.filter((i) => { const it = list.byId.get(i); return it && !hch.has(i) && !hc.has(it.cat); });
    const ch = list.byId.get(ids.includes(c.id) ? c.id : ids[0]);
    if (ch) out.push({ ...c, ch, ...lang.feedLang(ch.name, list.cats.get(ch.cat) || '') });
  }
  return lang.orderFeeds(out, pref);
}

// "in 25 min", "19:30", "Tue 01:00"
function whenText(ts, now) {
  const mins = Math.round((ts - now) / 60);
  if (mins <= 60) return `in ${Math.max(1, mins)} min`;
  return sameDay(ts, now) ? fmtClock(ts) : `${fmtDate(ts, { weekday: 'short' })} ${fmtClock(ts)}`;
}

function minsLeft(stop, now) {
  const m = Math.max(0, Math.round((stop - now) / 60));
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m left` : `${m} min left`;
}

function selectEl(label, options, value, onchange) {
  const sel = h('select', { class: 'select', 'aria-label': label });
  for (const [v, t] of options) sel.append(h('option', { value: v, text: t }));
  sel.value = value;
  sel.addEventListener('change', () => onchange(sel.value));
  return sel;
}

// Programme search results (guide index on the Pi), grouped Live now / Starting soon / Later.
// allow: Set of channel ids that may be offered (null = any); open: Set of expanded sections.
function programmeSections(d, list, allow, open) {
  const sections = { live: [], soon: [], later: [] };
  for (const ev of (d && d.events) || []) {
    const chans = [];
    for (const c of ev.channels) {
      const ids = allow ? c.ids.filter((i) => allow.has(i)) : c.ids;
      const ch = list.byId.get(ids.includes(c.id) ? c.id : ids[0]);
      if (ch) chans.push({ ...c, ch });
    }
    if (chans.length) sections[ev.when].push({ ...ev, chans });
  }
  const shown = sections.live.length + sections.soon.length + sections.later.length;
  const out = [];
  for (const [when, title] of [['live', 'On now'], ['soon', 'Starting soon'], ['later', 'Later']]) {
    const evs = sections[when];
    if (!evs.length) continue;
    const ol = h('ol', { class: 'prog-list', role: 'list' });
    const more = h('button', { class: 'btn ghost small prog-more', type: 'button' });
    const LIMIT = 5;
    const paint = (all) => {
      ol.replaceChildren(...(all ? evs : evs.slice(0, LIMIT)).map(programmeRow));
      more.hidden = all || evs.length <= LIMIT;
      more.textContent = `Show ${evs.length - LIMIT} more`;
    };
    more.addEventListener('click', () => { open.add(when); paint(true); });
    paint(open.has(when));
    out.push(h('section', { class: 'prog-sec' }, h('h2', { class: `prog-sec-head ${when}`, text: title }), ol, more));
  }
  if (d && d.broad && shown) out.push(h('p', { class: 'muted small', text: 'Lots of programmes match: showing only what is on now and starting soon. Add a word to see later ones.' }));
  return { shown, nodes: out };
}

function programmeRow(ev) {
  const now = Date.now() / 1000;
  const top = h('div', { class: 'prog-head' });
  if (ev.when === 'live') top.append(h('span', { class: `live-pill ${ev.replay ? 'replay' : ''}`, text: ev.replay ? 'Replay' : 'Live' }));
  else top.append(h('span', { class: `when ${ev.when}`, text: whenText(ev.start, now) }));
  top.append(h('strong', { class: `prog-title ${isFavEvent(ev.fav_ids) ? 'is-fav' : ''}`, text: ev.title }));
  const rows = [top, h('div', { class: 'prog-time' }, `${fmtClock(ev.start)}–${fmtClock(ev.stop)}`,
    ev.when === 'live' ? progressBar((now - ev.start) / (ev.stop - ev.start), 'thin live') : '',
    ev.sub ? h('span', { class: 'prog-sub', text: ev.sub }) : '')];
  if (ev.strength < 2 && ev.desc) rows.push(h('p', { class: 'prog-desc', text: ev.desc }));
  const chs = h('div', { class: 'prog-chs' });
  const SHOW = 3;
  const paint = (all) => {
    chs.replaceChildren(...(all ? ev.chans : ev.chans.slice(0, SHOW)).map(feedButton));
    const rest = ev.chans.length - SHOW + (ev.more || 0);
    if (!all && ev.chans.length > SHOW + 1) {
      chs.append(h('button', { class: 'chip prog-chs-more', type: 'button', text: `+${rest} more`, onclick: () => paint(true) }));
    }
  };
  paint(ev.chans.length <= SHOW + 1);
  rows.push(chs);
  return h('li', { class: `prog ${ev.strength < 2 ? 'weak' : ''}` }, ...rows);
}

// ------------------------------------------------------------------ LIVE: stage + rail
let guideData = {};

async function viewLive() {
  const [qField, q] = searchField('Channels and programmes', 'Search channels and programmes');
  const body = h('div', { class: 'rail-body' }, skeletonRows(10));
  view.replaceChildren(h('div', { class: 'rail' }, h('div', { class: 'rail-head' }, qField), body));
  maybeIdle();
  let list;
  try {
    [list, guideData] = await Promise.all([catalogue('live'), epgNow()]);
  } catch (e) {
    body.replaceChildren(errorBox(e.message, () => render()));
    return;
  }
  if (state.section !== 'live') return;
  if (!player.item) maybeIdle();          // redraw the "last watched" card now the guide has loaded
  if (!list.items.length) {
    body.replaceChildren(emptyBox('No channels', 'The playlist has no live channels.', providerHint()));
    return;
  }
  const filter = state.liveFilter || { mode: store.prefs.get('liveMode', 'all'), cat: store.prefs.get('liveCat', ''), q: '' };
  filter.edit = false;
  if (filter.cat && !list.counts.has(filter.cat)) filter.cat = '';
  state.liveFilter = filter;
  const modes = seg('Channel groups', [['all', 'All'], ['fav', 'Favourites'], ['recent', 'Recent']], filter.mode, (m) => {
    filter.mode = m; store.prefs.set('liveMode', m); draw(); paintProgrammes();
  });
  const catLabel = h('span');
  const catBtn = h('button', { class: 'select cat-btn', type: 'button', 'aria-haspopup': 'dialog' }, catLabel);
  catBtn.addEventListener('click', () => openCategoryPicker({
    title: 'Live categories', kind: 'live', list, current: filter.cat, extra: [['', 'All categories']],
    onPick: (id) => { filter.cat = id; store.prefs.set('liveCat', id); draw(); paintProgrammes(); }, onHide: () => { draw(); paintProgrammes(); },
  }));
  const editBtn = h('button', { class: 'round', type: 'button', 'aria-pressed': 'false', 'aria-label': 'Hide channels', title: 'Hide channels' }, icon('eye-off'));
  const editNote = h('div', { class: 'edit-note', hidden: true },
    h('span', { text: 'Tap channels to hide or show them, on all your devices.' }),
    h('button', { class: 'btn small primary', type: 'button', text: 'Done', onclick: () => editBtn.click() }));
  editBtn.addEventListener('click', () => {
    filter.edit = !filter.edit;
    editBtn.setAttribute('aria-pressed', String(filter.edit));
    editBtn.classList.toggle('on', filter.edit);
    editNote.hidden = !filter.edit;
    draw();
    findProgrammes();
  });
  q.value = filter.q;
  q.addEventListener('input', () => { filter.q = q.value; draw(); findProgrammes(); });
  const count = h('span', { class: 'rail-count' });
  const ul = h('ul', { class: 'ch-list', role: 'list' });
  const progBox = h('div', { class: 'prog-results', hidden: true, 'aria-live': 'polite' });
  const chHead = h('h2', { class: 'list-head', text: 'Channels', hidden: true });
  view.querySelector('.rail-head').append(h('div', { class: 'rail-row' }, modes, catBtn, editBtn), editNote, count);
  body.replaceChildren(progBox, chHead, ul);

  // Everything the current mode / category / hidden settings show, before the search words.
  function shown() {
    let items = list.items;
    if (filter.mode === 'fav') { const f = store.favs.all(); items = items.filter((i) => f[i.id]); }
    if (filter.mode === 'recent') {
      const order = store.recent.list().filter((r) => r.kind === 'live').map((r) => r.id);
      items = order.map((id) => list.byId.get(id)).filter(Boolean);
    }
    if (filter.cat) items = items.filter((i) => i.cat === filter.cat);
    if (filter.mode === 'all') {
      // Hidden categories drop out of "All categories" (a picked one still shows); hidden
      // channels drop out unless editing. Favourites and Recent always show everything.
      const hc = store.hidden.cats('live');
      const hch = store.hidden.channels();
      if ((hc.size && !filter.cat) || (hch.size && !filter.edit)) {
        items = items.filter((i) => (filter.cat || !hc.has(i.cat)) && (filter.edit || !hch.has(i.id)));
      }
    }
    return items;
  }

  function current() {
    let items = shown();
    if (filter.q.trim()) {
      const terms = fold(filter.q).split(/\s+/).filter(Boolean);
      items = items.filter((i) => !names.parse(i.name).sep && terms.every((t) => i.key.includes(t) || String(i.num) === t));
    }
    return items;
  }

  let stopChunks = null;
  function draw() {
    const hiddenCats = store.hidden.cats('live').size;
    const c = filter.cat ? names.category(list.cats.get(filter.cat) || 'Category') : null;
    catLabel.textContent = `${c ? [c.region, c.title].filter(Boolean).join(' · ') : 'All categories'}${hiddenCats ? `  ·  ${hiddenCats} hidden` : ''}`;
    const items = current();
    state.liveList = items;
    shownIds = null;
    setCount();
    if (stopChunks) stopChunks();
    if (!items.length) {
      emptyList();
      return;
    }
    stopChunks = chunked(ul, items, (ch) => channelRow(ch, filter.edit), { chunk: 80 });
    if (player.item && player.item.kind === 'live') markActiveChannel(player.item.id);
  }

  function setCount() {
    const n = state.liveList.filter((c) => !names.parse(c.name).sep).length;
    const p = progs.shown;
    count.textContent = `${n.toLocaleString()} channel${n === 1 ? '' : 's'}${p ? ` · ${p} programme${p === 1 ? '' : 's'}` : ''}`;
  }

  function emptyList() {
    if (progs.shown) { ul.replaceChildren(h('li', { class: 'empty-li muted small', text: 'No channel names match.' })); return; }
    ul.replaceChildren(h('li', { class: 'empty-li' }, emptyBox(filter.mode === 'fav' ? 'No favourite channels yet' : 'Nothing here',
      filter.mode === 'fav' ? 'Tap the star next to a channel to add it.' : 'Try another category or filter.')));
  }

  // ---- programmes: the guide searched on the Pi (tvapp/epgsearch.py), after a pause in typing
  const progs = { timer: 0, ctl: null, data: null, shown: 0, open: new Set() };
  let shownIds = null;
  function allowed() {
    if (filter.mode === 'all' && !filter.cat && !store.hidden.cats('live').size && !store.hidden.channels().size) return null;
    if (!shownIds) shownIds = new Set(shown().map((i) => i.id));
    return shownIds;
  }
  function findProgrammes(now = false) {
    clearTimeout(progs.timer);
    const text = filter.q.trim();
    if (filter.edit || fold(text).replace(/[^\p{L}\p{N}]/gu, '').length < 2) {
      if (progs.ctl) progs.ctl.abort();
      progs.data = null;
      paintProgrammes();
      return;
    }
    progs.timer = setTimeout(async () => {
      if (progs.ctl) progs.ctl.abort();
      const ctl = progs.ctl = new AbortController();
      progBox.classList.add('busy');
      try {
        const c = await caps.get(player.preferNative).catch(() => '');
        const d = await searchGuide(text, c, ctl.signal);
        if (ctl.signal.aborted || text !== filter.q.trim()) return;
        progs.data = d;
      } catch (e) {
        if (ctl.signal.aborted) return;
        progs.data = { events: [], error: e.message };
      } finally {
        if (progs.ctl === ctl) progBox.classList.remove('busy');
      }
      paintProgrammes();
    }, now ? 0 : 280);
  }
  function paintProgrammes() {
    const d = progs.data;
    const r = d && !filter.edit ? programmeSections(d, list, allowed(), progs.open) : { shown: 0, nodes: [] };
    progs.shown = r.shown;
    setCount();
    chHead.hidden = !progs.shown;
    if (!state.liveList.length) emptyList();
    if (!progs.shown) {
      progBox.hidden = !(d && d.error);
      progBox.replaceChildren(d && d.error ? h('p', { class: 'muted small', text: `Programme search: ${d.error}` }) : '');
      return;
    }
    progBox.replaceChildren(...r.nodes);
    progBox.hidden = false;
  }

  draw();
  findProgrammes(true);
  state.redraw = (changed) => {
    if (changed.has('hide') || (filter.mode !== 'all' && (changed.has('fav') || changed.has('recent')))) { draw(); paintProgrammes(); }
  };
  state.cleanup.push(() => stopChunks && stopChunks(), () => { state.redraw = null; clearTimeout(progs.timer); if (progs.ctl) progs.ctl.abort(); });
  const timer = setInterval(async () => {
    guideData = await epgNow(); updateGuideRows(); if (player.isLive) renderLiveInfo(player.item, false);
    if (progs.data) findProgrammes(true);                // what's on now has moved on
  }, 60000);
  state.cleanup.push(() => clearInterval(timer));
  if (player.isLive) renderLiveInfo(player.item);
}

// edit: the row hides/shows the channel instead of playing it (Live > Hide channels)
function channelRow(ch, edit = false) {
  const p = names.parse(ch.name);
  if (p.sep) return h('li', { class: 'ch-sep', role: 'presentation', text: p.title });
  const nn = guideData[ch.id];
  const li = h('li', { class: 'ch-li', dataset: { id: ch.id } });
  const btn = h('button', { class: 'ch', type: 'button', 'aria-label': `${ch.num ? 'Channel ' + ch.num + ', ' : ''}${ch.name}` },
    h('span', { class: 'ch-num', text: ch.num || '' }),
    thumb(ch.img, p.title, 'logo'),
    h('span', { class: 'ch-text' }, h('span', { class: 'ch-name' }, ...chName(ch.name)), epgLine(nn)));
  const meta = { name: ch.name, img: ch.img, kind: 'live', num: ch.num };
  if (!edit) {
    btn.addEventListener('click', () => playChannel(ch));
    li.append(btn, favButton(ch.id, meta));
    return li;
  }
  const eye = h('button', { class: 'fav-btn eye-btn', type: 'button' });
  const paint = () => {
    const off = store.hidden.channels().has(ch.id);
    li.classList.toggle('is-hidden', off);
    eye.setAttribute('aria-pressed', String(off));
    eye.setAttribute('aria-label', off ? `Show ${ch.name}` : `Hide ${ch.name}`);
    setIcon(eye, off ? 'eye-off' : 'eye');
  };
  const toggle = () => { store.hidden.setChannel(ch.id, meta, !store.hidden.channels().has(ch.id)); paint(); };
  btn.addEventListener('click', toggle);
  eye.addEventListener('click', toggle);
  li.append(btn, eye);
  paint();
  return li;
}

function epgLine(nn) {
  const wrap = h('span', { class: 'ch-epg' });
  fillEpg(wrap, nn);
  return wrap;
}

function fillEpg(wrap, nn) {
  wrap.replaceChildren();
  if (!nn || !nn.now) return;
  const now = Date.now() / 1000;
  const [s, e, t] = nn.now;
  wrap.append(h('span', { class: 'epg-now', text: t }), progressBar((now - s) / (e - s), 'thin'));
}

function updateGuideRows() {
  for (const li of document.querySelectorAll('.ch-li')) {
    const w = li.querySelector('.ch-epg');
    if (w) fillEpg(w, guideData[li.dataset.id]);
  }
}

function markActiveChannel(id) {
  for (const el of document.querySelectorAll('.ch-li.active')) el.classList.remove('active');
  const li = document.querySelector(`.ch-li[data-id="${CSS.escape(id)}"]`);
  if (li) {
    li.classList.add('active');
    const r = li.getBoundingClientRect();
    if (r.top < 0 || r.bottom > innerHeight) li.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
}

function maybeIdle() {
  if (state.section !== 'live' || player.item) return;
  const last = store.lastChannel.get();
  if (!last) { player.showMode('off'); return; }
  player.showIdle(last);
  $('p-idle-name').textContent = plain(last.name);
  renderLiveInfo(last);
  updateAmbient();
}

// Under the stage: the channel, what's on (big), and a timeline of what's next on it.
let infoFor = '';
async function renderLiveInfo(item, fresh = true) {
  const box = $('p-info');
  if (!item) { box.replaceChildren(); infoFor = ''; return; }
  const nn = guideData[item.id];
  const now = Date.now() / 1000;
  const p = names.parse(item.name);
  const chLine = h('div', { class: 'now-ch-name' }, item.num ? h('span', { class: 'num', text: String(item.num) }) : null,
    h('b', { text: p.title }), ...p.tags.slice(0, 3).map((t) => h('span', { class: 'tag', text: t })));
  const text = h('div', { class: 'now-ch' });
  if (nn && nn.now) {
    text.append(chLine);
    text.append(h('div', { class: 'now-title', text: nn.now[2] }),
      h('div', { class: 'now-meta' }, `${fmtClock(nn.now[0])}–${fmtClock(nn.now[1])}`,
        progressBar((now - nn.now[0]) / (nn.now[1] - nn.now[0]), player.isLive ? 'live' : ''), minsLeft(nn.now[1], now)));
    if (player.item && player.item.id === item.id) player.setTitles(p.title, nn.now[2]);
  } else {
    text.append(h('div', { class: 'now-title', text: p.title }),
      h('div', { class: 'now-meta' }, item.num ? h('span', { text: `CH ${item.num}` }) : null, ...p.tags.slice(0, 3).map((t) => h('span', { class: 'tag', text: t })),
        h('span', { text: 'No programme guide' })));
  }
  // a backup provider has this channel: switch to it (or back), e.g. when the main one stutters
  const res = player.item && player.item.id === item.id ? player.res : null;
  const swap = res && res.backup ? h('button', { class: 'btn ghost small', type: 'button',
    text: res.via === 'backup' ? 'Use main provider' : `Use ${res.backup}`, title: 'Play this channel from your other provider' }) : null;
  if (swap) swap.addEventListener('click', () => player.open(item, { via: res.via === 'backup' ? 'main' : 'backup' }));
  const card = h('div', { class: 'now-card' }, thumb(item.img, p.title, 'logo lg'), text,
    h('div', { class: 'now-actions' }, swap, favButton(item.id, { name: item.name, img: item.img, kind: 'live', num: item.num })));
  const keepTl = !fresh && infoFor === item.id && box.querySelector('.tl');
  const tl = keepTl || h('div', { class: 'tl' });
  const also = (!fresh && infoFor === item.id && box.querySelector('.also-on')) || h('section', { class: 'also-on', hidden: true });
  box.replaceChildren(card, also, tl);
  if (fresh || infoFor !== item.id) alsoShowing(item, also);
  if (keepTl || !nn) { if (!nn) tl.remove(); infoFor = item.id; return; }
  infoFor = item.id;
  try {
    const g = await api(`/epg/${item.id}`);
    if (infoFor !== item.id) return;
    paintTimeline(tl, g.rows || []);
  } catch { tl.remove(); }
}

// Watching a match: the other channels showing it (the Sports view's grouping of the guide), so the
// commentary - or the picture - can be changed without leaving Live. Ordered by the Sports commentary
// preference, the best version for this device first; hidden channels left out.
async function alsoShowing(item, box) {
  let d;
  try { d = await sportsData('today'); } catch { return; }
  if (!box.isConnected || infoFor !== item.id) return;          // another channel's info by now
  const mine = (c) => c.id === item.id || (c.ids || []).includes(item.id);
  const ev = (d.events || []).find((e) => e.when === 'live' && (e.channels || []).some(mine));
  const live = cached('live');
  if (!ev || !live) { box.hidden = true; return; }
  const feeds = visibleFeeds(ev.channels.filter((c) => !mine(c)), live, store.prefs.get('sportsFeeds', 'all'));
  if (!feeds.length) { box.hidden = true; return; }
  const SHOW = 8;
  const row = h('div', { class: 'fx-feeds' }, ...feeds.slice(0, SHOW).map(feedButton));
  const more = feeds.length > SHOW ? h('button', { class: 'btn ghost small', type: 'button', text: `${feeds.length - SHOW} more` }) : null;
  if (more) more.addEventListener('click', () => { row.append(...feeds.slice(SHOW).map(feedButton)); more.remove(); });
  box.replaceChildren(h('h3', { class: 'also-title', text: `Also showing ${ev.title}` }), row, ...(more ? [more] : []));
  box.hidden = false;
}

function paintTimeline(tl, rows) {
  const now = Date.now() / 1000;
  const items = rows.filter(([, e]) => e > now).slice(0, 14);
  if (!items.length) { tl.remove(); return; }
  const scroll = h('div', { class: 'tl-scroll', role: 'list' });
  const desc = h('p', { class: 'tl-desc', hidden: true });
  for (const [s, e, title, d] of items) {
    const on = s <= now && now < e;
    const w = Math.max(150, Math.min(420, ((e - s) / 60) * 2.6));
    const b = h('button', { class: `tl-item ${on ? 'on' : ''}`, type: 'button', role: 'listitem', 'aria-pressed': 'false' },
      h('span', { class: 't', text: on ? `Now · ${minsLeft(e, now)}` : fmtClock(s) }), h('b', { text: title }),
      on ? progressBar((now - s) / (e - s), 'live') : null);
    b.style.width = `${w}px`;
    b.addEventListener('click', () => {
      const open = b.getAttribute('aria-pressed') !== 'true';
      for (const x of scroll.children) x.setAttribute('aria-pressed', 'false');
      b.setAttribute('aria-pressed', String(open));
      desc.textContent = d ? `${fmtClock(s)}–${fmtClock(e)}  ${d}` : `${fmtClock(s)}–${fmtClock(e)}  No description.`;
      desc.hidden = !open;
    });
    scroll.append(b);
  }
  tl.replaceChildren(scroll, desc);
}

// ------------------------------------------------------------------ sports artwork
// Real crests and competition logos come from the Pi's own library (tvnext): the page asks which of
// the canonical ids it is about to show have artwork; the Pi answers from disk and queues the rest
// for a background lookup. Nothing here waits for it - cards draw at once with the generated crest
// and pick up artwork on a later paint.
const artIdx = new Map();                 // id -> {v, sizes} | null (asked; none yet)
const artAsked = new Map();               // id -> when asked
// Team names the live app sent without an id (a club it doesn't know yet): the Pi resolves them with
// this build's own dataset. name -> canonical id | null (asked; not a known team)
const nameIdx = new Map();
// Sides the dataset doesn't know at all (a fighter, an unlisted club): the Pi looks the exact name up
// in that sport (tvnext sportsart guests). "sport|label" -> guest id | null (not looked up)
const guestIdx = new Map();
const GUEST_SPORTS = new Set(['football', 'basketball', 'nfl', 'mma', 'boxing', 'rugby', 'hockey', 'handball', 'volleyball']);
async function loadArt(ids, labels = [], guests = []) {
  const now = Date.now();
  const gw = [...new Set(guests)].filter((g) => !guestIdx.has(g)).slice(0, 600);
  for (const g of gw) guestIdx.set(g, null);
  const gids = [...guestIdx.values()].filter(Boolean);
  const want = [...new Set([...ids, ...gids])].filter((id) => id && (!artAsked.has(id) || (artIdx.get(id) === null && now - artAsked.get(id) > 120000)));
  const names = [...new Set(labels)].filter((n) => n && !nameIdx.has(n)).slice(0, 600);
  if (!want.length && !names.length && !gw.length) return false;
  for (const id of want) artAsked.set(id, now);
  let found = false;
  const rounds = Math.max(Math.ceil(want.length / 200), Math.ceil(names.length / 100), Math.ceil(gw.length / 100), 1);
  for (let r = 0; r < rounds; r++) {
    const part = want.slice(r * 200, r * 200 + 200);
    const namepart = names.slice(r * 100, r * 100 + 100);
    const gpart = gw.slice(r * 100, r * 100 + 100);
    const q = new URLSearchParams({ ids: part.join(',') });
    if (namepart.length) q.set('names', namepart.join('\n'));
    if (gpart.length) q.set('guests', gpart.join('\n'));
    try {
      const res = await fetch(`${NEXT}/api/art?${q}`, { credentials: 'same-origin' });
      const d = res.ok ? await res.json() : { items: {}, names: {} };
      for (const id of part) {
        const was = artIdx.get(id);
        artIdx.set(id, d.items[id] || null);
        if (d.items[id] && !was) found = true;
      }
      for (const g of gpart) {
        const id = (d.guests || {})[g] || null;
        guestIdx.set(g, id);
        if (!id) continue;
        artAsked.set(id, now);
        artIdx.set(id, d.items[id] || null);
        if (d.items[id]) found = true;
      }
      for (const n of namepart) {
        const id = (d.names || {})[n] || null;
        nameIdx.set(n, id);
        if (!id) continue;
        found = true;                                 // a side now has its own id: crests and colours can change
        artAsked.set(id, now);
        artIdx.set(id, d.items[id] || artIdx.get(id) || null);
      }
    } catch { /* offline or no sidecar: generated art only */ }
  }
  return found;
}

// Live or replay, from the real fixture dates (the Pi's tvnext/fixtures.py): many channels re-air a
// match days later with nothing in the guide to say so. "home|away|start" -> {live} | {replay, played},
// with the meeting's competition (comp, comp_name) when ESPN lists it - shown only where the guide names none;
// asked for today's football, basketball and NFL with two known teams, answered from the Pi's cache, the rest looked up
// in the background (another paint picks them up).
const fixtureIdx = new Map();
const fixtureAsked = new Map();
const FX_SPORTS = new Set(['football', 'basketball', 'nfl']);           // what ESPN's scoreboards cover
const fxKey = (ev) => (FX_SPORTS.has(ev.sport) && (ev.teams || []).length === 2 && ev.teams.every((t) => String(t).startsWith('team:'))
  ? `${ev.teams[0]}|${ev.teams[1]}|${ev.start}` : '');
async function loadFixtures(evs) {
  const now = Date.now();
  const rank = { live: 0, soon: 1, later: 2 };
  const want = [...new Set(evs.filter((e) => e.when in rank).sort((a, b) => rank[a.when] - rank[b.when]).map(fxKey))]
    .filter((k) => k && !fixtureIdx.has(k) && now - (fixtureAsked.get(k) || 0) > 20000);
  let found = false;
  let pending = 0;
  for (let i = 0; i < want.length; i += 80) {
    const part = want.slice(i, i + 80);
    for (const k of part) fixtureAsked.set(k, now);
    try {
      const res = await fetch(`${NEXT}/api/fixtures?${new URLSearchParams({ q: part.join(',') })}`, { credentials: 'same-origin' });
      const d = res.ok ? await res.json() : { items: {}, pending: 0 };
      for (const [k, v] of Object.entries(d.items || {})) { fixtureIdx.set(k, v); found = true; }
      pending = d.pending || 0;
    } catch { return { found, pending: 0 }; }      // no sidecar: the guide's own reading stands
  }
  return { found, pending };
}
// replays found by the live scores (an airing that started long after the real kick-off): "title|start"
const scoreReplays = new Map();
function withFixture(ev) {
  const r = scoreReplays.get(`${ev.title}|${ev.start}`);
  if (r) return { ...ev, replay: true, played: r.played };
  const v = fixtureIdx.get(fxKey(ev));
  if (!v) return ev;
  const comp = !ev.comp && v.comp ? { comp: v.comp_name, comp_id: v.comp } : {};
  return v.replay ? { ...ev, ...comp, replay: true, played: v.played } : { ...ev, ...comp, replay: false, played: 0 };
}
// Live scores on the live cards (the Pi's tvnext/scores.py, from ESPN): per device, and never on replays.
const SCORES_KEY = `${LSK}scores`;
const scoresOn = () => { try { return localStorage.getItem(SCORES_KEY) !== 'hide'; } catch { return true; } };
const playedOn = (ts) => fmtDate(ts, { weekday: 'short', day: 'numeric', month: 'short' });
const replayTag = (ev) => h('span', { class: 'sp-tag replay', text: ev.played ? `Replay · played ${playedOn(ev.played)}` : 'Replay' });

// Artwork gaps: every generated crest / competition mark drawn because the Pi had no verified artwork
// is reported once per entity + place per page load; the Pi keeps one record per entity (first/last
// seen, count, places, competitions, why) - `iptv artwork missing` and Settings > Artwork read it.
const gapSent = new Set();
const gapQueue = [];
let gapTimer = 0;
function noteGap(id, name, context, competition = '', reason = 'none') {
  const key = `${id || `name:${name}`}#${context}`;
  if (gapSent.has(key) || gapSent.size > 2000) return;
  gapSent.add(key);
  gapQueue.push({ id: id || 'name:', name, context, competition, reason });
  clearTimeout(gapTimer);
  gapTimer = setTimeout(sendGaps, 4000);
}
function sendGaps() {
  const items = gapQueue.splice(0, 200);
  if (!items.length) return;
  fetch(`${NEXT}/api/art/gaps`, { method: 'POST', credentials: 'same-origin', keepalive: true,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items }) }).catch(() => {});
  if (gapQueue.length) gapTimer = setTimeout(sendGaps, 1000);
}
// asked and answered "none" - before the answer a missing crest isn't a gap yet
const artNone = (id) => !!id && artIdx.has(id) && artIdx.get(id) === null;
const artUrl = (id, size) => `${NEXT}/art/${id.startsWith('comp:') ? 'competitions' : id.startsWith('guest:') ? 'guests' : 'teams'}/${id.split(':')[1]}/${size}.webp?v=${artIdx.get(id).v}`;
const hasArt = (id) => !!(id && artIdx.get(id));

// ------------------------------------------------------------------ SPORTS: matchday
// Matches and events from the guide (tvapp/epgsearch.py Index.sports): one card per event, its
// channels best-for-this-device first. Tapping plays the first through the normal live path.
const SPORTS = [['football', 'Football'], ['all', 'All sports'], ['f1', 'F1'], ['mma', 'UFC / MMA'], ['boxing', 'Boxing'],
  ['basketball', 'Basketball'], ['nfl', 'NFL'], ['tennis', 'Tennis'], ['cricket', 'Cricket'], ['rugby', 'Rugby']];
const SPORT_NAMES = Object.fromEntries([...SPORTS, ['hockey', 'Ice hockey'], ['handball', 'Handball'],
  ['volleyball', 'Volleyball'], ['other', 'Other']]);
SPORT_NAMES.nfl = 'American football';                     // the chip says NFL; a card without a competition may be college
const sportsCache = new Map();

async function sportsData(day, force = false) {
  const hit = sportsCache.get(day);
  if (hit && !force && Date.now() - hit.at < 55000) return hit.d;
  const c = await caps.get(player.preferNative).catch(() => '');
  const tzo = tzOffset();
  const d = await api(`/sports?day=${day}&tzo=${tzo}&caps=${encodeURIComponent(c)}`, { timeout: 30000 });
  if (!d.pending) sportsCache.set(day, { at: Date.now(), d });
  return d;
}

// For You: the favourites' events today and tomorrow (Index.for_you on the Pi). The favourites
// are sent with the request, so a star tapped a moment ago counts before it has synced.
async function forYouData(force = false) {
  const favs = store.sportsFavs.ids().sort();
  const key = `foryou|${favs.join(',')}`;
  const hit = sportsCache.get(key);
  if (hit && !force && Date.now() - hit.at < 55000) return hit.d;
  if (!favs.length) return { events: [], counts: {}, none: true };
  const c = await caps.get(player.preferNative).catch(() => '');
  const tzo = tzOffset();
  const d = await api(`/sports?view=foryou&fav=${encodeURIComponent(favs.join(','))}&tzo=${tzo}&caps=${encodeURIComponent(c)}`,
    { timeout: 30000 });
  if (!d.pending) sportsCache.set(key, { at: Date.now(), d });
  return d;
}

// Every team and competition that can be a favourite (tvapp/sports.py), fetched once.
let sportsCat = null;
async function sportsCatalogue() {
  if (!sportsCat) {
    const d = await api('/sports/catalogue');
    sportsCat = { items: d.items, byId: new Map(d.items.map((i) => [i.id, i])) };
    for (const i of d.items) i.key = fold(`${i.name} ${(i.aka || []).join(' ')}`);
  }
  return sportsCat;
}

function isFavEvent(ids) {
  return (ids || []).some((i) => store.sportsFavs.has(i));
}

const ALERT_CHOICES = [['off', 'Off'], ['15', '15 minutes before'], ['30', '30 minutes before'], ['60', '60 minutes before']];

// Favourite teams and competitions: the list, a search over every known one, and match alerts.
async function openSportsFavs() {
  const box = h('div', { class: 'picker' }, h('h2', { id: 'sheet-title', text: 'Teams & competitions' }), skeletonRows(4));
  openSheet(box, 'Favourite teams and competitions');
  let cat;
  try { cat = await sportsCatalogue(); } catch (e) { box.replaceChildren(errorBox(e.message, () => openSportsFavs())); return; }
  const alerts = selectEl('Match alerts', ALERT_CHOICES, String(store.prefs.get('sportsAlerts', 'off')),
    (v) => { store.prefs.set('sportsAlerts', v); toast(v === 'off' ? 'Match alerts off' : `Alerts ${v} minutes before kick-off`, 1800); });
  const mine = h('ul', { class: 'sfav-list', role: 'list' });
  const [qField, q] = searchField('Find a team or competition', 'Find a team or competition');
  const found = h('ul', { class: 'sfav-list', role: 'list' });
  const row = (item) => {
    const on = store.sportsFavs.has(item.id);
    const star = h('button', { class: `fav-btn ${on ? 'on' : ''}`, type: 'button', 'aria-pressed': String(on),
      'aria-label': `${on ? 'Remove' : 'Add'} ${item.name}` }, icon('star'));
    star.addEventListener('click', () => { store.sportsFavs.toggle(item.id, item); draw(); });
    const kind = item.kind === 'comp' ? 'Competition' : item.national ? 'National team' : 'Team';
    return h('li', { class: 'sfav-row' }, h('span', { class: 'sfav-name' }, h('strong', { text: item.name }),
      h('span', { class: 'muted small', text: [kind, SPORT_NAMES[item.sport]].filter(Boolean).join(' · ') })), star);
  };
  function draw() {
    const list = store.sportsFavs.list().map((f) => cat.byId.get(f.id) || { id: f.id, name: f.name || f.id, kind: f.kind || 'team' });
    mine.replaceChildren(...(list.length ? list.map(row) : [h('li', { class: 'muted small', text: 'None yet: find a team or competition below, or tap the star on a match.' })]));
    const terms = fold(q.value).split(/\s+/).filter(Boolean);
    const hits = terms.length ? cat.items.filter((i) => terms.every((t) => i.key.includes(t))).slice(0, 30) : [];
    found.replaceChildren(...hits.map(row));
    if (terms.length && !hits.length) found.append(h('li', { class: 'muted small', text: 'Nothing known by that name yet.' }));
  }
  q.addEventListener('input', draw);
  box.replaceChildren(h('h2', { id: 'sheet-title', text: 'Teams & competitions' }),
    h('p', { class: 'muted small', text: 'They fill Sports › For you on all your devices, and a star marks their matches everywhere.' }),
    ...(state.status && state.status.alerts_on === false ? [] : [
      h('div', { class: 'sfav-alerts' }, h('span', { class: 'small', text: 'Telegram alert before kick-off' }), alerts),
      h('p', { class: 'muted small', text: 'One message per match, sent by the Pi. Not for replays, youth or women’s games.' })]),
    h('h3', { class: 'sub-title', text: 'Your favourites' }), mine, qField, found);
  draw();
}

async function viewSports() {
  const favBtn = h('button', { class: 'btn small', type: 'button' }, icon('star'), 'Teams');
  favBtn.addEventListener('click', () => openSportsFavs());
  const pick = { sport: store.prefs.get('sportsTab', 'football'), day: 'today', feeds: store.prefs.get('sportsFeeds', 'all') };
  if (![...SPORTS, ['foryou']].some(([k]) => k === pick.sport)) pick.sport = 'football';
  if (!['en', 'intl', 'all'].includes(pick.feeds)) pick.feeds = 'all';
  const dateLine = h('span', { class: 'sub' });
  const days = seg('Day', [['today', 'Today'], ['tomorrow', 'Tomorrow']], pick.day, async (d) => { pick.day = d; await reload(); });
  // Commentary: which broadcaster is offered first, and the order of the rest. Never hides an event.
  const feedSeg = seg('Commentary', [['en', 'English'], ['intl', 'International'], ['all', 'All']], pick.feeds, (v) => {
    pick.feeds = v;
    store.prefs.set('sportsFeeds', v);
    paint();
  });
  feedSeg.title = 'Which broadcaster each event plays first. English: UK, Irish, US, Canadian, Australian feeds and channels named English. International: foreign-language feeds. All: best quality for this device. Unknown feeds sit between.';
  const pageHead = head('Sports', dateLine, days, favBtn);
  const body = h('div', {}, skeletonRows(6));
  view.replaceChildren(pageHead, body);
  const chips = h('div', { class: 'chips', role: 'tablist', 'aria-label': 'Sport' });
  const list = h('div', { 'aria-live': 'polite' });
  let data = null;
  let mine = null;                                // For You data
  let live = null;
  const load = (force = false) => (pick.sport === 'foryou' ? forYouData(force).then((d) => { mine = d; })
    : sportsData(pick.day, force).then((d) => { data = d; }));
  try {
    [live] = await Promise.all([catalogue('live'), sportsData(pick.day).then((d) => { data = d; }),
      pick.sport === 'foryou' ? forYouData().then((d) => { mine = d; }) : null]);
    sportsCatalogue().then(() => paint()).catch(() => {});      // names for the stars and crests
  } catch (e) {
    body.replaceChildren(errorBox(e.message, () => render()));
    return;
  }
  if (state.section !== 'sports') return;
  body.replaceChildren(h('div', { class: 'sp-controls' }, chips,
    h('div', { class: 'sp-controls-row' }, h('span', { class: 'seg-label' }, h('span', { text: 'Commentary' }), feedSeg))), list);

  async function reload(force = false) {
    list.classList.add('busy');
    try { await load(force); } catch (e) { list.replaceChildren(errorBox(e.message, () => render())); return; }
    finally { list.classList.remove('busy'); }
    paint();
  }

  function visible(events) {
    const out = [];
    for (const ev of events || []) {
      if (!['all', 'foryou'].includes(pick.sport) && ev.sport !== pick.sport) continue;
      const feeds = visibleFeeds(ev.channels, live, pick.feeds);
      if (feeds.length) out.push({ ...ev, feeds });
    }
    return out;
  }

  function paintChips() {
    const n = {};
    for (const ev of data.events || []) n[ev.sport] = (n[ev.sport] || 0) + 1;
    chips.replaceChildren();
    for (const [k, label] of [['foryou', 'For you'], ...SPORTS]) {
      const c = k === 'all' ? (data.events || []).length : k === 'foryou' ? 0 : n[k] || 0;
      if (!c && k !== pick.sport && !['football', 'all', 'foryou'].includes(k)) continue;
      const b = h('button', { class: 'chip', type: 'button', role: 'tab', 'aria-selected': String(pick.sport === k) },
        k === 'foryou' ? icon('star') : '', label, h('span', { class: 'chip-n', text: c ? String(c) : '' }));
      b.addEventListener('click', async () => {
        pick.sport = k;
        store.prefs.set('sportsTab', k);
        if (k === 'foryou' || !data) await reload(); else paint();
      });
      chips.append(b);
    }
    days.hidden = pick.sport === 'foryou';         // For You covers today and tomorrow
    const day = Date.now() / 1000 + (pick.day === 'tomorrow' ? 86400 : 0);
    dateLine.textContent = pick.sport === 'foryou' ? 'Today and tomorrow' : fmtDate(day, { weekday: 'long', day: 'numeric', month: 'long' });
  }

  function paint() {
    if (!data) return;
    paintChips();
    const foryou = pick.sport === 'foryou';
    if (foryou && !mine) { reload(); return; }
    const evs = visible(foryou ? mine.events : data.events).map(withFixture);
    const secs = foryou ? [['live', 'Live now'], ['soon', 'Starting soon'], ['later', 'Later today'], ['tomorrow', 'Tomorrow']]
      : pick.day === 'today' ? [['live', 'Live now'], ['soon', 'Starting soon'], ['later', 'Later today']] : [['all', 'Tomorrow']];
    const out = [];
    for (const [when, title] of secs) {
      const items = evs.filter((e) => !e.replay && (when === 'all' || (foryou ? (when === 'tomorrow' ? e.day === 'tomorrow' : e.day === 'today' && e.when === when) : e.when === when)));
      if (!items.length) continue;
      if (when !== 'live') items.sort((a, b) => a.start - b.start || b.score - a.score);
      out.push(when === 'live' ? liveBlock(title, items) : boardBlock(title, items));
    }
    // replays apart, after everything live or still to come: the ones on now first
    const nowS = Date.now() / 1000;
    const replays = evs.filter((e) => e.replay).sort((a, b) => (b.start <= nowS) - (a.start <= nowS) || a.start - b.start);
    if (replays.length) out.push(boardBlock('Replays', replays));
    if (!out.length && foryou) {
      const has = store.sportsFavs.ids().length;
      const add = h('button', { class: 'btn primary', type: 'button', onclick: () => openSportsFavs() }, icon('star'), 'Choose teams');
      out.push(emptyBox(has ? 'Nothing from your teams in the guide today or tomorrow' : 'No favourite teams or competitions yet',
        has ? 'Matches show up here as soon as a channel’s guide lists them.'
          : 'Add teams like Arsenal or competitions like the Champions League. Their matches from every broadcaster then appear here.',
        add));
    } else if (!out.length) {
      const what = pick.sport === 'all' ? 'sport' : (SPORT_NAMES[pick.sport] || 'sport').toLowerCase();
      out.push(emptyBox(`No ${what} in the guide ${pick.day === 'today' ? 'for the rest of today' : 'for tomorrow'}`,
        'Only channels with a programme guide are listed. Live search finds everything else by name.'));
    }
    // more than one section: a row of jumps to each (with its count), so Replays at the bottom is one tap away
    const blocks = out.filter((el) => el.classList.contains('sp-block'));
    const jump = blocks.length > 1 ? h('nav', { class: 'sp-jump', 'aria-label': 'Jump to' }, ...blocks.map((b) => {
      const t = b.querySelector('.section-title').textContent;
      const btn = h('button', { class: 'chip small', type: 'button' }, t, h('span', { class: 'chip-n', text: b.querySelector('.sp-block-head .n').textContent }),
        icon('chev-down', 'ico sm'));
      btn.addEventListener('click', () => b.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }));
      return btn;
    })) : null;
    list.replaceChildren(...(jump ? [jump] : []), ...out);
    const ids = evs.flatMap((e) => [e.comp_id, ...(e.teams || [])]);
    const labels = evs.flatMap((e) => names.teams(e.title) || []);   // every side: exact per name
    // and every side with no id, by its name in its sport (the Pi skips the ones it knows)
    const guests = evs.flatMap((e) => (GUEST_SPORTS.has(e.sport) && e.kind === 'match' && (e.teams || []).length < 2
      ? (names.teams(e.title) || []).map((l) => `${e.sport}|${l}`) : []));
    loadArt(ids, labels, guests).then((found) => { if (found && state.section === 'sports') paint(); });
    shownLive = evs.filter((e) => e.when === 'live' && !e.replay);
    loadScores();
    loadFixtures(foryou ? mine.events : data.events).then(({ found, pending }) => {
      if (state.section !== 'sports') return;
      if (found) paint();
      else if (pending && !fixtureWait) fixtureWait = setTimeout(() => { fixtureWait = 0; if (state.section === 'sports') paint(); }, 15000);
    });
  }
  let fixtureWait = 0;

  // live scores: asked for the live, not-replayed matches on show; then every minute while Sports is open
  const scoreIdx = new Map();                     // "comp|a|b|start" -> {score: {team: '2'}, clock, state, detail}
  let shownLive = [];
  // a side: its team id, or the guide's own name for a club the app doesn't know (the Pi matches it by name)
  const sideToken = (t) => t.id || `name:${String(t.label).replace(/[|,]/g, ' ').trim().slice(0, 60)}`;
  const SCORE_SPORTS = new Set(['football', 'basketball', 'nfl']);
  const scKey = (ev) => {
    if (ev.when !== 'live' || ev.replay || !SCORE_SPORTS.has(ev.sport)) return '';
    const sides = teamSides(ev);
    if (!sides || sides.some((t) => !t.id && !t.label)) return '';
    return `${ev.comp_id || 'comp:none'}|${sideToken(sides[0])}|${sideToken(sides[1])}|${ev.start}`;
  };
  async function loadScores() {
    if (!scoresOn() || document.hidden) return;
    const keys = [...new Set(shownLive.map(scKey).filter(Boolean))].slice(0, 40);
    if (!keys.length) return;
    try {
      const res = await fetch(`${NEXT}/api/scores?${new URLSearchParams({ q: keys.join(',') })}`, { credentials: 'same-origin' });
      const d = res.ok ? await res.json() : { items: {} };
      let replays = false;
      for (const k of keys) {
        const v = d.items[k];
        if (v && v.replay) {                        // aired after the real game: to Replays, without its score
          const ev = shownLive.find((e) => scKey(e) === k);
          if (ev) { scoreReplays.set(`${ev.title}|${ev.start}`, { played: v.played }); replays = true; }
          scoreIdx.delete(k);
        } else if (v) scoreIdx.set(k, v); else scoreIdx.delete(k);
      }
      if (replays) { paint(); return; }
    } catch { return; }
    for (const li of list.querySelectorAll('.fixture[data-sk]')) paintScore(li, scoreIdx.get(li.dataset.sk));
  }
  const scoreTimer = setInterval(() => { if (state.section === 'sports') loadScores(); }, 60000);
  state.cleanup.push(() => clearInterval(scoreTimer));

  const blockHead = (title, n) => h('div', { class: 'sp-block-head' }, h('h2', { class: 'section-title', text: title }), h('span', { class: 'n', text: String(n) }));

  // Live now: one feature, two majors, the rest compact. Importance = the Pi's event score
  // (competition, known teams, broadcasters, LIVE tags; replays and youth games lower) plus a
  // large bonus for your teams and competitions. Replays are never featured.
  function liveBlock(title, items) {
    const weight = (ev) => ev.score + (isFavEvent([...(ev.teams || []), ev.comp_id]) ? 1000 : 0) - (ev.replay ? 500 : 0);
    const ranked = items.slice().sort((a, b) => weight(b) - weight(a) || a.start - b.start);
    // the three most important live (not replayed) events lead, the rest keep their rank
    const lead = ranked.filter((ev) => !ev.replay).slice(0, 3);
    const order = [...lead, ...ranked.filter((ev) => !lead.includes(ev))];
    const ul = h('ul', { class: 'fixtures', role: 'list' });
    const LIMIT = 27;
    const size = (ev) => (ev === lead[0] ? 'feature' : lead.includes(ev) ? 'major' : '');
    ul.append(...order.slice(0, LIMIT).map((ev) => fixtureCard(ev, size(ev))));
    const more = h('button', { class: 'btn ghost small', type: 'button', text: `Show ${items.length - LIMIT} more`, hidden: items.length <= LIMIT });
    more.addEventListener('click', () => { ul.append(...order.slice(LIMIT).map((ev) => fixtureCard(ev, ''))); more.hidden = true; });
    return h('section', { class: 'sp-block' }, blockHead(title, items.length), ul, more);
  }

  function boardBlock(title, items) {
    const ol = h('ol', { class: 'board', role: 'list' });
    const LIMIT = 30;
    ol.append(...items.slice(0, LIMIT).map(departure));
    const more = h('button', { class: 'btn ghost small', type: 'button', text: `Show ${items.length - LIMIT} more`, hidden: items.length <= LIMIT });
    more.addEventListener('click', () => { ol.append(...items.slice(LIMIT).map(departure)); more.hidden = true; });
    return h('section', { class: 'sp-block' }, blockHead(title, items.length), ol, more);
  }

  // The ☆: favourite the event's teams / competition in place (names from the catalogue)
  function favControl(ev, host) {
    const ids = [...(ev.teams || []), ev.comp_id].filter(Boolean);
    if (!ids.length) return [null, null];
    const on = isFavEvent(ids);
    const btn = h('button', { class: `sp-star ${on ? 'on' : ''}`, type: 'button', 'aria-expanded': 'false',
      'aria-label': `Favourite ${ev.title} teams or competition`, title: 'Favourite a team or competition' }, icon('star'));
    const row = h('div', { class: 'sp-fav-row', hidden: true });
    const paintRow = () => {
      row.replaceChildren(...ids.map((id) => {
        const item = (sportsCat && sportsCat.byId.get(id)) || { id, name: id.split(':')[1].replace(/-/g, ' '), kind: id.split(':')[0] };
        const sel = store.sportsFavs.has(id);
        const chip = h('button', { class: `chip sp-fav-chip ${sel ? 'on' : ''}`, type: 'button', 'aria-pressed': String(sel) }, icon('star'), item.name);
        chip.addEventListener('click', (e) => {
          e.stopPropagation();
          const now = store.sportsFavs.toggle(id, item);
          toast(now ? `${item.name} added to favourites` : `${item.name} removed`, 1600);
          paintRow();
          btn.classList.toggle('on', isFavEvent(ids));
          host.classList.toggle('is-fav', isFavEvent(ids));
        });
        return chip;
      }));
    };
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      row.hidden = !row.hidden;
      btn.setAttribute('aria-expanded', String(!row.hidden));
      if (!row.hidden) paintRow();
    });
    return [btn, row];
  }

  // Competition colours + the sport's line drawing behind the card (sportsart.js).
  function paintArt(el, ev) {
    const a = art.compArt(ev.comp_id, ev.sport);
    el.style.setProperty('--c1', a.c1);
    el.style.setProperty('--c2', a.c2);
    el.style.setProperty('--pat', a.pattern);
  }

  // The two teams as shown, each with its crest: catalogue names decide which id is which, else order.
  function teamSides(ev) {
    if (ev.kind && ev.kind !== 'match') return null;        // "F1: Sprint - GP Singapur" is one event, not two sides
    if (ev.sport === 'f1') return null;                     // nor is "Brad Pitt vs McLaren" (a feature)
    const pair = names.teams(ev.title);
    if (!pair) return null;
    const ids = (ev.teams || []).slice(0, 2);
    const known = (id) => (sportsCat && sportsCat.byId.get(id)) || null;
    const matches = (id, label) => {
      const t = known(id);
      if (!t) return false;
      const f = fold(label);
      return [t.name, ...(t.aka || [])].some((n) => { const k = fold(n); return k && (f.includes(k) || k.includes(f)); });
    };
    const sideIds = art.sides(pair, ids, pair.map((l) => nameIdx.get(l) || ''), matches);
    // national sides: the flag (by the label, or by the known team's own name for "Ισπανία"-style labels)
    const fl = flags.pairFlags(pair.map((l, i) => (flags.flagCode(l) ? l : (known(sideIds[i]) || {}).name || l)));
    return pair.map((label, i) => {
      const t = known(sideIds[i]);
      const flag = fl[i] || (t && t.national ? flags.flagCode(t.name) : '');   // a known national side on its own counts too
      const g = sideIds[i] ? '' : guestIdx.get(`${ev.sport}|${label}`) || '';       // looked up by name on the Pi
      return { label, id: sideIds[i], art: sideIds[i] || (g && hasArt(g) ? g : ''), guest: g, crest: art.crest(sideIds[i], label), flag, national: !!(t && t.national) };
    });
  }

  // The club's real crest when the library has it, else the generated disc in its colours - also if
  // the crest file fails to load. National sides: football keeps the federation's crest when there is
  // one; every other sport shows the flag (England's cricket team is not the FA).
  // gap: {label, context, comp} - where a generated crest is drawn for want of artwork (noteGap)
  function crestEl(c, id = '', big = false, sport = 'football', gap = null, flag = '') {
    const disc = () => {
      const el = h('span', { class: `crest ${c.known ? '' : 'plain'}`, 'aria-hidden': 'true', dataset: { i: c.initials } });
      el.style.setProperty('--a', c.a);
      el.style.setProperty('--b', c.b);
      return el;
    };
    if (flag && (sport !== 'football' || !hasArt(id))) {
      const im = h('img', { src: `${STATIC}/flags/${flag}.svg`, alt: '', decoding: 'async' });
      const el = h('span', { class: 'crest flag', 'aria-hidden': 'true' }, im);
      im.addEventListener('error', () => el.replaceWith(disc()), { once: true });
      return el;
    }
    // a national team's artwork is its football federation's: never on cricket, tennis…
    if (sport !== 'football' && (!hasArt(id) || ((sportsCat && sportsCat.byId.get(id)) || {}).national)) return disc();
    if (!hasArt(id)) {
      // an unlisted club the Pi looked up by name: the gap is that id's (so a crest added for it shows here)
      if (gap && !id && gap.guest && artNone(gap.guest)) noteGap(gap.guest, gap.label, gap.context, gap.comp);
      else if (gap && (id ? artNone(id) : nameIdx.has(gap.label) && !nameIdx.get(gap.label))) noteGap(id, gap.label, gap.context, gap.comp);
      return disc();
    }
    const im = h('img', { src: artUrl(id, big ? 256 : 128), alt: '', decoding: 'async' });
    const photo = id.startsWith('guest:') && (sport === 'mma' || sport === 'boxing');   // a fighter: head and shoulders
    const el = h('span', { class: `crest real ${photo ? 'photo' : ''}`, 'aria-hidden': 'true' }, im);
    im.addEventListener('error', () => {
      el.replaceWith(disc());
      if (gap) noteGap(id, gap.label, gap.context, gap.comp, 'load-failed');
    }, { once: true });
    return el;
  }

  // a team or event name in capitals, the script's own way (names.caps); the original stays as the title
  function capsSpan(text) {
    const c = names.caps(text);
    return h('span', { text: c.text, lang: c.lang || null, title: text });
  }

  // the competition's own mark beside its name, when the library has a verified one
  function compLabel(ev, meta, context = 'sports:card') {
    const el = h('span', { class: `fx-comp ${hasArt(ev.comp_id) ? 'has-logo' : ''}` });
    if (hasArt(ev.comp_id)) {
      const im = h('img', { class: 'comp-logo', src: artUrl(ev.comp_id, 64), alt: '', decoding: 'async' });
      im.addEventListener('error', () => { im.remove(); el.classList.remove('has-logo'); noteGap(ev.comp_id, ev.comp, context, '', 'load-failed'); }, { once: true });
      el.append(im);
    } else if (artNone(ev.comp_id)) noteGap(ev.comp_id, ev.comp, context);
    el.append(h('span', { text: meta }));
    return el;
  }

  // English / International chosen, but no broadcaster of that kind: say so (the best feed still plays)
  function feedNote(ev, short = false) {
    const want = pick.feeds === 'en' ? 'en' : pick.feeds === 'intl' ? 'xx' : '';
    if (!want || ev.feeds.some((f) => f.lang === want)) return null;
    const what = want === 'en' ? 'English' : 'international';
    return h('span', { class: 'feed-note', text: short ? `No ${what} feed listed` : `No ${what} feed listed — showing best available` });
  }

  function feedList(ev, host, open = false) {
    const others = ev.feeds.length - 1 + (ev.more || 0);
    const feeds = h('div', { class: 'fx-feeds', hidden: !open });
    if (open) feeds.append(...ev.feeds.slice(1).map(feedButton));
    if (others <= 0) return [null, null];
    const tog = h('button', { class: 'fx-more', type: 'button', 'aria-expanded': String(open) },
      h('span', { text: open ? 'Hide broadcasters' : `${others} more broadcaster${others === 1 ? '' : 's'}` }), icon('chev-down'));
    tog.addEventListener('click', (e) => {
      e.stopPropagation();
      const now = feeds.hidden;
      if (now && !feeds.childElementCount) feeds.append(...ev.feeds.slice(1).map(feedButton));
      feeds.hidden = !now;
      tog.setAttribute('aria-expanded', String(now));
      tog.firstChild.textContent = now ? 'Hide broadcasters' : `${others} more broadcaster${others === 1 ? '' : 's'}`;
      host.classList.toggle('open', now);
    });
    return [tog, feeds];
  }

  function fixtureCard(ev, size) {
    const now = Date.now() / 1000;
    const best = ev.feeds[0];
    const ids = [...(ev.teams || []), ev.comp_id].filter(Boolean);
    const li = h('li', { class: `fixture ${size} ${isFavEvent(ids) ? 'is-fav' : ''}` });
    paintArt(li, ev);
    const [star, favRow] = favControl(ev, li);
    const meta = [ev.comp, ['all', 'foryou'].includes(pick.sport) || !ev.comp ? SPORT_NAMES[ev.sport] : ''].filter(Boolean).join(' · ');
    const where = `sports:${size || 'compact'}`;
    const sk = scoresOn() ? scKey(ev) : '';
    const top = h('div', { class: 'fx-top' }, h('span', { class: `live-pill ${ev.replay ? 'replay' : ''}`, text: ev.replay ? 'Replay' : 'Live' }),
      sk ? h('span', { class: 'fx-clock', hidden: true }) : null,
      compLabel(ev, meta || SPORT_NAMES[ev.sport] || 'Sport', where), ev.youth ? h('span', { class: 'sp-tag', text: 'Youth' }) : null, star);
    const sides = teamSides(ev);
    const name = (t) => { const s = capsSpan(t.label); s.classList.add('fx-name'); return s; };
    const title = sides ? h('div', { class: 'fx-teams' }, ...sides.map((t) => h('div', { class: 'fx-team' }, crestEl(t.crest, t.art, size === 'feature', ev.sport, { label: t.label, context: where, comp: ev.comp, guest: t.guest }, t.flag), name(t),
      sk ? h('span', { class: 'fx-score', dataset: { team: sideToken(t) }, 'aria-hidden': 'true' }) : null)))
      : h('div', { class: 'fx-title' }, capsSpan(ev.title));
    const mainBtn = h('button', { class: 'fx-main', type: 'button', 'aria-label': `Play ${ev.title} on ${best.ch.name}` }, title);
    mainBtn.addEventListener('click', () => playChannel(best.ch));
    const bestBtn = h('button', { class: 'fx-best', type: 'button', 'aria-label': `Play on ${best.ch.name}` },
      h('span', { class: 'play' }, icon('play')), thumb(best.ch.img, best.ch.name, 'logo sm'),
      h('span', { class: 'nm', text: plain(best.ch.name) }),
      best.region ? h('span', { class: `reg ${best.lang === 'en' ? 'en' : ''}`, text: best.region }) : null, qualityBadge(best));
    bestBtn.addEventListener('click', () => playChannel(best.ch));
    const time = h('div', { class: 'fx-time' }, `${fmtClock(ev.start)}–${fmtClock(ev.stop)}`,
      progressBar((now - ev.start) / (ev.stop - ev.start), 'live'), h('span', { class: 'left', text: minsLeft(ev.stop, now) }));
    // feature / major: the next two broadcasters are always in view; compact: on hover (desktop)
    const peek = ev.feeds.length > 1 ? h('div', { class: 'fx-peek' }, ...ev.feeds.slice(1, size === 'feature' ? 4 : 3).map(feedButton)) : null;
    const [tog, feeds] = feedList(ev, li);
    // the feature carries the competition's mark large and faint, in the artwork layer
    if (size === 'feature' && hasArt(ev.comp_id)) li.append(h('img', { class: 'fx-mark', src: artUrl(ev.comp_id, 256), alt: '', decoding: 'async', 'aria-hidden': 'true' }));
    li.append(top, favRow || '', mainBtn, time, h('div', { class: 'fx-bottom' }, bestBtn, feedNote(ev)));
    if (peek) li.append(peek);
    if (tog) li.append(tog, feeds);
    if (sk) { li.dataset.sk = sk; paintScore(li, scoreIdx.get(sk)); }
    return li;
  }

  // the score beside each side and the minute beside LIVE; nothing at all until ESPN has the match under way
  function paintScore(li, d) {
    const on = d && (d.state === 'in' || d.state === 'post') && Object.values(d.score || {}).some((v) => v !== '');
    for (const s of li.querySelectorAll('.fx-score')) s.textContent = on ? (d.score[s.dataset.team] ?? '') : '';
    const c = li.querySelector('.fx-clock');
    const when = !on ? '' : d.state === 'post' ? 'FT' : /half/i.test(d.detail || '') ? 'HT' : String(d.clock || '').replace(/'/g, '′');
    if (c) { c.textContent = when; c.hidden = !when; }
    li.classList.toggle('has-score', !!on);
    const main = li.querySelector('.fx-main');
    if (main && on) {
      const sides = [...li.querySelectorAll('.fx-team')].map((r) => `${r.querySelector('.fx-name').title} ${r.querySelector('.fx-score').textContent}`);
      main.setAttribute('aria-label', `${sides.join(', ')}${when ? `, ${when === 'HT' ? 'half time' : when === 'FT' ? 'full time' : when}` : ''}. ${main.getAttribute('aria-label').split('. ').pop()}`);
    }
  }

  function departure(ev) {
    const now = Date.now() / 1000;
    const best = ev.feeds[0];
    const ids = [...(ev.teams || []), ev.comp_id].filter(Boolean);
    const li = h('li', { class: `dep ${isFavEvent(ids) ? 'is-fav' : ''}` });
    li.style.setProperty('--c2', art.compArt(ev.comp_id, ev.sport).c2);
    const soon = ev.start - now <= 3600 && ev.start > now;
    const onNow = ev.start <= now && now < ev.stop;
    const time = h('div', { class: 'dep-time' }, h('b', { text: onNow ? 'Now' : fmtClock(ev.start) }),
      onNow ? h('span', { class: 'when', text: minsLeft(ev.stop, now) }) : soon ? h('span', { class: 'when soon', text: whenText(ev.start, now) }) : null);
    const meta = [ev.comp, ['all', 'foryou'].includes(pick.sport) || !ev.comp ? SPORT_NAMES[ev.sport] : ''].filter(Boolean).join(' · ');
    const sides = teamSides(ev);
    const title = h('span', { class: `dep-title ${isFavEvent(ids) ? 'is-fav' : ''}` });
    const gap = (t) => ({ label: t.label, context: 'sports:board', comp: ev.comp, guest: t.guest });
    if (sides) title.append(crestEl(sides[0].crest, sides[0].art, false, ev.sport, gap(sides[0]), sides[0].flag), capsSpan(sides[0].label), h('span', { class: 'vs', text: 'v' }),
      crestEl(sides[1].crest, sides[1].art, false, ev.sport, gap(sides[1]), sides[1].flag), capsSpan(sides[1].label));
    else title.append(capsSpan(ev.title));
    const mainBtn = h('button', { class: 'dep-main', type: 'button', 'aria-label': `${ev.title}, ${fmtClock(ev.start)}, on ${best.ch.name}` },
      title, h('span', { class: 'dep-meta' }, hasArt(ev.comp_id) ? h('img', { class: 'comp-logo', src: artUrl(ev.comp_id, 64), alt: '', decoding: 'async' })
        : (artNone(ev.comp_id) && noteGap(ev.comp_id, ev.comp, 'sports:board'), null),
        h('span', { text: meta }), ev.replay ? replayTag(ev) : null,
        ev.youth ? h('span', { class: 'sp-tag', text: 'Youth' }) : null, feedNote(ev, true)));
    mainBtn.addEventListener('click', () => playChannel(best.ch));
    const [star, favRow] = favControl(ev, li);
    // the broadcasters' logos are the toggle for the full list (preferred commentary first)
    const n = ev.feeds.length + (ev.more || 0);
    const feeds = h('div', { class: 'prog-chs dep-feeds', hidden: true });
    const more = h('button', { class: 'dep-more', type: 'button', 'aria-expanded': 'false', disabled: n < 2,
      'aria-label': n > 1 ? `${n} broadcasters` : plain(best.ch.name), title: n > 1 ? `${n} broadcasters` : plain(best.ch.name) },
      h('span', { class: 'dep-logos' }, ...ev.feeds.slice(0, 3).map((f) => thumb(f.ch.img, f.ch.name, 'logo sm'))),
      h('span', { class: 'dep-n', text: n > 1 ? `${n}` : '' }));
    more.addEventListener('click', () => {
      const open = feeds.hidden;
      if (open && !feeds.childElementCount) feeds.append(...ev.feeds.map(feedButton));
      feeds.hidden = !open;
      more.setAttribute('aria-expanded', String(open));
    });
    const playBtn = h('button', { class: 'round', type: 'button', 'aria-label': `Play on ${best.ch.name}`, title: `${plain(best.ch.name)}${best.region ? ` · ${best.region}` : ''}` }, icon('play', 'ico sm'));
    playBtn.addEventListener('click', () => playChannel(best.ch));
    li.append(time, mainBtn, h('div', { class: 'dep-end' }, more, star, playBtn));
    if (favRow) li.append(h('div', { class: 'dep-feeds' }, favRow));
    li.append(feeds);
    return li;
  }

  paint();
  // another device changed favourites, hidden channels or the commentary choice: show it
  state.redraw = (changed) => {
    if (changed.has('pref')) {
      const f = store.prefs.get('sportsFeeds', 'all');
      if (f !== pick.feeds) { pick.feeds = f; for (const b of feedSeg.children) b.setAttribute('aria-selected', String(b.dataset.v === f)); paint(); }
    }
    if (changed.has('sfav') && pick.sport === 'foryou') reload();
    else if (changed.has('hide') || changed.has('sfav')) paint();
  };
  const timer = setInterval(() => { reload(true).catch(() => {}); }, 60000);
  state.cleanup.push(() => clearInterval(timer), () => { state.redraw = null; });
}

// ------------------------------------------------------------------ category picker
// One sheet to choose what a view shows and to hide categories everywhere (synced like
// favourites). Searchable and filterable by region prefix ("UK|", "US|"), because providers have
// hundreds of categories. For Live it also lists hidden channels so they can be shown again.
//   kind: 'live' | 'movie' | 'series'; extra: rows above the categories, e.g. [['', 'All categories']]
function openCategoryPicker({ title, kind, list, current, extra, onPick, onHide }) {
  const cats = usedCats(list).map(([id, name, n]) => {
    const c = names.category(name);
    return { id, name, n, key: fold(name), region: c.region, title: c.title, tags: c.tags };
  });
  const [qField, q] = searchField(`Search ${cats.length.toLocaleString()} categories`, 'Search categories');
  let mode = 'all';
  let region = '';
  const modeSeg = seg('Which categories', [['all', 'All'], ['shown', 'Shown'], ['hidden', 'Hidden']], mode, (m) => { mode = m; draw(); });
  const regionCounts = new Map();
  for (const c of cats) if (c.region) regionCounts.set(c.region, (regionCounts.get(c.region) || 0) + 1);
  const regions = [...regionCounts.entries()].filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]);
  const regionBox = h('div', { class: 'picker-regions', role: 'tablist', 'aria-label': 'Region' });
  if (regions.length > 1) {
    for (const [r, label] of [['', 'Everywhere'], ...regions.map(([k]) => [k, k])]) {
      const b = h('button', { class: 'chip', type: 'button', role: 'tab', text: label, 'aria-selected': String(r === region) });
      b.addEventListener('click', () => {
        region = r;
        for (const x of regionBox.children) x.setAttribute('aria-selected', String(x === b));
        draw();
      });
      regionBox.append(b);
    }
  }
  const bulk = h('div', { class: 'picker-bulk' });
  const ul = h('ul', { class: 'picker-list', role: 'list' });
  const chBox = kind === 'live' ? h('section', { class: 'picker-channels' }) : null;
  const terms = () => fold(q.value).split(/\s+/).filter(Boolean);

  const pick = (id) => { closeSheet(false); onPick(id); };
  const hide = (cs, on) => {
    const n = store.hidden.setCats(kind, cs.map((c) => [c.id, c.name]), on);
    if (cs.length > 1) toast(`${on ? 'Hidden' : 'Showing'}: ${n} categor${n === 1 ? 'y' : 'ies'}`);
    draw();
    onHide();
  };

  function row(c, off) {
    const li = h('li', { class: `pick-row${off ? ' is-hidden' : ''}${c.id === current ? ' is-current' : ''}` });
    const name = h('button', { class: 'pick-name', type: 'button', onclick: () => pick(c.id) },
      c.region && !region ? h('span', { class: 'pfx', text: c.region }) : null,
      h('span', { class: 'pick-text', text: c.title }), ...c.tags.slice(0, 2).map((t) => h('span', { class: 'tag', text: t })),
      h('span', { class: 'pick-n', text: c.n.toLocaleString() }));
    const eye = h('button', { class: 'fav-btn eye-btn', type: 'button', 'aria-pressed': String(off),
      'aria-label': off ? `Show ${c.name}` : `Hide ${c.name}`, onclick: () => hide([c], !off) }, icon(off ? 'eye-off' : 'eye'));
    li.append(name, eye);
    return li;
  }

  function drawChannels() {
    const tt = terms();
    const all = store.hidden.channelList();
    const shownCh = all.filter((c) => tt.every((term) => fold(String(c.name || '')).includes(term)));
    if (!all.length) {
      chBox.replaceChildren(h('h3', { class: 'sub-title', text: 'Hidden channels' }),
        h('p', { class: 'muted small', text: 'None. Use the eye button on Live to hide single channels.' }));
      return;
    }
    chBox.replaceChildren(h('h3', { class: 'sub-title', text: `Hidden channels (${all.length})` }),
      h('ul', { class: 'picker-list', role: 'list' }, shownCh.map((c) => h('li', { class: 'pick-row is-hidden' },
        h('span', { class: 'pick-name' }, h('span', { class: 'pick-text', text: plain(c.name || c.id) }),
          c.num ? h('span', { class: 'pick-n', text: String(c.num) }) : null),
        h('button', { class: 'btn small', type: 'button', text: 'Show', onclick: () => {
          store.hidden.setChannel(c.id, c, false);
          drawChannels();
          onHide();
        } })))));
  }

  function draw() {
    const off = store.hidden.cats(kind);
    const tt = terms();
    const matches = cats.filter((c) => (!region || c.region === region) && tt.every((term) => c.key.includes(term))
      && (mode === 'all' || (mode === 'hidden') === off.has(c.id)));
    const rows = [];
    if (!tt.length && mode === 'all' && !region) {
      for (const [id, label] of extra) {
        rows.push(h('li', { class: `pick-row${id === current ? ' is-current' : ''}` },
          h('button', { class: 'pick-name', type: 'button', onclick: () => pick(id) }, h('span', { class: 'pick-text', text: label }))));
      }
    }
    for (const c of matches) rows.push(row(c, off.has(c.id)));
    if (!matches.length) rows.push(h('li', { class: 'muted small picker-empty', text: mode === 'hidden' && !tt.length ? 'No hidden categories.' : 'No categories match.' }));
    ul.replaceChildren(...rows);
    const narrowed = tt.length || region;
    const toHide = matches.filter((c) => !off.has(c.id));
    const toShow = matches.filter((c) => off.has(c.id));
    bulk.replaceChildren(...[
      narrowed && toHide.length > 1 ? h('button', { class: 'btn small', type: 'button', onclick: () => hide(toHide, true) }, icon('eye-off'), `Hide all ${toHide.length}`) : null,
      narrowed && toShow.length > 1 ? h('button', { class: 'btn small', type: 'button', onclick: () => hide(toShow, false) }, icon('eye'), `Show all ${toShow.length}`) : null,
    ].filter(Boolean));
    if (chBox) drawChannels();
  }

  let timer = 0;
  q.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(draw, 80); });
  openSheet(h('div', { class: 'picker' },
    h('h2', { id: 'sheet-title', class: 'picker-title', text: title }),
    h('p', { class: 'muted small', text: 'Tap a category to show it. The eye hides it from “All” and from search, on all your devices.' }),
    qField, h('div', { class: 'rail-row' }, modeSeg), regionBox, bulk, ul, chBox), title);
  draw();
  if (!TOUCH) setTimeout(() => q.focus({ preventScroll: true }), 60);   // no keyboard pop-up on phones
}

// ------------------------------------------------------------------ FILMS / SERIES
// Progress bar / watched tick on a movie poster (series cards carry neither).
function setPosterBadges(poster, id) {
  for (const el of poster.querySelectorAll(':scope > .pbar, :scope > .watched')) el.remove();
  const frac = store.progress.fraction(id);
  if (frac > 0.01 && frac < 0.999) poster.append(progressBar(frac, 'on-poster'));
  if ((store.progress.get(id) || {}).done) poster.append(h('span', { class: 'watched', 'aria-label': 'Watched' }, icon('check')));
}

// ---- catalogue language (lang.js): one synced preference for Films, Series and Search
// The viewer's language (Settings › Languages, synced): English unless they chose one the catalogue carries.
const langWant = () => { const v = store.prefs.get('catLangCode', 'en'); return /^[a-z]{2,3}$/.test(v) ? v : 'en'; };
const langPrefs = () => { const n = lang.langName(langWant()); return [['all', 'All'], ['first', `${n} first`], ['only', `${n} only`]]; };
const langPref = () => { const v = store.prefs.get('catLang', 'all'); return ['all', 'first', 'only'].includes(v) ? v : 'all'; };
function vinfo(it) {                       // cached on the item: version tier, title key, display bits
  const want = langWant();
  if (!it.vi) {
    const f = names.film(it.name);
    const year = it.year || f.year;
    it.vi = { tier: lang.versionTier(it.name, want), want, key: lang.titleKey(f.title, year), clean: f.title, prefix: f.prefix, code: lang.versionCode(f.prefix), uhd: f.uhd };
  } else if (it.vi.want !== want) {
    it.vi.tier = lang.versionTier(it.name, want);
    it.vi.want = want;
  }
  return it.vi;
}
// The list in the viewer's sort order with the language preference applied, computed once per
// (sort, preference) like sortedItems() itself.
function langItems(list, sort, pref) {
  if (pref === 'all') return sortedItems(list, sort);
  const k = `${sort}|${pref}|${langWant()}`;
  if (!list.sorted[k]) list.sorted[k] = lang.rankByLanguage(lang.applyLangPref(sortedItems(list, sort), pref, vinfo), vinfo);
  return list.sorted[k];
}
const langHelp = () => {
  const n = lang.langName(langWant());
  return 'Language is read from the provider’s own labels (EN, DE, “dubbed”…), so it is a good guide, not a guarantee. '
    + `${n} first lists ${n} titles first, then unlabelled ones, then other languages, each in the order you picked (in search, the best match still comes first). `
    + (langWant() === 'en' ? 'English only hides versions labelled as another language. '
      : `${n} only hides versions dubbed into another language, and English or subtitled versions of a title that also exists in ${n}. `)
    + 'Unlabelled titles always stay, so a few foreign ones can remain. Choose your language in Settings › Languages.';
};
// the segmented control + a small "i" that says what the choice can and can't promise
function langSeg(onchange) {
  const s = seg('Language', langPrefs(), langPref(), (v) => { store.prefs.set('catLang', v); onchange(v); });
  s.title = langHelp();
  const help = h('p', { class: 'lang-help', hidden: true, text: langHelp() });
  const info = h('button', { class: 'info-btn', type: 'button', 'aria-expanded': 'false', 'aria-label': 'About the language choice' }, icon('info'));
  info.addEventListener('click', () => { help.hidden = !help.hidden; info.setAttribute('aria-expanded', String(!help.hidden)); });
  const box = h('span', { class: 'lang-ctl' }, s, info);
  box.help = help;
  box.seg = s;
  return box;
}

// Names, years and ratings come from the provider; titles keep their language label as a chip
// on the poster (EN, FR, 4K…), so versions of one film are easy to tell apart.
function cardFor(kind, it) {
  const v = vinfo(it);
  const a = h('a', { class: 'card', href: `#/${kind}/${it.id}`, 'aria-label': it.name, dataset: { id: it.id, kind } });
  const poster = thumb(it.img, v.clean, 'poster');
  if (v.code) poster.append(h('span', { class: `lang-chip ${v.tier === 0 ? 'en' : ''} ${v.uhd ? 'hot' : ''}`, text: v.code, title: v.prefix }));
  if (kind === 'movies') setPosterBadges(poster, it.id);
  // favourite straight from a grid or search: the star in the poster's corner (the tile itself opens the title)
  const star = favButton(it.id, { name: it.name, img: it.img, kind: kind === 'movies' ? 'movie' : 'series' });
  star.classList.add('card-fav');
  star.setAttribute('aria-label', `Favourite ${v.clean}`);
  star.addEventListener('click', (e) => e.preventDefault());
  poster.append(star);
  const year = it.year || names.film(it.name).year;
  a.append(poster, h('span', { class: 'card-title', text: v.clean }),
    h('span', { class: 'card-sub' }, year ? h('span', { text: String(year) }) : null,
      it.rating ? h('span', { class: 'rate', text: `★ ${Number(it.rating).toFixed(1)}` }) : null));
  if (!TOUCH) a.addEventListener('mouseenter', () => { if (it.img && $('sheet').hidden && player.mode !== 'vod' && window.scrollY > 300) { state.pageArt = imgv(it.img, 'poster-s'); updateAmbient(); } });
  return a;
}

async function viewGrid(kind) {
  const title = kind === 'movies' ? 'Films' : 'Series';
  const sub = h('span', { class: 'sub' });
  const heroBox = h('div');
  const body = h('div', {}, skeletonGrid(18));
  view.replaceChildren(heroBox, head(title, sub), body);
  heroFor(kind, null, heroBox);                       // a saved set draws now; otherwise a calm placeholder
  let list;
  try { list = await catalogue(kind); } catch (e) { body.replaceChildren(errorBox(e.message, () => render())); return; }
  if (state.section !== kind) return;
  if (!list.items.length) { body.replaceChildren(emptyBox(`No ${title.toLowerCase()}`, 'The provider has none, or the catalogue is still loading.', providerHint())); return; }
  const pk = `${kind}.`;
  const hideKind = STORE_KIND[kind];
  let cat = store.prefs.get(pk + 'cat', '');
  let sort = store.prefs.get(pk + 'sort', kind === 'movies' ? 'added' : 'name');
  if (cat && cat !== '__fav' && !list.counts.has(cat)) cat = '';
  const extra = [['', 'All categories'], ['__fav', '★ Favourites']];
  const sorts = kind === 'movies' ? [['added', 'New'], ['name', 'A–Z'], ['year', 'Year'], ['rating', 'Rating']] : [['name', 'A–Z'], ['year', 'Year'], ['rating', 'Rating']];
  const grid = h('div', { class: 'grid' });
  const catLabel = h('span');
  const catBtn = h('button', { class: 'select cat-btn', type: 'button', 'aria-haspopup': 'dialog' }, catLabel);
  catBtn.addEventListener('click', () => openCategoryPicker({
    title: `${title} categories`, kind: hideKind, list, current: cat, extra,
    onPick: (id) => { cat = id; store.prefs.set(pk + 'cat', id); draw(); }, onHide: () => draw(),
  }));
  const sortSeg = seg('Sort', sorts, sort, (v) => { sort = v; store.prefs.set(pk + 'sort', v); draw(); });
  const lSeg = langSeg(() => { draw(); heroBox.dataset.shown = ''; heroBox.replaceChildren(); heroFor(kind, list, heroBox); });
  const [qField, q] = searchField(`Filter ${list.items.length.toLocaleString()} ${title.toLowerCase()}`, `Filter ${title.toLowerCase()}`);
  q.value = state.gridQuery[kind] || '';
  let qTimer = 0;
  q.addEventListener('input', () => { clearTimeout(qTimer); qTimer = setTimeout(() => { state.gridQuery[kind] = q.value; draw(); }, 150); });
  body.replaceChildren(h('div', { class: 'grid-tools' }, qField, catBtn, sortSeg, lSeg, lSeg.help), grid);
  let stop = null;
  function draw() {
    const hc = store.hidden.cats(hideKind);
    const name = cat ? (extra.find(([k]) => k === cat) || [])[1] || list.cats.get(cat) || 'Category' : 'All categories';
    catLabel.textContent = `${cat && cat !== '__fav' ? [names.category(name).region, names.category(name).title].filter(Boolean).join(' · ') : name}${hc.size ? `  ·  ${hc.size} hidden` : ''}`;
    let items = langItems(list, sort, langPref());          // sorted once per session; filtering keeps the order
    if (cat === '__fav') { const f = store.favs.all(); items = items.filter((i) => f[i.id]); } else if (cat) items = items.filter((i) => i.cat === cat);
    else if (hc.size) items = items.filter((i) => !hc.has(i.cat));
    const terms = fold(q.value).split(/\s+/).filter(Boolean);
    if (terms.length) items = items.filter((i) => terms.every((term) => i.key.includes(term)));
    sub.replaceChildren(h('span', { class: 'num', text: items.length.toLocaleString() }), ` title${items.length === 1 ? '' : 's'}`);
    if (stop) stop();
    if (!items.length) {
      grid.replaceChildren(terms.length ? emptyBox('No matches', `Nothing here matches “${q.value.trim()}”.`)
        : emptyBox(cat === '__fav' ? 'No favourites yet' : 'Nothing here', cat === '__fav' ? 'Open a title and tap the star.' : ''));
      return;
    }
    stop = chunked(grid, items, (it) => cardFor(kind, it), { chunk: 60 });
  }
  draw();
  heroFor(kind, list, heroBox);
  state.cleanup.push(() => clearTimeout(qTimer));
  state.redraw = (changed) => {
    if (changed.has('pref') && lSeg.seg.firstChild.nextSibling.textContent !== langPrefs()[1][1]) { render(true); return; }  // another language chosen
    if (changed.has('pref') && lSeg.seg.querySelector('[aria-selected="true"]').dataset.v !== langPref()) {
      for (const b of lSeg.seg.children) b.setAttribute('aria-selected', String(b.dataset.v === langPref()));
      draw();
    }
    if (changed.has('hide') || (cat === '__fav' && changed.has('fav'))) draw();
  };
  state.cleanup.push(() => stop && stop(), () => { state.redraw = null; });
}

// ---- the hero: hero.js picks; this resolves each slot to a title with a real backdrop. The resolved
// set is kept per 6-hour window, so after the first visit in a window the hero draws at once -
// before the 180k-title catalogue has even downloaded.
const HERO_KEY = `${LSK}hero.`;
const HERO_V = 3;                                // bump when the choice rules change: older picks are redone
const heroLS = {
  get(kind) { try { return JSON.parse(localStorage.getItem(HERO_KEY + kind)) || {}; } catch { return {}; } },
  set(kind, v) { try { localStorage.setItem(HERO_KEY + kind, JSON.stringify(v)); } catch { /* private mode: just no memory */ } },
};
const HERO_FIELDS = ['name', 'year', 'dur', 'rating', 'genre', 'plot', 'backdrop', 'img'];
const heroWindow = () => hero.windowOf(Date.now(), -tzOffset());

function savedHero(kind) {
  const s = heroLS.get(kind);
  return s.v === HERO_V && s.w === heroWindow() && s.pref === `${langPref()}|${langWant()}` && Array.isArray(s.picks) && s.picks.length ? s.picks : null;
}

async function resolveHero(kind, list) {
  const pref = langPref();
  const w = heroWindow();
  const saved = heroLS.get(kind);
  const progress = kind === 'movies'
    ? store.progress.inProgress().filter((e) => e.kind === 'movie').map((e) => e.id)
    : Object.values(store.progress.lastBySeries()).sort((a, b) => b.at - a.at).map((e) => e.series);
  const slots = hero.candidates({ kind, window: w, items: list.items, byId: list.byId, sortedBy: (s) => sortedItems(list, s),
    info: (it) => { const v = vinfo(it); return { clean: v.clean, prefix: v.prefix, tier: v.tier }; },
    progress, favs: store.favs.list(kind === 'movies' ? 'movie' : 'series').map((f) => f.id),
    recent: hero.recentIds(saved.history || [], w), langPref: pref });
  const fetchOne = (id) => (kind === 'movies' ? api(`/movie/${id}`) : getSeries(id)).catch(() => null);
  // each slot in parallel; inside a slot, fallbacks one by one until one has a backdrop (max 3 tries)
  const resolved = await Promise.all(slots.map(async ({ slot, ids }) => {
    for (const id of ids.slice(0, 3)) {
      const d = await fetchOne(id);
      if (d && d.backdrop && (d.plot || '').length > 20) {
        const keep = {};
        for (const k of HERO_FIELDS) if (d[k] != null) keep[k] = typeof d[k] === 'string' ? d[k].slice(0, 400) : d[k];
        return { id, why: slot, d: keep };
      }
    }
    return null;
  }));
  const picks = resolved.filter(Boolean);
  heroLS.set(kind, { v: HERO_V, w, pref: `${pref}|${langWant()}`, picks, history: hero.remember(saved.history || [], w, picks.map((p) => p.id)) });
  return picks;
}

function heroSkeleton() {
  return h('section', { class: 'hero is-loading', 'aria-hidden': 'true' }, h('div', { class: 'hero-art' }),
    h('div', { class: 'hero-body' }, h('span', { class: 'sk-line w20' }), h('span', { class: 'sk-line big w60' }), h('span', { class: 'sk-line w45' }),
      h('span', { class: 'sk-line w35' })));
}

const WHY = { new: 'Just added', new2: 'Just added', top: 'Highly rated', continue: 'Continue watching', rediscover: 'Rediscover', fav: 'From your favourites' };
// list: the catalogue, or null before it has loaded (then only a saved set can be shown)
async function heroFor(kind, list, box) {
  let picks = savedHero(kind);
  if (!picks && !list) { box.replaceChildren(heroSkeleton()); return false; }
  if (box.dataset.shown === 'saved' && picks && list) return true;     // already drawn from the saved set
  if (!picks) {
    if (!box.firstChild) box.replaceChildren(heroSkeleton());
    try { picks = await resolveHero(kind, list); } catch { picks = []; }
  }
  if (!box.isConnected) return false;
  if (!picks.length) { box.replaceChildren(); return false; }
  box.dataset.shown = list ? 'resolved' : 'saved';
  picks = picks.slice();
  const artBox = h('div', { class: 'hero-art' });
  const bodyBox = h('div', { class: 'hero-body', 'aria-live': 'polite' });
  const dots = h('div', { class: 'hero-dots', role: 'tablist', 'aria-label': 'Featured titles' });
  const prev = h('button', { class: 'hero-step', type: 'button', 'aria-label': 'Previous featured title' }, icon('back'));
  const next = h('button', { class: 'hero-step', type: 'button', 'aria-label': 'Next featured title' }, icon('chev'));
  const nav = h('div', { class: 'hero-nav' }, prev, dots, next);
  const heroEl = h('section', { class: 'hero', 'aria-roledescription': 'carousel', 'aria-label': 'Featured', tabindex: '-1' }, artBox, bodyBox, nav);
  const DWELL = 10000;
  heroEl.style.setProperty('--dwell', `${DWELL / 1000}s`);
  let i = -1;
  let timer = 0;
  let hover = false;
  heroEl.addEventListener('mouseenter', () => { hover = true; heroEl.classList.add('paused'); });
  heroEl.addEventListener('mouseleave', () => { hover = false; heroEl.classList.remove('paused'); });
  heroEl.addEventListener('focusin', () => heroEl.classList.add('paused'));
  heroEl.addEventListener('focusout', () => { if (!hover) heroEl.classList.remove('paused'); });
  heroEl.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') { step(e.key === 'ArrowRight' ? 1 : -1); e.preventDefault(); e.stopPropagation(); }
  });
  const step = (d) => { show((i + d + picks.length) % picks.length); restart(); };
  prev.addEventListener('click', () => step(-1));
  next.addEventListener('click', () => step(1));
  const paintDots = () => {
    dots.replaceChildren(...picks.map((p, k) => {
      const b = h('button', { type: 'button', role: 'tab', 'aria-selected': String(k === i), 'aria-current': String(k === i),
        'aria-label': `${WHY[p.why] || 'Featured'}: ${names.film(p.d.name || '').title}` });
      b.addEventListener('click', () => { show(k); restart(); });
      return b;
    }));
    nav.hidden = picks.length < 2;
  };
  const restart = () => {
    clearInterval(timer);
    if (picks.length > 1) {
      timer = setInterval(() => {
        if (!heroEl.isConnected) { clearInterval(timer); return; }
        if (!hover && !heroEl.classList.contains('paused') && document.visibilityState === 'visible' && window.scrollY < 300 && $('sheet').hidden) step(1);
      }, DWELL);
    }
  };
  const warm = (p) => { const pre = new Image(); pre.decoding = 'async'; setImg(pre, p.d.backdrop, 'hero', '100vw'); };
  // a candidate whose artwork can't be loaded at all leaves the set (and its dot) quietly
  const drop = (p) => {
    const k = picks.indexOf(p);
    if (k < 0) return;
    picks.splice(k, 1);
    if (!picks.length) { box.replaceChildren(); return; }
    show(Math.min(k, picks.length - 1));
  };
  function show(k) {
    i = k;
    const p = picks[k];
    const d = p.d;
    const it = (list && list.byId.get(p.id)) || { id: p.id, name: d.name, img: d.img, year: d.year };
    const f = names.film(d.name || it.name);
    const pic = h('img', { alt: '', decoding: 'async', fetchpriority: k === 0 ? 'high' : 'auto' });
    pic.addEventListener('load', () => {
      for (const old of artBox.querySelectorAll('img.on')) { old.classList.remove('on'); setTimeout(() => old.remove(), 1400); }
      requestAnimationFrame(() => pic.classList.add('on'));
      heroEl.classList.remove('is-loading');
    }, { once: true });
    pic.addEventListener('error', () => { if (pic.dataset.orig) { pic.remove(); drop(p); } });
    setImg(pic, d.backdrop, 'hero', '100vw');
    artBox.append(pic);
    const meta = [d.year || f.year, d.dur ? fmtDuration(Number(d.dur)) : '', Number(d.rating) ? `★ ${Number(d.rating).toFixed(1)}` : ''].filter(Boolean);
    const prog = kind === 'movies' ? store.progress.get(p.id) : null;
    const playBtn = h('button', { class: 'btn primary big', type: 'button' }, icon('play'),
      kind === 'movies' && prog && !prog.done && prog.t > 15 ? `Resume · ${fmtTime(prog.d - prog.t)} left` : kind === 'series' && p.why === 'continue' ? 'Continue' : 'Play');
    playBtn.addEventListener('click', async () => {
      if (kind === 'movies') {
        playVod({ id: p.id, kind: 'movie', name: it.name, img: it.img, sub: [d.year, d.genre].filter(Boolean).join(' · ') }, prog && !prog.done && prog.t > 15 ? prog.t : 0);
      } else {
        const sd = await getSeries(p.id);
        const up = nextUpFor(sd);
        if (up) playVod(episodeItem(sd, up.s, up.ep), up.resume); else location.hash = `#/series/${p.id}`;
      }
    });
    const v = vinfo(it.name ? it : { name: d.name });
    const len = f.title.length;
    const fill = () => {
      bodyBox.replaceChildren(
        h('div', { class: 'hero-kicker' }, p.why.startsWith('new') ? h('span', { class: 'new', text: 'New' }) : null,
          h('span', { class: 'why', text: WHY[p.why] || 'Featured' }),
          v.code ? h('span', { class: `tag ${v.uhd ? 'hot' : ''}`, text: v.code }) : null,
          meta.length ? h('span', { class: 'meta', text: meta.join('  ·  ') }) : null),
        h('h2', { class: `hero-title ${len > 44 ? 'xlong' : len > 24 ? 'long' : ''}`, text: f.title, title: f.title }),
        d.plot ? h('p', { class: 'hero-plot', text: d.plot }) : null,
        h('div', { class: 'hero-actions' }, playBtn, h('a', { class: 'btn big', href: `#/${kind}/${p.id}`, text: 'Details' }),
          favButton(p.id, { name: it.name || d.name, img: it.img || d.img, kind: kind === 'movies' ? 'movie' : 'series' })));
      bodyBox.classList.remove('leaving');
      bodyBox.classList.remove('entering'); void bodyBox.offsetWidth; bodyBox.classList.add('entering');
    };
    if (bodyBox.childElementCount) { bodyBox.classList.add('leaving'); setTimeout(fill, 260); } else fill();
    paintDots();
    if (window.scrollY < 200 && $('sheet').hidden) { state.pageArt = imgv(d.backdrop, 'hero-s'); updateAmbient(); }
    if (picks.length > 1) warm(picks[(k + 1) % picks.length]);       // the next backdrop is ready before it is needed
  }
  heroEl.classList.add('is-loading');
  box.replaceChildren(heroEl);
  show(0);
  restart();
  state.cleanup.push(() => clearInterval(timer));
  return true;
}

// Update badges on the cards already on screen. Re-rendering the grid instead would
// rebuild it from the first chunk and lose the scroll position.
function refreshProgressBadges() {
  for (const a of view.querySelectorAll('a.card[data-kind="movies"]')) {
    const poster = a.querySelector('.thumb');
    if (poster) setPosterBadges(poster, a.dataset.id);
  }
}

// ------------------------------------------------------------------ sheets: details pages + modals
let sheetOpenedByUs = false;
function openSheet(content, label, kind = 'modal') {
  const sheet = $('sheet');
  sheet.className = `sheet ${kind}`;
  sheet.replaceChildren(
    h('button', { class: 'icon-btn sheet-close', type: 'button', 'aria-label': kind === 'page' ? 'Back' : 'Close', onclick: () => closeSheet(true) },
      icon(kind === 'page' ? 'back' : 'close')),
    content);
  sheet.setAttribute('aria-label', label || 'Details');
  sheet.hidden = false;
  $('sheet-backdrop').hidden = kind === 'page';
  document.body.classList.add('sheet-open');
  sheet.scrollTop = 0;
  if (kind !== 'page') state.sheetArt = '';
  requestAnimationFrame(() => sheet.querySelector('.sheet-close').focus({ preventScroll: true }));
  updateAmbient();
}

function closeSheet(navigate) {
  const sheet = $('sheet');
  if (sheet.hidden) return;
  sheet.hidden = true;
  $('sheet-backdrop').hidden = true;
  document.body.classList.remove('sheet-open');
  sheet.replaceChildren();
  state.sheetArt = '';
  if (navigate) {
    const { sec, id } = parseHash();
    if (id) {
      if (sheetOpenedByUs && history.length > 1) history.back();
      else history.replaceState(null, '', `#/${sec}`);
    }
  }
  sheetOpenedByUs = false;
  updateAmbient();
}
$('sheet-backdrop').addEventListener('click', () => closeSheet(true));
document.addEventListener('click', (e) => { if (e.target.closest('a.card, .hero a.btn')) sheetOpenedByUs = true; });

async function openDetails(kind, id) {
  const loading = h('div', { class: 'dt' }, h('div', { class: 'skeleton' }, h('div', { class: 'sk-hero' })));
  openSheet(loading, 'Loading', 'page');
  try {
    if (kind === 'movies') await movieDetails(id); else await seriesDetails(id);
  } catch (e) {
    const { id: cur } = parseHash();
    if (cur === id) openSheet(h('div', { class: 'dt-body' }, errorBox(e.message, () => openDetails(kind, id))), 'Error', 'page');
  }
}

// Full-bleed backdrop, poster, title, meta, actions; then plot + facts (+ episodes).
function detailsPage(d0, actions, extras = [], more = []) {
  let d = d0;
  const art = h('div', { class: `dt-art ${d.backdrop ? '' : 'blur'}` });
  // a small poster, blurred, at once; the backdrop (sized for this screen) fades in over it
  if (d.img) art.append(h('img', { class: 'dt-ph', src: imgv(d.img, 'poster-s'), alt: '', decoding: 'async' }));
  if (d.backdrop || d.img) {
    const bi = h('img', { class: 'dt-bd', alt: '', decoding: 'async', fetchpriority: 'high' });
    bi.addEventListener('load', () => bi.classList.add('on'), { once: true });
    bi.addEventListener('error', () => { if (bi.dataset.orig) bi.remove(); });
    setImg(bi, d.backdrop || d.img, d.backdrop ? 'hero' : 'poster', d.backdrop ? '100vw' : '400px');
    art.append(bi);
  }
  state.sheetArt = d.backdrop ? imgv(d.backdrop, 'hero-s') : imgv(d.img, 'poster-s');
  const fy = names.film(d.name).year;
  const meta = [(d.year || fy) ? h('span', { text: String(d.year || fy) }) : null, d.dur ? h('span', { text: fmtDuration(d.dur) }) : null,
    ...more.map((t) => h('span', { text: t })),
    Number(d.rating) ? h('span', { class: 'star', text: `★ ${Number(d.rating).toFixed(1)}` }) : null, d.genre ? h('span', { class: 'gen', dataset: { field: 'genre' }, dir: 'auto', text: d.genre }) : null].filter(Boolean);
  const cat = d.cat ? names.category(d.cat) : null;
  const f = names.film(d.name);
  if (!d.year && f.year) d = { ...d, year: f.year };
  const facts = h('dl', { class: 'dt-facts' },
    d.director ? [h('dt', { text: 'Director' }), h('dd', { dataset: { field: 'director' }, dir: 'auto', text: d.director })] : null,
    d.cast ? [h('dt', { text: 'Cast' }), h('dd', { dataset: { field: 'cast' }, dir: 'auto', text: d.cast })] : null,
    d.genre ? [h('dt', { text: 'Genre' }), h('dd', { dataset: { field: 'genre' }, dir: 'auto', text: d.genre })] : null,
    cat ? [h('dt', { text: 'Category' }), h('dd', { text: [cat.region, cat.title].filter(Boolean).join(' · ') })] : null);
  return h('article', { class: 'dt' }, art,
    h('div', { class: 'dt-body' }, h('div', {}, d.img ? thumb(d.img, d.name, 'poster dt-poster') : null),
      h('div', { class: 'dt-text' }, h('span', { class: 'dt-kicker' }, f.prefix ? h('span', { class: `tag ${f.uhd ? 'hot' : ''}`, text: f.prefix }) : null,
          [cat ? (f.prefix && cat.region === f.prefix ? cat.title : [cat.region, cat.title].filter(Boolean).join(' · ')) : '', f.region].filter(Boolean).join('  ·  ')),
        h('h2', { id: 'sheet-title', class: 'dt-title', text: f.title }), meta.length ? h('div', { class: 'dt-meta' }, ...meta) : null, ...actions)),
    h('div', { class: 'dt-more' }, h('div', { class: 'dt-about' },
      d.plot ? h('p', { class: 'dt-plot', dir: 'auto', text: d.plot }) : h('p', { class: 'dt-plot muted', text: 'No description from the provider.' }),
      h('section', { class: 'dt-versions', hidden: true })),
      facts, ...extras));
}

// Other versions of this title (languages / 4K) and, when this version's description isn't in
// English, the English version's. Both need the catalogue list (usually already loaded: the page was
// opened from it); the details page draws first and this fills in.
// More like this (the Pi's tvapp/similar.py): series by genre, the words their descriptions share and
// era; films by their genre's categories and era. Same language, one version per title.
async function moreLikeThis(kind, d, page, list) {
  let r;
  try { r = await api(`/similar/${d.id}`, { timeout: 20000 }); } catch { return; }
  if (parseHash().id !== d.id || !page.isConnected) return;
  const items = (r.ids || []).map((id) => list.byId.get(id)).filter(Boolean);
  if (items.length < 3) return;
  page.querySelector('.dt-like')?.remove();
  page.append(h('section', { class: 'dt-like' },
    h('h3', { class: 'dt-like-title', text: 'More like this' }),
    h('div', { class: 'shelf like-shelf' }, items.map((it) => cardFor(kind, it)))));
}

const PLOT_PREFS = [['en', 'English when available'], ['orig', 'As the provider sends']];
const plotPref = () => (store.prefs.get('plotLang', 'en') === 'orig' ? 'orig' : 'en');

async function enrichDetails(kind, d, page) {
  let list = cached(kind);
  try { list = list || await catalogue(kind); } catch { return; }
  if (parseHash().id !== d.id || !page.isConnected) return;
  const item = list.byId.get(d.id) || { id: d.id, name: d.name, cat: '', year: d.year, key: fold(d.name) };
  const vs = versions.versionsOf(item, list.items, list.cats, langWant());
  const slot = page.querySelector('.dt-versions');
  if (slot && vs.length) {
    const route = kind === 'movies' ? 'movies' : 'series';
    const chip = (v) => h('a', { class: 'chip', href: `#/${route}/${v.item.id}`, text: v.label, title: v.item.name });
    const SHOW = 8;
    const more = vs.length > SHOW ? h('button', { class: 'chip ghost', type: 'button', text: `+${vs.length - SHOW} more` }) : null;
    const chips = h('div', { class: 'chips dt-chips' }, h('span', { class: 'chip on', 'aria-current': 'true', text: versions.label(d.name), title: d.name }),
      ...vs.slice(0, SHOW).map(chip), more);
    if (more) more.addEventListener('click', () => { more.replaceWith(...vs.slice(SHOW).map(chip)); });
    slot.replaceChildren(h('h3', { class: 'dt-sub', text: 'Also available' }), chips);
    slot.hidden = false;
  }
  moreLikeThis(kind, d, page, list);
  const about = page.querySelector('.dt-about');
  if (!about || plotPref() !== 'en' || !versions.foreignPlot(d.name, d.plot)) return;
  const en = versions.englishVersion(vs);
  if (!en) return;
  let ed;
  try { ed = kind === 'movies' ? await api(`/movie/${en.item.id}`) : await getSeries(en.item.id); } catch { return; }
  if (parseHash().id !== d.id || !page.isConnected || !ed || !ed.plot) return;
  const p = about.querySelector('.dt-plot');
  // genre, cast and director follow the description when theirs aren't in English either
  const fields = ['genre', 'cast', 'director'].filter((f) => ed[f] && d[f] && versions.foreignPlot(d.name, d[f]));
  let english = true;
  const toggle = h('button', { class: 'linkish', type: 'button' });
  const note = h('p', { class: 'dt-plot-note muted small' },
    h('span', { text: `${fields.length ? 'Description and details' : 'Description'} from the English version · ` }), toggle);
  const paint = () => {
    p.textContent = english ? ed.plot : d.plot;
    p.lang = english ? 'en' : '';
    for (const f of fields) {
      for (const el of page.querySelectorAll(`[data-field="${f}"]`)) { el.textContent = english ? ed[f] : d[f]; el.lang = english ? 'en' : ''; }
    }
    toggle.textContent = english ? 'Show original' : 'Show English';
  };
  toggle.addEventListener('click', () => { english = !english; paint(); });
  paint();
  p.after(note);
}

async function movieDetails(id) {
  const d = await api(`/movie/${id}`);
  if (parseHash().id !== id) return;
  const meta = { name: d.name, img: d.img, kind: 'movie' };
  const item = { id: d.id, kind: 'movie', name: d.name, img: d.img, sub: [d.year, d.genre].filter(Boolean).join(' · ') };
  const p = store.progress.get(id);
  const actions = h('div', { class: 'dt-actions' });
  const play = (resume) => { closeSheet(true); playVod(item, resume); };
  if (p && !p.done && p.t > 15) {
    actions.append(h('button', { class: 'btn primary big', type: 'button', onclick: () => play(p.t) }, icon('play'), `Resume from ${fmtTime(p.t)}`),
      h('button', { class: 'btn big', type: 'button', onclick: () => play(0), text: 'Start over' }));
  } else {
    actions.append(h('button', { class: 'btn primary big', type: 'button', onclick: () => play(0) }, icon('play'), p && p.done ? 'Play again' : 'Play'));
  }
  actions.append(favButton(id, meta));
  const watched = h('button', { class: 'btn ghost', type: 'button' }, icon(p && p.done ? 'close' : 'check'), p && p.done ? 'Mark as unwatched' : 'Mark as watched');
  watched.addEventListener('click', () => {
    if (p && p.done) store.progress.clear(id); else store.progress.markDone(id, meta);
    movieDetails(id);
    refreshProgressBadges();
  });
  actions.append(watched);
  const prog = p && !p.done && p.d ? h('div', { class: 'dt-progress' }, progressBar(p.t / p.d), `${fmtTime(p.d - p.t)} left`) : null;
  const page = detailsPage(d, [actions, prog].filter(Boolean));
  openSheet(page, d.name, 'page');
  enrichDetails('movies', d, page);
}

// ---- cast in the player (the Pi's tvnext/cast.py, from TMDB with the owner's key): who is in this film or
// episode - its regulars, then the episode's guest stars - shown with the controls. Per device: Settings.
const CAST_KEY = `${LSK}cast`;
const castOn = () => lsGet(CAST_KEY, 'show') !== 'hide';
let castFor = '';
async function playerCast(item) {
  const box = $('p-cast');
  const id = item && (item.kind === 'movie' || item.kind === 'episode') ? item.id : '';
  castFor = id;
  if (!id || !castOn()) { box.hidden = true; box.replaceChildren(); return; }
  box.hidden = true;
  let q;
  try {
    if (item.kind === 'movie') {
      const d = await api(`/movie/${item.id}`);
      const f = names.film(d.name || item.name);
      q = { type: 'movie', tmdb: d.tmdb || 0, title: f.title, year: d.year || f.year || 0 };
    } else {
      const d = await getSeries(item.series);
      const f = names.film(d.name || item.seriesName || '');
      q = { type: 'tv', tmdb: d.tmdb || 0, title: f.title, year: d.year || f.year || 0, s: item.season || 0, e: item.episode || 0 };
    }
  } catch { return; }
  let r;
  try {
    const res = await fetch(`${NEXT}/api/cast?${new URLSearchParams(q)}`, { credentials: 'same-origin' });
    r = res.ok ? await res.json() : null;
  } catch { return; }
  if (castFor !== id || !r || !r.cast || !r.cast.length) return;
  const person = (p) => {
    const face = h('span', { class: 'pc-face', 'aria-hidden': 'true', dataset: { i: p.name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('') } });
    if (p.photo) {
      const im = h('img', { src: `${NEXT}/cast-img/w185/${p.photo}`, alt: '', decoding: 'async', loading: 'lazy' });
      im.addEventListener('error', () => im.remove(), { once: true });
      face.append(im);
    }
    return h('li', { class: `pc-person ${p.guest ? 'guest' : ''}` }, face,
      h('span', { class: 'pc-text' }, h('b', { text: p.name }), p.character ? h('span', { text: p.character }) : null,
        p.guest ? h('em', { text: 'Guest' }) : null));
  };
  box.replaceChildren(h('div', { class: 'pc-head' }, h('span', { text: item.kind === 'episode' ? 'In this episode' : 'Cast' }),
    h('span', { class: 'pc-src', title: r.credit || '', text: 'TMDB' })),
  h('ul', { class: 'pc-list', role: 'list' }, r.cast.map(person)));
  box.hidden = false;
}

async function getSeries(id) {
  const c = state.seriesCache.get(id);
  if (c && Date.now() - c.at < 10 * 60000) return c.d;
  const d = await api(`/series/${id}`);
  state.seriesCache.set(id, { d, at: Date.now() });
  return d;
}

function episodeItem(d, season, ep) {
  return { id: ep.id, kind: 'episode', name: ep.name, img: ep.img || d.img, series: d.id, seriesName: d.name,
    season: season.n, episode: ep.episode, sub: `${ftitle(d.name)} · S${season.n} E${ep.episode}` };
}

function flatEpisodes(d) {
  const out = [];
  for (const s of d.seasons) for (const ep of s.episodes) out.push({ s, ep });
  return out;
}

function nextUpFor(d) {
  const flat = flatEpisodes(d);
  if (!flat.length) return null;
  let best = null;
  for (let i = 0; i < flat.length; i++) {
    const p = store.progress.get(flat[i].ep.id);
    if (p && (!best || p.at > best.p.at)) best = { i, p };
  }
  if (!best) return { ...flat[0], resume: 0, label: `Play S${flat[0].s.n} E${flat[0].ep.episode}` };
  if (!best.p.done) return { ...flat[best.i], resume: best.p.t, label: `Resume S${flat[best.i].s.n} E${flat[best.i].ep.episode}` };
  const n = flat[best.i + 1];
  return n ? { ...n, resume: 0, label: `Next: S${n.s.n} E${n.ep.episode}` } : null;
}

async function nextEpisode(item) {
  if (!item.series) return null;
  const d = await getSeries(item.series);
  const flat = flatEpisodes(d);
  const i = flat.findIndex((x) => x.ep.id === item.id);
  const n = i >= 0 ? flat[i + 1] : null;
  return n ? episodeItem(d, n.s, n.ep) : null;
}

async function seriesDetails(id) {
  const d = await getSeries(id);
  if (parseHash().id !== id) return;
  const meta = { name: d.name, img: d.img, kind: 'series' };
  const actions = h('div', { class: 'dt-actions' });
  const up = nextUpFor(d);
  if (up) {
    actions.append(h('button', { class: 'btn primary big', type: 'button', onclick: () => { closeSheet(true); playVod(episodeItem(d, up.s, up.ep), up.resume); } },
      icon('play'), up.label));
  }
  const total = d.seasons.reduce((n, s) => n + s.episodes.length, 0);
  // Shuffle: one random episode - from the whole series, or from the season you chose below.
  // Never the episode playing now or the one you just watched, and nothing seen in the last two
  // weeks while there is anything else (then the longest-unseen ones).
  let picked = false;                              // a season chosen by you (not the page's default)
  const label = h('span');
  const shuffleBtn = h('button', { class: 'btn big shuffle-btn', type: 'button', title: 'Play one random episode. Choose a season below to shuffle only that season; choose it again for the whole series.' },
    icon('swap'), label);
  const paintShuffle = () => {
    const scoped = picked && season && d.seasons.length > 1;
    label.textContent = scoped ? `Shuffle S${season.n}` : 'Shuffle series';
    shuffleBtn.setAttribute('aria-label', scoped ? `Play a random episode from season ${season.n}` : 'Play a random episode from the whole series');
  };
  shuffleBtn.addEventListener('click', () => {
    const last = store.progress.lastBySeries()[id];
    const playing = player.item && player.item.series === id ? player.item.id : null;
    const seen = store.progress.all();
    const pickEp = shuffle.pickEpisode(d.seasons, { season: picked && season ? season.n : null, avoid: [playing, last && last.id],
      seenAt: (eid) => (seen[eid] ? seen[eid].at : 0) });
    if (!pickEp) return;
    const it = episodeItem(d, pickEp.s, pickEp.ep);
    toast(`Shuffle · S${pickEp.s.n} E${pickEp.ep.episode} · ${pickEp.ep.name}`, 2600);
    closeSheet(true);
    const p = store.progress.get(it.id);
    playVod(it, p && !p.done ? p.t : 0);
  });
  if (total) actions.append(shuffleBtn);
  actions.append(favButton(id, meta));
  const tabs = h('div', { class: 'chips', role: 'tablist', 'aria-label': 'Seasons' });
  const eps = h('ol', { class: 'episodes' });
  const epQ = total > 12 ? h('input', { class: 'input ep-filter', type: 'search', placeholder: `Filter ${total} episodes`,
    'aria-label': 'Filter episodes', enterkeyhint: 'search', autocomplete: 'off' }) : null;
  let season = null;
  // withSeason: rows from several seasons (filter results) say which season they are from
  const epRow = (s, ep, withSeason) => {
    const p = store.progress.get(ep.id);
    const it = episodeItem(d, s, ep);
    const still = thumb(ep.img || d.img, ep.name, 'still');
    still.append(h('span', { class: 'ep-play' }, icon('play')));
    if (p && !p.done && p.d) still.append(progressBar(p.t / p.d, 'on-poster'));
    const b = h('button', { class: 'ep', type: 'button', 'aria-label': `Season ${s.n}, episode ${ep.episode}: ${ep.name}` },
      still,
      h('span', { class: 'ep-text' },
        h('span', { class: 'ep-title' }, h('span', { class: 'n', text: withSeason ? `S${s.n} E${ep.episode}` : `E${ep.episode}` }), h('span', { text: ep.name })),
        h('span', { class: 'ep-meta', text: [ep.dur ? fmtDuration(ep.dur) : '', p && !p.done && p.t > 15 ? `${fmtTime(p.t)} watched` : ''].filter(Boolean).join('  ·  ') }),
        ep.plot ? h('span', { class: 'ep-plot', text: ep.plot }) : null),
      p && p.done ? h('span', { class: 'watched inline', 'aria-label': 'Watched' }, icon('check')) : h('span'));
    b.addEventListener('click', () => { closeSheet(true); playVod(it, p && !p.done ? p.t : 0); });
    return h('li', {}, b);
  };
  const showSeason = (s) => {
    season = s;
    if (epQ) epQ.value = '';
    for (const t of tabs.children) t.setAttribute('aria-selected', t.dataset.n === String(s.n) ? 'true' : 'false');
    store.prefs.set(`season.${id}`, s.n);
    eps.replaceChildren(...s.episodes.map((ep) => epRow(s, ep, false)));
    paintShuffle();
  };
  if (epQ) {
    const keyed = d.seasons.flatMap((s) => s.episodes.map((ep) => ({ s, ep, key: fold(`${ep.name} ${ep.plot || ''}`) })));
    let timer = 0;
    epQ.addEventListener('input', () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const terms = fold(epQ.value).split(/\s+/).filter(Boolean);
        if (!terms.length) { if (season) showSeason(season); return; }
        for (const t of tabs.children) t.setAttribute('aria-selected', 'false');
        const hits = keyed.filter(({ s, ep, key }) => terms.every((term) => key.includes(term)
          || term === String(ep.episode) || term === `s${s.n}e${ep.episode}`));
        eps.replaceChildren(...(hits.length ? hits.map(({ s, ep }) => epRow(s, ep, true))
          : [h('li', {}, emptyBox('No matches', `No episode matches “${epQ.value.trim()}”.`))]));
      }, 120);
    });
  }
  for (const s of d.seasons) {
    const t = h('button', { class: 'chip', type: 'button', role: 'tab', dataset: { n: String(s.n) } }, `Season ${s.n}`,
      h('span', { class: 'chip-n', text: String(s.episodes.length) }));
    t.addEventListener('click', () => {
      picked = !(picked && season === s);           // the chosen season again: back to the whole series
      showSeason(s);
    });
    tabs.append(t);
  }
  const epsBox = h('section', { class: 'dt-eps' }, d.seasons.length
    ? [h('div', { class: 'dt-eps-head' }, h('h3', { class: 'section-title', text: 'Episodes' }), epQ), tabs, eps]
    : emptyBox('No episodes', 'The provider did not list any episodes for this series.'));
  const counts = [d.seasons.length > 1 ? `${d.seasons.length} seasons` : '', total ? `${total} episode${total === 1 ? '' : 's'}` : ''].filter(Boolean);
  const page = detailsPage(d, [actions], [epsBox], counts);
  openSheet(page, d.name, 'page');
  enrichDetails('series', d, page);
  paintShuffle();
  if (d.seasons.length) {
    const want = up ? up.s.n : store.prefs.get(`season.${id}`, d.seasons[0].n);
    showSeason(d.seasons.find((s) => s.n === want) || d.seasons[0]);
  }
}

// ------------------------------------------------------------------ SEARCH
// Films / series by name. Relevance first - the cleaned title equal to the query, then starting
// with it, then a word starting with it, then anywhere - and only inside each of those groups does
// the language preference order versions (English, unlabelled, subtitled, dubbed); then shorter
// titles and newer years. 'English only' then drops the versions lang.applyLangPref drops.
function rankedSearch(list, query, limit, keep, pref) {
  const terms = fold(query).split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const q = terms.join(' ');
  const hits = [];
  for (const it of list.items) {
    if (terms.every((t) => it.key.includes(t)) && (!keep || keep(it))) hits.push(it);
  }
  const rel = (it) => {
    const t = fold(vinfo(it).clean);
    return t === q ? 0 : t.startsWith(q) ? 1 : (` ${t}`).includes(` ${terms[0]}`) ? 2 : 3;
  };
  const scored = hits.map((it) => ({ it, r: rel(it), l: pref === 'all' ? 0 : vinfo(it).tier, n: vinfo(it).clean.length, y: Number(it.year) || 0 }));
  scored.sort((a, b) => a.r - b.r || a.l - b.l || a.n - b.n || b.y - a.y);
  let out = scored.map((x) => x.it);
  if (pref === 'only') out = lang.applyLangPref(out, 'only', vinfo);
  return out.slice(0, limit);
}

async function viewSearch() {
  const input = h('input', { class: 'input', type: 'search', placeholder: 'Channels, programmes, films, series', 'aria-label': 'Search', enterkeyhint: 'search', autocomplete: 'off', spellcheck: 'false' });
  const hint = h('div', { class: 'search-hint' }, h('span', { text: 'Runs on this device — nothing is sent to the provider' }),
    TOUCH ? null : h('span', {}, h('kbd', { text: '/' }), ' anywhere to search'));
  const results = h('div', { class: 'results', 'aria-live': 'polite' });
  const lc = langSeg(() => run());
  hint.append(h('span', { class: 'seg-label' }, h('span', { text: 'Films & series' }), lc), lc.help);
  view.replaceChildren(h('div', { class: 'search-hero' }, h('div', { class: 'search-box' }, icon('search'), input), hint), results);
  const linked = parseHash().id;                     // #/search/<words>: a link straight to results
  input.value = linked ? decodeURIComponent(linked) : store.prefs.get('lastSearch', '');
  setTimeout(() => input.focus(), 50);
  results.replaceChildren(h('div', { class: 'grid skeleton', 'aria-hidden': 'true' }, Array.from({ length: 14 }, () => h('div', { class: 'sk-card' }))));
  const loaded = {};
  const kinds = ['live', 'movies', 'series'];
  await Promise.all(kinds.map((k) => catalogue(k).then((l) => { loaded[k] = l; }).catch(() => {})));
  if (state.section !== 'search') return;
  if (!guideData || !Object.keys(guideData).length) epgNow().then((g) => { guideData = g; }).catch(() => {});
  let timer = 0;
  const progs = { ctl: null, timer: 0, open: new Set() };
  const progBox = h('section', { hidden: true });
  state.cleanup.push(() => { clearTimeout(timer); clearTimeout(progs.timer); if (progs.ctl) progs.ctl.abort(); });
  const findProgrammes = (q) => {
    clearTimeout(progs.timer);
    if (progs.ctl) progs.ctl.abort();
    progBox.hidden = true;
    if (!loaded.live || fold(q).replace(/[^\p{L}\p{N}]/gu, '').length < 2) return;
    progs.timer = setTimeout(async () => {
      const ctl = progs.ctl = new AbortController();
      try {
        const c = await caps.get(player.preferNative).catch(() => '');
        const d = await searchGuide(q, c, ctl.signal);
        if (ctl.signal.aborted || q !== input.value.trim()) return;
        const hc = store.hidden.cats('live');
        const hch = store.hidden.channels();
        const allow = hc.size || hch.size ? new Set(loaded.live.items.filter((i) => !hch.has(i.id) && !hc.has(i.cat)).map((i) => i.id)) : null;
        const r = programmeSections(d, loaded.live, allow, progs.open);
        if (!r.shown) return;
        progBox.replaceChildren(h('div', { class: 'shelf-head' }, h('h2', { class: 'section-title', text: 'On TV' }), h('span', { class: 'n', text: String(r.shown) })), ...r.nodes);
        progBox.hidden = false;
        if (!results.contains(progBox)) results.prepend(progBox);
      } catch { /* aborted or offline: names still match below */ }
    }, 280);
  };
  const run = () => {
    const q = input.value.trim();
    store.prefs.set('lastSearch', q);
    if (!q) { results.replaceChildren(emptyBox('Find anything', 'Channel names, what’s on now and in the next 24 hours, films and series.')); return; }
    const sections = [progBox];
    let total = 0;
    const hiddenCh = store.hidden.channels();
    const anyHidden = hiddenCh.size > 0 || kinds.some((k) => store.hidden.cats(STORE_KIND[k]).size > 0);
    const sh = (title, n, ...content) => h('section', {}, h('div', { class: 'shelf-head' }, h('h2', { class: 'section-title', text: title }), h('span', { class: 'n', text: String(n) })), ...content);
    if (loaded.live) {
      const hc = store.hidden.cats('live');
      const r = search(loaded.live, q, 40, (i) => !hiddenCh.has(i.id) && !hc.has(i.cat) && !names.parse(i.name).sep);
      total += r.length;
      if (r.length) sections.push(sh('Channels', r.length, h('ul', { class: 'ch-list', role: 'list' }, r.map((ch) => channelRow(ch)))));
    }
    for (const k of ['movies', 'series']) {
      if (!loaded[k]) continue;
      const hc = store.hidden.cats(STORE_KIND[k]);
      const r = rankedSearch(loaded[k], q, 48, hc.size ? (i) => !hc.has(i.cat) : null, langPref());
      total += r.length;
      if (r.length) sections.push(sh(k === 'movies' ? 'Films' : 'Series', r.length, h('div', { class: 'grid' }, r.map((it) => cardFor(k, it)))));
    }
    if (anyHidden) sections.push(h('p', { class: 'muted small', text: 'Hidden channels and categories are left out.' }));
    results.replaceChildren(...(total ? sections : [progBox, emptyBox('No names match', `Nothing is called “${q}”.`)]));
    findProgrammes(q);
  };
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 60); });
  run();
}

// ------------------------------------------------------------------ LIBRARY + settings
// An episode's card shows its series' poster: the provider's episode images are small video frames,
// blurry and oddly cropped in a poster-shaped card. From the Series list when it's loaded, else this
// device's memory of series posters, else the series' details (once; then remembered).
const SERIES_POSTERS = `${LSK}seriesPosters`;
function knownSeriesPoster(id) {
  const it = cached('series') && cached('series').byId.get(id);
  if (it && it.img) return it.img;
  try { return JSON.parse(localStorage.getItem(SERIES_POSTERS) || '{}')[id] || ''; } catch { return ''; }
}
function rememberSeriesPoster(id, img) {
  try {
    const m = JSON.parse(localStorage.getItem(SERIES_POSTERS) || '{}');
    m[id] = img;
    const keys = Object.keys(m);
    for (const k of keys.slice(0, Math.max(0, keys.length - 300))) delete m[k];
    localStorage.setItem(SERIES_POSTERS, JSON.stringify(m));
  } catch { /* private mode: fetched again next time */ }
}

function posterCard(entry, onClick, sub) {
  const b = h('button', { class: 'card', type: 'button', 'aria-label': entry.name });
  const episode = entry.kind === 'episode' && entry.series;
  const art = (key) => {
    const t = thumb(key, ftitle(entry.name), 'poster');
    if (entry.frac) t.append(progressBar(entry.frac, 'on-poster'));
    return t;
  };
  const known = episode ? knownSeriesPoster(entry.series) : '';
  const poster = art(episode ? known : entry.img);
  if (episode && !known) {
    getSeries(entry.series).then((d) => {
      if (!d || !d.img) return;
      rememberSeriesPoster(entry.series, d.img);
      if (poster.isConnected) poster.replaceWith(art(d.img));
    }).catch(() => { if (poster.isConnected && entry.img) poster.replaceWith(art(entry.img)); });
  }
  b.append(poster, h('span', { class: 'card-title', text: ftitle(entry.name) }));
  if (sub) b.append(h('span', { class: 'card-sub', text: sub }));
  b.addEventListener('click', onClick);
  return b;
}

// What a channel is showing now (and next), from the guide's now/next list.
function nowOn(id) {
  const g = (guideData || {})[id];
  if (!g || !g.now) return null;
  const [start, stop, title] = g.now;
  const t = Date.now() / 1000;
  return { title, frac: (t - start) / (stop - start), left: minsLeft(stop, t), next: g.next ? { at: fmtClock(g.next[0]), title: g.next[2] } : null };
}
// A channel in the Library (Recently played, Favourites): a wide card over its own logo, softened.
// The cleaned name on up to two lines (the provider's own name stays as the tooltip); a second line
// only when other channels share that name (names.twinLabel). With the guide: what's on, how far in,
// what's next. Without: the channel's own category and tags in the same places, and for a recent one
// when you last watched - real information only, never an empty card.
// A saved channel (recent / favourite) as the catalogue has it now: event channels are reused for
// other matches, so the name saved when it was watched can be days out of date.
function currentChannel(e) {
  const it = e.kind === 'live' || !e.kind ? cached('live')?.byId.get(e.id) : null;
  return it ? { ...e, name: it.name || e.name, img: it.img || e.img } : e;
}

function channelCard(saved, onClick, recent = false) {
  const e = currentChannel(saved);
  const p = names.parse(e.name || '');
  const title = names.cardTitle(e.name || '');
  const live = cached('live');
  const it = live && live.byId.get(e.id);
  const cat = it && live.cats.get(it.cat) ? names.category(live.cats.get(it.cat)) : null;
  const twin = live ? names.twinLabel(e, live.items, live.cats) : '';
  const sub = twin || names.eventStatus(e.name || '');
  const bg = h('span', { class: 'rc-bg', 'aria-hidden': 'true' });
  if (e.img) bg.append(h('img', { src: imgv(e.img, 'logo-l'), alt: '', decoding: 'async' }));
  const n = nowOn(e.id);
  let body;
  if (n) {
    body = [h('span', { class: 'rc-now', text: n.title }), progressBar(n.frac, 'live'),
      h('span', { class: 'rc-next', text: n.next ? `${n.left} · then ${n.next.title}` : n.left })];
  } else {
    const tags = [p.prefix, ...p.tags].filter(Boolean).slice(0, 3);
    const catTitle = cat ? cat.title.replace(/\s*[:|]\s*$/, '') : '';                 // "4K| ᵁᴴᴰ" -> "4K", already a tag
    body = [catTitle && !tags.includes(catTitle.toUpperCase()) ? h('span', { class: 'rc-now rc-cat', text: catTitle }) : null,
      tags.length ? h('span', { class: 'rc-tags' }, ...tags.map((t) => h('span', { class: 'tag', text: t }))) : null,
      h('span', { class: 'rc-next', text: recent && e.at ? `No guide · watched ${ago(e.at / 1000)}` : 'No programme guide' })];
  }
  const who = sub ? `${title} (${sub})` : title;
  const b = h('button', { class: `ch-wide ${n ? '' : 'no-guide'}`, type: 'button', title: e.name,
    'aria-label': n ? `${who}: ${n.title}, ${n.left}` : `${who}, no programme guide` }, bg,
    h('span', { class: 'rc-head' }, thumb(e.img, title, 'logo'),
      h('span', { class: 'rc-names' }, h('span', { class: 't', text: title }), sub ? h('span', { class: 'rc-sub', text: sub }) : null)),
    h('span', { class: 'rc-body' }, ...body.filter(Boolean)));
  b.addEventListener('click', onClick);
  return b;
}
// a row of them
const channelCards = (list, open, recent = false) => h('div', { class: 'shelf ch-row' }, ...list.map((e) => channelCard(e, () => open(e), recent)));

function openEntry(e, resume) {
  if (e.kind === 'live') { const c = currentChannel(e); playChannel({ id: c.id, name: c.name, img: c.img, num: c.num }); return; }
  if (e.kind === 'movie') { playVod({ id: e.id, kind: 'movie', name: e.name, img: e.img }, resume); return; }
  if (e.kind === 'series') { location.hash = `#/series/${e.id}`; return; }
  if (e.kind === 'episode') {
    playVod({ id: e.id, kind: 'episode', name: e.name, img: e.img, series: e.series, seriesName: e.seriesName,
      season: e.season, episode: e.episode, sub: e.seriesName ? `${e.seriesName} · S${e.season} E${e.episode}` : '' }, resume);
  }
}

function viewLibrary() {
  const which = state.section;
  const shelf = () => h('div', { class: 'shelf' });
  const sec = (id, title, n, content, extra) => h('section', { class: 'shelf-sec', id: `lib-${id}` },
    h('div', { class: 'shelf-head' }, h('h2', { class: 'section-title', text: title }), h('span', { class: 'n', text: n ? String(n) : '' }), extra || null), content);

  // Continue watching: in-progress items + next-up for finished episodes
  const cont = shelf();
  const inprog = store.progress.inProgress();
  for (const e of inprog.slice(0, 30)) {
    const sub = e.kind === 'episode' ? `S${e.season} E${e.episode} · ${fmtTime(e.d - e.t)} left` : `${fmtTime(e.d - e.t)} left`;
    cont.append(posterCard({ ...e, name: e.kind === 'episode' && e.seriesName ? e.seriesName : e.name, frac: e.t / e.d }, () => openEntry(e, e.t), sub));
  }
  const lastBySeries = store.progress.lastBySeries();
  const pendingNext = Object.values(lastBySeries).filter((e) => e.done).sort((a, b) => b.at - a.at).slice(0, 6);
  for (const e of pendingNext) {
    getSeries(e.series).then((d) => {
      const up = nextUpFor(d);
      if (!up || up.resume) return;
      const it = episodeItem(d, up.s, up.ep);
      cont.querySelector('.state')?.remove();
      cont.append(posterCard({ ...it, name: d.name, kind: 'episode' }, () => playVod(it, 0), `Up next · S${up.s.n} E${up.ep.episode}`));
    }).catch(() => {});
  }
  if (!inprog.length) cont.append(emptyBox('Nothing in progress', 'Films and episodes you start appear here.'));

  // Favourites by kind
  const favWrap = h('div', {});
  let favN = 0;
  for (const [k, label] of [['live', 'Channels'], ['movie', 'Films'], ['series', 'Series']]) {
    const list = store.favs.list(k);
    if (!list.length) continue;
    favN += list.length;
    favWrap.append(h('h3', { class: 'sub-title', text: label }),
      k === 'live' ? channelCards(list, (e) => openEntry({ ...e, kind: k }))
        : h('div', { class: 'shelf' }, list.map((e) => posterCard({ ...e, kind: k }, () => openEntry({ ...e, kind: k })))));
  }
  if (!favN) favWrap.append(emptyBox('No favourites yet', 'Use the star on any channel, film or series.'));

  // Recent: channels as wide cards, then films and series (each series once, its latest episode)
  // each series once: its latest episode stands for the rest ("S3 E8 · +7 more")
  const seen = new Map();
  const rec = [];
  for (const e of store.recent.list()) {
    if (e.kind === 'episode' && e.series) {
      if (seen.has(e.series)) { seen.get(e.series).more += 1; continue; }
      const x = { ...e, more: 0 };
      seen.set(e.series, x);
      rec.push(x);
    } else rec.push(e);
  }
  const titleCard = (e) => {
    const p = store.progress.get(e.id);
    return posterCard({ ...e, name: e.kind === 'episode' && e.seriesName ? e.seriesName : e.name, frac: p && !p.done ? p.t / p.d : 0 }, () => openEntry(e, p && !p.done ? p.t : 0),
      e.kind === 'episode' ? `S${e.season} E${e.episode}${e.more ? ` · +${e.more} more episode${e.more === 1 ? '' : 's'}` : ''}` : 'Film');
  };
  const chans = rec.filter((e) => e.kind === 'live');
  const titles = rec.filter((e) => e.kind !== 'live');
  let recRow = h('div', { class: 'rec-split' },
    chans.length ? channelCards(chans, (e) => openEntry(e), true) : null,
    titles.length ? h('div', { class: 'shelf' }, ...titles.map(titleCard)) : null);
  // channel cards show what's on (the guide's now/next list) and the channel's category and namesakes
  // (the channel list): both loaded here if Live hasn't been opened, then the page redraws once each
  if (chans.length || store.favs.list('live').length) {
    const again = () => { if (['library', 'recent', 'favourites'].includes(state.section)) render(true); };
    if (!guideData || !Object.keys(guideData).length) epgNow().then((g) => { guideData = g; if (Object.keys(g || {}).length) again(); }).catch(() => {});
    if (!cached('live')) catalogue('live').then(again).catch(() => {});
  }
  if (!rec.length) recRow = h('div', {}, emptyBox('Nothing yet', 'Channels and titles you play appear here.'));
  const clearBtn = rec.length ? h('button', { class: 'btn ghost small', type: 'button', text: 'Clear', onclick: () => { store.recent.clear(); render(true); } }) : null;

  const gear = h('a', { class: 'btn ghost small', href: '#/settings' }, icon('settings'), 'Settings');
  view.replaceChildren(head('Library', 'Synced across your devices', gear),
    sec('continue', 'Continue watching', inprog.length, cont),
    sec('favourites', 'Favourites', favN, favWrap),
    sec('recent', 'Recently played', store.recent.list().length, recRow, clearBtn));
  if (which !== 'library') {
    const target = $(`lib-${which}`);
    if (target) requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }));
  }
}

// Settings: preferences, this device's interface, sync & backup, the Pi's status; diagnostics last.
function viewSettings() {
  const tracksBox = h('section', { class: 'panel', id: 'lib-tracks' });
  const uiBox = h('section', { class: 'panel', id: 'lib-interface' });
  const layoutBox = h('section', { class: 'panel', id: 'lib-layout' });
  const castBox = h('section', { class: 'panel', id: 'lib-cast' });
  const provBox = h('section', { class: 'panel', id: 'lib-providers', hidden: FAMILY });
  const timeBox = h('section', { class: 'panel', id: 'lib-time' });
  const famBox = h('section', { class: 'panel', id: 'lib-family', hidden: true });
  const sportsBox = h('section', { class: 'panel', id: 'lib-sports' });
  const backupBox = h('section', { class: 'panel', id: 'lib-backup' });
  const statusBox = h('section', { class: 'panel', id: 'lib-status' });
  const artBox = h('section', { class: 'panel', id: 'lib-artwork' });
  view.replaceChildren(head('Settings', 'Languages and sync are shared by all your devices'),
    h('div', { class: 'settings' }, tracksBox, uiBox, layoutBox, castBox, provBox, timeBox, sportsBox, famBox, backupBox, statusBox),
    h('div', { class: 'settings-group' }, h('h2', { class: 'section-title', text: 'Diagnostics' }),
      h('div', { class: 'settings' }, artBox)));
  renderTrackPrefs(tracksBox);
  renderInterface(uiBox);
  renderLayout(layoutBox);
  renderCast(castBox);
  if (!FAMILY) renderProviders(provBox);
  renderTimes(timeBox);
  sportsBox.replaceChildren(h('h2', { text: 'Sports' }),
    h('label', { class: 'pref-row' }, h('span', { text: 'Live scores' }),
      selectEl('Live scores', [['show', 'Show'], ['hide', 'Hide (no spoilers)']], scoresOn() ? 'show' : 'hide', (v) => {
        try { localStorage.setItem(SCORES_KEY, v); } catch { /* private mode */ }
        toast('Saved on this device');
      })),
    h('p', { class: 'muted small', text: 'The score and minute on live matches in Sports, updated every minute. Replays never show one. Only this device changes.' }));
  renderFamily(famBox);
  renderBackup(backupBox);
  renderStatus(statusBox);
  renderArtwork(artBox);
  // a family site: no diagnostics (its owner sees them on their own site)
  loadStatus().then((st) => { if (st && st.site && st.site.auth === 'passphrase') artBox.closest('.settings-group').hidden = true; });
}

// ---- Family sites (the owner's own site only): the other households' copies of the app, each behind
// one passphrase. Change it, or sign everyone out, from anywhere - e.g. a phone, when someone texts.
async function postJSON(path, body) {
  const res = await fetch(BASE + path, { method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-TV-Sync': '1', Accept: 'application/json' }, body: JSON.stringify(body || {}) });
  let d = null;
  try { d = await res.json(); } catch { /* empty */ }
  if (!res.ok) throw new Error((d && d.error) || `Server error (${res.status})`);
  return d;
}

function renderFamily(box) {
  if (FAMILY) { box.hidden = true; return; }           // only on the owner's own site
  const draw = async () => {
    let d;
    try { d = await api('/family', { timeout: 10000 }); } catch { box.hidden = true; return; }
    if (!d || !d.sites || !d.sites.length) { box.hidden = true; return; }
    box.hidden = false;
    const rows = d.sites.map((s) => {
      const state = !s.up ? { cls: 'warn', text: 'Not running' }
        : !s.configured ? { cls: 'warn', text: 'Running · provider not set up yet' }
          : s.error ? { cls: 'warn', text: `Running · provider problem: ${s.error}` }
            : { cls: 'ok', text: `Running · ${(s.counts && s.counts.live) ? `${s.counts.live.toLocaleString()} channels` : 'catalogue loading'}${s.streams ? ` · ${s.streams} watching now` : ''}` };
      const input = h('input', { class: 'input', type: 'text', placeholder: s.passphrase ? 'New passphrase' : 'Set a passphrase', autocomplete: 'off',
        autocapitalize: 'off', spellcheck: 'false', 'aria-label': `New passphrase for ${s.name}`, enterkeyhint: 'done' });
      const save = h('button', { class: 'btn small primary', type: 'button', text: 'Save' });
      const out = h('button', { class: 'btn small ghost', type: 'button', text: 'Sign everyone out', disabled: !s.passphrase });
      const go = async (fn, done) => {
        save.disabled = true; out.disabled = true;
        try { await fn(); toast(done); await draw(); } catch (e) { toast(e.message); save.disabled = false; out.disabled = !s.passphrase; }
      };
      const doSave = () => {
        const v = input.value.trim();
        if (v.length < 6) { toast('Use at least 6 characters.'); input.focus(); return; }
        go(() => postJSON(`/family/${s.name}/passphrase`, { passphrase: v }), `${s.name}: new passphrase saved - everyone there signs in again`);
      };
      save.addEventListener('click', doSave);
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSave(); });
      out.addEventListener('click', () => {
        if (confirm(`Sign every device out of ${s.base}? They'll need the passphrase again.`)) go(() => postJSON(`/family/${s.name}/signout`), `${s.name}: everyone signed out`);
      });
      const pv = s.provider;
      const provText = !pv ? '' : pv.configured
        ? `Provider: ${pv.type === 'xtream' ? 'Xtream account' : 'playlist link'}${pv.port ? ` (port ${pv.port})` : ''}, set ${pv.source === 'web' ? 'here' : 'on the Pi'} ${ago(pv.changed)}.`
        : 'Provider: not set up yet.';
      const provBtn = h('button', { class: 'btn small ghost', type: 'button', text: pv && pv.configured ? 'Change provider' : 'Set up provider', hidden: !s.up });
      const provForm = providerForm(s, draw);
      provBtn.addEventListener('click', () => { provForm.hidden = !provForm.hidden; if (!provForm.hidden) provForm.querySelector('input').focus(); });
      return h('div', { class: 'family-site' },
        h('div', { class: 'family-head' }, h('b', { text: s.name }), h('a', { href: `${s.base}/`, target: '_blank', rel: 'noopener', text: `${location.host}${s.base}` })),
        h('p', { class: `small ${state.cls === 'warn' ? 'warn' : 'muted'}`, text: state.text }),
        provText ? h('div', { class: 'family-prov' }, h('p', { class: 'muted small', text: provText }), provBtn) : null, provForm,
        h('p', { class: 'muted small', text: s.passphrase ? `Passphrase set ${ago(s.changed)}${s.signed_out > s.changed ? ` · everyone signed out ${ago(s.signed_out)}` : ''}.` : 'No passphrase yet: nobody can open it until you set one.' }),
        h('div', { class: 'family-actions' }, input, save, out));
    });
    box.replaceChildren(h('h2', { text: 'Family sites' }), ...rows,
      h('p', { class: 'muted small', text: 'A new passphrase signs everyone out of that site; tell them the new one. Your own sign-in here is separate.' }));
  };
  draw();
}

// Providers: the main one (set on the Pi) and a backup the player falls back to (tvapp/backups.py).
async function renderProviders(box) {
  const st = (await loadStatus()) || {};
  const b = (st.backups || []).find((x) => x && typeof x === 'object');
  const main = `Main: ${st.provider === 'xtream' ? 'Xtream account' : 'playlist'}${st.configured ? '' : ' (not set up)'} - changed on the Pi (iptv set-xtream).`;
  const line = b ? `${b.label}: ${b.type === 'xtream' ? 'Xtream account' : 'playlist link'} · ${b.channels ? `${b.channels.toLocaleString()} channels ready` : 'loading its channels…'}${b.error ? ` · ${b.error}` : ''}`
    : 'No backup yet.';
  const form = providerForm({ name: 'Backup' }, () => renderProviders(box), (body) => postJSON('/backup', { ...body, label: 'Backup' }));
  const add = h('button', { class: 'btn small', type: 'button', text: b ? 'Change backup' : 'Add a backup provider' });
  add.addEventListener('click', () => { form.hidden = !form.hidden; });
  const rm = b ? h('button', { class: 'btn small ghost', type: 'button', text: 'Remove backup' }) : null;
  if (rm) {
    rm.addEventListener('click', async () => {
      if (!confirm('Remove the backup provider? Channels then play from the main one only.')) return;
      try { await postJSON('/backup', { remove: true }); toast('Backup removed'); renderProviders(box); } catch (e) { toast(e.message); }
    });
  }
  box.replaceChildren(h('h2', { text: 'Providers' }),
    h('p', { class: 'muted small', text: main }),
    h('p', { class: `small ${b && b.error ? 'warn' : ''}`, text: line }),
    h('div', { class: 'family-actions' }, add, rm), form,
    h('p', { class: 'muted small', text: 'A second subscription to fall back on: a channel that won\'t start on the main provider plays from the backup instead, and the Live page offers "Use Backup" to switch by hand (when the main one stutters). The catalogue stays the main provider\'s.' }));
}

// Cast in the player: on/off for this device; on the owner's own site, the TMDB key (kept on the Pi).
async function renderCast(box) {
  let st = { on: false, credit: '' };
  try { st = await (await fetch(`${NEXT}/api/cast/status`, { credentials: 'same-origin' })).json(); } catch { /* no sidecar */ }
  const sel = selectEl('Cast in the player', [['show', 'Show'], ['hide', 'Hide']], castOn() ? 'show' : 'hide', (v) => {
    lsSet(CAST_KEY, v);
    toast('Saved on this device');
  });
  const parts = [h('h2', { text: 'Cast in the player' })];
  if (st.on) {
    parts.push(h('label', { class: 'pref-row' }, h('span', { text: 'Show the cast' }), sel),
      h('p', { class: 'muted small', text: 'Who is in the film or episode - with the episode’s guest stars - when the player’s controls are showing. Only this device changes.' }));
  } else {
    parts.push(h('p', { class: 'muted small', text: FAMILY ? 'Not set up on this TV.' : 'Shows who is in a film or episode in the player, with photos and characters. It needs a free TMDB API key: make an account at themoviedb.org, then Settings › API.' }));
  }
  if (!FAMILY) {
    const input = h('input', { class: 'input', type: 'password', placeholder: st.on ? 'New key (replaces the saved one)' : 'TMDB API key or read access token',
      autocomplete: 'off', spellcheck: 'false', 'data-lpignore': 'true', 'aria-label': 'TMDB API key' });
    const save = h('button', { class: 'btn small primary', type: 'submit', text: 'Check and save' });
    const off = st.on ? h('button', { class: 'btn small ghost', type: 'button', text: 'Remove key' }) : null;
    const msg = h('p', { class: 'small', 'aria-live': 'polite' });
    const send = async (key) => {
      save.disabled = true;
      msg.className = 'small muted';
      msg.textContent = key ? 'Checking with TMDB…' : 'Removing…';
      try {
        await postJSON('/tmdb', { key });
        toast(key ? 'TMDB key saved - cast shows in the player' : 'TMDB key removed');
        renderCast(box);
      } catch (e) { msg.className = 'small warn'; msg.textContent = e.message; save.disabled = false; }
    };
    const form = h('form', { class: 'family-actions', autocomplete: 'off' }, input, save, off);
    form.addEventListener('submit', (e) => { e.preventDefault(); if (input.value.trim()) send(input.value.trim()); });
    if (off) off.addEventListener('click', () => { if (confirm('Remove the TMDB key? The cast stops showing on every TV.')) send(''); });
    parts.push(h('p', { class: 'muted small', text: st.on ? `Key saved on the Pi${st.set ? ` ${ago(st.set)}` : ''}; it’s never shown again. Used for every TV, family sites too.` : 'Kept on the Pi only, and checked with TMDB first.' }), form, msg);
  }
  if (st.credit) parts.push(h('p', { class: 'muted small', text: st.credit }));
  box.replaceChildren(...parts);
}

function renderLayout(box) {
  const startSel = selectEl('Open on', START_PAGES.filter(([k]) => k !== 'sports' || sportsShown()), startPage(), (v) => {
    lsSet(LAYOUT_START, v);
    applyLayout();
    toast('Saved on this device');
  });
  const sportsSel = selectEl('Sports tab', [['1', 'Show'], ['0', 'Hide']], sportsShown() ? '1' : '0', (v) => {
    lsSet(LAYOUT_SPORTS, v);
    applyLayout();
    renderLayout(box);                                    // "Open on" loses or regains Sports
    toast(v === '0' ? 'Sports tab hidden on this device' : 'Sports tab back on this device');
  });
  box.replaceChildren(h('h2', { text: 'Layout' }),
    h('label', { class: 'pref-row' }, h('span', { text: 'Open on' }), startSel),
    h('label', { class: 'pref-row' }, h('span', { text: 'Sports tab' }), sportsSel),
    h('p', { class: 'muted small', text: 'Only this device changes: a TV or phone that never needs Sports can leave it out, and open straight to the page it’s used for. Search still finds sports channels and programmes.' }));
}

// A family site's provider: an Xtream account (server, username, password) or a playlist link. The site
// checks them with the provider before keeping them; they are never shown again (tvapp/family.py).
function providerForm(s, done, post = (body) => postJSON(`/family/${s.name}/provider`, body)) {
  let kind = 'xtream';
  const field = (label, attrs) => {
    const inp = h('input', { class: 'input', autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false', 'data-lpignore': 'true', 'aria-label': label, ...attrs });
    return [h('label', { class: 'pref-row' }, h('span', { text: label }), inp), inp];
  };
  const [baseRow, base] = field('Server', { type: 'url', placeholder: 'http://example.com:8080', inputmode: 'url' });
  const [userRow, user] = field('Username', { type: 'text' });
  const [passRow, pass] = field('Password', { type: 'password' });
  const [linkRow, link] = field('Playlist link', { type: 'url', placeholder: 'http://…/get.php?username=…', inputmode: 'url' });
  const msg = h('p', { class: 'small', 'aria-live': 'polite' });
  const save = h('button', { class: 'btn small primary', type: 'submit', text: 'Check and save' });
  const paint = () => { for (const r of [baseRow, userRow, passRow]) r.hidden = kind !== 'xtream'; linkRow.hidden = kind !== 'm3u'; };
  const kinds = seg('Provider type', [['xtream', 'Server + login'], ['m3u', 'Playlist link']], kind, (v) => { kind = v; paint(); msg.textContent = ''; });
  const form = h('form', { class: 'prov-form', hidden: true, autocomplete: 'off' }, kinds, baseRow, userRow, passRow, linkRow,
    h('div', { class: 'family-actions' }, save, msg),
    h('p', { class: 'muted small', text: 'Use the details from the provider’s welcome email. They are checked with the provider first, kept only on the Pi for this site, and never shown here again.' }));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    save.disabled = true;
    msg.className = 'small muted';
    msg.textContent = 'Checking with the provider…';
    const body = kind === 'xtream' ? { type: 'xtream', base: base.value, username: user.value, password: pass.value } : { type: 'm3u', url: link.value };
    try {
      const d = await post(body);
      for (const i of [base, user, pass, link]) i.value = '';
      const exp = d.check && d.check.expires ? ` The account runs until ${fmtDate(d.check.expires, { day: 'numeric', month: 'short', year: 'numeric' })}.` : '';
      toast(`${s.name}: provider accepted`);
      msg.className = 'small';
      msg.textContent = `Accepted.${exp} Channels, films and series load in the next minute or two.`;
      setTimeout(done, 4000);
    } catch (err) {
      msg.className = 'small warn';
      msg.textContent = err.message;
    } finally {
      save.disabled = false;
    }
  });
  paint();
  return form;
}

// Times: the Pi's zone (the guide's home) or this device's own. Per device: a laptop abroad can show
// local times while the TV at home keeps the Pi's.
const zoneName = (z) => (z ? (z.split('/').pop() || z).replace(/_/g, ' ') : '');
function renderTimes(box) {
  const pi = piTimeZone();
  const dev = deviceTimeZone();
  const now = Date.now() / 1000;
  const sample = (m) => {
    const was = timeMode();
    setTimeMode(m);
    const t = fmtClock(now);
    setTimeMode(was);
    return t;
  };
  const opts = [['pi', pi ? `${zoneName(pi)} (the Pi)` : 'The Pi’s zone'], ['device', `This device${dev ? ` (${zoneName(dev)})` : ''}`]];
  const note = h('p', { class: 'muted small' });
  const paintNote = () => {
    const same = sample('pi') === sample('device');
    note.textContent = `Guide times, kick-offs and dates use this. Right now: ${sample('pi')} ${pi ? zoneName(pi) : 'on the Pi'}`
      + (same ? ', the same here.' : `, ${sample('device')} by this device’s clock${dev === 'UTC' || dev === 'Etc/UTC' ? ' (it reports UTC: privacy settings or a VPN often do that)' : ''}.`)
      + ' Only this device changes.';
  };
  paintNote();
  box.replaceChildren(h('h2', { text: 'Times' }),
    h('label', { class: 'pref-row' }, h('span', { text: 'Show times in' }),
      selectEl('Show times in', opts, timeMode(), (v) => { setTimeMode(v); sportsCache.clear(); paintNote(); toast('Saved on this device'); })),
    note);
}

// Synced preferences (every device follows them); the player's CC / audio menus override them
// per film or series. Rules: web/static/js/tracks.js and tvapp/tracks.py.
function renderTrackPrefs(box) {
  const get = (k) => store.prefs.get(k, tracks.DEFAULTS[k]);
  const set = (k, v) => { store.prefs.set(k, v); toast('Saved - applies from the next title you play'); };
  const langInput = (key, placeholder, label) => {
    const inp = h('input', { class: 'input', type: 'text', value: get(key), placeholder, 'aria-label': label, autocomplete: 'off', spellcheck: 'false' });
    inp.addEventListener('change', () => {
      const v = tracks.langList(inp.value).join(', ');
      inp.value = v;
      set(key, v);
    });
    return inp;
  };
  const ad = h('input', { type: 'checkbox', checked: !!get('audioAd') });
  ad.addEventListener('change', () => set('audioAd', ad.checked));
  const row = (label, control) => h('label', { class: 'pref-row' }, h('span', { text: label }), control);
  // the catalogue language: one the provider carries (counted from its own labels once the lists are in)
  const want = langWant();
  const langSel = selectEl('Your language', [[want, lang.langName(want)]], want, (v) => {
    store.prefs.set('catLangCode', v);
    toast(`Saved - Films, Series and Search offer “${lang.langName(v)} first” and “${lang.langName(v)} only”`);
  });
  Promise.all(['movies', 'series'].map((k) => catalogue(k).catch(() => null))).then((lists) => {
    const have = lang.catalogueLangs(lists.filter(Boolean), 100);
    if (!have.length || !langSel.isConnected) return;
    if (!have.some(([c]) => c === 'en')) have.push(['en', 0]);
    if (!have.some(([c]) => c === want)) have.push([want, 0]);
    const opts = have.map(([c, n]) => [c, `${lang.langName(c)}${n ? ` · ${n.toLocaleString()} titles` : ''}`])
      .sort((a, b) => (a[0] === 'en' ? -1 : b[0] === 'en' ? 1 : a[1].localeCompare(b[1])));
    langSel.replaceChildren(...opts.map(([v, t]) => h('option', { value: v, text: t })));
    langSel.value = langWant();
  });
  box.replaceChildren(
    h('h2', { text: 'Languages' }),
    row('Your language', langSel),
    row('Descriptions', selectEl('Film and series descriptions', PLOT_PREFS, plotPref(), (v) => { store.prefs.set('plotLang', v); toast('Saved'); })),
    row('Subtitles', selectEl('Subtitles', tracks.SUB_MODES, get('subMode'), (v) => set('subMode', v))),
    row('Subtitle languages', langInput('subLangs', 'en, fr', 'Subtitle languages')),
    row('Hearing-impaired (SDH)', selectEl('SDH subtitles', tracks.SDH_MODES, get('subSdh'), (v) => set('subSdh', v))),
    row('Audio languages', langInput('audioLangs', 'original', 'Audio languages')),
    h('label', { class: 'pref-check' }, ad, h('span', { text: 'Prefer audio description' })),
    h('p', { class: 'muted small', text: 'Your language: the one Films, Series and Search put first (“… first” / “… only”), from the languages your provider’s catalogue is labelled in. ' }),
    h('p', { class: 'muted small', text: 'Descriptions: when a version’s description isn’t in English (a Persian or German catalogue, say), the English version’s is shown, with a link back to the original. Subtitle and audio languages: two-letter codes in order of preference, e.g. "en, fr". Leave audio empty for each title’s original language. A choice made in the player is remembered for that film or series.' }));
}

function syncLine() {
  const s = store.syncStatus;
  if (s.ok === null) return 'Connecting to the Pi…';
  if (s.ok) return `Synced with the Pi ${ago(s.at / 1000)}.`;
  return `Not synced (${s.error})${s.pending ? ` - ${s.pending} change${s.pending === 1 ? '' : 's'} waiting on this device` : ''}. It will retry automatically.`;
}

function renderBackup(box) {
  const line = h('p', { class: store.syncStatus.ok === false ? 'warn small' : 'muted small', text: syncLine() });
  const file = h('input', { type: 'file', accept: '.json,application/json', hidden: true });
  let mode = 'merge';
  const pick = (m) => { mode = m; file.value = ''; file.click(); };
  file.addEventListener('change', async () => {
    const f = file.files && file.files[0];
    if (!f) return;
    if (mode === 'replace' && !confirm('Replace everything saved on the Pi (favourites, progress, history, preferences) with this file? Every device will follow.')) return;
    try {
      const r = await store.importState(await f.text(), mode);
      toast(mode === 'replace' ? `Restored ${r.applied} items` : `Imported: ${r.applied} new or newer item${r.applied === 1 ? '' : 's'}`);
      render(true);
    } catch (e) { toast(e.message); }
  });
  const exportBtn = h('button', { class: 'btn small', type: 'button' }, icon('download'), 'Export backup');
  exportBtn.addEventListener('click', async () => {
    exportBtn.disabled = true;
    await store.sync();                      // include changes made here a moment ago
    const a = h('a', { href: store.EXPORT_URL, download: '' });
    document.body.append(a);
    a.click();
    a.remove();
    exportBtn.disabled = false;
  });
  box.replaceChildren(
    h('h2', { text: 'Sync & backup' }),
    h('p', { class: 'small muted', text: 'Favourites, progress, recently played, last channel, preferences and hidden channels/categories live on the Pi and are shared by all your devices.' }),
    line,
    h('div', { class: 'actions' }, exportBtn,
      h('button', { class: 'btn small', type: 'button', text: 'Import (merge)…', onclick: () => pick('merge') }),
      h('button', { class: 'btn ghost small', type: 'button', text: 'Restore (replace)…', onclick: () => pick('replace') }), file),
    h('p', { class: 'muted small', text: 'Readable JSON with no provider details. Merge keeps whichever copy of each item is newer; replace makes the file the whole saved state.' }));
  if (store.syncStatus.ok === null) store.sync().then(() => { if (box.isConnected) line.textContent = syncLine(); });
}

async function loadStatus() {
  try { state.status = await api('/status', { timeout: 10000 }); } catch { /* offline */ }
  if (state.status && setPiTimeZone(state.status.tz)) { sportsCache.clear(); render(true); }
  renderNet();
  return state.status;
}

function ago(ts) {
  if (!ts) return 'never';
  const s = Date.now() / 1000 - ts;
  if (s < 90) return 'just now';
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 129600) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function compact(n) {
  return n >= 10000 ? `${Math.round(n / 1000)}k` : n.toLocaleString();
}

function renderNet() {
  const box = $('net');
  const st = state.status;
  if (!st) { box.replaceChildren(); return; }
  const c = st.counts;
  box.title = `${c.live.toLocaleString()} channels · ${c.movies.toLocaleString()} films · ${c.series.toLocaleString()} series`;
  box.replaceChildren(h('span', { class: `dot ${st.error ? 'bad' : st.refreshing ? 'busy' : ''}`, 'aria-hidden': 'true' }),
    h('span', { text: st.refreshing ? 'refreshing' : st.error ? 'provider problem' : `${compact(c.live)} ch · ${compact(c.movies)} films` }));
}

function renderStatus(box) {
  const draw = () => {
    const st = state.status;
    if (!st) { box.replaceChildren(h('h2', { text: 'Status' }), h('p', { class: 'muted', text: 'Status unavailable.' })); return; }
    const c = st.counts;
    const dl = h('dl', { class: 'kv' },
      h('dt', { text: 'Provider' }), h('dd', { text: `${st.provider === 'xtream' ? 'Xtream Codes' : 'M3U playlist'}${st.configured ? '' : ' (not configured)'}` }),
      h('dt', { text: 'Catalogue' }), h('dd', { text: `${c.live.toLocaleString()} channels · ${c.movies.toLocaleString()} films · ${c.series.toLocaleString()} series` }),
      h('dt', { text: 'Updated' }), h('dd', { text: st.refreshing ? 'refreshing now…' : ago(st.updated) }),
      h('dt', { text: 'Guide' }), h('dd', { text: st.epg.channels ? `${st.epg.channels.toLocaleString()} channels, ${ago(st.epg.updated)}` : (st.epg.error || 'none') }),
      h('dt', { text: 'Streams' }), h('dd', { text: `${st.jobs.length} active (limit ${st.limits.live} live / ${st.limits.vod} remux)` }),
      st.refresh && st.refresh.last_ok ? h('dt', { text: 'Last change' }) : null,
      st.refresh && st.refresh.last_ok ? h('dd', { text: `${st.refresh.last_ok.changes} (${ago(st.refresh.last_ok.t)})` }) : null,
      st.health ? h('dt', { text: 'Health' }) : null,
      st.health ? h('dd', { text: st.health.ok ? 'OK' : st.health.problems.join('; ') }) : null,
      st.state ? h('dt', { text: 'Saved' }) : null,
      st.state ? h('dd', { text: `${st.state.favourites} favourites, ${st.state.progress} in progress, ${st.state.recent} recent` }) : null);
    const btn = h('button', { class: 'btn small', type: 'button' }, icon('refresh'), 'Refresh catalogue');
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const r = await api('/refresh');
        toast(r.started ? 'Refreshing catalogue…' : r.message);
        if (r.started) pollRefresh(draw);
      } catch (e) { toast(e.message); }
    });
    box.replaceChildren(...[h('h2', { text: 'Status' }), dl,
      st.error ? h('p', { class: 'warn small', text: st.error }) : null,
      st.epg.error && st.epg.error !== 'no EPG URL configured' ? h('p', { class: 'warn small', text: `Guide: ${st.epg.error}` }) : null,
      h('div', { class: 'actions' }, btn), h('p', { class: 'muted small', text: 'Provider settings are changed over SSH with the iptv command.' })].filter(Boolean));
  };
  draw();
  loadStatus().then(draw);
}

// Interface: this one or the classic one, per device (the tv_ui cookie, read by the app when it
// serves /tv/); devices that haven't chosen get the Pi's default (`iptv ui new|classic`).
function uiChoice() {
  const m = document.cookie.match(/(?:^|;\s*)tv_ui=(new|classic)/);
  return m ? m[1] : '';
}
function renderInterface(box) {
  if (FAMILY) {                              // a family site: sign this device out
    const out = h('button', { class: 'btn small', type: 'button', text: 'Sign out of this device' });
    out.addEventListener('click', async () => {
      if (!confirm('Sign out of this TV site on this device? You will need the passphrase again.')) return;
      try { await postJSON('/logout'); } catch { /* signed out already */ }
      location.reload();
    });
    box.replaceChildren(h('h2', { text: 'This device' }),
      h('p', { class: 'muted small', text: 'Signed in with the passphrase. It stays signed in for 30 days at a time.' }), out);
    return;
  }
  const preview = !location.pathname.startsWith('/tv/');
  const head = h('h2', { text: 'Interface' });
  if (preview) {
    box.replaceChildren(head, h('p', { class: 'muted small', text: 'Once the new interface is installed at /tv, each device chooses here between it and the classic one (Automatic follows the Pi’s default). In this preview there is nothing to choose yet. Both share favourites, progress and settings.' }));
    return;
  }
  const draw = () => {
    const ui = (state.status && state.status.ui) || { new: true, default: 'classic' };
    const name = (k) => (k === 'new' ? 'New' : 'Classic');
    const set = (v) => {
      const tail = `; Path=/tv/; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`;
      document.cookie = v ? `tv_ui=${v}; Max-Age=34560000${tail}` : `tv_ui=; Max-Age=0${tail}`;
      location.reload();
    };
    box.replaceChildren(head,
      seg('Interface', [['', `Automatic (${name(ui.default)})`], ['new', 'New'], ['classic', 'Classic']], uiChoice(), set),
      h('p', { class: 'muted small', text: 'On this device. Both interfaces share favourites, progress and settings; Automatic follows the Pi’s choice.' }));
  };
  draw();
  loadStatus().then(draw);
}

// Sports artwork: coverage and the crests / logos the Sports view has had to draw generated
// (the Pi's gap registry; the full report is `iptv artwork missing` over SSH)
function renderArtwork(box) {
  const OPEN_KEY = `${LSK}artOpen`;                     // collapsed unless this device opened it
  let open = false;
  try { open = localStorage.getItem(OPEN_KEY) === '1'; } catch { /* private mode */ }
  let pick = 'seen';
  let shownN = 5;                                         // the first 5, then 25 more at a time
  let gaps = [];
  const list = h('ol', { class: 'gap-list' });
  const more = h('button', { class: 'btn ghost small', type: 'button', hidden: true });
  const sum = h('p', { class: 'muted small', text: 'Loading…' });
  const toggle = h('button', { class: 'btn ghost small art-toggle', type: 'button', 'aria-expanded': 'false' }, h('span'), icon('chev-down'));
  const body = h('div', { class: 'art-body' },
    seg('Artwork gaps', [['seen', 'Most seen'], ['recent', 'Recent'], ['resolved', 'Resolved']], pick, (v) => { pick = v; shownN = 5; draw(); }), list, more,
    h('p', { class: 'muted small', text: 'Generated crests and marks drawn for want of verified artwork. Add one yourself with Add crest: pick an image, or paste the link to one (on Wikipedia: open the crest, then copy the image address). It is kept on the Pi and used on every TV.' }));
  const paintOpen = () => {
    body.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.firstChild.textContent = open ? 'Hide gaps' : 'Show gaps';
  };
  toggle.addEventListener('click', () => {
    open = !open;
    try { localStorage.setItem(OPEN_KEY, open ? '1' : '0'); } catch { /* private mode */ }
    paintOpen();
  });
  const paintRows = () => {
    const shown = gaps.slice(0, shownN);
    const rows = shown.map((g) => {
      const what = g.type === 'competition' ? 'logo' : 'crest';
      const add = g.status === 'open' && !FAMILY ? h('button', { class: 'btn ghost small gap-add', type: 'button', text: `Add ${what}` }) : null;
      const li = h('li', { class: 'gap' },
        h('span', { class: 'gap-n', text: `${g.count}×` }),
        h('span', { class: 'gap-what' }, h('span', {}, h('b', { text: g.name }), h('span', { class: 'muted', text: ` ${g.type === 'competition' ? 'logo' : g.type === 'unlisted team' ? 'unlisted team' : 'crest'} · ${ago(Date.parse(g.last_seen) / 1000)}` })),
          h('span', { class: 'gap-why', text: g.status === 'resolved' ? `Resolved: ${g.resolved_by}` : g.reason }), add));
      if (add) add.addEventListener('click', () => { add.replaceWith(artworkForm(g, what, () => { toast(`${g.name}: ${what} added`); draw(); })); });
      return li;
    });
    list.replaceChildren(...(rows.length ? rows : [h('li', { class: 'muted small', text: pick === 'resolved' ? 'Nothing resolved yet.' : 'No gaps recorded: every crest and logo shown so far was real.' })]));
    const rest = gaps.length - shown.length;
    more.hidden = rest <= 0;
    more.textContent = `Show ${Math.min(rest, 25)} more`;
  };
  more.addEventListener('click', () => { shownN += 25; paintRows(); });
  const draw = async () => {
    const q = pick === 'resolved' ? 'state=resolved&sort=recent' : `state=open&sort=${pick}`;
    try {
      const r = await fetch(`${NEXT}/api/art/gaps?${q}`, { credentials: 'same-origin' });
      if (!r.ok) throw new Error(String(r.status));
      const d = await r.json();
      const c = d.coverage;
      sum.textContent = `Crests ${c.teams.cached}/${c.teams.of} · logos ${c.competitions.cached}/${c.competitions.of} · ${d.gaps_open} open gap${d.gaps_open === 1 ? '' : 's'}, ${d.gaps_resolved} resolved`;
      gaps = d.gaps || [];
      toggle.hidden = false;
      paintRows();
    } catch {
      sum.textContent = 'Artwork service unavailable.';
      gaps = [];
      toggle.hidden = true;
      body.hidden = true;
      list.replaceChildren();
      return;
    }
    paintOpen();
  };
  box.replaceChildren(h('h2', { text: 'Artwork' }), h('div', { class: 'art-sum' }, sum, toggle), body);
  paintOpen();
  draw();
}

// Add a crest / logo by hand (the owner's own site): an image from this device - shrunk here to a small
// PNG / WebP, SVG included - or the link to one, which the Pi fetches (tvnext: /api/art/manual).
async function shrinkImage(file) {
  const src = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = src;
    await img.decode();
    const w0 = img.naturalWidth || 512;
    const h0 = img.naturalHeight || 512;
    for (const max of [256, 192, 128]) {
      const k = Math.min(1, max / Math.max(w0, h0));
      const c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(w0 * k));
      c.height = Math.max(1, Math.round(h0 * k));
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      for (const type of ['image/webp', 'image/png']) {
        const b = await new Promise((r) => c.toBlob(r, type, 0.92));
        if (b && b.type === type && b.size < 60000) return b;
      }
    }
  } finally { URL.revokeObjectURL(src); }
  throw new Error('That image is too detailed to send, even shrunk. Try another.');
}

function artworkForm(g, what, done) {
  const file = h('input', { type: 'file', accept: 'image/*', hidden: true });
  const choose = h('button', { class: 'btn small', type: 'button', text: 'Choose image' });
  const url = h('input', { class: 'input', type: 'url', placeholder: 'or paste a link to the image', autocomplete: 'off', 'aria-label': `Link to a ${what} for ${g.name}` });
  const save = h('button', { class: 'btn small primary', type: 'button', text: 'Save' });
  const msg = h('span', { class: 'small muted', 'aria-live': 'polite' });
  const send = async (body, type) => {
    msg.className = 'small muted';
    msg.textContent = 'Saving…';
    save.disabled = true;
    try {
      const res = await fetch(`${NEXT}/api/art/manual?${new URLSearchParams({ id: g.id, name: g.name })}`, {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': type }, body });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(d.error || `Not saved (HTTP ${res.status})`);
      artAsked.delete(d.id);                          // the Sports page asks again and draws it
      done();
    } catch (e) { msg.className = 'small warn'; msg.textContent = e.message; save.disabled = false; }
  };
  choose.addEventListener('click', () => file.click());
  file.addEventListener('change', async () => {
    const f = file.files && file.files[0];
    if (!f) return;
    try { const b = await shrinkImage(f); await send(b, b.type); } catch (e) { msg.className = 'small warn'; msg.textContent = e.message; }
  });
  save.addEventListener('click', () => { if (url.value.trim()) send(JSON.stringify({ url: url.value.trim() }), 'application/json'); else url.focus(); });
  url.addEventListener('keydown', (e) => { if (e.key === 'Enter') save.click(); });
  return h('span', { class: 'gap-form' }, choose, url, save, file, msg);
}

async function pollRefresh(after) {
  const before = state.status ? state.status.version : '';
  for (let i = 0; i < 90; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const st = await loadStatus();
    if (after) after();
    if (st && !st.refreshing && !st.epg.refreshing) {
      if (st.version !== before) { dropCatalogue(); toast('Catalogue updated'); }
      return;
    }
  }
}

// ------------------------------------------------------------------ keyboard
document.addEventListener('keydown', (e) => {
  if (e.defaultPrevented || e.ctrlKey || e.altKey) return;
  const t = e.target;
  const typing = t && (t.tagName === 'INPUT' && !['range', 'button', 'checkbox'].includes(t.type) || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable);
  if (e.metaKey) {
    if (e.key === 'k' || e.key === 'K') { location.hash = '#/search'; e.preventDefault(); }
    return;
  }
  if (e.key === 'Escape') {
    if (!$('sheet').hidden) { closeSheet(true); e.preventDefault(); return; }
    if (player.mode === 'vod' && !document.fullscreenElement) { player.close(); e.preventDefault(); }
    return;
  }
  if (typing) return;
  // a remote's left / right along a row of cards (Library, rails): the neighbouring card, scrolled to
  if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && t && t.parentElement && t.parentElement.classList.contains('shelf')) {
    const next = e.key === 'ArrowRight' ? t.nextElementSibling : t.previousElementSibling;
    if (next && next.tabIndex >= 0) {
      next.focus();
      next.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'smooth' });
    }
    e.preventDefault();
    return;
  }
  const live = player.isLive || (player.mode === 'live' && player.idleChannel);
  const active = player.mode !== 'off';
  switch (e.key) {
    case 'ArrowUp': if (live) { stepChannel(1); e.preventDefault(); } break;
    case 'ArrowDown': if (live) { stepChannel(-1); e.preventDefault(); } break;
    case 'PageUp': if (live) { stepChannel(1); e.preventDefault(); } break;
    case 'PageDown': if (live) { stepChannel(-1); e.preventDefault(); } break;
    case 'ArrowLeft': if (active && !player.isLive && player.item) { player.seekTo(player.absTime() - 10); e.preventDefault(); } break;
    case 'ArrowRight': if (active && !player.isLive && player.item) { player.seekTo(player.absTime() + 30); e.preventDefault(); } break;
    case ' ': case 'k': case 'K':
      if (active && !(t && t.tagName === 'BUTTON')) { player.togglePlay(); e.preventDefault(); }
      break;
    case 'f': case 'F': if (active) { player.toggleFullscreen(); e.preventDefault(); } break;
    case 'm': case 'M': if (active) { player.toggleMute(); e.preventDefault(); } break;
    case 'p': case 'P': if (player.item) { player.togglePip(); e.preventDefault(); } break;
    case 'c': case 'C': if (player.item && !player.isLive) { player.toggleMenu('subs'); e.preventDefault(); } break;
    case 'i': case 'I': if (player.item) { player.showDiag(); e.preventDefault(); } break;
    case 'b': case 'B': case 'Backspace': if (live) { lastChannel(); e.preventDefault(); } break;
    case '/': location.hash = '#/search'; e.preventDefault(); break;
    default:
  }
});

// ------------------------------------------------------------------ sync from other devices
store.onChange((changed) => {
  if (changed.has('fav')) for (const b of document.querySelectorAll('.fav-btn[data-fav-id]')) paintFav(b);
  if (changed.has('progress')) refreshProgressBadges();
  if (state.redraw) state.redraw(changed);
  if (changed.has('last') && state.section === 'live' && !player.item) maybeIdle();
  if (['library', 'continue', 'favourites', 'recent'].includes(state.section) && !player.item && $('sheet').hidden) render(true);
});

// ------------------------------------------------------------------ boot
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';     // the router decides where each view starts
let scrolled = false;
window.addEventListener('scroll', () => {
  const now = window.scrollY > 24;
  if (now !== scrolled) { scrolled = now; document.body.classList.toggle('scrolled', now); }
}, { passive: true });
store.startSync();
window.addEventListener('hashchange', route);
applyLayout();
if (!location.hash) history.replaceState(null, '', `#/${startPage()}`);
route();
requestAnimationFrame(moveTabIndicator);
fitLiveColumn();
loadStatus();
setInterval(loadStatus, 120000);
if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
