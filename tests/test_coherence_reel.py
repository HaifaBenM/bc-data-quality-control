import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import io

print("1. Imports...")
from app.core.file_parser import parse_uploaded_file
from app.core.execution_planner import get_execution_plan
from app.core.coherence_detector import get_eligible_fields, detect_rare_pairs
print("2. Imports OK")

class FakeUpload(io.BytesIO):
    def __init__(self, path):
        with open(path, "rb") as f:
            super().__init__(f.read())
        self.name = path

CHEMIN_FICHIER = r"C:\Users\hbenmaatoug\Desktop\Data Quality Control Tool\bc-data-quality-control\MDD-STOCK-DEMO.xlsx"
PROFILE_CODE = "AQUACHIARA001"
COMPANY_ID = "d37553fd-0490-f111-8072-6045bd19e3ae"
PACKAGE_CODE = "MDD-STOCK-V2"

print("3. Parsing du fichier...")
pr = parse_uploaded_file(FakeUpload(CHEMIN_FICHIER))
print("4. Fichier parsé.")
print("   data_tables :", pr.get("data_tables"))
print("   ref_tables  :", pr.get("ref_tables"))

print("5. Appel get_execution_plan...")
exec_plan = get_execution_plan(profile_code=PROFILE_CODE, company_id=COMPANY_ID, package_code=PACKAGE_CODE)
print("6. Plan récupéré")

print("\n--- DIAGNOSTIC exec_plan ---")
print("Tables connues par exec_plan :", list(exec_plan.tables.keys()))
print("Tables avec fields_meta      :", list(exec_plan.fields_meta.keys()))
print("Nom table 27 selon exec_plan :", exec_plan.get_table_name(27))

for sheet in pr["data_tables"] + pr["ref_tables"]:
    df = pr["sheets"][sheet]
    table_id = int(pr["metadata"][sheet]["table_id"])
    eligible = [f for f in get_eligible_fields(exec_plan, table_id) if f in df.columns]
    print(f"\n=== {sheet} (table {table_id}) — champs éligibles : {eligible}")
    candidates = detect_rare_pairs(df, eligible)
    if not candidates:
        print("  -> 0 candidat")
    for c in candidates[:10]:
        print(f"  {c['champ_a']}={c['valeur_a']} ({c['total_a']}x) -> {c['champ_b']}={c['valeur_b']} ({c['occurrences']}x, attendu {c['valeur_b_habituelle']})")

print("\n7. Terminé")