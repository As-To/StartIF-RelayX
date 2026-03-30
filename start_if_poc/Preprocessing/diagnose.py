"""
Diagnostic script to inspect the raw sccs_results.json data
and understand the issues with ingredient names and categories.
"""
import json
from pathlib import Path

base = Path(__file__).resolve().parent.parent / "scrapping"
data = json.load(open(base / "sccs_results.json", encoding="utf-8"))

print(f"Total rows: {len(data)}")
print()
print("=== All Ingredient / Categorie / Type_Rapport ===")
for r in data:
    ingr = r.get("Ingredient", "")
    cat  = r.get("Categorie", "")
    typ  = r.get("Type_Rapport", "")
    print(f"  INGR={ingr!r:60s}  CAT={cat!r:20s}  TYPE={typ!r}")

print()
print("=== All distinct Categorie values ===")
cats = set(r.get("Categorie","") for r in data)
for c in sorted(cats, key=lambda x: x or ""):
    print(f"  {c!r}")

print()
print("=== Sample keys for first row ===")
if data:
    print(list(data[0].keys()))
