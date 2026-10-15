// Shuffle for a series: pick one episode at random.
//   pickEpisode(seasons, { season, avoid, rng, filter })
//     seasons: [{n, episodes: [{id, ...}]}]
//     season:  a season number to shuffle within (the viewer chose it), or null for the whole series
//     avoid:   episode ids to skip when there is anything else to pick (playing now, just watched)
//     filter:  optional (season, episode) -> bool for later options (unwatched only);
//              when it leaves nothing, the unfiltered pool is used rather than doing nothing
//     seenAt:  optional episode id -> when it was last watched (ms, 0 = never). Episodes seen within
//              `lately` ms are left out; when every one was, the longest-unseen third is drawn from,
//              so a short show you have just been through doesn't hand back what you saw minutes ago
//   -> { s, ep } or null when there are no episodes at all.
// One press, one episode: a shuffled queue can be built on top of this later.

export function pool(seasons, season = null) {
  const out = [];
  for (const s of seasons || []) {
    if (season != null && s.n !== season) continue;
    for (const ep of s.episodes || []) out.push({ s, ep });
  }
  return out;
}

export function pickEpisode(seasons, { season = null, avoid = [], rng = Math.random, filter = null,
  seenAt = null, lately = 14 * 86400e3, now = Date.now() } = {}) {
  let all = pool(seasons, season);
  if (!all.length && season != null) all = pool(seasons, null);        // an empty season: the whole show
  if (!all.length) return null;
  let cands = filter ? all.filter(({ s, ep }) => filter(s, ep)) : all;
  if (!cands.length) cands = all;
  const skip = new Set(avoid.filter(Boolean));
  const fresh = cands.filter(({ ep }) => !skip.has(ep.id));
  if (fresh.length) cands = fresh;
  if (seenAt && cands.length > 1) {
    const at = ({ ep }) => seenAt(ep.id) || 0;
    const unseen = cands.filter((c) => now - at(c) > lately);
    cands = unseen.length ? unseen : cands.slice().sort((a, b) => at(a) - at(b)).slice(0, Math.max(1, Math.ceil(cands.length / 3)));
  }
  return cands[Math.min(cands.length - 1, Math.floor(rng() * cands.length))];
}
