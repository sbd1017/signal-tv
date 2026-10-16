"""More like this: titles similar to a series or a film, from what the provider's own catalogue says.

Series come with a genre and a description (95% of them, in the get_series list), so a series is
compared by: shared genres, the distinctive words the descriptions share ("sitcom", "radio",
"Brooklyn" - weighted by how rare they are across the catalogue), how close the years are, and a
little by rating. Films have no genre in the list; the film's own (its details, fetched when its page
opens) is matched against categories named after a genre ("EN - COMEDY", "EN - HORROR"), then by year
and rating.

Only titles in the same language as the one shown (its catalogue label, EN / DE / GR..., unlabelled
with unlabelled), never another version of the same title, one version per title. Nothing leaves
the Pi; the word index is built once per catalogue version, in a worker thread.
"""
from __future__ import annotations

import math
import re
import unicodedata

PREFIX = re.compile(r"^([A-Z0-9+&]{1,6}(?:-[A-Z0-9+&]{1,6}){0,3})\s+[-|:]\s+(?=\S)")
TAIL = re.compile(r"\s*\((\d{4}|[A-Z]{2})\)\s*$")
WORD = re.compile(r"[a-z][a-z'-]{2,}")
ENGLISH = {"EN", "UK", "US", "AF-EN"}
# words every description uses: never evidence of a likeness
STOP = set("""the and for with from that this his her their they them she him who whom whose when where while which what into
onto over under after before about against between through during without within upon also just only even still very more most
much many some such than then there these those other another each every both all any few own same new old young first last
one two three four five life lives world story stories series season seasons episode episodes show shows film films movie
movies follows follow following find finds found must take takes make makes get gets set sets lead leads way back down out
will would can could may might should been being have has had are was were not but are its it's our your you we what's
after year years day days time times man men woman women people family friends friend group home live lives turn turns become
becomes help helps try tries begin begins discover discovers face faces begin each own true real""".split())
GENRE_WORDS = {
    "action": "action", "adventure": "adventure", "animation": "animation", "anime": "animation", "manga": "animation",
    "cartoon": "animation", "comedy": "comedy", "sitcom": "comedy", "crime": "crime", "documentary": "documentary",
    "documentaries": "documentary", "drama": "drama", "family": "family", "kids": "family", "children": "family",
    "fantasy": "fantasy", "history": "history", "historical": "history", "horror": "horror", "music": "music",
    "musical": "music", "concerts": "music", "mystery": "mystery", "romance": "romance", "romantic": "romance",
    "sci-fi": "science fiction", "scifi": "science fiction", "science fiction": "science fiction", "thriller": "thriller",
    "war": "war", "western": "western", "westerns": "western", "reality": "reality", "talk": "talk", "news": "news",
    "soap": "soap", "biography": "biography", "sport": "sport", "suspense": "thriller",
}


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower()
    return "".join(c for c in text if not unicodedata.combining(c))


def label(name: str) -> tuple[str, str]:
    """"EN - Martin (1992)" -> ("EN", "martin"): the language label (4K-/-HDR dropped) and the title."""
    m = PREFIX.match(name or "")
    code = ""
    rest = name or ""
    if m:
        code = re.sub(r"^(4K|8K|UHD)-|-(HDR|DV|DO|TOP)$", "", m.group(1).upper())
        rest = rest[m.end():]
    for _ in range(3):
        rest = TAIL.sub("", rest)
    code = "EN" if code in ENGLISH else code
    return code, re.sub(r"[^a-z0-9]+", " ", fold(rest)).strip()


def genres(text: str) -> frozenset:
    out = set()
    low = fold(text)
    for part in re.split(r"[,/&|;]| - ", low):
        p = part.strip()
        if not p:
            continue
        if p in GENRE_WORDS:
            out.add(GENRE_WORDS[p])
            continue
        for w, g in GENRE_WORDS.items():
            if re.search(rf"\b{re.escape(w)}\b", p):
                out.add(g)
    return frozenset(out)


def genre_order(text: str) -> list[str]:
    """Genres in the order given: a film's first genre is what it mostly is ("Action, Crime, Drama")."""
    out: list[str] = []
    for part in re.split(r"[,/&|;]| - ", fold(text)):
        for g in sorted(genres(part)):
            if g not in out:
                out.append(g)
    return out


def words(text: str) -> set:
    return {w.strip("'-") for w in WORD.findall(fold(text)) if w not in STOP and len(w.strip("'-")) > 2}


class Similar:
    def __init__(self):
        self.version = None
        self.series: dict = {}        # id -> (code, title, genres, keywords, year, rating)
        self.idf: dict = {}

    def prepare(self, data: dict, version: str, keep: int = 12) -> None:
        """The series index for one catalogue version: per series its best `keep` words by rarity."""
        if version == self.version:
            return
        docs = {}
        df: dict[str, int] = {}
        for s in data.get("series", []):
            ws = words(s.get("plot", ""))
            docs[s["id"]] = ws
            for w in ws:
                df[w] = df.get(w, 0) + 1
        n = max(1, len(docs))
        idf = {w: math.log(n / c) for w, c in df.items() if c > 1}           # a word in one description only can't link two
        index = {}
        for s in data.get("series", []):
            code, title = label(s.get("name", ""))
            kw = sorted((w for w in docs[s["id"]] if w in idf and df[w] < n * 0.05), key=lambda w: -idf[w])[:keep]
            index[s["id"]] = (code, title, genres(s.get("genre", "")), frozenset(kw), int(s.get("year") or 0),
                              float(s.get("rating") or 0))
        self.series, self.idf, self.version = index, idf, version

    def like_series(self, sid: str, n: int = 18) -> list[str]:
        me = self.series.get(sid)
        if not me:
            return []
        code, title, gen, kw, year, _ = me
        mine = sum(self.idf.get(w, 0) for w in kw) or 1.0
        best: dict[str, tuple[float, str]] = {}                  # title -> (score, id): one version per title
        for oid, (c, t, g, k, y, r) in self.series.items():
            if oid == sid or c != code or t == title or not t:
                continue
            shared_g = len(gen & g)
            shared_w = kw & k
            if not shared_g and not shared_w:
                continue
            words_sim = sum(self.idf.get(w, 0) for w in shared_w) / math.sqrt(mine * (sum(self.idf.get(w, 0) for w in k) or 1.0))
            score = 2.0 * (shared_g / len(gen | g) if gen | g else 0) + 3.0 * words_sim
            if year and y:
                score += 0.45 * max(0.0, 1 - abs(year - y) / 15)
            score += 0.03 * min(r, 10)
            if score > best.get(t, (0.0, ""))[0]:
                best[t] = (score, oid)
        ranked = sorted(best.values(), key=lambda x: -x[0])
        return [oid for score, oid in ranked[:n] if score >= 1.0]

    @staticmethod
    def like_film(data: dict, film: dict, film_genre: str, n: int = 18) -> list[str]:
        """Films in the same language whose category is one of this film's genres (or its own category)."""
        code, title = label(film.get("name", ""))
        order = genre_order(film_genre) or genre_order(data["cats"]["movie"].get(film.get("cat", ""), ""))
        weight = {g: 1.0 / (1 + 0.6 * i) for i, g in enumerate(order)}      # its first genre counts most
        gen = frozenset(order)
        cat_genres = {k: genres(v) for k, v in data["cats"]["movie"].items()}
        year = int(film.get("year") or 0)
        best: dict[str, tuple[float, str]] = {}
        for f in data.get("movie", []):
            if f["id"] == film["id"]:
                continue
            cg = cat_genres.get(f.get("cat", ""), frozenset())
            same_cat = f.get("cat") == film.get("cat") and bool(cg)
            if not (gen & cg) and not same_cat:
                continue
            c, t = label(f.get("name", ""))
            if c != code or t == title or not t:
                continue
            y = int(f.get("year") or 0)
            score = 3.0 * sum(weight[g] for g in gen & cg) + (0.5 if same_cat else 0)
            if year and y:
                score += 1.2 * max(0.0, 1 - abs(year - y) / 12)
            score += 0.12 * min(float(f.get("rating") or 0), 10)
            if score > best.get(t, (0.0, ""))[0]:
                best[t] = (score, f["id"])
        return [fid for _, fid in sorted(best.values(), key=lambda x: -x[0])[:n]]
