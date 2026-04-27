# index.py — Sistema de Numeração de Documentos (Multi-Delegacia)
# Refatorado por Claude | Superuser + N delegacias com sequências independentes

from datetime import datetime
import hashlib
import logging

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# UTILS
# ──────────────────────────────────────────────

TIPOS_DOCUMENTO = [
    "Oficio",
    "Protocolo",
    "Despacho",
    "Ordem de Missão",
    "Relatório Policial",
    "Verificação de Procedência de Informação - VPI",
    "Carta Precatória Expedida",
    "Carta Precatória Recebida",
    "Intimação",
]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed


# ──────────────────────────────────────────────
# ENGINE
# ──────────────────────────────────────────────
from sqlalchemy.pool import NullPool   # ← adiciona este import no topo

@st.cache_resource
def get_engine():
    s = st.secrets["postgres"]
    pw = quote_plus(s["password"])
    url = (
        f"postgresql://{s['user']}:{pw}"
        f"@{s['host']}:{s['port']}/{s['dbname']}"
    )
    return create_engine(
        url,
        poolclass=NullPool,            # Supabase pooler já gerencia conexões
        future=True,
        connect_args={"sslmode": "require"},
    )


# ──────────────────────────────────────────────
# INIT DB
# ──────────────────────────────────────────────

@st.cache_resource
def init_db():
    engine = get_engine()
    with engine.begin() as conn:
        # Tabela delegacias
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS delegacias (
                id          SERIAL PRIMARY KEY,
                nome        TEXT NOT NULL,
                codigo      TEXT NOT NULL UNIQUE,
                username    TEXT NOT NULL UNIQUE,
                senha_hash  TEXT NOT NULL,
                ativa       BOOLEAN NOT NULL DEFAULT TRUE,
                criada_em   TIMESTAMP NOT NULL DEFAULT NOW()
            )
        """))

        # ── MIGRAÇÃO: recria indices com nova estrutura ──
        conn.execute(text("DROP TABLE IF EXISTS indices CASCADE"))
        conn.execute(text("""
            CREATE TABLE indices (
                delegacia_id INTEGER NOT NULL REFERENCES delegacias(id) ON DELETE CASCADE,
                tipo         TEXT    NOT NULL,
                ultimo_numero BIGINT  NOT NULL DEFAULT 0,
                PRIMARY KEY (delegacia_id, tipo)
            )
        """))

        # ── MIGRAÇÃO: recria documentos com delegacia_id ──
        conn.execute(text("DROP TABLE IF EXISTS indices CASCADE"))
        conn.execute(text("""
            CREATE TABLE indices (
                delegacia_id INTEGER NOT NULL REFERENCES delegacias(id) ON DELETE CASCADE,
                tipo         TEXT    NOT NULL,
                ultimo_numero BIGINT  NOT NULL DEFAULT 0,
                PRIMARY KEY (delegacia_id, tipo)
            )
        """))

        # ── MIGRAÇÃO: garante colunas novas em documentos ──
        conn.execute(text("ALTER TABLE documentos ADD COLUMN IF NOT EXISTS ano INTEGER"))
        conn.execute(text("ALTER TABLE documentos ADD COLUMN IF NOT EXISTS delegacia_id INTEGER REFERENCES delegacias(id)"))

    logger.info("DB init OK")

# ──────────────────────────────────────────────
# DELEGACIAS — CRUD
# ──────────────────────────────────────────────

def listar_delegacias():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, nome, codigo, username, ativa, criada_em "
            "FROM delegacias ORDER BY nome"
        )).fetchall()
    return rows


def criar_delegacia(nome: str, codigo: str, username: str, password: str):
    if not all([nome.strip(), codigo.strip(), username.strip(), password.strip()]):
        raise ValueError("Todos os campos são obrigatórios.")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO delegacias (nome, codigo, username, senha_hash)
            VALUES (:nome, :codigo, :username, :senha_hash)
        """), {
            "nome": nome.strip(),
            "codigo": codigo.strip(),
            "username": username.strip(),
            "senha_hash": hash_password(password),
        })


def toggle_delegacia(delegacia_id: int, ativa: bool):
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE delegacias SET ativa = :ativa WHERE id = :id"
        ), {"ativa": ativa, "id": delegacia_id})


def alterar_senha_delegacia(delegacia_id: int, nova_senha: str):
    if not nova_senha.strip():
        raise ValueError("Senha não pode ser vazia.")
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE delegacias SET senha_hash = :h WHERE id = :id"
        ), {"h": hash_password(nova_senha), "id": delegacia_id})


# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────

def check_superuser(username: str, password: str) -> bool:
    su = st.secrets.get("superuser", {})
    return (
        username == su.get("username", "")
        and password == su.get("password", "")
    )


def check_delegacia(username: str, password: str):
    """Retorna dict da delegacia ou None."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, nome, codigo, senha_hash, ativa "
            "FROM delegacias WHERE username = :u"
        ), {"u": username}).fetchone()
    if row is None:
        return None
    if not row.ativa:
        return None
    if not verify_password(password, row.senha_hash):
        return None
    return {"id": row.id, "nome": row.nome, "codigo": row.codigo}


# ──────────────────────────────────────────────
# DOCUMENTOS
# ──────────────────────────────────────────────

def get_next_number(delegacia_id: int, codigo: str, tipo: str) -> str:
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(text("""
            INSERT INTO indices (delegacia_id, tipo, ultimo_numero)
            VALUES (:did, :tipo, 1)
            ON CONFLICT (delegacia_id, tipo)
            DO UPDATE SET ultimo_numero = indices.ultimo_numero + 1
            RETURNING ultimo_numero
        """), {"did": delegacia_id, "tipo": tipo})
        novo = result.scalar_one()
    ano = datetime.now().year
    return f"{codigo}-{int(novo):03d}/{ano}"


def save_document(delegacia_id: int, codigo: str, tipo: str, destino: str, data_emissao: str) -> str:
    if not destino or not destino.strip():
        raise ValueError("Destino inválido.")
    while True:
        numero = get_next_number(delegacia_id, codigo, tipo)
        ano = datetime.now().year
        engine = get_engine()
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO documentos (delegacia_id, tipo, numero, destino, data_emissao, ano)
                    VALUES (:did, :tipo, :numero, :destino, :data_emissao, :ano)
                """), {
                    "did": delegacia_id,
                    "tipo": tipo,
                    "numero": numero,
                    "destino": destino,
                    "data_emissao": data_emissao,
                    "ano": ano,
                })
            return numero
        except IntegrityError:
            logger.warning("Colisão em %s, tentando novamente.", numero)
            continue
        except SQLAlchemyError as e:
            logger.exception("Erro ao salvar documento: %s", e)
            raise


def fetch_documentos(delegacia_id: int | None = None) -> pd.DataFrame:
    """Se delegacia_id=None traz todos (superuser)."""
    engine = get_engine()
    base = """
        SELECT d.nome AS delegacia, doc.tipo, doc.numero,
               doc.destino, doc.data_emissao, doc.ano
        FROM documentos doc
        JOIN delegacias d ON d.id = doc.delegacia_id
    """
    if delegacia_id is not None:
        base += " WHERE doc.delegacia_id = :did"
        params = {"did": delegacia_id}
    else:
        params = {}
    base += " ORDER BY doc.id DESC"
    return pd.read_sql_query(text(base), con=engine, params=params)


# ──────────────────────────────────────────────
# BACKUP
# ──────────────────────────────────────────────

def backup_documentos(delegacia_id: int | None = None):
    """Gera CSV em memória e oferece download."""
    try:
        df = fetch_documentos(delegacia_id)
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        fname = "backup_todos.csv" if delegacia_id is None else f"backup_del_{delegacia_id}.csv"
        st.download_button(
            "📥 Baixar CSV",
            data=csv_bytes,
            file_name=fname,
            mime="text/csv",
        )
        st.success(f"✅ {len(df)} registros prontos para download.")
    except Exception as e:
        logger.exception("Erro no backup")
        st.error(f"Erro ao gerar backup: {e}")


# ══════════════════════════════════════════════
# TELAS — SUPERUSER
# ══════════════════════════════════════════════

def tela_su_delegacias():
    st.title("🏛️ Gerenciar Delegacias")

    # ── Criar nova delegacia
    with st.expander("➕ Criar Nova Delegacia", expanded=False):
        with st.form("form_criar_del"):
            col1, col2 = st.columns(2)
            with col1:
                nome = st.text_input("Nome da Delegacia", placeholder="1ª Delegacia de Itapipoca")
                codigo = st.text_input("Código (prefixo dos documentos)", placeholder="466")
            with col2:
                username = st.text_input("Usuário de acesso", placeholder="del_itapipoca")
                senha = st.text_input("Senha inicial", type="password")
                senha2 = st.text_input("Confirmar senha", type="password")

            if st.form_submit_button("✅ Criar Delegacia"):
                if senha != senha2:
                    st.error("As senhas não conferem.")
                else:
                    try:
                        criar_delegacia(nome, codigo, username, senha)
                        st.success(f"Delegacia **{nome}** criada com sucesso!")
                        st.rerun()
                    except IntegrityError:
                        st.error("Código ou usuário já existem. Escolha outros.")
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Erro: {e}")

    st.markdown("---")
    st.subheader("📋 Delegacias Cadastradas")

    delegacias = listar_delegacias()
    if not delegacias:
        st.info("Nenhuma delegacia cadastrada ainda.")
        return

    for d in delegacias:
        status_icon = "🟢" if d.ativa else "🔴"
        with st.expander(f"{status_icon} **{d.nome}** — código `{d.codigo}` | usuário: `{d.username}`"):
            col1, col2 = st.columns(2)
            with col1:
                label_toggle = "🔴 Desativar" if d.ativa else "🟢 Ativar"
                if st.button(label_toggle, key=f"toggle_{d.id}"):
                    toggle_delegacia(d.id, not d.ativa)
                    st.rerun()
            with col2:
                with st.form(f"form_senha_{d.id}"):
                    nova_senha = st.text_input("Nova senha", type="password", key=f"ns_{d.id}")
                    if st.form_submit_button("🔑 Alterar Senha"):
                        try:
                            alterar_senha_delegacia(d.id, nova_senha)
                            st.success("Senha alterada!")
                        except ValueError as e:
                            st.error(str(e))

            # Mini-resumo de documentos
            try:
                df = fetch_documentos(d.id)
                st.caption(f"📄 {len(df)} documento(s) registrado(s)")
            except Exception:
                pass


def tela_su_historico():
    st.title("📜 Histórico Global (Todas as Delegacias)")
    try:
        df = fetch_documentos()
        if df.empty:
            st.info("Nenhum documento registrado.")
            return

        col1, col2 = st.columns(2)
        with col1:
            filtro_del = st.selectbox("Delegacia", ["Todas"] + sorted(df["delegacia"].unique().tolist()))
        with col2:
            filtro_tipo = st.selectbox("Tipo", ["Todos"] + sorted(df["tipo"].unique().tolist()))

        if filtro_del != "Todas":
            df = df[df["delegacia"] == filtro_del]
        if filtro_tipo != "Todos":
            df = df[df["tipo"] == filtro_tipo]

        st.dataframe(df, height=400, use_container_width=True)
        st.caption(f"Total: {len(df)} documento(s)")
    except Exception as e:
        st.error(f"Erro: {e}")


def tela_su_backup():
    st.title("🛠️ Backup Global")
    st.markdown("Exporta **todos** os documentos de todas as delegacias.")
    if st.button("💾 Gerar Backup Global"):
        backup_documentos(delegacia_id=None)


def menu_superuser():
    st.sidebar.image("imagens/brasao.png", width=150)
    st.sidebar.markdown("## 👑 Superusuário")
    menu = st.sidebar.radio("Navegação", [
        "🏛️ Delegacias",
        "📜 Histórico Global",
        "🛠️ Backup Global",
        "🔁 Status",
        "🚪 Sair",
    ])
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<span style='font-size:12px;color:#ccc;'>By Robson Oliveira</span>",
        unsafe_allow_html=True,
    )

    if menu == "🏛️ Delegacias":
        tela_su_delegacias()
    elif menu == "📜 Histórico Global":
        tela_su_historico()
    elif menu == "🛠️ Backup Global":
        tela_su_backup()
    elif menu == "🔁 Status":
        st.title("🔁 Status")
        st.success("✅ Sistema online")
    elif menu == "🚪 Sair":
        st.session_state.clear()
        st.rerun()


# ══════════════════════════════════════════════
# TELAS — DELEGACIA
# ══════════════════════════════════════════════

def tela_gerar_documento():
    delegacia = st.session_state["delegacia"]
    st.title(f"📄 Gerar Documento — {delegacia['nome']}")

    with st.form("form_documento", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            tipo = st.selectbox("📌 Tipo de Documento", TIPOS_DOCUMENTO)
        with col2:
            destino = st.text_input("✉️ Destino")

        data_emissao = datetime.today().strftime("%d/%m/%Y")
        st.text(f"📅 Data de Emissão: {data_emissao}")
        submit = st.form_submit_button("✅ Gerar Número")

    if submit:
        if destino.strip():
            try:
                numero = save_document(
                    delegacia["id"],
                    delegacia["codigo"],
                    tipo,
                    destino,
                    data_emissao,
                )
                st.success(f"📄 Número **{numero}** gerado com sucesso!")
                st.code(numero, language="text")
            except Exception as e:
                st.error(f"Erro ao gerar número: {e}")
        else:
            st.error("Por favor, informe o destino.")


def tela_historico_delegacia():
    delegacia = st.session_state["delegacia"]
    st.title(f"📜 Histórico — {delegacia['nome']}")
    try:
        df = fetch_documentos(delegacia["id"])
        if df.empty:
            st.info("Nenhum documento registrado.")
            return

        filtro_tipo = st.selectbox("Filtrar por Tipo", ["Todos"] + sorted(df["tipo"].unique().tolist()))
        if filtro_tipo != "Todos":
            df = df[df["tipo"] == filtro_tipo]

        st.dataframe(df.drop(columns=["delegacia"], errors="ignore"), height=350, use_container_width=True)
        st.caption(f"Total: {len(df)} documento(s)")
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")


def tela_backup_delegacia():
    delegacia = st.session_state["delegacia"]
    st.title("🛠️ Backup")
    if st.button("💾 Gerar Backup"):
        backup_documentos(delegacia_id=delegacia["id"])


def menu_delegacia():
    delegacia = st.session_state["delegacia"]
    st.sidebar.image("imagens/brasao.png", width=150)
    st.sidebar.markdown(f"## 🏛️ {delegacia['nome']}")
    st.sidebar.markdown(f"**Código:** `{delegacia['codigo']}`")
    menu = st.sidebar.radio("Navegação", [
        "📄 Gerar Documento",
        "📜 Histórico",
        "🛠️ Backup",
        "🔁 Status",
        "🚪 Sair",
    ])
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<span style='font-size:12px;color:#ccc;'>Sistema Multi-Delegacia</span>",
        unsafe_allow_html=True,
    )

    if menu == "📄 Gerar Documento":
        tela_gerar_documento()
    elif menu == "📜 Histórico":
        tela_historico_delegacia()
    elif menu == "🛠️ Backup":
        tela_backup_delegacia()
    elif menu == "🔁 Status":
        st.title("🔁 Status")
        st.success("✅ Sistema online")
    elif menu == "🚪 Sair":
        st.session_state.clear()
        st.rerun()


# ══════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════

def tela_login():
    st.sidebar.image("imagens/brasao.png", width=150)
    st.sidebar.markdown("## 🔒 Acesso Restrito")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("## 🔒 Sistema de Documentos")
        st.markdown("Faça login com as credenciais da sua delegacia ou como superusuário.")

        with st.form("login_form"):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            btn = st.form_submit_button("Entrar", use_container_width=True)

        if btn:
            if check_superuser(username, password):
                st.session_state["role"] = "superuser"
                st.rerun()
            else:
                delegacia = check_delegacia(username, password)
                if delegacia:
                    st.session_state["role"] = "delegacia"
                    st.session_state["delegacia"] = delegacia
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos, ou delegacia inativa.")


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

st.set_page_config(
    page_title="Numerador de Documentos",
    page_icon="📄",
    layout="centered",
    initial_sidebar_state="expanded",
)


def main():
    init_db()

    role = st.session_state.get("role")

    if role == "superuser":
        menu_superuser()
    elif role == "delegacia":
        menu_delegacia()
    else:
        tela_login()


if __name__ == "__main__":
    main()
