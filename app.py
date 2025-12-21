import streamlit as st
import psycopg2
import pytz 
from datetime import datetime, date, time, timedelta 
from typing import List, Dict, Optional

# Configuração da página
st.set_page_config(
    page_title="Escala de Acólitos",
    page_icon="⛪️",
    layout="wide"
)


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
    st.title("⛪️ Escala de Acólitos")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### Bem-vindo!")
        st.markdown("Selecione seu nome para acessar a escala de missas.")
        
        # Buscar lista de acólitos cadastrados
        acolitos = listar_acolitos()
        
        if not acolitos:
            st.warning("⚠️ Nenhum acólito cadastrado. Acesse como Coordenador para configurar.")
            nome_selecionado = None
        else:
            nome_selecionado = st.selectbox(
                "Selecione seu nome",
                options=[""] + acolitos,
                key="select_nome",
                index=0
            )
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("Entrar", type="primary", use_container_width=True):
                if nome_selecionado and nome_selecionado.strip():
                    st.session_state['usuario'] = nome_selecionado.strip()
                    st.session_state['tela'] = 'escala'
                    st.rerun()
                else:
                    st.warning("Por favor, selecione seu nome.")
        
        with col_btn2:
            if st.button("Sair", use_container_width=True):
                if 'usuario' in st.session_state:
                    del st.session_state['usuario']
                if 'tela' in st.session_state:
                    del st.session_state['tela']
                st.rerun()
        
        st.markdown("---")
        st.markdown("### Acesso Coordenador")
        
        is_coordenador = st.checkbox("Sou Coordenador")
        
        if is_coordenador:
            senha = st.text_input("Digite a senha", type="password", key="input_senha")
            
            if st.button("Acessar como Coordenador", type="secondary", use_container_width=True):
                if senha == st.secrets["ADMIN_SENHA"]:
                    st.session_state['tela'] = 'admin'
                    st.rerun()
                else:
                    st.error("Senha incorreta!")

def tela_escala():
    """Renderiza a tela de escala para acólitos"""
    nome = st.session_state.get('usuario', 'Usuário')
    
    st.title(f"⛪️ Olá, {nome}!")
    st.markdown("---")
    
    # Botão para voltar ao login
    if st.button("← Voltar ao Login"):
        if 'usuario' in st.session_state:
            del st.session_state['usuario']
        if 'tela' in st.session_state:
            del st.session_state['tela']
        st.rerun()
    
    st.markdown("### 📅 Missas Disponíveis")
    
    missas = listar_missas_futuras()
    
    if not missas:
        st.info("📭 Não há missas cadastradas no momento.")
    else:
        for missa in missas:
            try:
                fuso = pytz.timezone('America/Sao_Paulo')
                agora = datetime.now(fuso)
                dt_str = f"{missa['data']} {missa['hora']}"
                dt_missa = fuso.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
                
                # Se passou 6h, pula essa missa (não exibe)
                if agora > (dt_missa + timedelta(hours=6)): continue
            except: pass
            with st.container():
                # Formatar data para exibição
                try:
                    data_obj = datetime.strptime(missa['data'], "%Y-%m-%d")
                    data_formatada = data_obj.strftime("%d/%m/%Y")
                except:
                    data_formatada = missa['data']
                
                # Card da missa
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"#### 📿 {missa['descricao'] or 'Missa'}")
                    st.markdown(f"**Data:** {data_formatada} | **Hora:** {missa['hora']}")
                    
                    # Lista de acólitos inscritos
                    nomes_inscritos = missa.get('nomes_inscritos', [])
                    if nomes_inscritos:
                        nomes_formatados = ", ".join(nomes_inscritos)
                        st.markdown(f"**Escalados:** {nomes_formatados}")
                    else:
                        st.markdown("**Escalados:** Nenhum inscrito ainda")
                    
                    # Barra de progresso
                    vagas_preenchidas = missa['vagas_preenchidas']
                    vagas_totais = missa['vagas_totais']
                    progresso = vagas_preenchidas / vagas_totais if vagas_totais > 0 else 0
                    
                    st.progress(progresso)
                    st.caption(f"Vagas: {vagas_preenchidas}/{vagas_totais} preenchidas")
                
                with col2:
                    esta_inscrito = verificar_inscricao(missa['id'], nome)
                    tem_vaga = vagas_preenchidas < vagas_totais
                    
                    if esta_inscrito:
                        if st.button("❌ Sair da Escala", key=f"sair_{missa['id']}", 
                                   use_container_width=True, type="secondary"):
                            if desinscrever_acolito(missa['id'], nome):
                                st.success("Você saiu da escala!")
                                st.rerun()
                            else:
                                st.error("Erro ao sair da escala.")
                    elif tem_vaga:
                        if st.button("✅ Servir", key=f"servir_{missa['id']}", 
                                   use_container_width=True, type="primary"):
                            if inscrever_acolito(missa['id'], nome):
                                st.success("Você foi inscrito na escala!")
                                st.rerun()
                            else:
                                st.error("Não foi possível inscrever. A missa pode estar lotada ou você já está inscrito.")
                    else:
                        st.button("🔒 Escala Completa", key=f"lotado_{missa['id']}", 
                                use_container_width=True, disabled=True)
                
                st.markdown("---")

    st.subheader("🏆 Ranking de Acólitos")
    ranking = obter_ranking()
    if ranking:
        for i, (nome, pontos) in enumerate(ranking, 1):
            medalha = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}º"
            st.write(f"**{medalha} {nome}:** {pontos} missas servidas")
    else:
        st.info("Nenhum ponto contabilizado ainda.")

def tela_admin():
    """Renderiza a tela de administração"""
    st.title("⚙️ Painel do Coordenador")
    st.markdown("---")
    
    # Botão para voltar
    if st.button("← Voltar ao Login"):
        if 'tela' in st.session_state:
            del st.session_state['tela']
        st.rerun()
    
    # Tabs para organizar as seções
    tab1, tab2, tab3 = st.tabs(["📋 Missas", "👥 Gerenciar Equipe", "🏆 Ranking"])
    
    # TAB 1: Missas
    with tab1:
        # Sidebar com formulário de nova missa
        with st.sidebar:
            st.header("➕ Nova Missa")
            
            with st.form("form_nova_missa"):
                data = st.date_input("Data", value=date.today(), min_value=date.today())
                hora = st.time_input("Hora", value=time(19, 0))
                descricao = st.text_input("Descrição", placeholder="Ex: Missa Solene")
                vagas_totais = st.number_input("Vagas Totais", min_value=1, value=4, step=1)
                
                submitted = st.form_submit_button("Cadastrar Missa", type="primary", use_container_width=True)
                
                if submitted:
                    data_str = data.strftime("%Y-%m-%d")
                    hora_str = hora.strftime("%H:%M")
                    
                    if cadastrar_missa(data_str, hora_str, descricao, vagas_totais):
                        st.success(f"Missa das {hora_str} cadastrada com sucesso!")
                        st.rerun()
                    else:
                        st.error("Erro ao cadastrar missa.")
        
        # Lista de missas na tela principal
        st.header("📋 Missas Cadastradas")
        
        missas = listar_todas_missas()
        
        if not missas:
            st.info("📭 Nenhuma missa cadastrada ainda.")
        else:
            for missa in missas:
                try:
                fuso = pytz.timezone('America/Sao_Paulo')
                agora = datetime.now(fuso)
                dt_str = f"{missa['data']} {missa['hora']}"
                dt_missa = fuso.localize(datetime.strptime(dt_str, "%Y-%m-%d %H:%M"))
                
                # Se passou 6h, pula essa missa (não exibe)
                if agora > (dt_missa + timedelta(hours=6)): continue
            except: pass
                with st.expander(f"📿 {missa['descricao'] or 'Missa'} - {missa['data']} {missa['hora']}", expanded=True):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        try:
                            data_obj = datetime.strptime(missa['data'], "%Y-%m-%d")
                            data_formatada = data_obj.strftime("%d/%m/%Y")
                        except:
                            data_formatada = missa['data']
                        
                        st.markdown(f"**Data:** {data_formatada}")
                        st.markdown(f"**Hora:** {missa['hora']}")
                        st.markdown(f"**Vagas:** {missa['vagas_preenchidas']}/{missa['vagas_totais']}")
                    
                    with col2:
                        inscritos = listar_inscritos(missa['id'])
                        if inscritos:
                            with st.expander("👥 Gerenciar Inscritos", expanded=False):
                                for acolito in inscritos:
                                    col_nome, col_btn = st.columns([3, 1])
                                    with col_nome:
                                        st.markdown(f"• {acolito}")
                                    with col_btn:
                                        if st.button("🗑️", key=f"remove_{missa['id']}_{acolito}", 
                                                   help=f"Remover {acolito}"):
                                            if remover_inscricao_admin(missa['id'], acolito):
                                                st.success(f"{acolito} removido da escala!")
                                                st.rerun()
                                            else:
                                                st.error(f"Erro ao remover {acolito}.")
                        else:
                            st.markdown("**Nenhum acólito inscrito ainda.**")
                    
                    with col3:
                        if st.button("🗑️ Excluir Missa", key=f"excluir_{missa['id']}", 
                                   use_container_width=True, type="secondary"):
                            if excluir_missa(missa['id']):
                                st.success("Missa excluída com sucesso!")
                                st.rerun()
                            else:
                                st.error("Erro ao excluir missa.")
    
    # TAB 2: Gerenciar Equipe
    with tab2:
        st.header("👥 Gerenciar Equipe")
        st.markdown("Cadastre e gerencie os acólitos que podem acessar o sistema.")
        
        # Formulário para cadastrar novo acólito
        st.subheader("➕ Cadastrar Novo Acólito")
        
        with st.form("form_novo_acolito"):
            nome_acolito = st.text_input("Nome do Acólito", placeholder="Digite o nome completo", key="input_nome_acolito")
            
            submitted = st.form_submit_button("Cadastrar Acólito", type="primary", use_container_width=True)
            
            if submitted:
                if nome_acolito.strip():
                    if cadastrar_acolito(nome_acolito):
                        st.success(f"Acólito '{nome_acolito}' cadastrado com sucesso!")
                        st.rerun()
                    else:
                        st.error(f"Erro ao cadastrar acólito. O nome '{nome_acolito}' pode já estar cadastrado.")
                else:
                    st.warning("Por favor, digite o nome do acólito.")
        
        st.markdown("---")
        
        # Lista de acólitos cadastrados
        st.subheader("📋 Acólitos Cadastrados")
        
        acolitos = listar_acolitos()
        
        if not acolitos:
            st.info("📭 Nenhum acólito cadastrado ainda.")
        else:
            st.markdown(f"**Total:** {len(acolitos)} acólito(s)")
            st.markdown("")
            
            for acolito in acolitos:
                col_nome, col_btn = st.columns([4, 1])
                with col_nome:
                    st.markdown(f"• **{acolito}**")
                with col_btn:
                    if st.button("🗑️ Remover", key=f"remover_acolito_{acolito}", 
                               use_container_width=True, type="secondary"):
                        if remover_acolito(acolito):
                            st.success(f"Acólito '{acolito}' removido com sucesso!")
                            st.rerun()
                        else:
                            st.error(f"Erro ao remover acólito '{acolito}'.")

    # TAB 3: Ranking
    with tab3:
        st.header("🏆 Ranking Geral")
        ranking = obter_ranking()
        if ranking:
            st.table([{"Posição": f"{i}º", "Nome": n, "Missas": p} for i, (n, p) in enumerate(ranking, 1)])
        else:
            st.info("Sem dados.")

# ==================== LÓGICA PRINCIPAL ====================

def main():
    # --- INÍCIO DO BLOCO DE CSS (Para esconder menu e rodapé) ---
    st.markdown("""
        <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stDeployButton {display:none;}
        </style>
    """, unsafe_allow_html=True)
    # --- FIM DO BLOCO DE CSS ---
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
