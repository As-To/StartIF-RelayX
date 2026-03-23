"""
EUR-Lex Scraper — Annexes II & III du Règlement (CE) 1223/2009
===============================================================
Scrape les listes officielles de substances interdites (Annexe II)
et restreintes (Annexe III) du règlement cosmétique européen.

Architecture en 3 étapes :
  1. CELLAR SPARQL  → récupère les métadonnées + URI de toutes les
                      versions consolidées du règlement 1223/2009
  2. CELLAR REST    → télécharge le HTML de la version consolidée la + récente
  3. BeautifulSoup  → parse les tableaux des Annexes II et III

Pas de clé API requise. Open access officiel Publications Office UE.
  SPARQL endpoint : https://publications.europa.eu/webapi/rdf/sparql
  REST  endpoint  : https://publications.europa.eu/resource/cellar/{id}

Usage :
  pip install requests beautifulsoup4 lxml pandas

  python eurlex_scraper.py
  python eurlex_scraper.py --annex 2             # Annexe II uniquement
  python eurlex_scraper.py --annex 3             # Annexe III uniquement
  python eurlex_scraper.py --lang FR             # langue (EN par défaut)
  python eurlex_scraper.py --all-versions        # toutes les versions consolidées
  python eurlex_scraper.py --output results.json
  python eurlex_scraper.py --csv                 # export CSV en plus du JSON
"""

import re
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# Supprimer le warning BeautifulSoup sur les documents XML parsés comme HTML
# (EUR-Lex retourne parfois du XHTML avec un Content-Type XML)
import warnings
try:
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    pass  # Versions BS4 < 4.12 n'ont pas ce warning

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def _has_lxml() -> bool:
    """Vérifie si lxml est disponible (parser plus rapide que html.parser)."""
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

# SPARQL endpoint public CELLAR (Publications Office EU)
SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

# REST endpoint CELLAR pour télécharger le contenu HTML
CELLAR_REST = "https://publications.europa.eu/resource/cellar"

# CELEX du règlement de base (non consolidé)
CELEX_BASE = "32009R1223"

# Identifiant CELEX du texte consolidé (préfixe 0 = consolidé)
# Format : 0{année}{type}{numéro}-{YYYYMMDD}
CELEX_CONSOLIDATED_PREFIX = "02009R1223"

# URL directe du texte consolidé le plus récent (fallback si SPARQL échoue)
# EUR-Lex maintient une URL canonique "latest" via ce pattern
EURLEX_BASE = "https://eur-lex.europa.eu"
CONSOLIDATED_URL_TEMPLATE = (
    f"{EURLEX_BASE}/legal-content/{{lang}}/TXT/HTML/"
    f"?uri=CELEX:{CELEX_CONSOLIDATED_PREFIX}-{{date}}"
)

DELAY = 1.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# HTTP helper
# ──────────────────────────────────────────────────────────────

def http_get(url: str, params: dict = None, headers: dict = None,
             timeout: int = 30) -> requests.Response | None:
    """GET robuste avec retry sur 429/503."""
    time.sleep(DELAY)
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers,
                             timeout=timeout, allow_redirects=True)
            if r.status_code == 429:
                wait = 20 * (attempt + 1)
                log.warning(f"  Rate limit (429) — attente {wait}s...")
                time.sleep(wait)
                continue
            if r.status_code == 503:
                log.warning(f"  Service indisponible (503) — tentative {attempt+1}/3")
                time.sleep(10)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as e:
            log.error(f"  HTTP {e.response.status_code} : {url}")
            return None
        except requests.exceptions.ConnectionError:
            log.error(f"  Connexion impossible (tentative {attempt+1}/3) : {url}")
            time.sleep(5)
        except Exception as e:
            log.error(f"  Erreur réseau : {e}")
            return None
    return None


def clean(text: str) -> str:
    """Normalise les espaces et caractères invisibles."""
    if not text:
        return ""
    text = re.sub(r"[\u00ad\u200b\u200c\u200d\ufeff\xa0]", " ", str(text))
    text = re.sub(r"[–—\u2013\u2014]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


# ──────────────────────────────────────────────────────────────
# ÉTAPE 1 : SPARQL CELLAR — lister les versions consolidées
# ──────────────────────────────────────────────────────────────
#
# Le CELLAR SPARQL endpoint permet de requêter toutes les versions
# consolidées du règlement 1223/2009 et leurs dates d'entrée en vigueur.
#
# Endpoint : https://publications.europa.eu/webapi/rdf/sparql
# Format   : application/sparql-results+json

SPARQL_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX owl: <http://www.w3.org/2002/07/owl#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT DISTINCT ?work ?celex ?date_doc ?title
WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  FILTER(STRSTARTS(STR(?celex), "{prefix}"))

  OPTIONAL {{ ?work cdm:work_date_document ?date_doc }}
  OPTIONAL {{
    ?work cdm:work_has_expression ?expr .
    ?expr cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/{lang}> .
    ?expr cdm:expression_title ?title .
  }}
}}
ORDER BY DESC(?date_doc)
LIMIT 50
"""


def get_consolidated_versions(lang: str = "ENG") -> list[dict]:
    """
    Via SPARQL CELLAR, récupère toutes les versions consolidées
    du règlement 1223/2009.
    Retourne une liste triée par date décroissante.
    """
    log.info("  SPARQL : recherche des versions consolidées...")

    query = SPARQL_QUERY.format(
        prefix=CELEX_CONSOLIDATED_PREFIX,
        lang=lang,
    )

    headers = {
        "Accept":     "application/sparql-results+json",
        "User-Agent": "EURLexScraper/1.0 (research; contact via github)",
    }

    r = http_get(
        SPARQL_ENDPOINT,
        params={"query": query, "format": "application/sparql-results+json"},
        headers=headers,
        timeout=60,
    )

    if not r:
        log.warning("  SPARQL indisponible — fallback URL directe")
        return []

    try:
        data    = r.json()
        results = data.get("results", {}).get("bindings", [])
        versions = []
        for row in results:
            celex    = row.get("celex",    {}).get("value", "")
            date_doc = row.get("date_doc", {}).get("value", "")[:10]
            title    = row.get("title",    {}).get("value", "")
            work_uri = row.get("work",     {}).get("value", "")

            if not celex or CELEX_CONSOLIDATED_PREFIX not in celex:
                continue

            # Extraire la date depuis le CELEX si absent
            if not date_doc:
                m = re.search(r"-(\d{8})$", celex)
                if m:
                    raw = m.group(1)
                    date_doc = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"

            versions.append({
                "celex":    celex,
                "date":     date_doc,
                "title":    title,
                "work_uri": work_uri,
            })

        # Déduplication et tri par date
        seen = set()
        unique = []
        for v in versions:
            if v["celex"] not in seen:
                seen.add(v["celex"])
                unique.append(v)

        unique.sort(key=lambda x: x["date"], reverse=True)
        log.info(f"  SPARQL : {len(unique)} version(s) consolidée(s) trouvée(s)")
        return unique

    except Exception as e:
        log.error(f"  Erreur parsing SPARQL : {e}")
        return []


# ──────────────────────────────────────────────────────────────
# ÉTAPE 2 : Téléchargement HTML via CELLAR REST ou EUR-Lex direct
# ──────────────────────────────────────────────────────────────
#
# Deux méthodes :
#   A. CELLAR REST : GET https://publications.europa.eu/resource/cellar/{UUID}
#      Header Accept: text/html  → redirige vers le HTML
#   B. EUR-Lex direct : GET https://eur-lex.europa.eu/legal-content/{lang}/TXT/HTML/
#      ?uri=CELEX:{celex}
#      Plus simple, même résultat.

def download_html_eurlex(celex: str, lang: str = "EN") -> str | None:
    """
    Télécharge le HTML d'un texte consolidé EUR-Lex via l'URL directe.
    C'est la méthode la plus fiable pour les textes consolidés.

    Ex: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:02009R1223-20250501
    """
    url = f"{EURLEX_BASE}/legal-content/{lang}/TXT/HTML/?uri=CELEX:{celex}"
    log.info(f"  ⬇️  {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; EURLexScraper/1.0)",
        "Accept":     "text/html,application/xhtml+xml",
        "Accept-Language": f"{lang.lower()},{lang.lower()}-{lang};q=0.9",
    }

    r = http_get(url, headers=headers, timeout=60)
    if not r:
        return None

    log.info(f"  ✅ HTML téléchargé ({len(r.content) // 1024} KB)")
    return r.text


def download_html_cellar(work_uri: str, lang: str = "ENG") -> str | None:
    """
    Télécharge le HTML via le CELLAR REST endpoint.
    Méthode officielle — utilise l'URI CELLAR du document.

    Header Accept: text/html;notice=branch → HTML complet avec annexes
    """
    if not work_uri:
        return None

    # Extraire l'UUID depuis l'URI CELLAR
    cellar_id = work_uri.split("/")[-1] if "/" in work_uri else work_uri
    url       = f"{CELLAR_REST}/{cellar_id}"

    headers = {
        "User-Agent":     "EURLexScraper/1.0",
        "Accept":         "text/html",
        "Accept-Language": lang[:3].lower(),
    }

    log.info(f"  ⬇️  CELLAR REST : {url}")
    r = http_get(url, headers=headers, timeout=60)
    if r and len(r.text) > 1000:
        log.info(f"  ✅ HTML CELLAR ({len(r.content) // 1024} KB)")
        return r.text
    return None


def get_latest_consolidated(lang: str = "EN") -> tuple[str, str]:
    """
    Identifie la version consolidée la plus récente et retourne
    (celex, html_content).

    Stratégie :
      1. SPARQL → liste des versions → télécharge la plus récente
      2. Fallback : essaie des dates connues en ordre décroissant
    """
    lang_sparql = {"EN": "ENG", "FR": "FRA", "DE": "DEU"}.get(lang.upper(), "ENG")
    versions    = get_consolidated_versions(lang_sparql)

    # Essai SPARQL + téléchargement
    for v in versions[:5]:  # essaie les 5 plus récentes
        log.info(f"  Tentative version {v['celex']} ({v['date']})")

        # Méthode A : EUR-Lex direct (plus fiable)
        html = download_html_eurlex(v["celex"], lang)
        if html and len(html) > 50_000:
            return v["celex"], html

        # Méthode B : CELLAR REST
        if v.get("work_uri"):
            html = download_html_cellar(v["work_uri"], lang_sparql)
            if html and len(html) > 50_000:
                return v["celex"], html

    # Fallback : dates connues des consolidations récentes
    log.warning("  Fallback : essai des dates de consolidation connues")
    known_dates = [
        "20250901", "20250501", "20250101",
        "20241201", "20240901", "20240601",
        "20240301", "20231201", "20230901",
    ]
    for date_str in known_dates:
        celex = f"{CELEX_CONSOLIDATED_PREFIX}-{date_str}"
        html  = download_html_eurlex(celex, lang)
        if html and len(html) > 50_000:
            log.info(f"  ✅ Version fallback : {celex}")
            return celex, html
        time.sleep(0.5)

    log.error("  Impossible de télécharger le texte consolidé")
    return "", ""


# ──────────────────────────────────────────────────────────────
# ÉTAPE 3 : Parsing des tableaux Annexes II et III
# ──────────────────────────────────────────────────────────────

def find_annex_section(soup: BeautifulSoup, annex_num: int) -> BeautifulSoup | None:
    """
    Localise la section d'une annexe dans le HTML EUR-Lex et retourne
    un sous-soup contenant UNIQUEMENT le contenu de cette annexe
    (du titre de l'annexe N jusqu'au titre de l'annexe N+1).

    Problèmes connus du HTML EUR-Lex :
      - Les annexes ne sont PAS dans des <div> séparés avec id
      - Le HTML est une longue séquence de <p>, <table>, <div>
      - find_parent() remonte trop haut et englobe toutes les annexes
      - L'en-tête du tableau est "a b c d e f" (lettres) pas des textes
    """
    roman      = {2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}
    num_r      = roman.get(annex_num, str(annex_num))
    num_r_next = roman.get(annex_num + 1, str(annex_num + 1))

    annex_pat      = re.compile(rf"^\s*ANNEX\s+{num_r}\s*$", re.IGNORECASE)
    annex_next_pat = re.compile(
        rf"^\s*ANNEX\s+{num_r_next}\s*$"
        rf"|\s*ANNEX\s+{num_r_next}\b",
        re.IGNORECASE,
    )

    # ── Stratégie 1 : id EUR-Lex structuré ──────────────────────
    for attr in [f"annex_{num_r}", f"L_ANNEX_{num_r}",
                 f"annex_{annex_num}", f"ann{annex_num}"]:
        el = soup.find(id=re.compile(rf"^{re.escape(attr)}$", re.I))
        if el:
            log.info(f"  Annexe {num_r} via id='{attr}'")
            return el

    # ── Stratégie 2 : trouver le titre exact puis collecter les  ─
    #    éléments jusqu'au titre de l'annexe suivante             ─
    #    (approche position dans le flux du document)             ─
    all_elements = list(soup.find_all(True))  # tous les éléments

    start_idx = None
    end_idx   = None

    for i, el in enumerate(all_elements):
        tag  = el.name
        text = clean(el.get_text())

        # Cherche le titre de l'annexe cible
        if start_idx is None:
            if tag in ("h1","h2","h3","h4","p","div","span") and len(text) < 80:
                if annex_pat.search(text):
                    start_idx = i
                    log.info(f"  Annexe {num_r} trouvée : <{tag}> '{text}' (idx={i})")

        # Cherche le début de l'annexe suivante
        elif end_idx is None:
            if tag in ("h1","h2","h3","h4","p","div","span") and len(text) < 80:
                if annex_next_pat.search(text):
                    end_idx = i
                    log.info(f"  Fin Annexe {num_r} : <{tag}> '{text}' (idx={i})")
                    break

    if start_idx is None:
        log.warning(f"  Annexe {num_r} introuvable")
        return None

    # Construire un conteneur virtuel avec les éléments de la section
    # On utilise le parent commun le plus proche (le body ou html)
    body = soup.find("body") or soup

    # Créer un nouveau BeautifulSoup "virtuel" avec les éléments de la section
    # En pratique : retourner un objet wrapper qui contient les bons éléments
    section_elements = all_elements[start_idx: end_idx if end_idx else start_idx + 3000]

    # Construire un mini-HTML avec ces éléments
    # On garde uniquement les éléments <table> et leurs ancêtres directs
    # dans la plage start_idx → end_idx
    section_html = "".join(str(el) for el in section_elements
                            if el.name == "table")

    if not section_html:
        # Fallback : retourner le parent du premier élément trouvé
        anchor = all_elements[start_idx]
        parent = anchor.find_parent(["div", "section", "article", "body"])
        log.warning(f"  Pas de table dans la section, fallback parent")
        return parent

    # Wrapper HTML minimal
    wrapper_html = f"<div id='annex_section_{num_r}'>{section_html}</div>"
    parser = "lxml" if _has_lxml() else "html.parser"
    return BeautifulSoup(wrapper_html, parser)


# ──────────────────────────────────────────────────────────────
# Grille virtuelle — résolution colspan / rowspan
# ──────────────────────────────────────────────────────────────
#
# Le HTML EUR-Lex utilise massivement colspan et rowspan dans les
# tableaux des annexes :
#   - rowspan : une cellule "substance" couvre N lignes produit
#   - colspan : une cellule "nom+CAS+EC" fusionne 3 colonnes logiques
#
# L'approche naïve (cells[i]) décale tous les indices dès qu'une
# cellule fusionnée apparaît.
#
# Solution : construire une grille 2D où chaque case (row, col)
# contient le texte de la cellule qui la couvre — même si cette
# cellule est en rowspan ou colspan depuis une ligne précédente.

def _build_grid(table) -> list[list[str]]:
    """
    Construit une grille 2D (liste de listes de str) depuis un <table> HTML.
    Résout correctement tous les colspan et rowspan.

    Retourne : grid[row_idx][col_idx] = texte nettoyé de la cellule
    """
    grid    = []          # grid[r][c] = texte
    pending = {}          # pending[(r,c)] = texte à propager (rowspan)

    for row_idx, tr in enumerate(table.find_all("tr")):
        row_cells = []
        col_cursor = 0

        for td in tr.find_all(["td", "th"]):
            # Avancer le curseur pour dépasser les cellules en attente (rowspan)
            while (row_idx, col_cursor) in pending:
                row_cells.append(pending.pop((row_idx, col_cursor)))
                col_cursor += 1

            text    = _cell_text(td)
            colspan = int(td.get("colspan", 1))
            rowspan = int(td.get("rowspan", 1))

            # Remplir colspan : répéter le texte sur N colonnes
            for c in range(colspan):
                row_cells.append(text)
                # Propager rowspan sur les lignes suivantes
                for r in range(1, rowspan):
                    pending[(row_idx + r, col_cursor + c)] = text
            col_cursor += colspan

        # Vider les pending restants pour cette ligne
        max_col = max((c for (r, c) in pending if r == row_idx), default=col_cursor - 1)
        for c in range(col_cursor, max_col + 1):
            if (row_idx, c) in pending:
                row_cells.append(pending.pop((row_idx, c)))

        if row_cells:
            grid.append(row_cells)

    return grid


def _cell_text(td) -> str:
    """
    Extrait le texte d'une cellule HTML.
    Les balises <br> et <p> internes deviennent des espaces
    pour préserver la lisibilité des champs multi-lignes.
    """
    # Remplacer <br> par espace avant extraction
    for br in td.find_all("br"):
        br.replace_with(" | ")
    return clean(td.get_text())


# ──────────────────────────────────────────────────────────────
# Détection des colonnes sur la grille résolue
# ──────────────────────────────────────────────────────────────

_COL_KEYWORDS = {
    # Annexe II
    "entry":      ["ref", "numéro", "number", "n°", "entry", "référence"],
    "name":       ["substance", "name", "nom", "chemical", "dénomination",
                   "name of substance", "substance name"],
    "cas":        ["cas"],
    "ec":         ["ec no", "ec number", "einecs", "elincs", "ce no"],
    "notes":      ["note", "remark", "condition", "autres"],
    # Annexe III (en plus)
    "product":    ["product type", "type of product", "type de produit",
                   "products", "produit"],
    "max_conc":   ["maximum concentration", "concentration", "maximum",
                   "max", "teneur", "conc"],
    "conditions": ["other", "condition", "restriction", "autres conditions"],
    "labelling":  ["label", "étiquetage", "warning", "mention", "wording"],
}

# Positions fixes EUR-Lex quand l'en-tête est a/b/c/d/e/f (lettres)
# Annexe II  : a=entrée, b=nom, c=CAS, d=EC
# Annexe III : a=entrée, b=nom, c=type produit, d=conc max, e=conditions, f=étiquetage
_POSITIONAL_II  = {"entry": 0, "name": 1, "cas": 2, "ec": 3, "notes": 4}
_POSITIONAL_III = {"entry": 0, "name": 1, "product": 2,
                   "max_conc": 3, "conditions": 4, "labelling": 5}


def _is_letter_header(header_row: list[str]) -> bool:
    """
    Détecte si l'en-tête du tableau utilise des lettres simples (a, b, c…)
    au lieu de textes descriptifs — format habituel EUR-Lex.
    """
    letters = {h.strip().lower() for h in header_row if h.strip()}
    alpha   = {h for h in letters if re.match(r"^[a-f]$", h)}
    return len(alpha) >= 2  # au moins 2 lettres a-f


def _detect_columns(header_row: list[str], annex_num: int = 2) -> dict[str, int | None]:
    """
    Détecte l'indice de colonne de chaque champ sémantique.

    EUR-Lex Annexe II/III utilise des en-têtes à lettres (a, b, c, d, e, f)
    → fallback positionnel selon l'annexe concernée.
    """
    col = {k: None for k in _COL_KEYWORDS}

    # Cas 1 : en-têtes textuels descriptifs
    if not _is_letter_header(header_row):
        for i, h in enumerate(header_row):
            h_low = h.lower()
            for field, keywords in _COL_KEYWORDS.items():
                if col[field] is None:
                    if any(kw in h_low for kw in keywords):
                        col[field] = i

    # Cas 2 : en-têtes à lettres → positions fixes EUR-Lex
    else:
        log.info("  En-tête à lettres détecté → positions fixes EUR-Lex")
        template = _POSITIONAL_III if annex_num == 3 else _POSITIONAL_II
        for field, idx in template.items():
            col[field] = idx

    # Fallbacks positionnels minimaux
    if col["entry"] is None:
        col["entry"] = 0
    if col["name"] is None:
        col["name"] = 1

    return col


def _get(row: list[str], idx: int | None, default: str = "") -> str:
    """Lecture sûre d'une cellule de la grille."""
    if idx is None or idx >= len(row):
        return default
    return row[idx] or default


# ──────────────────────────────────────────────────────────────
# Extraction CAS / EC depuis le texte d'une cellule
# ──────────────────────────────────────────────────────────────

# Format CAS : 2-7 chiffres - 2 chiffres - 1 chiffre
_RE_CAS = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")
# Format EC (EINECS/ELINCS) : 3-3-1 ex: 200-001-8
_RE_EC  = re.compile(r"\b(\d{3}-\d{3}-\d)\b")
# Mention CAS explicite
_RE_CAS_LABEL = re.compile(r"CAS\s*(?:No\.?)?\s*:?\s*(\d{2,7}-\d{2}-\d)", re.I)
_RE_EC_LABEL  = re.compile(r"EC\s*(?:No\.?)?\s*:?\s*(\d{3}-\d{3}-\d)", re.I)


def _extract_cas_ec(text: str) -> tuple[str, str]:
    """
    Extrait les numéros CAS et EC depuis un texte libre.
    Priorité : mentions explicites "CAS No." / "EC No." > regex seule.
    Gère aussi les listes multiples (plusieurs CAS séparés par virgule).
    """
    cas_list, ec_list = [], []

    # 1. Mentions explicites (priorité)
    for m in _RE_CAS_LABEL.finditer(text):
        cas_list.append(m.group(1))
    for m in _RE_EC_LABEL.finditer(text):
        ec_list.append(m.group(1))

    # 2. Regex générique si rien trouvé
    if not cas_list:
        for m in _RE_CAS.finditer(text):
            v = m.group(1)
            # Éviter de confondre un EC (3-3-1) avec un CAS
            if not _RE_EC.match(v):
                cas_list.append(v)
    if not ec_list:
        for m in _RE_EC.finditer(text):
            ec_list.append(m.group(1))

    cas = " | ".join(dict.fromkeys(cas_list))  # dédupliqué, ordre préservé
    ec  = " | ".join(dict.fromkeys(ec_list))
    return cas, ec


def _strip_cas_ec(text: str) -> str:
    """
    Retire les numéros CAS et EC d'un texte de nom de substance.
    Utile quand CAS/EC sont dans la même cellule que le nom.
    """
    text = _RE_CAS_LABEL.sub("", text)
    text = _RE_EC_LABEL.sub("", text)
    text = _RE_CAS.sub("", text)
    text = _RE_EC.sub("", text)
    # Nettoyer les séparateurs orphelins
    text = re.sub(r"[\|/,;]\s*[\|/,;]", "|", text)
    text = re.sub(r"^[\s|/,;]+|[\s|/,;]+$", "", text)
    return clean(text)


# ──────────────────────────────────────────────────────────────
# Annexe II — parser principal
# ──────────────────────────────────────────────────────────────

def parse_annex_II(soup: BeautifulSoup) -> list[dict]:
    """
    Parse l'Annexe II (substances INTERDITES) via grille virtuelle.

    Structure réelle du tableau EUR-Lex Annexe II :
      Col a : Numéro d'ordre (1, 2, 3 …)
      Col b : Nom de la substance (+ CAS + EC parfois dans la même cellule)
      Col c : Numéro CAS    ← peut être absent ou fusionné avec col b
      Col d : Numéro CE     ← idem

    Les rowspans couvrent les synonymes d'une même substance.
    """
    log.info("\n  Parsing Annexe II (substances interdites)...")

    section = find_annex_section(soup, 2)
    tables  = (section or soup).find_all("table")
    log.info(f"  {len(tables)} tableau(x) dans la section Annexe II")

    entries = []

    for t_idx, table in enumerate(tables):
        grid = _build_grid(table)
        if len(grid) < 3:
            continue

        # Ligne d'en-tête = première ligne non vide
        header = grid[0]
        col    = _detect_columns(header, annex_num=2)

        # Vérifier que c'est bien un tableau d'annexe
        header_str = " ".join(header).lower()
        if t_idx > 0 and not any(
            kw in header_str for kw in
            ["substance", "cas", "name", "nom", "reference", "numéro"]
        ):
            continue

        log.info(f"  Tableau {t_idx} : {len(grid)} lignes | colonnes détectées : {col}")

        for row in grid[1:]:
            if not row:
                continue

            entry_num = _get(row, col["entry"])
            name_raw  = _get(row, col["name"])

            # Skip lignes vides
            if not entry_num and not name_raw:
                continue

            # Skip en-têtes répétés (colonne b contient "substance" etc.)
            if any(kw in name_raw.lower() for kw in
                   ["substance", "name of", "chemical name", "dénomination"]):
                continue

            # ── Nettoyage des marqueurs d'amendement EUR-Lex ────────────
            # Marqueurs standalone : "▼M32", "▼B", "►M4", "◄", "▼C6 -----"
            # → toute la ligne est un marqueur, on la skip
            _MARKER_RE = re.compile(
                r'^[▼►▲◄]\s*(?:[A-Z]\d*|\d+)[\s\-]*$', re.UNICODE
            )
            if _MARKER_RE.match(entry_num.strip()) or _MARKER_RE.match(name_raw.strip()):
                continue
            # Nettoyer les préfixes de marqueur dans le numéro d'entrée
            # ex: "►M4 203" → "203" | "►C3 297 ◄" → "297"
            entry_num = re.sub(r'^[▼►▲◄]\s*[A-Z]\d*\s*', '', entry_num).strip()
            entry_num = re.sub(r'\s*[◄▼►▲]\s*$', '', entry_num).strip()

            # CAS/EC : colonne dédiée ou extrait depuis le nom
            cas_col = _get(row, col["cas"])
            ec_col  = _get(row, col["ec"])
            notes   = _get(row, col["notes"])

            # Extraire CAS/EC depuis les colonnes dédiées en priorité
            cas, ec = "", ""
            if cas_col:
                cas, _ = _extract_cas_ec(cas_col)
                if not cas:
                    cas = cas_col.strip()
            if ec_col:
                _, ec = _extract_cas_ec(ec_col)
                if not ec:
                    ec = ec_col.strip()

            # Si pas de colonnes dédiées → extraire depuis le nom
            if not cas or not ec:
                cas2, ec2 = _extract_cas_ec(name_raw)
                if not cas:
                    cas = cas2
                if not ec:
                    ec = ec2
                name_raw = _strip_cas_ec(name_raw)

            if len(name_raw) < 2 and len(entry_num) < 1:
                continue

            entries.append({
                "annex":          "II",
                "status":         "prohibited",
                "entry_number":   clean(entry_num),
                "substance_name": clean(name_raw),
                "cas_number":     _normalize_cas(cas.split(" | ")[0]) if cas else "",
                "cas_all":        cas,
                "ec_number":      ec.split(" | ")[0] if ec else "",
                "ec_all":         ec,
                "notes":          clean(notes),
            })

    # Déduplication par numéro d'entrée + nom
    seen, unique = set(), []
    for e in entries:
        key = e["entry_number"] or e["substance_name"][:40]
        if key and key not in seen:
            seen.add(key)
            unique.append(e)

    log.info(f"  ✅ Annexe II : {len(unique)} entrée(s)")
    return unique


# ──────────────────────────────────────────────────────────────
# Annexe III — parser principal
# ──────────────────────────────────────────────────────────────

def parse_annex_III(soup: BeautifulSoup) -> list[dict]:
    """
    Parse l'Annexe III (substances RESTREINTES) via grille virtuelle.

    Structure réelle du tableau EUR-Lex Annexe III (6 colonnes) :
      Col a : Numéro d'ordre
      Col b : Nom substance / CAS / EC  ← souvent tout dans une cellule
      Col c : Type de produit / conditions d'usage
      Col d : Concentration maximale dans le produit fini
      Col e : Autres conditions de restriction
      Col f : Mentions d'étiquetage obligatoires

    rowspan fréquents : une substance (col b) couvre N lignes
    produit (col c = différents types de produit avec concentrations diff.)
    """
    log.info("\n  Parsing Annexe III (substances restreintes)...")

    section = find_annex_section(soup, 3)
    tables  = (section or soup).find_all("table")
    log.info(f"  {len(tables)} tableau(x) dans la section Annexe III")

    entries = []

    for t_idx, table in enumerate(tables):
        grid = _build_grid(table)
        if len(grid) < 3:
            continue

        header     = grid[0]
        col        = _detect_columns(header, annex_num=3)
        header_str = " ".join(header).lower()

        if t_idx > 0 and not any(
            kw in header_str for kw in
            ["substance", "product", "concentration", "condition",
             "restriction", "label", "maximum"]
        ):
            continue

        log.info(f"  Tableau {t_idx} : {len(grid)} lignes | colonnes : {col}")

        # État courant pour propager les infos substance en cas de rowspan
        current_substance = {
            "entry_number": "", "substance_name": "",
            "cas_number": "", "cas_all": "", "ec_number": "", "ec_all": "",
        }

        _MARKER_RE = re.compile(
            r'^[▼►▲◄]\s*(?:[A-Z]\d*|\d+)[\s\-]*$', re.UNICODE
        )

        for row in grid[1:]:
            if not row:
                continue

            entry_num = _get(row, col["entry"])
            name_raw  = _get(row, col["name"])
            product   = _get(row, col["product"])
            max_conc  = _get(row, col["max_conc"])
            conditions= _get(row, col["conditions"])
            labelling = _get(row, col["labelling"])

            # Skip en-têtes répétés
            if any(kw in name_raw.lower() for kw in
                   ["substance", "name of", "chemical name", "dénomination"]):
                continue

            # ── Nettoyage des marqueurs d'amendement EUR-Lex ────────────
            if _MARKER_RE.match(entry_num.strip()) or _MARKER_RE.match(name_raw.strip()):
                continue
            # ex: "►M4 203" → "203" | "►C4 306 ◄" → "306"
            entry_num = re.sub(r'^[▼►▲◄]\s*[A-Z]\d*\s*', '', entry_num).strip()
            entry_num = re.sub(r'\s*[◄▼►▲]\s*$', '', entry_num).strip()

            # ── Fallback : product_type et max_conc depuis conditions ───
            # EUR-Lex III fusionne souvent colonnes c/d/e en une seule cellule.
            # Dans ce cas col["product"] et col["max_conc"] pointent sur la
            # même colonne que col["conditions"] → product et max_conc sont vides
            # mais conditions contient tout le texte.
            if not product and conditions:
                # Extraire la première ligne comme type de produit
                # ex: "(a) Rinse-off hair products\n(b) Leave-on products"
                first_line = conditions.split("\n")[0].strip()
                # Nettoyer les marqueurs (a), (b) etc.
                first_clean = re.sub(r'^\([a-z]\)\s*', '', first_line).strip()
                if first_clean and len(first_clean) < 120:
                    product = first_clean

            if not max_conc and conditions:
                # Chercher un pourcentage dans le texte de conditions
                m = re.search(r'(\d+[,.]?\d*)\s*%', conditions)
                if m:
                    max_conc = m.group(0).strip()  # ex: "0,5 %"

            # ── Ligne de CONTINUATION (rowspan) ─────────────────
            # Quand la cellule "nom" est identique à la ligne précédente
            # (grâce au rowspan résolu dans _build_grid), on détecte que
            # c'est la même substance avec un type de produit différent.
            is_continuation = (
                name_raw == current_substance["substance_name"]
                and current_substance["substance_name"] != ""
                and not _MARKER_RE.match(name_raw.strip())
                and (product or max_conc or conditions)
            )

            if is_continuation:
                entries.append({
                    "annex":              "III",
                    "status":             "restricted",
                    **{k: current_substance[k] for k in
                       ["entry_number", "substance_name",
                        "cas_number", "cas_all", "ec_number", "ec_all"]},
                    "product_type":       clean(product),
                    "max_concentration":  clean(max_conc),
                    "max_concentration_pct": _parse_concentration(max_conc),
                    "conditions":         clean(conditions),
                    "labelling":          clean(labelling),
                    "_continuation":      True,
                })
                continue

            # ── Nouvelle entrée substance ────────────────────────
            if not entry_num and not name_raw:
                continue
            if len(name_raw) < 2 and len(entry_num) < 1:
                continue

            # Extraire CAS/EC depuis colonnes dédiées ou depuis le nom
            cas_col = _get(row, col["cas"])
            ec_col  = _get(row, col["ec"])
            cas, ec = "", ""

            if cas_col:
                cas, _ = _extract_cas_ec(cas_col)
                if not cas:
                    cas = cas_col.strip()
            if ec_col:
                _, ec = _extract_cas_ec(ec_col)
                if not ec:
                    ec = ec_col.strip()

            # Toujours tenter l'extraction depuis le texte du nom
            # (EUR-Lex met souvent CAS/EC dans la même cellule que le nom)
            cas2, ec2 = _extract_cas_ec(name_raw)
            if not cas:
                cas = cas2
            if not ec:
                ec = ec2
            # Nettoyer le nom si CAS/EC y étaient inclus
            name_clean = _strip_cas_ec(name_raw) if (cas2 or ec2) else clean(name_raw)

            current_substance = {
                "entry_number":   clean(entry_num),
                "substance_name": name_clean,
                "cas_number":     _normalize_cas(cas.split(" | ")[0]) if cas else "",
                "cas_all":        cas,
                "ec_number":      ec.split(" | ")[0] if ec else "",
                "ec_all":         ec,
            }

            entries.append({
                "annex":              "III",
                "status":             "restricted",
                **current_substance,
                "product_type":       clean(product),
                "max_concentration":  clean(max_conc),
                "max_concentration_pct": _parse_concentration(max_conc),
                "conditions":         clean(conditions),
                "labelling":          clean(labelling),
                "_continuation":      False,
            })

    # Déduplication
    seen, unique = set(), []
    for e in entries:
        key = (e["entry_number"] + "|" +
               e["substance_name"][:30] + "|" +
               e["product_type"][:20])
        if key not in seen:
            seen.add(key)
            unique.append(e)

    log.info(f"  ✅ Annexe III : {len(unique)} entrée(s)")
    return unique


# ──────────────────────────────────────────────────────────────
# Helpers de normalisation
# ──────────────────────────────────────────────────────────────

def _normalize_cas(cas: str) -> str:
    """Normalise un numéro CAS au format standard XXXXXX-XX-X."""
    if not cas:
        return ""
    # Supprimer les espaces et normaliser les tirets
    cas = re.sub(r"\s+", "", cas)
    # Valider le format CAS : digits-digits-digit
    if re.match(r"^\d{2,7}-\d{2}-\d$", cas):
        return cas
    # Tenter de reformater
    digits = re.sub(r"[^0-9]", "", cas)
    if len(digits) >= 5:
        return f"{digits[:-3]}-{digits[-3:-1]}-{digits[-1]}"
    return cas


def _parse_concentration(text: str) -> float | None:
    """
    Extrait une valeur numérique de concentration depuis un texte.
    Exemples : "0,5 %", "1%", "up to 2 %", "maximum 0.5%"
    """
    if not text:
        return None
    # Cherche un nombre suivi de %
    m = re.search(r"(\d+[,.]?\d*)\s*%", text)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


# ──────────────────────────────────────────────────────────────
# Extraction des métadonnées du règlement
# ──────────────────────────────────────────────────────────────

def extract_regulation_metadata(soup: BeautifulSoup, celex: str) -> dict:
    """
    Extrait les métadonnées globales du règlement depuis le HTML.
    """
    title_tag = soup.find("title") or soup.find("h1")
    title     = clean(title_tag.get_text()) if title_tag else ""

    # Date de consolidation depuis le CELEX
    date_match = re.search(r"-(\d{8})$", celex)
    if date_match:
        raw = date_match.group(1)
        consolidation_date = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    else:
        consolidation_date = ""

    return {
        "regulation":          "Regulation (EC) No 1223/2009",
        "celex":               celex,
        "consolidation_date":  consolidation_date,
        "title":               title,
        "scrape_date":         datetime.now().isoformat()[:10],
        "source":              f"{EURLEX_BASE}/legal-content/EN/TXT/HTML/?uri=CELEX:{celex}",
    }


# ──────────────────────────────────────────────────────────────
# Mode multi-versions : tracking des changements
# ──────────────────────────────────────────────────────────────

def diff_versions(v_old: list[dict], v_new: list[dict],
                  key: str = "entry_number") -> dict:
    """
    Compare deux versions d'une annexe et retourne les ajouts/suppressions.
    Utile pour construire une time series des interdictions.
    """
    old_keys = {e.get(key): e for e in v_old if e.get(key)}
    new_keys = {e.get(key): e for e in v_new if e.get(key)}

    added   = [new_keys[k] for k in new_keys if k not in old_keys]
    removed = [old_keys[k] for k in old_keys if k not in new_keys]
    changed = []
    for k in new_keys:
        if k in old_keys:
            n, o = new_keys[k], old_keys[k]
            if n.get("substance_name") != o.get("substance_name"):
                changed.append({"key": k, "old": o, "new": n})

    return {"added": added, "removed": removed, "changed": changed}


# ──────────────────────────────────────────────────────────────
# Enrichissement PubChem : CAS et EC depuis le nom de substance
# ──────────────────────────────────────────────────────────────

PUBCHEM_URL = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"

def _pubchem_lookup(name: str) -> tuple[str, str]:
    """
    Cherche le CAS et le numéro EC d'une substance via l'API PubChem.

    Stratégie :
      1. Recherche du CID par nom (PUG REST /compound/name/{name}/cids)
      2. Récupération des synonymes du CID
      3. Extraction CAS (pattern XX-XX-X) et EC (pattern XXX-XXX-X)
         dans les synonymes (les CAS y apparaissent comme "XXXX-XX-X")

    Limitations connues :
      - Certains noms EUR-Lex sont génériques (ex: "Antibiotics") → pas de CID
      - Rate limit PubChem : 5 req/s environ → pause automatique
      - Si CID non trouvé le tuple ("", "") est retourné
    """
    name_clean = name.strip()
    if not name_clean or len(name_clean) < 4:
        return "", ""

    try:
        # Étape 1 : CID par nom
        r = requests.get(
            f"{PUBCHEM_URL}/compound/name/{requests.utils.quote(name_clean)}/cids/JSON",
            timeout=8,
        )
        if r.status_code == 404:
            return "", ""
        if r.status_code == 429:
            time.sleep(2)
            r = requests.get(
                f"{PUBCHEM_URL}/compound/name/{requests.utils.quote(name_clean)}/cids/JSON",
                timeout=8,
            )
        r.raise_for_status()
        cids = r.json().get("IdentifierList", {}).get("CID", [])
        if not cids:
            return "", ""

        cid = cids[0]

        # Étape 2 : synonymes du CID
        r2 = requests.get(
            f"{PUBCHEM_URL}/compound/cid/{cid}/synonyms/JSON",
            timeout=8,
        )
        if r2.status_code != 200:
            return "", ""
        synonyms = r2.json().get("InformationList", {}) \
                            .get("Information", [{}])[0] \
                            .get("Synonym", [])

        # Étape 3 : extraire CAS et EC depuis les synonymes
        cas, ec = "", ""
        for syn in synonyms:
            if not cas:
                m = _RE_CAS.match(syn.strip())
                if m:
                    cas = m.group(1)
            if not ec:
                m = _RE_EC.match(syn.strip())
                if m:
                    ec = m.group(1)
            if cas and ec:
                break

        return _normalize_cas(cas), ec

    except Exception:
        return "", ""


def enrich_with_pubchem(
    entries: list[dict],
    delay:   float = 0.22,   # ≈ 4.5 req/s, sous la limite PubChem
    max_entries: int | None = None,
) -> list[dict]:
    """
    Enrichit une liste d'entrées avec CAS et EC via PubChem.
    Ne touche aux entrées que si cas_number est vide.

    Args:
        entries     : liste des dicts (annex_II ou annex_III)
        delay       : pause entre chaque appel API (secondes)
        max_entries : limiter à N entrées (utile pour les tests)

    Returns:
        La liste mutée in-place (et retournée pour commodité).
    """
    to_enrich = [
        e for e in entries
        if not e.get("cas_number") and e.get("substance_name")
    ]
    if max_entries:
        to_enrich = to_enrich[:max_entries]

    log.info(f"  PubChem enrichissement : {len(to_enrich)} entrée(s) sans CAS")

    for i, entry in enumerate(to_enrich, 1):
        name = entry["substance_name"]
        # Tronquer si le nom contient des parenthèses ou "and" → prendre
        # la première partie qui est souvent le nom principal
        name_short = re.split(r'\s+and\s+|\s*\(', name)[0].strip()

        cas, ec = _pubchem_lookup(name_short)
        if cas:
            entry["cas_number"] = cas
            entry["cas_all"]    = cas
        if ec:
            entry["ec_number"] = ec
            entry["ec_all"]    = ec

        if i % 50 == 0:
            log.info(f"    {i}/{len(to_enrich)} traités "
                     f"({sum(1 for e in to_enrich[:i] if e.get('cas_number'))} CAS trouvés)")

        time.sleep(delay)

    found = sum(1 for e in to_enrich if e.get("cas_number"))
    log.info(f"  ✅ PubChem : {found}/{len(to_enrich)} CAS récupérés")
    return entries


# ──────────────────────────────────────────────────────────────
# Pipeline principal
# ──────────────────────────────────────────────────────────────

def scrape(
    annex:        int | None = None,   # None = toutes, 2 = II, 3 = III
    lang:         str        = "EN",
    all_versions: bool       = False,
    pubchem:      bool       = False,  # enrichissement CAS/EC via PubChem
    pubchem_max:  int | None = None,   # limiter le nb d'appels PubChem
) -> dict:
    """
    Pipeline principal :
      1. Récupère la(les) version(s) consolidée(s)
      2. Télécharge le HTML
      3. Parse les annexes demandées
      4. (Optionnel) Enrichit avec PubChem pour les CAS/EC manquants
    """
    log.info("=" * 65)
    log.info("  EUR-Lex — Annexes II & III — Règlement 1223/2009")
    log.info("=" * 65)

    results = {
        "metadata":   {},
        "annex_II":   [],
        "annex_III":  [],
        "amendments": [],
    }

    # ── Version unique (la plus récente) ──────────────────────
    log.info("\n[1/3] Identification de la version consolidée...")
    celex, html = get_latest_consolidated(lang)

    if not html:
        log.error("Impossible de télécharger le règlement consolidé.")
        return results

    log.info("\n[2/3] Parsing du HTML...")
    parser = "lxml" if _has_lxml() else "html.parser"
    soup   = BeautifulSoup(html, parser)
    results["metadata"] = extract_regulation_metadata(soup, celex)
    log.info(f"  Version : {celex} ({results['metadata']['consolidation_date']})")

    log.info("\n[3/3] Extraction des annexes...")
    if annex in (None, 2):
        results["annex_II"]  = parse_annex_II(soup)
    if annex in (None, 3):
        results["annex_III"] = parse_annex_III(soup)

    # ── Enrichissement PubChem (optionnel) ────────────────────
    if pubchem:
        log.info("\n[4/4] Enrichissement CAS/EC via PubChem...")
        if annex in (None, 2) and results["annex_II"]:
            enrich_with_pubchem(results["annex_II"],  max_entries=pubchem_max)
        if annex in (None, 3) and results["annex_III"]:
            enrich_with_pubchem(results["annex_III"], max_entries=pubchem_max)

    # ── Multi-versions (optionnel) ─────────────────────────────
    if all_versions:
        log.info("\n[BONUS] Mode multi-versions : tracking des changements...")
        lang_sparql = {"EN": "ENG", "FR": "FRA"}.get(lang.upper(), "ENG")
        versions    = get_consolidated_versions(lang_sparql)

        amendments  = []
        prev_ii     = results["annex_II"]
        prev_iii    = results["annex_III"]

        for v in versions[1:6]:  # 5 versions précédentes max
            log.info(f"  Version historique : {v['celex']} ({v['date']})")
            _, old_html = download_html_eurlex(v["celex"], lang), ""
            old_html    = download_html_eurlex(v["celex"], lang)
            if not old_html:
                continue
            old_soup = BeautifulSoup(old_html, "lxml" if _has_lxml() else "html.parser")
            old_ii   = parse_annex_II(old_soup)  if annex in (None, 2) else []
            old_iii  = parse_annex_III(old_soup) if annex in (None, 3) else []

            amendments.append({
                "from_version": v["celex"],
                "to_version":   celex,
                "date":         v["date"],
                "annex_II_diff":  diff_versions(old_ii, prev_ii),
                "annex_III_diff": diff_versions(old_iii, prev_iii),
            })
            prev_ii  = old_ii
            prev_iii = old_iii

        results["amendments"] = amendments

    return results


# ──────────────────────────────────────────────────────────────
# Affichage et export
# ──────────────────────────────────────────────────────────────

def print_summary(results: dict):
    meta = results["metadata"]
    sep  = "=" * 65
    print(f"\n{sep}")
    print(f"  EUR-Lex — {meta.get('regulation', '')}")
    print(f"{sep}")
    print(f"  CELEX               : {meta.get('celex', 'N/D')}")
    print(f"  Version consolidée  : {meta.get('consolidation_date', 'N/D')}")
    print(f"  Date de scraping    : {meta.get('scrape_date', '')}")
    print(f"  URL source          : {meta.get('source', '')}")
    print(f"\n  Annexe II  (interdites) : {len(results['annex_II'])} entrées")
    print(f"  Annexe III (restreintes): {len(results['annex_III'])} entrées")

    if results["annex_II"]:
        print(f"\n  Aperçu Annexe II (5 premières entrées) :")
        for e in results["annex_II"][:5]:
            print(f"    [{e.get('entry_number', '?')}] {e.get('substance_name', '?')[:60]}")
            if e.get("cas_number"):
                print(f"         CAS : {e['cas_number']}")

    if results["annex_III"]:
        print(f"\n  Aperçu Annexe III (5 premières entrées) :")
        for e in results["annex_III"][:5]:
            print(f"    [{e.get('entry_number', '?')}] {e.get('substance_name', '?')[:55]}")
            if e.get("max_concentration"):
                print(f"         Max : {e['max_concentration']} | Produit : {e.get('product_type', '?')[:40]}")


def save_json(results: dict, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log.info(f"  💾 JSON → {path}")


def save_csv(results: dict, base_path: Path):
    """Export CSV séparé pour Annexe II et Annexe III."""
    if not HAS_PANDAS:
        log.warning("  pandas requis pour l'export CSV — pip install pandas")
        return

    for annex_key, label in [("annex_II", "annex2"), ("annex_III", "annex3")]:
        data = results.get(annex_key, [])
        if not data:
            continue
        df   = pd.DataFrame(data)
        path = base_path.parent / f"{base_path.stem}_{label}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        log.info(f"  💾 CSV  → {path} ({len(df)} lignes)")


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="EUR-Lex Scraper — Annexes II & III (Règlement 1223/2009)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemples :
  python eurlex_scraper.py
  python eurlex_scraper.py --annex 2
  python eurlex_scraper.py --annex 3 --lang FR
  python eurlex_scraper.py --all-versions --csv
  python eurlex_scraper.py --output eurlex_cosmetics.json --csv
        """,
    )
    parser.add_argument(
        "--annex", type=int, choices=[2, 3], default=None,
        help="Annexe à scraper : 2 (interdites) ou 3 (restreintes). Défaut : toutes.",
    )
    parser.add_argument(
        "--lang", default="EN",
        help="Langue du document (EN, FR, DE). Défaut : EN.",
    )
    parser.add_argument(
        "--all-versions", action="store_true",
        help="Récupérer aussi les versions historiques et calculer les diffs.",
    )
    parser.add_argument(
        "--output", default="eurlex_annexes.json",
        help="Fichier JSON de sortie (défaut : eurlex_annexes.json).",
    )
    parser.add_argument(
        "--csv", action="store_true",
        help="Exporter aussi en CSV (un fichier par annexe).",
    )
    parser.add_argument(
        "--pubchem", action="store_true",
        help="Enrichir les CAS/EC manquants via l'API PubChem (lent, ~0.25s/entrée).",
    )
    parser.add_argument(
        "--pubchem-max", type=int, default=None,
        metavar="N",
        help="Limiter l'enrichissement PubChem à N entrées (test/débogage).",
    )
    args = parser.parse_args()

    results = scrape(
        annex=args.annex,
        lang=args.lang.upper(),
        all_versions=args.all_versions,
        pubchem=args.pubchem,
        pubchem_max=args.pubchem_max,
    )

    print_summary(results)

    out = Path(args.output)
    save_json(results, out)

    if args.csv:
        save_csv(results, out)

    log.info(f"\n✅ Terminé")
    log.info(f"   Annexe II  : {len(results['annex_II'])} substances interdites")
    log.info(f"   Annexe III : {len(results['annex_III'])} substances restreintes")


if __name__ == "__main__":
    main()