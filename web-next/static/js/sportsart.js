// Sports artwork without images: the guide has no event pictures and the provider no crests, so
// cards are drawn from facts we do have - the competition, the sport and the teams.
//   compArt(comp_id, sport)  -> { c1, c2, pattern }   colours + a line drawing for the sport
//   crest(team_id, name)     -> { a, b, initials }    a disc in the club's colours with its initials
// Colours are the clubs'/competitions' own (facts, not logos); nothing is fetched. Unknown teams get
// a neutral graphite disc, unknown competitions a palette chosen from the sport.

const T = {
  arsenal: ['#EF0107', '#FFFFFF'], 'aston-villa': ['#670E36', '#95BFE5'], 'afc-bournemouth': ['#DA291C', '#111111'], brentford: ['#E30613', '#FFFFFF'],
  'brighton-hove-albion': ['#0057B8', '#FFFFFF'], burnley: ['#6C1D45', '#99D6EA'], chelsea: ['#034694', '#FFFFFF'], 'crystal-palace': ['#1B458F', '#C4122E'],
  everton: ['#003399', '#FFFFFF'], fulham: ['#F2F2F2', '#111111'], 'leeds-united': ['#F2F2F2', '#1D428A'], liverpool: ['#C8102E', '#FFFFFF'],
  'manchester-city': ['#6CABDD', '#1C2C5B'], 'manchester-united': ['#DA291C', '#FBE122'], 'newcastle-united': ['#241F20', '#FFFFFF'],
  'nottingham-forest': ['#DD0000', '#FFFFFF'], sunderland: ['#EB172B', '#FFFFFF'], 'tottenham-hotspur': ['#F2F2F2', '#132257'],
  'west-ham-united': ['#7A263A', '#1BB1E7'], 'wolverhampton-wanderers': ['#FDB913', '#231F20'], 'leicester-city': ['#003090', '#FDBE11'],
  southampton: ['#D71920', '#FFFFFF'], 'ipswich-town': ['#3A64A3', '#FFFFFF'], 'sheffield-united': ['#EE2737', '#111111'], 'sheffield-wednesday': ['#2B4A9B', '#FFFFFF'],
  'west-bromwich-albion': ['#122F67', '#FFFFFF'], middlesbrough: ['#E11B22', '#FFFFFF'], 'norwich-city': ['#FFF200', '#00A650'], 'coventry-city': ['#59CBE8', '#FFFFFF'],
  watford: ['#FBEE23', '#ED2127'], 'stoke-city': ['#E03A3E', '#FFFFFF'], 'hull-city': ['#F5A12D', '#111111'], 'derby-county': ['#F2F2F2', '#111111'],
  'queens-park-rangers': ['#1D5BA4', '#FFFFFF'], 'birmingham-city': ['#0000C8', '#FFFFFF'], wrexham: ['#E4002B', '#FFFFFF'], celtic: ['#018749', '#FFFFFF'],
  rangers: ['#1B458F', '#FFFFFF'], aberdeen: ['#E2001A', '#FFFFFF'], 'heart-of-midlothian': ['#8B0D24', '#FFFFFF'],
  'real-madrid': ['#F2F2F2', '#FEBE10'], barcelona: ['#A50044', '#004D98'], 'atletico-madrid': ['#CB3524', '#272E61'], 'athletic-club': ['#EE2523', '#FFFFFF'],
  'real-sociedad': ['#0067B1', '#FFFFFF'], 'real-betis': ['#0BB363', '#FFFFFF'], sevilla: ['#F2F2F2', '#D71920'], 'valencia-cf': ['#F2F2F2', '#EE8707'],
  villarreal: ['#FFE667', '#005187'], 'celta-vigo': ['#8AC3EE', '#FFFFFF'], girona: ['#CD2534', '#FFFFFF'], osasuna: ['#D91A21', '#0A346F'], getafe: ['#005999', '#FFFFFF'],
  'rayo-vallecano': ['#F2F2F2', '#E53027'], mallorca: ['#E20613', '#111111'], espanyol: ['#007FC8', '#FFFFFF'],
  juventus: ['#111111', '#FFFFFF'], 'inter-milan': ['#0068A8', '#111111'], 'ac-milan': ['#FB090B', '#111111'], napoli: ['#12A0D7', '#FFFFFF'], 'as-roma': ['#8E1F2F', '#F0BC42'],
  lazio: ['#87D8F7', '#FFFFFF'], atalanta: ['#1E71B8', '#111111'], fiorentina: ['#482E92', '#FFFFFF'], bologna: ['#1A2F48', '#A21C26'], torino: ['#8A1E03', '#FFFFFF'],
  como: ['#003DA5', '#FFFFFF'], venezia: ['#111111', '#F27B26'], udinese: ['#111111', '#FFFFFF'], cagliari: ['#A50F2E', '#002350'], genoa: ['#A6192E', '#002D72'],
  sassuolo: ['#00A752', '#111111'], parma: ['#FFD200', '#0B3EA2'], lecce: ['#FFE600', '#D50000'], monza: ['#E30613', '#FFFFFF'],
  'bayern-munich': ['#DC052D', '#FFFFFF'], 'borussia-dortmund': ['#FDE100', '#111111'], 'bayer-leverkusen': ['#E32221', '#111111'], 'rb-leipzig': ['#DD0741', '#FFFFFF'],
  'eintracht-frankfurt': ['#E1000F', '#111111'], 'vfb-stuttgart': ['#F2F2F2', '#E32219'], 'borussia-monchengladbach': ['#00A04F', '#FFFFFF'],
  'vfl-wolfsburg': ['#65B32E', '#FFFFFF'], 'sc-freiburg': ['#E1001A', '#FFFFFF'], 'werder-bremen': ['#1D9053', '#FFFFFF'], 'union-berlin': ['#EB1923', '#FFFFFF'],
  'hamburger-sv': ['#0A3F86', '#FFFFFF'], 'paris-saint-germain': ['#004170', '#DA291C'], marseille: ['#2FAEE0', '#FFFFFF'], lyon: ['#F2F2F2', '#14387F'],
  'as-monaco': ['#E51B22', '#FFFFFF'], lille: ['#E01E13', '#24215B'], 'ogc-nice': ['#C4161C', '#111111'], 'rc-lens': ['#FFD100', '#E30613'], 'stade-rennais': ['#E13327', '#111111'],
  benfica: ['#E83030', '#FFFFFF'], 'fc-porto': ['#00428C', '#FFFFFF'], 'sporting-cp': ['#008057', '#FFFFFF'], 'sc-braga': ['#E30613', '#FFFFFF'], ajax: ['#F2F2F2', '#D2122E'],
  'psv-eindhoven': ['#ED1C24', '#FFFFFF'], feyenoord: ['#E30613', '#FFFFFF'], 'az-alkmaar': ['#DB0021', '#FFFFFF'], galatasaray: ['#A90432', '#FDB912'],
  fenerbahce: ['#00205B', '#FFED00'], besiktas: ['#111111', '#FFFFFF'], trabzonspor: ['#8B1B37', '#43B2E3'], 'club-brugge': ['#0067CE', '#111111'],
  anderlecht: ['#4C2683', '#FFFFFF'], 'red-bull-salzburg': ['#ED1C24', '#FFFFFF'], 'shakhtar-donetsk': ['#F26522', '#111111'], 'dinamo-zagreb': ['#0055A4', '#FFFFFF'],
  'red-star-belgrade': ['#E30613', '#FFFFFF'], olympiacos: ['#E30613', '#FFFFFF'], panathinaikos: ['#00843D', '#FFFFFF'], 'al-hilal': ['#005BAC', '#FFFFFF'],
  'al-nassr': ['#FFD700', '#003DA5'], 'al-ittihad': ['#FFDD00', '#111111'], 'al-ahli-saudi': ['#007A33', '#FFFFFF'], 'inter-miami': ['#F7B5CD', '#231F20'],
  'la-galaxy': ['#00245D', '#FFD200'], flamengo: ['#E30613', '#111111'], palmeiras: ['#006437', '#FFFFFF'], corinthians: ['#F2F2F2', '#111111'],
  'boca-juniors': ['#00337F', '#FFD100'], 'river-plate': ['#F2F2F2', '#E30613'], 'club-america': ['#FFE600', '#002855'],
  england: ['#F2F2F2', '#CE1124'], scotland: ['#0065BF', '#FFFFFF'], wales: ['#C8102E', '#00B140'], 'northern-ireland': ['#00A04A', '#FFFFFF'],
  'republic-of-ireland': ['#169B62', '#FFFFFF'], france: ['#0055A4', '#EF4135'], germany: ['#F2F2F2', '#111111'], spain: ['#AA151B', '#F1BF00'],
  italy: ['#0066CC', '#FFFFFF'], portugal: ['#E42518', '#046A38'], netherlands: ['#F36C21', '#FFFFFF'], belgium: ['#E30613', '#111111'], brazil: ['#FEDD00', '#009C3B'],
  argentina: ['#75AADB', '#FFFFFF'], 'united-states': ['#0A3161', '#B31942'], mexico: ['#006847', '#CE1126'], croatia: ['#E30613', '#FFFFFF'], denmark: ['#C8102E', '#FFFFFF'],
  sweden: ['#FECC02', '#006AA7'], norway: ['#BA0C2F', '#00205B'], poland: ['#F2F2F2', '#DC143C'], turkey: ['#E30A17', '#FFFFFF'], switzerland: ['#FF0000', '#FFFFFF'],
  austria: ['#ED2939', '#FFFFFF'], morocco: ['#C1272D', '#006233'], japan: ['#000555', '#FFFFFF'], 'south-korea': ['#CD2E3A', '#FFFFFF'], australia: ['#FFCD00', '#00843D'],
  uruguay: ['#5CBFEB', '#FFFFFF'], colombia: ['#FCD116', '#003893'], 'saudi-arabia': ['#006C35', '#FFFFFF'], egypt: ['#CE1126', '#FFFFFF'], nigeria: ['#008751', '#FFFFFF'],
  senegal: ['#00853F', '#FDEF42'], india: ['#1C3F94', '#FF9933'], pakistan: ['#01411C', '#FFFFFF'], 'south-africa': ['#007749', '#FFB612'], 'new-zealand': ['#111111', '#FFFFFF'],
  'west-indies': ['#7B0041', '#FFC72C'], 'sri-lanka': ['#0F2C6A', '#FFBE29'], bangladesh: ['#006A4E', '#F42A41'], afghanistan: ['#0066B3', '#D32011'],
  zimbabwe: ['#FCE300', '#D40000'], finland: ['#F2F2F2', '#002F6C'], iceland: ['#02529C', '#DC1E35'], greece: ['#0D5EAF', '#FFFFFF'], serbia: ['#C6363C', '#0C4076'],
  czechia: ['#D7141A', '#11457E'], hungary: ['#CD2A3E', '#436F4D'], romania: ['#FCD116', '#002B7F'], ukraine: ['#FFD500', '#005BBB'], slovakia: ['#F2F2F2', '#0B4EA2'],
  slovenia: ['#F2F2F2', '#005DA4'], albania: ['#E41E20', '#111111'], 'bosnia-and-herzegovina': ['#002395', '#FECB00'], 'north-macedonia': ['#D20000', '#FFE600'],
  montenegro: ['#C40308', '#D3AE3B'], israel: ['#F2F2F2', '#0038B8'], canada: ['#D80621', '#FFFFFF'], chile: ['#D52B1E', '#0039A6'], peru: ['#F2F2F2', '#D91023'],
  ecuador: ['#FFDD00', '#034EA2'], paraguay: ['#D52B1E', '#0038A8'], iran: ['#F2F2F2', '#DA0000'], qatar: ['#8A1538', '#FFFFFF'], ghana: ['#F2F2F2', '#006B3F'],
  cameroon: ['#007A5E', '#CE1126'], 'ivory-coast': ['#F77F00', '#009E60'], algeria: ['#F2F2F2', '#006233'], tunisia: ['#E70013', '#FFFFFF'],
};

// [deep base, accent]
const C = {
  'premier-league': ['#2A0230', '#00FF85'], 'uefa-champions-league': ['#071436', '#9DB4FF'], 'uefa-womens-champions-league': ['#071436', '#9DB4FF'],
  'uefa-europa-league': ['#1A1205', '#F68E00'], 'uefa-conference-league': ['#04231A', '#00BE14'], 'uefa-youth-league': ['#071436', '#9DB4FF'],
  laliga: ['#2A0808', '#FF4B44'], 'laliga-hypermotion': ['#2A0808', '#FF4B44'], 'serie-a': ['#06172F', '#3DD6F5'], bundesliga: ['#2A0204', '#E2031A'],
  '2-bundesliga': ['#2A0204', '#E2031A'], 'ligue-1': ['#07162F', '#DAE025'], 'ligue-2': ['#07162F', '#DAE025'], eredivisie: ['#2A1304', '#FF6B00'],
  'primeira-liga': ['#04201A', '#2BD4A4'], 'scottish-premiership': ['#121A3A', '#6CC4F0'], 'super-lig': ['#2A0606', '#E30A17'],
  'saudi-pro-league': ['#05221A', '#3BD77E'], 'major-league-soccer': ['#0B1626', '#E21F26'], 'liga-mx': ['#1B0A24', '#C6FF00'], brasileirao: ['#04220F', '#FFDF00'],
  'efl-championship': ['#0A1A33', '#00A3E0'], 'efl-league-one': ['#0A1A33', '#00A3E0'], 'efl-league-two': ['#0A1A33', '#00A3E0'], 'fa-cup': ['#16130C', '#E8C25A'],
  'efl-cup': ['#0A1A2E', '#00C3E0'], 'copa-del-rey': ['#2A0808', '#F1BF00'], 'coppa-italia': ['#06172F', '#2FB86B'], 'dfb-pokal': ['#151515', '#D9B44A'],
  'coupe-de-france': ['#07162F', '#E1000F'], 'fifa-world-cup': ['#2A0A12', '#C8A15A'], 'fifa-club-world-cup': ['#11122A', '#C8A15A'],
  'world-cup-qualifiers': ['#16121F', '#C8A15A'], 'uefa-nations-league': ['#0E1838', '#7FB3FF'], 'uefa-euro': ['#081A4A', '#E30613'],
  'copa-libertadores': ['#1A1505', '#E8C25A'], 'copa-sudamericana': ['#0A1A33', '#E8C25A'], 'afc-champions-league': ['#0A1A33', '#3DD6F5'],
  'caf-champions-league': ['#1F1605', '#E8C25A'], 'womens-super-league': ['#1A0A2A', '#B38BFF'], 'jupiler-pro-league': ['#0A1A2E', '#E30613'],
  'scottish-cup': ['#121A3A', '#6CC4F0'], nba: ['#1A0E02', '#F58426'], wnba: ['#1A0E02', '#F58426'], euroleague: ['#1A0E02', '#FF7A00'], nfl: ['#0A1626', '#D50A0A'],
  'indian-premier-league': ['#0F1238', '#FF9933'], 't20-world-cup': ['#1A0F24', '#FF2E9A'], 'the-ashes': ['#0E1E12', '#E8E2C8'], 'the-hundred': ['#0B0B0B', '#FF4FD8'],
  'six-nations': ['#081A2E', '#7FC4FF'], 'rugby-world-cup': ['#1A1205', '#E8C25A'], 'formula-1': ['#1A0202', '#E10600'], ufc: ['#0A0A0A', '#D20A0A'],
  wimbledon: ['#0A1F0E', '#B9A6FF'], 'roland-garros': ['#2A1206', '#E07A3B'], 'australian-open': ['#04203A', '#38B6FF'], 'atp-finals': ['#0A0F1F', '#3DD6F5'],
};
const SPORT = {
  football: ['#0B1A12', '#5EE08F'], f1: ['#1A0202', '#E10600'], mma: ['#0A0A0A', '#D20A0A'], boxing: ['#1A1205', '#D4AF37'], basketball: ['#1A0E02', '#F58426'],
  nfl: ['#0A1626', '#D50A0A'], tennis: ['#08240F', '#C7F000'], cricket: ['#0E1E12', '#E8E2C8'], rugby: ['#0A2410', '#7FC4FF'], hockey: ['#061A2A', '#9BD3FF'],
};

const svg = (body) => `url("data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 240' preserveAspectRatio='xMidYMid slice'><g fill='none' stroke='white' stroke-width='1.2' stroke-opacity='.32'>${body}</g></svg>`)}")`;
const PATTERN = {
  football: svg("<rect x='20' y='20' width='360' height='200'/><line x1='200' y1='20' x2='200' y2='220'/><circle cx='200' cy='120' r='36'/><rect x='20' y='70' width='54' height='100'/><rect x='326' y='70' width='54' height='100'/><rect x='20' y='98' width='20' height='44'/><rect x='360' y='98' width='20' height='44'/><path d='M74 100 a26 26 0 0 1 0 40 M326 100 a26 26 0 0 0 0 40'/>"),
  f1: svg("<path d='M-20 180 L420 60 M-20 200 L420 80 M-20 220 L420 100 M-20 140 L420 20' stroke-dasharray='60 18'/><path d='M40 240 C120 120 220 200 400 40'/>"),
  mma: svg("<path d='M141 20 H259 L342 103 V137 L259 220 H141 L58 137 V103 Z'/><path d='M154 42 H246 L320 116 V124 L246 198 H154 L80 124 V116 Z' opacity='.5'/>"),
  boxing: svg("<rect x='40' y='30' width='320' height='180'/><line x1='40' y1='70' x2='360' y2='70'/><line x1='40' y1='110' x2='360' y2='110'/><line x1='40' y1='150' x2='360' y2='150'/>"),
  basketball: svg("<rect x='20' y='20' width='360' height='200'/><line x1='200' y1='20' x2='200' y2='220'/><circle cx='200' cy='120' r='30'/><rect x='20' y='90' width='70' height='60'/><rect x='310' y='90' width='70' height='60'/><path d='M20 40 h40 a90 90 0 0 1 0 160 h-40 M380 40 h-40 a90 90 0 0 0 0 160 h40'/>"),
  nfl: svg("<rect x='20' y='20' width='360' height='200'/><path d='M50 20 V220 M80 20 V220 M110 20 V220 M140 20 V220 M170 20 V220 M200 20 V220 M230 20 V220 M260 20 V220 M290 20 V220 M320 20 V220 M350 20 V220'/>"),
  tennis: svg("<rect x='40' y='30' width='320' height='180'/><line x1='40' y1='52' x2='360' y2='52'/><line x1='40' y1='188' x2='360' y2='188'/><line x1='120' y1='52' x2='120' y2='188'/><line x1='280' y1='52' x2='280' y2='188'/><line x1='120' y1='120' x2='280' y2='120'/><line x1='200' y1='30' x2='200' y2='210' stroke-width='3'/>"),
  cricket: svg("<ellipse cx='200' cy='120' rx='180' ry='100'/><ellipse cx='200' cy='120' rx='90' ry='50' opacity='.5'/><rect x='186' y='80' width='28' height='80'/><line x1='180' y1='92' x2='220' y2='92'/><line x1='180' y1='148' x2='220' y2='148'/>"),
  rugby: svg("<rect x='20' y='20' width='360' height='200'/><path d='M60 20 V220 M120 20 V220 M200 20 V220 M280 20 V220 M340 20 V220' stroke-dasharray='8 8'/><path d='M30 90 V150 M30 120 H46 M46 70 V120 M370 90 V150 M354 120 H370 M354 70 V120'/>"),
  hockey: svg("<rect x='20' y='20' width='360' height='200' rx='60'/><line x1='200' y1='20' x2='200' y2='220'/><circle cx='200' cy='120' r='30'/><line x1='120' y1='20' x2='120' y2='220'/><line x1='280' y1='20' x2='280' y2='220'/>"),
  other: svg("<path d='M-40 240 L200 0 M0 240 L240 0 M40 240 L280 0 M80 240 L320 0 M120 240 L360 0 M160 240 L400 0 M200 240 L440 0' opacity='.6'/>"),
};
const ALIAS = { mma: 'mma', ufc: 'mma', 'formula-1': 'f1', motorsport: 'f1' };

function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }

export function compArt(compId, sport) {
  const key = String(compId || '').replace(/^comp:/, '');
  const sp = ALIAS[sport] || sport;
  const [c1, c2] = C[key] || SPORT[sp] || SPORT.football;
  return { c1, c2, pattern: PATTERN[sp] || PATTERN.other, known: !!C[key] };
}

const STOP = new Set(['FC', 'CF', 'AFC', 'SC', 'AC', 'AS', 'CD', 'SD', 'RC', 'UD', 'CA', 'SV', 'VFB', 'VFL', 'TSG', 'OGC', 'RB', 'DE', 'LA', 'EL', 'THE', 'CLUB', 'REAL']);
export function initials(name) {
  const words = String(name || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toUpperCase().match(/[\p{L}\p{N}]+/gu) || [];
  const core = words.filter((w) => !STOP.has(w));
  const use = core.length ? core : words;
  if (!use.length) return '·';
  if (use.length === 1) return use[0].slice(0, 3);
  return (use[0][0] + use[1][0] + (use[2] ? use[2][0] : '')).slice(0, 3);
}

export function crest(teamId, name) {
  const key = String(teamId || '').replace(/^team:/, '');
  const c = T[key];
  if (c) return { a: c[0], b: c[1], initials: initials(name), known: true };
  const hue = hash(name || key) % 360;
  return { a: `hsl(${hue} 14% 22%)`, b: `hsl(${hue} 30% 70%)`, initials: initials(name), known: false };
}

// Which team id belongs to which side of "A v B". byName: the Pi's own reading of each side's name
// (exact, per side: '' when unknown or not asked yet); ids: the live app's team ids for the event (its
// order is not guaranteed); fits(id, label): the id's names match that label. A lone id goes only to the
// side it fits - never by position, so "Viking v Bayern Munich" with only Bayern known can't show
// Bayern's crest for Viking.
export function sides(pair, ids, byName, fits) {
  const [x, y] = [ids[0] || '', ids[1] || ''];
  let a = '', b = '';
  if (x && y) {
    [a, b] = fits(y, pair[0]) || fits(x, pair[1]) ? [y, x] : [x, y];
  } else if (x) {
    if (byName[0] === x || fits(x, pair[0])) a = x;
    else if (byName[1] === x || fits(x, pair[1])) b = x;
  }
  return [byName[0] || a, byName[1] || b];
}
