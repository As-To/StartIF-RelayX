# Synthese des donnees de scraping

## 1. ECHA — European Chemicals Agency

**Methode :** Scraping web du site echa.europa.eu via `requests` + `BeautifulSoup` (variante basique), avec rotation de User-Agent et retry (variante avancee), ou via Selenium avec ChromeDriver (variante navigateur reel). Le site possede une forte protection anti-bot : taux de succes ~30% (basique), ~60% (avance), ~90% (Selenium). Aucune API officielle n'est disponible. Accessibilite difficile.

**Format de stockage :** JSON (ou TXT structure)

**Quantite estimee :** ~100 000 substances enregistrees sur ECHA ; le scraper les recupere une par une a la demande. Pas de donnees deja stockees dans le depot.

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `url` | `string` | URL de la fiche ECHA | `https://echa.europa.eu/substance-information/-/substanceinfo/100.000.024` |
| `name` | `string` | Nom de la substance | `Formaldehyde` |
| `cas` | `string` | Numero CAS (identifiant chimique) | `50-00-0` |
| `ec` | `string` | Numero EC europeen | `200-001-8` |
| `molecular_formula` | `string` | Formule moleculaire | `CH2O` |
| `molecular_weight` | `string` | Masse moleculaire | `30.03 g/mol` |
| `classification` | `array[string]` | Classifications CLP (dangers) | `["Carc. 1A", "Muta. 2", "Acute Tox. 3"]` |
| `uses` | `array[string]` | Usages identifies | `["adhesives", "coatings"]` |
| `tonnage` | `string` | Bande de tonnage REACH | `>1 000 000 tonnes/an` |
| `raw_text` | `string` | Texte brut de la page pour reference | *(texte complet)* |

---

## 2. PubChem — NIH (API REST)

**Methode :** Appels a l'API REST publique PUG-REST de PubChem (`pubchem.ncbi.nlm.nih.gov/rest/pug/`). Aucune cle API requise, aucun blocage, 100% fiable. Les donnees sont extraites via des requetes HTTP simples (module `requests`). Accessibilite tres facile.

**Format de stockage :** CSV (`pubchem_results.csv`)

**Quantite estimee :** ~116 millions de composes dans PubChem ; le fichier de demo contient 3 substances. Recuperation par lot possible sans limitation stricte.

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `Name` | `string` | Nom courant de la substance | `Aspirin` |
| `CID` | `int` | Identifiant PubChem (Compound ID) | `2244` |
| `CAS` | `string` | Numero CAS | `50-78-2` |
| `EC` | `string` | Numero EC | *(vide si absent)* |
| `Molecular formula` | `string` | Formule moleculaire | `C9H8O4` |
| `Molecular weight` | `float` | Masse moleculaire (g/mol) | `180.16` |
| `IUPAC name` | `string` | Nom IUPAC officiel | `2-acetyloxybenzoic acid` |
| `InChI` | `string` | Identifiant InChI | `InChI=1S/C9H8O4/c1-6(10)13-8-5-3-...` |
| `InChIKey` | `string` | Cle InChI (hash) | `BSYNRYMUTXBXSQ-UHFFFAOYSA-N` |
| `SMILES` | `string` | Notation SMILES de la structure | *(notation lineaire)* |
| `XLogP` | `float` | Coefficient de partage octanol/eau | `1.2` |
| `TPSA` | `float` | Surface polaire topologique (A^2) | `63.6` |
| `Complexity` | `float` | Indice de complexite moleculaire | `212` |
| `H-Bond Donors` | `int` | Nombre de donneurs de liaison H | `1` |
| `H-Bond Acceptors` | `int` | Nombre d'accepteurs de liaison H | `4` |
| `Rotatable Bonds` | `int` | Nombre de liaisons rotatives | `3` |
| `Heavy Atoms` | `int` | Nombre d'atomes lourds | `13` |
| `Synonyms` | `array[string]` | Synonymes et noms commerciaux | `["ACETYLSALICYLIC ACID", "Acylpyrin"]` |
| `GHS_Hazards` | `string` | Phrases de danger GHS (H-codes) | `H302: Harmful if swallowed` |
| `GHS_Precautions` | `string` | Conseils de prudence (P-codes) | `P264, P270, P301+P317...` |
| `Signal_Word` | `string` | Mention d'avertissement | `Warning` |
| `Pictograms` | `string` | Pictogrammes de danger | *(references pictogrammes)* |
| `Hazard_Classes` | `string` | Classes de danger | *(texte)* |
| `Uses` | `string` | Usages et indications therapeutiques | `Anti-Inflammatory Agents, Non-Steroidal...` |
| `Manufacturing` | `string` | Procedes de fabrication | `Crystallization from acetone...` |
| `Exposure_Routes` | `string` | Voies d'exposition et pharmacocinetique | `Oral Use; Intravenous Use...` |
| `Symptoms` | `string` | Symptomes de toxicite | `Irritating to the eyes, skin...` |
| `First_Aid` | `string` | Premiers soins | `Fresh air, rest...` |
| `Fire_Hazard` | `string` | Risque d'incendie | `This chemical is combustible` |
| `Stability` | `string` | Stabilite chimique | `STABLE IN DRY AIR` |

---

## 3. CosIng — Base europeenne des ingredients cosmetiques

**Methode :** Scraping web via Selenium + ChromeDriver de la base CosIng de la Commission Europeenne (`ec.europa.eu/growth/tools-databases/cosing/`). Le navigateur automatise simule une recherche par nom d'ingredient, puis extrait les informations de la fiche et les liens vers les avis SCCS. Necessite Selenium. Vitesse ~5-8 secondes par substance. Accessibilite moyenne (necessite un navigateur headless).

**Format de stockage :** CSV (`sccs_results.csv`)

**Quantite estimee :** ~30 000 ingredients dans la base CosIng ; le fichier de demo contient 5 substances.

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `Substance_Recherchee` | `string` | Nom recherche en entree | `retinol` |
| `INCI_Name` | `string` | Nom INCI officiel international | `RETINOL` |
| `CAS` | `string` | Numero CAS | `68-26-8` |
| `Function` | `string` | Fonction cosmetique (texte brut de la fiche) | `SKIN CONDITIONING` |
| `Restriction` | `string` | Restrictions d'usage reglementaires | *(si applicable)* |
| `SCCS_Opinion` | `string` | URL vers l'avis SCCS (PDF) | `https://ec.europa.eu/.../sccs_o_199.pdf` |
| `Has_SCCS_URL` | `boolean` | Indique si un lien SCCS a ete trouve | `True` |
| `Source_URL` | `string` | Lien vers la fiche CosIng complete | `https://ec.europa.eu/growth/tools-databases/cosing/details/37479` |
| `Statut` | `string` | Statut du traitement | `TROUVE` / `NON_TROUVE` / `ERREUR` |

---

## 4. EUR-Lex — Reglement (CE) 1223/2009 (Annexes II et III)

**Methode :** Scraping en 3 etapes : (1) requete SPARQL sur le endpoint CELLAR de l'Office des publications de l'UE pour obtenir les metadonnees et URI des versions consolidees, (2) telechargement du HTML de la version consolidee la plus recente via l'API REST CELLAR, (3) parsing des tableaux HTML des Annexes II et III avec BeautifulSoup. Aucune cle API requise, acces ouvert officiel. Accessibilite facile.

**Format de stockage :** JSON (`eurlex_annexes.json`)

**Quantite estimee :** 1 546 substances interdites (Annexe II) + 501 substances restreintes (Annexe III) = **2 047 entrees** dans le fichier actuel.

### Annexe II (substances interdites)

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `annex` | `string` | Numero de l'annexe | `II` |
| `status` | `string` | Statut reglementaire | `prohibited` |
| `entry_number` | `string` | Numero d'entree dans l'annexe | `1` |
| `substance_name` | `string` | Nom de la substance | `N-(5-Chlorobenzoxazol-2-yl)acetamide` |
| `cas_number` | `string` | Numero CAS principal | *(souvent vide)* |
| `cas_all` | `string` | Tous les numeros CAS | *(si multiples)* |
| `ec_number` | `string` | Numero EC principal | *(souvent vide)* |
| `ec_all` | `string` | Tous les numeros EC | *(si multiples)* |
| `notes` | `string` | Notes et remarques | *(texte libre)* |

### Annexe III (substances restreintes)

Inclut tous les attributs de l'Annexe II, plus :

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `product_type` | `string` | Type de produit concerne | `Hair waving or straightening products` |
| `max_concentration` | `string` | Concentration maximale autorisee (texte) | *(texte brut)* |
| `max_concentration_pct` | `float\|null` | Concentration maximale en % | `null` |
| `conditions` | `string` | Conditions d'utilisation | `(a) Hair waving or straightening products` |
| `labelling` | `string` | Exigences d'etiquetage | `Avoid contact with eyes...` |
| `_continuation` | `boolean` | Indique une ligne de continuation | `false` |

---

## 5. EFSA — European Food Safety Authority (OpenFoodTox + Zenodo)

**Methode :** Deux sources accessibles via HTTP sans cle API : (1) OpenFoodTox, un fichier XLSX heberge sur Zenodo (record 8120114) contenant des donnees toxicologiques structurees (ADI, TDI, NOAEL, genotoxicite) ; (2) l'API Zenodo Records pour recuperer les publications de la communaute "EFSA Knowledge Junction" (rapports, datasets, avis scientifiques). L'API EFSA Deposits n'est pas encore disponible (prevue 2026). Accessibilite facile.

**Format de stockage :** JSON (`efsa_cicadomorpha.json`)

**Quantite estimee :** OpenFoodTox contient ~5 000 substances evaluees ; Zenodo/EFSA-KJ contient ~10 000 records. Le fichier de demo contient 0 entree OpenFoodTox et 5 entrees Zenodo pour "Cicadomorpha".

### Donnees OpenFoodTox

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `ingredient` | `string` | Nom de la substance recherchee | `caffeine` |
| `cas` | `string` | Numero CAS | `58-08-2` |
| *(Colonnes du XLSX OpenFoodTox : ADI, TDI, ARfD, NOAEL, genotoxicite, avis EFSA, etc.)* | varies | Donnees toxicologiques de reference | *(valeurs numeriques et textuelles)* |

### Donnees Zenodo (EFSA Knowledge Junction)

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `source` | `string` | Source du record | `Zenodo` |
| `record_id` | `string` | Identifiant Zenodo | `18695599` |
| `ingredient` | `string` | Ingredient recherche | `Cicadomorpha` |
| `title` | `string` | Titre de la publication | `Database for the surveillance of non-EU Cicadomorpha...` |
| `abstract` | `string` | Resume (HTML) | *(texte HTML)* |
| `date` | `string` | Date de publication | `2026-03-11` |
| `type` | `string` | Type de record | `Dataset` / `Report` |
| `doi` | `string` | Identifiant DOI | `10.5281/zenodo.18695599` |
| `url` | `string` | URL du record | `https://doi.org/10.5281/zenodo.18695599` |
| `keywords` | `array[string]` | Mots-cles | `["surveillance", "host plants"]` |
| `authors` | `array[string]` | Auteurs | `["Sanna, Francesco", ...]` |
| `files` | `array[object]` | Fichiers attaches (nom + taille) | `[{"name": "...", "size_kb": 382.9}]` |
| `conclusion` | `string` | Conclusion (si extractible) | `unknown` |
| `relevance` | `int` | Score de pertinence calcule | `10` |

---

## 6. PubMed — Articles scientifiques (API E-utilities)

**Methode :** Utilisation de l'API NCBI E-utilities (eutils.ncbi.nlm.nih.gov) en 2 etapes : (1) `esearch` pour recuperer les PMIDs des articles correspondant a une requete combinant le nom de l'ingredient et des termes cosmetiques, (2) `efetch` pour telecharger le contenu XML des articles, puis parsing et scoring de pertinence. Fonctionne sans cle API (3 req/s) ou avec cle (10 req/s). Accessibilite tres facile.

**Format de stockage :** JSON (`pubmed_niacinamide.json`)

**Quantite estimee :** PubMed contient ~36 millions d'articles ; le scraper retourne jusqu'a 25 articles par requete (configurable). Le fichier de demo contient 25 articles pour "niacinamide".

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `pmid` | `string` | Identifiant PubMed | `16596767` |
| `doi` | `string` | Identifiant DOI | `10.1080/10915810500434183` |
| `title` | `string` | Titre de l'article | `Final report of the safety assessment of niacinamide...` |
| `abstract` | `string` | Resume complet | *(texte long)* |
| `authors` | `array[string]` | Liste des auteurs | `["Gonzalez-Molina V", "Marti-Pineda A"]` |
| `journal` | `string` | Nom du journal | `International journal of toxicology` |
| `date` | `string` | Date de publication | `2005` |
| `mesh` | `array[string]` | Termes MeSH (descripteurs medicaux) | `["Cosmetics", "Niacinamide", "Humans"]` |
| `keywords` | `array[string]` | Mots-cles de l'article | `["melasma", "depigmentation"]` |
| `url` | `string` | URL PubMed | `https://pubmed.ncbi.nlm.nih.gov/16596767/` |
| `ingredient_query` | `string` | Ingredient recherche | `niacinamide` |
| `relevance_score` | `int` | Score de pertinence calcule (securite cosmetique) | `14` |

---

## 7. SCCS — Avis du comite scientifique (scraping health.ec.europa.eu)

**Methode :** Scraping du site health.ec.europa.eu via `requests` + `BeautifulSoup` pour lister les publications SCCS, puis telechargement et extraction du contenu des PDF d'avis via `pdfplumber`. Le scraper parcourt les pages de resultats (jusqu'a 637 pages), filtre les articles SCCS, puis extrait les informations cles (ingredient, verdict, concentration max) directement depuis les PDF. Delai de 1.2s entre les requetes. Accessibilite moyenne (volume important, PDF parsing).

**Format de stockage :** JSON (`sccs_results.json`)

**Quantite estimee :** ~300 avis SCCS publies depuis 2004 ; le fichier de demo contient 4 avis recents.

| Attribut | Type | Description | Exemple |
|---|---|---|---|
| `Ingredient` | `string` | Nom de l'ingredient evalue | `Basic Brown 16` |
| `CAS_EC` | `string` | Numeros CAS et EC combines | `26381-41-9 / 247-640-9` |
| `SCCS_Number` | `string` | Reference de l'avis SCCS | `SCCS/1684/25` |
| `Date_Avis` | `string` | Date de l'avis | `2026-02-02` |
| `Verdict` | `string\|null` | Verdict de securite | `Not Safe` / `Conditionally Safe` / `null` |
| `Concentration_Max` | `string` | Concentration maximale evaluee | `2 % in non-oxidative hair dye formulations` |
| `Lien_Source` | `string` | URL de la page source | `https://health.ec.europa.eu/latest-updates/sccs-...` |
| `Type_Rapport` | `string` | Type de rapport | `Scientific Advice` / `Final Opinion` |
| `Categorie` | `string` | Categorie de l'ingredient | `Colorant` / `Preservative` |
| `_title` | `string` | Titre complet de l'avis | `SCCS - Scientific advice on hair dye 'Basic Brown 16'...` |
| `_pdf_url` | `string` | URL directe du PDF de l'avis | `https://health.ec.europa.eu/.../sccs_o_305.pdf` |
| `_conclusion` | `string` | Conclusion extraite du PDF | `the SCCS considers that a concern...` |
| `_error` | `string\|null` | Erreur eventuelle lors de l'extraction | `null` |

---

## Tableau recapitulatif

| Source | Methode | Accessibilite | Format | Donnees demo | Potentiel total |
|---|---|---|---|---|---|
| ECHA | Web scraping (requests/Selenium) | Difficile (anti-bot) | JSON | 0 | ~100 000 substances |
| PubChem | API REST publique | Tres facile | CSV | 3 substances | ~116M composes |
| CosIng | Selenium (navigateur headless) | Moyenne | CSV | 5 substances | ~30 000 ingredients |
| EUR-Lex | SPARQL + REST CELLAR + parsing HTML | Facile | JSON | 2 047 entrees | ~2 050 (Annexes II+III) |
| EFSA | HTTP (OpenFoodTox XLSX + Zenodo API) | Facile | JSON | 5 records Zenodo | ~5 000 (OFT) + ~10 000 (Zenodo) |
| PubMed | API E-utilities (esearch + efetch) | Tres facile | JSON | 25 articles | ~36M articles |
| SCCS | Web scraping + PDF parsing | Moyenne | JSON | 4 avis | ~300 avis |
