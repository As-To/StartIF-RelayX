"""
Test rapide pour vérifier la récupération complète des données PubChem
"""

from pubchem_alternative import PubChemAPI

print("=" * 70)
print("TEST RAPIDE - RÉCUPÉRATION COMPLÈTE PUBCHEM")
print("=" * 70)

api = PubChemAPI()

# Test avec l'aspirine (substance bien documentée)
print("\n🧪 Test avec: ASPIRIN")
print("-" * 70)

info = api.get_full_info("aspirin", include_extra=True)

if 'error' not in info:
    print("\n✅ RÉCUPÉRATION RÉUSSIE\n")
    
    print("📋 IDENTIFIANTS:")
    print(f"  Name: {info.get('Name')}")
    print(f"  CAS: {info.get('CAS')}")
    print(f"  CID: {info.get('CID')}")
    
    print("\n⚗️  PROPRIÉTÉS CHIMIQUES:")
    print(f"  Formule: {info.get('Molecular formula')}")
    print(f"  Poids: {info.get('Molecular weight')}")
    
    print("\n⚠️  DONNÉES GHS:")
    print(f"  Signal Word: {info.get('Signal_Word', 'N/A')}")
    print(f"  Pictograms: {info.get('Pictograms', 'N/A')}")
    
    hazards = info.get('GHS_Hazards', '')
    print(f"  Hazards: {hazards if hazards else 'N/A'}")
    
    print("\n🏭 USAGE:")
    uses = info.get('Uses', '')
    print(f"  {uses if uses else 'N/A'}")
    
    print("\n🚨 SÉCURITÉ:")
    exposure = info.get('Exposure_Routes', '')
    print(f"  Exposure: {exposure[:150] if exposure else 'N/A'}...")
    
    first_aid = info.get('First_Aid', '')
    print(f"  First Aid: {first_aid[:150] if first_aid else 'N/A'}...")
    
    print("\n" + "=" * 70)
    print("📊 RÉSUMÉ:")
    filled = sum(1 for k, v in info.items() if v and str(v).strip())
    total = len(info)
    print(f"  Champs remplis: {filled}/{total} ({filled/total*100:.0f}%)")
    print("=" * 70)
else:
    print("\n❌ ERREUR:", info.get('error'))
