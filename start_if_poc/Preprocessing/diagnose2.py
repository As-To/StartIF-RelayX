"""Writes diagnostic data to a JSON file for easy inspection."""
import json
from pathlib import Path

base = Path(__file__).resolve().parent.parent / "scrapping"
data = json.load(open(base / "sccs_results.json", encoding="utf-8"))

# Collect ingredient/categorie overview
overview = []
for r in data:
    overview.append({
        "Ingredient": r.get("Ingredient"),
        "Categorie": r.get("Categorie"),
        "Type_Rapport": r.get("Type_Rapport"),
        "Verdict": r.get("Verdict"),
    })

categories = list(set(r.get("Categorie") for r in data))
keys = list(data[0].keys()) if data else []

result = {
    "total_rows": len(data),
    "keys": keys,
    "distinct_categories": categories,
    "rows": overview,
}

out = Path(__file__).resolve().parent / "diagnose_result.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"Written to {out}")
