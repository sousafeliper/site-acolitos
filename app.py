import streamlit as st
import psycopg2
import psycopg2.pool
import pytz
from datetime import datetime, date, time, timedelta
from typing import List, Dict, Optional, Tuple

# ==================== CONFIGURAÇÃO DA PÁGINA ====================
st.set_page_config(
    page_title="Escala de Acólitos",
    page_icon="⛪️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== ESTILIZAÇÃO CSS ====================
st.markdown("""
    <style>
        .stApp {
            background-color: var(--primary-background-color);
            color: var(--text-color);
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display:none;}
        
        div[data-testid="stMetric"], div[data-testid="stContainer"] {
            background-color: var(--secondary-background-color); 
            padding: 10px;
            border-radius: 10px;
            border: 1px solid rgba(128, 128, 128, 0.2);
        }
        .stTextInput > div > div > input {
            color: var(--text-color);
        }
    </style>
""", unsafe_allow_html=True)

# ==================== OTIMIZAÇÃO DE BANCO (CONNECTION POOL) ====================

@st.cache_resource(ttl=3600, show_spinner=False)
def init_connection_pool():
    """Cria e mantém um pool de conexões com o banco de dados"""
    try:
        database_url = st.secrets.get("DATABASE_URL")
        if database_url:
            # Pool mantém de 1 a 10 conexões abertas
            return psycopg2.pool.ThreadedConnectionPool(1, 40, database_url)
        else:
            st.warning("⚠️ **Configuração de banco de dados não encontrada.**")
            return None
    except Exception as e:
        st.error(f"❌ **Erro ao criar pool de banco de dados:** {str(e)}")
        return None

def get_db_connection():
    """Pega uma conexão disponível do pool"""
    pool = init_connection_pool()
    if pool:
        try:
            conn = pool.getconn()
            conn.autocommit = False
            return conn
        except Exception as e:
            st.error(f"Erro ao conectar: {e}")
            return None
    return None

def release_db_connection(conn):
    """Devolve a conexão para o pool ao invés de fechá-la"""
    pool = init_connection_pool()
    if pool and conn:
        pool.putconn(conn)

# ==================== FUNÇÕES DE BANCO DE DADOS ====================

def criar_tabelas():
    conn = get_db_connection()
    if not conn: return
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS missas (
                id SERIAL PRIMARY KEY,
                data VARCHAR(10) NOT NULL,
                hora VARCHAR(5) NOT NULL,
                descricao TEXT,
                vagas_totais INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inscricoes (
                id SERIAL PRIMARY KEY,
                missa_id INTEGER NOT NULL,
                nome_acolito VARCHAR(255) NOT NULL,
                FOREIGN KEY (missa_id) REFERENCES missas(id) ON DELETE CASCADE,
                UNIQUE(missa_id, nome_acolito)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS acolitos (
                nome TEXT PRIMARY KEY
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historico_pontos (
                id SERIAL PRIMARY KEY,
                nome_acolito VARCHAR(255) NOT NULL,
                data_missa DATE NOT NULL
            )
        """)
        # Novas tabelas para automação
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS missas_padrao (
                id SERIAL PRIMARY KEY,
                dia_semana INTEGER NOT NULL,
                hora VARCHAR(5) NOT NULL,
                descricao TEXT,
                vagas_totais INTEGER NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS controle_geracao (
                semana_id VARCHAR(15) PRIMARY KEY
            )
        """)
        conn.commit()
    except psycopg2.Error as e:
        st.error(f"Erro ao criar tabelas: {e}")
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def arquivar_missas_antigas():
    conn = get_db_connection()
    if not conn: return
    cursor = None
    try:
        cursor = conn.cursor()
        hoje = date.today()
        data_limite = (hoje - timedelta(days=5)).strftime("%Y-%m-%d")
        
        cursor.execute("SELECT id, data FROM missas WHERE data < %s", (data_limite,))
        missas_antigas = cursor.fetchall()
        
        for m_id, m_data in missas_antigas:
            cursor.execute("""
                INSERT INTO historico_pontos (nome_acolito, data_missa)
                SELECT nome_acolito, %s 
                FROM inscricoes 
                WHERE missa_id = %s
            """, (m_data, m_id))
            cursor.execute("DELETE FROM missas WHERE id = %s", (m_id,))
            
        conn.commit()
    except psycopg2.Error as e:
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def obter_missa_por_id(missa_id: int) -> Optional[Dict]:
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT m.id, m.data, m.hora, m.descricao, m.vagas_totais,
                   COUNT(i.id) as vagas_preenchidas,
                   STRING_AGG(i.nome_acolito, ', ' ORDER BY i.nome_acolito) as nomes_inscritos
            FROM missas m
            LEFT JOIN inscricoes i ON m.id = i.missa_id
            WHERE m.id = %s
            GROUP BY m.id
        """, (missa_id,))
        row = cursor.fetchone()
        if row:
            nomes = row[6] if row[6] else None
            nomes_lista = [nome.strip() for nome in nomes.split(',')] if nomes else []
            return {
                'id': row[0], 'data': row[1], 'hora': row[2], 'descricao': row[3],
                'vagas_totais': row[4], 'vagas_preenchidas': row[5] or 0, 'nomes_inscritos': nomes_lista
            }
        return None
    except Exception: return None
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def listar_missas_futuras() -> List[Dict]:
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor()
        hoje = date.today().strftime("%Y-%m-%d")
        
        cursor.execute("""
            SELECT m.id, m.data, m.hora, m.descricao, m.vagas_totais,
                   COUNT(i.id) as vagas_preenchidas,
                   STRING_AGG(i.nome_acolito, ', ' ORDER BY i.nome_acolito) as nomes_inscritos
            FROM missas m
            LEFT JOIN inscricoes i ON m.id = i.missa_id
            WHERE m.data >= %s
            GROUP BY m.id
            ORDER BY m.data, m.hora
        """, (hoje,))
        
        resultados = cursor.fetchall()
        missas = []
        for row in resultados:
            nomes = row[6] if row[6] else None
            nomes_lista = [nome.strip() for nome in nomes.split(',')] if nomes else []
            missas.append({
                'id': row[0], 'data': row[1], 'hora': row[2], 'descricao': row[3],
                'vagas_totais': row[4], 'vagas_preenchidas': row[5] or 0, 'nomes_inscritos': nomes_lista
            })
        return missas
    except psycopg2.Error: return []
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def verificar_inscricao(missa_id: int, nome_acolito: str) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM inscricoes WHERE missa_id = %s AND nome_acolito = %s", (missa_id, nome_acolito))
        return cursor.fetchone()[0] > 0
    except psycopg2.Error: return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def inscrever_acolito(missa_id: int, nome_acolito: str, ignorar_vagas: bool = False) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        if not ignorar_vagas:
            cursor.execute("SELECT m.vagas_totais, COUNT(i.id) FROM missas m LEFT JOIN inscricoes i ON m.id = i.missa_id WHERE m.id = %s GROUP BY m.id", (missa_id,))
            res = cursor.fetchone()
            if not res or res[1] >= res[0]: return False
        
        cursor.execute("INSERT INTO inscricoes (missa_id, nome_acolito) VALUES (%s, %s)", (missa_id, nome_acolito))
        conn.commit()
        return True
    except psycopg2.Error:
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def desinscrever_acolito(missa_id: int, nome_acolito: str) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM inscricoes WHERE missa_id = %s AND nome_acolito = %s", (missa_id, nome_acolito))
        conn.commit()
        return cursor.rowcount > 0
    except psycopg2.Error:
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def cadastrar_missa(data: str, hora: str, descricao: str, vagas_totais: int) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO missas (data, hora, descricao, vagas_totais) VALUES (%s, %s, %s, %s)", (data, hora, descricao, vagas_totais))
        conn.commit()
        return True
    except psycopg2.Error as e:
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def atualizar_missa(missa_id: int, data: str, hora: str, descricao: str, vagas_totais: int) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE missas 
            SET data = %s, hora = %s, descricao = %s, vagas_totais = %s
            WHERE id = %s
        """, (data, hora, descricao, vagas_totais, missa_id))
        conn.commit()
        return True
    except psycopg2.Error:
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def obter_ranking_filtrado(periodo: str = 'anual', data_referencia: date = None):
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.nome_acolito, m.data, m.hora 
            FROM inscricoes i JOIN missas m ON i.missa_id = m.id
        """)
        dados_ativos = cursor.fetchall()
        
        cursor.execute("SELECT nome_acolito, data_missa FROM historico_pontos")
        dados_historicos = cursor.fetchall()
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

    pontuacao = {}
    fuso = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso)
    data_ref = data_referencia if data_referencia else date.today()

    for nome, data_str, hora_str in dados_ativos:
        try:
            dt_str = f"{data_str} {hora_str}"
            dt_missa = fuso.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
            if agora > (dt_missa + timedelta(hours=6)):
                data_obj = dt_missa.date()
                aplicar_filtro_e_pontuar(pontuacao, nome, data_obj, periodo, data_ref)
        except: continue

    for nome, data_obj in dados_historicos:
        if isinstance(data_obj, str):
            try: data_obj = datetime.strptime(data_obj, "%Y-%m-%d").date()
            except: continue
        aplicar_filtro_e_pontuar(pontuacao, nome, data_obj, periodo, data_ref)

    return sorted(pontuacao.items(), key=lambda x: x[1], reverse=True)

def aplicar_filtro_e_pontuar(pontuacao_dict, nome, data_missa, periodo, data_ref):
    if data_missa.year != data_ref.year: return
    if periodo == 'trimestral':
        trimestre_ref = (data_ref.month - 1) // 3 + 1
        trimestre_missa = (data_missa.month - 1) // 3 + 1
        if trimestre_ref != trimestre_missa: return
    if periodo == 'mensal':
        if data_missa.month != data_ref.month: return
    pontuacao_dict[nome] = pontuacao_dict.get(nome, 0) + 1

def listar_todas_missas() -> List[Dict]:
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id, m.data, m.hora, m.descricao, m.vagas_totais, COUNT(i.id)
            FROM missas m LEFT JOIN inscricoes i ON m.id = i.missa_id
            GROUP BY m.id ORDER BY m.data DESC, m.hora DESC
        """)
        resultados = cursor.fetchall()
        missas = []
        for row in resultados:
            missas.append({
                'id': row[0], 'data': row[1], 'hora': row[2], 'descricao': row[3],
                'vagas_totais': row[4], 'vagas_preenchidas': row[5] or 0
            })
        return missas
    except psycopg2.Error: return []
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def listar_inscritos(missa_id: int) -> List[str]:
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT nome_acolito FROM inscricoes WHERE missa_id = %s ORDER BY nome_acolito", (missa_id,))
        return [row[0] for row in cursor.fetchall()]
    except psycopg2.Error: return []
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def excluir_missa(missa_id: int) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM missas WHERE id = %s", (missa_id,))
        res = cursor.fetchone()
        if res:
            data_missa = res[0]
            cursor.execute("""
                INSERT INTO historico_pontos (nome_acolito, data_missa)
                SELECT nome_acolito, %s FROM inscricoes WHERE missa_id = %s
            """, (data_missa, missa_id))
            
        cursor.execute("DELETE FROM inscricoes WHERE missa_id = %s", (missa_id,))
        cursor.execute("DELETE FROM missas WHERE id = %s", (missa_id,))
        conn.commit()
        return True
    except psycopg2.Error as e:
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def remover_inscricao_admin(missa_id: int, nome_acolito: str) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM inscricoes WHERE missa_id = %s AND nome_acolito = %s", (missa_id, nome_acolito))
        conn.commit()
        return cursor.rowcount > 0
    except psycopg2.Error:
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def listar_acolitos() -> List[str]:
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT nome FROM acolitos ORDER BY nome")
        return [row[0] for row in cursor.fetchall()]
    except psycopg2.Error: return []
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def cadastrar_acolito(nome: str) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO acolitos (nome) VALUES (%s)", (nome.strip(),))
        conn.commit()
        return True
    except psycopg2.Error: return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def remover_acolito(nome: str) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM acolitos WHERE nome = %s", (nome,))
        conn.commit()
        return cursor.rowcount > 0
    except psycopg2.Error: return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def alterar_nome_acolito(nome_antigo: str, nome_novo: str) -> bool:
    """Atualiza o nome do acólito em todas as tabelas para preservar o histórico."""
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Atualiza o nome nas 3 tabelas em que ele aparece
        cursor.execute("UPDATE acolitos SET nome = %s WHERE nome = %s", (nome_novo.strip(), nome_antigo))
        cursor.execute("UPDATE inscricoes SET nome_acolito = %s WHERE nome_acolito = %s", (nome_novo.strip(), nome_antigo))
        cursor.execute("UPDATE historico_pontos SET nome_acolito = %s WHERE nome_acolito = %s", (nome_novo.strip(), nome_antigo))
        
        conn.commit()
        return True
    except psycopg2.Error as e:
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

# ==================== FUNÇÕES DA AUTOMAÇÃO DE MISSAS ====================

def cadastrar_missa_padrao(dia_semana: int, hora: str, descricao: str, vagas_totais: int) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO missas_padrao (dia_semana, hora, descricao, vagas_totais) VALUES (%s, %s, %s, %s)", 
                       (dia_semana, hora, descricao, vagas_totais))
        conn.commit()
        return True
    except psycopg2.Error:
        if conn: conn.rollback()
        return False
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def listar_missas_padrao() -> List[Dict]:
    conn = get_db_connection()
    if not conn: return []
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, dia_semana, hora, descricao, vagas_totais FROM missas_padrao ORDER BY dia_semana, hora")
        return [{'id': r[0], 'dia_semana': r[1], 'hora': r[2], 'descricao': r[3], 'vagas_totais': r[4]} for r in cursor.fetchall()]
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def excluir_missa_padrao(padrao_id: int) -> bool:
    conn = get_db_connection()
    if not conn: return False
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM missas_padrao WHERE id = %s", (padrao_id,))
        conn.commit()
        return True
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

def gerar_missas_automaticamente():
    """Gera as missas da próxima semana se já passou de sábado às 12:59"""
    conn = get_db_connection()
    if not conn: return
    cursor = None
    try:
        cursor = conn.cursor()
        fuso = pytz.timezone('America/Sao_Paulo')
        agora = datetime.now(fuso)
        
        # Checa se passou de Sábado 12:59 (weekday: 5 = Sábado, 6 = Domingo)
        passou_limite = agora.weekday() == 6 or (agora.weekday() == 5 and (agora.hour > 12 or (agora.hour == 12 and agora.minute >= 59)))
        
        if passou_limite:
            # Encontra a data da próxima SEGUNDA-FEIRA
            dias_para_segunda = (7 - agora.weekday()) % 7
            if dias_para_segunda == 0: dias_para_segunda = 7
            proxima_segunda = agora.date() + timedelta(days=dias_para_segunda)
            
            # O ID da semana será a data da próxima segunda-feira (Ex: "2026-05-11")
            id_semana = proxima_segunda.strftime("%Y-%m-%d")
            
            cursor.execute("SELECT COUNT(*) FROM controle_geracao WHERE semana_id = %s", (id_semana,))
            if cursor.fetchone()[0] == 0:
                # Ainda não foi gerado. Vamos gerar!
                cursor.execute("SELECT dia_semana, hora, descricao, vagas_totais FROM missas_padrao")
                padroes = cursor.fetchall()
                
                for dia, hora, desc, vagas in padroes:
                    # Calcula o dia exato da missa (0=Segunda, 6=Domingo)
                    data_missa = proxima_segunda + timedelta(days=dia)
                    cursor.execute("""
                        INSERT INTO missas (data, hora, descricao, vagas_totais) 
                        VALUES (%s, %s, %s, %s)
                    """, (data_missa.strftime("%Y-%m-%d"), hora, desc, vagas))
                
                # Salva no banco que esta semana já foi gerada
                cursor.execute("INSERT INTO controle_geracao (semana_id) VALUES (%s)", (id_semana,))
                conn.commit()
    except psycopg2.Error:
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        release_db_connection(conn)

# ==================== FUNÇÕES DE INTERFACE / UI ====================

@st.dialog("➕ Criar Nova Missa")
def modal_nova_missa():
    with st.form("new_mass", clear_on_submit=True):
        dt = st.date_input("Data", min_value=date.today())
        hr = st.time_input("Hora", value=time(19, 0))
        desc = st.text_input("Descrição (Ex: Missa Solene)")
        vagas = st.number_input("Vagas", 0, 50, 2)
        if st.form_submit_button("Salvar Missa", type="primary", use_container_width=True):
            if cadastrar_missa(dt.strftime("%Y-%m-%d"), hr.strftime("%H:%M"), desc, vagas):
                st.toast("✅ Missa criada com sucesso!")
                st.rerun()

@st.dialog("✏️ Editar Dados da Missa")
def modal_editar_missa(m):
    with st.form(f"edit_mass_form_{m['id']}"):
        try: m_dt = datetime.strptime(m['data'], "%Y-%m-%d").date()
        except: m_dt = date.today()
        try: m_hr = datetime.strptime(m['hora'], "%H:%M").time()
        except: m_hr = time(19, 0)
        
        c_d, c_h = st.columns(2)
        new_dt = c_d.date_input("Data", value=m_dt)
        new_hr = c_h.time_input("Hora", value=m_hr)
        new_desc = st.text_input("Descrição", value=m['descricao'])
        new_vagas = st.number_input("Vagas Totais", 0, 50, value=m['vagas_totais'])
        
        if st.form_submit_button("Salvar Alterações", type="primary", use_container_width=True):
            if atualizar_missa(m['id'], new_dt.strftime("%Y-%m-%d"), new_hr.strftime("%H:%M"), new_desc, new_vagas):
                st.toast("✅ Missa atualizada!")
                st.rerun()

@st.dialog("✏️ Renomear Acólito")
def modal_renomear_acolito(nome_atual: str):
    with st.form(f"edit_ac_form_{nome_atual}"):
        novo_nome = st.text_input("Novo Nome", value=nome_atual)
        
        if st.form_submit_button("Salvar Alteração", type="primary", use_container_width=True):
            if novo_nome.strip() and novo_nome.strip() != nome_atual:
                if alterar_nome_acolito(nome_atual, novo_nome):
                    st.toast("✅ Nome atualizado com sucesso em todo o histórico!")
                    st.rerun()
                else:
                    st.error("Erro ao alterar o nome.")
            elif novo_nome.strip() == nome_atual:
                st.warning("O nome inserido é igual ao atual.")
            else:
                st.warning("O nome não pode ficar vazio.")

@st.fragment
def renderizar_card_missa(missa_id: int, nome_usuario: str):
    """Componente otimizado para Mobile (Container em vez de colunas)"""
    missa = obter_missa_por_id(missa_id)
    if not missa:
        st.error("Missa não encontrada.")
        return

    try:
        d_obj = datetime.strptime(missa['data'], "%Y-%m-%d")
        d_fmt = d_obj.strftime("%d/%m")
        dia = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][d_obj.weekday()]
    except: d_fmt, dia = missa['data'], ""

    with st.container(border=True):
        st.markdown(f"### {missa['descricao'] or 'Santa Missa'}")
        st.markdown(f"🗓️ **{dia}, {d_fmt}** às **{missa['hora']}**")
        
        progresso = missa['vagas_preenchidas'] / missa['vagas_totais'] if missa['vagas_totais'] > 0 else 0
        st.progress(progresso)
        st.caption(f"👥 **{missa['vagas_preenchidas']}/{missa['vagas_totais']} vagas preenchidas**")
        
        if missa['nomes_inscritos']:
            st.info(f"✨ **Escalados:** {', '.join(missa['nomes_inscritos'])}")
        
        st.write("") # Espaçador natural
        esta_inscrito = verificar_inscricao(missa['id'], nome_usuario)
        
        if esta_inscrito:
            if st.button("❌ Cancelar minha Inscrição", key=f"btn_sair_{missa['id']}", use_container_width=True):
                if desinscrever_acolito(missa['id'], nome_usuario):
                    st.toast("Você saiu da escala.")
        elif missa['vagas_preenchidas'] < missa['vagas_totais']:
            if st.button("✅ Servir nesta Missa", key=f"btn_entrar_{missa['id']}", type="primary", use_container_width=True):
                if inscrever_acolito(missa['id'], nome_usuario):
                    st.toast("Inscrição confirmada!")
        else:
            st.button("🔒 Escala Lotada", key=f"btn_lotado_{missa['id']}", disabled=True, use_container_width=True)

def tela_login():
    col_vazia_esq, col_centro, col_vazia_dir = st.columns([1, 1.5, 1])
    with col_centro:
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center;'>⛪️</h1>", unsafe_allow_html=True)
            st.markdown("<h2 style='text-align: center;'>Escala de Acólitos</h2>", unsafe_allow_html=True)
            st.caption("Sistema de agendamento e controle de escala")
            st.divider()
            
            st.markdown("##### 👤 Acesso do Acólito")
            acolitos = listar_acolitos()
            
            if not acolitos:
                st.warning("⚠️ Nenhum acólito cadastrado.")
                nome_selecionado = None
            else:
                nome_selecionado = st.selectbox("Selecione seu nome", options=[""] + acolitos, key="select_nome")
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Entrar", type="primary", use_container_width=True):
                    if nome_selecionado and nome_selecionado.strip():
                        st.session_state['usuario'] = nome_selecionado.strip()
                        st.session_state['tela'] = 'escala'
                        st.rerun()
                    else:
                        st.toast("Selecione seu nome.")
            with col_btn2:
                if st.button("Sair", use_container_width=True):
                    if 'usuario' in st.session_state: del st.session_state['usuario']
                    st.rerun()
            
            st.divider()
            with st.expander("🔐 Área do Coordenador"):
                is_coordenador = st.checkbox("Confirmar acesso administrativo")
                if is_coordenador:
                    senha = st.text_input("Senha", type="password")
                    if st.button("Acessar", type="secondary", use_container_width=True):
                        if senha == st.secrets["ADMIN_SENHA"]:
                            st.session_state['tela'] = 'admin'
                            st.rerun()
                        else:
                            st.error("Senha incorreta!")

def tela_escala():
    nome = st.session_state.get('usuario', 'Usuário')
    col_header, col_sair = st.columns([5, 1])
    with col_header:
        st.title(f"Olá, {nome}!")
        st.caption(f"Hoje é {date.today().strftime('%d/%m/%Y')}.")
    with col_sair:
        st.write("")
        if st.button("Sair", use_container_width=True):
            if 'usuario' in st.session_state: del st.session_state['usuario']
            st.session_state['tela'] = 'login'
            st.rerun()
    
    st.divider()
    tab_missas, tab_ranking = st.tabs(["📅 Próximas Missas", "🏆 Ranking Mês Atual"])

    with tab_missas:
        st.subheader("Missas Disponíveis")
        missas = listar_missas_futuras()
        if not missas:
            st.info("📭 Nenhuma missa agendada no momento. Aproveite o descanso!")
        else:
            for missa in missas:
                try:
                    fuso = pytz.timezone('America/Sao_Paulo')
                    agora = datetime.now(fuso)
                    dt_str = f"{missa['data']} {missa['hora']}"
                    dt_missa = fuso.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
                    if agora > (dt_missa + timedelta(hours=6)): continue
                except: pass
                
                renderizar_card_missa(missa['id'], nome)

    with tab_ranking:
        st.subheader(f"Ranking de {date.today().strftime('%B').capitalize()}")
        ranking = obter_ranking_filtrado('mensal') 
        if ranking:
            for i, (nome_r, pontos) in enumerate(ranking, 1):
                st.write(f"**{i}º** {nome_r} - {pontos} pts")
        else:
            st.info("🏆 O mês acabou de começar! Inscreva-se em uma missa para liderar o ranking.")

def render_ranking_table(dados, titulo):
    st.markdown(f"### {titulo}")
    if dados:
        col1, col2 = st.columns([1, 2])
        with col1:
            top3 = dados[:3]
            for i, (n, p) in enumerate(top3, 1):
                em = "🥇" if i==1 else "🥈" if i==2 else "🥉"
                st.metric(f"{em} {i}º", str(p), n)
        with col2:
            st.dataframe(
                [{"Pos": f"{i}º", "Acólito": n, "Pontos": p} for i, (n, p) in enumerate(dados, 1)],
                hide_index=True, use_container_width=True
            )
    else:
        st.info("Sem dados consolidados para este período.")

@st.fragment
def fragment_missas_padrao():
    st.info("🤖 **Automação:** Missas cadastradas aqui aparecerão na escala automaticamente todo Sábado às 12:59 para a semana seguinte (Segunda a Domingo).")
    
    with st.form("form_novo_padrao", clear_on_submit=True):
        c1, c2 = st.columns(2)
        dias_dict = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
        dia_sel = c1.selectbox("Dia da Semana", options=list(dias_dict.keys()), format_func=lambda x: dias_dict[x])
        hr_sel = c2.time_input("Hora", value=time(19, 0))
        desc_sel = st.text_input("Descrição (Ex: Missa Paroquial)")
        vagas_sel = st.number_input("Vagas", 1, 50, 2)
        
        if st.form_submit_button("➕ Salvar na Rotina", type="primary"):
            cadastrar_missa_padrao(dia_sel, hr_sel.strftime("%H:%M"), desc_sel, vagas_sel)
            st.rerun(scope="fragment")

    st.divider()
    st.write("📋 **Rotina Semanal Cadastrada**")
    padroes = listar_missas_padrao()
    if not padroes:
        st.caption("Nenhuma missa padrão cadastrada ainda.")
    else:
        for p in padroes:
            c_texto, c_btn = st.columns([4, 1])
            c_texto.write(f"**{dias_dict[p['dia_semana']]}** às **{p['hora']}** - {p['descricao']} ({p['vagas_totais']} vagas)")
            if c_btn.button("🗑️", key=f"del_padrao_{p['id']}", use_container_width=True):
                excluir_missa_padrao(p['id'])
                st.rerun(scope="fragment")

@st.fragment
def fragment_agenda():
    col_titulo, col_btn = st.columns([3, 1])
    with col_titulo:
        st.subheader("Missas Ativas")
    with col_btn:
        if st.button("➕ Nova Missa", use_container_width=True):
            modal_nova_missa()
            
    st.divider()
    missas = listar_todas_missas()
    
    if not missas:
        st.info("📭 Nenhuma missa cadastrada no sistema.")
        
    for m in missas:
        try:
            fuso = pytz.timezone('America/Sao_Paulo')
            agora = datetime.now(fuso)
            dt_missa = fuso.localize(datetime.strptime(f"{m['data']} {m['hora']}", "%Y-%m-%d %H:%M"))
            if agora > (dt_missa + timedelta(hours=6)): continue
        except: pass

        with st.expander(f"{m['data']} - {m['descricao']} ({m['vagas_preenchidas']}/{m['vagas_totais']})"):
            
            # Botões de Ação na Missa
            col_edit, col_del = st.columns(2)
            with col_edit:
                if st.button("✏️ Editar Missa", key=f"btn_edit_{m['id']}", use_container_width=True):
                    modal_editar_missa(m)
            with col_del:
                if st.button("🗑️ Excluir", key=f"btn_del_req_{m['id']}", use_container_width=True):
                    st.session_state[f"confirm_del_{m['id']}"] = True
            
            # Dupla Confirmação de Exclusão
            if st.session_state.get(f"confirm_del_{m['id']}", False):
                st.warning("⚠️ **Tem certeza?** Esta ação apagará as inscrições da missa.")
                c1, c2 = st.columns(2)
                if c1.button("✅ Sim, Excluir", key=f"del_conf_{m['id']}", type="primary", use_container_width=True):
                    excluir_missa(m['id'])
                    del st.session_state[f"confirm_del_{m['id']}"]
                    st.rerun(scope="fragment")
                if c2.button("❌ Cancelar", key=f"del_canc_{m['id']}", use_container_width=True):
                    del st.session_state[f"confirm_del_{m['id']}"]
                    st.rerun(scope="fragment")
            
            st.divider()
            st.write("👥 **Inscritos**")
            inscritos = listar_inscritos(m['id'])
            if inscritos:
                for u in inscritos:
                    c1, c2 = st.columns([4, 1])
                    c1.text(f"• {u}")
                    if c2.button("❌", key=f"rm_{m['id']}_{u}"):
                        remover_inscricao_admin(m['id'], u)
                        st.rerun(scope="fragment")
            else: 
                st.caption("Nenhum acólito inscrito ainda.")
                
            # NOVA FUNCIONALIDADE: Adicionar múltiplos acólitos
            st.divider()
            st.write("➕ **Adicionar Acólitos à Escala**")
            
            todos_acolitos = listar_acolitos()
            # Filtra os acólitos que já estão inscritos para evitar duplicidade
            disponiveis = [a for a in todos_acolitos if a not in inscritos]
            
            if disponiveis:
                selecionados = st.multiselect(
                    "Selecione os acólitos:", 
                    options=disponiveis, 
                    key=f"multi_add_{m['id']}",
                    placeholder="Escolha um ou mais..."
                )
                
                if st.button("Adicionar Selecionados", key=f"btn_multi_add_{m['id']}", type="secondary", use_container_width=True):
                    if selecionados:
                        for ac in selecionados:
                            # Ignoramos o limite de vagas porque é o coordenador que está adicionando
                            inscrever_acolito(m['id'], ac, ignorar_vagas=True) 
                        st.toast(f"✅ {len(selecionados)} acólito(s) adicionado(s) com sucesso!")
                        st.rerun(scope="fragment")
                    else:
                        st.warning("Selecione ao menos um acólito na lista acima.")
            else:
                st.caption("✨ Todos os acólitos cadastrados já estão nesta missa.")

@st.fragment
def fragment_historico():
    st.info("Missas finalizadas (+6h) que ainda não foram arquivadas.")
    missas = listar_todas_missas()
    for m in missas:
        mostrar = False
        try:
            fuso = pytz.timezone('America/Sao_Paulo')
            agora = datetime.now(fuso)
            dt_missa = fuso.localize(datetime.strptime(f"{m['data']} {m['hora']}", "%Y-%m-%d %H:%M"))
            if agora > (dt_missa + timedelta(hours=6)): mostrar = True
        except: pass
        
        if mostrar:
            with st.expander(f"✅ {m['data']} - {m['descricao']}"):
                insc = listar_inscritos(m['id'])
                st.write(f"Pontuaram: {', '.join(insc) if insc else 'Ninguém'}")
                acolito_add = st.selectbox("Adicionar manual (Excede vagas):", [""] + listar_acolitos(), key=f"sa_{m['id']}")
                if st.button("Adicionar Ponto", key=f"ba_{m['id']}"):
                    if acolito_add: 
                        inscrever_acolito(m['id'], acolito_add, ignorar_vagas=True)
                        st.rerun(scope="fragment")

def tela_admin():
    st.title("⚙️ Painel do Coordenador")
    if st.button("← Voltar / Sair"):
        st.session_state['tela'] = 'login'
        st.rerun()
    st.divider()
    
    # Aba 2 nova adicionada aqui:
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Agenda", "🔁 Padrão Semanal", "👥 Equipe", "🏆 Rankings", "📜 Histórico"])
    
    with tab1: # AGENDA
        fragment_agenda()

    with tab2: # PADRÃO SEMANAL
        fragment_missas_padrao()

    with tab3: # EQUIPE
        c_add, c_view = st.columns([1, 2])
        
        with c_add:
            with st.form("add_ac", clear_on_submit=True):
                nm = st.text_input("Nome do Novo Acólito")
                if st.form_submit_button("Adicionar", type="primary", use_container_width=True):
                    if nm and nm.strip():
                        cadastrar_acolito(nm)
                        st.rerun()
                        
        with c_view:
            st.markdown("#### Acólitos Ativos")
            
            acolitos_lista = listar_acolitos()
            if not acolitos_lista:
                st.info("Nenhum acólito cadastrado.")
                
            for ac in acolitos_lista:
                with st.container(border=True): # Container visual para organizar melhor os botões
                    c1, c_edit, c_del = st.columns([3, 1, 1])
                    
                    c1.write(f"👤 **{ac}**")
                    
                    # 1) Botão de Editar Nome
                    if c_edit.button("✏️", key=f"edit_ac_{ac}", use_container_width=True):
                        modal_renomear_acolito(ac)
                        
                    # 2) Botão de Deletar (com trava de confirmação)
                    if c_del.button("🗑️", key=f"btn_del_req_ac_{ac}", use_container_width=True):
                        st.session_state[f"confirm_del_ac_{ac}"] = True

                    # 3) Dupla Confirmação de Exclusão
                    if st.session_state.get(f"confirm_del_ac_{ac}", False):
                        st.warning(f"⚠️ **Tem certeza que deseja excluir '{ac}'?**")
                        cd1, cd2 = st.columns(2)
                        
                        if cd1.button("✅ Sim, Excluir", key=f"del_ac_sim_{ac}", type="primary", use_container_width=True):
                            if remover_acolito(ac):
                                st.toast(f"Acólito {ac} excluído.")
                            del st.session_state[f"confirm_del_ac_{ac}"]
                            st.rerun(scope="fragment")
                            
                        if cd2.button("❌ Cancelar", key=f"del_ac_nao_{ac}", use_container_width=True):
                            del st.session_state[f"confirm_del_ac_{ac}"]
                            st.rerun(scope="fragment")

    with tab4: # RANKINGS
        st.subheader("Painel de Pontuação")
        st.caption("Selecione o período de referência para visualizar os rankings.")
        c_mes, c_ano, c_vazio = st.columns([1, 1, 2])
        
        meses = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
                 7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
        
        hj = date.today()
        
        with c_mes:
            sel_mes_num = st.selectbox("Mês", options=list(meses.keys()), 
                                       format_func=lambda x: meses[x], index=hj.month-1)
        with c_ano:
            sel_ano = st.number_input("Ano", min_value=2024, max_value=2030, value=hj.year)
            
        data_referencia = date(sel_ano, sel_mes_num, 1)

        rt1, rt2, rt3 = st.tabs(["📅 Mensal", "📊 Trimestral", "📆 Anual"])
        
        with rt1:
            render_ranking_table(obter_ranking_filtrado('mensal', data_referencia), f"Ranking: {meses[sel_mes_num]}/{sel_ano}")
        with rt2:
            trimestre = (sel_mes_num - 1) // 3 + 1
            render_ranking_table(obter_ranking_filtrado('trimestral', data_referencia), f"Ranking: {trimestre}º Trimestre/{sel_ano}")
        with rt3:
            render_ranking_table(obter_ranking_filtrado('anual', data_referencia), f"Ranking: Ano {sel_ano}")

    with tab5: # HISTORICO
        fragment_historico()

# ==================== MAIN ====================

def main():
    criar_tabelas()
    arquivar_missas_antigas()
    gerar_missas_automaticamente() # <--- Automação conectada aqui
    
    if 'tela' not in st.session_state:
        st.session_state['tela'] = 'login'
    
    if st.session_state['tela'] == 'login': tela_login()
    elif st.session_state['tela'] == 'escala': tela_escala()
    elif st.session_state['tela'] == 'admin': tela_admin()

if __name__ == "__main__":
    main()
