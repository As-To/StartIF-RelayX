import re
import json
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

URL = "https://eur-lex.europa.eu/legal-content/FR/TXT/HTML/?uri=CELEX:32009R1223"


def clean(text):
    if not text:
        return ""
    # Remplacer les espaces insécables par des espaces normaux
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()
def fill_forward(matrix):
    """
    Remplit les cellules vides avec la dernière valeur connue (colonne par colonne)
    """
    if not matrix:
        return matrix

    last = [""] * len(matrix[0])

    for row in matrix:
        for i in range(len(row)):
            if row[i]:
                last[i] = row[i]
            else:
                row[i] = last[i]

    return matrix

def get_soup():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()
    return BeautifulSoup(html, "lxml")

def parse_table(table):
    rows = table.find_all("tr")
    data = []
    for tr in rows:
        cells = [clean(td.get_text()) for td in tr.find_all("td")]
        if not cells:
            continue
        if all(len(cell) <= 1 for cell in cells):
            continue
        if any(kw in " ".join(cells) for kw in [
            "Numéro CAS", "Nom chimique", "Dénomination", "Numéro d'ordre"
        ]):
            continue
        data.append(cells)
    return data

def parse_annex_II(soup):
    container = soup.find("div", id="anx_II")
    if not container:
        print("⚠️  div#anx_II introuvable")
        return []
    table = container.find("table")
    if not table:
        print("⚠️  Pas de table dans div#anx_II")
        return []
    return [
        {
            "entry_number": row[0] if len(row) > 0 else "",
            "substance":    row[1] if len(row) > 1 else "",
            "cas":          row[2] if len(row) > 2 else "",
            "ec":           row[3] if len(row) > 3 else "",
        }
        for row in parse_table(table)
    ]
def parse_annex_III(soup):
    container = soup.find("div", id="anx_III")
    if not container:
        print("⚠️  div#anx_III introuvable")
        return []
    
    table = container.find("table")
    if not table:
        return []

    # --- CORRECTION ICI ---
    # Parcourir uniquement les enfants directs pour ignorer les sous-tableaux
    main_rows = []
    for child in table.children:
        if child.name == "tbody":
            main_rows.extend(child.find_all("tr", recursive=False))
        elif child.name == "tr":
            main_rows.append(child)

    matrix = []
    rowspan_map = {}

    for tr in main_rows:
        row_cells = []
        # On s'assure de ne prendre que les cellules directes de la ligne
        tds = tr.find_all(["td", "th"], recursive=False)
        td_iter = iter(tds)

        col_idx = 0
        td = next(td_iter, None)

        while col_idx < 20:  # max colonnes raisonnables
            if col_idx in rowspan_map:
                val, remaining = rowspan_map[col_idx]
                row_cells.append(val)
                if remaining - 1 > 0:
                    rowspan_map[col_idx] = (val, remaining - 1)
                else:
                    del rowspan_map[col_idx]
                col_idx += 1
            elif td is not None:
                # Ajout de separator=" " pour ne pas coller les textes des sous-éléments
                val = clean(td.get_text(separator=" "))
                rowspan = int(td.get("rowspan", 1))
                colspan = int(td.get("colspan", 1))

                for c in range(colspan):
                    row_cells.append(val)
                    if rowspan > 1:
                        rowspan_map[col_idx + c] = (val, rowspan - 1)

                col_idx += colspan
                td = next(td_iter, None)
            else:
                break

        if row_cells:
            matrix.append(row_cells)
        
    # 1. construire matrix
    matrix = normalize_matrix(matrix)
    matrix = fill_forward(matrix)

    # Filtrer headers et lignes parasites
    results = []
    for row in matrix:
        joined = " ".join(row)
        if not row:
            continue
        if all(len(c) <= 1 for c in row):
            continue
        if any(kw in joined for kw in ["Numéro d'ordre", "Numéro CAS", "Identification"]):
            continue

        results.append({
            "entry_number":      row[0] if len(row) > 0 else "",
            "substance":         row[1] if len(row) > 1 else "",
            "inci_name":         row[2] if len(row) > 2 else "",
            "cas":               row[3] if len(row) > 3 else "",
            "ec":                row[4] if len(row) > 4 else "",
            "product_type":      row[5] if len(row) > 5 else "",
            "max_concentration": row[6] if len(row) > 6 else "",
            "conditions":        row[7] if len(row) > 7 else "",
            "labelling":         row[8] if len(row) > 8 else "",
        })

    return results

def normalize_matrix(matrix):
    """
    Force toutes les lignes à avoir la même longueur
    """
    if not matrix:
        return matrix

    max_len = max(len(row) for row in matrix)

    for row in matrix:
        while len(row) < max_len:
            row.append("")

    return matrix

def main():
    print("Chargement via Chromium...")
    soup = get_soup()
    print(f"HTML : {len(str(soup))} caractères\n")

    annex_II = parse_annex_II(soup)
    annex_III = parse_annex_III(soup)

    print(f"Annex II  : {len(annex_II)} entrées")
    print(f"Annex III : {len(annex_III)} entrées")
    # Export JSON
    output = {
        "source": URL,
        "annex_II": annex_II,
        "annex_III": annex_III,
    }

    with open("eurlex_32009R1223.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n✅ Exporté dans eurlex_32009R1223.json")
    print("\nExemple Annex II :", annex_II[:2])
    print("\nExemple Annex III :", annex_III[:2])
    print("Colonnes dispo :", len(annex_III[0]) if annex_III else 0)


if __name__ == "__main__":
    main()