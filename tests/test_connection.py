"""
Tests de base pour la connexion Supabase.
Lancer avec : pytest tests/
"""
import os
import pytest


def test_env_variables_exist():
    """
    Vérifie que les variables d'environnement Supabase sont définies.
    """
    from dotenv import load_dotenv
    load_dotenv()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    assert url is not None, "SUPABASE_URL manquant dans le .env"
    assert key is not None, "SUPABASE_KEY manquant dans le .env"
    assert url.startswith("https://"), "SUPABASE_URL doit commencer par https://"
    assert len(key) > 20, "SUPABASE_KEY semble invalide (trop court)"
