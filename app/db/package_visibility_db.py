"""
Gestion de la visibilité des packages BC par client.

Table Supabase requise :

CREATE TABLE package_visibility (
    id                UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_code       TEXT NOT NULL,
    package_code      TEXT NOT NULL,
    visible           BOOLEAN DEFAULT TRUE,
    first_export_done BOOLEAN DEFAULT FALSE,
    updated_at        TIMESTAMPTZ DEFAULT now(),
    UNIQUE(client_code, package_code)
);
"""
from datetime import datetime, timezone
from app.db.supabase_client import get_supabase_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_visibility_map(client_code: str) -> dict[str, bool]:
    """
    Retourne {package_code: visible} pour un client.
    Les packages sans entrée sont visibles par défaut.
    """
    try:
        res = (
            get_supabase_client()
            .table("package_visibility")
            .select("package_code, visible")
            .eq("client_code", client_code)
            .execute()
        )
        return {r["package_code"]: r["visible"] for r in (res.data or [])}
    except Exception:
        return {}


def set_visibility(client_code: str, package_code: str, visible: bool) -> None:
    """Active ou masque un package pour un client."""
    try:
        get_supabase_client().table("package_visibility").upsert(
            {
                "client_code":  client_code,
                "package_code": package_code,
                "visible":      visible,
                "updated_at":   _now(),
            },
            on_conflict="client_code,package_code",
        ).execute()
    except Exception:
        pass


def is_first_export(client_code: str, package_code: str) -> bool:
    """Retourne True si le package n'a jamais été exporté pour ce client."""
    try:
        res = (
            get_supabase_client()
            .table("package_visibility")
            .select("first_export_done")
            .eq("client_code", client_code)
            .eq("package_code", package_code)
            .execute()
        )
        if not res.data:
            return True
        return not res.data[0].get("first_export_done", False)
    except Exception:
        return True


def mark_exported(client_code: str, package_code: str) -> None:
    """Marque le premier export comme effectué."""
    try:
        get_supabase_client().table("package_visibility").upsert(
            {
                "client_code":       client_code,
                "package_code":      package_code,
                "first_export_done": True,
                "updated_at":        _now(),
            },
            on_conflict="client_code,package_code",
        ).execute()
    except Exception:
        pass


def filter_visible_packages(packages: list[dict], client_code: str) -> list[dict]:
    """
    Filtre la liste des packages BC selon la visibilité configurée.
    Les packages sans règle sont visibles par défaut.
    """
    vis_map = get_visibility_map(client_code)
    return [p for p in packages if vis_map.get(p.get("code", ""), True)]
