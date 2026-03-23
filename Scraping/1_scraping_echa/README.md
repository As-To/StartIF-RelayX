# 🔬 Scrapers ECHA

Ce dossier contient les différents scrapers pour récupérer les données ECHA.

## Fichiers

### scraper_basic.py
**Scraper basique avec requests**
- ✅ Simple et léger
- ❌ Souvent bloqué par ECHA (erreur 403)
- 📊 Utilise requests + BeautifulSoup

**Utilisation:**
```python
from echa.scraper_basic import ECHAScraper

scraper = ECHAScraper()
info = scraper.get_substance_info("formaldehyde")
```

### scraper_advanced.py
**Scraper avancé avec techniques anti-blocage**
- ✅ Rotation de User-Agents
- ✅ Délais aléatoires
- ✅ Retry automatique
- ✅ Support de proxies
- ⚡ Meilleur taux de succès que le basique

**Utilisation:**
```python
from echa.scraper_advanced import ECHAScraperAdvanced

scraper = ECHAScraperAdvanced()
info = scraper.get_substance_info_safe("benzene")
```

### scraper_selenium.py
**Scraper avec navigateur automatisé**
- ✅ Simule un vrai navigateur
- ✅ Taux de succès maximum
- ❌ Plus lent
- ⚙️ Nécessite ChromeDriver

**Utilisation:**
```python
from echa.scraper_selenium import ECHAScraperSelenium

scraper = ECHAScraperSelenium(headless=True)
info = scraper.get_substance_info("toluene")
scraper.close()
```

## Quel scraper choisir ?

1. **Tests rapides** → scraper_basic.py
2. **Production** → scraper_advanced.py ou scraper_selenium.py
3. **Maximum de fiabilité** → scraper_selenium.py

## Import depuis le package

```python
# Méthode recommandée
from echa import ECHAScraper, ECHAScraperAdvanced, ECHAScraperSelenium

# Ou import direct
from echa.scraper_basic import ECHAScraper
```
