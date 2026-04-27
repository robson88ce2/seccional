# index.py — Sistema de Numeração de Documentos (Multi-Delegacia)
# Layout moderno + imagem centralizada + destino opcional + lembrar login

from datetime import datetime
import hashlib, hmac, logging, base64, os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.pool import NullPool
from urllib.parse import quote_plus

try:
    import extra_streamlit_components as stx
    COOKIES_OK = True
except ImportError:
    COOKIES_OK = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  PAGE CONFIG  (deve ser a 1ª chamada st.)
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Numerador de Documentos",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  UTIL — Imagem → base64 (inline HTML)
# ─────────────────────────────────────────────
def img_to_b64(path: str) -> str:
    """Converte imagem local para string base64 para uso em HTML."""
    try:
        with open(path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        ext = "jpeg" if ext == "jpg" else ext
        return f"data:image/{ext};base64,{data}"
    except Exception:
        return ""

# ─────────────────────────────────────────────
#  CSS  —  Tema Institucional Escuro + Dourado
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap');

:root {
    --navy:   #0b1d35;
    --navy2:  #112447;
    --navy3:  #1a3260;
    --gold:   #c9a84c;
    --gold2:  #e8c97a;
    --text:   #1e293b;
    --muted:  #64748b;
    --bg:     #f1f5f9;
    --white:  #ffffff;
    --green:  #059669;
    --red:    #dc2626;
    --radius: 14px;
    --shadow: 0 4px 24px rgba(11,29,53,.10);
}

html, body, [class*="css"] {
    font-family: 'Outfit', sans-serif !important;
}

/* ── FUNDO PRINCIPAL ── */
.stApp { background: var(--bg); }
.block-container {
    padding: 2rem 2.5rem 3rem !important;
    max-width: 900px !important;
}

/* ── SIDEBAR ── */
[data-testid="stSidebar"] {
    background: linear-gradient(170deg, var(--navy) 0%, var(--navy2) 55%, var(--navy3) 100%) !important;
    border-right: 1px solid rgba(201,168,76,.15);
}
[data-testid="stSidebar"] > div { padding-top: 0 !important; }
[data-testid="stSidebar"] * { color: #dde6f0 !important; }

/* ── LOGO SIDEBAR — forçamos alinhamento via classe própria ── */
.sidebar-logo-wrap {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    padding: 28px 0 12px !important;
    width: 100% !important;
}
.sidebar-logo-wrap img {
    border-radius: 16px;
    box-shadow: 0 6px 32px rgba(0,0,0,.55);
    border: 2px solid rgba(201,168,76,.30);
    width: 110px !important;
    height: 110px !important;
    object-fit: cover;
    display: block !important;
}

/* ── LOGO LOGIN — centralizada ── */
.login-logo-wrap {
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    width: 100% !important;
    margin-bottom: 1.2rem !important;
}
.login-logo-wrap img {
    width: 110px;
    height: 110px;
    border-radius: 18px;
    box-shadow: 0 8px 36px rgba(11,29,53,.28);
    border: 2px solid rgba(201,168,76,.30);
    object-fit: cover;
    display: block;
}

/* Emoji fallback quando não há imagem */
.logo-emoji-fallback {
    font-size: 4rem;
    text-align: center;
    display: block;
    padding: 10px 0 6px;
}

/* Divisor dourado sidebar */
.gold-divider {
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--gold), transparent);
    margin: 10px 16px 14px;
    border: none;
    opacity: .6;
}

/* Radio sidebar */
[data-testid="stSidebar"] .stRadio > div { gap: 4px !important; }
[data-testid="stSidebar"] .stRadio label {
    display: flex !important;
    align-items: center !important;
    gap: 10px !important;
    padding: 10px 16px !important;
    border-radius: 10px !important;
    font-size: .92rem !important;
    font-weight: 500 !important;
    cursor: pointer;
    transition: all .18s ease !important;
    border: 1px solid transparent !important;
}
[data-testid="stSidebar"] .stRadio label:hover {
    background: rgba(201,168,76,.12) !important;
    border-color: rgba(201,168,76,.2) !important;
}
[data-testid="stSidebar"] .stRadio [data-testid="stMarkdownContainer"] p {
    font-size: .92rem !important;
}

/* ── CARD PRINCIPAL ── */
.card {
    background: var(--white);
    border-radius: var(--radius);
    padding: 2rem 2.2rem;
    box-shadow: var(--shadow);
    border: 1px solid rgba(11,29,53,.07);
    margin-bottom: 1.2rem;
    animation: fadeUp .35s ease both;
}
@keyframes fadeUp {
    from { opacity:0; transform:translateY(12px); }
    to   { opacity:1; transform:translateY(0); }
}

/* ── PAGE HEADER ── */
.page-header {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 1.8rem;
    padding-bottom: 1rem;
    border-bottom: 2px solid rgba(11,29,53,.08);
}
.page-header .icon-wrap {
    width: 48px; height: 48px;
    background: linear-gradient(135deg, var(--navy), var(--navy3));
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem;
    box-shadow: 0 4px 14px rgba(11,29,53,.25);
    flex-shrink: 0;
}
.page-header h1 {
    margin: 0; font-size: 1.4rem;
    font-weight: 700; color: var(--navy);
    line-height: 1.2;
}
.page-header p {
    margin: 2px 0 0; font-size: .82rem;
    color: var(--muted); font-weight: 400;
}

/* ── NÚMERO GERADO ── */
.numero-box {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2.2rem;
    font-weight: 700;
    color: var(--navy);
    text-align: center;
    padding: 1.6rem 2rem;
    background: linear-gradient(135deg, #eef3ff 0%, #e4edff 100%);
    border-radius: 16px;
    border: 2px solid #c5d5ff;
    letter-spacing: 3px;
    margin: 1rem 0 .5rem;
    animation: popIn .4s cubic-bezier(.175,.885,.32,1.275) both;
    user-select: all; /* facilita seleção manual */
}
@keyframes popIn {
    from { opacity:0; transform:scale(.88); }
    to   { opacity:1; transform:scale(1); }
}
.numero-meta {
    text-align: center;
    font-size: .82rem;
    color: var(--muted);
    margin-bottom: 1rem;
}

/* ── CLIPBOARD BUTTON ── */
.clip-wrap {
    display: flex;
    justify-content: center;
    margin-top: .6rem;
    margin-bottom: .2rem;
}
.btn-copiar {
    font-family: 'Outfit', sans-serif;
    font-size: .9rem;
    font-weight: 600;
    padding: 10px 32px;
    border-radius: 10px;
    border: none;
    background: linear-gradient(135deg, #0b1d35, #1a3260);
    color: #fff;
    cursor: pointer;
    letter-spacing: .3px;
    box-shadow: 0 4px 14px rgba(11,29,53,.25);
    transition: all .2s ease;
    min-width: 180px;
}
.btn-copiar:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(11,29,53,.35);
}
.btn-copiar.copiado {
    background: linear-gradient(135deg, #059669, #047857) !important;
}

/* ── BADGES ── */
.badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 11px; border-radius: 20px;
    font-size: .73rem; font-weight: 600; letter-spacing: .3px;
}
.badge-green { background:#d1fae5; color:#065f46; }
.badge-red   { background:#fee2e2; color:#991b1b; }
.badge-blue  { background:#dbeafe; color:#1e40af; }
.badge-gold  { background:#fef3c7; color:#92400e; }

/* ── INFO STRIP ── */
.info-strip {
    background: linear-gradient(90deg, #eef3ff, #f8faff);
    border-left: 4px solid var(--navy3);
    border-radius: 0 10px 10px 0;
    padding: 10px 16px;
    margin-bottom: 1.4rem;
    font-size: .84rem;
    color: var(--navy);
}
.info-strip strong { font-weight: 700; }
.info-strip code {
    background: rgba(11,29,53,.08);
    padding: 1px 6px; border-radius: 5px;
    font-family: 'JetBrains Mono', monospace;
    font-size: .8rem;
}

/* ── BOTÕES STREAMLIT ── */
.stButton > button {
    font-family: 'Outfit', sans-serif !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    transition: all .18s ease !important;
    letter-spacing: .2px !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(11,29,53,.18) !important;
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--navy), var(--navy3)) !important;
    border: none !important; color: #fff !important;
}

/* ── TEXTOS VISÍVEIS NA ÁREA PRINCIPAL ── */
.stApp .main *,
.stApp .main p,
.stApp .main span,
.stApp .main label,
.stApp .main div { color: var(--text); }

[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] span,
[data-testid="stWidgetLabel"] label,
div[class*="Label"] p,
div[class*="label"] p,
p[class*="label"],
label { color: var(--text) !important; }

.stCheckbox label p,
.stCheckbox label span,
.stCheckbox [data-testid="stMarkdownContainer"] p,
div[data-baseweb="checkbox"] ~ div p,
div[data-baseweb="checkbox"] label { color: var(--text) !important; }

/* ── INPUTS ── */
.stTextInput input {
    border-radius: 10px !important;
    border: 1.5px solid #cbd5e1 !important;
    background: #fff !important;
    color: var(--text) !important;
    font-family: 'Outfit', sans-serif !important;
    font-size: .93rem !important;
    transition: border-color .15s, box-shadow .15s !important;
}
.stTextInput input:focus {
    border-color: var(--navy3) !important;
    box-shadow: 0 0 0 3px rgba(26,50,96,.10) !important;
    outline: none !important;
}
.stTextInput input::placeholder { color: #94a3b8 !important; }

/* ── SELECT ── */
div[data-baseweb="select"] > div,
div[data-baseweb="select"] input {
    background: #fff !important;
    border-radius: 10px !important;
    border: 1.5px solid #cbd5e1 !important;
    color: var(--text) !important;
    font-family: 'Outfit', sans-serif !important;
}
div[data-baseweb="select"] span { color: var(--text) !important; }
div[data-baseweb="popover"] li { color: var(--text) !important; background: #fff !important; }
div[data-baseweb="popover"] li:hover { background: #f1f5f9 !important; }

/* ── DATAFRAME ── */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    overflow: hidden;
    border: 1px solid #e2e8f0 !important;
}

/* ── LOGIN PAGE ── */
.login-card {
    width: 100%;
    max-width: 420px;
    background: var(--white);
    border-radius: 22px;
    padding: 2.8rem 2.5rem 2.2rem;
    box-shadow: 0 12px 60px rgba(11,29,53,.14);
    border: 1px solid rgba(201,168,76,.15);
    animation: fadeUp .4s ease both;
    margin: 0 auto;
}
.login-title {
    text-align: center;
    font-size: 1.35rem; font-weight: 800;
    color: var(--navy); margin: 0 0 3px;
}
.login-sub {
    text-align: center;
    font-size: .82rem; color: var(--muted);
    margin-bottom: 1.8rem;
    letter-spacing: .3px;
}
.login-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(201,168,76,.4), transparent);
    margin: 1.4rem 0;
}
.login-footer {
    text-align: center;
    font-size: .7rem; color: #94a3b8;
    margin-top: 1.4rem; letter-spacing: .3px;
}

/* ── SIDEBAR FOOTER ── */
.sb-footer {
    padding: 14px 16px;
    border-top: 1px solid rgba(255,255,255,.07);
    margin-top: 24px;
}
.sb-footer .sys-label {
    font-size: .7rem !important;
    color: rgba(255,255,255,.28) !important;
    text-align: center;
    display: block;
}
.sb-footer .by-label {
    font-size: .65rem !important;
    color: rgba(201,168,76,.45) !important;
    text-align: center;
    display: block;
    margin-top: 2px;
}

/* Esconde radio button nativo */
[data-testid="stSidebar"] .stRadio input[type="radio"] { display:none !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  CONSTANTES
# ─────────────────────────────────────────────
TIPOS_DOCUMENTO = [
    "Oficio", "Protocolo", "Despacho", "Ordem de Missão",
    "Relatório Policial",
    "Verificação de Procedência de Informação - VPI",
    "Carta Precatória Expedida", "Carta Precatória Recebida",
    "Intimação",
]

IMG_PATH = "imagens/brasao.png"  # caminho único — muda aqui se necessário

# ─────────────────────────────────────────────
#  UTILS
# ─────────────────────────────────────────────
def hash_pw(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

def verify_pw(plain: str, hashed: str) -> bool:
    return hash_pw(plain) == hashed

def make_token(role: str, ident: str) -> str:
    secret = st.secrets.get("superuser", {}).get("password", "fallback")
    sig = hmac.new(secret.encode(), f"{role}:{ident}".encode(), hashlib.sha256).hexdigest()
    return f"{sig}:{role}:{ident}"

def parse_token(token: str):
    try:
        sig, role, ident = token.split(":", 2)
        if hmac.compare_digest(sig, make_token(role, ident).split(":")[0]):
            return role, ident
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────
#  COOKIES
# ─────────────────────────────────────────────
def _cookie_mgr():
    if not COOKIES_OK:
        return None
    if "_ck_mgr" not in st.session_state:
        st.session_state["_ck_mgr"] = stx.CookieManager(key="ck")
    return st.session_state["_ck_mgr"]

def save_cookie(role, ident):
    cm = _cookie_mgr()
    if cm: cm.set("sess", make_token(role, ident), key="ck_set")

def clear_cookie():
    cm = _cookie_mgr()
    if cm:
        try: cm.delete("sess", key="ck_del")
        except: pass

def restore_cookie():
    cm = _cookie_mgr()
    if not cm: return
    try:
        tok = cm.get("sess")
        if not tok: return
        res = parse_token(tok)
        if not res: return
        role, ident = res
        if role == "superuser":
            st.session_state["role"] = "superuser"
        elif role == "delegacia":
            info = _delegacia_by_username(ident)
            if info:
                st.session_state["role"] = "delegacia"
                st.session_state["delegacia"] = info
    except Exception as e:
        logger.warning("Cookie restore: %s", e)

# ─────────────────────────────────────────────
#  ENGINE
# ─────────────────────────────────────────────
@st.cache_resource
def get_engine():
    s = st.secrets["postgres"]
    pw = quote_plus(s["password"])
    db = s.get("dbname", s.get("database", "postgres"))
    url = f"postgresql://{s['user']}:{pw}@{s['host']}:{s['port']}/{db}"
    return create_engine(url, poolclass=NullPool, future=True,
                         connect_args={"sslmode": "require"})

# ─────────────────────────────────────────────
#  INIT DB
# ─────────────────────────────────────────────
@st.cache_resource
def init_db():
    e = get_engine()
    with e.begin() as c:
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS delegacias (
                id SERIAL PRIMARY KEY, nome TEXT NOT NULL,
                codigo TEXT NOT NULL UNIQUE, username TEXT NOT NULL UNIQUE,
                senha_hash TEXT NOT NULL, ativa BOOLEAN NOT NULL DEFAULT TRUE,
                criada_em TIMESTAMP NOT NULL DEFAULT NOW())"""))
        c.execute(text("DROP TABLE IF EXISTS indices CASCADE"))
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS indices (
                delegacia_id INTEGER NOT NULL REFERENCES delegacias(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL, ultimo_numero BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (delegacia_id, tipo))"""))
        c.execute(text("""
            CREATE TABLE IF NOT EXISTS documentos (
                id SERIAL PRIMARY KEY,
                delegacia_id INTEGER REFERENCES delegacias(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL, numero TEXT NOT NULL UNIQUE,
                destino TEXT, data_emissao TEXT NOT NULL, ano INTEGER)"""))
        c.execute(text("ALTER TABLE documentos ADD COLUMN IF NOT EXISTS ano INTEGER"))
        c.execute(text("ALTER TABLE documentos ADD COLUMN IF NOT EXISTS delegacia_id INTEGER REFERENCES delegacias(id)"))
        c.execute(text("ALTER TABLE documentos ALTER COLUMN destino DROP NOT NULL"))
    logger.info("DB OK")

# ─────────────────────────────────────────────
#  DELEGACIAS CRUD
# ─────────────────────────────────────────────
def listar_delegacias():
    with get_engine().connect() as c:
        return c.execute(text(
            "SELECT id,nome,codigo,username,ativa,criada_em FROM delegacias ORDER BY nome"
        )).fetchall()

def criar_delegacia(nome, codigo, username, password):
    if not all([nome.strip(), codigo.strip(), username.strip(), password.strip()]):
        raise ValueError("Todos os campos são obrigatórios.")
    with get_engine().begin() as c:
        c.execute(text("""
            INSERT INTO delegacias (nome,codigo,username,senha_hash)
            VALUES (:n,:c,:u,:h)"""),
            {"n":nome.strip(),"c":codigo.strip(),"u":username.strip(),"h":hash_pw(password)})

def toggle_delegacia(did, ativa):
    with get_engine().begin() as c:
        c.execute(text("UPDATE delegacias SET ativa=:a WHERE id=:id"), {"a":ativa,"id":did})

def alterar_senha(did, nova):
    if not nova.strip(): raise ValueError("Senha não pode ser vazia.")
    with get_engine().begin() as c:
        c.execute(text("UPDATE delegacias SET senha_hash=:h WHERE id=:id"), {"h":hash_pw(nova),"id":did})

def _delegacia_by_username(u):
    with get_engine().connect() as c:
        row = c.execute(text(
            "SELECT id,nome,codigo,ativa FROM delegacias WHERE username=:u"), {"u":u}).fetchone()
    if row and row.ativa:
        return {"id":row.id,"nome":row.nome,"codigo":row.codigo,"username":u}
    return None

# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────
def check_su(u, p):
    su = st.secrets.get("superuser",{})
    return u == su.get("username") and p == su.get("password")

def check_del(u, p):
    with get_engine().connect() as c:
        row = c.execute(text(
            "SELECT id,nome,codigo,senha_hash,ativa FROM delegacias WHERE username=:u"),{"u":u}).fetchone()
    if not row or not row.ativa or not verify_pw(p, row.senha_hash): return None
    return {"id":row.id,"nome":row.nome,"codigo":row.codigo,"username":u}

# ─────────────────────────────────────────────
#  DOCUMENTOS
# ─────────────────────────────────────────────
def next_num(did, codigo, tipo):
    with get_engine().begin() as c:
        r = c.execute(text("""
            INSERT INTO indices (delegacia_id,tipo,ultimo_numero) VALUES (:d,:t,1)
            ON CONFLICT (delegacia_id,tipo)
            DO UPDATE SET ultimo_numero=indices.ultimo_numero+1
            RETURNING ultimo_numero"""), {"d":did,"t":tipo})
        n = r.scalar_one()
    return f"{codigo}-{int(n):03d}/{datetime.now().year}"

def save_doc(did, codigo, tipo, destino, data_emissao):
    destino = destino.strip() if destino else ""
    while True:
        numero = next_num(did, codigo, tipo)
        try:
            with get_engine().begin() as c:
                c.execute(text("""
                    INSERT INTO documentos (delegacia_id,tipo,numero,destino,data_emissao,ano)
                    VALUES (:d,:t,:n,:de,:da,:a)"""),
                    {"d":did,"t":tipo,"n":numero,"de":destino or None,
                     "da":data_emissao,"a":datetime.now().year})
            return numero
        except IntegrityError:
            continue

def fetch_docs(did=None):
    q = """SELECT d.nome AS delegacia, doc.tipo, doc.numero,
                  COALESCE(doc.destino,'—') AS destino,
                  doc.data_emissao, doc.ano
           FROM documentos doc JOIN delegacias d ON d.id=doc.delegacia_id"""
    params = {}
    if did is not None:
        q += " WHERE doc.delegacia_id=:did"; params={"did":did}
    q += " ORDER BY doc.id DESC"
    return pd.read_sql_query(text(q), con=get_engine(), params=params)

# ─────────────────────────────────────────────
#  UI HELPERS
# ─────────────────────────────────────────────
def page_header(icon: str, title: str, subtitle: str = ""):
    st.markdown(f"""
    <div class="page-header">
        <div class="icon-wrap">{icon}</div>
        <div>
            <h1>{title}</h1>
            {'<p>' + subtitle + '</p>' if subtitle else ''}
        </div>
    </div>""", unsafe_allow_html=True)


def render_logo_html(size: int = 110, css_class: str = "sidebar-logo-wrap") -> str:
    """
    Retorna HTML com a logo em base64.
    Usa emoji de fallback se a imagem não existir.
    """
    b64 = img_to_b64(IMG_PATH)
    if b64:
        return f"""
        <div class="{css_class}">
            <img src="{b64}" alt="Brasão" />
        </div>"""
    else:
        return f"<div class='logo-emoji-fallback'>🏛️</div>"


def render_sidebar_logo(title: str, subtitle: str = ""):
    """Renderiza logo + título na sidebar via HTML puro (sem st.image)."""
    st.sidebar.markdown(render_logo_html(110, "sidebar-logo-wrap"), unsafe_allow_html=True)
    st.sidebar.markdown(f"""
        <div style='text-align:center;padding:0 8px 4px'>
            <div style='font-size:.95rem;font-weight:700;color:#e8f0fa;
                        letter-spacing:.3px'>{title}</div>
            {'<div style="font-size:.75rem;color:#c9a84c;margin-top:3px;letter-spacing:.5px">'
             + subtitle + '</div>' if subtitle else ''}
        </div>
        <div class="gold-divider"></div>
    """, unsafe_allow_html=True)


def sidebar_footer():
    st.sidebar.markdown("""
        <div class="sb-footer">
            <span class="sys-label">Sistema de Numeração de Documentos</span>
            <span class="by-label">by Robson Oliveira</span>
        </div>""", unsafe_allow_html=True)


def info_strip(nome: str, codigo: str):
    st.markdown(f"""
        <div class="info-strip">
            🏛️ &nbsp;<strong>{nome}</strong>
            &nbsp;·&nbsp; Código: <code>{codigo}</code>
        </div>""", unsafe_allow_html=True)


def clipboard_button(texto: str, btn_id: str = "btn-copiar"):
    """
    Botão de copiar robusto:
    - Tenta navigator.clipboard (HTTPS)
    - Fallback: cria textarea temporário + execCommand('copy')
    - Feedback visual de sucesso/falha
    """
    # Escapa aspas simples para não quebrar o JS
    texto_js = texto.replace("'", "\\'")

    st.markdown(f"""
    <div class="clip-wrap">
        <button
            id="{btn_id}"
            class="btn-copiar"
            onclick="copyToClipboard_{btn_id}()"
        >
            📋&nbsp; Copiar Número
        </button>
    </div>

    <script>
    function copyToClipboard_{btn_id}() {{
        var texto = '{texto_js}';
        var btn   = document.getElementById('{btn_id}');

        function onSuccess() {{
            btn.classList.add('copiado');
            btn.innerHTML = '✅&nbsp; Copiado!';
            setTimeout(function() {{
                btn.classList.remove('copiado');
                btn.innerHTML = '📋&nbsp; Copiar Número';
            }}, 2500);
        }}

        function onFail() {{
            btn.innerHTML = '⚠️&nbsp; Erro — copie manualmente';
            setTimeout(function() {{
                btn.innerHTML = '📋&nbsp; Copiar Número';
            }}, 3000);
        }}

        /* ── Tentativa 1: API moderna (requer HTTPS) ── */
        if (navigator.clipboard && window.isSecureContext) {{
            navigator.clipboard.writeText(texto)
                .then(onSuccess)
                .catch(function() {{
                    fallbackCopy(texto, onSuccess, onFail);
                }});
        }} else {{
            /* ── Tentativa 2: execCommand (funciona em HTTP/iframes) ── */
            fallbackCopy(texto, onSuccess, onFail);
        }}
    }}

    function fallbackCopy(texto, onSuccess, onFail) {{
        try {{
            var ta = document.createElement('textarea');
            ta.value = texto;
            /* Esconde o textarea fora da tela */
            ta.style.position = 'fixed';
            ta.style.left     = '-9999px';
            ta.style.top      = '-9999px';
            ta.style.opacity  = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            var ok = document.execCommand('copy');
            document.body.removeChild(ta);
            if (ok) {{ onSuccess(); }} else {{ onFail(); }}
        }} catch(e) {{
            onFail();
        }}
    }}
    </script>
    """, unsafe_allow_html=True)

# ═══════════════════════════════════════════
#  LOGIN
# ═══════════════════════════════════════════
def tela_login():
    if COOKIES_OK:
        _cookie_mgr()

    # 3 colunas para centralizar o card
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        # ── Logo centralizada via HTML puro ──
        st.markdown(render_logo_html(110, "login-logo-wrap"), unsafe_allow_html=True)

        st.markdown("""
            <div class="login-title">Sistema de Documentos</div>
            <div class="login-sub">POLÍCIA CIVIL · ACESSO RESTRITO</div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            usuario = st.text_input("Usuário", placeholder="seu.usuario")
            senha   = st.text_input("Senha",  type="password", placeholder="••••••••")
            lembrar = st.checkbox("🔄 Lembrar de mim neste dispositivo", value=False)
            st.markdown("<br>", unsafe_allow_html=True)
            btn = st.form_submit_button("Entrar  →", use_container_width=True, type="primary")

        if btn:
            if check_su(usuario, senha):
                st.session_state["role"] = "superuser"
                if lembrar and COOKIES_OK: save_cookie("superuser", usuario)
                st.rerun()
            else:
                d = check_del(usuario, senha)
                if d:
                    st.session_state["role"] = "delegacia"
                    st.session_state["delegacia"] = d
                    if lembrar and COOKIES_OK: save_cookie("delegacia", usuario)
                    st.rerun()
                else:
                    st.error("Usuário / senha inválidos ou delegacia inativa.", icon="🚫")

        if not COOKIES_OK:
            st.caption("💡 `pip install extra-streamlit-components` para ativar 'Lembrar de mim'.")

        st.markdown("""
            <div class="login-divider"></div>
            <div class="login-footer">🔒 Acesso exclusivo a servidores autorizados</div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════
#  SUPERUSER
# ═══════════════════════════════════════════
def su_delegacias():
    page_header("🏛️", "Gerenciar Delegacias", "Criar e administrar unidades do sistema")

    with st.expander("➕  Criar Nova Delegacia", expanded=False):
        with st.form("form_nova_del"):
            c1, c2 = st.columns(2)
            with c1:
                nome   = st.text_input("Nome da Delegacia", placeholder="1ª Del. de Itapipoca")
                codigo = st.text_input("Código dos documentos", placeholder="466")
            with c2:
                uname = st.text_input("Usuário de acesso", placeholder="del_itapipoca")
                s1    = st.text_input("Senha inicial", type="password")
                s2    = st.text_input("Confirmar senha", type="password")
            if st.form_submit_button("✅  Criar Delegacia", use_container_width=True):
                if s1 != s2:
                    st.error("As senhas não conferem.")
                else:
                    try:
                        criar_delegacia(nome, codigo, uname, s1)
                        st.success(f"Delegacia **{nome}** criada com sucesso!")
                        st.rerun()
                    except IntegrityError:
                        st.error("Código ou usuário já existem.")
                    except ValueError as e:
                        st.error(str(e))

    st.markdown("---")
    dels = listar_delegacias()
    if not dels:
        st.info("Nenhuma delegacia cadastrada ainda."); return

    st.markdown(f"<p style='color:var(--muted);font-size:.85rem;margin-bottom:1rem'>"
                f"<strong>{len(dels)}</strong> delegacia(s) cadastrada(s)</p>",
                unsafe_allow_html=True)

    for d in dels:
        badge = (f"<span class='badge badge-green'>● Ativa</span>" if d.ativa
                 else f"<span class='badge badge-red'>● Inativa</span>")
        with st.expander(f"**{d.nome}** &nbsp; `{d.codigo}` &nbsp; {badge}"):
            c1, c2, c3 = st.columns([1.2, 1.8, 1.4])
            with c1:
                st.markdown(f"**Usuário:** `{d.username}`")
                criado = d.criada_em.strftime("%d/%m/%Y") if d.criada_em else "—"
                st.markdown(f"<span style='font-size:.78rem;color:var(--muted)'>Criado em {criado}</span>",
                            unsafe_allow_html=True)
                try:
                    df_mini = fetch_docs(d.id)
                    st.markdown(f"<span class='badge badge-blue'>📄 {len(df_mini)} doc(s)</span>",
                                unsafe_allow_html=True)
                except Exception:
                    pass
            with c2:
                with st.form(f"fs_{d.id}"):
                    ns = st.text_input("Nova senha", type="password", key=f"ns_{d.id}",
                                       label_visibility="collapsed", placeholder="Nova senha…")
                    if st.form_submit_button("🔑 Alterar Senha"):
                        try:
                            alterar_senha(d.id, ns); st.success("Senha alterada!")
                        except ValueError as e:
                            st.error(str(e))
            with c3:
                lbl = "🔴 Desativar" if d.ativa else "🟢 Ativar"
                if st.button(lbl, key=f"tog_{d.id}", use_container_width=True):
                    toggle_delegacia(d.id, not d.ativa); st.rerun()

def su_historico():
    page_header("📜", "Histórico Global", "Todos os documentos de todas as delegacias")
    try:
        df = fetch_docs()
        if df.empty: st.info("Nenhum documento registrado."); return
        c1, c2, c3 = st.columns(3)
        with c1:
            fd = st.selectbox("Delegacia", ["Todas"] + sorted(df["delegacia"].unique().tolist()))
        with c2:
            ft = st.selectbox("Tipo", ["Todos"] + sorted(df["tipo"].unique().tolist()))
        with c3:
            ano_opts = ["Todos"] + sorted(df["ano"].dropna().astype(int).unique().tolist(), reverse=True)
            fa = st.selectbox("Ano", ano_opts)
        if fd != "Todas":  df = df[df["delegacia"] == fd]
        if ft != "Todos":  df = df[df["tipo"] == ft]
        if fa != "Todos":  df = df[df["ano"] == int(fa)]
        st.dataframe(df, height=420, use_container_width=True)
        st.markdown(f"<p style='color:var(--muted);font-size:.8rem'>"
                    f"Total: <strong>{len(df)}</strong> documento(s)</p>", unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Erro: {e}")

def su_backup():
    page_header("🛠️", "Backup Global", "Exportação completa do sistema")
    st.info("Gera um CSV com todos os documentos de todas as delegacias.")
    if st.button("💾 Gerar Backup Completo", type="primary"):
        df = fetch_docs()
        st.download_button("📥 Baixar backup_global.csv",
                           df.to_csv(index=False).encode(),
                           "backup_global.csv", "text/csv")
        st.success(f"{len(df)} registros prontos para download.")

def menu_superuser():
    render_sidebar_logo("Superusuário", "ADMINISTRAÇÃO GERAL")
    st.sidebar.markdown("""
        <div style='text-align:center;margin-bottom:14px'>
            <span class='badge badge-gold'>👑 &nbsp;SUPER ADMIN</span>
        </div>""", unsafe_allow_html=True)

    menu = st.sidebar.radio("", [
        "🏛️  Delegacias",
        "📜  Histórico Global",
        "🛠️  Backup Global",
        "🔁  Status",
        "🚪  Sair",
    ])
    sidebar_footer()

    if   "Delegacias"       in menu: su_delegacias()
    elif "Histórico Global" in menu: su_historico()
    elif "Backup"           in menu: su_backup()
    elif "Status"           in menu:
        page_header("🔁", "Status do Sistema")
        st.success("✅ Sistema online e funcionando normalmente.")
    elif "Sair"             in menu:
        clear_cookie(); st.session_state.clear(); st.rerun()

# ═══════════════════════════════════════════
#  DELEGACIA
# ═══════════════════════════════════════════
def del_gerar():
    d = st.session_state["delegacia"]
    page_header("📄", "Gerar Documento", "Preencha o formulário para obter o número oficial")
    info_strip(d["nome"], d["codigo"])

    with st.form("form_doc", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            tipo = st.selectbox("📌 Tipo de Documento", TIPOS_DOCUMENTO)
        with c2:
            destino = st.text_input("✉️ Destino", placeholder="Opcional")

        data_emissao = datetime.today().strftime("%d/%m/%Y")
        st.markdown(
            f"<p style='color:var(--muted);font-size:.84rem;margin:.4rem 0 .8rem'>"
            f"📅 Data de Emissão: <strong>{data_emissao}</strong></p>",
            unsafe_allow_html=True)

        submit = st.form_submit_button("✅  Gerar Número", use_container_width=True, type="primary")

    if submit:
        try:
            numero = save_doc(d["id"], d["codigo"], tipo, destino, data_emissao)
            st.success("Número gerado com sucesso!")
            st.markdown(f"<div class='numero-box'>{numero}</div>", unsafe_allow_html=True)

            dest_txt = f"Destino: <strong>{destino}</strong> &nbsp;·&nbsp;" if destino.strip() else ""
            st.markdown(
                f"<div class='numero-meta'>{dest_txt}Tipo: <strong>{tipo}</strong></div>",
                unsafe_allow_html=True)

            # ── Botão copiar robusto (HTTP + HTTPS) ──
            clipboard_button(numero)

        except Exception as e:
            st.error(f"Erro ao gerar número: {e}")

def del_historico():
    d = st.session_state["delegacia"]
    page_header("📜", "Histórico de Documentos", d["nome"])
    try:
        df = fetch_docs(d["id"])
        if df.empty: st.info("Nenhum documento registrado ainda."); return

        c1, c2, c3 = st.columns(3)
        with c1:
            ft = st.selectbox("Tipo", ["Todos"] + sorted(df["tipo"].unique().tolist()))
        with c2:
            ano_opts = ["Todos"] + sorted(df["ano"].dropna().astype(int).unique().tolist(), reverse=True)
            fa = st.selectbox("Ano", ano_opts)
        with c3:
            busca = st.text_input("🔍 Buscar destino")

        if ft != "Todos": df = df[df["tipo"] == ft]
        if fa != "Todos": df = df[df["ano"] == int(fa)]
        if busca: df = df[df["destino"].str.contains(busca, case=False, na=False)]

        st.dataframe(df.drop(columns=["delegacia"], errors="ignore"),
                     height=400, use_container_width=True)
        st.markdown(f"<p style='color:var(--muted);font-size:.8rem'>"
                    f"Total: <strong>{len(df)}</strong> documento(s)</p>",
                    unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Erro: {e}")

def del_backup():
    d = st.session_state["delegacia"]
    page_header("🛠️", "Backup de Dados", d["nome"])
    if st.button("💾 Gerar Backup", type="primary"):
        df = fetch_docs(d["id"])
        st.download_button("📥 Baixar CSV",
                           df.to_csv(index=False).encode(),
                           f"backup_{d['codigo']}.csv", "text/csv")
        st.success(f"{len(df)} registros prontos para download.")

def menu_delegacia():
    d = st.session_state["delegacia"]
    render_sidebar_logo(d["nome"], d["codigo"])

    menu = st.sidebar.radio("", [
        "📄  Gerar Documento",
        "📜  Histórico",
        "🛠️  Backup",
        "🔁  Status",
        "🚪  Sair",
    ])
    sidebar_footer()

    if   "Gerar"     in menu: del_gerar()
    elif "Histórico" in menu: del_historico()
    elif "Backup"    in menu: del_backup()
    elif "Status"    in menu:
        page_header("🔁", "Status")
        st.success("✅ Sistema online e funcionando normalmente.")
    elif "Sair"      in menu:
        clear_cookie(); st.session_state.clear(); st.rerun()

# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════
def main():
    init_db()

    if "role" not in st.session_state and COOKIES_OK:
        restore_cookie()

    role = st.session_state.get("role")
    if   role == "superuser": menu_superuser()
    elif role == "delegacia":  menu_delegacia()
    else:                      tela_login()

if __name__ == "__main__":
    main()