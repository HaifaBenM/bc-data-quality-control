"""
Module de connexion à Supabase.
Gère la connexion à la base de données pour toute l'application.
"""
import os
import streamlit as st
from supabase import create_client, Client


def get_credentials():
    """
    Récupère les credentials Supabase.
    - En local : depuis le fichier .env
    - Sur Streamlit Cloud : depuis st.secrets
    """
    # Essayer d'abord les variables d'environnement (local avec .env)
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    # Si pas trouvé, essayer st.secrets (Streamlit Cloud)
    if not url or not key:
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        except Exception:
            pass

    return url, key


@st.cache_resource
def get_supabase_client() -> Client:
    """
    Crée et retourne le client Supabase.
    @st.cache_resource = créé une seule fois et réutilisé.
    """
    url, key = get_credentials()

    if not url or not key:
        raise ValueError(
            "Credentials Supabase manquants. "
            "Vérifiez votre fichier .env ou les secrets Streamlit."
        )

    return create_client(url, key)


def test_connection() -> tuple[bool, str]:
    """
    Teste la connexion à Supabase.
    Retourne (True, "OK") ou (False, "message d'erreur")
    """
    try:
        client = get_supabase_client()
        # Tester avec une requête simple sur la table client_profiles
        client.table("client_profiles").select("id").limit(1).execute()
        return True, "Connecté"
    except ValueError as e:
        return False, "Credentials manquants"
    except Exception as e:
        return False, str(e)[:50]
