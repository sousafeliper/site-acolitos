import streamlit as st
import psycopg2
from datetime import datetime, date, time
from typing import List, Dict, Optional

# Configuração da págna
st.set_page_coinfig(
    page_title="Escala de Acólitos",
    page_icon="⛪️",
    layout="wide"
)

# Constantes
SENHA_ADMIN = "admin123"

# ==================== FUNÇÃO DE CONEXÃO ====================

def get_db_connection():
    """Obtém uma nova conexão com o banco de dados PostgreSQL"""
    try:
        # Tenta pegar a URL do banco dos secrets do Streamlit
        database_url = st.secrets.get("DATABASE_URL")
        if database_url:
            conn = psycopg2.connect(database_url)
            # Configurar autocommit para evitar problemas com transações
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

# ==================== FUNÇÕES DE INTERFACE ====================

def tela_login():
    """Renderiza a tela de login"""
    st.title("⛪️ Escala de Acólitos")
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("### Bem-vindo!")
        st.markdown("Digite seu nome para acessar a escala de missas.")
        
        nome = st.text_input("Digite seu nome para entrar", key="input_nome")
        
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            if st.button("Entrar", type="primary", use_container_width=True):
                if nome.strip():
                    st.session_state['usuario'] = nome.strip()
                    st.session_state['tela'] = 'escala'
                    st.rerun()
                else:
                    st.warning("Por favor, digite seu nome.")
        
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
                if senha == SENHA_ADMIN:
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

def tela_admin():
    """Renderiza a tela de administração"""
    st.title("⚙️ Painel do Coordenador")
    st.markdown("---")
    
    # Botão para voltar
    if st.button("← Voltar ao Login"):
        if 'tela' in st.session_state:
            del st.session_state['tela']
        st.rerun()
    
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
                        st.markdown("**Acólitos Inscritos:**")
                        for acolito in inscritos:
                            st.markdown(f"- {acolito}")
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

