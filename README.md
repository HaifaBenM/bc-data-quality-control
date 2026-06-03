# 🔍 BC Data Quality Control

Outil de contrôle qualité des données Master Data pour Microsoft Dynamics 365 Business Central.

## Objectif

Garantir que les fichiers de données clients peuvent être importés dans BC sans erreur,
en combinant validation automatique, intelligence artificielle et règles métier client.

## Fonctionnalités

- ✅ Validation des contraintes BC standard (type, longueur, format...)
- ✅ Vérification des références croisées BC (Payment Terms, Currency, Country...)
- ✅ Suggestions de correction par IA (Google Gemini)
- ✅ Règles métier spécifiques par client
- ✅ Génération du fichier de corrections structuré (16 colonnes)
- ✅ Application des corrections validées par le client
- ✅ Fichier final prêt pour import BC via Package de Configuration

## Installation locale

```bash
# 1. Cloner le dépôt
git clone https://github.com/HaifaBenM/bc-data-quality-control.git
cd bc-data-quality-control

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer les variables d'environnement
cp .env.example .env
# Remplir le fichier .env avec vos credentials

# 4. Lancer l'application
streamlit run main.py
```

## Structure du projet

```
bc-data-quality-control/
├── main.py                    # Page d'accueil Streamlit
├── pages/                     # Pages de navigation
│   ├── 1_Dashboard.py
│   ├── 2_Sessions.py
│   ├── 3_Profils_Clients.py
│   └── 4_Regles_Metier.py
├── app/
│   ├── core/                  # Logique métier (validation, corrections)
│   ├── db/                    # Accès base de données Supabase
│   └── utils/                 # Fonctions utilitaires
├── tests/                     # Tests automatisés
├── .streamlit/config.toml     # Configuration Streamlit
├── requirements.txt
└── .env.example
```

## Déploiement

L'application est déployée automatiquement sur Streamlit Community Cloud
à chaque merge sur la branche `main`.

## Sprints

| Sprint | Fonctionnalité | Statut |
|--------|---------------|--------|
| 0 | Setup & squelette | ✅ Terminé |
| 1 | Upload + vérification structurelle | 🚧 À venir |
| 2 | Profils clients + règles métier | 🚧 À venir |
| 3 | Connexion BC + metadata | 🚧 À venir |
| 4 | Validation Axe A | 🚧 À venir |
| 5 | Validation Axe B | 🚧 À venir |
| 6 | IA + règles métier | 🚧 À venir |
| 7 | Fichier de corrections | 🚧 À venir |
| 8 | Application corrections + fichier final | 🚧 À venir |
| 9 | Dashboard + sessions + bouton AL | 🚧 À venir |
