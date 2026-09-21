# Pastoral de Acólitos

Sistema web para organizar a escala de acólitos, desenvolvido com Streamlit e PostgreSQL.

## Funcionalidades

### Acesso do acólito

- Seleção do nome cadastrado para entrar no sistema.
- Visualização das próximas missas disponíveis.
- Inscrição em uma missa enquanto houver vagas.
- Cancelamento da própria inscrição.
- Ranking mensal de pontos.

### Área do coordenador

- Cadastro, renomeação, consulta e remoção de acólitos.
- Agenda de missas ativas, com criação, edição e exclusão.
- Cadastro de uma rotina semanal de missas.
- Geração automática das missas da semana seguinte a partir da rotina cadastrada.
- Histórico de missas finalizadas e arquivamento dos pontos.
- Rankings mensal, trimestral e anual.
- Aba de baixa frequência, listando acólitos que serviram menos de 5 vezes nos últimos 90 dias.

## Tecnologias

- [Python 3](https://www.python.org/)
- [Streamlit](https://streamlit.io/)
- [PostgreSQL](https://www.postgresql.org/)
- [psycopg2](https://www.psycopg.org/)
- [pytz](https://pypi.org/project/pytz/)

As dependências do projeto estão em [`requirements.txt`](requirements.txt). O `pandas` permanece listado como dependência disponível para recursos de dados, embora a lógica atual do aplicativo não o importe diretamente.

## Configuração

O aplicativo precisa de uma conexão PostgreSQL e de uma senha para a área do coordenador. Crie o arquivo `.streamlit/secrets.toml` com:

```toml
DATABASE_URL = "postgresql://usuario:senha@host:5432/banco"
ADMIN_SENHA = "defina-uma-senha-forte"
```

Não versione esse arquivo nem publique suas credenciais. As tabelas necessárias (`missas`, `inscricoes`, `acolitos`, `historico_pontos` e tabelas auxiliares) são criadas automaticamente na inicialização.

## Como executar

1. Clone o repositório e entre na pasta do projeto:

	```bash
	git clone https://github.com/sousafeliper/site-acolitos.git
	cd site-acolitos
	```

2. Instale as dependências:

	```bash
	pip install -r requirements.txt
	```

3. Configure o arquivo `.streamlit/secrets.toml` conforme a seção anterior.

4. Inicie a aplicação:

	```bash
	streamlit run app.py
	```

5. Abra `http://localhost:8501` no navegador.

## Estrutura do projeto

- [`app.py`](app.py): aplicação Streamlit, interface, regras de negócio e acesso ao banco.
- [`requirements.txt`](requirements.txt): dependências Python.
- `.streamlit/secrets.toml`: credenciais locais da aplicação; não deve ser commitado.

## Autor

Desenvolvido por **Felipe Rodrigues de Sousa**.

- GitHub: [@sousafeliper](https://github.com/sousafeliper)
- E-mail: rodriguesdesousa.felipe01@gmail.com

