"""
Stockage des templates Excel BC (format natif préservé).

Table Supabase requise :

CREATE TABLE package_excel_templates (
    id           UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    client_code  TEXT NOT NULL,
    package_code TEXT NOT NULL,
    template_b64 TEXT NOT NULL,
    sheets_info  TEXT NOT NULL DEFAULT '[]',
    uploaded_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE(client_code, package_code)
);
"""
import base64
import json
from app.db.supabase_client import get_supabase_client


def save_excel_template(
    client_code:    str,
    package_code:   str,
    template_bytes: bytes,       # fichier complet BC (avec Template sheet, xmlMaps...)
    sheets_info:    list[dict],  # métadonnées des onglets data
) -> tuple[bool, str]:
    """
    Stocke deux versions du template :
      - template_b64  : fichier complet VIDÉ (rows 4+ supprimées)
                        → servi au client pour téléchargement
      - original_b64  : fichier complet ORIGINAL (avec données BC si présentes)
                        → utilisé comme base pour write_corrected_data()
    """
    try:
        from app.core.bc_excel_processor import clear_bc_excel_data
        cleared_bytes, _ = clear_bc_excel_data(template_bytes)
        get_supabase_client().table("package_excel_templates").upsert(
            {
                "client_code":  client_code,
                "package_code": package_code,
                "template_b64": base64.b64encode(cleared_bytes).decode(),
                "original_b64": base64.b64encode(template_bytes).decode(),
                "sheets_info":  json.dumps(sheets_info),
            },
            on_conflict="client_code,package_code",
        ).execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def get_excel_template(
    client_code: str,
    package_code: str,
) -> tuple[bytes | None, list[dict]]:
    """Retourne (template_bytes, sheets_info) ou (None, [])."""
    try:
        res = (
            get_supabase_client()
            .table("package_excel_templates")
            .select("template_b64, sheets_info")
            .eq("client_code", client_code)
            .eq("package_code", package_code)
            .execute()
        )
        if not res.data:
            return None, []
        row = res.data[0]
        tpl = base64.b64decode(row["template_b64"])
        info = json.loads(row.get("sheets_info") or "[]")
        return tpl, info
    except Exception:
        return None, []


def has_excel_template(client_code: str, package_code: str) -> bool:
    try:
        res = (
            get_supabase_client()
            .table("package_excel_templates")
            .select("id")
            .eq("client_code", client_code)
            .eq("package_code", package_code)
            .limit(1)
            .execute()
        )
        return bool(res.data)
    except Exception:
        return False


def delete_excel_template(client_code: str, package_code: str) -> None:
    try:
        get_supabase_client().table("package_excel_templates").delete()\
            .eq("client_code", client_code)\
            .eq("package_code", package_code)\
            .execute()
    except Exception:
        pass


def get_configured_packages(client_code: str) -> set[str]:
    try:
        res = (
            get_supabase_client()
            .table("package_excel_templates")
            .select("package_code")
            .eq("client_code", client_code)
            .execute()
        )
        return {r["package_code"] for r in (res.data or [])}
    except Exception:
        return set()


def get_original_template(
    client_code: str,
    package_code: str,
) -> bytes | None:
    """Retourne le template original complet (pour write_corrected_data)."""
    try:
        res = (
            get_supabase_client()
            .table("package_excel_templates")
            .select("original_b64")
            .eq("client_code", client_code)
            .eq("package_code", package_code)
            .execute()
        )
        if not res.data or not res.data[0].get("original_b64"):
            # Fallback sur template vidé si original absent
            return get_excel_template(client_code, package_code)[0]
        return base64.b64decode(res.data[0]["original_b64"])
    except Exception:
        return None
