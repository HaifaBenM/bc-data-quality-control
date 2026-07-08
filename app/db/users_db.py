"""
Gestion des utilisateurs de l'outil BC QC.

Table Supabase requise :

CREATE TABLE qc_users (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('consultant', 'client')),
    profile_code  TEXT,           -- NULL pour consultant, code profil pour client
    display_name  TEXT NOT NULL,  -- nom affiché dans l'outil
    active        BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Créer un consultant (remplacer les valeurs) :
INSERT INTO qc_users (username, password_hash, role, display_name)
VALUES (
    'rami',
    encode(digest('ton_mot_de_passe', 'sha256'), 'hex'),
    'consultant',
    'Rami'
);

-- Créer un accès client :
INSERT INTO qc_users (username, password_hash, role, profile_code, display_name)
VALUES (
    'aquachiara',
    encode(digest('mot_de_passe_client', 'sha256'), 'hex'),
    'client',
    'AQUACHIARA001',
    'Aquachiara'
);

-- Générer le hash en Python :
-- import hashlib
-- print(hashlib.sha256('mot_de_passe'.encode()).hexdigest())
"""
import hashlib
from app.db.supabase_client import get_supabase_client


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_login(username: str, password: str) -> dict | None:
    """
    Vérifie les credentials et retourne l'utilisateur si valide.

    Returns:
        {username, role, profile_code, display_name} ou None si invalide.
    """
    if not username or not password:
        return None
    try:
        res = (
            get_supabase_client()
            .table("qc_users")
            .select("username, role, profile_code, display_name, active")
            .eq("username", username.strip().lower())
            .eq("password_hash", hash_password(password))
            .execute()
        )
        if not res.data:
            return None
        user = res.data[0]
        if not user.get("active", True):
            return None
        return user
    except Exception:
        return None


def get_all_users() -> list:
    """Retourne tous les utilisateurs (pour gestion admin future)."""
    try:
        res = (
            get_supabase_client()
            .table("qc_users")
            .select("username, role, profile_code, display_name, active, created_at")
            .order("role")
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def create_user(
    username: str,
    password: str,
    role: str,
    display_name: str,
    profile_code: str = "",
) -> tuple[bool, str]:
    """Crée un nouvel utilisateur."""
    try:
        get_supabase_client().table("qc_users").insert({
            "username":      username.strip().lower(),
            "password_hash": hash_password(password),
            "role":          role,
            "display_name":  display_name.strip(),
            "profile_code":  profile_code.strip() or None,
            "active":        True,
        }).execute()
        return True, ""
    except Exception as e:
        err = str(e)
        if "duplicate" in err.lower() or "unique" in err.lower():
            return False, f"L'utilisateur '{username}' existe déjà."
        return False, f"Erreur : {err}"
