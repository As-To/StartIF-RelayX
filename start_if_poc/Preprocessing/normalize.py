"""
Normalize Profile A raw files into one unified JSON file per ingredient.

Inputs:
- start_if_poc/scrapping/sccs_results.json
- start_if_poc/scrapping/aggregate_sccs_results.json

Output:
- start_if_poc/Preprocessing/data/ingredients/<ingredient_slug>.json
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def normalize_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    value = str(value).strip().lower()
    value = "".join(
        c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn"
    )
    value = re.sub(r"\s+", " ", value)
    return value


def safe_strip(value: Any) -> Optional[str]:
    if value is None:
        return None
    txt = str(value).strip()
    return txt or None


def parse_cas_ec(cas_ec_raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    if not cas_ec_raw:
        return None, None
    text = str(cas_ec_raw)
    cas_match = re.findall(r"\b\d{2,7}-\d{2}-\d\b", text)
    ec_match = re.findall(r"\b\d{3}-\d{3}-\d\b", text)
    cas = cas_match[0] if cas_match else None
    ec = ec_match[0] if ec_match else None
    return cas, ec


def parse_date(date_value: Optional[str]) -> Optional[datetime]:
    if not date_value:
        return None
    txt = str(date_value).strip()
    if not txt:
        return None

    # Try strict ISO date first
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%Y"):
        try:
            return datetime.strptime(txt, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # Flexible fallback: extract year/month/day if present
    m = re.search(r"(20\d{2}|19\d{2})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?", txt)
    if m:
        year = int(m.group(1))
        month = int(m.group(2)) if m.group(2) else 1
        day = int(m.group(3)) if m.group(3) else 1
        try:
            return datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            return None

    return None


def to_iso_date(date_value: Optional[str]) -> Optional[str]:
    dt = parse_date(date_value)
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d")


def slugify_filename(value: str) -> str:
    txt = normalize_text(value)
    txt = re.sub(r"[^a-z0-9]+", "_", txt)
    txt = re.sub(r"_+", "_", txt).strip("_")
    return txt or "unknown_ingredient"


def first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        cleaned = safe_strip(value)
        if cleaned:
            return cleaned
    return None


def parse_percent(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    txt = str(value).replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", txt)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def choose_canonical_name(sccs_rows: List[Dict[str, Any]]) -> str:
    names = [safe_strip(r.get("Ingredient")) for r in sccs_rows]
    names = [n for n in names if n]
    if not names:
        return "Unknown ingredient"

    normalized_counter = Counter(normalize_text(n) for n in names)
    if not normalized_counter:
        return names[0]

    best_norm = normalized_counter.most_common(1)[0][0]
    best_candidates = [n for n in names if normalize_text(n) == best_norm]
    best_candidates.sort(key=lambda x: (len(x), x))
    return best_candidates[0]


def extract_sccs_group(sccs_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_number: Dict[str, Dict[str, Any]] = {}

    for row in sccs_rows:
        sccs_number = safe_strip(row.get("SCCS_Number"))
        if not sccs_number:
            continue
        if sccs_number not in by_number:
            by_number[sccs_number] = row

    avis: List[Dict[str, Any]] = []
    certitudes: List[str] = []

    for row in by_number.values():
        avis_item = {
            "sccs_number": safe_strip(row.get("SCCS_Number")),
            "date_avis": to_iso_date(row.get("Date_Avis")),
            "type_rapport": safe_strip(row.get("Type_Rapport")),
            "verdict": safe_strip(row.get("Verdict")),
            "concentration_max": safe_strip(row.get("Concentration_Max")),
            "categorie": safe_strip(row.get("Categorie")),
            "conclusion": safe_strip(row.get("_conclusion")),
            "abstract": safe_strip(row.get("Abstract_all_text")),
            "pdf_url": safe_strip(row.get("_pdf_url")),
        }
        avis.append(avis_item)

        cert = first_non_empty(row.get("certitude"), row.get("_certitude"), row.get("llm_certitude"))
        if cert:
            certitudes.append(cert)

    # Sort by date desc (unknown dates at end)
    avis.sort(
        key=lambda a: parse_date(a.get("date_avis")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    latest_verdict = None
    for item in avis:
        if item.get("verdict"):
            latest_verdict = item["verdict"]
            break

    certitude = certitudes[0] if certitudes else None

    return {
        "nb_avis": len(avis),
        "avis": avis,
        "dernier_verdict": latest_verdict,
        "certitude": certitude,
    }


def collect_source_matches(
    source_map: Dict[str, Any],
    ingredient_name: str,
    cas: Optional[str],
) -> List[Any]:
    """
    Match source entries using:
    1) CAS equality (if available)
    2) ingredient name (normalized)
    """
    target_name = normalize_text(ingredient_name)
    target_cas = normalize_text(cas)

    matches: List[Any] = []
    for key, value in source_map.items():
        key_norm = normalize_text(key)

        value_cas = first_non_empty(
            value.get("CAS"),
            value.get("cas"),
            value.get("cas_query"),
        ) if isinstance(value, dict) else None
        value_cas_norm = normalize_text(value_cas)

        by_cas = bool(target_cas and value_cas_norm and value_cas_norm == target_cas)
        by_name = bool(target_name and key_norm == target_name)

        if by_cas or by_name:
            matches.append(value)

    return matches


def build_eurlex_block(eurlex_match: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    eurlex_match = eurlex_match or {}

    annex_ii_entries = eurlex_match.get("annex_II") if isinstance(eurlex_match, dict) else None
    annex_iii_entries = eurlex_match.get("annex_III") if isinstance(eurlex_match, dict) else None

    in_annex_ii = bool(annex_ii_entries)
    in_annex_iii = bool(annex_iii_entries)

    annex_iii_details = None
    if in_annex_iii:
        first = annex_iii_entries[0]
        annex_iii_details = {
            "entry_number": first_non_empty(first.get("entry_number")),
            "product_type": first_non_empty(first.get("product_type")),
            "max_concentration": first_non_empty(first.get("max_concentration")),
            "max_concentration_pct": parse_percent(first.get("max_concentration")),
            "conditions": first_non_empty(first.get("conditions")),
            "labelling": first_non_empty(first.get("labelling")),
        }

    return {
        "in_annex_II": in_annex_ii,
        "in_annex_III": in_annex_iii,
        "annex_III_details": annex_iii_details,
    }


def build_pubchem_block(pubchem_match: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    pubchem_match = pubchem_match or {}
    synonyms = pubchem_match.get("Synonyms")
    if not isinstance(synonyms, list):
        synonyms = []

    return {
        "cid": pubchem_match.get("CID"),
        "molecular_formula": pubchem_match.get("Molecular formula"),
        "molecular_weight": pubchem_match.get("Molecular weight"),
        "xlogp": pubchem_match.get("XLogP") or None,
        "tpsa": pubchem_match.get("TPSA"),
        "ghs_hazards": pubchem_match.get("GHS Hazards") or pubchem_match.get("GHS") or None,
        "signal_word": pubchem_match.get("Signal Word") or None,
        "uses": pubchem_match.get("Uses") or None,
        "synonyms": synonyms,
    }


def build_pubmed_block(pubmed_match: Any, now_utc: datetime) -> Dict[str, Any]:
    articles = pubmed_match if isinstance(pubmed_match, list) else []

    simplified_articles: List[Dict[str, Any]] = []
    for art in articles:
        if not isinstance(art, dict):
            continue
        if art.get("error"):
            continue
        simplified_articles.append(
            {
                "pmid": first_non_empty(art.get("pmid")),
                "doi": first_non_empty(art.get("doi")),
                "title": first_non_empty(art.get("title")),
                "abstract": first_non_empty(art.get("abstract")),
                "journal": first_non_empty(art.get("journal")),
                "date": first_non_empty(art.get("date")),
                "mesh": art.get("mesh") if isinstance(art.get("mesh"), list) else [],
                "keywords": art.get("keywords") if isinstance(art.get("keywords"), list) else [],
                "relevance_score": art.get("relevance_score"),
            }
        )

    cutoff = now_utc - timedelta(days=365)
    nb_12m = 0
    for art in simplified_articles:
        dt = parse_date(art.get("date"))
        if dt and dt >= cutoff:
            nb_12m += 1

    return {
        "nb_articles_total": len(simplified_articles),
        "nb_articles_12mois": nb_12m,
        "articles": simplified_articles,
    }


def build_cosing_block(cosing_match: Optional[Dict[str, Any]], fallback_inci: str) -> Dict[str, Any]:
    cosing_match = cosing_match or {}

    inci_name = first_non_empty(cosing_match.get("INCI_Name"), fallback_inci)
    function = first_non_empty(cosing_match.get("Function"))
    restriction = first_non_empty(cosing_match.get("Restriction"))
    sccs_url = first_non_empty(cosing_match.get("SCCS_Opinion"), cosing_match.get("Source_URL"))

    return {
        "inci_name": inci_name,
        "function": function,
        "restriction": restriction,
        "has_sccs_opinion": bool(sccs_url),
        "sccs_opinion_url": sccs_url,
    }


def build_echa_block(echa_match: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    echa_match = echa_match or {}

    is_svhc = bool(echa_match.get("is_svhc") or echa_match.get("svhc") or False)
    return {
        "is_svhc": is_svhc,
        "svhc_date": first_non_empty(echa_match.get("svhc_date")),
        "classification_clp": echa_match.get("classification_clp") if isinstance(echa_match.get("classification_clp"), list) else None,
        "uses": echa_match.get("uses") if isinstance(echa_match.get("uses"), list) else None,
        "tonnage": first_non_empty(echa_match.get("tonnage")),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize SCCS profile data into one JSON per ingredient")
    parser.add_argument(
        "--input-sccs",
        default=None,
        help="Path to sccs_results.json (default: ../scrapping/sccs_results.json)",
    )
    parser.add_argument(
        "--input-aggregate",
        default=None,
        help="Path to aggregate_sccs_results.json (default: ../scrapping/aggregate_sccs_results.json)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output folder for one JSON per ingredient (default: ./data/ingredients)",
    )
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent

    input_sccs = Path(args.input_sccs) if args.input_sccs else (script_dir.parent / "scrapping" / "sccs_results.json")
    input_aggregate = (
        Path(args.input_aggregate)
        if args.input_aggregate
        else (script_dir.parent / "scrapping" / "aggregate_sccs_results.json")
    )
    output_dir = Path(args.output_dir) if args.output_dir else (script_dir / "data" / "ingredients")

    if not input_sccs.exists():
        raise FileNotFoundError(f"Input SCCS file not found: {input_sccs}")
    if not input_aggregate.exists():
        raise FileNotFoundError(f"Input aggregate file not found: {input_aggregate}")

    output_dir.mkdir(parents=True, exist_ok=True)

    sccs_rows = load_json(input_sccs)
    aggregate = load_json(input_aggregate)

    if not isinstance(sccs_rows, list):
        raise ValueError("sccs_results.json must be a list of SCCS rows")
    if not isinstance(aggregate, dict):
        raise ValueError("aggregate_sccs_results.json must be a dictionary")

    # Group SCCS rows by pivot key: CAS first, otherwise normalized ingredient name.
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in sccs_rows:
        ingredient = safe_strip(row.get("Ingredient"))
        cas, _ec = parse_cas_ec(row.get("CAS_EC"))
        pivot_key = f"cas::{cas}" if cas else f"name::{normalize_text(ingredient)}"
        grouped[pivot_key].append(row)

    cosing_map = aggregate.get("cosing", {}) if isinstance(aggregate.get("cosing"), dict) else {}
    pubchem_map = aggregate.get("pubchem", {}) if isinstance(aggregate.get("pubchem"), dict) else {}
    pubmed_map = aggregate.get("pubmed", {}) if isinstance(aggregate.get("pubmed"), dict) else {}
    eurlex_map = aggregate.get("eurlex", {}) if isinstance(aggregate.get("eurlex"), dict) else {}
    echa_map = aggregate.get("echa", {}) if isinstance(aggregate.get("echa"), dict) else {}

    now_utc = datetime.now(timezone.utc)

    generated = 0
    for _pivot, rows in grouped.items():
        canonical_name = choose_canonical_name(rows)

        # Prefer first row for main identity fields
        base = rows[0]
        cas, ec = parse_cas_ec(base.get("CAS_EC"))

        # Try to enrich CAS/EC from matched pubchem/cosing if missing
        pubchem_matches = collect_source_matches(pubchem_map, canonical_name, cas)
        cosing_matches = collect_source_matches(cosing_map, canonical_name, cas)

        pubchem_match = pubchem_matches[0] if pubchem_matches else None
        cosing_match = cosing_matches[0] if cosing_matches else None

        if not cas:
            cas = first_non_empty(
                pubchem_match.get("CAS") if isinstance(pubchem_match, dict) else None,
                cosing_match.get("CAS") if isinstance(cosing_match, dict) else None,
            )
        if not ec:
            ec = first_non_empty(
                pubchem_match.get("EC") if isinstance(pubchem_match, dict) else None,
                cosing_match.get("EC") if isinstance(cosing_match, dict) else None,
            )

        inci_name = first_non_empty(
            cosing_match.get("INCI_Name") if isinstance(cosing_match, dict) else None,
            canonical_name.upper(),
        )

        # Section builders
        sccs_block = extract_sccs_group(rows)

        eurlex_candidates = collect_source_matches(eurlex_map, canonical_name, cas)
        eurlex_match = eurlex_candidates[0] if eurlex_candidates else None
        eurlex_block = build_eurlex_block(eurlex_match)

        echa_candidates = collect_source_matches(echa_map, canonical_name, cas)
        echa_match = echa_candidates[0] if echa_candidates else None
        echa_block = build_echa_block(echa_match)

        pubmed_candidates = collect_source_matches(pubmed_map, canonical_name, cas)
        pubmed_match = pubmed_candidates[0] if pubmed_candidates else []
        pubmed_block = build_pubmed_block(pubmed_match, now_utc)

        pubchem_block = build_pubchem_block(pubchem_match)
        cosing_block = build_cosing_block(cosing_match, fallback_inci=inci_name)

        out_obj = {
            "ingredient": canonical_name,
            "cas": cas,
            "ec": ec,
            "inci_name": inci_name,
            "sccs": sccs_block,
            "eurlex": eurlex_block,
            "echa": echa_block,
            "pubmed": pubmed_block,
            "pubchem": pubchem_block,
            "cosing": cosing_block,
        }

        file_name = slugify_filename(canonical_name) + ".json"
        out_path = output_dir / file_name
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(out_obj, f, ensure_ascii=False, indent=2)

        generated += 1

    print(f"✅ Done. {generated} ingredient files generated in: {output_dir}")


if __name__ == "__main__":
    main()
