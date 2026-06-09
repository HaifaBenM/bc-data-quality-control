"""
Opérations CRUD pour les sessions de contrôle qualité dans Supabase.
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
            "id":              session_id,
            "name":            data.get("session_name", ""),
            "profile_code":    data.get("profile_code", ""),
            "file_name":       data.get("file_name", ""),
            "status":          data.get("status", "Analyse terminée"),
            "iteration":       data.get("iteration", 1),
            "total_anomalies": data.get("total_anomalies", 0),
            "major_anomalies": data.get("major_anomalies", 0),
            "minor_anomalies": data.get("minor_anomalies", 0),
            "notes":           data.get("notes", ""),
            "created_at":      now,
            "updated_at":      now,
        }
        client.table("qc_sessions").insert(row).execute()
        return True, session_id
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def update_session(session_id: str, data: dict) -> tuple[bool, str]:
    """
    Met à jour les champs modifiables d'une session.
    Champs modifiables : name, status, notes.
    """
    try:
        client = get_supabase_client()
        payload = {k: v for k, v in data.items()
                   if k in ("name", "status", "notes")}
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
