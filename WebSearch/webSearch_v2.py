import re
import csv
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

try:
    from ddgs import DDGS
except ImportError:
    raise SystemExit(
        "Le package 'ddgs' est requis.\n"
        "Installe-le avec : pip install ddgs beautifulsoup4 requests"
    )

# ============================================================
# CONFIGURATION
# ============================================================

TRUSTED_DOMAINS = {
    "echa.europa.eu": 3,
    "health.ec.europa.eu": 3,
    "ec.europa.eu": 3,
    "eur-lex.europa.eu": 3,
    "pubmed.ncbi.nlm.nih.gov": 3,
    "ncbi.nlm.nih.gov": 3,
    "efsa.europa.eu": 2,
    "oecd.org": 2,
    "who.int": 2,
    "pubchem.ncbi.nlm.nih.gov": 2,
    "cosmeticseurope.eu": 1,
    "personalcareinsights.com": 1,
    "cosmeticsbusiness.com": 1,
    "chemicalwatch.com": 2,
}

BLACKLIST_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "pinterest.com",
    "amazon.com",
    "linkedin.com",
}

KEYWORDS = {
    "toxicity": 2,
    "toxic": 2,
    "safety": 2,
    "safe": 1,
    "risk": 2,
    "concern": 2,
    "restriction": 3,
    "restricted": 3,
    "ban": 3,
    "banned": 3,
    "prohibit": 3,
    "prohibited": 3,
    "sccs": 3,
    "cosmetic": 2,
    "regulation": 2,
    "regulatory": 2,
    "echa": 2,
    "clp": 2,
    "reach": 2,
    "cmr": 2,
    "endocrine": 2,
    "exposure": 2,
    "hazard": 2,
    "opinion": 2,
    "scientific advice": 2,
}

SIGNAL_WEAK_PATTERNS = [
    r"under review",
    r"further assessment",
    r"potential risk",
    r"safety concern",
    r"concern raised",
    r"emerging evidence",
    r"new evidence",
    r"classification proposal",
    r"public consultation",
    r"scientific opinion",
    r"not safe",
    r"safe when used up to",
    r"restriction",
    r"draft regulation",
]

MAX_RESULTS_PER_QUERY = 10
INITIAL_MIN_SCORE = 3

# Nombre maximum de pages qu'on ouvre réellement
TOP_N_FOR_HTML_FETCH = 8

# Timeout HTTP
REQUEST_TIMEOUT = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; StartIF-RelayX-Agent/0.2; "
        "+https://example.com/bot-info)"
    )
}


# ============================================================
# OUTILS GÉNÉRAUX
# ============================================================

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def find_year_in_text(text: str):
    if not text:
        return None
    current_year = datetime.now().year
    matches = re.findall(r"\b(20\d{2})\b", text)
    years = [int(y) for y in matches if 2000 <= int(y) <= current_year]
    return max(years) if years else None


def score_keywords(text: str):
    score = 0
    hits = []
    clean = normalize_text(text)
    for kw, kw_score in KEYWORDS.items():
        if kw in clean:
            score += kw_score
            hits.append(kw)
    return score, hits


def score_weak_signals(text: str):
    score = 0
    hits = []
    clean = normalize_text(text)
    for pattern in SIGNAL_WEAK_PATTERNS:
        if re.search(pattern, clean):
            score += 2
            hits.append(pattern)
    return score, hits


# ============================================================
# CONSTRUCTION DES REQUÊTES
# ============================================================

def build_queries(ingredient: str):
    ingredient = ingredient.strip()
    return [
        f'"{ingredient}" cosmetic SCCS safety opinion Europe',
        f'"{ingredient}" toxicity cosmetic regulation EU restriction',
        f'"{ingredient}" ECHA CLP REACH cosmetic risk',
        f'"{ingredient}" "used in cosmetic products" SCCS',
        f'"{ingredient}" ban restriction cosmetic Europe',
    ]


# ============================================================
# RECHERCHE WEB
# ============================================================

def web_search(query: str, max_results: int = 10):
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title": r.get("title", "") or "",
                "url": r.get("href", "") or "",
                "snippet": r.get("body", "") or "",
            })
    return results


# ============================================================
# SCORING NIVEAU 1 : TITLE + SNIPPET + URL
# ============================================================

def score_result_light(title: str, snippet: str, url: str):
    score = 0
    reasons = []

    domain = extract_domain(url)
    combined = f"{title} {snippet}"

    # Domaine
    if domain in TRUSTED_DOMAINS:
        domain_score = TRUSTED_DOMAINS[domain]
        score += domain_score
        reasons.append(f"source fiable (+{domain_score}) : {domain}")
    elif domain in BLACKLIST_DOMAINS:
        score -= 5
        reasons.append(f"source blacklistée (-5) : {domain}")
    else:
        score += 1
        reasons.append(f"source non prioritaire mais acceptée (+1) : {domain}")

    # Mots-clés
    kw_score, kw_hits = score_keywords(combined)
    score += kw_score
    if kw_hits:
        reasons.append(f"keywords (+{kw_score}) : {', '.join(sorted(set(kw_hits)))}")

    # Signaux faibles
    weak_score, weak_hits = score_weak_signals(combined)
    score += weak_score
    if weak_hits:
        reasons.append(f"weak signals (+{weak_score}) : {len(weak_hits)}")

    # Fraîcheur à partir du snippet/titre
    year = find_year_in_text(combined)
    if year:
        current_year = datetime.now().year
        age = current_year - year
        if age <= 1:
            score += 3
            reasons.append(f"très récent (+3) : {year}")
        elif age <= 3:
            score += 2
            reasons.append(f"récent (+2) : {year}")
        elif age <= 5:
            score += 1
            reasons.append(f"encore exploitable (+1) : {year}")
        else:
            reasons.append(f"ancien (+0) : {year}")
    else:
        reasons.append("date non trouvée dans snippet/titre (+0)")

    return score, reasons, year


# ============================================================
# FETCH HTML + EXTRACTION
# ============================================================

def fetch_html(url: str):
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200 and "text/html" in response.headers.get("Content-Type", ""):
            return response.text
    except Exception:
        return None
    return None


def extract_date_from_html(soup: BeautifulSoup, html_text: str):
    """
    Essaie plusieurs stratégies :
    - meta article:published_time
    - meta publication_date
    - balise <time datetime=...>
    - regex dans le HTML visible
    """
    meta_candidates = [
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"name": "publication_date"},
        {"name": "pubdate"},
        {"name": "date"},
        {"name": "dc.date"},
        {"property": "og:updated_time"},
    ]

    for attrs in meta_candidates:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            content = tag["content"]
            year = find_year_in_text(content)
            if year:
                return content, year

    time_tag = soup.find("time")
    if time_tag:
        if time_tag.get("datetime"):
            dt = time_tag.get("datetime")
            year = find_year_in_text(dt)
            if year:
                return dt, year
        time_text = time_tag.get_text(" ", strip=True)
        year = find_year_in_text(time_text)
        if year:
            return time_text, year

    visible_text = soup.get_text(" ", strip=True)
    year = find_year_in_text(visible_text[:5000])
    if year:
        return str(year), year

    year = find_year_in_text(html_text[:5000])
    if year:
        return str(year), year

    return None, None


def extract_main_text(soup: BeautifulSoup):
    """
    Extraction simple :
    - on supprime script/style/nav/footer/header
    - on privilégie <article> si présent
    - sinon on prend le texte global
    """
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()

    article = soup.find("article")
    if article:
        text = article.get_text(" ", strip=True)
    else:
        body = soup.find("body")
        text = body.get_text(" ", strip=True) if body else soup.get_text(" ", strip=True)

    text = re.sub(r"\s+", " ", text).strip()
    return text[:12000]  # on tronque pour rester raisonnable


# ============================================================
# SCORING NIVEAU 2 : HTML
# ============================================================

def enrich_with_html(result):
    html = fetch_html(result["url"])
    if not html:
        result["html_fetched"] = False
        result["html_text"] = ""
        result["date_from_html"] = None
        result["year_from_html"] = None
        return result

    soup = BeautifulSoup(html, "html.parser")
    main_text = extract_main_text(soup)
    date_raw, year_html = extract_date_from_html(soup, html)

    result["html_fetched"] = True
    result["html_text"] = main_text
    result["date_from_html"] = date_raw
    result["year_from_html"] = year_html
    return result


def rescore_with_html(result):
    """
    On repart du score initial et on ajoute des points
    si le HTML confirme la pertinence.
    """
    score = result["score"]
    reasons = list(result["reasons_list"])

    if not result.get("html_fetched"):
        reasons.append("html non récupéré (+0)")
        result["final_score"] = score
        result["final_reasons"] = " | ".join(reasons)
        return result

    html_text = result.get("html_text", "")

    # Mots-clés dans le texte réel
    kw_score, kw_hits = score_keywords(html_text)
    html_kw_bonus = min(kw_score, 10)  # pour éviter qu'un gros HTML explose le score
    score += html_kw_bonus
    if kw_hits:
        reasons.append(f"html keywords (+{html_kw_bonus}) : {', '.join(sorted(set(kw_hits))[:8])}")

    # Signaux faibles dans le texte réel
    weak_score, weak_hits = score_weak_signals(html_text)
    html_weak_bonus = min(weak_score, 6)
    score += html_weak_bonus
    if weak_hits:
        reasons.append(f"html weak signals (+{html_weak_bonus}) : {len(weak_hits)}")

    # Date HTML plus fiable
    year_html = result.get("year_from_html")
    if year_html:
        current_year = datetime.now().year
        age = current_year - year_html
        if age <= 1:
            score += 2
            reasons.append(f"html date très récente (+2) : {year_html}")
        elif age <= 3:
            score += 1
            reasons.append(f"html date récente (+1) : {year_html}")
        else:
            reasons.append(f"html date ancienne (+0) : {year_html}")
    else:
        reasons.append("date non trouvée dans html (+0)")

    result["final_score"] = score
    result["final_reasons"] = " | ".join(reasons)
    return result


# ============================================================
# AGENT
# ============================================================

def autonomous_agent_search_v2(ingredient: str):
    queries = build_queries(ingredient)
    candidate_results = []
    seen_urls = set()

    # Étape 1 : recherche + scoring léger
    for query in queries:
        print(f"\n[Recherche] {query}")
        try:
            raw_results = web_search(query, max_results=MAX_RESULTS_PER_QUERY)
        except Exception as e:
            print(f"Erreur pendant la recherche : {e}")
            continue

        print(f"Nombre de résultats bruts : {len(raw_results)}")

        for result in raw_results:
            url = result["url"]
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            score, reasons, year_detected = score_result_light(
                result["title"],
                result["snippet"],
                result["url"]
            )

            if score >= INITIAL_MIN_SCORE:
                candidate_results.append({
                    "ingredient": ingredient,
                    "query": query,
                    "title": result["title"],
                    "url": result["url"],
                    "domain": extract_domain(result["url"]),
                    "snippet": result["snippet"],
                    "score": score,
                    "year_detected": year_detected,
                    "reasons_list": reasons,
                    "html_fetched": False,
                    "html_text": "",
                    "date_from_html": None,
                    "year_from_html": None,
                    "final_score": score,
                    "final_reasons": " | ".join(reasons),
                })

    # Tri intermédiaire
    candidate_results.sort(key=lambda x: x["score"], reverse=True)

    # Étape 2 : on ouvre seulement les top N
    top_for_html = candidate_results[:TOP_N_FOR_HTML_FETCH]
    for i, result in enumerate(top_for_html, start=1):
        print(f"[HTML] {i}/{len(top_for_html)} -> {result['url']}")
        enrich_with_html(result)
        rescore_with_html(result)
        time.sleep(1)  # petite pause par prudence

    # Étape 3 : résultats finaux
    final_results = candidate_results
    final_results.sort(key=lambda x: x["final_score"], reverse=True)

    return final_results


# ============================================================
# EXPORT CSV
# ============================================================

def export_to_csv(results, output_file="websearch_results_v2.csv"):
    fieldnames = [
        "ingredient",
        "query",
        "title",
        "url",
        "domain",
        "year_detected",
        "date_from_html",
        "year_from_html",
        "score",
        "final_score",
        "snippet",
        "final_reasons",
        "html_fetched",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "ingredient": r["ingredient"],
                "query": r["query"],
                "title": r["title"],
                "url": r["url"],
                "domain": r["domain"],
                "year_detected": r["year_detected"],
                "date_from_html": r["date_from_html"],
                "year_from_html": r["year_from_html"],
                "score": r["score"],
                "final_score": r["final_score"],
                "snippet": r["snippet"],
                "final_reasons": r["final_reasons"],
                "html_fetched": r["html_fetched"],
            })

    print(f"\nRésultats exportés dans : {output_file}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    ingredient = input("Nom de l’ingrédient à analyser : ").strip()
    if not ingredient:
        raise SystemExit("Aucun ingrédient fourni.")

    results = autonomous_agent_search_v2(ingredient)

    if not results:
        print("\nAucun résultat pertinent trouvé.")
    else:
        print("\nTop résultats retenus :\n")
        for i, r in enumerate(results[:10], start=1):
            print(f"{i}. [{r['final_score']}] {r['title']}")
            print(f"   URL         : {r['url']}")
            print(f"   Domaine     : {r['domain']}")
            print(f"   Année snip. : {r['year_detected']}")
            print(f"   Année HTML  : {r['year_from_html']}")
            print(f"   HTML lu ?   : {r['html_fetched']}")
            print(f"   Extrait     : {r['snippet'][:220]}")
            print(f"   Raisons     : {r['final_reasons']}")
            print()

        export_to_csv(results)