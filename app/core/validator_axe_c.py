"""
Validation Axe C — Suggestions de correction par IA.
Pour chaque anomalie Axe A + B, suggère une correction avec un score de confiance.
Auto-correction si score ≥ seuil défini (défaut : 90%).
"""
import os
import json
import requests
import streamlit as st


# ── Configuration ─────────────────────────────────────────────────────────────
# RÉVISÉ (01/09/2026) — bascule de Google Gemini vers Groq comme fournisseur
# PRINCIPAL, à la demande de Rami : le niveau gratuit Gemini plafonne à
# ~20 requêtes/jour sans facturation activée (carte bancaire refusée), ce
# qui a bloqué l'outil en plein test plusieurs fois cette semaine. Groq
# offre un niveau gratuit sans carte bancaire nettement plus généreux (30
# requêtes/minute, 14 400/jour).
# RÉVISÉ (01/09/2026, 2e passe) — demande Rami : bascule automatique vers
# Gemini en repli si Groq échoue (quota, panne...), et vice versa —
# Gemini restauré comme second fournisseur plutôt que remplacé. Les DEUX
# clés API (GROQ_API_KEY et GEMINI_API_KEY) peuvent être configurées en
# parallèle ; l'outil essaie Groq en premier (quota plus généreux), puis
# Gemini automatiquement si le premier essai échoue, sans intervention
# manuelle. Fonctionne aussi avec une seule des deux clés configurée.
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
# RÉVISÉ (01/09/2026, 2e passe) — CAUSE RÉELLE du "0 suggestion IA" malgré
# clés API confirmées présentes : llama-3.3-70b-versatile a été
# officiellement retiré par Groq le 16 août 2026 (plus d'un mois avant
# cette bascule) — chaque appel échouait silencieusement en 404 "modèle
# introuvable" depuis le tout premier jour. Remplacé par openai/gpt-oss-
# 120b, le remplacement officiellement recommandé par Groq — confirme
# aussi le support du mode JSON structuré (plus robuste que l'ancien
# modèle sur ce point précis).
GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/gemini-3.6-flash:generateContent"
)
AUTO_CORRECT_THRESHOLD = 90  # % de confiance minimum pour auto-correction
MAX_ANOMALIES_PER_BATCH = 15 # Nb max d'anomalies par appel API


def _get_secret(name: str) -> str:
    """Lit une clé API depuis les variables d'environnement ou les secrets Streamlit."""
    key = os.environ.get(name, "")
    if not key:
        try:
            key = st.secrets.get(name, "")
        except Exception:
            pass
    return key


def get_gemini_api_key() -> str:
    """
    RÉVISÉ (01/09/2026) — nom de fonction conservé pour ne rien casser côté
    appelants (2_Sessions_Integration.py notamment) : sert maintenant de
    simple test de disponibilité — retourne la première clé configurée
    parmi Groq (priorité) et Gemini, peu importe laquelle _call_gemini
    utilisera réellement (elle regarde les deux elle-même, voir plus bas).
    """
    return _get_secret("GROQ_API_KEY") or _get_secret("GEMINI_API_KEY")


def is_gemini_available() -> bool:
    """Vérifie qu'au moins un des deux fournisseurs IA est configuré."""
    return bool(get_gemini_api_key())


# Nom conservé pour ne rien casser côté appelants qui l'importent déjà
# pour le diagnostic.
LAST_GEMINI_ERROR: str = ""


def _call_groq(prompt: str, api_key: str) -> dict | None:
    """Appel à l'API Groq (format OpenAI-compatible). Retourne le JSON parsé ou None."""
    global LAST_GEMINI_ERROR
    try:
        resp = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                # RÉVISÉ (01/09/2026, 3e passe) — CAUSE RÉELLE probable du
                # "0 suggestion IA" persistant même après correction du nom
                # de modèle : openai/gpt-oss-120b est un modèle de
                # RAISONNEMENT — il consomme une partie du budget de
                # tokens pour son raisonnement interne (champ "reasoning",
                # séparé de "content"), avec un bug documenté côté Groq où
                # le contenu final revient VIDE si le raisonnement épuise
                # tout le budget avant de produire la réponse finale.
                # "max_tokens" (ancien paramètre) est en plus le mauvais
                # nom pour ces modèles précis — "max_completion_tokens"
                # est le paramètre correct. reasoning_effort=low réduit le
                # risque en minimisant le raisonnement interne, laissant
                # plus de place au contenu final recherché.
                "max_completion_tokens": 8192,
                "reasoning_effort": "low",
                "response_format": {"type": "json_object"},
            },
            timeout=45,
        )
        if resp.status_code != 200:
            LAST_GEMINI_ERROR = f"[Groq] HTTP {resp.status_code} : {resp.text[:500]}"
            return None

        data    = resp.json()
        content = (
            data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
        )
        if not content:
            LAST_GEMINI_ERROR = f"[Groq] Réponse sans contenu exploitable : {str(data)[:500]}"
            return None

        return _parse_json_response(content, provider="Groq")
    except Exception as e:
        LAST_GEMINI_ERROR = f"[Groq] {type(e).__name__} : {e}"
        return None


def _call_gemini_native(prompt: str, api_key: str) -> dict | None:
    """Appel direct à l'API Gemini. Retourne le JSON parsé ou None."""
    global LAST_GEMINI_ERROR
    try:
        resp = requests.post(
            f"{GEMINI_URL}?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature":      0.1,
                    "maxOutputTokens":  4096,
                    "responseMimeType": "application/json",
                },
            },
            timeout=45,
        )
        if resp.status_code != 200:
            LAST_GEMINI_ERROR = f"[Gemini] HTTP {resp.status_code} : {resp.text[:500]}"
            return None

        data    = resp.json()
        content = (
            data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
        )
        if not content:
            LAST_GEMINI_ERROR = f"[Gemini] Réponse sans contenu exploitable : {str(data)[:500]}"
            return None

        return _parse_json_response(content, provider="Gemini")
    except Exception as e:
        LAST_GEMINI_ERROR = f"[Gemini] {type(e).__name__} : {e}"
        return None


def _parse_json_response(content: str, provider: str) -> dict | None:
    """
    Nettoyage et parsing JSON communs aux deux fournisseurs (extrait dans sa
    propre fonction lors de l'ajout du repli automatique Groq/Gemini, pour
    éviter de dupliquer cette logique deux fois).
    """
    global LAST_GEMINI_ERROR
    clean = content.strip()
    for tag in ["```json", "```"]:
        clean = clean.replace(tag, "")
    clean = clean.strip()
    try:
        result = json.loads(clean)
        # RÉVISÉ (01/09/2026) — bug réel trouvé et confirmé (comportement
        # documenté du mode JSON forcé de Groq/OpenAI) : quand le prompt
        # demande un tableau JSON en racine mais que le mode json_object
        # est actif, le modèle a tendance à envelopper le tableau dans un
        # objet (ex. {"resultats": [...]}) au lieu de le renvoyer tel
        # quel — même si le prompt demande explicitement un tableau. Le
        # JSON est valide, donc json.loads() réussit sans erreur, mais la
        # forme n'est pas celle attendue par le code appelant (qui
        # vérifie isinstance(response, list)) — résultat : la réponse
        # était silencieusement ignorée, sans la moindre erreur visible.
        # N'existait pas avec l'ancien mode Gemini (responseMimeType),
        # plus permissif sur les tableaux en racine. Si le résultat est
        # un objet contenant une seule liste, on la déballe automatiquement.
        if isinstance(result, dict):
            list_values = [v for v in result.values() if isinstance(v, list)]
            if len(list_values) == 1:
                result = list_values[0]
            elif "id" in result:
                # AJOUTÉ (01/09/2026) — 2e cas confirmé par test réel isolé
                # (script test_groq.py) : avec un lot d'UNE SEULE anomalie,
                # Groq renvoie l'objet suggestion directement (ex. {"id":
                # 1, "valeur_suggeree": "Nearest", ...}), sans même
                # l'envelopper dans un tableau à un élément — ni dans une
                # clé de type liste (le cas déjà couvert juste au-dessus).
                # Reconnu ici via la présence de la clé "id" (présente sur
                # tout objet suggestion attendu par les deux prompts de ce
                # fichier), et remballé en tableau à un élément.
                result = [result]
        LAST_GEMINI_ERROR = ""
        return result
    except json.JSONDecodeError:
        # AJOUTÉ (27/08/2026, jour de la démo) — filet de sécurité : même
        # avec maxOutputTokens relevé, une réponse peut encore être coupée
        # en plein milieu (variabilité du modèle). Plutôt que de tout
        # perdre, on récupère les objets JSON déjà complets dans un
        # tableau tronqué (cas le plus fréquent : "[{...}, {...}, {..."
        # sans fermeture) — mieux vaut quelques suggestions que zéro.
        if clean.startswith("["):
            _last_complete = clean.rfind("},")
            if _last_complete != -1:
                _repaired = clean[:_last_complete + 1] + "]"
                try:
                    result = json.loads(_repaired)
                    LAST_GEMINI_ERROR = f"[{provider}] Réponse tronquée — {len(result)} candidat(s) récupéré(s) sur une réponse incomplète."
                    return result
                except json.JSONDecodeError:
                    pass
        LAST_GEMINI_ERROR = f"[{provider}] Réponse JSON invalide et non réparable."
        return None


def _call_gemini(prompt: str, api_key: str) -> dict | None:
    """
    RÉVISÉ (01/09/2026, 3e passe, veille de démo) — répartiteur : essaie
    RÉVISÉ (01/09/2026, 4e passe, test ce soir) — remis Groq en premier,
    à la demande de Rami, pour vérifier si le fix du déballage (objet nu
    -> tableau à un élément, confirmé sur un cas à une seule anomalie via
    test_groq.py) tient aussi sur des lots plus grands (fichier Devise
    complet, plusieurs lots de 15 anomalies). Bascule automatique sur
    Gemini en repli si Groq échoue malgré tout — rien à changer côté
    appelants existants (enrich_coherence_with_ai, validate_file_axe_c).
    Le paramètre `api_key` reçu n'est plus utilisé directement — chaque
    fournisseur va chercher sa propre clé, puisque les deux peuvent être
    configurés en parallèle.
    """
    _groq_key   = _get_secret("GROQ_API_KEY")
    _gemini_key = _get_secret("GEMINI_API_KEY")

    if _groq_key:
        result = _call_groq(prompt, _groq_key)
        if result is not None:
            return result
        # Échec Groq (quota ou autre) — bascule sur Gemini si disponible.
        if _gemini_key:
            return _call_gemini_native(prompt, _gemini_key)
        return None

    if _gemini_key:
        return _call_gemini_native(prompt, _gemini_key)

    LAST_GEMINI_ERROR = "Aucune clé API configurée (ni GROQ_API_KEY, ni GEMINI_API_KEY)."
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
        print(f"[QC-DIAG] validate_file_axe_c : api_key vide, arrêt immédiat.")
        return result

    if not api_key:
        return result

    metadata    = parse_result.get("metadata", {})
    data_tables = parse_result.get("data_tables", [])
    print(f"[QC-DIAG] validate_file_axe_c : api_key présente (len={len(api_key)}), data_tables={data_tables}")

    for sheet_name in data_tables:
        meta        = metadata.get(sheet_name, {})
        table_label = meta.get("label", sheet_name)

        # Récupérer les anomalies des deux axes pour cet onglet
        a_anomalies = axe_a_result.get("by_sheet", {}).get(sheet_name, [])
        b_anomalies = axe_b_result.get("by_sheet", {}).get(sheet_name, [])
        all_anomalies = a_anomalies + b_anomalies
        print(f"[QC-DIAG] Onglet {sheet_name!r} : {len(a_anomalies)} anomalie(s) Axe A, {len(b_anomalies)} Axe B")

        if not all_anomalies:
            result["by_sheet"][sheet_name] = []
            continue

        # Enrichir avec l'IA
        try:
            enriched = enrich_anomalies_with_ai(
                anomalies=all_anomalies,
                table_label=table_label,
                api_key=api_key,
            )
        except Exception as _exc:
            print(f"[QC-DIAG] EXCEPTION dans enrich_anomalies_with_ai pour {sheet_name!r} : {type(_exc).__name__} : {_exc}")
            import traceback
            traceback.print_exc()
            enriched = all_anomalies
        nb_avec_suggestion = sum(1 for a in enriched if a.get("suggestion_ia"))
        print(f"[QC-DIAG] Onglet {sheet_name!r} : {nb_avec_suggestion}/{len(enriched)} anomalie(s) avec suggestion_ia après enrichissement. LAST_GEMINI_ERROR={LAST_GEMINI_ERROR!r}")

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
- justification : UNE SEULE phrase courte, 15 mots maximum (garde la réponse rapide à générer)
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