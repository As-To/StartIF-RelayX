
import re
import sys
import json
import io
import time
import argparse
import logging
from pathlib import Path
from urllib.parse import urljoin

import requests
import pdfplumber
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

BASE_URL  = "https://health.ec.europa.eu"
LIST_PATH = "/latest-updates_en"
HEADERS   = {"User-Agent": "Mozilla/5.0 (compatible; SCCSScraper/8.0)"}
DELAY     = 1.2
LAST_PAGE = 637

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sccs_scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def fetch(url, timeout=25):
    time.sleep(DELAY)
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r

def fetch_bytes(url):
    time.sleep(DELAY)
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.content

def abs_url(href):
    return urljoin(BASE_URL, href)

def clean(text):
    """Nettoie les espaces, tirets conditionnels et caractères invisibles."""
    text = re.sub(r"[\u00ad\u200b\u200c\u200d\ufeff]", "", str(text))
    # Normalise les tirets longs en tiret simple pour faciliter les regex
    text = re.sub(r"[–—\u2013\u2014]", "-", text)
    return re.sub(r"\s+", " ", text).strip()

def split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases individuelles."""
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 15]

# ──────────────────────────────────────────────────────────────
# Filtre & détection du type
# ──────────────────────────────────────────────────────────────

def is_sccs(title, url):
    """
    Détecte si un article est du SCCS.
    Cas couverts :
      - URL contient /sccs- ou /sccs_
      - Titre commence par "SCCS" suivi d'un espace, tiret, virgule ou fin
        ex: "SCCS opinion...", "SCCS - Request...", "SCCS/1234/22"
    """
    if re.search(r"/sccs[-_]", url, re.I):
        return True
    # v8 : autoriser tiret/espace/slash après SCCS en début de titre
    if re.search(r"^sccs[\s\-/,]", title.strip(), re.I):
        return True
    return False

DOC_TYPES = [
    ("Addendum",          re.compile(r"\baddendum\b", re.I)),
    ("Scientific Advice", re.compile(r"\bscientific\s+advice\b", re.I)),
    ("Final Opinion",     re.compile(
        r"\bfinal\s+opinion\b|\bopinion\s+on\b|\bscientific\s+opinion\b"
        r"|\bpreliminary\s+opinion\b|\brequest\s+for\s+a\s+scientific\b",
        re.I)),
]

def detect_doc_type(title, url=""):
    for dtype, pat in DOC_TYPES:
        if pat.search(f"{title} {url}"):
            return dtype
    return None

# ──────────────────────────────────────────────────────────────
# Collecte Playwright
# ──────────────────────────────────────────────────────────────

def collect_articles_playwright(max_pages):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("pip install playwright && playwright install chromium")
        sys.exit(1)

    articles = []
    limit    = min(LAST_PAGE, max_pages - 1) if max_pages else LAST_PAGE

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        pg      = browser.new_page()

        for page_num in range(0, limit + 1):
            url = f"{BASE_URL}{LIST_PATH}?page={page_num}"
            log.info(f"  📋 Page {page_num}/{limit}")
            try:
                pg.goto(url, wait_until="networkidle", timeout=45_000)
                # v8 : timeout augmenté à 20s + fallback sur HTML brut si timeout
                try:
                    pg.wait_for_selector("article.ecl-content-item", timeout=20_000)
                except Exception:
                    # Le sélecteur n'est pas apparu — on parse quand même le HTML actuel
                    log.warning(f"  ⚠ Page {page_num} : sélecteur timeout, parse HTML brut")
            except Exception as e:
                log.warning(f"  ⚠ Page {page_num} goto échoué : {e}")
                continue

            soup     = BeautifulSoup(pg.content(), "html.parser")
            all_arts = _parse_page(soup)
            kept     = []
            for a in all_arts:
                if not is_sccs(a["title"], a["url"]):
                    continue
                dt = detect_doc_type(a["title"], a["url"])
                if dt:
                    a["doc_type"] = dt
                    kept.append(a)
            articles.extend(kept)
            log.info(f"       {len(all_arts)} total | {len(kept)} retenus")

        browser.close()
    return articles


def _parse_page(soup):
    results = []
    for art in soup.find_all("article", class_="ecl-content-item"):
        title_div = art.find("div", class_="ecl-content-block__title")
        a_tag     = (title_div or art).find("a", href=True)
        if not a_tag:
            continue
        title = clean(a_tag.get_text())
        href  = abs_url(a_tag["href"])
        if not title:
            continue
        time_tag  = art.find("time")
        card_date = time_tag.get("datetime", "") if time_tag else ""
        results.append({"title": title, "url": href, "card_date": card_date})
    return results

# ──────────────────────────────────────────────────────────────
# PDF → texte + sections
# ──────────────────────────────────────────────────────────────

SECTION_ANCHORS = {
    "ABSTRACT":    [r"1\.\s*ABSTRACT", r"\bABSTRACT\b"],
    # CORRECTION v7 : "CONCLUSIONS" (avec S) ajouté
    "CONCLUSION":  [r"\d+\.\s*CONCLUSION[S]?\b", r"\bCONCLUSION[S]?\b"],
    "OPINION":     [r"\bOPINION\b"],
    "SUMMARY":     [r"\bSUMMARY\b"],
}

def pdf_to_text(pdf_bytes):
    pages = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for p in pdf.pages:
            raw = p.extract_text(x_tolerance=2, y_tolerance=3) or ""
            pages.append(clean(raw))
    return " ".join(pages)

def extract_sections(full):
    hits = []
    for name, pats in SECTION_ANCHORS.items():
        for pat in pats:
            for m in re.finditer(pat, full, re.IGNORECASE):
                hits.append((m.start(), name, m.end()))
    hits.sort(key=lambda x: x[0])
    sections = {}
    for idx, (_, name, end) in enumerate(hits):
        nxt     = hits[idx + 1][0] if idx + 1 < len(hits) else end + 2500
        content = clean(full[end:min(nxt, end + 2500)])
        if name not in sections or len(content) > len(sections[name]):
            sections[name] = content
    return sections

# ──────────────────────────────────────────────────────────────
# Extraction : Date
# ──────────────────────────────────────────────────────────────

MONTHS    = (r"January|February|March|April|May|June|July|August|"
             r"September|October|November|December")
MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}
DATE_PATS = [
    rf"\b(\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}})\b",
    rf"\b((?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}})\b",
    r"\b(\d{4}-\d{2}-\d{2})\b",
]

def normalise_date(raw):
    m = re.match(rf"(\d{{1,2}})\s+({MONTHS})\s+(\d{{4}})", raw, re.IGNORECASE)
    if m:
        return f"{m.group(3)}-{MONTH_MAP[m.group(2).lower()]}-{m.group(1).zfill(2)}"
    return raw

def extract_date(text):
    for pat in DATE_PATS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            ctx = text[max(0, m.start() - 80):m.end() + 10].lower()
            if any(k in ctx for k in ("adopted", "opinion", "final", "meeting", "issued")):
                return normalise_date(m.group(1))
    for pat in DATE_PATS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return normalise_date(m.group(1))
    return None

# ──────────────────────────────────────────────────────────────
# Extraction : SCCS Number
# ──────────────────────────────────────────────────────────────

def extract_sccs_number(text):
    m = re.search(r"SCCS[/_\-](\d{3,4}[/_\-]\d{2})\b", text)
    if m:
        return "SCCS/" + m.group(1).replace("_", "/").replace("-", "/")
    m = re.search(r"(SCCS/\d{3,4}/\d{2})\b", text)
    return m.group(1) if m else None

# ──────────────────────────────────────────────────────────────
# Extraction : Ingredient — v7 CORRIGÉ
#
# Problèmes v6 :
#   - Patterns trop restrictifs (guillemets ou mots-clés obligatoires)
#   - Borne de fin $ capturait des trailers parasites
#   - Tirets longs (–/—) mal gérés dans les PDFs
#
# Corrections v7 :
#   - 8 patterns titre avec bornes de fin plus strictes
#   - Nettoyage post-extraction des trailers
#   - Normalisation des tirets avant matching PDF
# ──────────────────────────────────────────────────────────────

# Tokens qui ne font jamais partie du nom de la substance
_TRAILER = re.compile(
    r"\s*(?:\(CAS|\(EC|\(INCI|\(INN|\bat\b|used\s+as|in\s+cosmet"
    r"|as\s+used|version|revision|\d{4}|SCCS).*$",
    re.IGNORECASE,
)

def _clean_ingredient(raw: str) -> str | None:
    """Nettoie et valide un nom de substance extrait."""
    if not raw:
        return None
    raw = _TRAILER.sub("", raw)        # supprime les trailers
    raw = raw.strip(" ,;.'\"()[]/-")   # supprime la ponctuation de bord
    raw = re.sub(r"\s+", " ", raw)     # normalise les espaces
    # Rejet si trop court, trop long, ou ne contient aucune lettre
    if len(raw) < 3 or len(raw) > 90 or not re.search(r"[A-Za-z]", raw):
        return None
    return raw


# ── Patterns titre (ordre décroissant de fiabilité) ────────────────────────
#
# Chaque pattern capture le nom dans le groupe 1.
# On arrête au premier match valide.

TITLE_INGR_PATS = [
    # 1. "opinion on the safety of 'X'" ou "opinion on 'X'" (avec guillemets)
    r"[Oo]pinion\s+on\s+(?:the\s+)?(?:safety\s+of\s+)?['\u2018\u2019\u201c\u201d]([^'\"]{2,70})['\u2018\u2019\u201c\u201d]",

    # 2. "opinion on the safety of X" (sans guillemets, borne stricte)
    r"[Oo]pinion\s+on\s+the\s+safety\s+of\s+([A-Za-z0-9][A-Za-z0-9 ,+'\-/®()\[\]]{1,70}?)(?:\s*\(C|\s*\(CAS|\s*\(EC|\s*[-–—]|\s*$)",

    # 3. "opinion on X" (sans "safety of")
    r"[Oo]pinion\s+on\s+([A-Za-z][A-Za-z0-9 ,+'\-/®()\[\]]{2,60}?)(?:\s*\(C|\s*\(CAS|\s*\(EC|\s*[-–—]|\s+at\b|\s*$)",

    # 4. "safety of X" seul dans le titre
    r"[Ss]afety\s+of\s+([A-Za-z0-9][A-Za-z0-9 ,+'\-/®()\[\]]{2,70}?)(?:\s*\(|\s*[-–—]|\s+at\b|\s*$)",

    # 5. "advice on [hair dye] 'X'" (avec guillemets)
    r"[Aa]dvice\s+on\s+(?:\w+\s+){0,3}['\u2018\u201c]([^'\u2019\u201d]{2,60})['\u2019\u201d]",

    # 6. "advice on X (C009)" — identifiant SCCS entre parenthèses comme borne
    r"[Aa]dvice\s+on\s+(?:\w+\s+){0,2}([A-Za-z][A-Za-z0-9 +'\-/®]{2,60}?)\s*\(C\d",

    # 7. "addendum to the opinion on X"
    r"[Aa]ddendum\s+to\s+.*?[Oo]pinion\s+on\s+(?:the\s+)?(?:safety\s+of\s+)?([A-Za-z0-9][A-Za-z0-9 ,+'\-/®()\[\]]{2,70}?)(?:\s*\(|\s*[-–—]|\s*$)",

    # 8. "preliminary / scientific opinion on X"
    r"(?:preliminary|scientific)\s+[Oo]pinion\s+on\s+([A-Za-z][A-Za-z0-9 ,+'\-/®()\[\]]{2,70}?)(?:\s*\(|\s*[-–—]|\s*$)",

    # 9. v8 — "Request for a scientific Opinion on [aggregate exposure to] X"
    r"[Rr]equest\s+for\s+a\s+scientific\s+[Oo]pinion\s+on\s+(?:aggregate\s+exposure\s+to\s+)?([A-Za-z][A-Za-z0-9 ,+'\-/®()\[\]]{2,80}?)(?:\s*\(|\s*[-–—]|\s*$)",

    # 10. v8 — "SCCS - X" (titre avec tiret, sans mot-clé opinion/advice)
    #     Capture tout ce qui suit "SCCS - " jusqu'à une borne
    r"^SCCS\s*[-–]\s*([A-Za-z][A-Za-z0-9 ,+'\-/®()\[\]]{2,80}?)(?:\s*\(|\s*[-–—]\s*\d|\s*$)",
]

# ── Patterns PDF (fallback si titre échoue) ────────────────────────────────
PDF_INGR_PATS = [
    r"[Ss]afety\s+(?:assessment\s+)?of\s+([A-Za-z0-9][A-Za-z0-9 ,'\-/®()\[\]]{2,70}?)\s*(?:\(CAS|\(EC|used\s+as|in\s+cosmet|[-–—]|\n|\.)",
    r"[Oo]pinion\s+on\s+(?:the\s+)?(?:safety\s+of\s+)?([A-Za-z0-9][A-Za-z0-9 ,'\-/®()\[\]]{2,70}?)\s*(?:\(CAS|\(EC|[-–—]|\n|\.)",
    r"[Ss]cientific\s+[Aa]dvice\s+on\s+(?:\w+\s+){0,3}([A-Za-z0-9][A-Za-z0-9 ,'\-/®()\[\]]{2,60}?)\s*(?:\(CAS|\(C\d|\(EC|[-–—]|\n|\.)",
    r"[Aa]ddendum\s+to\s+.*?[Oo]pinion\s+on\s+([A-Za-z0-9][A-Za-z0-9 ,'\-/®()\[\]]{2,70}?)\s*(?:\(CAS|\(EC|[-–—]|\n|\.)",
    # Fallback : "The SCCS was asked to evaluate X"
    r"SCCS\s+was\s+asked\s+to\s+(?:evaluate|assess|consider)\s+([A-Za-z][A-Za-z0-9 ,'\-/®()\[\]]{2,70}?)\s*(?:\(|\.|,)",
]


def extract_ingredient(title: str, pdf_text: str) -> str | None:
    # 1. Depuis le titre
    for pat in TITLE_INGR_PATS:
        m = re.search(pat, title, re.IGNORECASE)
        if m:
            result = _clean_ingredient(m.group(1))
            if result:
                log.debug(f"  Ingredient from title: '{result}'")
                return result

    # 2. Depuis le PDF (après normalisation des tirets longs)
    pdf_norm = re.sub(r"[–—\u2013\u2014]", "-", pdf_text)
    for pat in PDF_INGR_PATS:
        m = re.search(pat, pdf_norm, re.IGNORECASE)
        if m:
            result = _clean_ingredient(m.group(1))
            if result:
                log.debug(f"  Ingredient from PDF: '{result}'")
                return result

    return None

# ──────────────────────────────────────────────────────────────
# Extraction : CAS_EC
# ──────────────────────────────────────────────────────────────

def extract_cas_ec(text):
    c = re.search(
        r"CAS[/\s]*EC\s*No\.?\s*([0-9]+-[0-9]+-[0-9]+)\s*/\s*([0-9]+-[0-9]+-[0-9]+)",
        text,
    )
    if c:
        return f"{c.group(1)} / {c.group(2)}"
    cas = re.search(r"CAS\s*(?:No\.?)?\s*([0-9]+-[0-9]+-[0-9]+)", text)
    ec  = re.search(r"EC\s*(?:No\.?)?\s*([0-9]+-[0-9]+-[0-9]+)", text)
    parts = [x.group(1) for x in (cas, ec) if x]
    return " / ".join(parts) if parts else None

# ──────────────────────────────────────────────────────────────
# Extraction : Verdict — v7 CORRIGÉ
#
# Problèmes v6 :
#   - "CONCLUSIONS" (avec S) absent des sections → section jamais parsée
#   - Faux positif : "safe up to X% but not safe for Y" → Conditionally Safe
#     car COND_PATS matchait avant NEG_PATS au niveau de la phrase entière
#   - Phrases boilerplate courtes (< 15 chars) polluaient le scoring
#
# Corrections v7 :
#   - CONCLUSIONS ajouté dans SECTION_ANCHORS (voir plus haut)
#   - Ordre NEG > COND > POS garanti *avant* de scorer
#   - Filtre longueur phrase (> 15 chars) dans split_sentences()
#   - Nouveau pattern NEG : "safety cannot be assured"
#   - Nouveau pattern NEG : "SCCS concludes that X is not safe"
# ──────────────────────────────────────────────────────────────

NEG_PATS = [
    re.compile(r"not\s+considered\s+safe",                                           re.I),
    re.compile(r"cannot\s+be\s+considered\s+safe",                                   re.I),
    re.compile(r"is\s+not\s+safe\b",                                                 re.I),
    re.compile(r"\bnot\s+safe\b",                                                    re.I),
    re.compile(r"unacceptable\s+risk",                                               re.I),
    re.compile(r"poses?\s+a\s+(?:safety\s+)?risk\s+(?:for|to)",                     re.I),
    re.compile(r"concern\s+(?:for|regarding|about).*?remains",                       re.I),
    re.compile(r"genotoxic\s+(?:potential|concern|risk)\s+remains",                  re.I),
    re.compile(r"does\s+not\s+consider.*?safe",                                      re.I),
    # NOUVEAU v7
    re.compile(r"safety\s+(?:of\s+\w+\s+)?cannot\s+be\s+assured",                   re.I),
    re.compile(r"SCCS\s+concludes?\s+that\s+.*?\bnot\s+safe\b",                      re.I),
    re.compile(r"SCCS\s+(?:is\s+of\s+the\s+opinion\s+that\s+|considers?\s+that\s+)?.*?\bnot\s+safe\b", re.I),
    re.compile(r"safety\s+concern\s+(?:has\s+)?(?:not\s+been\s+resolved|remains)",  re.I),
]

COND_PATS = [
    re.compile(r"safe\s+(?:only\s+)?(?:when|if|provided|as\s+long)",  re.I),
    re.compile(r"safe\s+up\s+to\b",                                    re.I),
    re.compile(r"safe\s+at\s+(?:a\s+)?(?:concentration|level|maximum)",re.I),
    re.compile(r"safe\s+in\s+(?:rinse|leave|certain|specific)",        re.I),
    re.compile(r"safe\s+for\s+use\s+in\s+(?:rinse|leave)",            re.I),
    re.compile(r"conditionally\s+safe",                                re.I),
    re.compile(r"(?:rinse.off|leave.on).*?\bsafe\b",                   re.I),
    re.compile(r"\bsafe\b.*?(?:rinse.off|leave.on)",                   re.I),
    re.compile(r"safe\s+at\s+\d",                                      re.I),
    re.compile(r"safe\s+when\s+used\s+(?:as|in|at)",                  re.I),
]

POS_PATS = [
    re.compile(r"(?:is\s+)?considered\s+safe\b",                       re.I),
    re.compile(r"safe\s+for\s+use\b",                                  re.I),
    re.compile(r"does\s+not\s+pose\s+a\s+(?:safety\s+)?risk",         re.I),
    re.compile(r"no\s+safety\s+concern",                               re.I),
    re.compile(r"SCCS\s+considers.*?\bsafe\b",                         re.I),
    re.compile(r"safe\s+at\s+the\s+(?:proposed|tested|maximum)",       re.I),
]


def _classify_sentence(sent: str) -> str | None:
    """
    Classifie une phrase.
    CORRECTION v7 : NEG testé en premier sur la phrase ENTIÈRE,
    avant tout test COND — évite le faux positif sur les phrases mixtes.
    """
    for pat in NEG_PATS:
        if pat.search(sent):
            return "Not Safe"
    for pat in COND_PATS:
        if pat.search(sent):
            return "Conditionally Safe"
    for pat in POS_PATS:
        if pat.search(sent):
            return "Safe"
    return None


def extract_verdict(sections: dict, full: str) -> str | None:
    verdicts_found = {"Not Safe": 0, "Conditionally Safe": 0, "Safe": 0}

    # Sections par ordre de priorité
    for sec in ["ABSTRACT", "CONCLUSION", "OPINION", "SUMMARY"]:
        content = sections.get(sec, "")
        if not content:
            continue
        for sent in split_sentences(content):
            v = _classify_sentence(sent)
            if v:
                verdicts_found[v] += 1

    # Fallback : premières 2500 chars du texte complet
    if not any(verdicts_found.values()):
        for sent in split_sentences(full[:2500]):
            v = _classify_sentence(sent)
            if v:
                verdicts_found[v] += 1

    # Priorité stricte
    if verdicts_found["Not Safe"] > 0:
        return "Not Safe"
    if verdicts_found["Conditionally Safe"] > 0:
        return "Conditionally Safe"
    if verdicts_found["Safe"] > 0:
        return "Safe"
    return None

# ──────────────────────────────────────────────────────────────
# Extraction : Concentration_Max — v7 CORRIGÉ
#
# Problèmes v6 :
#   - `[^.;]{0,250}` capturait des phrases entières parasites
#   - Multi-produits ("1% rinse-off, 0.5% leave-on") capturés partiellement
#   - Pas de déduplication des valeurs trouvées
#
# Corrections v7 :
#   - Capture nettoyée : arrêt strict après la valeur numérique + contexte court
#   - Extraction de TOUTES les occurrences dans une phrase → concaténation
#   - Déduplication et tri par score
#   - Nouveau pattern : "X% when used as/in [type produit]"
# ──────────────────────────────────────────────────────────────

# Unités acceptées
_UNIT = r"(?:%|ppm|mg/(?:kg|L|ml|day)|g/(?:kg|day)|µg/(?:kg|day))"

# Pattern de base : valeur numérique + unité + contexte court optionnel
_VAL  = rf"[\d.,]+\s*{_UNIT}"
# Contexte produit court : "in rinse-off products", "when used as hair dye", etc.
_CTX  = r"(?:\s+(?:in|when|for|as|of)\s+[a-z][a-z\s\-/]{0,40})?"

CONC_PATS = [
    # Score 5 — "safe at/up to X% [in product]"
    (rf"safe\s+(?:at|up\s+to|when\s+used\s+at)\s+({_VAL}{_CTX})",          5),
    # Score 5 — "maximum authorised/permitted concentration of X%"
    (rf"maximum\s+(?:authorised|permitted|allowed)?\s*concentration\s+of\s+({_VAL})", 5),
    # Score 4 — "not safe at X%"
    (rf"not\s+safe\s+at\s+({_VAL}{_CTX})",                                  4),
    # Score 4 — "X% when used as/in [type]"
    (rf"({_VAL}\s+when\s+used\s+(?:as|in)\s+[a-z][a-z\s\-/]{{3,40}})",     4),
    # Score 3 — "concentration of X% / up to X%"
    (rf"concentrations?\s+(?:of\s+|up\s+to\s+)?({_VAL}{_CTX})",             3),
    # Score 3 — "X% in [product type]" (phrase courte)
    (rf"({_VAL}\s+in\s+[a-z][a-z\s\-/]{{3,40}})",                           3),
    # Score 2 — sans % (ex: "at the currently permitted levels")
    (r"not\s+(?:considered\s+)?safe\s+at\s+(the\s+concentration[^.;]{0,120})", 2),
    (r"safe\s+at\s+(the\s+(?:proposed|tested|current|maximum)[^.;]{0,120})",   2),
    # Score 1 — ppm/mg générique
    (rf"(?:at|up\s+to)\s+({_VAL})",                                          1),
]


def _extract_all_values(text: str) -> list[tuple[int, str]]:
    """
    Extrait TOUTES les occurrences de concentrations dans un texte.
    Retourne une liste de (score, valeur_nettoyée).
    """
    found = []
    for pat, score in CONC_PATS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            val = clean(m.group(1))
            # Tronque après 120 chars pour éviter les captures trop longues
            val = val[:120].rstrip(" ,;")
            if len(val) > 1:
                found.append((score, val))
    return found


def extract_concentration(sections: dict, full: str) -> str | None:
    """
    Cherche les concentrations par ordre de priorité des sections.
    Si plusieurs valeurs dans la même section → les concatène (multi-produits).
    """
    targets = [
        (sections.get("ABSTRACT", ""),   3),
        (sections.get("CONCLUSION", ""), 2),
        (sections.get("OPINION", ""),    2),
        (full[:5000],                    1),
    ]

    all_candidates: list[tuple[int, str]] = []

    for text, text_bonus in targets:
        if not text:
            continue
        vals = _extract_all_values(text)
        for score, val in vals:
            all_candidates.append((score + text_bonus, val))

    if not all_candidates:
        return None

    # Déduplication (garder la valeur unique la mieux scorée)
    seen, deduped = set(), []
    for score, val in sorted(all_candidates, key=lambda x: -x[0]):
        key = val.lower()
        if key not in seen:
            seen.add(key)
            deduped.append((score, val))

    # Si plusieurs valeurs de score proche → les concatène (cas multi-produits)
    top_score  = deduped[0][0]
    top_values = [v for s, v in deduped if s >= top_score - 1]

    if len(top_values) == 1:
        return top_values[0]

    # Concaténation propre des valeurs multi-produits (max 3)
    return " | ".join(top_values[:3])

# ──────────────────────────────────────────────────────────────
# Extraction : Catégorie
# ──────────────────────────────────────────────────────────────

CATEGORY_MAP = [
    (re.compile(r"\bcolorant\b|\bdye\b|\bpigment\b|\bcolour\b|\bcolor\b",           re.I), "Colorant"),
    (re.compile(r"\bpreservative\b|\bantimicrobial\b",                               re.I), "Preservative"),
    (re.compile(r"\bUV\s*filter\b|\bsunscreen\b|\bUV\s*absorber\b",                 re.I), "UV Filter"),
    (re.compile(r"\bfragrance\b|\bparfum\b|\baromatic\b",                            re.I), "Fragrance"),
    (re.compile(r"\bsurfactant\b|\bdetergent\b|\bcleansing\b",                       re.I), "Surfactant"),
    (re.compile(r"\bemollient\b|\bmoisturi[sz]er\b|\bhumectant\b|\bskin\s*condit",   re.I), "Emollient/Moisturiser"),
    (re.compile(r"\bantioxidant\b|\bfree\s*radical\b",                               re.I), "Antioxidant"),
    (re.compile(r"\bnano\b|\bnanoparticle\b|\bnanomaterial\b",                       re.I), "Nanomaterial"),
    (re.compile(r"\bhair\s*dye\b|\bhair\s*colour\b",                                 re.I), "Hair Dye"),
    (re.compile(r"\bskin\s*lightening\b|\bbleaching\b|\bdepigment",                  re.I), "Skin Lightening"),
    (re.compile(r"\bplant\s*extract\b|\bherbal\b|\bbotanical\b",                     re.I), "Plant Extract"),
    (re.compile(r"\bvitamin\b|\bretinol\b|\bretinoid\b|\bascorbic\b",                re.I), "Vitamin/Active"),
    (re.compile(r"\bessential\s*oil\b|\baromatherapy\b",                             re.I), "Essential Oil"),
]

def extract_category(text):
    for pat, label in CATEGORY_MAP:
        if pat.search(text):
            return label
    return "Other"

# ──────────────────────────────────────────────────────────────
# Extraction : Conclusion texte (abstract-first)
# ──────────────────────────────────────────────────────────────

CONCL_PATS = [
    r"(The SCCS considers[^.]{20,500}\.)",
    r"(The SCCS is of the opinion[^.]{20,500}\.)",
    r"(The SCCS concludes[^.]{20,500}\.)",
    r"([^.]{20,}(?:considered safe|safe for use|safe when used|not safe|does not pose a risk|concern.*?remains)[^.]{0,300}\.)",
]
CONCL_KW = [
    "considered safe", "not considered safe", "safe for use", "safe when used",
    "does not pose", "the sccs concludes", "the sccs is of the opinion",
    "not safe", "no safety concern", "concern.*?remains",
]

def _score_conclusion(s):
    sl = s.lower()
    return sum(1 for kw in CONCL_KW if re.search(kw, sl))

def extract_conclusion(sections, full):
    candidates = []
    for sec, bonus in [("ABSTRACT", 3), ("CONCLUSION", 2), ("OPINION", 2)]:
        content = sections.get(sec, "")
        if not content:
            continue
        for pat in CONCL_PATS:
            for m in re.finditer(pat, content, re.IGNORECASE | re.DOTALL):
                sent = clean(m.group(1))
                if len(sent) > 40:
                    candidates.append((_score_conclusion(sent) + bonus + 2, sent))
        for sent in split_sentences(content):
            sc = _score_conclusion(sent)
            if sc > 0 and len(sent) > 40:
                candidates.append((sc + bonus, clean(sent)))
    for sent in split_sentences(full):
        sc = _score_conclusion(sent)
        if sc > 0 and len(sent) > 40:
            candidates.append((sc, clean(sent)))
    if not candidates:
        return None
    return sorted(candidates, key=lambda x: -x[0])[0][1]

# ──────────────────────────────────────────────────────────────
# Scraping article
# ──────────────────────────────────────────────────────────────

def get_pdf_url(article_url):
    r    = fetch(article_url)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        if ".pdf" in a["href"].lower():
            return abs_url(a["href"])
    return None


def scrape_article(article_url, doc_type, title=""):
    row = {
        "Ingredient":      None,
        "CAS_EC":          None,
        "SCCS_Number":     None,
        "Date_Avis":       None,
        "Verdict":         None,
        "Concentration_Max": None,
        "Lien_Source":     article_url,
        "Type_Rapport":    doc_type,
        "Categorie":       None,
        "_title":          title,
        "_pdf_url":        None,
        "_conclusion":     None,
        "_error":          None,
    }
    try:
        pdf_url = get_pdf_url(article_url)
        if not pdf_url:
            row["_error"] = "No PDF found"
            log.warning(f"    ⚠ Pas de PDF : {article_url}")
            return row
        row["_pdf_url"] = pdf_url

        full     = pdf_to_text(fetch_bytes(pdf_url))
        sections = extract_sections(full)

        row["SCCS_Number"]       = extract_sccs_number(full)
        row["Date_Avis"]         = extract_date(full)
        row["Ingredient"]        = extract_ingredient(title, full)
        row["CAS_EC"]            = extract_cas_ec(full)
        row["Verdict"]           = extract_verdict(sections, full)
        row["Concentration_Max"] = extract_concentration(sections, full)
        row["Categorie"]         = extract_category(full)
        row["_conclusion"]       = extract_conclusion(sections, full)

        log.info(
            f"    ✓ {row['Ingredient'] or '?'} | "
            f"{row['Verdict'] or '?'} | {row['Concentration_Max'] or '?'}"
        )
    except Exception as e:
        row["_error"] = str(e)
        log.error(f"    ✗ {article_url} : {e}")
    return row


def save(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SCCS Scraper v7 — Corrections Ingredient / Verdict / Concentration"
    )
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Nombre max de pages à parcourir (défaut: toutes)")
    parser.add_argument("--output",    default="sccs_results.json",
                        help="Fichier JSON de sortie")
    parser.add_argument("--resume",    action="store_true",
                        help="Reprendre depuis un fichier de sortie existant")
    # Mode test : scraper un article précis sans passer par Playwright
    parser.add_argument("--test-url",  default=None,
                        help="URL d'un article SCCS à tester directement")
    parser.add_argument("--test-type", default="Final Opinion",
                        help="Type de document pour --test-url")
    parser.add_argument("--test-title", default="",
                        help="Titre de l'article pour --test-url")
    args = parser.parse_args()

    # ── Mode test unitaire ───────────────────────────────────────
    if args.test_url:
        log.info(f"Mode test : {args.test_url}")
        row = scrape_article(args.test_url, args.test_type, args.test_title)
        print(json.dumps(row, ensure_ascii=False, indent=2))
        return

    # ── Mode complet ─────────────────────────────────────────────
    output_path     = Path(args.output)
    results, done_urls = [], set()

    if args.resume and output_path.exists():
        with open(output_path, encoding="utf-8") as f:
            results = json.load(f)
        done_urls = {r["Lien_Source"] for r in results}
        log.info(f"▶ Reprise : {len(done_urls)} articles déjà traités.")

    log.info("═" * 60)
    log.info("ÉTAPE 1 — Collecte des liens")
    log.info("═" * 60)

    articles = collect_articles_playwright(args.max_pages)

    seen, unique = set(), []
    for a in articles:
        if a["url"] not in seen:
            seen.add(a["url"])
            unique.append(a)

    by_type = {}
    for a in unique:
        by_type[a["doc_type"]] = by_type.get(a["doc_type"], 0) + 1
    log.info(f"✅ {len(unique)} articles | {by_type}")

    log.info("═" * 60)
    log.info("ÉTAPE 2 — Scraping PDF")
    log.info("═" * 60)

    for i, article in enumerate(unique, 1):
        url = article["url"]
        if url in done_urls:
            log.info(f"  [{i}/{len(unique)}] ⏭ Déjà traité")
            continue
        log.info(f"  [{i}/{len(unique)}] [{article['doc_type']}] {article['title'][:65]}")
        row = scrape_article(url, article["doc_type"], article["title"])
        results.append(row)
        if i % 5 == 0:
            save(results, output_path)
            log.info(f"    💾 {len(results)} articles sauvegardés")

    save(results, output_path)
    log.info("═" * 60)
    log.info(f"✅ TERMINÉ — {len(results)} → {output_path}")

    verdicts = {}
    for r in results:
        v = r.get("Verdict") or "Unknown"
        verdicts[v] = verdicts.get(v, 0) + 1
    log.info(f"  Erreurs  : {sum(1 for r in results if r.get('_error'))}/{len(results)}")
    log.info(f"  Verdicts : {verdicts}")


if __name__ == "__main__":
    main()
