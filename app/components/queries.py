"""Requêtes SQL partagées entre les pages Streamlit.

Centralise les patterns dupliqués (listes joueurs, tournois, dernier match) pour
éviter la dérive entre pages. Chaque fonction est cachée par `(cache_key, ...)`
où `cache_key` est le `data_key()` issu de `init_app()` : racine du projet **et**
empreinte des parquets. Dès que l'ingestion quotidienne réécrit les données,
la clé change et les résultats cachés sont recalculés — sans redémarrage.

Note : ce module est dans `app/components/` plutôt qu'`app/db/` pour éviter
le conflit de namespace avec `src/db/duckdb_session` (déjà importé sous `db.*`).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from components._bootstrap import connection_for_key


def _shared_connection(conn_key: str) -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB partagée (réutilise le cache de :func:`init_app`)."""
    return connection_for_key(conn_key)


@st.cache_data(ttl=3600, show_spinner=False)
def player_options(cache_key: str, circuit: str) -> pd.DataFrame:
    """Retourne les joueurs d'un circuit avec leur code pays IOC.

    Fusion de l'ancien `_player_options` (1_Joueurs) et `_player_options_circuit`
    (2_Face_a_Face). `circuit` peut valoir 'ATP', 'WTA' ou 'Tous'.

    **Seuls les joueurs ayant réellement disputé un match sont proposés.** Le
    fichier joueurs de Sackmann contient ~122 800 entrées (juniors, qualifiés,
    homonymes) contre ~3 500 ayant joué depuis 2010 : sans ce filtre, 97 % des
    noms de la liste n'ont ni statistiques ni historique Elo, et la page affiche
    « Historique Elo indisponible » dès l'ouverture.

    Args:
        cache_key: Clé `data_key()` (racine + empreinte des données).
        circuit: 'ATP', 'WTA' ou 'Tous'.

    Returns:
        DataFrame avec colonnes `player_id`, `full_name`, `ioc`, trié par nom.
    """
    conn = _shared_connection(cache_key)
    try:
        cols = conn.execute("DESCRIBE v_players").df()["column_name"].tolist()
    except duckdb.Error:
        return pd.DataFrame(columns=["player_id", "full_name", "ioc"])
    pays_col = "ioc" if "ioc" in cols else ("country_code" if "country_code" in cols else "NULL")
    where_circuit = "" if circuit == "Tous" else "WHERE p.circuit = ?"
    # Le filtre par circuit s'applique aussi aux matchs : un joueur « BOTH » ne
    # doit pas remonter dans la liste ATP s'il n'a joué que sur le circuit WTA.
    where_matchs = "" if circuit == "Tous" else "WHERE circuit = ?"
    sql = f"""
        WITH joueurs_actifs AS (
            SELECT DISTINCT player_id FROM (
                SELECT winner_id AS player_id, circuit FROM v_matches
                UNION ALL
                SELECT loser_id AS player_id, circuit FROM v_matches
            ) {where_matchs}
        )
        SELECT p.player_id,
               TRIM(CONCAT(COALESCE(ANY_VALUE(p.name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(p.name_last), ''))) AS full_name,
               ANY_VALUE({pays_col}) AS ioc
        FROM v_players p
        JOIN joueurs_actifs a ON p.player_id = a.player_id
        {where_circuit}
        GROUP BY p.player_id
        HAVING TRIM(CONCAT(COALESCE(ANY_VALUE(p.name_first), ''),
                           ' ',
                           COALESCE(ANY_VALUE(p.name_last), ''))) <> ''
        ORDER BY full_name
    """
    try:
        # Deux placeholders quand un circuit est choisi : filtre matchs + filtre joueurs.
        params = [] if circuit == "Tous" else [circuit, circuit]
        return conn.execute(sql, params).df()
    except duckdb.Error:
        return pd.DataFrame(columns=["player_id", "full_name", "ioc"])


@st.cache_data(ttl=3600, show_spinner=False)
def tournaments_for_circuit(cache_key: str, circuit: str) -> list[str]:
    """Retourne la liste triée des tournois distincts pour un circuit donné."""
    conn = _shared_connection(cache_key)
    try:
        if circuit == "Tous":
            df = conn.execute(
                "SELECT DISTINCT tourney_name FROM v_matches ORDER BY tourney_name"
            ).df()
        else:
            df = conn.execute(
                "SELECT DISTINCT tourney_name FROM v_matches WHERE circuit = ? ORDER BY tourney_name",
                [circuit],
            ).df()
        return df["tourney_name"].tolist()
    except duckdb.Error:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def latest_match_per_circuit(cache_key: str, circuit: str) -> dict:
    """Retourne le tournoi et la date du dernier match d'un circuit."""
    conn = _shared_connection(cache_key)
    try:
        row = conn.execute(
            """
            SELECT tourney_name, tourney_date
            FROM v_matches
            WHERE circuit = ?
            ORDER BY tourney_date DESC
            LIMIT 1
            """,
            [circuit],
        ).fetchone()
        if not row:
            return {"tourney_name": "—", "tourney_date": None}
        return {"tourney_name": row[0], "tourney_date": row[1]}
    except duckdb.Error:
        return {"tourney_name": "—", "tourney_date": None}


# ─────────────────────────────────────────────────────────────────────────────
# Requêtes des pages Accueil / Résultats / Classements / Joueurs
# ─────────────────────────────────────────────────────────────────────────────

#: Rang chronologique des tours (cf. tennis_analytics.transformation.ordering).
ROUND_ORDER_SQL = """
    CASE round
        WHEN 'Q1' THEN 0 WHEN 'Q2' THEN 1 WHEN 'Q3' THEN 2 WHEN 'Q4' THEN 3
        WHEN 'R128' THEN 10 WHEN 'R64' THEN 11 WHEN 'R32' THEN 12 WHEN 'R16' THEN 13
        WHEN 'RR' THEN 14 WHEN 'QF' THEN 15 WHEN 'SF' THEN 16 WHEN 'BR' THEN 17
        WHEN 'F' THEN 18 ELSE 9
    END
"""

#: Jour du match : date réelle (sources récentes) sinon début du tournoi.
PLAYED_ON_SQL = "COALESCE(match_date, tourney_date)"

#: Colonnes Elo autorisées (allowlist avant interpolation).
ELO_COLUMNS = ("elo_global", "elo_hard", "elo_clay", "elo_grass")

#: Fenêtre d'activité : un joueur sans match depuis plus longtemps n'est pas classé.
ACTIVE_DAYS = 365


def _circuit_params(circuit: str) -> tuple[str, list[str]]:
    """Clause `AND circuit = ?` et paramètres, ou rien pour « Tous »."""
    if circuit in ("ATP", "WTA"):
        return "AND circuit = ?", [circuit]
    return "", []


def _has_column(conn: duckdb.DuckDBPyConnection, view: str, column: str) -> bool:
    try:
        cols = conn.execute(f"DESCRIBE {view}").df()["column_name"].tolist()
    except duckdb.Error:
        return False
    return column in cols


@st.cache_data(ttl=3600, show_spinner=False)
def elo_ranking(
    cache_key: str,
    circuit: str,
    surface_col: str = "elo_global",
    limit: int = 20,
    include_inactive: bool = False,
) -> pd.DataFrame:
    """Classement Elo d'un circuit, avec forme récente et classement officiel.

    Par défaut, seuls les joueurs ayant joué dans les 12 derniers mois (par
    rapport au dernier match connu) sont classés : sans ce filtre, des joueurs
    retraités (Federer, Söderling…) apparaissent dans le top.

    Returns:
        Colonnes : rang, player_id, joueur, ioc, elo_global, elo_hard, elo_clay,
        elo_grass, forme (5 derniers, du plus ancien au plus récent),
        classement officiel (`rang_atp_wta`), last_match_date.
    """
    if surface_col not in ELO_COLUMNS:
        raise ValueError(f"Colonne Elo invalide : {surface_col!r}")
    conn = _shared_connection(cache_key)
    activity = (
        ""
        if include_inactive
        else f"""AND strptime(CAST(e.last_match_date AS VARCHAR), '%Y%m%d')
                 >= (SELECT ref FROM ref_date) - INTERVAL {ACTIVE_DAYS} DAY"""
    )
    sql = f"""
        WITH ref_date AS (
            SELECT strptime(CAST(MAX(tourney_date) AS VARCHAR), '%Y%m%d') AS ref FROM v_matches
        ),
        joueurs AS (
            SELECT player_id, circuit, ioc,
                   TRIM(CONCAT(COALESCE(name_first, ''), ' ', COALESCE(name_last, ''))) AS joueur
            FROM v_players
            WHERE circuit = ?
        ),
        resultats AS (
            SELECT pid, res, ROW_NUMBER() OVER (
                       PARTITION BY pid ORDER BY jour DESC, tour DESC) AS rn
            FROM (
                SELECT winner_id AS pid, 'V' AS res, {PLAYED_ON_SQL} AS jour,
                       {ROUND_ORDER_SQL} AS tour
                FROM v_matches WHERE circuit = ?
                UNION ALL
                SELECT loser_id, 'D', {PLAYED_ON_SQL}, {ROUND_ORDER_SQL}
                FROM v_matches WHERE circuit = ?
            )
        ),
        forme AS (
            SELECT pid, STRING_AGG(res, ' ' ORDER BY rn DESC) AS forme
            FROM resultats WHERE rn <= 5 GROUP BY pid
        ),
        officiel AS (
            SELECT player, arg_max(rank, ranking_date) AS rang_officiel,
                   MAX(ranking_date) AS date_officiel
            FROM v_rankings WHERE circuit = ? GROUP BY player
        )
        SELECT
            ROW_NUMBER() OVER (ORDER BY e.{surface_col} DESC) AS rang,
            e.player_id, j.joueur, j.ioc,
            ROUND(e.elo_global) AS elo_global, ROUND(e.elo_hard) AS elo_hard,
            ROUND(e.elo_clay) AS elo_clay, ROUND(e.elo_grass) AS elo_grass,
            f.forme,
            CASE WHEN o.date_officiel >= (
                     SELECT CAST(strftime(ref - INTERVAL 60 DAY, '%Y%m%d') AS INTEGER)
                     FROM ref_date)
                 THEN o.rang_officiel END AS rang_officiel,
            e.last_match_date
        FROM v_elo_latest e
        JOIN joueurs j ON e.player_id = j.player_id
        LEFT JOIN forme f ON f.pid = e.player_id
        LEFT JOIN officiel o ON o.player = e.player_id
        WHERE e.{surface_col} IS NOT NULL AND j.joueur <> '' {activity}
        ORDER BY e.{surface_col} DESC
        LIMIT ?
    """
    try:
        return conn.execute(sql, [circuit, circuit, circuit, circuit, limit]).df()
    except duckdb.Error:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def top_player_ids(cache_key: str, circuit: str, n: int = 2) -> list[int]:
    """Identifiants des `n` meilleurs joueurs Elo actifs (sélections par défaut)."""
    circuits = ("ATP", "WTA") if circuit not in ("ATP", "WTA") else (circuit,)
    ids: list[int] = []
    for circ in circuits:
        frame = elo_ranking(cache_key, circ, "elo_global", n)
        ids.extend(int(x) for x in frame.get("player_id", []))
        if len(ids) >= n:
            break
    return ids[:n]


@st.cache_data(ttl=900, show_spinner=False)
def recent_results(cache_key: str, circuit: str, limit: int = 30) -> pd.DataFrame:
    """Derniers matchs joués (toutes sources), du plus récent au plus ancien."""
    conn = _shared_connection(cache_key)
    clause, params = _circuit_params(circuit)
    source = "source" if _has_column(conn, "v_matches", "source") else "'sackmann'"
    match_date = "match_date" if _has_column(conn, "v_matches", "match_date") else "NULL"
    sql = f"""
        SELECT COALESCE({match_date}, tourney_date) AS jour, circuit, tourney_name, tourney_id,
               round, winner_name, winner_ioc, loser_name, loser_ioc, score,
               {source} AS source, {ROUND_ORDER_SQL} AS tour
        FROM v_matches
        WHERE 1=1 {clause}
        ORDER BY jour DESC, tourney_id, tour DESC
        LIMIT ?
    """
    try:
        return conn.execute(sql, [*params, limit]).df()
    except duckdb.Error:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def recent_tournaments(cache_key: str, circuit: str, limit: int = 8) -> pd.DataFrame:
    """Derniers tournois (en cours ou terminés) avec vainqueur et état d'avancement.

    Returns:
        Colonnes : tourney_id, tourney_name, circuit, tourney_level, surface,
        debut, fin, matchs, provisoires, dernier_tour, vainqueur, finaliste,
        score_finale.
    """
    conn = _shared_connection(cache_key)
    clause, params = _circuit_params(circuit)
    source = "source" if _has_column(conn, "v_matches", "source") else "'sackmann'"
    match_date = "match_date" if _has_column(conn, "v_matches", "match_date") else "NULL"
    sql = f"""
        WITH m AS (
            SELECT *, COALESCE({match_date}, tourney_date) AS jour,
                   {ROUND_ORDER_SQL} AS tour, {source} AS src
            FROM v_matches
            WHERE tourney_level NOT IN ('D', 'W') {clause}
        ),
        t AS (
            SELECT tourney_id, ANY_VALUE(tourney_name) AS tourney_name,
                   ANY_VALUE(circuit) AS circuit, ANY_VALUE(tourney_level) AS tourney_level,
                   ANY_VALUE(surface) AS surface, MIN(tourney_date) AS debut,
                   MAX(jour) AS fin, COUNT(*) AS matchs,
                   COUNT(*) FILTER (WHERE src = 'espn') AS provisoires,
                   arg_max(round, tour) AS dernier_tour
            FROM m GROUP BY tourney_id
        ),
        finales AS (
            SELECT tourney_id, winner_name AS vainqueur, loser_name AS finaliste,
                   score AS score_finale
            FROM m WHERE round = 'F'
        )
        SELECT t.*, f.vainqueur, f.finaliste, f.score_finale
        FROM t LEFT JOIN finales f USING (tourney_id)
        ORDER BY t.debut DESC, t.tourney_level, t.tourney_name
        LIMIT ?
    """
    try:
        return conn.execute(sql, [*params, limit]).df()
    except duckdb.Error:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def tournament_matches(cache_key: str, tourney_id: str) -> pd.DataFrame:
    """Tous les matchs d'une édition de tournoi, de la finale au premier tour."""
    conn = _shared_connection(cache_key)
    source = "source" if _has_column(conn, "v_matches", "source") else "'sackmann'"
    match_date = "match_date" if _has_column(conn, "v_matches", "match_date") else "NULL"
    sql = f"""
        SELECT COALESCE({match_date}, tourney_date) AS jour, round, winner_name, winner_ioc,
               loser_name, loser_ioc, score, {source} AS source, {ROUND_ORDER_SQL} AS tour
        FROM v_matches WHERE tourney_id = ?
        ORDER BY tour DESC, jour DESC
    """
    try:
        return conn.execute(sql, [tourney_id]).df()
    except duckdb.Error:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def season_champions(cache_key: str, circuit: str, year: int) -> pd.DataFrame:
    """Vainqueurs des tournois d'une saison (hors Coupe Davis / ITF)."""
    conn = _shared_connection(cache_key)
    clause, params = _circuit_params(circuit)
    sql = f"""
        SELECT tourney_date AS debut, circuit, tourney_name, tourney_level, surface,
               winner_name AS vainqueur, winner_ioc, loser_name AS finaliste, score
        FROM v_matches
        WHERE round = 'F' AND tourney_level NOT IN ('D', 'W')
          AND tourney_date BETWEEN ? AND ? {clause}
        ORDER BY tourney_date DESC, tourney_name
    """
    try:
        return conn.execute(sql, [year * 10000 + 101, year * 10000 + 1231, *params]).df()
    except duckdb.Error:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def player_elo(cache_key: str, player_id: int) -> pd.DataFrame:
    """Dernier état Elo d'un joueur (global + surfaces)."""
    conn = _shared_connection(cache_key)
    try:
        return conn.execute(
            """
            SELECT elo_global, elo_hard, elo_clay, elo_grass, last_match_date
            FROM v_elo_latest WHERE player_id = ?
            """,
            [player_id],
        ).df()
    except duckdb.Error:
        return pd.DataFrame()
