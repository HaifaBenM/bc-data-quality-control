"""
Opérations CRUD pour les sessions de contrôle qualité dans Supabase.

⚠️ Nécessite l'ajout de 4 colonnes sur la table qc_sessions avant déploiement :
   ALTER TABLE qc_sessions ADD COLUMN original_file_b64 text;
   ALTER TABLE qc_sessions ADD COLUMN generated_file_b64 text;
   ALTER TABLE qc_sessions ADD COLUMN generated_file_name text;
   ALTER TABLE qc_sessions ADD COLUMN prerequisites_report jsonb;

   Stockage en base64 dans une colonne text — acceptable pour des fichiers
   de taille démo. Si les fichiers clients deviennent volumineux (plusieurs
   Mo), migrer vers Supabase Storage (bucket + URL en base) plutôt que de
   continuer à grossir la table qc_sessions.

⚠️ AJOUTÉ (19/08/2026) — architecture mère/fille (une session par table de
la roadmap, sessions imbriquées en arbre reflétant les dépendances de
level_config, cf. décisions Rami du 18-19/08) — 3 colonnes supplémentaires :
   ALTER TABLE qc_sessions ADD COLUMN parent_session_id text REFERENCES qc_sessions(id);
   ALTER TABLE qc_sessions ADD COLUMN table_id integer;
   ALTER TABLE qc_sessions ADD COLUMN is_root boolean DEFAULT false;

   - is_root=true : session "conteneur" d'un socle (ex. "Socle Stock —
     TEST-GL-VALIDATION"), pas rattachée à une table précise, pas de
     package BC ni de fichier associé — juste la racine de l'arbre.
   - table_id : la table BC (level_config) que CETTE session fille traite.
   - parent_session_id : résolu automatiquement à la création quand un
     candidat unique existe (voir resolve_parent_candidates ci-dessous) ;
     laissé au choix de l'utilisateur si plusieurs candidats sont possibles
     (level_config donne un NIVEAU, pas un graphe de dépendance table-à-
     table précis — deux tables du même niveau, comme 204 Unité et 5722
     Catégorie article, ne dépendent pas forcément l'une de l'autre, donc
     l'automatisme ne peut pas toujours trancher seul).
"""
import uuid
from datetime import datetime, timezone
from app.db.supabase_client import get_supabase_client

SESSION_STATUSES = [
    "Nouvelle",
    "Analyse en cours",
    "Analyse terminée",
    "En attente client",
    "Corrections reçues",
    "Terminée",
]

STATUS_COLORS = {
    "Nouvelle":           "#64748B",
    "Analyse en cours":   "#534AB7",
    "Analyse terminée":   "#2E6FBF",
    "En attente client":  "#854F0B",
    "Corrections reçues": "#0F6E56",
    "Terminée":           "#0F6E56",
}

STATUS_ICONS = {
    "Nouvelle":           "🆕",
    "Analyse en cours":   "🔄",
    "Analyse terminée":   "📊",
    "En attente client":  "⏳",
    "Corrections reçues": "📥",
    "Terminée":           "✅",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_session_id(client_code: str) -> str:
    ts    = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    short = str(uuid.uuid4())[:6].upper()
    return f"{client_code}-{ts}-{short}"


def save_session(data: dict) -> tuple[bool, str]:
    """Crée une nouvelle session. Retourne (True, session_id) ou (False, erreur)."""
    try:
        client     = get_supabase_client()
        session_id = generate_session_id(data.get("profile_code", "SES"))
        now        = _now()
        row = {
            "id":                    session_id,
            "name":                  data.get("session_name", ""),
            "profile_code":          data.get("profile_code", ""),
            "file_name":             data.get("file_name", ""),
            "status":                data.get("status", "Analyse terminée"),
            "iteration":             data.get("iteration", 1),
            "total_anomalies":       data.get("total_anomalies", 0),
            "major_anomalies":       data.get("major_anomalies", 0),
            "minor_anomalies":       data.get("minor_anomalies", 0),
            "notes":                 data.get("notes", ""),
            "date_controle":         data.get("date_controle", ""),
            "company_id":            data.get("company_id", ""),
            "company_name":          data.get("company_name", ""),
            # Fichier chargé par le client — permet de le retélécharger
            # depuis "Mes sessions" sans redemander l'upload.
            "original_file_b64":     data.get("original_file_b64", ""),
            # Fichier corrigé généré (corrections VALEUR_CORRIGIBLE validées
            # par le consultant appliquées, mapping XML préservé).
            "generated_file_b64":    data.get("generated_file_b64", ""),
            "generated_file_name":   data.get("generated_file_name", ""),
            # Checklist des données maîtresses à créer côté BC avant import
            # (anomalies PREALABLE_BC_REQUIS) — distinct du fichier corrigé.
            "prerequisites_report":  data.get("prerequisites_report", []),
            # AJOUTÉ (19/08/2026) — architecture mère/fille.
            "table_id":              data.get("table_id"),
            "parent_session_id":     data.get("parent_session_id"),
            "is_root":               data.get("is_root", False),
            "created_at":            now,
            "updated_at":            now,
        }
        client.table("qc_sessions").insert(row).execute()
        return True, session_id
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def update_session(session_id: str, data: dict) -> tuple[bool, str]:
    """
    Met à jour les champs modifiables d'une session.
    Champs modifiables : name, status, notes, et — quand une nouvelle
    génération de fichier corrigé est faite après coup — generated_file_b64,
    generated_file_name, prerequisites_report.
    """
    try:
        client = get_supabase_client()
        editable = (
            "name", "status", "notes",
            "generated_file_b64", "generated_file_name", "prerequisites_report",
        )
        payload = {k: v for k, v in data.items() if k in editable}
        payload["updated_at"] = _now()
        client.table("qc_sessions").update(payload).eq("id", session_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def delete_session(session_id: str) -> tuple[bool, str]:
    """Supprime une session et ses corrections."""
    try:
        client = get_supabase_client()
        client.table("qc_corrections").delete().eq("session_id", session_id).execute()
        client.table("qc_sessions").delete().eq("id", session_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def get_all_sessions(profile_code: str = None) -> list:
    """Retourne toutes les sessions triées par date décroissante."""
    try:
        client = get_supabase_client()
        query  = client.table("qc_sessions").select("*").order("created_at", desc=True)
        if profile_code:
            query = query.eq("profile_code", profile_code)
        res = query.execute()
        return res.data or []
    except Exception:
        return []


def get_session_by_id(session_id: str) -> dict:
    """Retourne une session par son ID."""
    try:
        client = get_supabase_client()
        res    = client.table("qc_sessions").select("*").eq("id", session_id).execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════
# AJOUTÉ (19/08/2026) — architecture mère/fille (une session par table de la
# roadmap, imbriquées en arbre reflétant level_config). Toutes les fonctions
# ci-dessous travaillent sur un seul appel get_all_sessions() par société —
# le calcul d'arbre/scope se fait ensuite en mémoire (léger, pas d'aller-
# retour Supabase par nœud), même logique que le principe déjà appliqué au
# fix perf du 07/08 (regrouper les appels réseau, calculer en mémoire).
# ══════════════════════════════════════════════════════════════════════════

def get_sessions_for_company(profile_code: str, company_id: str) -> list:
    """Toutes les sessions (racines + filles) d'une société donnée, triées
    par date de création croissante — ordre stable pour l'affichage en arbre."""
    try:
        client = get_supabase_client()
        res = (
            client.table("qc_sessions")
            .select("*")
            .eq("profile_code", profile_code)
            .eq("company_id",   company_id)
            .order("created_at", desc=False)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def build_sessions_tree(sessions: list) -> list[dict]:
    """
    Transforme une liste plate de sessions (avec parent_session_id) en arbre.

    Retourne une liste de noeuds racines, chacun avec une clé "children"
    (liste récursive du même format). Une session dont le parent_session_id
    référence un ID absent de la liste (parent supprimé, ou d'une autre
    société par erreur de données) est remontée comme racine plutôt que
    silencieusement perdue — mieux vaut un arbre légèrement inexact et
    visible qu'une session invisible dans l'UI.
    """
    by_id: dict[str, dict] = {s["id"]: {**s, "children": []} for s in sessions}
    roots: list[dict] = []
    for s in sessions:
        node = by_id[s["id"]]
        parent_id = s.get("parent_session_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


def resolve_parent_candidates(
    session_list: list,
    table_id: int,
    level_config: dict,
) -> list[dict]:
    """
    Calcule les sessions candidates pour être le parent d'une nouvelle
    session fille rattachée à `table_id`.

    Logique : le parent doit être une session existante (de la même
    société) dont la table est classée à un niveau STRICTEMENT INFÉRIEUR
    dans level_config — c'est la seule information de dépendance fiable
    que level_config fournit (un numéro de niveau, pas un graphe table-à-
    table précis). Parmi tous les niveaux inférieurs déjà représentés par
    une session, on ne propose que ceux du niveau le PLUS PROCHE (le plus
    élevé parmi les niveaux < niveau de table_id) — c'est le rattachement
    le plus probable, mais reste une PROPOSITION, pas une certitude : deux
    tables du même niveau (ex. 204 Unité et 5722 Catégorie article, toutes
    deux niveau -1) ne dépendent pas forcément l'une de l'autre, donc quand
    plusieurs sessions existent à ce niveau le plus proche, elles sont
    TOUTES retournées et c'est à l'utilisateur de choisir — jamais de choix
    automatique arbitraire entre plusieurs candidats de même niveau.

    Retourne une liste vide si aucun niveau inférieur n'a encore de session
    (le nouveau nœud doit alors être rattaché à la racine du socle).
    """
    my_level = level_config.get(table_id).level if table_id in level_config else None
    if my_level is None:
        return []  # table non classée : pas de dépendance connue, rattacher à la racine

    candidates_by_level: dict[int, list[dict]] = {}
    for s in session_list:
        s_tid = s.get("table_id")
        if not s_tid or s.get("is_root"):
            continue
        s_level = level_config.get(s_tid).level if s_tid in level_config else None
        if s_level is None or s_level >= my_level:
            continue
        candidates_by_level.setdefault(s_level, []).append(s)

    if not candidates_by_level:
        return []
    closest_level = max(candidates_by_level.keys())
    return candidates_by_level[closest_level]


def get_descendant_table_ids(session_id: str, session_list: list) -> set[int]:
    """
    Retourne l'ensemble des table_id de la session donnée ET de TOUS ses
    descendants (fille, petite-fille, etc.) — utilisé pour scoper le bouton
    "Revérifier" à un sous-arbre plutôt qu'à toute la société (voir
    refresh_roadmap(scope_table_ids=...) dans integration_levels.py).

    Complexité O(n) sur le nombre de sessions de la société (construit une
    fois la map parent -> enfants, puis parcourt en largeur) — négligeable
    vu les volumes attendus (dizaines de sessions par société, pas des
    milliers).
    """
    children_by_parent: dict[str, list[str]] = {}
    table_id_by_session: dict[str, int] = {}
    for s in session_list:
        table_id_by_session[s["id"]] = s.get("table_id")
        pid = s.get("parent_session_id")
        if pid:
            children_by_parent.setdefault(pid, []).append(s["id"])

    result: set[int] = set()
    queue = [session_id]
    seen: set[str] = set()
    while queue:
        sid = queue.pop(0)
        if sid in seen:
            continue
        seen.add(sid)
        tid = table_id_by_session.get(sid)
        if tid:
            result.add(tid)
        queue.extend(children_by_parent.get(sid, []))
    return result