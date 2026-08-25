"""
Détection statistique de combinaisons de champs rares (incohérences
potentielles), en amont de tout appel IA — pur pandas, gratuit, déterministe.
"""
from itertools import combinations
import pandas as pd


def get_eligible_fields(execution_plan, table_id: int) -> list[str]:
    """Champs catégoriels courts, candidats à une vérification croisée."""
    field_defs = execution_plan.get_field_defs_for_table(table_id)
    eligible = []
    for name, meta in field_defs.items():
        if meta.option_values:
            eligible.append(name)
        elif meta.py_type == "Text" and 0 < meta.max_length <= 20:
            eligible.append(name)
    return eligible


def detect_rare_pairs(df: pd.DataFrame, eligible_fields: list[str],
                       min_field_support: int = 8,
                       max_pair_ratio: float = 0.08,
                       max_cardinality_ratio: float = 0.5) -> list[dict]:
    """Combinaisons de valeurs rares entre deux champs individuellement fréquents."""
    usable = [
        f for f in eligible_fields
        if f in df.columns and df[f].nunique(dropna=True) < max_cardinality_ratio * len(df)
    ]

    candidates = []
    for field_a, field_b in combinations(usable, 2):
        sub = df[[field_a, field_b]].dropna()
        if sub.empty:
            continue
        counts_a = sub[field_a].value_counts()
        counts_pair = sub.groupby([field_a, field_b]).size()

        for (val_a, val_b), pair_count in counts_pair.items():
            total_a = counts_a[val_a]
            if total_a < min_field_support:
                continue
            ratio = pair_count / total_a
            if ratio > max_pair_ratio:
                continue
            dominant_b = sub[sub[field_a] == val_a][field_b].mode().iloc[0]
            if dominant_b == val_b:
                continue  # la "valeur rare" est en fait la valeur majoritaire
            candidates.append({
                "champ_a": field_a, "valeur_a": val_a,
                "champ_b": field_b, "valeur_b": val_b,
                "occurrences": int(pair_count), "total_a": int(total_a),
                "ratio": ratio, "valeur_b_habituelle": dominant_b,
            })

    candidates.sort(key=lambda c: c["ratio"])
    return candidates


def map_candidates_to_rows(df: pd.DataFrame, flagged: list[dict],
                            sheet_name: str, key_field: str = "") -> list[dict]:
    """Transforme les combinaisons confirmées par l'IA en anomalies au format standard."""
    anomalies = []
    for c in flagged:
        mask = (df[c["champ_a"]] == c["valeur_a"]) & (df[c["champ_b"]] == c["valeur_b"])
        for row_idx in df[mask].index:
            id_metier = str(df.loc[row_idx, key_field]) if key_field and key_field in df.columns else ""
            suggestion = c.get("valeur_suggeree_ia", "")
            anomalies.append({
                "Ligne": int(row_idx) + 4, "Onglet": sheet_name,
                "Identifiant métier": id_metier,
                "Champ": c["champ_b"], "Valeur": c["valeur_b"],
                "Type d'anomalie": "Incohérence inter-champs (IA)",
                "Sévérité": "Info",
                "Message": (
                    f"'{c['valeur_a']}' ({c['champ_a']}) apparaît {c['total_a']} fois, "
                    f"mais avec {c['champ_b']}='{c['valeur_b']}' seulement {c['occurrences']} fois "
                    f"(habituellement '{c['valeur_b_habituelle']}'). {c.get('justification_ia', '')}"
                ),
                "Correction suggérée": f"🧠 {suggestion} ({c.get('confiance_ia', 0)}%)" if suggestion else "",
                "Classification": "SUGGESTION_IA", "Axe": "C",
            })
    return anomalies