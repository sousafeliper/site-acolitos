import streamlit as st
import psycopg2
import pytz 
from datetime import datetime, date, time, timedelta 
from typing import List, Dict, Optional

# Configuração da página
st.set_page_config(
    page_title="Escala de Acólitos",
    page_icon="⛪️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==================== ESTILIZAÇÃO CSS (CORRIGIDA) ====================
st.markdown("""
    <style>
        /* SOLUÇÃO DO TEMA: 
           Usa variáveis nativas do Streamlit (var(--...)) para que as cores
           se adaptem automaticamente ao Tema Claro ou Escuro selecionado pelo dispositivo.
        */
        
        /* Forçar o app a usar as cores do tema, prevenindo fundo branco forçado */
        .stApp {
            background-color: var(--primary-background-color);
            color: var(--text-color);
        }

        /* Ajuste de espaçamento do topo */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
        }

        /* Remover menu padrão e rodapé para visual de app */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stDeployButton {display:none;}
        
        /* Melhorar visual dos cards (Metrics e Containers) */
        div[data-testid="stMetric"], div[data-testid="stContainer"] {
            /* Fundo secundário adapta: cinza claro no Light Mode, cinza escuro no Dark Mode */
            background-color: var(--secondary-background-color); 
            padding: 10px;
            border-radius: 10px;
            /* Borda sutil para destacar do fundo */
            border: 1px solid rgba(128, 128, 128, 0.2);
        }

        /* Ajuste para inputs ficarem legíveis em ambos os modos */
        .stTextInput > div > div > input {
            color: var(--text-color);
        }
    </style>
""", unsafe_allow_html=True)

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
    """Renderiza a tela de login"""
    
    # Layout centralizado
    col_vazia_esq, col_centro, col_vazia_dir = st.columns([1, 1.5, 1])
    
    with col_centro:
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center;'>⛪️</h1>", unsafe_allow_html=True)
            st.markdown("<h2 style='text-align: center;'>Escala de Acólitos</h2>", unsafe_allow_html=True)
            st.caption("Sistema de agendamento e controle de escala")
            st.divider()
            
            st.markdown("##### 👤 Acesso do Acólito")
            # Buscar lista de acólitos cadastrados
            acolitos = listar_acolitos()
            
            if not acolitos:
                st.warning("⚠️ Nenhum acólito cadastrado. Solicite ao coordenador.")
                nome_selecionado = None
            else:
                nome_selecionado = st.selectbox(
                    "Selecione seu nome",
                    options=[""] + acolitos,
                    key="select_nome",
                    index=0,
                    placeholder="Clique para buscar seu nome"
                )
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Entrar no Sistema", type="primary", use_container_width=True):
                    if nome_selecionado and nome_selecionado.strip():
                        st.session_state['usuario'] = nome_selecionado.strip()
                        st.session_state['tela'] = 'escala'
                        st.rerun()
                    else:
                        st.toast("⚠️ Por favor, selecione seu nome para continuar.")
            
            with col_btn2:
                if st.button("Sair / Logout", use_container_width=True):
                    if 'usuario' in st.session_state:
                        del st.session_state['usuario']
                    if 'tela' in st.session_state:
                        del st.session_state['tela']
                    st.rerun()
            
            st.divider()
            
            with st.expander("🔐 Área do Coordenador"):
                is_coordenador = st.checkbox("Confirmar acesso administrativo")
                if is_coordenador:
                    senha = st.text_input("Senha de acesso", type="password", key="input_senha")
                    if st.button("Acessar Painel", type="secondary", use_container_width=True):
                        if senha == st.secrets["ADMIN_SENHA"]:
                            st.session_state['tela'] = 'admin'
                            st.rerun()
                        else:
                            st.error("Senha incorreta!")

def tela_escala():
    """Renderiza a tela de escala para acólitos"""
    nome = st.session_state.get('usuario', 'Usuário')
    
    # Header personalizado com colunas
    col_header, col_sair = st.columns([5, 1])
    with col_header:
        st.title(f"Olá, {nome}!")
        st.caption(f"Bem-vindo(a) ao painel de escalas. Hoje é {date.today().strftime('%d/%m/%Y')}.")
    with col_sair:
        st.write("") # Espaço
        if st.button("Sair", use_container_width=True):
            if 'usuario' in st.session_state: del st.session_state['usuario']
            if 'tela' in st.session_state: del st.session_state['tela']
            st.rerun()
    
    st.divider()
    
    tab_missas, tab_ranking = st.tabs(["📅 Próximas Missas", "🏆 Ranking Geral"])

    with tab_missas:
        st.subheader("Missas Disponíveis")
        missas = listar_missas_futuras()
        
        if not missas:
            st.info("📭 Nenhuma missa agendada no momento. Aproveite o descanso!")
        else:
            # Grid system para telas grandes
            for missa in missas:
                try:
                    fuso = pytz.timezone('America/Sao_Paulo')
                    agora = datetime.now(fuso)
                    dt_str = f"{missa['data']} {missa['hora']}"
                    dt_missa = fuso.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
                    if agora > (dt_missa + timedelta(hours=6)): continue
                except: pass
                
                with st.container(border=True):
                    # Formatação de data
                    try:
                        data_obj = datetime.strptime(missa['data'], "%Y-%m-%d")
                        dia_semana = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][data_obj.weekday()]
                        data_formatada = data_obj.strftime("%d/%m")
                    except:
                        data_formatada = missa['data']
                        dia_semana = ""

                    # Layout do Card
                    c_info, c_action = st.columns([3, 1.5])
                    
                    with c_info:
                        st.markdown(f"#### {missa['descricao'] or 'Santa Missa'}")
                        st.markdown(f"🗓️ **{dia_semana}, {data_formatada}** às **{missa['hora']}**")
                        
                        nomes_inscritos = missa.get('nomes_inscritos', [])
                        if nomes_inscritos:
                            nomes_formatados = ", ".join(nomes_inscritos)
                            st.info(f"**Escalados:** {nomes_formatados}")
                        else:
                            st.caption("Ainda sem inscritos.")
                            
                        # Barra de progresso visual
                        vagas_preenchidas = missa['vagas_preenchidas']
                        vagas_totais = missa['vagas_totais']
                        progresso = vagas_preenchidas / vagas_totais if vagas_totais > 0 else 0
                        st.progress(progresso)
                        st.caption(f"Vagas: {vagas_preenchidas} de {vagas_totais} preenchidas")

                    with c_action:
                        st.write("") # Espaçamento vertical
                        esta_inscrito = verificar_inscricao(missa['id'], nome)
                        tem_vaga = vagas_preenchidas < vagas_totais
                        
                        if esta_inscrito:
                            if st.button("❌ Sair", key=f"sair_{missa['id']}", 
                                         use_container_width=True, type="secondary", 
                                         help="Cancelar sua participação nesta missa"):
                                if desinscrever_acolito(missa['id'], nome):
                                    st.success("Removido!")
                                    st.rerun()
                                else:
                                    st.error("Erro ao sair.")
                        elif tem_vaga:
                            if st.button("✅ Servir", key=f"servir_{missa['id']}", 
                                         use_container_width=True, type="primary",
                                         help="Confirmar presença nesta missa"):
                                if inscrever_acolito(missa['id'], nome):
                                    st.canvas_event = True # Hack visual
                                    st.success("Confirmado!")
                                    st.rerun()
                                else:
                                    st.error("Erro: Vaga ocupada.")
                        else:
                            st.button("🔒 Lotado", key=f"lotado_{missa['id']}", 
                                      use_container_width=True, disabled=True)

    with tab_ranking:
        st.subheader("Quadro de Honra")
        st.caption("Pontuação baseada em missas servidas.")
        ranking = obter_ranking()
        
        if ranking:
            col1, col2 = st.columns([1, 2])
            with col1:
                # Destaque para o Top 3
                top3 = ranking[:3]
                for i, (nome_r, pontos) in enumerate(top3, 1):
                    emoji = "🥇" if i==1 else "🥈" if i==2 else "🥉"
                    st.metric(label=f"{emoji} {i}º Lugar", value=str(pontos), delta=nome_r)
            
            with col2:
                # Tabela completa
                st.markdown("**Classificação Completa**")
                for i, (nome_r, pontos) in enumerate(ranking, 1):
                    with st.container(border=True):
                        cl1, cl2 = st.columns([4, 1])
                        cl1.markdown(f"**{i}º** {nome_r}")
                        cl2.markdown(f"**{pontos}** pts")
        else:
            st.info("O ranking será atualizado após a realização das primeiras missas.")

def tela_admin():
    """Renderiza a tela de administração"""
    st.title("⚙️ Painel do Coordenador")
    st.markdown("Gerencie missas, equipe e pontuações.")
    
    if st.button("← Sair do Painel Admin"):
        if 'tela' in st.session_state: del st.session_state['tela']
        st.rerun()
    
    st.divider()
    
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Agenda", "👥 Equipe", "🏆 Ranking", "📜 Histórico"])
    
    # --- ABA 1: MISSAS FUTURAS ---
    with tab1:
        col_form, col_lista = st.columns([1, 2])
        
        with col_form:
            with st.container(border=True):
                st.subheader("➕ Nova Missa")
                with st.form("form_nova_missa", border=False):
                    data = st.date_input("Data", min_value=date.today())
                    hora = st.time_input("Hora", value=time(19, 0))
                    descricao = st.text_input("Descrição", placeholder="Ex: Missa Solene")
                    vagas_totais = st.number_input("Vagas", 1, 20, 4)
                    
                    if st.form_submit_button("Cadastrar Missa", type="primary", use_container_width=True):
                        if cadastrar_missa(data.strftime("%Y-%m-%d"), hora.strftime("%H:%M"), descricao, vagas_totais):
                            st.toast("Missa criada com sucesso!")
                            st.rerun()
        
        with col_lista:
            st.subheader("Gerenciar Agendamentos")
            missas = listar_todas_missas()
            if not missas: st.info("Nenhuma missa cadastrada.")
            
            for missa in missas:
                # FILTRO: Só mostra missas que AINDA VÃO ACONTECER (ou recentes)
                try:
                    fuso = pytz.timezone('America/Sao_Paulo')
                    agora = datetime.now(fuso)
                    dt_missa = fuso.localize(datetime.strptime(f"{missa['data']} {missa['hora']}", "%Y-%m-%d %H:%M"))
                    if agora > (dt_missa + timedelta(hours=6)): continue 
                except: pass

                with st.expander(f"📿 {missa['data']} - {missa['descricao'] or 'Missa'} ({missa['hora']})", expanded=False):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.write(f"**Lotação:** {missa['vagas_preenchidas']}/{missa['vagas_totais']}")
                        inscritos = listar_inscritos(missa['id'])
                        if inscritos:
                            st.markdown("---")
                            for u in inscritos:
                                cx, cy = st.columns([4, 1])
                                cx.text(f"• {u}")
                                if cy.button("❌", key=f"rm_{missa['id']}_{u}", help="Remover inscrito"):
                                    remover_inscricao_admin(missa['id'], u)
                                    st.rerun()
                        else:
                            st.caption("Sem inscritos.")
                    
                    with c2:
                        st.write("")
                        if st.button("🗑️ Excluir", key=f"del_{missa['id']}", type="primary", use_container_width=True):
                            excluir_missa(missa['id'])
                            st.rerun()

    # --- ABA 2: EQUIPE ---
    with tab2:
        col_add, col_view = st.columns([1, 2])
        with col_add:
            with st.container(border=True):
                st.subheader("Novo Acólito")
                with st.form("add_ac", border=False):
                    nome = st.text_input("Nome completo")
                    if st.form_submit_button("Adicionar", type="primary", use_container_width=True):
                        if cadastrar_acolito(nome): 
                            st.toast("Acólito cadastrado!")
                            st.rerun()
        
        with col_view:
            st.subheader("Acólitos Ativos")
            for ac in listar_acolitos():
                with st.container(border=True):
                    c1, c2 = st.columns([4,1])
                    c1.write(f"👤 {ac}")
                    if c2.button("🗑️", key=f"del_ac_{ac}", help="Remover acólito"):
                        remover_acolito(ac)
                        st.rerun()

    # --- ABA 3: RANKING ---
    with tab3:
        st.subheader("Ranking Geral")
        r = obter_ranking()
        if r: 
            st.table([{"Posição": f"{i}º", "Nome": n, "Missas Servidas": p} for i, (n,p) in enumerate(r,1)])
        else: 
            st.info("Sem dados de pontuação.")

    # --- ABA 4: HISTÓRICO ---
    with tab4:
        st.subheader("📜 Histórico e Correção")
        st.caption("Missas finalizadas (+6h). Use para corrigir presenças e pontuações.")
        
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
                with st.expander(f"✅ REALIZADA: {missa['data']} - {missa['descricao']} ({missa['hora']})"):
                    col_lista, col_add = st.columns([1, 1])
                    
                    with col_lista:
                        st.markdown("**Quem serviu (Pontuou):**")
                        inscritos = listar_inscritos(missa['id'])
                        if inscritos:
                            for u in inscritos:
                                c_nome, c_del = st.columns([3, 1])
                                c_nome.text(f"• {u}")
                                if c_del.button("Retirar", key=f"hist_rm_{missa['id']}_{u}", help="Remove pontuação"):
                                    remover_inscricao_admin(missa['id'], u)
                                    st.rerun()
                        else:
                            st.caption("Nenhum registro.")
                    
                    with col_add:
                        st.markdown("**Adicionar (Dar Ponto):**")
                        quem_add = st.selectbox("Acólito:", [""] + lista_completa_acolitos, key=f"sel_add_{missa['id']}")
                        
                        if st.button("Adicionar Manualmente", key=f"btn_add_{missa['id']}", use_container_width=True):
                            if quem_add:
                                if inscrever_acolito(missa['id'], quem_add):
                                    st.success(f"Ponto +1 para {quem_add}!")
                                    st.rerun()
                                else:
                                    st.error("Erro: Lotado ou já inscrito.")
                            else:
                                st.warning("Selecione um nome.")
                        
        if not encontrou_antiga:
            st.info("Nenhuma missa passada para exibir.")

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
