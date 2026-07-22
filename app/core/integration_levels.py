"""
Système de niveaux prérequis client — Besoin 2 (version dynamique).

Différences avec la V1 :
  - Plus AUCUNE liste de tables en dur dans ce fichier. La classification
    table -> (niveau, sous-niveau) vit dans Supabase (table `level_config`,
    éditable sans toucher au code) — voir load_level_config().
  - La détection des tables concernées par un fichier n'est plus basée sur
    le nom des onglets : elle traverse récursivement les jointures réelles
    de BC (ExecutionPlan.fields_ref), table -> fils -> fils du fils.
  - Le package_code utilisé pour explorer les champs d'une table découverte
    (ex. Vendor) N'EST PAS déduit automatiquement : il est fourni par
    l'appelant via resolve_package_code(table_id), au moment où on en a
    besoin (toi/le consultant sait quel package a été créé pour cette
    table). Si aucun package_code n'est fourni, la branche s'arrête
    proprement (marquée "chaîne non résolue"), elle ne plante pas et
    n'invente rien.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable


# ── Config niveau (dynamique — chargée depuis Supabase, rien en dur ici) ─────

@dataclass(frozen=True)
class LevelInfo:
    table_id:   int
    table_name: str
    level:      int | None       # 0 à 4, ou None = "Non classé" (détectée, pas encore classée)
    sub_level:  str | None = None
    note:       str = ""


def load_level_config(supabase_client) -> dict[int, LevelInfo]:
    """
    Charge la classification niveau/table depuis Supabase — remplace toute
    liste Python en dur. Éditable depuis une page admin ou directement en
    base, sans redéploiement de code.

    SCHÉMA REQUIS (à créer si absent — n'existe pas encore dans ton
    Supabase actuel, à confirmer) :

        CREATE TABLE level_config (
            table_id    integer PRIMARY KEY,
            table_name  text    NOT NULL,
            level       integer NOT NULL,   -- 0 à 4
            sub_level   text,               -- NULL sauf niveau 3
            note        text
        );

    NON VÉRIFIÉ : `supabase_client` suppose un client type supabase-py
    (`.table(...).select(...).execute()`). Si sessions_db.py / metadata_db.py
    utilisent un autre pattern d'accès Supabase dans ton projet, adapte
    cette fonction à ce pattern existant plutôt que d'en introduire un
    nouveau — je n'ai pas ces fichiers pour vérifier.
    """
    resp = supabase_client.table("level_config").select("*").execute()
    return {
        row["table_id"]: LevelInfo(
            table_id=row["table_id"],
            table_name=row["table_name"],
            level=row["level"],
            sub_level=row.get("sub_level"),
            note=row.get("note", ""),
        )
        for row in resp.data
    }


# ── Détection dynamique par jointures (Phase 1) ──────────────────────────────

@dataclass
class DiscoveredTable:
    table_id:       int
    chain_resolved: bool   # False = on n'a pas pu explorer SES propres refs
                           #  (pas de package_code fourni) — n'empêche pas
                           #  de vérifier si la table est remplie (Phase 2),
                           #  juste de creuser plus profond dans la chaîne.


def traverse_dependencies(
    root_plan:            "ExecutionPlan",
    build_plan_from_bc:    Callable[..., "ExecutionPlan"],  # réutilise la fonction existante d'execution_planner.py
    tenant_id:             str,
    environment:           str,
    company_id:            str,
    token:                 str,
    resolve_package_code:  Callable[[int], str | None],
    max_depth:             int = 10,
) -> dict[int, DiscoveredTable]:
    """
    Traverse récursivement les fields_ref du plan racine (le package en
    cours d'analyse) puis, pour chaque table référencée découverte, si un
    package_code est fourni par l'appelant pour CETTE table, reconstruit
    son ExecutionPlan (build_plan_from_bc, code existant, aucun nouveau
    mécanisme BC) et continue la récursion sur ses propres fields_ref.

    Anti-cycle : un `visited` empêche de re-traverser une table déjà
    rencontrée dans la chaîne, même si la taxonomie N0-N4 devrait déjà
    l'exclure par construction (N0 ne référence jamais N3, etc.) — filet
    de sécurité si une jointure BC contredit cet ordre.

    max_depth : garde-fou dur en plus du set visited, au cas où une
    donnée BC mal formée créerait une chaîne anormalement longue.

    Retourne {table_id: DiscoveredTable} — chain_resolved=False signale
    une branche où le package_code manquait, PAS une table non vérifiable :
    check_table_filled() reste utilisable sur cette table (elle ne dépend
    que du table_id, pas du package_code).
    """
    discovered: dict[int, DiscoveredTable] = {}
    visited: set[int] = set()

    def _walk(plan: "ExecutionPlan", depth: int) -> None:
        if depth > max_depth:
            return
        for _table_id, refs in plan.fields_ref.items():
            for _field_name, ref_table_id in refs.items():
                if not ref_table_id or ref_table_id in visited:
                    continue
                visited.add(ref_table_id)

                pkg_code = resolve_package_code(ref_table_id)
                if not pkg_code:
                    discovered[ref_table_id] = DiscoveredTable(ref_table_id, chain_resolved=False)
                    continue

                discovered[ref_table_id] = DiscoveredTable(ref_table_id, chain_resolved=True)
                sub_plan = build_plan_from_bc(tenant_id, environment, company_id, pkg_code, token)
                _walk(sub_plan, depth + 1)

    _walk(root_plan, 0)
    return discovered


# ── Roadmap (fusion détection + config niveau) ───────────────────────────────

@dataclass
class RoadmapEntry:
    level_info:     LevelInfo
    chain_resolved: bool = True
    status:         str = "pending"  # "pending" | "validated"
    last_check:     str | None = None  # None | "filled" | "empty" | "unknown" — motif du statut "pending", pour l'UI


def build_roadmap(
    discovered: dict[int, DiscoveredTable],
    level_config: dict[int, LevelInfo],
) -> list[RoadmapEntry]:
    """
    Fusionne les tables découvertes dynamiquement (traverse_dependencies)
    avec la classification niveau (load_level_config).

    Toute table détectée absente de level_config N'EST PAS écartée : elle
    devient une entrée de niveau spécial "Non classé" (level=None), pour
    ne jamais laisser passer une dépendance simplement parce qu'elle n'a
    pas encore été classée manuellement. Elle est :
      - toujours débloquée (is_level_unlocked la traite à part, indépendante
        de l'ordre N0-N4 puisqu'on ignore sa vraie position),
      - vérifiée par le même mécanisme BC que les autres (check_table_filled),
      - obligatoire : all_validated() exige qu'elle soit validée comme
        n'importe quelle autre entrée avant de déverrouiller la Phase 3.

    Retourne la roadmap triée : niveaux 0-4 d'abord (par niveau, sous-niveau,
    table_id), puis les entrées "Non classé" à la fin (ordre stable par
    table_id, elles ne dépendent d'aucun ordre).

    IMPORTANT : les tables de Niveau 0 (ex. G/L Account) sont TOUJOURS
    incluses, que la détection par jointures les ait trouvées ou non.
    C'est une règle métier absolue ("le plan comptable est toujours
    vérifié en premier") — elle ne peut pas dépendre du succès d'une
    traversée dynamique, qui s'arrête souvent avant d'atteindre le plan
    comptable (rarement référencé directement par les tables du package,
    plutôt à 2+ sauts via un groupe comptable). La faire dépendre de la
    détection reviendrait à violer la règle dans la majorité des cas réels.
    """
    roadmap: list[RoadmapEntry] = []
    _all_ids = dict(discovered)
    for _tid, _info in level_config.items():
        if _info.level == 0 and _tid not in _all_ids:
            _all_ids[_tid] = DiscoveredTable(table_id=_tid, chain_resolved=True)

    for table_id, disc in _all_ids.items():
        info = level_config.get(table_id)
        if info is None:
            info = LevelInfo(
                table_id=table_id,
                table_name=f"Table {table_id} (non classée)",
                level=None,
                sub_level=None,
                note="Détectée par jointure, absente de level_config — à classer, mais quand même vérifiée.",
            )
        roadmap.append(RoadmapEntry(level_info=info, chain_resolved=disc.chain_resolved))

    roadmap.sort(key=lambda e: (
        e.level_info.level if e.level_info.level is not None else 99,
        e.level_info.sub_level or "",
        e.level_info.table_id,
    ))
    return roadmap


# ── Règles de déblocage (inchangées dans leur logique) ───────────────────────

def is_level_unlocked(level: int | None, roadmap: list[RoadmapEntry]) -> bool:
    """
    N(x) débloqué seulement si tous les niveaux 0-4 < x sont validés.
    Sous-niveaux de N3 indépendants entre eux.
    N4 exige que TOUS les sous-niveaux N3 de la roadmap soient validés.

    Les entrées "Non classé" (level=None) sont toujours débloquées : on
    ignore leur position réelle dans la chaîne, donc on ne peut ni les
    faire dépendre d'un autre niveau ni faire dépendre un niveau connu
    d'elles. Elles restent malgré tout obligatoires pour all_validated().
    """
    if level is None:
        return True
    for e in roadmap:
        if e.level_info.level is not None and e.level_info.level < level and e.status != "validated":
            return False
    if level == 4:
        for e in roadmap:
            if e.level_info.level == 3 and e.status != "validated":
                return False
    return True


# ── Vérification BC (Phase 2, Mécanisme A — inchangé) ────────────────────────

def check_table_filled(profile_code: str, company_id: str, table_id: int) -> str:
    """
    Vérifie si une table de niveau contient déjà des données dans BC.
    Réutilise TEL QUEL get_reference_values_by_table_id() (Axe B,
    metadata_db.py) — ne dépend PAS du package_code, donc utilisable
    même sur une branche chain_resolved=False.

    ATTENTION (confirmé sur le vrai code, corrigé par rapport à la V1) :
    la fonction retourne un tuple (valid_codes, found), pas juste un set.
    found=True + codes vide = table interrogée avec succès, réellement
    vide côté BC (pas un échec). found=False = source injoignable, donc
    statut réellement inconnu — à ne jamais confondre avec "vide".

    Retourne :
      "filled"  : found=True et au moins un code -> niveau validable.
      "empty"   : found=True mais 0 code -> table réellement vide dans
                  BC, pas encore remplie -> niveau reste pending.
      "unknown" : found=False -> source injoignable (credentials,
                  réseau...) -> pending, mais l'UI doit distinguer ce
                  cas de "empty" pour ne pas laisser croire à l'usager
                  que la table est simplement vide alors que le check
                  a échoué techniquement.
    """
    from app.db.metadata_db import get_reference_values_by_table_id

    try:
        codes, found = get_reference_values_by_table_id(profile_code, company_id, table_id)
    except Exception:
        return "unknown"
    if not found:
        return "unknown"
    return "filled" if codes else "empty"


def refresh_roadmap(profile_code: str, company_id: str, roadmap: list[RoadmapEntry]) -> list[RoadmapEntry]:
    """
    Bouton "Revérifier" — relance le check BC pour chaque entrée débloquée
    et non validée. Seul "filled" fait passer le statut à "validated" ;
    "empty" et "unknown" laissent le niveau "pending" mais avec un motif
    différent (à afficher distinctement côté UI : "pas encore rempli"
    vs "vérification impossible pour le moment").
    """
    for e in roadmap:
        if e.status == "validated":
            continue
        if not is_level_unlocked(e.level_info.level, roadmap):
            continue
        result = check_table_filled(profile_code, company_id, e.level_info.table_id)
        e.last_check = result
        if result == "filled":
            e.status = "validated"
    return roadmap


def all_validated(roadmap: list[RoadmapEntry]) -> bool:
    return all(e.status == "validated" for e in roadmap)