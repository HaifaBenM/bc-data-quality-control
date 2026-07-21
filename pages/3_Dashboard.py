import streamlit as st
import pandas as pd
from app.core.auth import require_role, is_consultant
from app.db.sessions_db import get_all_sessions, STATUS_COLORS, STATUS_ICONS

require_role()

active_client      = st.session_state.get("active_client", "")
active_client_name = st.session_state.get("active_client_name", "")

st.markdown(f"# 📊 Dashboard — {active_client_name}")
st.caption(f"Client : **{active_client_name}** ({active_client})")
st.markdown("---")

sessions = get_all_sessions(profile_code=active_client)

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


def render_charts(session_list: list, key_prefix: str, show_by_client: bool = False) -> None:
    """
    Rend les graphiques réactifs à partir d'une liste de sessions déjà
    chargée (pas de nouvel appel réseau ici — la liste est passée en
    argument pour pouvoir être réutilisée telle quelle par la vue client
    scopée et par la vue globale consultant).

    Graphiques natifs Streamlit (st.bar_chart / st.line_chart) — pas de
    dépendance supplémentaire (plotly/altair) à ajouter à requirements.txt.
    """
    if not session_list:
        st.info("Aucune donnée à afficher pour le moment.")
        return

    df = pd.DataFrame([{
        "date":            (s.get("created_at", "") or "")[:10],
        "profile_code":    s.get("profile_code", ""),
        "status":          s.get("status", "Nouvelle"),
        "total_anomalies": s.get("total_anomalies", 0) or 0,
        "major_anomalies": s.get("major_anomalies", 0) or 0,
        "minor_anomalies": s.get("minor_anomalies", 0) or 0,
    } for s in session_list])
    df = df[df["date"] != ""]

    cg1, cg2 = st.columns(2)

    with cg1:
        st.markdown("**📈 Évolution des anomalies dans le temps**")
        if df.empty:
            st.caption("Pas de date exploitable sur ces sessions.")
        else:
            evol = (
                df.groupby("date")[["major_anomalies", "minor_anomalies"]]
                .sum()
                .rename(columns={"major_anomalies": "Majeures", "minor_anomalies": "Mineures"})
                .sort_index()
            )
            st.line_chart(evol, use_container_width=True)

    with cg2:
        st.markdown("**🔴🟠 Répartition majeures / mineures**")
        repartition = pd.DataFrame({
            "Nombre": [df["major_anomalies"].sum(), df["minor_anomalies"].sum()]
        }, index=["Majeures", "Mineures"])
        st.bar_chart(repartition, use_container_width=True)

    cg3, cg4 = st.columns(2)

    with cg3:
        st.markdown("**📋 Sessions par statut**")
        by_status = df["status"].value_counts().rename("Nombre")
        st.bar_chart(by_status, use_container_width=True)

    if show_by_client:
        with cg4:
            st.markdown("**👥 Sessions par client**")
            by_client = df["profile_code"].value_counts().rename("Nombre")
            st.bar_chart(by_client, use_container_width=True)


if not sessions:
    st.info("Aucune session pour ce client. Lancez une analyse depuis **Sessions Intégration** ou **Packages**.")
else:
    render_charts(sessions, key_prefix="client")
    st.markdown("---")

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

    if sessions:
        df_stats = pd.DataFrame([{
            "Session":   s.get("name", ""),
            "Statut":    s.get("status", ""),
            "Anomalies": s.get("total_anomalies", 0),
            "Majeures":  s.get("major_anomalies", 0),
            "Mineures":  s.get("minor_anomalies", 0),
            "Date":      s.get("created_at", "")[:10],
        } for s in sessions])

        with st.expander("📈 Données détaillées"):
            st.dataframe(df_stats, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════════════
# VUE GLOBALE — réservée aux consultants, tous clients confondus
# ════════════════════════════════════════════════════════════════════════════
if is_consultant():
    st.markdown("---")
    st.markdown("## 🌐 Vue globale — tous clients")
    st.caption("Réservée aux consultants — agrège les sessions de tous les clients, indépendamment du client actif.")

    all_sessions = get_all_sessions()  # sans profile_code = toutes les sessions

    gcol1, gcol2, gcol3, gcol4 = st.columns(4)
    g_total  = len(all_sessions)
    g_active = sum(1 for s in all_sessions if s.get("status") not in ("Terminée",))
    g_major  = sum(s.get("major_anomalies", 0) for s in all_sessions)
    g_ready  = sum(1 for s in all_sessions if s.get("major_anomalies", 0) == 0 and s.get("status") == "Terminée")
    gcol1.metric("Sessions totales (tous clients)", g_total)
    gcol2.metric("En cours",                         g_active)
    gcol3.metric("Anomalies majeures",               g_major)
    gcol4.metric("Fichiers prêts BC",                g_ready)

    st.markdown("---")
    render_charts(all_sessions, key_prefix="global", show_by_client=True)