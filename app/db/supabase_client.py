"""
Module de connexion à Supabase.
"""
import os
import streamlit as st
from supabase import create_client, Client


def get_credentials():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        try:
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        except Exception:
            pass
    return url, key


@st.cache_resource
def get_supabase_client() -> Client:
    url, key = get_credentials()
    if not url or not key:
        raise ValueError("Credentials Supabase manquants.")
    return create_client(url, key)


def test_connection() -> tuple[bool, str]:
    try:
        client = get_supabase_client()
        client.table("client_profiles").select("id").limit(1).execute()
        return True, "Connecté"
    except ValueError:
        return False, "Credentials manquants"
    except Exception as e:
        return False, str(e)[:50]
