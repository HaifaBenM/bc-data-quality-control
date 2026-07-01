"""
Opérations CRUD pour les packages de configuration BC.

Table Supabase requise (SQL ci-dessous) :

CREATE TABLE bc_packages (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_code  TEXT NOT NULL REFERENCES client_profiles(code) ON DELETE CASCADE,
    code         TEXT NOT NULL,
    nom_package  TEXT NOT NULL,
    nb_tables    INTEGER DEFAULT 0,
    nb_records   INTEGER DEFAULT 0,
    nb_errors    INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE(client_code, code)
);
"""
from datetime import datetime, timezone
from app.db.supabase_client import get_supabase_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_packages(client_code: str) -> list:
    """Retourne tous les packages d'un client, triés par code."""
    try:
        client = get_supabase_client()
        res = (
            client.table("bc_packages")
            .select("*")
            .eq("client_code", client_code)
            .order("code")
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def create_package(data: dict) -> tuple[bool, str]:
    """Crée un nouveau package. Retourne (True, id) ou (False, message_erreur)."""
    try:
        client = get_supabase_client()
        row = {
            "client_code": data.get("client_code", ""),
            "code":        data.get("code", "").strip().upper(),
            "nom_package": data.get("nom_package", "").strip(),
            "nb_tables":   int(data.get("nb_tables", 0)),
            "nb_records":  int(data.get("nb_records", 0)),
            "nb_errors":   int(data.get("nb_errors", 0)),
            "created_at":  _now(),
            "updated_at":  _now(),
        }
        res = client.table("bc_packages").insert(row).execute()
        inserted_id = res.data[0]["id"] if res.data else ""
        return True, inserted_id
    except Exception as e:
        err = str(e)
        if "duplicate" in err.lower() or "unique" in err.lower():
            return False, f"Le code '{data.get('code', '')}' existe déjà pour ce client."
        return False, f"Erreur : {err}"


def update_package(pkg_id: str, data: dict) -> tuple[bool, str]:
    """Met à jour un package existant."""
    try:
        client = get_supabase_client()
        allowed = ("nom_package", "nb_tables", "nb_records", "nb_errors")
        payload = {k: v for k, v in data.items() if k in allowed}
        payload["updated_at"] = _now()
        client.table("bc_packages").update(payload).eq("id", pkg_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def delete_package(pkg_id: str) -> tuple[bool, str]:
    """Supprime un package."""
    try:
        client = get_supabase_client()
        client.table("bc_packages").delete().eq("id", pkg_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def get_package_by_id(pkg_id: str) -> dict:
    """Retourne un package par son ID."""
    try:
        client = get_supabase_client()
        res = client.table("bc_packages").select("*").eq("id", pkg_id).execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


def update_package_stats(pkg_id: str, nb_tables: int, nb_records: int, nb_errors: int) -> None:
    """Met à jour les stats d'un package après une session d'intégration."""
    try:
        client = get_supabase_client()
        client.table("bc_packages").update({
            "nb_tables":  nb_tables,
            "nb_records": nb_records,
            "nb_errors":  nb_errors,
            "updated_at": _now(),
        }).eq("id", pkg_id).execute()
    except Exception:
        pass
