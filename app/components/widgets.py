"""Composants UI partagés (sélecteurs, formatage FR, mise en page).

Composants obligatoires — à préférer aux éléments Streamlit bruts :

- :func:`page_header` — titre + sous-titre de page (remplace `st.title`) ;
- :func:`kpi_row` — ligne d'indicateurs (`st.metric` bordés, aide accessible
  au clavier) ;
- :func:`section` — titre de section (hiérarchie h2/h3 respectée) ;
- :func:`df_styled` — `st.dataframe` avec `column_config` auto (Elo, rang,
  pourcentages, durées, dates) ;
- :func:`circuit_selectbox` — choix du circuit commun à toutes les pages.
"""

from __future__ import annotations

import html
import re
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
    help_text: str | None = "Tapez pour rechercher",
    placeholder: str = "Rechercher un joueur…",
    default_index: int = 0,
    default_player_id: int | None = None,
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
        default_player_id: Joueur présélectionné (prioritaire sur `default_index`),
            typiquement le n°1 Elo du circuit plutôt que le premier nom alphabétique.

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
    if default_player_id is not None:
        ids = list(mapping.values())
        if default_player_id in ids:
            default_index = ids.index(default_player_id)
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
    return f"{round(f)}"


_ALLOWED_CIRCUITS = frozenset({"ATP", "WTA", "Tous", "TOUS", "all", "ALL", ""})

# Liste canonique des circuits proposés. `Tous` en premier : valeur par défaut.
CIRCUITS: tuple[str, ...] = ("Tous", "ATP", "WTA")

#: Clé de session (et paramètre d'URL) du circuit choisi, partagée par les pages.
CIRCUIT_KEY = "circuit"


def circuit_selectbox(
    label: str = "Circuit",
    *,
    default: str = "Tous",
    key: str | None = None,
    include_all: bool = True,
    location: Any = None,
) -> str:
    """Choix du circuit, **commun à toutes les pages** de la session.

    Le choix est conservé en changeant de page et reflété dans l'URL
    (`?circuit=WTA`), donc partageable. Les pages qui exigent un circuit
    unique (`include_all=False`) ramènent « Tous » à « ATP ».

    Args:
        label: Libellé (masqué visuellement, lu par les lecteurs d'écran).
        default: Valeur initiale parmi `CIRCUITS`.
        key: Ignoré (compatibilité) : la clé est toujours :data:`CIRCUIT_KEY`.
        include_all: Si False, « Tous » n'est pas une valeur acceptée.
        location: Conteneur Streamlit (par défaut, la barre latérale).

    Returns:
        Valeur sélectionnée, garantie dans l'allowlist.
    """
    del key
    container = location if location is not None else st.sidebar
    if CIRCUIT_KEY not in st.session_state and default in CIRCUITS:
        st.session_state[CIRCUIT_KEY] = default
    choice = container.segmented_control(
        label,
        CIRCUITS,
        key=CIRCUIT_KEY,
        required=True,
        bind="query-params",
        persist_state="session",
        width="stretch",
    )
    value = choice if choice in CIRCUITS else default
    if not include_all and value == "Tous":
        return "ATP"
    return value


def current_circuit(*, include_all: bool = True) -> str:
    """Circuit actuellement choisi (sans afficher de widget)."""
    value = st.session_state.get(CIRCUIT_KEY, "Tous")
    if value not in CIRCUITS:
        value = "Tous"
    if not include_all and value == "Tous":
        return "ATP"
    return value


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
    """Ajustements CSS minimes, indépendants du thème clair/sombre.

    Tout le reste (couleurs, polices, rayons) vient de `.streamlit/config.toml`.
    Aucune couleur codée en dur, aucun sélecteur interne fragile.
    """
    st.markdown(
        """
        <style>
        .block-container { padding-top: 2.2rem; max-width: 1200px; }
        h1 { letter-spacing: -0.02em; }
        .page-subtitle { opacity: .72; margin: -.4rem 0 1.2rem; font-size: 1.02rem; }
        @media (max-width: 640px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(ttl=3600, show_spinner=False)
def load_model_bundle(model_path: str, cache_key: str = "") -> dict | None:
    """Charge le bundle joblib {'model': ..., 'features': [...]}.

    Args:
        model_path: Chemin du fichier joblib.
        cache_key: Clé `data_key()` : un nouveau modèle publié invalide le cache.
    """
    import joblib

    p = Path(model_path)
    if not p.exists():
        return None
    return joblib.load(str(p))


# ─────────────────────────────────────────────────────────────────────────────
# Composants de mise en page
# ─────────────────────────────────────────────────────────────────────────────


def page_header(title: str, subtitle: str | None = None, icon: str | None = None) -> None:
    """Titre de page (h1) et sous-titre facultatif.

    Args:
        title: Titre principal.
        subtitle: Phrase d'introduction (facultatif).
        icon: Ignoré (les titres n'ont plus d'emoji, lus à voix haute par les
            lecteurs d'écran) ; conservé pour compatibilité.
    """
    del icon
    st.title(title, anchor=False)
    if subtitle:
        st.markdown(
            f'<p class="page-subtitle">{html.escape(str(subtitle))}</p>',
            unsafe_allow_html=True,
        )


def kpi_row(metrics: list[dict[str, Any]], columns: int | None = None) -> None:
    """Ligne d'indicateurs homogènes (`st.metric` bordés).

    Chaque dict accepte ``label`` et ``value`` (obligatoires), ``delta``,
    ``delta_dir`` ('up'/'down'/'neutral'), ``help`` (infobulle accessible au
    clavier) ; ``icon`` est ignoré (plus d'emoji dans les libellés).

    Args:
        metrics: Liste de dicts décrivant chaque indicateur.
        columns: Nombre forcé de colonnes (par défaut, autant que d'indicateurs).
    """
    if not metrics:
        return
    n = columns or len(metrics)
    cols = st.columns(n)
    for i, m in enumerate(metrics):
        direction = str(m.get("delta_dir", "neutral")).lower()
        delta_color = {"up": "normal", "down": "normal"}.get(direction, "off")
        with cols[i % n]:
            st.metric(
                label=str(m.get("label", "")),
                value=str(m.get("value", "—")),
                delta=m.get("delta"),
                delta_color=delta_color,
                help=m.get("help"),
                border=True,
            )


def section(
    title: str,
    *,
    level: int = 2,
    divider_before: bool = False,
    anchor: str | None = None,
    caption: str | None = None,
) -> None:
    """Titre de section (h2 par défaut, h3 pour une sous-section).

    Args:
        title: Texte du titre.
        level: 2 (section) ou 3 (sous-section).
        divider_before: Si True, insère un séparateur au-dessus.
        anchor: Ancre stable (slug automatique sinon).
        caption: Phrase explicative courte sous le titre (facultatif).
    """
    if divider_before:
        st.divider()
    if anchor is None:
        anchor = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "section"
    if level <= 2:
        st.header(title, anchor=anchor, divider=False)
    else:
        st.subheader(title, anchor=anchor, divider=False)
    if caption:
        st.caption(caption)


def _auto_column_config(df: pd.DataFrame) -> dict[str, Any]:
    """Détecte automatiquement les `column_config` pour les colonnes connues.

    - ``elo`` → entier ;
    - ``rang`` / ``rank`` → ``#n`` ;
    - ``pct`` / ``taux`` / ``winrate`` / ``%`` → barre de progression de 0 à 100 ;
    - ``minutes`` / ``durée`` → ``n min`` ;
    - ``année`` / ``year`` → entier sans séparateur ;
    - colonnes de type date → ``JJ/MM/AAAA``.
    """
    config: dict[str, Any] = {}
    for col in df.columns:
        name = str(col).lower()
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            config[col] = st.column_config.DateColumn(format="DD/MM/YYYY")
        elif "elo" in name:
            config[col] = st.column_config.NumberColumn(format="%d")
        elif "rang" in name or name == "rank" or name.endswith("_rank"):
            config[col] = st.column_config.NumberColumn(format="#%d")
        elif "winrate" in name or name.endswith("_pct") or "taux" in name or name == "%":
            config[col] = st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.1f %%"
            )
        elif "minutes" in name or "duree" in name or "durée" in name:
            config[col] = st.column_config.NumberColumn(format="%d min")
        elif name in ("annee", "année", "year", "saison"):
            config[col] = st.column_config.NumberColumn(format="%d")
    return config


def df_styled(
    df: pd.DataFrame,
    *,
    column_config: dict[str, Any] | None = None,
    height: int | None = None,
    hide_index: bool = True,
    use_container_width: bool = True,
) -> None:
    """Wrapper :func:`st.dataframe` avec `column_config` auto-détecté.

    Args:
        df: DataFrame à afficher.
        column_config: Overrides explicites (priorité sur l'auto-détection).
        height: Hauteur en pixels (automatique si None).
        hide_index: Masque l'index pandas.
        use_container_width: Étend à la largeur du conteneur.
    """
    merged = _auto_column_config(df)
    if column_config:
        merged.update(column_config)
    st.dataframe(
        df,
        column_config=merged if merged else None,
        height=height if height else _fit_height(len(df)),
        hide_index=hide_index,
        width="stretch" if use_container_width else "content",
    )


def _fit_height(rows: int, max_rows: int = 25) -> int | str:
    """Hauteur affichant toutes les lignes d'un petit tableau (sans ascenseur interne)."""
    if rows > max_rows:
        return "auto"
    return 35 * (rows + 1) + 3


def mark_provisional(scores: pd.Series, sources: pd.Series) -> pd.Series:
    """Ajoute un astérisque aux scores des résultats provisoires (source ESPN)."""
    return scores.fillna("").astype(str) + sources.map(lambda s: " *" if s == "espn" else "")


PROVISIONAL_NOTE = (
    "* Résultat provisoire (source ESPN), confirmé à la prochaine publication de "
    "tennis-data.co.uk."
)


# ─────────────────────────────────────────────────────────────────────────────
# Libellés et petits formats
# ─────────────────────────────────────────────────────────────────────────────

SURFACE_FR: dict[str, str] = {
    "hard": "Dur",
    "clay": "Terre battue",
    "grass": "Gazon",
    "Hard": "Dur",
    "Clay": "Terre battue",
    "Grass": "Gazon",
    "Carpet": "Moquette",
}

LEVEL_FR: dict[str, str] = {
    "G": "Grand Chelem",
    "M": "Masters 1000",
    "PM": "WTA 1000",
    "P": "WTA 500",
    "I": "WTA 250",
    "A": "ATP 250/500",
    "F": "Masters de fin d'année",
    "D": "Coupe Davis / BJK Cup",
    "O": "Jeux olympiques",
    "W": "ITF",
}

ROUND_FR: dict[str, str] = {
    "F": "Finale",
    "SF": "Demi-finale",
    "QF": "Quart de finale",
    "R16": "8e de finale",
    "R32": "16e de finale",
    "R64": "32e de finale",
    "R128": "64e de finale",
    "RR": "Poules",
    "BR": "Match pour le bronze",
}


def surface_fr(value: object) -> str:
    """Surface en français (`Hard` → `Dur`)."""
    return SURFACE_FR.get(str(value), str(value) if value is not None else "—")


def level_fr(value: object) -> str:
    """Niveau de tournoi en clair (`G` → `Grand Chelem`)."""
    return LEVEL_FR.get(str(value), str(value))


def round_fr(value: object) -> str:
    """Tour en français (`SF` → `Demi-finale`)."""
    return ROUND_FR.get(str(value), str(value))


def to_date(series: pd.Series) -> pd.Series:
    """Convertit des entiers AAAAMMJJ en dates (pour `DateColumn`)."""
    return pd.to_datetime(series.astype("Int64").astype(str), format="%Y%m%d", errors="coerce")


def relative_age(moment: datetime, now: datetime | None = None) -> str:
    """Ancienneté lisible (« il y a 2 h », « il y a 3 j »)."""
    now = now or datetime.now(moment.tzinfo)
    minutes = max(int((now - moment).total_seconds() // 60), 0)
    if minutes < 60:
        return f"il y a {minutes} min"
    if minutes < 48 * 60:
        return f"il y a {minutes // 60} h"
    return f"il y a {minutes // (24 * 60)} j"


MONTHS_FR = (
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)


def format_date_long(value: int | None) -> str:
    """`20261116` → `16 nov. 2026`."""
    if not value:
        return "—"
    try:
        day = datetime.strptime(f"{int(value):08d}", "%Y%m%d")
    except ValueError:
        return str(value)
    return f"{day.day} {MONTHS_FR[day.month - 1]} {day.year}"


def freshness_panel(metadata: dict, location: Any = None) -> None:
    """Encart « fraîcheur des données » (barre latérale par défaut).

    Indique la date du dernier match par circuit, l'ancienneté de la dernière
    mise à jour et le nombre de résultats provisoires (pas encore confirmés).
    """
    container = location if location is not None else st.sidebar
    if not metadata:
        return
    last = metadata.get("last_match_date", {})
    lines = [f"**{c}** · {format_date_long(d)}" for c, d in sorted(last.items())]
    generated = metadata.get("generated_at")
    updated = ""
    if generated:
        try:
            updated = relative_age(datetime.fromisoformat(generated))
        except ValueError:
            updated = ""
    with container.container(border=True):
        st.markdown("**Derniers résultats**")
        st.markdown("  \n".join(lines) or "—")
        details = []
        if updated:
            details.append(f"Mise à jour {updated}")
        provisional = int(metadata.get("provisional_matches") or 0)
        if provisional:
            details.append(f"{provisional} résultats provisoires")
        if details:
            st.caption(" · ".join(details))
