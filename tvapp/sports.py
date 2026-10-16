"""Sports names and events in the guide: aliases, sport detection and match recognition.

Used by the guide index (epgsearch.py) for the Live search and the Sports view. Everything here
is a small maintained dataset plus conservative rules; nothing fuzzy, nothing fetched.

Aliases (DATA below, one entity per line; easy to extend):
- strong names ("Manchester United | Man Utd | Man United") are equivalent everywhere: searching
  one finds the others in titles and descriptions;
- weak names ("Spurs", "Inter", "Villa", "PL") are trusted only as a whole side of a recognised
  match ("Spurs v Arsenal"), or as the label of one ("PL 26/27: Chelsea v B'mouth"); typing a weak
  name that belongs to exactly one entity also searches for that entity;
- "not after" / "not before" words stop an alias where a qualifier makes it something else
  ("Champions League" after AFC, EHF, Global...; "Premier League" after Indian, or before Darts);
- "United", "City", "Real" and the like are never names on their own.

Matches: "A v B", "A vs B", "A x B", "A @ B" (and "A - B" only when both sides are known teams or a
sport label says so: "Nogomet: Como - Roma", "Boks: X - Y"), with a competition/label prefix,
round/date tails and country codes removed. A sport comes from, strongest first: a sport word in
the title (many languages: "Košarka" makes "Barcelona - Valencia" basketball), a competition,
known clubs, the channel. Highlights, magazines, classics, build-up and documentaries are
recognised and kept out of the live-match lists. Unknown teams count only on a sports channel or
with sports evidence: "Kramer vs. Kramer" on a film channel is not a match.
"""
from __future__ import annotations

import re
import unicodedata

# ------------------------------------------------------------------ sports
FOOTBALL, BASKETBALL, F1, MMA, BOXING, NFL, TENNIS, CRICKET, RUGBY, HOCKEY, HANDBALL, VOLLEYBALL, OTHER = range(1, 14)
SPORT_KEYS = {FOOTBALL: "football", BASKETBALL: "basketball", F1: "f1", MMA: "mma", BOXING: "boxing", NFL: "nfl",
              TENNIS: "tennis", CRICKET: "cricket", RUGBY: "rugby", HOCKEY: "hockey", HANDBALL: "handball",
              VOLLEYBALL: "volleyball", OTHER: "other"}
SPORT_LABELS = {FOOTBALL: "Football", BASKETBALL: "Basketball", F1: "Formula 1", MMA: "UFC / MMA", BOXING: "Boxing",
                NFL: "NFL", TENNIS: "Tennis", CRICKET: "Cricket", RUGBY: "Rugby", HOCKEY: "Ice hockey",
                HANDBALL: "Handball", VOLLEYBALL: "Volleyball", OTHER: "Other sport"}
BY_KEY = {v: k for k, v in SPORT_KEYS.items()}

# kinds of sports programme
MATCH, EVENT, SHOW = 1, 2, 3          # a match / a race, fight night or session / highlights, magazine, build-up...

_APOS = re.compile(r"['’`´]")
_NONWORD = re.compile(r"[\W_]+")
_MARKS = re.compile(r"[̀-ͯ]")      # combining accents, as the page's fold() (api.js)


def norm(text: str) -> str:
    """Case, accents, punctuation and spacing don't matter: "Women's Champions-League: Barça"
    -> "womens champions league barca"."""
    text = (text or "").lower()
    if not text.isascii():
        text = _MARKS.sub("", unicodedata.normalize("NFKD", text))
    return _NONWORD.sub(" ", _APOS.sub("", text)).strip()


# ------------------------------------------------------------------ the dataset
# @kind sport   starts a section. Line: id = Name | alias | alias ; weak: a | b ; not after: w w ;
# not before: w w ; priority: N (competitions: how prominent, 0-100) ; was: old-id old-id
# The first name is the one shown. The id ("team:arsenal", "comp:premier-league") is what favourites
# store: never change one. To rename, change the names; to merge two entries, keep one id and list
# the other under "was:" so favourites saved with it still work.
DATA = r"""
@club football
team:arsenal = Arsenal | Άρσεναλ
team:aston-villa = Aston Villa ; weak: Villa | A.Villa
team:afc-bournemouth = AFC Bournemouth | Bournemouth ; weak: B'mouth
team:brentford = Brentford
team:brighton-hove-albion = Brighton & Hove Albion | Brighton and Hove Albion | Brighton ; weak: B&HA
team:burnley = Burnley
team:chelsea = Chelsea
team:crystal-palace = Crystal Palace ; weak: Palace | C Palace
team:everton = Everton
team:fulham = Fulham
team:leeds-united = Leeds United | Leeds ; weak: Leeds Utd
team:liverpool = Liverpool
team:manchester-city = Manchester City | Man City ; weak: Man. City | ManCity
team:manchester-united = Manchester United | Man United | Man Utd | Manchester Utd | Μάντσεστερ Γιουνάιτεντ ; weak: ManU | Man U
team:newcastle-united = Newcastle United | Newcastle ; weak: Newcastle Utd
team:nottingham-forest = Nottingham Forest | Nott'm Forest | Nottm Forest | Nott. Forest ; weak: Forest | N Forest
team:sunderland = Sunderland | Sund'land
team:tottenham-hotspur = Tottenham Hotspur | Tottenham | Spurs ; not after: san antonio
team:west-ham-united = West Ham United | West Ham | Γουέστ Χαμ ; weak: West Ham Utd
team:wolverhampton-wanderers = Wolverhampton Wanderers | Wolves
team:leicester-city = Leicester City | Leicester
team:southampton = Southampton | Σαουθάμπτον
team:ipswich-town = Ipswich Town | Ipswich
team:sheffield-united = Sheffield United | Sheffield Utd | Sheff Utd
team:sheffield-wednesday = Sheffield Wednesday | Sheff Wed
team:west-bromwich-albion = West Bromwich Albion | West Brom ; weak: West Bromwich
team:middlesbrough = Middlesbrough
team:norwich-city = Norwich City | Norwich
team:coventry-city = Coventry City | Coventry
team:watford = Watford
team:stoke-city = Stoke City | Stoke
team:hull-city = Hull City | Hull
team:derby-county = Derby County ; weak: Derby
team:queens-park-rangers = Queens Park Rangers | QPR ; weak: ΚΠΡ
team:birmingham-city = Birmingham City ; weak: Birmingham
team:wrexham = Wrexham
team:celtic = Celtic
team:rangers = Rangers ; weak: Glasgow Rangers
team:aberdeen = Aberdeen
team:heart-of-midlothian = Heart of Midlothian | Hearts
team:real-madrid = Real Madrid | Real Madryt ; also: basketball
team:barcelona = Barcelona | FC Barcelona | Barca | Μπαρτσελόνα ; weak: Barcelone | Barcelonne | Barca FC ; also: basketball
team:atletico-madrid = Atlético Madrid | Atletico de Madrid | Atleti | Ατλέτικο Μαδρίτης ; weak: Atletico | A Madrid | Atl Madrid | Atletico Madryt
team:athletic-club = Athletic Club | Athletic Bilbao ; weak: Bilbao | Athletic
team:real-sociedad = Real Sociedad
team:real-betis = Real Betis | Betis | Real Betis Balompié
team:sevilla = Sevilla ; weak: Sevilla FC
team:valencia-cf = Valencia CF ; weak: Valencia
team:villarreal = Villarreal | Βιγιαρεάλ | Вильярреал ; weak: V'Real | Villareal
team:celta-vigo = Celta Vigo | Celta de Vigo | RC Celta ; weak: Celta | C Vigo
team:girona = Girona
team:osasuna = Osasuna
team:getafe = Getafe
team:rayo-vallecano = Rayo Vallecano ; weak: Rayo
team:mallorca = Mallorca | RCD Mallorca
team:espanyol = Espanyol
team:juventus = Juventus | Juve
team:inter-milan = Inter Milan | FC Internazionale | Inter Milano | FC Internazionale Milano | Internazionale Milano | Inter Mediolan ; weak: Inter | Internazionale | Ίντερ
team:ac-milan = AC Milan ; weak: Milan
team:napoli = Napoli | SSC Napoli | Νάπολι
team:as-roma = AS Roma ; weak: Roma
team:lazio = Lazio | SS Lazio | Λάτσιο
team:atalanta = Atalanta | Atalanta BC
team:fiorentina = Fiorentina | ACF Fiorentina
team:bologna = Bologna
team:torino = Torino
team:como = Como ; weak: Como 1907
team:venezia = Venezia ; weak: Veneza
team:udinese = Udinese
team:cagliari = Cagliari
team:genoa = Genoa | Genoa CFC
team:sassuolo = Sassuolo
team:parma = Parma | Πάρμα
team:lecce = Lecce | US Lecce
team:monza = Monza | Μόντσα
team:bayern-munich = Bayern Munich | Bayern München | Bayern Munchen | Bayern Muenchen | FC Bayern | FC Bayern Munchen | Bayern Monachium | Μπάγερν Μονάχου ; weak: Bayern ; also: basketball
team:borussia-dortmund = Borussia Dortmund | BVB ; weak: Dortmund
team:bayer-leverkusen = Bayer Leverkusen | Leverkusen | Bayer 04 Leverkusen
team:rb-leipzig = RB Leipzig | RB Lipsk | Λειψία ; weak: Leipzig
team:eintracht-frankfurt = Eintracht Frankfurt ; weak: Frankfurt
team:vfb-stuttgart = VfB Stuttgart ; weak: Stuttgart
team:borussia-monchengladbach = Borussia Mönchengladbach | Monchengladbach | Gladbach ; weak: Γκλάντμπαχ
team:vfl-wolfsburg = VfL Wolfsburg ; weak: Wolfsburg
team:sc-freiburg = SC Freiburg ; weak: Freiburg
team:werder-bremen = Werder Bremen | SV Werder Brema | Werder Brema ; weak: Bremen
team:union-berlin = Union Berlin | 1. FC Union Berlin
team:hamburger-sv = Hamburger SV | Hamburg SV ; weak: Hamburg | HSV
team:paris-saint-germain = Paris Saint-Germain | Paris St Germain | Paris St-Germain | Paris SG | PSG
team:marseille = Marseille | Olympique de Marseille | Olympique Marsylia | Olympique Marseille ; weak: OM
team:lyon = Lyon | Olympique Lyonnais | Olympique Lyon | O. Lyon ; weak: OL
team:as-monaco = AS Monaco ; weak: Monaco ; also: basketball
team:lille = Lille | LOSC Lille ; weak: LOSC | Λιλ
team:ogc-nice = OGC Nice ; weak: Nice
team:rc-lens = RC Lens ; weak: Lens | Λανς
team:stade-rennais = Stade Rennais | Rennes
team:benfica = Benfica | SL Benfica ; weak: SLB
team:fc-porto = FC Porto ; weak: Porto | Πόρτο
team:sporting-cp = Sporting CP | Sporting Lisbon | Sporting Clube de Portugal | Sporting Lissabon | Sporting Lisabona | Σπόρτινγκ Λισαβόνας ; weak: Sporting | SCP
team:sc-braga = SC Braga | Sporting Braga | Sporting de Braga ; weak: Braga
team:ajax = Ajax | AFC Ajax | Ajax Amsterdam | AFC Ajax Amsterdam
team:psv-eindhoven = PSV Eindhoven | PSV | PSV Αϊντχόφεν
team:feyenoord = Feyenoord
team:az-alkmaar = AZ Alkmaar ; weak: AZ
team:galatasaray = Galatasaray | Γαλατασαράι | Galatasaray AŞ ; also: basketball
team:fenerbahce = Fenerbahçe | Fenerbahce Istanbul | Fenerbahçe Beko | Fenerbahce Beko ; also: basketball
team:besiktas = Beşiktaş | Besiktas JK | Besiktas AS
team:trabzonspor = Trabzonspor
team:club-brugge = Club Brugge | Club Brugge KV | Κλαμπ Μπριζ ; weak: Brugge | Club Brugges
team:anderlecht = Anderlecht | RSC Anderlecht
team:red-bull-salzburg = Red Bull Salzburg | RB Salzburg | Red Bull Saltzburg | Saltzburg ; weak: Salzburg
team:shakhtar-donetsk = Shakhtar Donetsk | Szachtar Donieck | Šachtar Doněck ; weak: Shakhtar
team:dinamo-zagreb = Dinamo Zagreb ; weak: GNK Dinamo
team:red-star-belgrade = Red Star Belgrade | Crvena Zvezda ; also: basketball
team:olympiacos = Olympiacos | Olympiakos | Olympiakos SFP | Ολυμπιακός | Olympiakos Piraeus | Olympiacos Piraeus | Olympiakos Pireus ; also: basketball
team:panathinaikos = Panathinaikos | Panathinaikos Athens | Panathinaikos OPAP Athens | Panathinaikos AKTOR Athens ; also: basketball
team:al-hilal = Al Hilal
team:al-nassr = Al Nassr
team:al-ittihad = Al Ittihad
team:al-ahli-saudi = Al Ahli Saudi ; weak: Al Ahli
team:inter-miami = Inter Miami
team:la-galaxy = LA Galaxy
team:flamengo = Flamengo | CR Flamengo
team:palmeiras = Palmeiras
team:corinthians = Corinthians
team:boca-juniors = Boca Juniors | CA Boca Juniors
team:river-plate = River Plate
team:club-america = Club America ; weak: America
# added 2026-10-13: clubs seen in the guide without an entry (artwork completion pass)
team:portsmouth = Portsmouth | Πόρτσμουθ
team:motherwell = Motherwell
team:elche = Elche | Elche CF
team:deportivo-la-coruna = Deportivo La Coruña | Deportivo de La Coruña | RC Deportivo | La Coruña | La Coruna | Deportivo A Coruña | RC Deportivo La Coruna | Deprotivo La Coruna ; weak: Deportivo | Depor
team:malaga = Málaga CF | Malaga CF ; weak: Málaga | Malaga
team:frosinone = Frosinone | Frosinone Calcio | Frosinoe
team:tsg-hoffenheim = TSG Hoffenheim | TSG 1899 Hoffenheim | 1899 Hoffenheim | Hoffenheim ; weak: TSG
team:fc-augsburg = FC Augsburg ; weak: Augsburg
team:schalke-04 = Schalke 04 | FC Schalke 04 | Σάλκε ; weak: Schalke
team:1-fc-nurnberg = 1. FC Nürnberg | 1. FC Nurnberg | FC Nürnberg | Nürnberg | Nurnberg | Nuremberg | Νυρεμβέργη
team:hansa-rostock = Hansa Rostock | FC Hansa Rostock ; weak: Hansa
team:1-fc-saarbrucken = 1. FC Saarbrücken | 1. FC Saarbrucken | FC Saarbrücken | FC Saarbrucken | Saarbrücken | Saarbrucken
team:msv-duisburg = MSV Duisburg ; weak: Duisburg
team:1-fc-koln = 1. FC Köln | 1. FC Koln | FC Köln | FC Koln | 1 FC Köln | 1 FC Koln | FC Cologne | Cologne ; weak: Köln | Koln
team:fortuna-koln = Fortuna Köln | Fortuna Koln | SC Fortuna Köln | SC Fortuna Koln
team:rot-weiss-essen = Rot-Weiss Essen | Rot-Weiß Essen ; weak: Rot-Weiss
team:sv-meppen = SV Meppen ; weak: Meppen
team:strasbourg = RC Strasbourg | RC Strasbourg Alsace | Racing Strasbourg ; weak: Strasbourg
team:auxerre = AJ Auxerre | Auxerre
team:le-mans = Le Mans FC ; weak: Le Mans
team:stade-brestois = Stade Brestois | Stade Brestois 29 ; weak: Brest
team:angers = Angers SCO | Angers
team:troyes = ES Troyes AC | Troyes AC | Troyes
team:fc-nantes = FC Nantes ; weak: Nantes
team:stade-de-reims = Stade de Reims ; weak: Reims
team:famalicao = FC Famalicão | Famalicão | Famalicao
team:alverca = FC Alverca | Alverca
team:maritimo = CS Marítimo | Marítimo | Maritimo | CS Maritimo | Μαρίτιμο
team:vitoria-guimaraes = Vitória SC | Vitoria SC | Vitória Guimarães | Vitoria Guimaraes
team:nec-nijmegen = NEC Nijmegen | N.E.C. Nijmegen ; weak: NEC
team:heerenveen = SC Heerenveen | Heerenveen
team:rizespor = Çaykur Rizespor | Caykur Rizespor | Rizespor
team:basel = FC Basel | FC Basel 1893 ; weak: Basel
team:servette = Servette FC | Servette
team:sion = FC Sion ; weak: Sion
team:slavia-prague = Slavia Prague | Slavia Praha | SK Slavia Praha | Slavia Prag | Slavia Praga | Slavija Praga | Σλάβια Πράγας ; weak: Slavia
team:sparta-prague = Sparta Prague | Sparta Praha | AC Sparta Praha | AC Sparta Praga | Sparta Praga ; weak: Sparta
team:pardubice = FK Pardubice ; weak: Pardubice
team:nk-celje = NK Celje ; weak: Celje
team:sabah = Sabah FK | Σαμπάχ ; weak: Sabah
team:bodo-glimt = Bodø/Glimt | Bodo/Glimt | FK Bodø/Glimt | FK Bodo/Glimt | Bodø Glimt | Bodo Glimt ; weak: Glimt
team:viking = Viking FK | Βίκινγκ ; weak: Viking
team:lech-poznan = Lech Poznań | Lech Poznan | KKS Lech Poznań ; weak: Lech
team:legia-warsaw = Legia Warsaw | Legia Warszawa ; weak: Legia
team:rakow-czestochowa = Raków Częstochowa | Rakow Czestochowa ; weak: Raków | Rakow
team:wisla-krakow = Wisła Kraków | Wisla Krakow | Wisła Krakow
team:wisla-plock = Wisła Płock | Wisla Plock
team:wieczysta-krakow = Wieczysta Kraków | Wieczysta Krakow
team:cracovia = Cracovia | KS Cracovia
team:gks-katowice = GKS Katowice
team:pogon-szczecin = Pogoń Szczecin | Pogon Szczecin
team:korona-kielce = Korona Kielce
team:radomiak-radom = Radomiak Radom ; weak: Radomiak
team:slask-wroclaw = Śląsk Wrocław | Slask Wroclaw | Śląsk Wroclaw
team:piast-gliwice = Piast Gliwice
team:widzew-lodz = Widzew Łódź | Widzew Lodz
team:zaglebie-lubin = Zagłębie Lubin | Zaglebie Lubin | KGHM Zagłębie Lubin ; weak: Zaglebie | Zagłębie
team:motor-lublin = Motor Lublin
team:jagiellonia-bialystok = Jagiellonia Białystok | Jagiellonia Bialystok ; weak: Jagiellonia
team:paok = PAOK | PAOK FC | ΠΑΟΚ ; also: basketball
team:ofi-crete = OFI Crete | OFI Kreta ; weak: OFI
team:kalamata = Kalamata FC | Καλαμάτα ; weak: Kalamata
team:apoel = APOEL | APOEL Nicosia | ΑΠΟΕΛ
team:nea-salamina = Nea Salamina | Νέα Σαλαμίνα
team:vasco-da-gama = Vasco da Gama | CR Vasco da Gama ; weak: Vasco
team:al-sadd = Al Sadd | Al-Sadd ; weak: Sadd
team:shabab-al-ahli = Shabab Al Ahli | Shabab Al-Ahli | Shabab Ahli
team:al-ain = Al Ain | Al-Ain
team:al-shorta = Al Shorta | Al-Shorta
team:air-force-club = Al Quwa Al Jawiya | Air Force Club | Air Force SC
team:al-seeb = Al Seeb | Al-Seeb | Al Seeb Club
team:al-hussein = Al Hussein | Al-Hussein | Al Hussein Irbid
team:ratchaburi = Ratchaburi FC ; weak: Ratchaburi
team:buriram-united = Buriram United
team:pohang-steelers = Pohang Steelers
team:fc-seoul = FC Seoul
team:johor-darul-tazim = Johor Darul Ta'zim | Johor Darul Tazim ; weak: JDT
team:gamba-osaka = Gamba Osaka
team:kyoto-sanga = Kyoto Sanga | Kyoto Sanga FC | Kyoto Sanga F.C.
team:kashima-antlers = Kashima Antlers
team:newcastle-jets = Newcastle Jets
team:melbourne-victory = Melbourne Victory
team:east-bengal = East Bengal
team:cong-an-ha-noi = Cong An Ha Noi | Công An Hà Nội | CAHN
team:lion-city-sailors = Lion City Sailors

team:lask = LASK | LASK Linz
team:sturm-graz = SK Sturm Graz | Sturm Graz ; weak: Sturm
team:union-saint-gilloise = Union Saint-Gilloise | Royale Union Saint-Gilloise | Union SG | St Gilloise | St Gilloisse | Ουνιόν Σεν-Ζιλουάζ
team:torreense = SCU Torreense | Torreense | Torrense
team:kups = KuPS | Kuopion Palloseura
team:partizan = Partizan | Partizan Belgrade | Partizan Belgrad | FK Partizan | KK Partizan | Partizan Mozzart Bet Belgrade | Παρτίζαν ; also: basketball
team:omonia-nicosia = Omonia Nicosia | AC Omonia | Omonia | Ομόνοια
team:pafos = Pafos FC | Pafos | Πάφος
team:kauno-zalgiris = Kauno Žalgiris | Kauno Zalgiris | Κάουνο Ζαλγκίρις
team:hajduk-split = Hajduk Split | HNK Hajduk Split | Χάιντουκ Σπλιτ ; weak: Hajduk
team:fluminense = Fluminense
team:levante = Levante | Levante UD
team:universitatea-craiova = Universitatea Craiova | CS Universitatea Craiova | CS U Craiova | U Craiova
team:cska-sofia = CSKA Sofia | PFC CSKA Sofia
team:dinamo-bucuresti = Dinamo București | Dinamo Bucuresti | Dinamo Bucharest | Dínamo Bucareste | Dinamo Bucareste
team:gornik-zabrze = Górnik Zabrze | Gornik Zabrze
team:lugano = FC Lugano ; weak: Lugano
team:shanghai-shenhua = Shanghai Shenhua
team:gangwon = Gangwon FC ; weak: Gangwon
team:adelaide-united = Adelaide United
team:tampines-rovers = Tampines Rovers
team:holstein-kiel = Holstein Kiel
team:hertha-bsc = Hertha BSC | Hertha Berlin ; weak: Hertha
team:estudiantes = Estudiantes de La Plata | Estudiantes LP ; weak: Estudiantes
team:al-wasl = Al Wasl | Al-Wasl
team:neftchi = Neftçi | Neftchi | PFC Neftchi | Neftchi Baku
team:al-gharafa = Al Gharafa | Al-Gharafa
team:esteghlal = Esteghlal | Esteghlal FC
team:hapoel-beer-sheva = Hapoel Be'er Sheva | Hapoel Beer Sheva | Hapoel Be'er
team:jablonec = FK Jablonec ; weak: Jablonec
team:preussen-munster = Preußen Münster | Preussen Munster | SC Preußen Münster
team:fortuna-dusseldorf = Fortuna Düsseldorf | Fortuna Dusseldorf
team:lincoln-city = Lincoln City
team:brann = SK Brann ; weak: Brann
team:lincoln-red-imps = Lincoln Red Imps
team:fc-kobenhavn = FC København | FC Kobenhavn | FC Copenhagen | København | Kobenhavn | Κοπεγχάγη ; weak: Copenhagen
team:alaves = Deportivo Alavés | Alavés | Alaves
team:saint-etienne = AS Saint-Étienne | Saint-Étienne | Saint Etienne | St Etienne | ASSE
team:rodez = Rodez AF | Rodez
team:kashiwa-reysol = Kashiwa Reysol | Kashiwa
team:al-jazira = Al Jazira | Al-Jazira
team:ararat-armenia = Ararat-Armenia | Ararat Armenia
team:aris-thessaloniki = Aris Thessaloniki | Aris Salonika ; weak: Aris | Άρης ; also: basketball
team:aek-athens = AEK Athens | ΑΕΚ ; weak: AEK ; also: basketball
team:sudtirol = FC Südtirol | Südtirol | Sudtirol | Σουντιρόλ

@club basketball
team:anadolu-efes = Anadolu Efes | Anadolu Efes Istanbul ; weak: Efes
team:virtus-bologna = Virtus Bologna | Virtus Segafredo Bologna | Βίρτους Μπολόνια
team:olimpia-milano = Olimpia Milano | EA7 Emporio Armani Milano | Emporio Armani Milano | Armani Milano | AX Armani Exchange Milano | Αρμάνι Μιλάνο ; weak: Armani
team:baskonia = Baskonia | Saski Baskonia | Baskonia Vitoria-Gasteiz
team:maccabi-tel-aviv = Maccabi Tel Aviv | Maccabi Playtika Tel Aviv ; weak: Maccabi ; also: football
team:valencia-basket = Valencia Basket
team:asvel = LDLC ASVEL | ASVEL | ASVEL Villeurbanne | Villeurbanne | Βιλερμπάν
team:zalgiris-kaunas = Žalgiris Kaunas | Zalgiris Kaunas | BC Žalgiris ; weak: Žalgiris | Zalgiris
team:dubai-basketball = Dubai Basketball | Dubai BC | Ντουμπάι ; weak: Dubai
team:paris-basketball = Paris Basketball | Paris Basket
team:hapoel-tel-aviv = Hapoel Tel Aviv | Hapoel IBI Tel Aviv ; also: football
team:manresa = BAXI Manresa | Bàsquet Manresa | Manresa | Μανρέσα
team:derthona = Bertram Derthona | Derthona Tortona | Derthona Basket | Ντερτόνα
team:buducnost = Budućnost | Buducnost | KK Budućnost | Budućnost VOLI
team:atlanta-hawks = Atlanta Hawks ; scoped: Hawks | Atlanta
team:boston-celtics = Boston Celtics ; scoped: Celtics | Boston
team:brooklyn-nets = Brooklyn Nets ; scoped: Nets | Brooklyn
team:charlotte-hornets = Charlotte Hornets ; scoped: Hornets | Charlotte
team:chicago-bulls = Chicago Bulls ; scoped: Bulls | Chicago
team:cleveland-cavaliers = Cleveland Cavaliers ; scoped: Cavaliers | Cleveland | Cavs
team:dallas-mavericks = Dallas Mavericks ; scoped: Mavericks | Dallas | Mavs
team:denver-nuggets = Denver Nuggets ; scoped: Nuggets | Denver
team:detroit-pistons = Detroit Pistons ; scoped: Pistons | Detroit
team:golden-state-warriors = Golden State Warriors ; scoped: Warriors | Golden State | GS Warriors
team:houston-rockets = Houston Rockets ; scoped: Rockets | Houston
team:indiana-pacers = Indiana Pacers ; scoped: Pacers | Indiana
team:la-clippers = LA Clippers | Los Angeles Clippers | L.A. Clippers ; scoped: Clippers
team:los-angeles-lakers = Los Angeles Lakers | LA Lakers | L.A. Lakers ; scoped: Lakers
team:memphis-grizzlies = Memphis Grizzlies ; scoped: Grizzlies | Memphis
team:miami-heat = Miami Heat ; scoped: Heat | Miami
team:milwaukee-bucks = Milwaukee Bucks ; scoped: Bucks | Milwaukee
team:minnesota-timberwolves = Minnesota Timberwolves ; scoped: Timberwolves | Minnesota | Wolves
team:new-orleans-pelicans = New Orleans Pelicans ; scoped: Pelicans | New Orleans
team:new-york-knicks = New York Knicks ; scoped: Knicks | New York | NY Knicks
team:oklahoma-city-thunder = Oklahoma City Thunder ; scoped: Thunder | Oklahoma City | Oklahoma | OKC
team:orlando-magic = Orlando Magic ; scoped: Magic | Orlando
team:philadelphia-76ers = Philadelphia 76ers | Philadelphia Sixers ; scoped: 76ers | Philadelphia | Sixers
team:phoenix-suns = Phoenix Suns ; scoped: Suns | Phoenix
team:portland-trail-blazers = Portland Trail Blazers ; scoped: Trail Blazers | Portland | Blazers
team:sacramento-kings = Sacramento Kings ; scoped: Kings | Sacramento
team:san-antonio-spurs = San Antonio Spurs ; scoped: Spurs | San Antonio
team:toronto-raptors = Toronto Raptors ; scoped: Raptors | Toronto
team:utah-jazz = Utah Jazz ; scoped: Jazz | Utah
team:washington-wizards = Washington Wizards ; scoped: Wizards | Washington

@club nfl
team:arizona-cardinals = Arizona Cardinals ; scoped: Cardinals | Arizona
team:atlanta-falcons = Atlanta Falcons ; scoped: Falcons | Atlanta
team:baltimore-ravens = Baltimore Ravens ; scoped: Ravens | Baltimore
team:buffalo-bills = Buffalo Bills ; scoped: Bills | Buffalo
team:carolina-panthers = Carolina Panthers ; scoped: Panthers | Carolina
team:chicago-bears = Chicago Bears ; scoped: Bears | Chicago
team:cincinnati-bengals = Cincinnati Bengals ; scoped: Bengals | Cincinnati
team:cleveland-browns = Cleveland Browns ; scoped: Browns | Cleveland
team:dallas-cowboys = Dallas Cowboys ; scoped: Cowboys | Dallas
team:denver-broncos = Denver Broncos ; scoped: Broncos | Denver
team:detroit-lions = Detroit Lions ; scoped: Lions | Detroit
team:green-bay-packers = Green Bay Packers ; scoped: Packers | Green Bay
team:houston-texans = Houston Texans ; scoped: Texans | Houston
team:indianapolis-colts = Indianapolis Colts ; scoped: Colts | Indianapolis
team:jacksonville-jaguars = Jacksonville Jaguars ; scoped: Jaguars | Jacksonville
team:kansas-city-chiefs = Kansas City Chiefs ; scoped: Chiefs | Kansas City
team:las-vegas-raiders = Las Vegas Raiders ; scoped: Raiders | Las Vegas
team:los-angeles-chargers = Los Angeles Chargers | LA Chargers ; scoped: Chargers
team:los-angeles-rams = Los Angeles Rams | LA Rams ; scoped: Rams
team:miami-dolphins = Miami Dolphins ; scoped: Dolphins | Miami
team:minnesota-vikings = Minnesota Vikings ; scoped: Vikings | Minnesota
team:new-england-patriots = New England Patriots ; scoped: Patriots | New England
team:new-orleans-saints = New Orleans Saints ; scoped: Saints | New Orleans
team:new-york-giants = New York Giants ; scoped: Giants
team:new-york-jets = New York Jets ; scoped: Jets
team:philadelphia-eagles = Philadelphia Eagles ; scoped: Eagles | Philadelphia
team:pittsburgh-steelers = Pittsburgh Steelers ; scoped: Steelers | Pittsburgh
team:san-francisco-49ers = San Francisco 49ers ; scoped: 49ers | San Francisco | Niners
team:seattle-seahawks = Seattle Seahawks ; scoped: Seahawks | Seattle
team:tampa-bay-buccaneers = Tampa Bay Buccaneers ; scoped: Buccaneers | Tampa Bay | Bucs
team:tennessee-titans = Tennessee Titans ; scoped: Titans | Tennessee
team:washington-commanders = Washington Commanders ; scoped: Commanders | Washington

@national any
team:england = England
team:scotland = Scotland
team:wales = Wales | Ουαλία
team:northern-ireland = Northern Ireland
team:republic-of-ireland = Republic of Ireland | Ireland | Ιρλανδία
team:france = France | Γαλλία
team:germany = Germany | Deutschland
team:spain = Spain | Espana
team:italy = Italy | Italia
team:portugal = Portugal
team:netherlands = Netherlands | Nederland ; weak: Holland
team:belgium = Belgium | Belgique | Belgie | Βέλγιο | Belgia
team:brazil = Brazil | Brasil
team:argentina = Argentina
team:united-states = United States | USA | USMNT
team:mexico = Mexico
team:croatia = Croatia | Hrvatska
team:denmark = Denmark | Danmark | Δανία
team:sweden = Sweden | Sverige
team:norway = Norway | Norge
team:poland = Poland | Polska
team:turkey = Turkey | Turkiye
team:switzerland = Switzerland | Schweiz | Suisse
team:austria = Austria | Osterreich
team:morocco = Morocco | Maroc
team:japan = Japan
team:south-korea = South Korea | Korea Republic
team:australia = Australia ; weak: AUS
team:uruguay = Uruguay
team:colombia = Colombia
team:saudi-arabia = Saudi Arabia
team:egypt = Egypt
team:nigeria = Nigeria
team:senegal = Senegal
team:india = India ; weak: IND
team:pakistan = Pakistan ; weak: PAK
team:south-africa = South Africa ; weak: RSA | SA
team:new-zealand = New Zealand ; weak: NZ
team:west-indies = West Indies ; weak: WI
team:sri-lanka = Sri Lanka ; weak: SL
team:bangladesh = Bangladesh ; weak: BAN
team:afghanistan = Afghanistan ; weak: AFG
team:zimbabwe = Zimbabwe ; weak: ZIM
team:finland = Finland | Suomi
team:iceland = Iceland | Island
team:greece = Greece | Hellas
team:serbia = Serbia | Srbija
team:czechia = Czechia | Czech Republic | Cesko
team:hungary = Hungary | Magyarorszag
team:romania = Romania
team:ukraine = Ukraine
team:slovakia = Slovakia
team:slovenia = Slovenia | Slovenija
team:albania = Albania
team:bosnia-and-herzegovina = Bosnia and Herzegovina | Bosnia-Herzegovina
team:north-macedonia = North Macedonia
team:montenegro = Montenegro | Μαυροβούνιο
team:israel = Israel | Ισραήλ
team:canada = Canada
team:chile = Chile
team:peru = Peru
team:ecuador = Ecuador
team:paraguay = Paraguay
team:iran = Iran
team:qatar = Qatar
team:ghana = Ghana
team:cameroon = Cameroon
team:ivory-coast = Ivory Coast | Cote d'Ivoire
team:algeria = Algeria
team:tunisia = Tunisia
team:bulgaria = Bulgaria | Βουλγαρία
team:cyprus = Cyprus | Κύπρος
team:luxembourg = Luxembourg | Λουξεμβούργο
team:kazakhstan = Kazakhstan
team:azerbaijan = Azerbaijan
team:armenia = Armenia
team:estonia = Estonia
team:latvia = Latvia
team:lithuania = Lithuania
team:faroe-islands = Faroe Islands
team:malta = Malta
team:moldova = Moldova
team:kosovo = Kosovo
team:belarus = Belarus
team:andorra = Andorra
team:san-marino = San Marino
team:gibraltar = Gibraltar
team:liechtenstein = Liechtenstein

@competition football
comp:premier-league = Premier League | English Premier League | EPL | Barclays Premier League | Premier liga ; weak: PL ; priority: 100 ; not after: indian bangladesh caribbean pakistan lanka lankan egyptian egypt nigeria nigerian ghana ghanaian kenyan kenya russian ukrainian israeli welsh kong armenian belarusian kazakhstan tanzanian maltese jamaica jamaican lebanese singapore malaysian canadian hockey netball volleyball basketball darts snooker kabaddi ; not before: darts netball hockey kabaddi
comp:uefa-champions-league = UEFA Champions League | Champions League | UCL | Champions-League | Liga de Campeones | Ligue des champions | Liga dos Campeoes ; priority: 100 ; not after: afc caf ehf cev concacaf ofc global asian african basketball hockey volleyball womens t20 velux
comp:uefa-womens-champions-league = UEFA Women's Champions League | Women's Champions League | UWCL ; priority: 45
comp:uefa-europa-league = UEFA Europa League | Europa League | UEL | Liga Europa | Ligue Europa ; priority: 85
comp:uefa-conference-league = UEFA Conference League | Conference League | Europa Conference League | UECL ; priority: 70
comp:laliga = LaLiga | La Liga | LaLiga EA Sports | Spanish LaLiga | Primera Division ; priority: 90 ; not after: liga
comp:laliga-hypermotion = LaLiga Hypermotion | LaLiga 2 | Segunda Division ; priority: 45
comp:serie-a = Serie A | Serie A TIM | Serie A Enilive ; priority: 85 ; not after: brasileirao campeonato brasileiro basket volley lba
comp:bundesliga = Bundesliga ; priority: 85 ; not after: handball basketball basket volleyball hockey eishockey 2 osterreichische austrian admiral frauen
comp:2-bundesliga = 2. Bundesliga | 2 Bundesliga | Zweite Bundesliga ; priority: 45
comp:ligue-1 = Ligue 1 | French Ligue 1 | Ligue 1 McDonald's ; priority: 75
comp:ligue-2 = Ligue 2 ; priority: 40
comp:eredivisie = Eredivisie ; priority: 55
comp:primeira-liga = Primeira Liga | Liga Portugal | Liga Portugal Betclic ; priority: 55 ; not before: 2
comp:liga-portugal-2 = Liga Portugal 2 ; priority: 25
comp:scottish-premiership = Scottish Premiership | SPFL | Scottish Premier League ; priority: 55
comp:super-lig = Super Lig | Trendyol Super Lig ; priority: 50 ; not after: volleyball basketball
comp:saudi-pro-league = Saudi Pro League | Roshn Saudi League ; priority: 50
comp:major-league-soccer = Major League Soccer | MLS ; priority: 50
comp:liga-mx = Liga MX ; priority: 45
comp:brasileirao = Brasileirao | Brasileirao Serie A | Campeonato Brasileiro ; priority: 55
comp:efl-championship = EFL Championship | Sky Bet Championship | SkyBet Championship ; weak: Championship ; priority: 60 ; not after: racing truck touring car rally rallycross superbike superbikes supersport motocross enduro endurance karting speedway drift gt motorcycle motogp darts snooker pool rugby netball hockey golf swimming athletics gymnastics cycling sailing boxing world european national ; not before: series
comp:efl-league-one = EFL League One | Sky Bet League One ; weak: League One ; priority: 35
comp:efl-league-two = EFL League Two | Sky Bet League Two ; weak: League Two ; priority: 30
comp:fa-cup = FA Cup | Emirates FA Cup ; priority: 70 ; not after: womens scottish
comp:efl-cup = EFL Cup | Carabao Cup ; weak: League Cup ; priority: 65
comp:copa-del-rey = Copa del Rey ; priority: 60
comp:coppa-italia = Coppa Italia ; priority: 55
comp:dfb-pokal = DFB-Pokal | DFB Pokal ; priority: 55
comp:coupe-de-france = Coupe de France ; priority: 45
comp:fifa-world-cup = FIFA World Cup ; priority: 100
comp:fifa-club-world-cup = FIFA Club World Cup | Club World Cup ; priority: 80
comp:world-cup-qualifiers = World Cup Qualifiers | World Cup Qualifying | WC Qualifiers ; priority: 70 ; not after: rugby cricket t20 icc
comp:uefa-nations-league = UEFA Nations League ; weak: Nations League ; priority: 65
comp:uefa-euro = UEFA Euro | European Championship Qualifiers | Euro Qualifiers ; priority: 85
comp:copa-libertadores = Copa Libertadores | Libertadores ; priority: 60
comp:copa-sudamericana = Copa Sudamericana ; priority: 40
comp:afc-champions-league = AFC Champions League | AFC Champions League Elite | ACL Elite ; priority: 40
comp:uefa-youth-league = UEFA Youth League ; priority: 10
comp:caf-champions-league = CAF Champions League ; priority: 35
comp:womens-super-league = Women's Super League | Barclays WSL ; weak: WSL ; priority: 40
comp:jupiler-pro-league = Jupiler Pro League | Belgian Pro League ; priority: 30
comp:eliteserien = Eliteserien ; priority: 25
comp:allsvenskan = Allsvenskan ; priority: 25
comp:ekstraklasa = Ekstraklasa ; priority: 25
comp:qatar-stars-league = Qatar Stars League | Stars League | QSL ; priority: 25
comp:uae-pro-league = UAE Pro League ; priority: 25
comp:a-league = A-League | A League Men ; priority: 30

@competition basketball
comp:nba = NBA ; priority: 80 ; not before: 2k
comp:wnba = WNBA ; priority: 30
comp:euroleague = EuroLeague | Euroliga | Turkish Airlines EuroLeague ; priority: 50
comp:eurocup = EuroCup ; priority: 30 ; not after: rugby
comp:liga-endesa = Liga Endesa | Liga ACB | ACB ; priority: 40
comp:aba-league = ABA League | ABA liga ; priority: 25

@competition nfl
comp:nfl = NFL ; priority: 80

@competition cricket
comp:indian-premier-league = Indian Premier League | IPL ; priority: 60
comp:t20-world-cup = T20 World Cup | ICC Men's T20 World Cup ; priority: 70
comp:the-ashes = The Ashes | Ashes Test ; priority: 80
comp:the-hundred = The Hundred ; priority: 30

@competition rugby
comp:six-nations = Six Nations | Guinness Six Nations | 6 Nations ; priority: 80
comp:rugby-world-cup = Rugby World Cup ; priority: 90
comp:premiership-rugby = Premiership Rugby | Gallagher Premiership ; priority: 50
comp:united-rugby-championship = United Rugby Championship | URC ; priority: 45
comp:top-14 = Top 14 ; priority: 45
comp:super-rugby = Super Rugby ; priority: 40
comp:the-rugby-championship = The Rugby Championship ; priority: 60
comp:nrl = NRL ; priority: 40
comp:investec-champions-cup = Investec Champions Cup | European Rugby Champions Cup ; priority: 50

@competition tennis
comp:wimbledon = Wimbledon ; priority: 90
comp:roland-garros = Roland Garros | French Open ; priority: 80
comp:australian-open = Australian Open ; priority: 80
comp:atp-finals = ATP Finals ; priority: 60
comp:atp-tour = ATP Tour | ATP ; priority: 35
comp:wta-tour = WTA Tour | WTA ; priority: 30
comp:davis-cup = Davis Cup ; priority: 40

@competition f1
comp:formula-1 = Formula 1 | F1 | Formula One | Formel 1 | Formula Uno | Formule 1 | FIA Formula One World Championship ; priority: 90

@competition mma
comp:ufc = UFC ; priority: 80
comp:pfl = PFL ; priority: 30
comp:bellator = Bellator ; priority: 30
comp:one-championship = ONE Championship ; priority: 25
"""

# Sport words in titles and descriptions (any language seen in this guide). Matched as whole
# words / phrases on norm() text; longer phrases first ("american football" before "football").
TERMS = {
    NFL: "american football | americky fotbal | americki fudbal | am nogomet | americki nogomet | ameriski nogomet | "
         "futbol americano | football americain | "
         "american football | αμερικανικο ποδοσφαιρο | американский футбол | nfl",
    FOOTBALL: "football | soccer | futbol | futebol | calcio | fussball | fußball | voetbal | fotboll | fodbold | "
              "fotball | jalkapallo | fotbal | nogomet | fudbal | labdarugas | pilka nozna | piłka nozna | ποδοσφαιρο | "
              "футбол | futbal | kopaonik",
    BASKETBALL: "basketball | basket | baloncesto | pallacanestro | kosarka | koszykowka | kosarlabda | koripallo | "
                "basquete | basquetebol | μπασκετ | баскетбол | basketbol | 3x3",
    HANDBALL: "handball | handbold | handboll | rukomet | balonmano | pallamano | pilka reczna | piłka reczna | kezilabda | hazena | "
              "hentbol | χαντμπολ | гандбол | starligue | handball bundesliga",
    VOLLEYBALL: "volleyball | volley | odbojka | siatkowka | voleibol | pallavolo | roplabda | volejbal | lentopallo | "
                "voleybol | βολει | волейбол",
    HOCKEY: "ice hockey | hockey | nhl | khl | hokej | jaakiekko | ishockey | eishockey | хоккей",
    TENNIS: "tennis | tenis | tenisz",
    BOXING: "boxing | boks | boxe | boxeo | pugilato | бокс",
    MMA: "mma | mixed martial arts | fight night",
    F1: "grand prix | formula 1 | f1",
    CRICKET: "cricket | odi | t20 | t20i | test match | icc | cri | kriket",
    RUGBY: "rugby | rugby union | rugby league | ragbi",
    OTHER: "golf | darts | snooker | cycling | ciclismo | motogp | moto2 | moto3 | nascar | indycar | superbike | "
           "athletics | swimming | equestrian | sailing | sail gp | horse racing | motor racing | bowling | poker | wrestling | "
           "wwe | aew | padel | badminton | table tennis | esports | kabaddi | netball | volleyball nations",
}
# Not a live sports programme (kept for search, left out of the Sports view's live lists).
SHOW_WORDS = ("highlights | highlight | hl | hlts | hls | hoogtepunten | magazine | magazin | review | preview | greatest | classic | classics | "
              "rescaldo | antevisao | previa | avant match | apres match | nachbericht | vorbericht | "
              "podsumowanie | skrot | skroty | magazyn | zapowiedz | sestrih | sazetak | rezumat | ozet | "
              "pregled | turska liga | srce nemackog fudbala | rurska dolina | goal arena | stadion | "
              "rewind | best of | goals | stories | story | documentary | docu | doku | dokumentation | build up | "
              "buildup | countdown | studio | show | weekly | talk | news | analysis | roundup | round up | "
              "all or nothing | match of the day | motd | goal rush | moments | momenti | momentos | hojdpunkter | "
              "hoydepunkter | hojdepunkter | sammendrag | resumen | resumo | sintesi | zusammenfassung | samenvatting | "
              "melhores momentos | pre match | prematch | post match | postmatch | reaction | press conference | "
              "training | legends | icons | rivalry | rivals | inside | behind the | academy | debate | podcast | "
              "quiz | vlog | this week | tribute | history | archive | anthology | special | specials | nejlepsi momenty | "
              "greatest games | the story | movie | film | official film")
REPLAY_WORDS = ("replay | rerun | re run | re air | reair | delayed | deferred | repeat | wiederholung | repeticion | "
                "reprise | rediffusion | replica | en diferido | diferido | powtorka | ponovitev | encore")
LIVE_WORDS = "live | en vivo | en directo | ao vivo | en direct | direct | diretta | na zivo | uzivo | v zivo | live now"
WOMEN_WORDS = {"women", "womens", "w", "ladies", "feminino", "femenino", "femminile", "frauen", "damer", "kvinner",
               "kvinnor", "feminine", "zene", "kobiet", "noi", "ž"}
# Words that make an unknown side look like a football club ("Esteghlal FC", "Racing Club").
CLUB_WORDS = {"fc", "cf", "afc", "sc", "cd", "ud", "sd", "ac", "as", "ss", "ssc", "sv", "vfb", "vfl", "fk", "nk", "sk",
              "bk", "if", "ik", "united", "city", "athletic", "rovers", "wanderers", "albion", "town", "county",
              "real", "atletico", "sporting", "deportivo", "dynamo", "dinamo", "spartak", "cska", "olympique",
              "borussia", "calcio", "club", "hotspur"}
GENERIC = {"fc", "cf", "afc", "sc", "cd", "ud", "sd", "ssc", "sk", "fk", "nk", "club", "calcio", "the"}
# Youth and reserve sides are other matches than the first team's.
YOUTH_WORDS = {"u17", "u18", "u19", "u20", "u21", "u23", "sub", "youth", "juniors", "junior", "reserves", "primavera",
               "juvenil", "academy", "mlodziezowa", "młodziezowa", "juniorska", "omladinska", "mladinska", "jugend", "giovanile",
               "primavera", "espoirs", "juniores", "u19s", "under", "nextgen"}
_DATE = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{2}|\d{4})\b")
# Tails after the second team: rounds, legs, dates ("3rd T20", "Week 6", "MD 2", "26/27")
_TAIL = re.compile(r"\s+(?:\d+(?:st|nd|rd|th)\b|\d+[/.]\d+|\d{4}\b|'\d\d\b|week\b|wk\b|md\s*\d|mw\s*\d|round\b|leg\b|"
                   r"game\s*\d|g\d+\b|semi|final|quarter|test\b|odi\b|t20|matchday|jornada|giornata|spieltag|journee|"
                   r"etapa\b|runda\b|kolo\b|hafta\b|fecha\b|speeldag\b|omgang\b|kierros\b|forduló)",
                   re.I)
_VS = re.compile(r"\s(?:v|vs|vs\.|v\.|x|@)\s", re.I)
_DASH = re.compile(r"\s[-–—/]\s")
_HYPHEN = re.compile(r"(?<=[^\W\d_])-(?=[^\W\d_])")
_PAREN = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_LABEL = re.compile(r"\s*:\s*(?!\d\d\b)")
# A side that is a part of an event, never a team: "Race 1 - Jarama", "Heat 2 - Lohéac", "Stage 5"
_NOT_A_SIDE = re.compile(r"^(race|heat|stage|leg|round|session|practice|qualifying|sprint|semi final|final|run|moto)( \d+)?$"
                         r"|^[a-z]{1,3} ?\d{1,3}( extra| hd| sd)?$")     # a channel or feed code: "P02 - L2 EXTRA" is no match
_STAGE = re.compile(r"(?:\d+(?:st|nd|rd|th)\s+(?:test|odi|t20i?|one-day international)|(?:first|second|third|fourth|fifth)\s+test)\s*[:\-–]?\s+", re.I)
_LEADLIVE = re.compile(r"^\s*(?:live|en vivo|en directo|ao vivo|en direct|direct|diretta)\b\s*[:!|-]?\s*", re.I)


def _phrases(text: str) -> list[str]:
    return [p for p in (norm(x) for x in text.split("|")) if p]


class Entity:
    __slots__ = ("id", "key", "kind", "sport", "name", "names", "weak", "not_after", "not_before", "priority", "was", "also", "scoped")

    def __init__(self, eid: int, key: str, kind: str, sport: int, name: str):
        self.id, self.key, self.kind, self.sport, self.name = eid, key, kind, sport, name
        self.was: list[str] = []
        self.also: set[int] = set()            # other sports this club plays under the same name (EuroLeague clubs)
        self.scoped: list[str] = []            # names that are this team only in its own sport ("Spurs", "Atlanta")
        self.names: list[str] = []
        self.weak: list[str] = []
        self.not_after: set[str] = set()
        self.not_before: set[str] = set()
        self.priority = 0


def _load(data: str) -> list[Entity]:
    out: list[Entity] = []
    kind, sport = "", 0
    for raw in data.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            kind, sp = line[1:].split()
            sport = 0 if sp == "any" else BY_KEY[sp]
            continue
        key, sep, line = line.partition(" = ")
        if not sep or not re.fullmatch(r"(team|comp):[a-z0-9-]+", key):
            raise ValueError(f"sports DATA line without an id: {raw!r}")
        parts = [p.strip() for p in line.split(";")]
        names = [n.strip() for n in parts[0].split("|") if n.strip()]
        e = Entity(len(out), key, kind, sport, names[0])
        e.names = [n for n in dict.fromkeys(norm(n) for n in names) if n]
        for opt in parts[1:]:
            name, _, val = opt.partition(":")
            name = name.strip()
            if name == "weak":
                e.weak = [n for n in dict.fromkeys(norm(n) for n in val.split("|")) if n]
            elif name == "not after":
                e.not_after = set(norm(val).split())
            elif name == "not before":
                e.not_before = set(norm(val).split())
            elif name == "priority":
                e.priority = int(val)
            elif name == "was":
                e.was = val.split()
            elif name == "also":
                e.also = {BY_KEY[x] for x in val.split()}
            elif name == "scoped":
                # "Hawks | Atlanta": the nickname first. Also its city's initials + nickname, as US guides
                # abbreviate ("A Falcons", "NY Giants", "KC Chiefs").
                names = [n.strip() for n in val.split("|") if n.strip()]
                nick = norm(names[0]) if names else ""
                city = norm(e.name)[: -len(nick)].split() if nick and norm(e.name).endswith(nick) else []
                extra = [f"{city[0][0]} {nick}", f"{''.join(w[0] for w in city)} {nick}"] if city else []
                e.scoped = [n for n in dict.fromkeys([norm(n) for n in names] + extra) if n]
        out.append(e)
    return out



# Greek guides (Cosmote, Nova) name foreign clubs and countries in Greek, often not letter-for-letter
# ("Ρεάλ Μαδρίτης": Real of Madrid; "Κολωνία": Cologne). Added to each entity's names at load; any
# other Greek side goes through greek_side() (sound-alike matching) in resolve_side.
GREEK_NAMES = {
    "real-madrid": "Ρεάλ Μαδρίτης", "barcelona": "Μπαρτσελόνα", "atletico-madrid": "Ατλέτικο Μαδρίτης",
    "athletic-club": "Αθλέτικ Μπιλμπάο", "real-sociedad": "Ρεάλ Σοσιεδάδ", "real-betis": "Μπέτις | Ρεάλ Μπέτις",
    "sevilla": "Σεβίλλη", "valencia-cf": "Βαλένθια", "villarreal": "Βιγιαρεάλ", "celta-vigo": "Θέλτα | Σέλτα Βίγο",
    "girona": "Τζιρόνα", "osasuna": "Οσασούνα", "getafe": "Χετάφε", "rayo-vallecano": "Ράγιο Βαγιεκάνο",
    "mallorca": "Μαγιόρκα", "espanyol": "Εσπανιόλ", "elche": "Έλτσε", "deportivo-la-coruna": "Ντεπορτίβο Λα Κορούνια",
    "juventus": "Γιουβέντους", "inter-milan": "Ίντερ", "ac-milan": "Μίλαν", "napoli": "Νάπολι", "as-roma": "Ρόμα",
    "lazio": "Λάτσιο", "atalanta": "Αταλάντα", "fiorentina": "Φιορεντίνα", "bologna": "Μπολόνια", "torino": "Τορίνο",
    "como": "Κόμο", "venezia": "Βενέτσια", "udinese": "Ουντινέζε", "cagliari": "Κάλιαρι", "genoa": "Τζένοα",
    "sassuolo": "Σασουόλο", "parma": "Πάρμα", "lecce": "Λέτσε", "monza": "Μόντσα",
    "bayern-munich": "Μπάγερν Μονάχου | Μπάγερν", "borussia-dortmund": "Ντόρτμουντ | Μπορούσια Ντόρτμουντ",
    "bayer-leverkusen": "Λεβερκούζεν | Μπάγερ Λεβερκούζεν", "rb-leipzig": "Λειψία", "eintracht-frankfurt": "Άιντραχτ Φρανκφούρτης | Αϊντραχτ Φρανκφούρτης",
    "vfb-stuttgart": "Στουτγκάρδη", "borussia-monchengladbach": "Γκλάντμπαχ | Μπορούσια Μενχενγκλάντμπαχ",
    "vfl-wolfsburg": "Βόλφσμπουργκ", "sc-freiburg": "Φράιμπουργκ", "werder-bremen": "Βέρντερ Βρέμης | Βέρντερ",
    "union-berlin": "Ουνιόν Βερολίνου", "hamburger-sv": "Αμβούργο", "tsg-hoffenheim": "Χόφενχαϊμ", "fc-augsburg": "Άουγκσμπουργκ",
    "schalke-04": "Σάλκε", "1-fc-koln": "Κολωνία", "paris-saint-germain": "Παρί Σεν Ζερμέν | Παρί", "marseille": "Μαρσέιγ | Μαρσέιγ",
    "lyon": "Λιόν", "as-monaco": "Μονακό", "lille": "Λιλ", "ogc-nice": "Νις", "rc-lens": "Λανς", "stade-rennais": "Ρεν",
    "strasbourg": "Στρασβούργο", "fc-nantes": "Ναντ", "benfica": "Μπενφίκα", "fc-porto": "Πόρτο", "sporting-cp": "Σπόρτινγκ Λισαβόνας | Σπόρτινγκ",
    "sc-braga": "Μπράγκα", "ajax": "Άγιαξ", "psv-eindhoven": "Άιντχοφεν | Αϊντχόφεν", "feyenoord": "Φέγενορντ",
    "az-alkmaar": "Άλκμααρ | ΑΖ Άλκμααρ", "galatasaray": "Γαλατασαράι", "fenerbahce": "Φενέρμπαχτσε", "besiktas": "Μπεσίκτας",
    "trabzonspor": "Τράμπζονσπορ", "club-brugge": "Μπριζ | Κλαμπ Μπριζ", "anderlecht": "Άντερλεχτ", "red-bull-salzburg": "Σάλτσμπουργκ",
    "shakhtar-donetsk": "Σαχτάρ Ντονέτσκ | Σαχτάρ", "dinamo-zagreb": "Ντινάμο Ζάγκρεμπ", "red-star-belgrade": "Ερυθρός Αστέρας",
    "panathinaikos": "Παναθηναϊκός", "ofi-crete": "ΟΦΗ", "celtic": "Σέλτικ", "rangers": "Ρέιντζερς", "aberdeen": "Αμπερντίν",
    "motherwell": "Μάδεργουελ", "arsenal": "Άρσεναλ", "aston-villa": "Άστον Βίλα", "chelsea": "Τσέλσι", "liverpool": "Λίβερπουλ",
    "manchester-city": "Μάντσεστερ Σίτι", "manchester-united": "Μάντσεστερ Γιουνάιτεντ", "tottenham-hotspur": "Τότεναμ",
    "newcastle-united": "Νιούκαστλ", "west-ham-united": "Γουέστ Χαμ", "everton": "Έβερτον", "brighton-hove-albion": "Μπράιτον",
    "crystal-palace": "Κρίσταλ Πάλας", "fulham": "Φούλαμ", "brentford": "Μπρέντφορντ", "afc-bournemouth": "Μπόρνμουθ",
    "nottingham-forest": "Νότιγχαμ Φόρεστ", "wolverhampton-wanderers": "Γουλβς | Γουλβερχάμπτον", "leeds-united": "Λιντς",
    "burnley": "Μπέρνλι", "sunderland": "Σάντερλαντ", "nk-celje": "Τσέλιε", "heerenveen": "Χέρενφεν | Χέρενφεϊν",
    "nec-nijmegen": "Ναϊμέγκεν", "sparta-prague": "Σπάρτα Πράγας", "bodo-glimt": "Μπόντο Γκλιμτ", "legia-warsaw": "Λέγκια Βαρσοβίας | Λέγκια",
    "basel": "Βασιλεία", "lech-poznan": "Λεχ Πόζναν", "famalicao": "Φαμαλικάο", "vitoria-guimaraes": "Βιτόρια Γκιμαράες",
    "england": "Αγγλία", "scotland": "Σκωτία", "wales": "Ουαλία", "northern-ireland": "Βόρεια Ιρλανδία", "republic-of-ireland": "Ιρλανδία",
    "france": "Γαλλία", "germany": "Γερμανία", "spain": "Ισπανία", "italy": "Ιταλία", "portugal": "Πορτογαλία", "netherlands": "Ολλανδία",
    "belgium": "Βέλγιο", "brazil": "Βραζιλία", "argentina": "Αργεντινή", "united-states": "ΗΠΑ", "mexico": "Μεξικό", "croatia": "Κροατία",
    "denmark": "Δανία", "sweden": "Σουηδία", "norway": "Νορβηγία", "poland": "Πολωνία", "turkey": "Τουρκία", "switzerland": "Ελβετία",
    "austria": "Αυστρία", "morocco": "Μαρόκο", "japan": "Ιαπωνία", "south-korea": "Νότια Κορέα", "australia": "Αυστραλία",
    "uruguay": "Ουρουγουάη", "colombia": "Κολομβία", "finland": "Φινλανδία", "iceland": "Ισλανδία", "greece": "Ελλάδα",
    "serbia": "Σερβία", "czechia": "Τσεχία", "hungary": "Ουγγαρία", "romania": "Ρουμανία", "ukraine": "Ουκρανία", "slovakia": "Σλοβακία",
    "slovenia": "Σλοβενία", "albania": "Αλβανία", "bosnia-and-herzegovina": "Βοσνία-Ερζεγοβίνη | Βοσνία Ερζεγοβίνη",
    "north-macedonia": "Βόρεια Μακεδονία", "montenegro": "Μαυροβούνιο", "israel": "Ισραήλ", "bulgaria": "Βουλγαρία",
    "kazakhstan": "Καζακστάν", "azerbaijan": "Αζερμπαϊτζάν", "armenia": "Αρμενία", "estonia": "Εσθονία", "latvia": "Λετονία",
    "lithuania": "Λιθουανία", "faroe-islands": "Νήσοι Φερόες", "malta": "Μάλτα", "moldova": "Μολδαβία", "kosovo": "Κόσοβο",
    "belarus": "Λευκορωσία", "andorra": "Ανδόρα", "san-marino": "Άγιος Μαρίνος", "gibraltar": "Γιβραλτάρ", "liechtenstein": "Λιχτενστάιν",
    "luxembourg": "Λουξεμβούργο", "egypt": "Αίγυπτος", "algeria": "Αλγερία", "tunisia": "Τυνησία", "nigeria": "Νιγηρία",
    "senegal": "Σενεγάλη", "ghana": "Γκάνα", "cameroon": "Καμερούν", "canada": "Καναδάς", "chile": "Χιλή", "peru": "Περού",
    "ecuador": "Εκουαδόρ", "paraguay": "Παραγουάη", "iran": "Ιράν", "qatar": "Κατάρ", "saudi-arabia": "Σαουδική Αραβία",
    # NFL, as Greek guides (Cosmote, Nova) spell them; the sound match alone misses "Σιάτλ Σίχοκς"
    "arizona-cardinals": "Αριζόνα Κάρντιναλς", "atlanta-falcons": "Ατλάντα Φάλκονς", "baltimore-ravens": "Βαλτιμόρη Ρέιβενς | Μπάλτιμορ Ρέιβενς",
    "buffalo-bills": "Μπάφαλο Μπιλς", "carolina-panthers": "Καρολάινα Πάνθερς", "chicago-bears": "Σικάγο Μπέαρς",
    "cincinnati-bengals": "Σινσινάτι Μπένγκαλς", "cleveland-browns": "Κλίβελαντ Μπράουνς", "dallas-cowboys": "Ντάλας Κάουμποϊς",
    "denver-broncos": "Ντένβερ Μπρόνκος", "detroit-lions": "Ντιτρόιτ Λάιονς", "green-bay-packers": "Γκριν Μπέι Πάκερς | Γκρην Μπέι Πάκερς",
    "houston-texans": "Χιούστον Τέξανς", "indianapolis-colts": "Ιντιανάπολις Κολτς", "jacksonville-jaguars": "Τζάκσονβιλ Τζάγκουαρς",
    "kansas-city-chiefs": "Κάνσας Σίτι Τσιφς", "las-vegas-raiders": "Λας Βέγκας Ρέιντερς", "los-angeles-chargers": "Λος Άντζελες Τσάρτζερς",
    "los-angeles-rams": "Λος Άντζελες Ραμς", "miami-dolphins": "Μαϊάμι Ντόλφινς", "minnesota-vikings": "Μινεσότα Βάικινγκς",
    "new-england-patriots": "Νιού Ίνγκλαντ Πάτριοτς | Νιου Ινγκλαντ Πάτριοτς", "new-orleans-saints": "Νέα Ορλεάνη Σέιντς | Νιου Όρλινς Σέιντς",
    "new-york-giants": "Νιου Γιορκ Τζάιαντς | Νέα Υόρκη Τζάιαντς", "new-york-jets": "Νιου Γιορκ Τζετς | Νέα Υόρκη Τζετς",
    "philadelphia-eagles": "Φιλαδέλφεια Ίγκλς", "pittsburgh-steelers": "Πίτσμπουργκ Στίλερς",
    "san-francisco-49ers": "Σαν Φρανσίσκο 49ers | Σαν Φρανσίσκο Φόρτι Νάινερς", "seattle-seahawks": "Σιάτλ Σίχοκς",
    "tampa-bay-buccaneers": "Τάμπα Μπέι Μπουκανίρς | Τάμπα Μπέι Μπακανίαρς", "tennessee-titans": "Τενεσί Τάιτανς",
    "washington-commanders": "Ουάσιγκτον Κομάντερς",
}

ENTITIES = _load(DATA)


def in_sport(e: Entity, sport: int) -> bool:
    """Is this entity itself in that sport? A club only in its own (and its "also:" ones)."""
    return e.sport in (0, sport) or sport in e.also
BY_ID_KEY: dict[str, Entity] = {}          # stable id (and old ids) -> entity: what favourites resolve through
for _e in ENTITIES:
    for _k in (_e.key, *_e.was):
        if _k in BY_ID_KEY:
            raise ValueError(f"sports DATA: id {_k} used twice")
        BY_ID_KEY[_k] = _e
for _k, _names in GREEK_NAMES.items():
    _e = BY_ID_KEY[f"team:{_k}"]
    _e.names = list(dict.fromkeys(_e.names + [norm(n) for n in _names.split("|") if norm(n)]))
STRONG: dict[str, list[int]] = {}          # phrase -> entities (a phrase can only be strong for one)
WEAK: dict[str, list[int]] = {}
for _e in ENTITIES:
    for _p in _e.names:
        STRONG.setdefault(_p, []).append(_e.id)
    for _p in _e.weak:
        WEAK.setdefault(_p, []).append(_e.id)
# per sport: names that count only when the event is that sport (US leagues' cities and nicknames)
SCOPED: dict[int, dict[str, list[int]]] = {}
for _e in ENTITIES:
    for _p in _e.scoped:
        SCOPED.setdefault(_e.sport, {}).setdefault(_p, []).append(_e.id)
MAXLEN = max(len(p.split()) for p in list(STRONG) + list(WEAK))
_TERMS: dict[str, int] = {}
for _s, _txt in TERMS.items():
    for _p in _phrases(_txt):
        _TERMS.setdefault(_p, _s)
_SHOW = set(_phrases(SHOW_WORDS))
_REPLAY = set(_phrases(REPLAY_WORDS))
_LIVE = set(_phrases(LIVE_WORDS))
_TERMLEN = max(len(p.split()) for p in list(_TERMS) + list(_SHOW) + list(_REPLAY))


def _ok_context(e: Entity, words: list[str], i: int, j: int) -> bool:
    before = words[i - 1] if i > 0 else ""
    after = words[j] if j < len(words) else ""
    return before not in e.not_after and after not in e.not_before


def scan(words: list[str], weak: bool = False) -> list[tuple[int, int, int]]:
    """Entities named in a word list: [(start, end, entity id)], longest first, not overlapping.
    weak=True also accepts weak names (callers use it only for a whole match side or label)."""
    out = []
    i, n = 0, len(words)
    while i < n:
        hit = None
        for ln in range(min(MAXLEN, n - i), 0, -1):
            p = " ".join(words[i:i + ln])
            ids = STRONG.get(p) or (WEAK.get(p) if weak else None)
            if ids and len(ids) == 1 and _ok_context(ENTITIES[ids[0]], words, i, i + ln):
                hit = (i, i + ln, ids[0])
                break
        if hit:
            out.append(hit)
            i = hit[1]
        else:
            i += 1
    return out


def _find(words: list[str], table) -> list[tuple[int, int, object]]:
    out = []
    n = len(words)
    for i in range(n):
        for ln in range(min(_TERMLEN, n - i), 0, -1):
            p = " ".join(words[i:i + ln])
            if p in table:
                out.append((i, i + ln, table[p] if isinstance(table, dict) else p))
                break
    return out


def sport_word(words: list[str]) -> int:
    """The sport a sport word names: the first one, except that any NFL word wins over "football"
    ("Monday Night Football ... NFL")."""
    hits = [h[2] for h in _find(words, _TERMS)]
    if not hits:
        return 0
    return NFL if NFL in hits and hits[0] == FOOTBALL else hits[0]


def has_any(words: list[str], table: set) -> bool:
    return bool(_find(words, table))


# ---- Greek sides not in GREEK_NAMES: transliterate, then match by sound against the clubs' and
# countries' Latin names ("Ουντινέζε" -> oudineze -> Udinese). Only a single clear candidate counts.
_GREEK = re.compile(r"[\u0370-\u03ff\u1f00-\u1fff]")
_GR_START = (("μπ", "b"), ("ντ", "d"), ("γκ", "g"))
_GR_DI = (("μπ", "b"), ("ντ", "nt"), ("γκ", "g"), ("γγ", "ng"), ("τσ", "ts"), ("τζ", "tz"), ("ου", "ou"), ("αι", "e"),
          ("ει", "i"), ("οι", "i"), ("υι", "i"), ("αυ", "av"), ("ευ", "ev"))
_GR_ONE = dict(zip("αβγδεζηθικλμνξοπρσςτυφχψω", ("a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "x", "o",
                                                  "p", "r", "s", "s", "t", "i", "f", "ch", "ps", "o")))
_PHON = (("ph", "f"), ("th", "t"), ("ch", "k"), ("ck", "k"), ("c", "k"), ("q", "k"), ("w", "v"), ("y", "i"), ("j", "i"),
         ("z", "s"), ("x", "ks"), ("ou", "u"), ("ae", "e"), ("oe", "e"), ("ei", "i"))


def greek_latin(text: str, nt: str = "nt") -> str:
    """'Ντόρτμουντ' -> 'dortmount': Greek letters as they sound (digraphs first, word-initial ντ = d;
    inside a word ντ is "nt" (Αταλάντα) or "d" (Ουντινέζε): nt= picks)."""
    out = []
    for w in norm(text).split():
        w = re.sub(r"γι(?=[αεηιοωυ])", "i", w)                 # Γιουβέντους: "yu"
        for a, b in _GR_START:
            if w.startswith(a):
                w = b + w[2:]
        for a, b in _GR_DI:
            w = w.replace(a, nt if a == "ντ" else b)
        out.append("".join(_GR_ONE.get(c, c) for c in w))
    return " ".join(out)


def _phon(text: str) -> str:
    t = "".join(text.split())
    for a, b in _PHON:
        t = t.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", t)


def _lev(a: str, b: str, cap: int) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


_SOUNDS: dict[str, set[int]] | None = None        # sound key of a Latin name (or a distinctive word of one) -> entities


def _sounds() -> dict[str, set[int]]:
    global _SOUNDS
    if _SOUNDS is None:
        whole: dict[str, set[int]] = {}
        words: dict[str, set[int]] = {}
        for e in ENTITIES:
            if e.kind not in ("club", "national"):
                continue
            for n in e.names:
                if _GREEK.search(n):
                    continue
                ws = [w for w in n.split() if w not in GENERIC]
                for k in {_phon(n), _phon(" ".join(ws))}:
                    whole.setdefault(k, set()).add(e.id)
                for w in ws:
                    if len(w) >= 6:
                        words.setdefault(_phon(w), set()).add(e.id)
        for k, ids in words.items():                            # a word only one team uses ("dortmund")
            if len(ids) == 1:
                whole.setdefault(k, set()).update(ids)
        _SOUNDS = whole
    return _SOUNDS


def greek_side(words: list[str]) -> int:
    """A Greek side -> entity id, or -1 unless exactly one club/country sounds like it."""
    text = " ".join(w for w in words if w not in GENERIC)
    hits = {i for nt in ("nt", "d") if (i := _greek_one(_phon(greek_latin(text, nt)))) >= 0}
    return hits.pop() if len(hits) == 1 else -1


def _greek_one(key: str) -> int:
    idx = _sounds()
    if len(idx.get(key, ())) == 1:
        return next(iter(idx[key]))
    if len(key) < 6:
        return -1
    cap = 1 if len(key) < 9 else 2
    found: dict[int, set[int]] = {}
    for k, ids in idx.items():
        if len(k) >= 5:
            d = _lev(key, k, cap)
            if d <= cap:
                found.setdefault(d, set()).update(ids)
    if not found:
        return -1
    best = found[min(found)]
    return next(iter(best)) if len(best) == 1 else -1


def resolve_side(side: str, sport: int = 0) -> tuple[int, str, bool]:
    """A match side -> (entity id or -1, key text, women). Weak names count here: a whole side.
    sport: the event's, when known - then that sport's own names come first ("Spurs" in the NBA)."""
    words = norm(side).split()
    whole = STRONG.get(" ".join(words)) or WEAK.get(" ".join(words))
    # a team whose own name ends in a women's marker ("Cong An Ha Noi": "noi") keeps it
    women = bool(words) and words[-1] in WOMEN_WORDS and not whole
    while words and words[-1] in WOMEN_WORDS and not whole:
        words.pop()
    text = " ".join(words)
    own = SCOPED.get(sport, {})
    for cand in (text, " ".join(w for w in words if w not in GENERIC)):
        ids = own.get(cand)
        if ids and len(ids) == 1:
            return ids[0], ENTITIES[ids[0]].key, women
    for cand in (text, " ".join(w for w in words if w not in GENERIC)):
        ids = STRONG.get(cand) or WEAK.get(cand)
        if ids and len(ids) == 1 and ENTITIES[ids[0]].kind in ("club", "national"):
            return ids[0], ENTITIES[ids[0]].key, women
    if _GREEK.search(text):
        i = greek_side(words)
        if i >= 0:
            return i, ENTITIES[i].key, women
    key = " ".join(w for w in words if w not in GENERIC)
    return -1, key, women


def split_match(title: str) -> tuple[str, str, str, bool] | None:
    """'LaLiga 2026/27: Rayo Vallecano vs Athletic Bilbao' -> (label, left, right, dashed).
    label: whatever came before the teams (competition, sport word); dashed: "A - B" form."""
    t = _PAREN.sub(" ", title)
    t = _LEADLIVE.sub("", t)
    segs = _LABEL.split(t)
    for k in range(len(segs) - 1, -1, -1):
        seg = segs[k]
        m = _VS.search(f" {seg} ")
        dashed = False
        if not m:
            m = _DASH.search(seg)
            dashed = True
            if not m:
                # "Arsenal-Lille": a bare hyphen, only between two known teams
                parts = _HYPHEN.split(seg.split(",")[0])
                if len(parts) == 2 and all(resolve_side(_TAIL.split(x, 1)[0])[0] >= 0 for x in parts):
                    left, right = (_TAIL.split(x, 1)[0] for x in parts)
                    return " ".join(segs[:k]), left.strip(), right.strip(), True
                continue
            left, right = seg[:m.start()], seg[m.end():]
        else:
            left, right = f" {seg} "[:m.start()], f" {seg} "[m.end():]
            d = list(_DASH.finditer(left))
            if d:                                   # "Football - Arsenal v Chelsea"
                left = left[d[-1].end():]
        right = _DASH.split(right, 1)[0].split(",")[0].split("|")[0]
        right = _TAIL.split(right, 1)[0]
        left = _TAIL.split(left, 1)[0] if dashed else left
        label = " ".join(segs[:k])
        stage = _STAGE.match(left.strip())                 # "4th Test England vs India": the stage is not a side
        if stage:
            label, left = (label + " " + stage.group(0)).strip(), left.strip()[stage.end():]
        if left.strip() and right.strip():
            return label, left.strip(" -–"), right.strip(" -–"), dashed
        return None
    return None


class Info:
    """What a programme is, as far as sport goes."""
    __slots__ = ("sport", "kind", "key", "comp", "teams", "women", "youth", "replay", "live", "explicit", "names",
                 "dated", "from_desc", "comp_desc")

    def __init__(self):
        self.sport = 0
        self.kind = 0
        self.key = ""
        self.comp = -1
        self.teams = (-1, -1)
        self.women = False
        self.youth = False
        self.replay = False
        self.from_desc = False                    # the teams were found in the description, not the title
        self.comp_desc = False                    # the competition too
        self.dated = 0                            # a date in the title (YYYYMMDD): a replay unless it is today
        self.live = False
        self.explicit = False                     # the sport was named (a sport word or competition)
        self.names = ("", "")                     # sides as written, for display


_MAYBE = re.compile(r"\s(?:v|vs|vs\.|x|@)\s|\s[-–—/]\s|:|[^\W\d_]-[^\W\d_]", re.I)


def worth_classifying(title: str, channel_sport: int) -> bool:
    """Cheap pre-check: off sports channels, only titles shaped like a match or with a label."""
    return bool(channel_sport) or bool(_MAYBE.search(title))


def classify(title: str, desc: str, channel_sport: int = 0) -> Info | None:
    """None if the programme isn't recognisably sport. channel_sport: 0 not a sports channel,
    OTHER a sports channel, or the sport its name says (FOOTBALL for "LaLiga TV")."""
    tw = norm(title).split()
    if not tw:
        return None
    info = Info()
    info.replay = has_any(tw, _REPLAY) or "(r)" in title.lower() or "(rep)" in title.lower()
    if re.search(r"\((?:w|women|womens|ž|f|fem)\)", title, re.I):
        info.women = True
    m = _DATE.search(title)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        if 1 <= d <= 31 and 1 <= mo <= 12:
            info.dated = y * 10000 + mo * 100 + d
    info.live = bool(_LEADLIVE.match(title)) or has_any(tw[:2], _LIVE)
    show = has_any(tw, _SHOW)
    term = sport_word(tw)
    ents = scan(tw)
    comps = [ENTITIES[e] for _, _, e in ents if ENTITIES[e].kind == "competition"]
    pair = split_match(title)
    teams = (-1, -1)
    clubby = False
    sides: list[str] = []
    if pair:
        label, left, right, dashed = pair
        # the sport as far as the title, its competition or the channel say, for sport-only names
        hint = term or sport_word(norm(label).split()) or next((c.sport for c in comps if c.sport), 0) or \
            (channel_sport if channel_sport != OTHER else 0)
        # the sport-only names are the men's leagues' teams: a WNBA "Golden State" is not the Warriors
        if any(c.key == "comp:wnba" for c in comps) or any(w in WOMEN_WORDS or w == "womens" for w in tw):
            hint = 0
        a, ka, wa = resolve_side(left, hint)
        b, kb, wb = resolve_side(right, hint)
        lw = norm(label).split()
        if not comps and lw:
            comps = [ENTITIES[e] for _, _, e in scan(lw, weak=True) if ENTITIES[e].kind == "competition"]
        term = term or sport_word(lw)
        if term:
            comps = [c for c in comps if c.sport in (0, term)]
        known = (a >= 0) + (b >= 0)
        lw_side = norm(left).split() + norm(right).split()
        not_team = any(sport_word(norm(x).split()) or has_any(norm(x).split(), _SHOW) or _NOT_A_SIDE.match(norm(x)) or
                       any(ENTITIES[e].kind == "competition" for _, _, e in scan(norm(x).split(), weak=True))
                       for x, k in ((left, a), (right, b)) if k < 0)
        clubby = any(w in CLUB_WORDS for w in lw_side)
        long_side = max(len(norm(left).split()), len(norm(right).split())) > 6
        evidence = bool(term or comps or known == 2 or channel_sport)
        if term == F1 or any(c.sport == F1 for c in comps):
            pair = None                              # "Formel 1: Rennen - GP Singapur": no teams in F1
        elif dashed and not (known == 2 or ((term or comps) and channel_sport)):
            pair = None
        elif long_side or ka == kb or not evidence or not_team:
            pair = None
        else:
            teams = (a, b)
            info.women = info.women or wa or wb or any(w in WOMEN_WORDS for w in lw if w not in ("w",))
            info.youth = any(w in YOUTH_WORDS for w in tw) or "b" in (norm(left).split()[-1:] + norm(right).split()[-1:])
            info.names = (left, right)
            sides = sorted([ka, kb])
    dw: list[str] = []
    if not term or not comps:
        dw = norm(desc[:300]).split() if desc else []
    if not term and dw and (pair or comps or channel_sport):
        term = sport_word(dw)
        # the sport only the description gives ("Seahawks vs Broncos", "NFL ..."): the names that count
        # only in that sport (US teams' nicknames) are matched again with it
        if term and pair and info.names and min(teams) < 0 and term in SCOPED:
            a, ka, wa = resolve_side(info.names[0], term)
            b, kb, wb = resolve_side(info.names[1], term)
            if a >= 0 and b >= 0 and ka != kb:
                teams = (a, b)
                sides = sorted([ka, kb])
    if not comps and dw and (pair or term or channel_sport):
        comps = [ENTITIES[e] for _, _, e in scan(dw) if ENTITIES[e].kind == "competition"]
        info.comp_desc = bool(comps)
    title_comp = any(ENTITIES[e].kind == "competition" for _, _, e in ents)
    if term:
        comps = [c for c in comps if c.sport in (0, term)]   # "Rugby ... Championship" isn't the EFL's
    comp = comps[0] if comps else None
    # "Premier League" with "...reigning champions Arsenal host Leeds United" in the description
    if not pair and comp and title_comp and not show and dw and len(tw) <= len(comp.name.split()) + 2:
        # clubs only: countries in a description are places ("From Arsenal Stadium - London, England")
        clubs = list(dict.fromkeys(e for _, _, e in scan(dw) if ENTITIES[e].kind == "club"))
        if len(clubs) == 2 and not has_any(dw, _SHOW):
            teams = (clubs[0], clubs[1])
            sides = sorted([ENTITIES[clubs[0]].key, ENTITIES[clubs[1]].key])
            info.names = (ENTITIES[clubs[0]].name, ENTITIES[clubs[1]].name)
            info.from_desc = True
            pair = ("", "", "", False)
    # the sport, strongest evidence first
    sport = term or (comp.sport if comp else 0)
    info.explicit = bool(sport)
    if not sport and pair:
        club_sports = {ENTITIES[t].sport for t in teams if t >= 0 and ENTITIES[t].kind == "club"}
        if len(club_sports) == 1:
            sport = club_sports.pop()
        elif channel_sport and channel_sport != OTHER:
            sport = channel_sport
        elif clubby:
            sport = FOOTBALL
    if not sport and not pair:
        if channel_sport and channel_sport != OTHER and not show and ents:
            sport = channel_sport
        else:
            return None
    info.sport = sport or OTHER
    info.comp = comp.id if comp else -1
    if info.explicit:
        # "NBA: Spurs v Lakers" is not Tottenham: a club is that club only in its own sport. (The
        # event key keeps the names, so the same game listed without a sport word still merges.)
        teams = tuple(t if t < 0 or in_sport(ENTITIES[t], info.sport) else -1 for t in teams)
    info.teams = teams
    if comp and any(w in YOUTH_WORDS for w in comp.names[0].split()):
        info.youth = True                            # "Leipzig v PSV", description "UEFA Youth League"
    if comp and any(w in WOMEN_WORDS for w in comp.names[0].split()):
        info.women = True                            # "Chelsea v Arsenal" in the Women's Super League
    if pair and sport == F1:
        info.kind = SHOW                             # F1 has no head-to-heads: "Brad Pitt vs McLaren" is a feature
        info.key = "|".join(sides)
    elif pair:
        info.kind = SHOW if show else MATCH
        info.key = ("w|" if info.women else "") + ("y|" if info.youth else "") + "|".join(sides)
    elif sport == F1:
        f1_title = sport_word(tw) == F1 or comp is not None and comp.sport == F1 and title_comp
        session = (_f1_session(tw) or (_f1_session(dw) if dw else "")) if f1_title else ""
        info.kind = EVENT if session and not show else SHOW
        info.key = "f1|" + (session or norm(title))
    elif sport == MMA and not show and re.search(r"\b(ufc \d+|fight night|main card|prelims|pfl \d+)\b", " ".join(tw)):
        info.kind = EVENT
        info.key = norm(title)
    elif sport == TENNIS and not show and comp and (info.live or re.search(
            r"\b(atp|wta|masters|open|finals?|cup|round|ronda|turniej|torneo|tournoi|\d{3,4})\b", " ".join(tw))):
        info.kind = EVENT
        info.key = norm(title)
    else:
        info.kind = SHOW
        info.key = norm(title)
    return info


_F1 = [("sprint qualifying", "sprint-qualifying"), ("sprint shootout", "sprint-qualifying"), ("sprint", "sprint"),
       ("qualifying", "qualifying"), ("qualification", "qualifying"), ("clasificacion", "qualifying"),
       ("qualifiche", "qualifying"), ("quali", "qualifying"), ("kwalificatie", "qualifying"),
       ("practice", "practice"), ("fp1", "practice"), ("fp2", "practice"), ("fp3", "practice"),
       ("libres", "practice"), ("entrenamientos", "practice"), ("libere", "practice"), ("training", "practice"),
       ("race", "race"), ("carrera", "race"), ("corrida", "race"), ("gara", "race"), ("rennen", "race"),
       ("course", "race"), ("wyscig", "race"), ("main race", "race")]


def _f1_session(words: list[str]) -> str:
    text = f" {' '.join(words)} "
    for w, s in _F1:
        if f" {w} " in text:
            return s
    return ""


def display_title(info: Info, title: str) -> str:
    """'Arsenal vs Leeds United' for a recognised match; the guide's title otherwise."""
    if info.kind != MATCH:
        return title
    a, b = info.teams

    def side(e: int, raw: str) -> str:
        # a club's name only in its own sport: basketball's "Valencia" isn't Valencia CF
        if e >= 0 and (in_sport(ENTITIES[e], info.sport) or not info.explicit):
            return ENTITIES[e].name
        return _tidy(raw) or (ENTITIES[e].name if e >= 0 else "")
    left, right = side(a, info.names[0]), side(b, info.names[1])
    women = " (W)" if info.women else ""
    return f"{left}{women} vs {right}{women}"


def _tidy(side: str) -> str:
    side = re.sub(r"\s+", " ", side).strip(" -–:")
    return side.title() if side.isupper() and len(side) > 4 else side


# ------------------------------------------------------------------ search-side aliases
def query_groups(words: list[str]) -> list[tuple[int, int, int]]:
    """Entities named in a typed query: strong names, and weak names that belong to one entity
    (typing "Spurs" means Tottenham). Only whole typed words count ("man ut" is not yet anything)."""
    out = []
    i, n = 0, len(words)
    while i < n:
        hit = None
        for ln in range(min(MAXLEN, n - i), 0, -1):
            p = " ".join(words[i:i + ln])
            ids = STRONG.get(p) or WEAK.get(p)
            if ids and len(ids) == 1:
                hit = (i, i + ln, ids[0])
                break
        if hit:
            out.append(hit)
            i = hit[1]
        else:
            i += 1
    return out


def phrase_ok(e: Entity, text_words: list[str], start: int, length: int) -> bool:
    return _ok_context(e, text_words, start, start + length)


_FOOTBALL_CH = re.compile(r"\b(laliga|la liga|premier league|serie a|bundesliga|ligue 1|eredivisie|mutv|lfctv|lfc tv|"
                          r"chelsea tv|barca tv|real madrid tv|sky sports football|sky sports premier league|"
                          r"canal\+ foot|foot\+|liga portugal|benfica tv|sporting tv|porto canal|ziggo sport voetbal)\b")
_SPORT_CH = re.compile(r"\b(sports?|sport\d|bein|supersport|dazn|arena sport|sport klub|sportklub|eleven|sportdigital|"
                       r"ziggo|viaplay|v sport|cosmote|nova sport|polsat sport|cytavision|setanta|ssc|alkass|ad sport|"
                       r"on time sport|digi sport|prima sport|tnt sports?|premier sports|sky sport|movistar|m\+|"
                       r"espn|tsn|fox sports|stan sport|optus sport|astro|hub|tvn|canal\+ sport|rmc sport|"
                       r"eurosport|matchroom|ufc|nba|nfl|f1|motors? ?tv)\b")


def channel_sport(name: str, category: str) -> int:
    """What a channel says about its sport: FOOTBALL for "LaLiga TV", "V Fotboll", "MUTV"; another
    sport by its sport word ("NBA TV"); OTHER for a sports channel without one; 0 otherwise."""
    words = norm(name).split()
    s = sport_word(words)
    if s:
        return s
    text = " ".join(words)
    if _FOOTBALL_CH.search(text):
        return FOOTBALL
    if _SPORT_CH.search(text) or _SPORT_CH.search(norm(category)):
        return OTHER
    return 0
