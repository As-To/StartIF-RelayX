import re
import csv
from datetime import datetime
from urllib.parse import urlparse

try:
    from ddgs import DDGS
except ImportError:
    raise SystemExit(
        "Le package 'ddgs' est requis.\n"
        "Installe-le avec : pip install -U ddgs"
    )

# ----------------------------
# Configuration
# ----------------------------

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
]

MAX_RESULTS_PER_QUERY = 10
MIN_SCORE_TO_KEEP = 3


# ----------------------------
# Utilitaires
# ----------------------------

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def parse_year(text: str):
    """
    DuckDuckGo retourne parfois une date, parfois non.
    On essaie de repérer une année entre 2000 et l'année courante.
    """
    if not text:
        return None

    current_year = datetime.now().year
    matches = re.findall(r"\b(20\d{2})\b", text)
    years = [int(y) for y in matches if 2000 <= int(y) <= current_year]
    return max(years) if years else None


# ----------------------------
# Construction de requêtes
# ----------------------------

def build_queries(ingredient: str):
    ingredient = ingredient.strip()
    return [
        f'"{ingredient}" toxicity cosmetic regulation EU restriction',
        f'"{ingredient}" SCCS cosmetic safety opinion EU',
        f'"{ingredient}" ECHA CLP REACH risk',
        f'"{ingredient}" endocrine disruption cosmetic concern',
        f'"{ingredient}" ban restriction cosmetic Europe',
    ]


# ----------------------------
# Scoring / filtrage
# ----------------------------

def score_result(title: str, snippet: str, url: str):
    score = 0
    reasons = []

    domain = extract_domain(url)
    text = normalize_text(f"{title} {snippet}")

    # 1) Fiabilité de la source
    # if domain in TRUSTED_DOMAINS:
    #     domain_score = TRUSTED_DOMAINS[domain]
    #     score += domain_score
    #     reasons.append(f"source fiable (+{domain_score}) : {domain}")
    # elif domain in BLACKLIST_DOMAINS:
    #     score -= 5
    #     reasons.append(f"source blacklistée (-5) : {domain}")
    # else:
    #     reasons.append(f"source non prioritaire (+0) : {domain}")
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

    # 2) Pertinence thématique par mots-clés
    keyword_hits = 0
    for kw, kw_score in KEYWORDS.items():
        if kw in text:
            score += kw_score
            keyword_hits += 1
    if keyword_hits:
        reasons.append(f"mots-clés détectés ({keyword_hits})")

    # 3) Détection de signaux faibles
    weak_hits = 0
    for pattern in SIGNAL_WEAK_PATTERNS:
        if re.search(pattern, text):
            score += 2
            weak_hits += 1
    if weak_hits:
        reasons.append(f"signaux faibles détectés ({weak_hits})")

    # 4) Fraîcheur temporelle
    year = parse_year(f"{title} {snippet}")
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
        reasons.append("date non trouvée (+0)")

    return score, reasons


# ----------------------------
# Recherche web
# ----------------------------

def web_search(query: str, max_results: int = 10):
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            # clés fréquentes : title, href, body
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })
    return results


# ----------------------------
# Agent minimal
# ----------------------------

def autonomous_agent_search(ingredient: str):
    queries = build_queries(ingredient)
    kept_results = []
    seen_urls = set()

    for query in queries:
        print(f"\n[Recherche] {query}")
        try:
            raw_results = web_search(query, max_results=MAX_RESULTS_PER_QUERY)
            print(f"Nombre de résultats bruts : {len(raw_results)}")
            for r in raw_results[:3]:
                print("TITLE:", r["title"])
                print("URL:", r["url"])
                print("SNIPPET:", r["snippet"])
                print()
        except Exception as e:
            print(f"Erreur pendant la recherche : {e}")
            continue

        for result in raw_results:
            url = result["url"]
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            score, reasons = score_result(
                result["title"],
                result["snippet"],
                result["url"]
            )

            if score >= MIN_SCORE_TO_KEEP:
                kept_results.append({
                    "ingredient": ingredient,
                    "query": query,
                    "title": result["title"],
                    "url": result["url"],
                    "snippet": result["snippet"],
                    "score": score,
                    "reasons": " | ".join(reasons),
                    "domain": extract_domain(result["url"]),
                    "year_detected": parse_year(
                        f"{result['title']} {result['snippet']}"
                    ),
                })

    # tri décroissant par score
    kept_results.sort(key=lambda x: x["score"], reverse=True)
    return kept_results


# ----------------------------
# Export CSV
# ----------------------------

def export_to_csv(results, output_file="agent_results.csv"):
    fieldnames = [
        "ingredient",
        "query",
        "title",
        "url",
        "domain",
        "year_detected",
        "score",
        "snippet",
        "reasons",
    ]

    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nRésultats exportés dans : {output_file}")


# ----------------------------
# Main
# ----------------------------

if __name__ == "__main__":
    ingredient = input("Nom de l’ingrédient à analyser : ").strip()
    if not ingredient:
        raise SystemExit("Aucun ingrédient fourni.")

    results = autonomous_agent_search(ingredient)

    if not results:
        print("\nAucun résultat pertinent trouvé.")
    else:
        print("\nTop résultats retenus :\n")
        for i, r in enumerate(results[:10], start=1):
            print(f"{i}. [{r['score']}] {r['title']}")
            print(f"   URL      : {r['url']}")
            print(f"   Domaine  : {r['domain']}")
            print(f"   Extrait  : {r['snippet']}")
            print(f"   Raisons  : {r['reasons']}")
            print()

        export_to_csv(results)