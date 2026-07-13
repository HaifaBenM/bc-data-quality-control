from datetime import datetime, timezone
from app.db.supabase_client import get_supabase_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_packages(client_code: str) -> list:
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
    try:
        client  = get_supabase_client()
        allowed = ("nom_package", "nb_tables", "nb_records", "nb_errors")
        payload = {k: v for k, v in data.items() if k in allowed}
        payload["updated_at"] = _now()
        client.table("bc_packages").update(payload).eq("id", pkg_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def delete_package(pkg_id: str) -> tuple[bool, str]:
    try:
        client = get_supabase_client()
        client.table("bc_packages").delete().eq("id", pkg_id).execute()
        return True, ""
    except Exception as e:
        return False, f"Erreur : {str(e)}"


def get_package_by_id(pkg_id: str) -> dict:
    try:
        client = get_supabase_client()
        res    = client.table("bc_packages").select("*").eq("id", pkg_id).execute()
        return res.data[0] if res.data else {}
    except Exception:
        return {}


def update_package_stats(pkg_id: str, nb_tables: int, nb_records: int, nb_errors: int) -> None:
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


def get_template(profile_code: str, package_code: str) -> dict | None:
    try:
        client = get_supabase_client()
        res = (
            client.table("package_excel_templates")
            .select("original_b64, file_name")
            .eq("client_code", profile_code)
            .eq("package_code", package_code)
            .maybe_single()
            .execute()
        )
        return res.data
    except Exception:
        return None


def save_template(profile_code: str, package_code: str, b64: str, file_name: str) -> tuple[bool, str]:
    try:
        client   = get_supabase_client()
        existing = get_template(profile_code, package_code)
        if existing:
            client.table("package_excel_templates") \
                .update({"original_b64": b64, "file_name": file_name}) \
                .eq("client_code", profile_code) \
                .eq("package_code", package_code) \
                .execute()
        else:
            client.table("package_excel_templates").insert({
                "client_code":  profile_code,
                "package_code": package_code,
                "original_b64": b64,
                "file_name":    file_name,
            }).execute()
        return True, ""
    except Exception as e:
        return False, str(e)


def delete_template(profile_code: str, package_code: str) -> tuple[bool, str]:
    try:
        client = get_supabase_client()
        client.table("package_excel_templates") \
            .delete() \
            .eq("client_code", profile_code) \
            .eq("package_code", package_code) \
            .execute()
        return True, ""
    except Exception as e:
        return False, str(e)