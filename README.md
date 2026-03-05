# ⛪ Pastoral de Acólitos | Sistema de Gestão e Organização

Este projeto foi desenvolvido com o propósito de modernizar e centralizar a gestão da **Pastoral de Acólitos**, servindo como uma ferramenta administrativa essencial para a coordenação. O sistema automatiza tarefas burocráticas, como a elaboração de escalas e o controlo de membros, permitindo que a pastoral foque na sua missão litúrgica principal.

O **Acolitagem Manager** transforma a organização da paróquia numa experiência digital intuitiva, acessível e eficiente.

---

## ✨ Funcionalidades Principais

* **📊 Dashboard Administrativo:** Vista geral instantânea com métricas de membros ativos, escalas pendentes e avisos recentes.
* **👥 Gestão de Membros:** Registo completo de acólitos e cerimoniários, permitindo a edição de perfis, controlo de status e consulta rápida de contactos.
* **📅 Gestão de Escalas Dinâmicas:** Visualização de escalas por período e funcionalidade para geração automática de novas escalas para as celebrações.
* **📚 Biblioteca de Formações:** Repositório centralizado para materiais de estudo, manuais litúrgicos e guias de cerimónia para consulta constante da equipa.
* **📢 Mural de Avisos:** Espaço dedicado para comunicações internas importantes, garantindo que todos os membros estejam alinhados com as atividades da paróquia.

---

## 🛠️ Tecnologias Utilizadas

O sistema foi construído com foco em simplicidade de manutenção e rapidez de execução:

* **Linguagem:** [Python 3.x](https://www.python.org/)
* **Framework:** [Streamlit](https://streamlit.io/) (Interface web reativa e moderna)
* **Manipulação de Dados:** [Pandas](https://pandas.pydata.org/) (Processamento eficiente de registos e escalas)
* **Iconografia:** [Lucide/Streamlit Emoji](https://lucide.dev/)

---

## ⚙️ Como Executar a Aplicação

Para rodar o sistema no seu ambiente local, siga estes passos:

1. **Clone o repositório:**
```bash
git clone https://github.com/sousafeliper/site-acolitos.git
cd site-acolitos

```


2. **Instale as dependências necessárias:**
```bash
pip install -r requirements.txt

```


3. **Inicie o servidor Streamlit:**
```bash
streamlit run app.py

```


4. **Aceda ao sistema:**
Abra o seu navegador em `http://localhost:8501`

---

## 📂 Estrutura do Projeto

* `app.py`: Ficheiro principal que gere a navegação (Sidebar) e a lógica de cada módulo (Dashboard, Membros, Escalas).
* `requirements.txt`: Lista de bibliotecas necessárias para o funcionamento do sistema.
* `.devcontainer/`: Configurações para desenvolvimento isolado em contentores.

---

## 👤 Autor

Desenvolvido por **Felipe Rodrigues de Sousa** como um contributo tecnológico para a comunidade paroquial.

* **GitHub:** [@sousafeliper](https://www.google.com/search?q=https://github.com/sousafeliper)
* **E-mail:** rodriguesdesousa.felipe01@gmail.com
