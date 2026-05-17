"""Widgets Streamlit réutilisables (sélecteurs, formatage FR)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
import streamlit as st

# ── Mapping codes IOC (3 lettres) → ISO 3166-1 alpha-2 (2 lettres) ───────────
# Les emojis drapeaux sont composés à partir des 2 lettres ISO via les Regional
# Indicator Symbols (caractères Unicode 🇦-🇿).
_IOC_TO_ISO2: dict[str, str] = {
    # Top tennis nations
    "USA": "US",
    "FRA": "FR",
    "ESP": "ES",
    "ITA": "IT",
    "GER": "DE",
    "GBR": "GB",
    "AUS": "AU",
    "RUS": "RU",
    "SRB": "RS",
    "SUI": "CH",
    "ARG": "AR",
    "BRA": "BR",
    "CAN": "CA",
    "CHN": "CN",
    "JPN": "JP",
    "CRO": "HR",
    "POL": "PL",
    "BEL": "BE",
    "NED": "NL",
    "SWE": "SE",
    "AUT": "AT",
    "CZE": "CZ",
    "SVK": "SK",
    "HUN": "HU",
    "ROU": "RO",
    "BUL": "BG",
    "GRE": "GR",
    "POR": "PT",
    "DEN": "DK",
    "FIN": "FI",
    "NOR": "NO",
    "IRL": "IE",
    "ISR": "IL",
    "TUR": "TR",
    "UKR": "UA",
    "BLR": "BY",
    "KAZ": "KZ",
    "GEO": "GE",
    "ARM": "AM",
    "MDA": "MD",
    "EST": "EE",
    "LAT": "LV",
    "LTU": "LT",
    "SLO": "SI",
    "BIH": "BA",
    "MKD": "MK",
    "MNE": "ME",
    "ALB": "AL",
    "CYP": "CY",
    "MLT": "MT",
    "LUX": "LU",
    "ISL": "IS",
    "MEX": "MX",
    "CHI": "CL",
    "COL": "CO",
    "PER": "PE",
    "VEN": "VE",
    "URU": "UY",
    "PAR": "PY",
    "BOL": "BO",
    "ECU": "EC",
    "DOM": "DO",
    "PUR": "PR",
    "CUB": "CU",
    "JAM": "JM",
    "BAH": "BS",
    "TRI": "TT",
    "CRC": "CR",
    "GUA": "GT",
    "SLV": "SV",
    "PAN": "PA",
    "HON": "HN",
    "RSA": "ZA",
    "MAR": "MA",
    "TUN": "TN",
    "ALG": "DZ",
    "EGY": "EG",
    "NGR": "NG",
    "KEN": "KE",
    "CIV": "CI",
    "SEN": "SN",
    "CMR": "CM",
    "GHA": "GH",
    "ZIM": "ZW",
    "IND": "IN",
    "PAK": "PK",
    "BAN": "BD",
    "SRI": "LK",
    "THA": "TH",
    "VIE": "VN",
    "PHI": "PH",
    "INA": "ID",
    "MAS": "MY",
    "SGP": "SG",
    "TPE": "TW",
    "HKG": "HK",
    "KOR": "KR",
    "PRK": "KP",
    "UAE": "AE",
    "KSA": "SA",
    "QAT": "QA",
    "KUW": "KW",
    "BRN": "BH",
    "OMA": "OM",
    "JOR": "JO",
    "LBN": "LB",
    "SYR": "SY",
    "IRQ": "IQ",
    "IRI": "IR",
    "AFG": "AF",
    "NZL": "NZ",
    "FIJ": "FJ",
}


def country_flag(ioc_code: str | None) -> str:
    """Convertit un code pays IOC (3 lettres) en emoji drapeau Unicode.

    Args:
        ioc_code: Code IOC à 3 lettres (ex : 'FRA', 'ESP', 'USA').

    Returns:
        Emoji drapeau (ex : '🇫🇷') ou code original si pas de mapping connu.
    """
    if not ioc_code or ioc_code in ("—", "nan", "None", ""):
        return "—"
    code = str(ioc_code).strip().upper()
    iso2 = _IOC_TO_ISO2.get(code)
    if not iso2:
        return code  # fallback : on garde le code IOC visible
    # Construit l'emoji en combinant deux Regional Indicator Symbols
    # 'A' = U+1F1E6, donc 'A' + decalage vers la lettre cible
    return "".join(chr(ord(c) - ord("A") + 0x1F1E6) for c in iso2)


def country_flag_with_code(ioc_code: str | None) -> str:
    """Retourne 'drapeau + code IOC' (ex : '🇫🇷 FRA') pour affichage tableau."""
    if not ioc_code or ioc_code in ("—", "nan", "None", ""):
        return "—"
    flag = country_flag(ioc_code)
    code = str(ioc_code).strip().upper()
    if flag == code:  # pas de mapping trouvé
        return code
    return f"{flag} {code}"


def format_date_dd_mm_yyyy(value: int | float | None) -> str:
    """Formate un entier `YYYYMMDD` en `DD/MM/YYYY`."""
    if value is None:
        return ""
    try:
        text = f"{int(value):08d}"
        return datetime.strptime(text, "%Y%m%d").strftime("%d/%m/%Y")
    except ValueError:
        return str(value)


def format_percent(value: float | None, digits: int = 1) -> str:
    """Formate un ratio [0,1] en pourcentage avec virgule décimale."""
    if value is None:
        return ""
    pct = value * 100.0
    return f"{pct:.{digits}f}".replace(".", ",") + " %"


def load_player_options(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Retourne la liste des joueurs disponibles (id + nom)."""
    try:
        frame = connection.execute(
            """
            SELECT player_id, full_name
            FROM v_player_names
            WHERE TRIM(full_name) <> ''
            ORDER BY full_name;
            """
        ).df()
        if not frame.empty:
            return frame.drop_duplicates(subset=["full_name"])
    except duckdb.Error:
        pass
    frame = connection.execute(
        """
        SELECT DISTINCT winner_id AS player_id, winner_name AS full_name
        FROM v_matches
        ORDER BY full_name;
        """
    ).df()
    return frame.drop_duplicates(subset=["full_name"])


def load_active_players(
    connection: duckdb.DuckDBPyConnection,
    circuit: str | None = None,
    min_matches: int = 10,
) -> pd.DataFrame:
    """Retourne les joueurs ayant disputé au moins `min_matches` matchs.

    Pré-filtre la liste pour rendre la recherche utilisable (sinon plus de
    100k joueurs Sackmann incluent des juniors et qualifiés inconnus).

    Args:
        connection: Connexion DuckDB active.
        circuit: 'ATP', 'WTA' ou None ('Tous').
        min_matches: Seuil minimum de matchs joués (winner_id + loser_id).

    Returns:
        DataFrame avec player_id, full_name, ioc, total_matches, last_match_date.
    """
    circuit_clause = ""
    params: list[Any] = [min_matches]
    if circuit in ("ATP", "WTA"):
        circuit_clause = "AND m.circuit = ?"
        params.insert(0, circuit)

    sql = f"""
        WITH counts AS (
            SELECT player_id, COUNT(*) AS total_matches, MAX(tourney_date) AS last_match_date
            FROM (
                SELECT winner_id AS player_id, tourney_date, circuit FROM v_matches
                UNION ALL
                SELECT loser_id  AS player_id, tourney_date, circuit FROM v_matches
            ) m
            WHERE 1=1 {circuit_clause}
            GROUP BY player_id
            HAVING COUNT(*) >= ?
        )
        SELECT
            c.player_id,
            TRIM(CONCAT(COALESCE(ANY_VALUE(p.name_first), ''), ' ',
                        COALESCE(ANY_VALUE(p.name_last), ''))) AS full_name,
            ANY_VALUE(p.ioc) AS ioc,
            c.total_matches,
            c.last_match_date
        FROM counts c
        LEFT JOIN v_players p ON c.player_id = p.player_id
        GROUP BY c.player_id, c.total_matches, c.last_match_date
        HAVING TRIM(full_name) <> ''
        ORDER BY full_name
    """
    try:
        return connection.execute(sql, params).df()
    except duckdb.Error:
        return pd.DataFrame(
            columns=["player_id", "full_name", "ioc", "total_matches", "last_match_date"]
        )


def _is_valid_player_name(name: str) -> bool:
    """Filtre les noms de joueurs incomplets ou corrompus.

    Critères d'exclusion :
    - Vide ou trop court (< 4 caractères)
    - Contient un point d'interrogation (donnée corrompue Sackmann : `?? Baillie`)
    - Contient au moins un mot d'une seule lettre, type `A Dupont` (initiale isolée
      sans prénom complet — typique des matchs qualifiants où Sackmann n'a pas
      l'identité complète)
    """
    if not name or len(name) < 4 or "?" in name:
        return False
    parts = [p for p in name.split() if p]
    if len(parts) < 2:
        # Nom mononyme accepté seulement s'il fait >= 4 lettres (cas joueurs uniques)
        return len(name) >= 4
    # Au moins 2 mots : tous doivent faire >= 2 lettres
    return all(len(p) >= 2 for p in parts)


def disambiguate_player_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute une colonne `label` unique par joueur pour les selectbox.

    - Filtre les noms vides, trop courts, avec '?', ou avec initiale isolée
      (ex : `A Dupont`, `?? Baillie`).
    - Ajoute le code pays IOC entre parenthèses pour les homonymes : `John Smith (USA)`.
    - Si même les `(IOC)` ne suffisent pas (joueurs vraiment indistinguables),
      ajoute le `player_id` en suffixe pour garantir l'unicité du label.

    Args:
        df: DataFrame avec colonnes `player_id`, `full_name` et optionnellement `ioc`/`pays`.

    Returns:
        Le DataFrame avec une colonne `label` unique, filtré et trié par label.
    """
    if df.empty or "full_name" not in df.columns:
        return df.assign(label=df.get("full_name", []))

    # Détecter la colonne pays (selon schéma)
    pays_col = None
    for candidate in ("ioc", "pays", "country_code"):
        if candidate in df.columns:
            pays_col = candidate
            break

    out = df.copy()
    out["full_name"] = out["full_name"].astype(str).str.strip()
    # Filtre noms invalides (initiales isolées, '?', trop courts)
    out = out[out["full_name"].apply(_is_valid_player_name)]

    if pays_col:
        out["_pays"] = out[pays_col].fillna("").astype(str).str.strip().str.upper()
    else:
        out["_pays"] = ""

    # Étape 1 : ajouter (IOC) pour les homonymes
    name_counts = out["full_name"].value_counts()
    duplicates = set(name_counts[name_counts > 1].index)

    def _label_with_country(row: pd.Series) -> str:
        name = row["full_name"]
        if name in duplicates and row["_pays"]:
            return f"{name} ({row['_pays']})"
        return name

    out["label"] = out.apply(_label_with_country, axis=1)

    # Étape 2 : si encore des doublons, ajouter #player_id pour garantir l'unicité
    label_counts = out["label"].value_counts()
    still_duplicate = set(label_counts[label_counts > 1].index)
    if still_duplicate:
        out.loc[out["label"].isin(still_duplicate), "label"] = (
            out.loc[out["label"].isin(still_duplicate), "label"]
            + " #"
            + out.loc[out["label"].isin(still_duplicate), "player_id"].astype(str)
        )

    return out.drop(columns=["_pays"]).sort_values("label").reset_index(drop=True)


def player_selectbox(
    label: str,
    options: pd.DataFrame,
    key: str,
    *,
    help_text: str | None = "💡 Tapez pour rechercher",
    placeholder: str = "Rechercher un joueur…",
    default_index: int = 0,
) -> int | None:
    """Sélecteur Streamlit searchable basé sur une liste de joueurs.

    Streamlit selectbox supporte nativement la recherche par frappe clavier ;
    on expose juste un placeholder et un help_text pour le signaler à l'utilisateur.

    Args:
        label: Libellé affiché au-dessus du selectbox.
        options: DataFrame avec au moins `player_id` et `full_name` (+ optionnel `ioc`).
        key: Clé Streamlit pour state.
        help_text: Tooltip affiché à côté du label (None pour le retirer).
        placeholder: Texte affiché quand rien n'est sélectionné (Streamlit 1.30+).
        default_index: Index par défaut (0 = premier joueur après tri alphabétique).

    Returns:
        `player_id` sélectionné, ou None si la liste est vide.
    """
    if options.empty:
        st.warning("Aucun joueur disponible : lancez l'ingestion pour construire les parquets.")
        return None

    if "label" not in options.columns:
        options = disambiguate_player_labels(options)
        if options.empty:
            st.warning("Aucun joueur valide disponible.")
            return None

    mapping = dict(zip(options["label"], options["player_id"], strict=False))
    labels = list(mapping.keys())
    choice = st.selectbox(
        label,
        labels,
        index=min(default_index, len(labels) - 1),
        key=key,
        help=help_text,
        placeholder=placeholder,
    )
    return int(mapping[choice])


def query_dataframe(
    connection: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None
) -> pd.DataFrame:
    """Exécute une requête SQL et retourne un DataFrame pandas."""
    if params:
        return connection.execute(sql, params).df()
    return connection.execute(sql).df()


def safe_scalar(
    connection: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any] | None = None,
    default: Any = None,
) -> Any:
    """Exécute une requête scalaire et retourne `default` en cas d'erreur."""
    try:
        row = connection.execute(sql, params or []).fetchone()
        return row[0] if row else default
    except duckdb.Error:
        return default


def format_elo(value: float | None) -> str:
    """Formate un rating Elo en entier arrondi (ex : 1847).

    Tolère les NaN, None et valeurs non numériques en retournant '—'.
    """
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "—"
    import math

    if math.isnan(f):
        return "—"
    return f"{int(round(f))}"


_ALLOWED_CIRCUITS = frozenset({"ATP", "WTA", "Tous", "TOUS", "all", "ALL", ""})

# Liste canonique des circuits proposés dans les selectbox.
# `Tous` en premier : valeur par défaut cohérente entre toutes les pages.
CIRCUITS: tuple[str, ...] = ("Tous", "ATP", "WTA")


def circuit_selectbox(
    label: str = "Circuit",
    *,
    default: str = "Tous",
    key: str | None = None,
    include_all: bool = True,
) -> str:
    """Selectbox circuit unifié et cohérent entre toutes les pages.

    Args:
        label: Libellé affiché (par défaut "Circuit").
        default: Valeur initiale parmi `CIRCUITS`.
        key: Clé Streamlit (auto si None).
        include_all: Si False, retire 'Tous' (cas pages où c'est exclusif ATP/WTA).

    Returns:
        Valeur sélectionnée, garantie dans l'allowlist.
    """
    options: tuple[str, ...] = (
        CIRCUITS if include_all else tuple(c for c in CIRCUITS if c != "Tous")
    )
    if default not in options:
        default = options[0]
    return st.sidebar.selectbox(label, options, index=options.index(default), key=key)


def circuit_filter_sql(circuit: str) -> str:
    """Génère une clause SQL WHERE pour filtrer par circuit (ATP/WTA).

    Sécurité : la valeur d'entrée est validée contre une allowlist stricte
    avant interpolation. Toute valeur hors-allowlist lève ValueError pour
    interdire toute injection SQL même accidentelle.

    Args:
        circuit: 'ATP', 'WTA' ou 'Tous'/'TOUS'/'all'/'' (clause vide).

    Returns:
        Clause SQL `AND circuit = 'ATP'` (ou vide). Sûre à concaténer.

    Raises:
        ValueError: si `circuit` n'est pas dans l'allowlist.
    """
    if circuit not in _ALLOWED_CIRCUITS:
        raise ValueError(
            f"Circuit invalide: {circuit!r}. Valeurs autorisées: {sorted(_ALLOWED_CIRCUITS)}"
        )
    if circuit in ("ATP", "WTA"):
        return f"AND circuit = '{circuit}'"
    return ""


def inject_global_css() -> None:
    """Injecte le CSS global responsive tennis (à appeler une fois par page)."""
    st.markdown(
        """
        <style>
        /* ── Anti-débordement horizontal global ─────────────────────────── */
        html, body, [data-testid="stAppViewContainer"], .main, .stApp {
            overflow-x: hidden !important;
            max-width: 100vw !important;
        }

        /* ── Charts Plotly : 100% largeur + hauteur minimale ─────────────── */
        .js-plotly-plot, .plotly, .plotly-graph-div {
            max-width: 100% !important;
            width: 100% !important;
        }
        [data-testid="stPlotlyChart"] {
            max-width: 100% !important;
            overflow: hidden !important;
        }

        /* ── Encart info-band : largeur sûre ────────────────────────────── */
        .info-band {
            max-width: 100% !important;
            box-sizing: border-box !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
        }

        /* ── Tableaux markdown : scroll horizontal au besoin ────────────── */
        .main table {
            display: block !important;
            overflow-x: auto !important;
            max-width: 100% !important;
            -webkit-overflow-scrolling: touch !important;
        }

        /* ── Blocs de code : pas de débordement ─────────────────────────── */
        .main pre, .main code {
            white-space: pre-wrap !important;
            word-wrap: break-word !important;
            overflow-wrap: break-word !important;
            max-width: 100% !important;
        }

        /* ── Mobile (< 768px) ───────────────────────────────────────────── */
        @media (max-width: 768px) {

            /* Empile toutes les colonnes en vertical */
            [data-testid="stHorizontalBlock"] {
                flex-direction: column !important;
                gap: 0.5rem !important;
            }
            [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 0 !important;
                max-width: 100% !important;
            }

            /* Padding réduit + largeur 100 % */
            .main .block-container,
            section.main > div.block-container,
            [data-testid="stAppViewContainer"] .main .block-container,
            [data-testid="stMain"] .block-container {
                padding-left: 0.75rem !important;
                padding-right: 0.75rem !important;
                padding-top: 1rem !important;
                max-width: 100% !important;
                width: 100% !important;
            }

            /* Conteneurs internes : strictement contenus */
            [data-testid="stHorizontalBlock"],
            [data-testid="stVerticalBlock"] {
                width: 100% !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
            }

            /* Sidebar masquée par défaut */
            [data-testid="stSidebar"] {
                min-width: 0 !important;
            }

            /* Métriques : texte plus petit pour éviter le wrap moche */
            [data-testid="stMetricValue"] {
                font-size: 1.05rem !important;
                word-break: break-word !important;
            }
            [data-testid="stMetricLabel"] {
                font-size: 0.78rem !important;
            }
            [data-testid="stMetricDelta"] {
                font-size: 0.72rem !important;
            }

            /* Dataframes scrollables */
            [data-testid="stDataFrame"] {
                overflow-x: auto !important;
                max-width: 100% !important;
            }

            /* Titres réduits */
            h1 { font-size: 1.5rem !important; line-height: 1.2 !important; }
            h2 { font-size: 1.25rem !important; }
            h3 { font-size: 1.05rem !important; }
            h4 { font-size: 0.95rem !important; }

            /* Encart info-band en mobile : padding plus fin */
            .info-band {
                padding: 10px 12px !important;
                font-size: 0.88rem !important;
            }

            /* Tableaux markdown : police plus petite sur mobile */
            .main table {
                font-size: 0.82rem !important;
            }
            .main th, .main td {
                padding: 6px 8px !important;
            }

            /* st.dataframe (tableaux natifs) : conteneurs strictement bornés */
            [data-testid="stDataFrame"],
            [data-testid="stDataFrame"] > div,
            [data-testid="stDataFrame"] iframe {
                max-width: 100% !important;
                width: 100% !important;
            }

            /* Charts Plotly : hauteur minimale lisible sur mobile */
            [data-testid="stPlotlyChart"] {
                min-height: 320px !important;
            }
            .js-plotly-plot, .plotly-graph-div {
                min-height: 320px !important;
            }

            /* Code blocks : ne pas déborder */
            [data-testid="stCodeBlock"] pre,
            [data-testid="stCodeBlock"] code {
                font-size: 0.78rem !important;
                white-space: pre !important;
                overflow-x: auto !important;
                max-width: 100% !important;
            }
        }

        /* ── Tooltip Elo : reste dans le viewport ───────────────────────── */
        @media (max-width: 500px) {
            .elo-tooltip .elo-tip {
                width: 80vw !important;
                max-width: 280px !important;
                left: 50% !important;
                transform: translateX(-50%) !important;
                font-size: 0.78rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_info(text: str, icon: str = "🎾") -> None:
    """Affiche un encart descriptif soft au style tennis (vert discret)."""
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #f4f9f5 0%, #eaf3ec 100%);
            border-left: 4px solid #3A7D44;
            border-radius: 0 8px 8px 0;
            padding: 12px 16px;
            margin-bottom: 16px;
            color: #3a3a3a;
            font-size: 0.92rem;
            line-height: 1.6;
        ">
        {icon}&nbsp; {text}
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def load_model_bundle(model_path: str) -> dict | None:
    """Charge le bundle joblib {'model': ..., 'features': [...]}."""
    import joblib

    p = Path(model_path)
    if not p.exists():
        return None
    return joblib.load(str(p))
