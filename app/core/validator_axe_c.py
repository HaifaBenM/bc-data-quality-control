"""
Validation Axe C — Suggestions de correction par IA (Google Gemini).
Pour chaque anomalie Axe A + B, suggère une correction avec un score de confiance.
Auto-correction si score ≥ seuil défini (défaut : 90%).
"""
import os
import json
import requests
import streamlit as st


# ── Configuration ─────────────────────────────────────────────────────────────
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-1.5-flash:generateContent"
)
AUTO_CORRECT_THRESHOLD = 90  # % de confiance minimum pour auto-correction
MAX_ANOMALIES_PER_BATCH = 15 # Nb max d'anomalies par appel API


def get_gemini_api_key() -> str:
    """Récupère la clé API Gemini depuis les secrets ou variables d'environnement."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        try:
            key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            pass
    return key


def is_gemini_available() -> bool:
    """Vérifie si la clé API Gemini est configurée."""
    return bool(get_gemini_api_key())


def _call_gemini(prompt: str, api_key: str) -> dict | None:
    """Appel direct à l'API Gemini. Retourne le JSON parsé ou None."""
    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature":      0.1,
                    "maxOutputTokens":  2048,
                    "responseMimeType": "application/json",
                },
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return None

        data    = resp.json()
        content = (
            data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
        )
        if not content:
            return None

        # Nettoyer les balises markdown si présentes
        clean = content.strip()
        for tag in ["```json", "```"]:
            clean = clean.replace(tag, "")
        return json.loads(clean.strip())

    except Exception:
        return None


def _build_prompt(anomalies: list, table_label: str) -> str:
    """Construit le prompt Gemini pour un lot d'anomalies."""
    lines = []
    for i, a in enumerate(anomalies, 1):
        lines.append(
            f'{i}. Ligne {a["Ligne"]} · Champ "{a["Champ"]}" · '
            f'Valeur actuelle : "{a["Valeur"]}" · '
            f'Anomalie : {a["Type d\'anomalie"]}'
        )
        if a.get("Message"):
            lines.append(f'   Détail : {a["Message"]}')

    return f"""Tu es un expert Microsoft Dynamics 365 Business Central.
Analyse ces anomalies détectées dans la table "{table_label}" et propose une correction pour chacune.

Anomalies :
{chr(10).join(lines)}

Réponds UNIQUEMENT avec un tableau JSON valide (sans markdown) :
[
  {{
    "id": 1,
    "valeur_suggeree": "valeur corrigée",
    "confiance": 85,
    "explication": "explication courte"
  }}
]

Règles importantes :
- confiance : entier 0-100 (100 = certitude absolue)
- Donne confiance ≥ 90 UNIQUEMENT si tu es certain
- Codes pays ISO 2 lettres : FR, DE, US, GB...
- Codes devise ISO 3 lettres : EUR, USD, GBP...
- Pour les valeurs vides obligatoires : valeur_suggeree = "" et confiance = 0
- Pour les typos évidents : propose la correction avec haute confiance
- Pour les formats de date : utilise DD/MM/YYYY
- Réponds avec exactement {len(anomalies)} objets dans le tableau"""


def enrich_anomalies_with_ai(
    anomalies:   list,
    table_label: str,
    api_key:     str,
) -> list:
    """
    Enrichit une liste d'anomalies avec des suggestions IA (Gemini).
    Traite les anomalies par lots pour limiter les appels API.
    """
    if not anomalies or not api_key:
        return anomalies

    enriched = list(anomalies)  # Copie

    # Traiter seulement les anomalies avec une valeur non vide (utile pour l'IA)
    candidates = [
        (i, a) for i, a in enumerate(enriched)
        if a.get("Valeur", "").strip() and a.get("Ligne", 0) > 0
    ]

    # Traiter par lots
    for batch_start in range(0, len(candidates), MAX_ANOMALIES_PER_BATCH):
        batch = candidates[batch_start : batch_start + MAX_ANOMALIES_PER_BATCH]
        batch_anomalies = [a for _, a in batch]

        prompt   = _build_prompt(batch_anomalies, table_label)
        response = _call_gemini(prompt, api_key)

        if not response or not isinstance(response, list):
            continue

        # Associer les suggestions aux anomalies
        for j, suggestion in enumerate(response):
            if j >= len(batch):
                break
            orig_idx, _ = batch[j]

            suggested = str(suggestion.get("valeur_suggeree", "")).strip()
            confidence = int(suggestion.get("confiance", 0))
            explanation = str(suggestion.get("explication", "")).strip()

            # Mettre à jour l'anomalie avec la suggestion IA
            enriched[orig_idx]["suggestion_ia"]  = suggested
            enriched[orig_idx]["confiance_ia"]   = confidence
            enriched[orig_idx]["explication_ia"] = explanation
            enriched[orig_idx]["auto_corrige"]   = (
                confidence >= AUTO_CORRECT_THRESHOLD and bool(suggested)
            )
            # Mettre à jour la correction suggérée si pas déjà renseignée
            if suggested and not enriched[orig_idx].get("Correction suggérée"):
                enriched[orig_idx]["Correction suggérée"] = (
                    f"🤖 {suggested} ({confidence}%)"
                )

    return enriched


def validate_file_axe_c(
    axe_a_result: dict,
    axe_b_result: dict,
    parse_result:  dict,
    api_key:       str = "",
) -> dict:
    """
    Enrichit les anomalies Axe A + B avec des suggestions IA.

    Retourne :
    {
        available, total_suggestions, auto_corrected,
        high_confidence, low_confidence,
        by_sheet: {sheet_name: [anomalies enrichies]}
    }
    """
    result = {
        "available":       bool(api_key),
        "total_suggestions": 0,
        "auto_corrected":  0,
        "high_confidence": 0,
        "low_confidence":  0,
        "by_sheet":        {},
        "error":           "",
    }

    if not api_key:
        result["error"] = "Clé API Gemini non configurée."
        return result

    if not api_key:
        return result

    metadata    = parse_result.get("metadata", {})
    data_tables = parse_result.get("data_tables", [])

    for sheet_name in data_tables:
        meta        = metadata.get(sheet_name, {})
        table_label = meta.get("label", sheet_name)

        # Récupérer les anomalies des deux axes pour cet onglet
        a_anomalies = axe_a_result.get("by_sheet", {}).get(sheet_name, [])
        b_anomalies = axe_b_result.get("by_sheet", {}).get(sheet_name, [])
        all_anomalies = a_anomalies + b_anomalies

        if not all_anomalies:
            result["by_sheet"][sheet_name] = []
            continue

        # Enrichir avec l'IA
        enriched = enrich_anomalies_with_ai(
            anomalies=all_anomalies,
            table_label=table_label,
            api_key=api_key,
        )

        result["by_sheet"][sheet_name] = enriched

        # Comptages
        for a in enriched:
            if a.get("suggestion_ia"):
                result["total_suggestions"] += 1
                conf = a.get("confiance_ia", 0)
                if a.get("auto_corrige"):
                    result["auto_corrected"] += 1
                if conf >= AUTO_CORRECT_THRESHOLD:
                    result["high_confidence"] += 1
                else:
                    result["low_confidence"] += 1

    return result


def _build_coherence_prompt(candidates: list, table_label: str) -> str:
    lines = []
    for i, c in enumerate(candidates, 1):
        lines.append(
            f'{i}. Champ "{c["champ_a"]}"="{c["valeur_a"]}" (fréquent, {c["total_a"]} occurrences) '
            f'associé à "{c["champ_b"]}"="{c["valeur_b"]}" seulement {c["occurrences"]} fois '
            f'(habituellement "{c["valeur_b_habituelle"]}")'
        )
    return f"""Tu es un expert Microsoft Dynamics 365 Business Central.
Voici des combinaisons de champs statistiquement rares dans un fichier "{table_label}" à importer.
Pour chacune, indique si c'est probablement une VRAIE incohérence de saisie ou un cas légitime.

Combinaisons :
{chr(10).join(lines)}

Réponds UNIQUEMENT avec un tableau JSON valide (sans markdown) :
[{{"id": 1, "incoherence_probable": true, "confiance": 70, "justification": "...", "valeur_suggeree": ""}}]

Règles :
- incoherence_probable = false si le cas est plausible (ex. facturation export)
- valeur_suggeree : uniquement si tu es raisonnablement confiant, sinon chaîne vide
- Réponds avec exactement {len(candidates)} objets"""


def enrich_coherence_with_ai(candidates: list, table_label: str, api_key: str) -> list:
    if not candidates or not api_key:
        return []
    enriched = []
    for batch_start in range(0, len(candidates), MAX_ANOMALIES_PER_BATCH):
        batch = candidates[batch_start: batch_start + MAX_ANOMALIES_PER_BATCH]
        response = _call_gemini(_build_coherence_prompt(batch, table_label), api_key)
        if not response or not isinstance(response, list):
            continue
        for j, res in enumerate(response):
            if j >= len(batch):
                break
            c = dict(batch[j])
            c["incoherence_probable"] = bool(res.get("incoherence_probable", False))
            c["confiance_ia"] = int(res.get("confiance", 0))
            c["justification_ia"] = str(res.get("justification", "")).strip()
            c["valeur_suggeree_ia"] = str(res.get("valeur_suggeree", "")).strip()
            enriched.append(c)
    return enriched


def validate_coherence_axe_c(parse_result: dict, execution_plan, api_key: str,
                              max_candidates_per_sheet: int = 15) -> dict:
    from app.core.coherence_detector import get_eligible_fields, detect_rare_pairs, map_candidates_to_rows

    result = {"available": bool(api_key), "by_sheet": {}, "total_flagged": 0}
    if not api_key:
        return result

    for sheet_name in parse_result.get("data_tables", []):
        df = parse_result.get("sheets", {}).get(sheet_name)
        meta = parse_result.get("metadata", {}).get(sheet_name, {})
        table_id = meta.get("table_id", "")
        if df is None or df.empty or not table_id:
            result["by_sheet"][sheet_name] = []
            continue
        try:
            eligible = [f for f in get_eligible_fields(execution_plan, int(table_id)) if f in df.columns]
        except (ValueError, TypeError):
            eligible = []
        if len(eligible) < 2:
            result["by_sheet"][sheet_name] = []
            continue

        # RÉVISÉ (26/08/2026, jour J) — demande Rami, diagnostic confirmé
        # dans la conversation de calibration Axe C (25-26/08) : le seuil
        # par défaut (max_pair_ratio=0.08) est calibré pour des fichiers
        # volumineux (centaines de lignes) — sur un petit fichier de
        # démo (~18 lignes), un cas clairement suspect (2 occurrences sur
        # 18, ratio 0.083) rate le seuil DE JUSTESSE, mécaniquement, sans
        # rapport avec la pertinence réelle du cas. Relevé à 0.12 pour
        # rester fiable aussi bien sur un petit fichier de démo que sur un
        # gros fichier réel (candidats restent peu nombreux et pertinents
        # aux deux échelles, testé sur ce fichier précis : 6 candidats à
        # 0.12, tous plausibles).
        candidates = detect_rare_pairs(df, eligible, max_pair_ratio=0.12)[:max_candidates_per_sheet]
        if not candidates:
            result["by_sheet"][sheet_name] = []
            continue

        enriched = enrich_coherence_with_ai(candidates, meta.get("label", sheet_name), api_key)
        flagged = [c for c in enriched if c.get("incoherence_probable")]
        key_field = execution_plan.get_key_field(int(table_id))
        anomalies = map_candidates_to_rows(df, flagged, sheet_name, key_field)
        result["by_sheet"][sheet_name] = anomalies
        result["total_flagged"] += len(anomalies)

    return result