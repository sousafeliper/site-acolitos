import streamlit as st
import psycopg2
import pytz 
from datetime import datetime, date, time, timedelta 
from typing import List, Dict, Optional

# ==================== CONFIGURAÇÃO INICIAL E ESTILO ====================

st.set_page_config(
    page_title="Escala de Acólitos",
    page_icon="⛪️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def aplicar_estilo():
    """Aplica CSS personalizado para melhorar a UI"""
    st.markdown("""
        <style>
            /* Fonte e cores gerais */
            .stApp {
                background-color: #f8f9fa;
            }
            
            /* Estilo dos Cards (Containers com borda) */
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background-color: white;
                border-radius: 10px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                padding: 1rem;
                margin-bottom: 1rem;
            }

            /* Títulos centralizados na Login */
            .login-header {
                text-align: center;
                color: #2c3e50;
                margin-bottom: 2rem;
            }
            
            /* Melhoria nos botões */
            div.stButton > button {
                border-radius: 8px;
                font-weight: 600;
                transition: all 0.3s ease;
            }
            
            /* Remove menu padrão do Streamlit para visual app-like */
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            .stDeployButton {display:none;}
            
            /* Ajuste de Tabs */
            .stTabs [data-baseweb="tab-list"] {
                gap: 10px;
            }
            .stTabs [data-baseweb="tab"] {
                height: 50px;
                white-space: pre-wrap;
                background-color: white;
                border-radius: 5px;
                padding: 10px 20px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .stTabs [aria-selected="true"] {
                background-color: #e8f0fe;
                color: #1a73e8;
                border-bottom: 2px solid #1a73e8;
            }
        </style>
    """, unsafe_allow_html=True)

# Aplica o estilo imediatamente
aplicar_estilo()


# ==================== FUNÇÃO DE CONEXÃO ====================

def get_db_connection():
    """
    Cria e retorna uma nova conexão com o banco de dados PostgreSQL.
    NÃO usa cache - cria uma nova conexão a cada chamada para garantir estabilidade.
    """
    try:
        # Tenta pegar a URL do banco dos secrets do Streamlit
        database_url = st.secrets.get("DATABASE_URL")
        if database_url:
            conn = psycopg2.connect(database_url)
            conn.autocommit = False
            return conn
        else:
            # Se não encontrar nos secrets, exibe aviso
            st.warning("⚠️ **Configuração de banco de dados não encontrada.**")
            st.info("Para usar localmente, configure `st.secrets['DATABASE_URL']` ou use um arquivo `.streamlit/secrets.toml`")
            return None
    except Exception as e:
        st.error(f"❌ **Erro ao conectar ao banco de dados:** {str(e)}")
        st.info("💡 Verifique se a variável `DATABASE_URL` está configurada corretamente nos secrets do Streamlit.")
        return None

# ==================== FUNÇÕES DE BANCO DE DADOS ====================

def criar_tabelas():
    """Cria as tabelas do banco de dados se não existirem"""
    conn = get_db_connection()
    if not conn:
        return
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Tabela de missas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS missas (
                id SERIAL PRIMARY KEY,
                data VARCHAR(10) NOT NULL,
                hora VARCHAR(5) NOT NULL,
                descricao TEXT,
                vagas_totais INTEGER NOT NULL
            )
        """)
        
        # Tabela de inscrições
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inscricoes (
                id SERIAL PRIMARY KEY,
                missa_id INTEGER NOT NULL,
                nome_acolito VARCHAR(255) NOT NULL,
                FOREIGN KEY (missa_id) REFERENCES missas(id) ON DELETE CASCADE,
                UNIQUE(missa_id, nome_acolito)
            )
        """)
        
        # Tabela de acólitos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS acolitos (
                nome TEXT PRIMARY KEY
            )
        """)
        
        conn.commit()
    except psycopg2.Error as e:
        st.error(f"Erro ao criar tabelas: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def listar_missas_futuras() -> List[Dict]:
    """Retorna lista de missas futuras ordenadas por data"""
    conn = get_db_connection()
    if not conn:
        return []
    
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
                'id': row[0],
                'data': row[1],
                'hora': row[2],
                'descricao': row[3],
                'vagas_totais': row[4],
                'vagas_preenchidas': row[5] or 0,
                'nomes_inscritos': nomes_lista
            })
        
        return missas
    except psycopg2.Error as e:
        st.error(f"Erro ao listar missas: {e}")
        if conn:
            conn.rollback()
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def verificar_inscricao(missa_id: int, nome_acolito: str) -> bool:
    """Verifica se o acólito já está inscrito na missa"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM inscricoes
            WHERE missa_id = %s AND nome_acolito = %s
        """, (missa_id, nome_acolito))
        
        resultado = cursor.fetchone()[0] > 0
        return resultado
    except psycopg2.Error as e:
        st.error(f"Erro ao verificar inscrição: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def inscrever_acolito(missa_id: int, nome_acolito: str) -> bool:
    """Inscreve um acólito em uma missa (com verificação de concorrência)"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Verificar se ainda há vagas disponíveis
        cursor.execute("""
            SELECT m.vagas_totais, COUNT(i.id) as vagas_preenchidas
            FROM missas m
            LEFT JOIN inscricoes i ON m.id = i.missa_id
            WHERE m.id = %s
            GROUP BY m.id
        """, (missa_id,))
        
        resultado = cursor.fetchone()
        if not resultado:
            return False
        
        vagas_totais, vagas_preenchidas = resultado
        
        if vagas_preenchidas >= vagas_totais:
            return False
        
        # Verificar se já está inscrito (usando o mesmo cursor)
        cursor.execute("""
            SELECT COUNT(*) FROM inscricoes
            WHERE missa_id = %s AND nome_acolito = %s
        """, (missa_id, nome_acolito))
        
        if cursor.fetchone()[0] > 0:
            return False
        
        # Inserir inscrição
        cursor.execute("""
            INSERT INTO inscricoes (missa_id, nome_acolito)
            VALUES (%s, %s)
        """, (missa_id, nome_acolito))
        
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        # Já está inscrito (constraint UNIQUE)
        if conn:
            conn.rollback()
        return False
    except psycopg2.Error as e:
        st.error(f"Erro ao inscrever acólito: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def desinscrever_acolito(missa_id: int, nome_acolito: str) -> bool:
    """Remove a inscrição de um acólito"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM inscricoes
            WHERE missa_id = %s AND nome_acolito = %s
        """, (missa_id, nome_acolito))
        
        sucesso = cursor.rowcount > 0
        conn.commit()
        return sucesso
    except psycopg2.Error as e:
        st.error(f"Erro ao desinscrever acólito: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def cadastrar_missa(data: str, hora: str, descricao: str, vagas_totais: int) -> bool:
    """Cadastra uma nova missa"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO missas (data, hora, descricao, vagas_totais)
            VALUES (%s, %s, %s, %s)
        """, (data, hora, descricao, vagas_totais))
        
        conn.commit()
        return True
    except psycopg2.Error as e:
        st.error(f"Erro ao cadastrar missa: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def obter_ranking():
    conn = get_db_connection()
    if not conn: return []
    cur = conn.cursor()
    
    # Pega quem serviu e quando
    cur.execute("""
        SELECT i.nome_acolito, m.data, m.hora 
        FROM inscricoes i JOIN missas m ON i.missa_id = m.id
    """)
    dados = cur.fetchall()
    conn.close()

    pontuacao = {}
    fuso = pytz.timezone('America/Sao_Paulo')
    agora = datetime.now(fuso)

    for nome, data_str, hora_str in dados:
        try:
            # Monta data da missa
            dt_str = f"{data_str} {hora_str}"
            dt_missa = fuso.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
            
            # Se já passou 6 horas da missa, ganha ponto
            if agora > (dt_missa + timedelta(hours=6)):
                pontuacao[nome] = pontuacao.get(nome, 0) + 1
        except: continue

    # Ordena do maior para o menor
    return sorted(pontuacao.items(), key=lambda x: x[1], reverse=True)

def listar_todas_missas() -> List[Dict]:
    """Retorna todas as missas (para admin)"""
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT m.id, m.data, m.hora, m.descricao, m.vagas_totais,
                   COUNT(i.id) as vagas_preenchidas
            FROM missas m
            LEFT JOIN inscricoes i ON m.id = i.missa_id
            GROUP BY m.id
            ORDER BY m.data DESC, m.hora DESC
        """)
        
        resultados = cursor.fetchall()
        
        missas = []
        for row in resultados:
            missas.append({
                'id': row[0],
                'data': row[1],
                'hora': row[2],
                'descricao': row[3],
                'vagas_totais': row[4],
                'vagas_preenchidas': row[5] or 0
            })
        
        return missas
    except psycopg2.Error as e:
        st.error(f"Erro ao listar missas: {e}")
        if conn:
            conn.rollback()
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def listar_inscritos(missa_id: int) -> List[str]:
    """Retorna lista de nomes dos acólitos inscritos em uma missa"""
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT nome_acolito FROM inscricoes
            WHERE missa_id = %s
            ORDER BY nome_acolito
        """, (missa_id,))
        
        resultados = cursor.fetchall()
        
        return [row[0] for row in resultados]
    except psycopg2.Error as e:
        st.error(f"Erro ao listar inscritos: {e}")
        if conn:
            conn.rollback()
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def excluir_missa(missa_id: int) -> bool:
    """Exclui uma missa e suas inscrições"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Primeiro excluir as inscrições (cascade)
        cursor.execute("DELETE FROM inscricoes WHERE missa_id = %s", (missa_id,))
        
        # Depois excluir a missa
        cursor.execute("DELETE FROM missas WHERE id = %s", (missa_id,))
        
        conn.commit()
        return True
    except psycopg2.Error as e:
        st.error(f"Erro ao excluir missa: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def remover_inscricao_admin(missa_id: int, nome_acolito: str) -> bool:
    """Remove a inscrição de um acólito específico (função para admin)"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM inscricoes
            WHERE missa_id = %s AND nome_acolito = %s
        """, (missa_id, nome_acolito))
        
        sucesso = cursor.rowcount > 0
        conn.commit()
        return sucesso
    except psycopg2.Error as e:
        st.error(f"Erro ao remover inscrição: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def listar_acolitos() -> List[str]:
    """Retorna lista de todos os acólitos cadastrados"""
    conn = get_db_connection()
    if not conn:
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT nome FROM acolitos
            ORDER BY nome
        """)
        
        resultados = cursor.fetchall()
        
        return [row[0] for row in resultados]
    except psycopg2.Error as e:
        st.error(f"Erro ao listar acólitos: {e}")
        if conn:
            conn.rollback()
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def cadastrar_acolito(nome: str) -> bool:
    """Cadastra um novo acólito"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO acolitos (nome)
            VALUES (%s)
        """, (nome.strip(),))
        
        conn.commit()
        return True
    except psycopg2.IntegrityError:
        # Acólito já existe
        return False
    except psycopg2.Error as e:
        st.error(f"Erro ao cadastrar acólito: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def remover_acolito(nome: str) -> bool:
    """Remove um acólito da lista"""
    conn = get_db_connection()
    if not conn:
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM acolitos
            WHERE nome = %s
        """, (nome,))
        
        sucesso = cursor.rowcount > 0
        conn.commit()
        return sucesso
    except psycopg2.Error as e:
        st.error(f"Erro ao remover acólito: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ==================== FUNÇÕES DE INTERFACE ====================

def tela_login():
    """Renderiza a tela de login estilizada"""
    # Espaçamento vertical
    st.write("")
    st.write("")
    
    col_vazia_esq, col_centro, col_vazia_dir = st.columns([1, 1.5, 1])
    
    with col_centro:
        # Card de Login centralizado
        with st.container(border=True):
            st.markdown("<div class='login-header'><h1>⛪️</h1><h2>Escala de Acólitos</h2></div>", unsafe_allow_html=True)
            
            st.markdown("### 👋 Bem-vindo!")
            
            # Buscar lista de acólitos cadastrados
            acolitos = listar_acolitos()
            
            if not acolitos:
                st.warning("⚠️ Nenhum acólito cadastrado.")
                st.info("Acesse como **Coordenador** para configurar a equipe.")
                nome_selecionado = None
            else:
                nome_selecionado = st.selectbox(
                    "Quem é você?",
                    options=[""] + acolitos,
                    key="select_nome",
                    index=0,
                    placeholder="Selecione seu nome"
                )
            
            # Botão de entrar com destaque
            if st.button("Entrar no Sistema", type="primary", use_container_width=True):
                if nome_selecionado and nome_selecionado.strip():
                    st.session_state['usuario'] = nome_selecionado.strip()
                    st.session_state['tela'] = 'escala'
                    st.rerun()
                else:
                    st.toast("⚠️ Por favor, selecione seu nome.")
            
            st.markdown("---")
            
            # Área do Coordenador (Colapsible para não poluir)
            with st.expander("🔐 Acesso Coordenador"):
                senha = st.text_input("Senha de acesso", type="password", key="input_senha")
                
                if st.button("Entrar como Admin", use_container_width=True):
                    if senha == st.secrets.get("ADMIN_SENHA", "admin"): # fallback seguro se nao tiver secret configurada para teste
                        st.session_state['tela'] = 'admin'
                        st.rerun()
                    else:
                        st.error("Senha incorreta!")

def tela_escala():
    """Renderiza a tela principal do acólito"""
    nome = st.session_state.get('usuario', 'Usuário')
    
    # --- SIDEBAR: Perfil do Usuário ---
    with st.sidebar:
        st.title("👤 Meu Perfil")
        st.info(f"Logado como: **{nome}**")
        
        st.markdown("---")
        if st.button("🚪 Sair", use_container_width=True, type="secondary"):
            if 'usuario' in st.session_state:
                del st.session_state['usuario']
            if 'tela' in st.session_state:
                del st.session_state['tela']
            st.rerun()
        
        st.markdown("---")
        st.caption("Sistema de Escala v2.0")

    # --- ÁREA PRINCIPAL ---
    st.subheader(f"Olá, {nome}!")
    
    tab_missas, tab_ranking = st.tabs(["📅 Missas Disponíveis", "🏆 Ranking & Estatísticas"])
    
    # === ABA 1: MISSAS ===
    with tab_missas:
        missas = listar_missas_futuras()
        
        if not missas:
            st.container(border=True).info("📭 Nenhuma missa agendada no momento. Aproveite o descanso!")
        else:
            for missa in missas:
                # Filtro de tempo (ocultar missas que passaram há mais de 6h)
                try:
                    fuso = pytz.timezone('America/Sao_Paulo')
                    agora = datetime.now(fuso)
                    dt_str = f"{missa['data']} {missa['hora']}"
                    dt_missa = fuso.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
                    if agora > (dt_missa + timedelta(hours=6)): continue
                except: pass
                
                # Formatar data
                try:
                    data_obj = datetime.strptime(missa['data'], "%Y-%m-%d")
                    dia_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"][data_obj.weekday()]
                    data_formatada = f"{data_obj.strftime('%d/%m/%Y')} ({dia_semana})"
                except:
                    data_formatada = missa['data']
                
                # CARD DA MISSA (Container com borda)
                with st.container(border=True):
                    # Cabeçalho do Card
                    col_header, col_status = st.columns([3, 1])
                    with col_header:
                        st.markdown(f"#### ✝️ {missa['descricao'] or 'Santa Missa'}")
                        st.markdown(f"📅 **{data_formatada}** |  ⏰ **{missa['hora']}**")
                    
                    with col_status:
                         # Indicador visual de lotação
                        vagas_preenchidas = missa['vagas_preenchidas']
                        vagas_totais = missa['vagas_totais']
                        if vagas_preenchidas >= vagas_totais:
                            st.error("LOTADA", icon="🔒")
                        else:
                            st.success("ABERTA", icon="✨")

                    st.markdown("---")
                    
                    # Corpo do Card
                    c_detalhes, c_acao = st.columns([2, 1])
                    
                    with c_detalhes:
                        # Lista de inscritos
                        nomes_inscritos = missa.get('nomes_inscritos', [])
                        if nomes_inscritos:
                            st.markdown("**Acólitos Escalados:**")
                            for n in nomes_inscritos:
                                st.markdown(f"- {n}")
                        else:
                            st.caption("*Nenhum inscrito ainda. Seja o primeiro!*")
                            
                        # Barra de progresso visual
                        progresso = vagas_preenchidas / vagas_totais if vagas_totais > 0 else 0
                        st.progress(progresso)
                        st.caption(f"Vagas: {vagas_preenchidas}/{vagas_totais} preenchidas")

                    with c_acao:
                        # Botões de Ação
                        esta_inscrito = verificar_inscricao(missa['id'], nome)
                        tem_vaga = vagas_preenchidas < vagas_totais
                        
                        st.write("") # Espaçamento para alinhar verticalmente
                        
                        if esta_inscrito:
                            if st.button("❌ Cancelar", key=f"sair_{missa['id']}", 
                                       use_container_width=True, type="secondary", 
                                       help="Remover meu nome da lista"):
                                if desinscrever_acolito(missa['id'], nome):
                                    st.toast("Inscrição cancelada com sucesso!")
                                    st.rerun()
                                else:
                                    st.error("Erro ao sair.")
                        elif tem_vaga:
                            if st.button("✅ Servir nesta Missa", key=f"servir_{missa['id']}", 
                                       use_container_width=True, type="primary"):
                                if inscrever_acolito(missa['id'], nome):
                                    st.balloons()
                                    st.success("Confirmado!")
                                    st.rerun()
                                else:
                                    st.error("Não foi possível inscrever.")
                        else:
                            st.button("🔒 Lista Completa", key=f"lotado_{missa['id']}", 
                                    use_container_width=True, disabled=True)

    # === ABA 2: RANKING ===
    with tab_ranking:
        st.subheader("🏆 Quadro de Honra")
        st.markdown("Ranking contabilizado apenas após a realização das missas (+6h).")
        
        ranking = obter_ranking()
        
        if ranking:
            # Top 3 em destaque
            top3_cols = st.columns(3)
            for i, (nome_r, pontos) in enumerate(ranking[:3]):
                medalhas = ["🥇", "🥈", "🥉"]
                with top3_cols[i]:
                    with st.container(border=True):
                        st.markdown(f"<h1 style='text-align: center;'>{medalhas[i]}</h1>", unsafe_allow_html=True)
                        st.markdown(f"<h4 style='text-align: center;'>{nome_r}</h4>", unsafe_allow_html=True)
                        st.markdown(f"<p style='text-align: center;'>{pontos} Missas</p>", unsafe_allow_html=True)
            
            # Tabela completa
            if len(ranking) > 3:
                st.markdown("### Classificação Geral")
                for i, (nome_r, pontos) in enumerate(ranking[3:], 4):
                    with st.container(border=True):
                        col_pos, col_nom, col_pts = st.columns([1, 4, 2])
                        col_pos.write(f"**{i}º**")
                        col_nom.write(nome_r)
                        col_pts.write(f"{pontos} pts")
        else:
            st.info("Nenhum ponto contabilizado ainda.")

def tela_admin():
    """Renderiza a tela de administração organizada"""
    st.title("⚙️ Painel do Coordenador")
    
    # Botão de voltar discreto no topo
    if st.button("← Sair do Painel Admin", type="secondary"):
        if 'tela' in st.session_state: del st.session_state['tela']
        st.rerun()
    
    st.markdown("---")
    
    # Tabs com ícones
    tab1, tab2, tab3, tab4 = st.tabs(["➕ Gerenciar Missas", "👥 Equipe de Acólitos", "📊 Ranking Geral", "📜 Histórico/Correção"])
    
    # --- ABA 1: MISSAS ---
    with tab1:
        col_form, col_lista = st.columns([1, 2])
        
        with col_form:
            with st.container(border=True):
                st.subheader("Nova Missa")
                with st.form("form_nova_missa"):
                    data = st.date_input("Data", min_value=date.today())
                    hora = st.time_input("Hora", value=time(19, 0))
                    descricao = st.text_input("Descrição", placeholder="Ex: Missa Solene")
                    vagas_totais = st.number_input("Nº Vagas", 1, 20, 4)
                    
                    if st.form_submit_button("📅 Criar Agenda", type="primary", use_container_width=True):
                        if cadastrar_missa(data.strftime("%Y-%m-%d"), hora.strftime("%H:%M"), descricao, vagas_totais):
                            st.toast("Missa criada com sucesso!")
                            st.rerun()
        
        with col_lista:
            st.subheader("Próximas Celebrações")
            missas = listar_todas_missas()
            
            # Filtro visual apenas para limpar a lista do admin
            missas_futuras = []
            for m in missas:
                try:
                    fuso = pytz.timezone('America/Sao_Paulo')
                    agora = datetime.now(fuso)
                    dt_missa = fuso.localize(datetime.strptime(f"{m['data']} {m['hora']}", "%Y-%m-%d %H:%M"))
                    if agora <= (dt_missa + timedelta(hours=6)):
                        missas_futuras.append(m)
                except: pass
            
            if not missas_futuras:
                st.info("Nenhuma missa futura cadastrada.")
            
            for missa in missas_futuras:
                with st.expander(f"🗓️ {missa['data']} - {missa['descricao']} ({missa['hora']})"):
                    c1, c2 = st.columns([3, 1])
                    
                    with c1:
                        st.markdown(f"**Ocupação:** {missa['vagas_preenchidas']}/{missa['vagas_totais']}")
                        st.markdown("**Inscritos:**")
                        inscritos = listar_inscritos(missa['id'])
                        if inscritos:
                            for u in inscritos:
                                cx, cy = st.columns([3, 1])
                                cx.text(f"• {u}")
                                if cy.button("❌", key=f"rm_{missa['id']}_{u}", help="Remover acolito"):
                                    remover_inscricao_admin(missa['id'], u)
                                    st.rerun()
                        else:
                            st.caption("Nenhum inscrito.")
                    
                    with c2:
                        st.write("")
                        if st.button("🗑️ Excluir", key=f"del_{missa['id']}", type="secondary", use_container_width=True):
                            excluir_missa(missa['id'])
                            st.rerun()

    # --- ABA 2: EQUIPE ---
    with tab2:
        col_add, col_ver = st.columns([1, 2])
        
        with col_add:
            with st.container(border=True):
                st.subheader("Novo Membro")
                with st.form("add_ac"):
                    nome = st.text_input("Nome Completo")
                    if st.form_submit_button("Adicionar", type="primary", use_container_width=True):
                        if cadastrar_acolito(nome): 
                            st.success(f"{nome} adicionado!")
                            st.rerun()
        
        with col_ver:
            st.subheader("Membros Ativos")
            todos_acolitos = listar_acolitos()
            if todos_acolitos:
                for ac in todos_acolitos:
                    with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        c1.write(f"👤 **{ac}**")
                        if c2.button("🗑️", key=f"del_ac_{ac}"):
                            remover_acolito(ac)
                            st.rerun()
            else:
                st.warning("Nenhum membro cadastrado.")

    # --- ABA 3: RANKING ---
    with tab3:
        st.subheader("Relatório de Presença")
        r = obter_ranking()
        if r:
            # Usando st.dataframe para uma view mais limpa no admin
            import pandas as pd
            df = pd.DataFrame(r, columns=["Nome", "Missas Servidas"])
            df.index += 1
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Sem dados de pontuação.")

    # --- ABA 4: HISTÓRICO ---
    with tab4:
        st.info("📝 Use esta área para corrigir presenças em missas que já ocorreram.")
        
        missas = listar_todas_missas()
        lista_completa_acolitos = listar_acolitos()
        encontrou_antiga = False
        
        for missa in missas:
            mostrar = False
            try:
                fuso = pytz.timezone('America/Sao_Paulo')
                agora = datetime.now(fuso)
                dt_missa = fuso.localize(datetime.strptime(f"{missa['data']} {missa['hora']}", "%Y-%m-%d %H:%M"))
                if agora > (dt_missa + timedelta(hours=6)): 
                    mostrar = True
                    encontrou_antiga = True
            except: pass
            
            if mostrar:
                with st.expander(f"✅ {missa['data']} | {missa['descricao']}"):
                    col_lista, col_add = st.columns([1, 1])
                    
                    with col_lista:
                        st.caption("Quem serviu (Pontuou):")
                        inscritos = listar_inscritos(missa['id'])
                        if inscritos:
                            for u in inscritos:
                                c_nome, c_del = st.columns([3, 1])
                                c_nome.write(f"• {u}")
                                if c_del.button("➖", key=f"hist_rm_{missa['id']}_{u}", help="Remover ponto"):
                                    remover_inscricao_admin(missa['id'], u)
                                    st.rerun()
                        else:
                            st.warning("Registro vazio.")
                    
                    with col_add:
                        st.caption("Adicionar manualmente:")
                        quem_add = st.selectbox("Acólito:", [""] + lista_completa_acolitos, key=f"sel_add_{missa['id']}")
                        
                        if st.button("➕ Adicionar Presença", key=f"btn_add_{missa['id']}"):
                            if quem_add:
                                if inscrever_acolito(missa['id'], quem_add):
                                    st.success(f"Ponto +1 para {quem_add}!")
                                    st.rerun()
                                else:
                                    st.error("Erro ao adicionar (lotado ou duplicado).")
        
        if not encontrou_antiga:
            st.write("Nenhuma missa passada para exibir.")

# ==================== LÓGICA PRINCIPAL ====================

def main():
    # Inicializar banco de dados
    criar_tabelas()
    
    # Inicializar estado da sessão
    if 'tela' not in st.session_state:
        st.session_state['tela'] = 'login'
    
    # Navegação entre telas
    if st.session_state['tela'] == 'login':
        tela_login()
    elif st.session_state['tela'] == 'escala':
        tela_escala()
    elif st.session_state['tela'] == 'admin':
        tela_admin()

if __name__ == "__main__":
    main()
