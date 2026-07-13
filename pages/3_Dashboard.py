"""
Page Dashboard — Vue globale des sessions pour le client actif.
"""
import streamlit as st
from app.core.auth import require_role
from app.db.sessions_db import get_all_sessions, STATUS_COLORS, STATUS_ICONS

st.set_page_config(
    page_title="Dashboard — BC Quality Control",
    page_icon="📊",
    layout="wide",
)

require_role()

# ── Guard ─────────────────────────────────────────────────────────────────────
active_client      = st.session_state.get("active_client", "")
active_client_name = st.session_state.get("active_client_name", "")


# ── Page ──────────────────────────────────────────────────────────────────────
st.markdown(f"# 📊 Dashboard — {active_client_name}")
st.caption(f"Client : **{active_client_name}** ({active_client})")
st.markdown("---")

sessions = get_all_sessions(profile_code=active_client)

# ── Métriques ─────────────────────────────────────────────────────────────────
total_ses   = len(sessions)
active_ses  = sum(1 for s in sessions if s.get("status") not in ("Terminée",))
total_major = sum(s.get("major_anomalies", 0) for s in sessions)
ready_ses   = sum(1 for s in sessions if s.get("major_anomalies", 0) == 0 and s.get("status") == "Terminée")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Sessions totales",    total_ses)
col2.metric("En cours",            active_ses)
col3.metric("Anomalies majeures",  total_major)
col4.metric("Fichiers prêts BC",   ready_ses)

st.markdown("---")

if not sessions:
    st.info("Aucune session pour ce client. Lancez une analyse depuis **Sessions Intégration** ou **Packages**.")
else:
    # ── Tableau des sessions ──────────────────────────────────────────────────
    st.markdown(f"### 📋 {total_ses} session(s)")

    for s in sessions:
        status   = s.get("status", "Nouvelle")
        sc       = STATUS_COLORS.get(status, "#64748B")
        si       = STATUS_ICONS.get(status, "")
        tot_a    = s.get("total_anomalies", 0)
        maj_a    = s.get("major_anomalies", 0)
        min_a    = s.get("minor_anomalies", 0)
        crd      = s.get("created_at", "")[:16].replace("T", " ") if s.get("created_at") else ""
        fn       = s.get("file_name", "")

        an_str = (
            f'<span style="color:#993C1D">🔴 {maj_a} maj.</span> · '
            f'<span style="color:#854F0B">🟠 {min_a} min.</span>'
            if tot_a > 0 else
            '<span style="color:#0F6E56">✅ Aucune anomalie</span>'
        )

        st.markdown(
            f'<div style="background:white;border:1px solid #E2E8F0;border-radius:8px;'
            f'padding:.8rem 1.2rem;margin:.35rem 0">'
            f'<p style="font-size:.95rem;font-weight:600;color:#1B3A6B;margin:0 0 .2rem">'
            f'{s.get("name","")}</p>'
            f'<p style="font-size:.8rem;color:#64748B;margin:.1rem 0">'
            f'<span style="color:{sc};font-weight:500">{si} {status}</span>'
            f' · {an_str}'
            f'{"  · 📄 " + fn if fn else ""}'
            f'  · 🕐 {crd}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Stats agrégées ────────────────────────────────────────────────────────
    if sessions:
        import pandas as pd
        df_stats = pd.DataFrame([{
            "Session":       s.get("name", ""),
            "Statut":        s.get("status", ""),
            "Anomalies":     s.get("total_anomalies", 0),
            "Majeures":      s.get("major_anomalies", 0),
            "Mineures":      s.get("minor_anomalies", 0),
            "Date":          s.get("created_at", "")[:10],
        } for s in sessions])

        with st.expander("📈 Données détaillées"):
            st.dataframe(df_stats, width='stretch', hide_index=True)
