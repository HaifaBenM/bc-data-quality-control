"""
Stockage des structures de packages BC dans Supabase.

Le consultant uploade l'Excel BC natif → file_parser lit la structure
→ sauvegardée ici → réutilisée pour générer les templates clients.

Table Supabase requise :

CREATE TABLE package_templates (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_code  TEXT NOT NULL,
    package_code TEXT NOT NULL,
    table_id     INTEGER NOT NULL,
    table_name   TEXT NOT NULL,
    fields       JSONB NOT NULL DEFAULT '[]',
    sort_order   INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT now(),
    updated_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE(client_code, package_code, table_id)
);
"""
import json
from datetime import datetime, timezone
from app.db.supabase_client import get_supabase_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_template(
    client_code: str,
    package_code: str,
    tables: list[dict],
) -> tuple[bool, str]:
    """
    Sauvegarde la structure d'un package (tables + champs).

    Args:
        client_code  : code profil client
        package_code : code du package BC (ex: "003K-ARTICLE")
        tables       : [{ table_id, table_name, fields: [{field_name, data_type,
                         required, max_length, ...}], sort_order }]

    Returns:
        (True, "") ou (False, message_erreur)
    """
    try:
        client = get_supabase_client()
        now    = _now()

        for i, table in enumerate(tables):
            client.table("package_templates").upsert(
                {
                    "client_code":  client_code,
                    "package_code": package_code,
                    "table_id":     int(table.get("table_id", 0)),
                    "table_name":   table.get("table_name", ""),
                    "fields":       json.dumps(table.get("fields", [])),
                    "sort_order":   table.get("sort_order", i),
                    "updated_at":   now,
                },
                on_conflict="client_code,package_code,table_id",
            ).execute()

        return True, ""
    except Exception as e:
        return False, str(e)


def get_template(client_code: str, package_code: str) -> list[dict]:
    """
    Retourne la structure sauvegardée d'un package, triée par sort_order.
    Retourne [] si aucun template n'a été configuré.
    """
    try:
        res = (
            get_supabase_client()
            .table("package_templates")
            .select("table_id, table_name, fields, sort_order")
            .eq("client_code", client_code)
            .eq("package_code", package_code)
            .order("sort_order")
            .execute()
        )
        tables = []
        for row in (res.data or []):
            fields = row.get("fields", [])
            if isinstance(fields, str):
                fields = json.loads(fields)
            tables.append({
                "table_id":   row["table_id"],
                "table_name": row["table_name"],
                "fields":     fields,
                "sort_order": row["sort_order"],
            })
        return tables
    except Exception:
        return []


def has_template(client_code: str, package_code: str) -> bool:
    """Vérifie si un template existe pour ce package."""
    try:
        res = (
            get_supabase_client()
            .table("package_templates")
            .select("id")
            .eq("client_code", client_code)
            .eq("package_code", package_code)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


def delete_template(client_code: str, package_code: str) -> tuple[bool, str]:
    """Supprime le template d'un package (pour reconfigurer)."""
    try:
        get_supabase_client().table("package_templates").delete()\
            .eq("client_code", client_code)\
            .eq("package_code", package_code)\
            .execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_configured_packages(client_code: str) -> set[str]:
    """Retourne les codes de packages qui ont un template configuré."""
    try:
        res = (
            get_supabase_client()
            .table("package_templates")
            .select("package_code")
            .eq("client_code", client_code)
            .execute()
        )
        return {r["package_code"] for r in (res.data or [])}
    except Exception:
        return set()
