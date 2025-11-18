# -*- coding: utf-8 -*-
"""
FemiBot TAVI - versión Streamlit + GitHub
Requisitos de la base (Excel en el mismo folder que este archivo):
    Casos Realizados TAVI.xlsx
Columnas esperadas:
    - Obra Social
    - Pedido
    - Material
    - Medida
    - Cantidad
    - Centro
    - Medico
    - Mes
    - Localidad
    - Provincia
"""

import os
import re
import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz

# =========================
#   Config general
# =========================
st.set_page_config(
    page_title="FemiBot TAVI — Chat de Casos",
    page_icon="🤖",
    layout="wide",
)

# ---------- Acceso ----------
APP_USER = "femani"
APP_PASSWORD = "tavi2025"

with st.sidebar:
    st.subheader("🔒 Acceso")
    user = st.text_input("Usuario", value="", key="login_user")
    pwd = st.text_input("Clave", type="password", key="login_pwd")

if user != APP_USER or pwd != APP_PASSWORD:
    st.warning("Acceso restringido. Ingresá usuario y clave en la barra lateral.")
    st.stop()

# Header (solo se muestra si pasó el login)
st.markdown(
    """
<div style="display:flex; align-items:center; gap:12px; padding:6px 0 2px 0;">
  <div style="font-size:34px; line-height:1">🤖</div>
  <div>
    <div style="font-size:22px; font-weight:700; margin:0;">FemiBot TAVI</div>
    <div style="color:#475569; margin-top:-2px;">Consultas de casos y materiales </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- Ruta de datos ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "Casos Realizados TAVI.xlsx")  # Excel en el repo

# ---------- Utilidades ----------
def unaccent(s: str) -> str:
    return (
        str(s)
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ñ", "n")
    )

def normalize_obra(s: str) -> str:
    """Normaliza nombres de obra social (saca puntos, espacios, S.A., etc.)."""
    s0 = unaccent(str(s)).upper()
    s0 = re.sub(r"\bS\.?\s*A\.?\b", "", s0)  # S.A. / SA
    s0 = re.sub(r"[^A-Z0-9]+", "", s0)
    return s0

def canon(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).upper()).strip()

# ===== Provincias (detección robusta) =====
PROVINCIAS = [
    "BUENOS AIRES","CABA","CAPITAL FEDERAL","CATAMARCA","CHACO","CHUBUT","CORDOBA",
    "CORRIENTES","ENTRE RIOS","FORMOSA","JUJUY","LA PAMPA","LA RIOJA","MENDOZA",
    "MISIONES","NEUQUEN","RIO NEGRO","SALTA","SAN JUAN","SAN LUIS","SANTA CRUZ",
    "SANTA FE","SANTIAGO DEL ESTERO","TIERRA DEL FUEGO","TUCUMAN",
]
PROVINCIAS = [unaccent(p).upper() for p in PROVINCIAS]
PROVINCIAS_NORM = [re.sub(r"[^A-Z]", "", p) for p in PROVINCIAS]

# ===== Palabras de institución =====
STOP_TOKENS_CENTRO = {
    "DE","DEL","LA","EL","LOS","LAS","SAN","SANTA","NTRA","SRA","SR","Y","EN","DA","DO","DOS","DAS",
    "HOSPITAL","INSTITUTO","CLINICA","CLINICO","SANATORIO","CENTRO","POLICLINICO","PRIVADO",
    "GENERAL","REGIONAL","NACIONAL","UNIVERSITARIO","MEDICO","MEDICINA","CARDIOVASCULAR","CARDIOLOGIA",
    "FUNDACION","ASOCIACION","HOSP","HTAL","SA","SRL",
}

# ----- Small talk -----
SMALLTALK = {
    "saludo": ["hola","buen dia","buen día","buenas","buenas tardes","buenas noches","hey","qué tal","que tal"],
    "despedida": ["chau","adios","adiós","nos vemos","hasta luego","me voy","cuidate","que tengas buen dia","que tengas buen día"],
    "gracias": ["gracias","muchas gracias","mil gracias","te agradezco","agradezco"],
    "estado": ["como estas","cómo estás","todo bien","que tal estas","como va","cómo va","como andas","cómo andas"],
    "ayuda": ["ayuda","como uso","como se usa","instrucciones","palabras clave","help","ayudame","necesito ayuda"],
    "elogio": ["muy bien","excelente","perfecto","genial","buen trabajo","gracias por la ayuda","muy claro","muy útil"],
}

def smalltalk_reply(q: str):
    u = unaccent(q.lower())
    u = re.sub(r"\s+", " ", u).strip()
    def contains_any(words): return any(w in u for w in words)

    if contains_any(SMALLTALK["saludo"]):
        return "👋 Hola, soy **FemiBot TAVI**. Estoy listo para ayudarte con los casos realizados."
    if contains_any(SMALLTALK["gracias"]):
        return "😊 De nada. Me alegra poder ayudarte."
    if contains_any(SMALLTALK["estado"]):
        return "🙂 Todo en orden. ¿Querés que revise algún centro, médico u obra social en particular?"
    if contains_any(SMALLTALK["despedida"]):
        return "👋 Hasta luego. Cuando quieras seguimos con más consultas."
    if contains_any(SMALLTALK["ayuda"]):
        return (
            "🩺 Para consultas específicas incluí una **palabra clave**:\n"
            "• **centro** • **obra social** • **medico** • **provincia** • **localidad**\n"
            "También podés agregar el **mes** (ej. “octubre”) y la **medida** (ej. “29mm”)."
        )
    if contains_any(SMALLTALK["elogio"]):
        return "🤝 ¡Gracias! Sigo acá para lo que necesites."
    return None

@st.cache_data
def load_df_any(path: str):
    return pd.read_excel(path)

@st.cache_data
def prepare_df(df_in: pd.DataFrame):
    df = df_in.copy()

    # Normalizar nombres de columnas
    df.columns = [c.strip().lower() for c in df.columns]
    rename = {"obra social": "obra_social"}
    df = df.rename(columns=rename)

    # Asegurar columna cantidad numérica
    if "cantidad" in df.columns:
        df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0).astype(int)
    else:
        df["cantidad"] = 0

    # Normalización de texto
    for c in ["obra_social","material","medida","centro","medico","mes","localidad","provincia"]:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()
            df[c + "_U"]  = df[c].str.upper()
            df[c + "_UA"] = df[c].str.lower().map(unaccent).str.upper()

    # Ajustar medida para que "29MM" -> "29 MM"
    if "medida_UA" in df.columns:
        df["medida_UA"] = df["medida_UA"].str.replace(r"\s*MM\b", " MM", regex=True)

    # Obra social normalizada
    if "obra_social" in df.columns:
        df["obra_social_norm"] = df["obra_social"].map(normalize_obra)

    # Reglas de CASO (sólo válvulas verdaderas)
    if "material_U" in df.columns:
        df["material_canon"] = df["material_U"].map(lambda s: canon(s))
    else:
        df["material_canon"] = ""

    VALVULAS_VALIDAS = {
        "VALVULA AORTICA PERCUTANEA COREVALVE EVOLUT PRO +",
        "VALVULA AORTICA PERCUTANEA EVOLUT FX",
    }
    df["es_valvula"] = df["material_canon"].isin(VALVULAS_VALIDAS)

    return df

def build_vocabs(df: pd.DataFrame):
    v = {
        "centro":    sorted(df.get("centro_UA", pd.Series(dtype=str)).dropna().unique().tolist()),
        "medico":    sorted(df.get("medico_UA", pd.Series(dtype=str)).dropna().unique().tolist()),
        "material":  sorted(df.get("material_UA", pd.Series(dtype=str)).dropna().unique().tolist()),
        "provincia": sorted(df.get("provincia_UA", pd.Series(dtype=str)).dropna().unique().tolist()),
        "localidad": sorted(df.get("localidad_UA", pd.Series(dtype=str)).dropna().unique().tolist()),
    }
    canon_by_norm = {}
    if "obra_social_norm" in df.columns:
        tmp = (
            df.assign(_n=df.groupby("obra_social_norm")["obra_social"].transform("size"))
            .sort_values("_n", ascending=False)
        )
        seen = set()
        for _, row in tmp.iterrows():
            n = row["obra_social_norm"]
            if n and n not in seen:
                canon_by_norm[n] = str(row["obra_social"]).upper()
                seen.add(n)
    return v, canon_by_norm

# ---- Tokens únicos por centro ----
def unique_center_tokens(v_centros):
    token_counts, token_owner = {}, {}
    stop = {
        "DE","DEL","LA","EL","SAN","SANTA","CLINICA","CLINICO","HOSPITAL","INSTITUTO",
        "CENTRO","SANATORIO","Y","LOS","LAS","NTRA","SRA","SR","PRIVADO","PRIV","REGIONAL",
        "NACIONAL","GENERAL","UNIVERSITARIO","MEDICO","MEDICINA","CARDIOVASCULAR","CARDIOLOGIA",
        "FUNDACION","ASOCIACION","POLICLINICO","HOSP","HTAL","SA","SRL",
    }
    for c in v_centros:
        for t in re.split(r"[^A-Z0-9]+", c):
            if len(t) < 3 or t in stop:
                continue
            token_counts[t] = token_counts.get(t, 0) + 1
            token_owner.setdefault(t, set()).add(c)
    return {t: list(token_owner[t])[0] for t, cnt in token_counts.items() if cnt == 1}

# ---- Alias/acrónimos de centros ----
def build_center_aliases(v_centros):
    raw_alias_map = {}  # alias -> set(centros)

    def add_alias(alias, center):
        if len(alias) < 3:
            return
        raw_alias_map.setdefault(alias, set()).add(center)

    for c in v_centros:
        parts = [p for p in re.split(r"[^A-Z0-9]+", c) if p]

        # acrónimo con palabras "fuertes"
        strong = [p for p in parts if p not in STOP_TOKENS_CENTRO and len(p) >= 3]
        if len(strong) >= 1:
            acro = "".join(w[0] for w in strong)
            if len(acro) >= 3:
                add_alias(acro, c)

        # tokens tipo sigla que ya están en el nombre
        for p in parts:
            if p not in STOP_TOKENS_CENTRO and p.isalpha() and 3 <= len(p) <= 6:
                add_alias(p, c)

        # contenido entre paréntesis
        paren = re.findall(r"\(([A-Z0-9\s\.]+)\)", c)
        for block in paren:
            for p in re.split(r"[^A-Z0-9]+", block):
                if p and p.isalpha() and 3 <= len(p) <= 6:
                    add_alias(p, c)

    alias_unique = {alias: list(owners)[0] for alias, owners in raw_alias_map.items() if len(owners) == 1}
    return alias_unique  # alias -> centro_UA

def fuzzy_pick(q_u, vocab, cutoff=80):
    if not vocab:
        return None
    m = process.extractOne(q_u, vocab, scorer=fuzz.WRatio, score_cutoff=cutoff)
    return m[0] if m else None

# Meses y alias materiales
MESES = {
    "ENERO": "ENERO",
    "FEBRERO": "FEBRERO",
    "MARZO": "MARZO",
    "ABRIL": "ABRIL",
    "MAYO": "MAYO",
    "JUNIO": "JUNIO",
    "JULIO": "JULIO",
    "AGOSTO": "AGOSTO",
    "SEPTIEMBRE": "SEPTIEMBRE",
    "SETIEMBRE": "SEPTIEMBRE",
    "OCTUBRE": "OCTUBRE",
    "NOVIEMBRE": "NOVIEMBRE",
    "DICIEMBRE": "DICIEMBRE",
}

# 👉 acá agregamos PRO+ sin espacio
ALIAS_MATERIALES = {
    "FX": "VALVULA AORTICA PERCUTANEA EVOLUT FX",
    "PRO +": "VALVULA AORTICA PERCUTANEA COREVALVE EVOLUT PRO +",
    "PRO+": "VALVULA AORTICA PERCUTANEA COREVALVE EVOLUT PRO +",
    "PRO PLUS": "VALVULA AORTICA PERCUTANEA COREVALVE EVOLUT PRO +",
}

def match_obra_from_text(text, canon_by_norm):
    """
    Busca la obra social a partir del texto libre.

    - Si el usuario escribe una sigla (ej: OSPTF, OSDE, PAMI), solo acepta
      coincidencias EXACTAS (sin fuzzy) para evitar errores.
    - Para nombres largos / descriptivos (ej: "union personal", "swiss medical")
      mantiene algo de flexibilidad como antes.
    """
    if not canon_by_norm:
        return None, None

    raw = str(text).strip()
    if not raw:
        return None, None

    # Normalizamos igual que la columna obra_social_norm
    q_norm = normalize_obra(raw)
    if not q_norm:
        return None, None

    # 1) Coincidencia EXACTA (lo más importante)
    if q_norm in canon_by_norm:
        return q_norm, canon_by_norm[q_norm]

    # 2) ¿Parece una sigla? (solo letras/números, corta)
    is_sigla = bool(re.fullmatch(r"[A-Z0-9]{3,10}", q_norm))
    if is_sigla:
        return None, None

    # 3) Para nombres más largos/descriptivos mantenemos algo de flexibilidad
    for n in canon_by_norm.keys():
        if q_norm in n or n in q_norm:
            return n, canon_by_norm[n]

    # 4) Fuzzy solo para nombres largos
    best = process.extractOne(
        q_norm,
        list(canon_by_norm.keys()),
        scorer=fuzz.WRatio,
        score_cutoff=85,
    )
    if best:
        n = best[0]
        return n, canon_by_norm[n]

    return None, None


def parse_query(q, vocabs, center_tokens, center_aliases, canon_by_norm):
    q_raw = q
    q_u = unaccent(q.lower()).upper()

    wants = {
        "centro":    ("CENTRO" in q_u),
        "medico":    ("MEDICO" in q_u) or ("MÉDICO" in q_u),
        "obra":      ("OBRA SOCIAL" in q_u) or ("OBRASOCIAL" in q_u),
        "provincia": "PROVINCIA" in q_u,
        "localidad": "LOCALIDAD" in q_u,
    }

    # --------- CENTRO ---------
    centro = None
    centro_candidates = []
    if wants["centro"]:
        m = re.search(r"CENTRO\s+([A-ZÁÉÍÓÚÜÑ0-9\.\s\-]+)", q_u)
        frag = None
        if m:
            frag = m.group(1).strip()
            frag = re.split(
                r"\b(OBRA SOCIAL|MEDICO|LOCALIDAD|PROVINCIA|MATERIAL|MES|CASOS?)\b",
                frag
            )[0].strip()

        candidates = vocabs["centro"]
        toks = []
        if frag:
            toks = [t for t in re.split(r"[^A-Z0-9]+", frag) if len(t) >= 2]

        # 1) alias único (HAM, IMEV, etc.)
        if not centro:
            for t in toks:
                if t in center_aliases:
                    centro = center_aliases[t]
                    break

        # 2) token único de centro
        if not centro:
            for t in toks:
                if t in center_tokens:
                    centro = center_tokens[t]
                    break

        # 3) Fuzzy con tokens fuertes
        if not centro:
            toks_strong = [t for t in toks if t not in STOP_TOKENS_CENTRO]
            if toks_strong:
                pool = [c for c in candidates if all(tok in c for tok in toks_strong)]
                if not pool:
                    pool = [c for c in candidates if any(tok in c for tok in toks_strong)]
                if pool:
                    scored = process.extract(
                        " ".join(toks_strong),
                        pool,
                        scorer=fuzz.WRatio,
                        limit=10
                    )
                    centro_candidates = [c for c, score, _ in scored if score >= 78]
                    strong = [c for c, score, _ in scored if score >= 86]
                    if len(strong) == 1:
                        centro = strong[0]
                    elif len(strong) == 0 and len(centro_candidates) == 1:
                        centro = centro_candidates[0]

        # 4) último intento: token corto
        if not centro and toks:
            short = [t for t in toks if 3 <= len(t) <= 6]
            if len(short) == 1:
                t = short[0]
                pool = [c for c in candidates if t in c]
                if len(pool) == 1:
                    centro = pool[0]
                elif pool:
                    best = process.extractOne(
                        t,
                        pool,
                        scorer=fuzz.WRatio,
                        score_cutoff=70
                    )
                    if best:
                        centro = best[0]

    # --------- MES ---------
    mes = None
    tokens = re.split(r"[^A-ZÁÉÍÓÚÜÑ0-9]+", q_u)
    for k, v in MESES.items():
        if k in tokens:
            mes = v
            break

    # --------- MATERIAL (FX / PRO+) ---------
    material = None
    # 👉 ahora solo detectamos material si aparece la palabra MODELO
    if "MODELO" in q_u:
        for alias, canon_name in ALIAS_MATERIALES.items():
            pattern = r"MODELO\s+" + re.escape(alias)
            if re.search(pattern, q_u):
                material = canon_name.upper()
                break
    # si no se escribió "modelo", no detectamos tipo de válvula para evitar confusiones

    # --------- MEDIDA ---------
    mm = re.search(r"(\d{2})\s*MM", q_u) or re.search(r"\b(23|26|29|34)\b", q_u)
    size = mm.group(1) if mm else None  # solo número (23/26/29/34)

    # --------- MEDICO ---------
    medico = None
    if wants["medico"]:
        # Tomo solo lo que viene después de la palabra MEDICO
        m = re.search(r"MEDICO\s+([A-ZÁÉÍÓÚÜÑ0-9\.\s\-]+)", q_u)
        frag = ""
        if m:
            frag = m.group(1)
            # Corto si después vienen otras palabras clave
            frag = re.split(
                r"\b(OBRA SOCIAL|CENTRO|LOCALIDAD|PROVINCIA|MATERIAL|MES|CASOS?)\b",
                frag
            )[0].strip()

        # Si quedó algo razonable, hago fuzzy solo sobre eso
        if frag:
            medico = fuzzy_pick(frag, vocabs["medico"], cutoff=82)


    # --------- PROVINCIA ---------
    provincia = None
    if wants["provincia"]:
        m = re.search(r"PROVINCIA\s+DE\s+([A-ZÁÉÍÓÚÜÑ\s]+)", q_u)
        if m:
            cand = m.group(1).strip()
            cand = re.split(
                r"\b(CENTRO|OBRA SOCIAL|MEDICO|LOCALIDAD|MATERIAL|CASOS?)\b",
                cand
            )[0].strip()
            norm = re.sub(r"[^A-Z]", "", cand)
            if norm in PROVINCIAS_NORM:
                provincia = PROVINCIAS[PROVINCIAS_NORM.index(norm)]
        if not provincia:
            for p in PROVINCIAS:
                if p in q_u:
                    provincia = p
                    break
        if not provincia:
            provincia = fuzzy_pick(q_u, PROVINCIAS, cutoff=88)

    # --------- LOCALIDAD ---------
    localidad = fuzzy_pick(q_u, vocabs["localidad"], cutoff=82) if wants["localidad"] else None

    # --------- OBRA SOCIAL ---------
    obra_norm, obra_canon = (None, None)
    obra_candidates = []

    if wants["obra"]:
        m = re.search(r"OBRA\s+SOCIAL\s+([A-ZÁÉÍÓÚÜÑ0-9\.\s\-]+)", q_u)
        subtext = q_raw
        if m:
            subtext = m.group(1)

        # 👉 NUEVO: cortar la parte de obra antes de otros filtros (mes, centro, médico, etc.)
        subtext = re.split(
            r"\b(mes|centro|medico|médico|localidad|provincia|material|modelo|casos?)\b",
            subtext,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()

        # intento normal (exacto + nombres largos)
        obra_norm, obra_canon = match_obra_from_text(subtext, canon_by_norm)

        # si no encontró nada y parece sigla, buscamos sugerencias pero NO filtramos
        if not obra_norm and canon_by_norm:
            raw = str(subtext).strip()
            q_norm = normalize_obra(raw)
            if q_norm:
                is_sigla = bool(re.fullmatch(r"[A-Z0-9]{3,10}", q_norm))
                if is_sigla:
                    keys = list(canon_by_norm.keys())
                    matches = process.extract(
                        q_norm,
                        keys,
                        scorer=fuzz.WRatio,
                        limit=10,
                    )
                    seen = set()
                    for key, score, _ in matches:
                        if score >= 70:
                            canon_name = canon_by_norm[key]
                            if canon_name not in seen:
                                obra_candidates.append(canon_name)
                                seen.add(canon_name)

    is_casos = ("CASO" in q_u) or ("CASOS" in q_u)
    is_unidades = ("UNIDADES" in q_u) or ("CANTIDAD" in q_u)

    return {
        "wants": wants,
        "centro": centro,
        "centro_candidates": centro_candidates,
        "mes": mes,
        "size": size,
        "material": material,
        "medico": medico,
        "provincia": provincia,
        "localidad": localidad,
        "obra_norm": obra_norm,
        "obra_canon": obra_canon,
        "obra_candidates": obra_candidates,
        "is_casos": is_casos,
        "is_unidades": is_unidades,
    }


def apply_filters(df, p):
    d = df.copy()
    if p["wants"]["centro"]    and p["centro"]:
        d = d[d["centro_UA"] == p["centro"]]
    if p["wants"]["medico"]    and p["medico"]:
        d = d[d["medico_UA"] == p["medico"]]
    if p["wants"]["obra"]      and p["obra_norm"]:
        d = d[d["obra_social_norm"] == p["obra_norm"]]
    if p["wants"]["provincia"] and p["provincia"]:
        d = d[d["provincia_UA"] == p["provincia"]]
    if p["wants"]["localidad"] and p["localidad"]:
        d = d[d["localidad_UA"] == p["localidad"]]
    if p["mes"]:
        d = d[d["mes_UA"] == p["mes"]]
    if p["material"]:
        d = d[d["material_UA"] == p["material"]]
    if p["size"]:
        d = d[d["medida_UA"].str.contains(p["size"], na=False)]
    return d

# ---------- Sidebar / carga de datos ----------
with st.sidebar:
    st.header("📂 Datos")

    if not os.path.exists(DATA_PATH):
        st.error(
            "No se encontró el archivo **'Casos Realizados TAVI.xlsx'**.\n\n"
            "Subilo al mismo repositorio y carpeta donde está `app.py` y volvé a recargar la app."
        )
        st.stop()

    try:
        df_raw = load_df_any(DATA_PATH)
        df = prepare_df(df_raw)
    except Exception as e:
        st.error("Error al leer o preparar la base. Revisá que el Excel tenga las columnas esperadas.")
        st.exception(e)
        st.stop()

    vocabs, canon_by_norm = build_vocabs(df)
    center_tokens = unique_center_tokens(vocabs["centro"])
    center_aliases = build_center_aliases(vocabs["centro"])

    n_reg = len(df)
    n_ped = df["pedido"].nunique() if "pedido" in df.columns else n_reg
    st.caption(f"Registros: {n_reg} | Pedidos (todas las líneas): {n_ped}")

# ---------- Cuadro fijo de palabras clave ----------
st.markdown(
    """
<style>
.helper-box{
  border:1px solid #e5e7eb; border-radius:12px; padding:12px 14px;
  background:#f9fafb; margin:8px 0 10px 0; color:#111827;
}
:root [data-theme="dark"] .helper-box{
  background:#0f172a; border-color:#374151; color:#e5e7eb;
}
.helper-box b, .helper-box i { color: inherit; }
</style>
<div class="helper-box">
  <div style="font-weight:700; margin-bottom:6px;">Cómo preguntarle a FemiBot</div>
  <ul style="margin:0 0 0 18px; padding:0;">
    <li>Usá <b>centro</b> para instituciones (ej.: <i>centro favaloro</i>, <i>centro ham</i>).</li>
    <li>Usá <b>obra social</b>, <b>medico</b>, <b>mes</b>, <b>provincia</b> o <b>localidad</b> para esos filtros.</li>
    <li>Para tipo de válvula, escribí <b>modelo pro+</b> o <b>modelo fx</b>.</li>
    <li>Para medida, incluí el número (ej.: <b>29mm</b>, <b>34 mm</b>).</li>
  </ul>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- Input principal ----------
q = st.text_input("💬 Escriba su consulta aquí")

if q:
    # Small talk primero
    st_msg = smalltalk_reply(q)
    if st_msg:
        st.info(st_msg)
        st.stop()

    p = parse_query(q, vocabs, center_tokens, center_aliases, canon_by_norm)

    # Si pidieron centro pero quedó ambiguo, ofrecer opciones
    if p["wants"]["centro"] and not p["centro"] and p["centro_candidates"]:
        st.warning(
            "No se identificó un centro con claridad. Refiná la consulta con el nombre completo "
            "o una palabra distintiva del centro."
        )
        st.write("**Coincidencias posibles:**")
        st.dataframe(pd.DataFrame({"Centro (posible)": [c.title() for c in p["centro_candidates"]]}))
        st.stop()

    # Si pidieron obra social y NO se identificó con claridad
    if p["wants"]["obra"] and not p["obra_norm"]:

        st.warning(
            "No se identificó una obra social con claridad. "
            "Elegí una opción de la lista o escribila tal como figura en la base."
        )

        # Si hay candidatos → mostrar radio
        if p.get("obra_candidates"):
            choice = st.radio(
                "Coincidencias posibles:",
                p["obra_candidates"],
                key="obra_choice_value",
            )

            if st.button("Usar esta obra social"):
                selected = choice
                norm = normalize_obra(selected)
                if norm in canon_by_norm:
                    p["obra_norm"] = norm
                    p["obra_canon"] = canon_by_norm[norm]
                else:
                    p["obra_norm"] = None
                    p["obra_canon"] = selected
            else:
                st.stop()

        # Si NO hay candidatos → mensaje y stop
        else:
            st.info("No pude encontrar coincidencias razonables para esa obra social.")
            st.stop()

    # 👉 aplicar filtros recién después de resolver obra social
    dff = apply_filters(df, p)

    # Casos = suma de cantidad SOLO en filas con válvula verdadera
    dff_valv = dff[dff["es_valvula"]]
    casos = int(dff_valv["cantidad"].sum())

    # Preparar detalle de filtros aplicados
    detalle = []
    if p["wants"]["centro"]    and p["centro"]:
        detalle.append(f"Centro: **{p['centro'].title()}**")
    if p["wants"]["medico"]    and p["medico"]:
        detalle.append(f"Médico: **{p['medico'].title()}**")
    if p["wants"]["obra"]      and p["obra_canon"]:
        detalle.append(f"Obra Social: **{p['obra_canon'].title()}**")
    if p["wants"]["provincia"] and p["provincia"]:
        detalle.append(f"Provincia: **{p['provincia'].title()}**")
    if p["wants"]["localidad"] and p["localidad"]:
        detalle.append(f"Localidad: **{p['localidad'].title()}**")
    if p["mes"]:
        detalle.append(f"Mes: **{p['mes'].title()}**")
    if p["material"] in [
        "VALVULA AORTICA PERCUTANEA COREVALVE EVOLUT PRO +",
        "VALVULA AORTICA PERCUTANEA EVOLUT FX",
    ]:
        # 👉 ahora también reconoce PRO+ sin espacio
        q_up = q.upper()
        if "PRO +" in q_up or "PRO+" in q_up or "PRO PLUS" in q_up:
            detalle.append("Tipo de válvula: **PRO+**")
        elif "FX" in q_up:
            detalle.append("Tipo de válvula: **FX**")
        else:
            detalle.append(f"Material: **{p['material'].title()}**")
    if p["size"]:
        detalle.append(f"Medida: **{p['size']} mm**")

    st.success(
        f"**Casos (unidades de válvula): {casos}**  "
        + (" | ".join(detalle) if detalle else "")
    )

    # Tops de ayuda si faltó el valor concreto
    def show_top(col_u, label):
        if col_u in dff_valv.columns and len(dff_valv) > 0:
            tb = (
                dff_valv.groupby(col_u)["cantidad"]
                .sum()
                .reset_index()
                .rename(columns={"cantidad": "casos"})
                .sort_values("casos", ascending=False)
                .head(15)
            )
            st.write(f"### Top {label} (por casos)")
            st.dataframe(tb.rename(columns={col_u: label}), use_container_width=True)

    if p["wants"]["obra"] and not p["obra_norm"]:
        if "obra_social_U" in dff_valv.columns:
            show_top("obra_social_U", "Obra Social")
    if p["wants"]["medico"] and not p["medico"]:
        show_top("medico_U", "Médico")
    if p["wants"]["centro"] and not p["centro"]:
        show_top("centro_U", "Centro")
    if p["wants"]["provincia"] and not p["provincia"]:
        show_top("provincia_U", "Provincia")
    if p["wants"]["localidad"] and not p["localidad"]:
        show_top("localidad_U", "Localidad")
