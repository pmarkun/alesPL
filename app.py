import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
from google import genai
from pydantic import BaseModel
import time

# Configuração inicial do Streamlit
st.set_page_config(layout="wide")
st.title("Análise Integrada de Projetos de Lei - ALESP")

# Definição do esquema para a análise
class ProjectAnalysis(BaseModel):
    analise_constitucional: str
    avaliacao_merito: str
    sugestao_emendas: str
    recomendacao_voto: str
    emoji_avaliacao: str

# Função para buscar PL por número e ano
def buscar_pl(numero, ano):
    url_busca = (
        f"https://www.al.sp.gov.br/alesp/pesquisa-proposicoes/?"
        f"direction=inicio&lastPage=1&currentPage=1&act=detalhe&idDocumento=&rowsPerPage=20&"
        f"currentPageDetalhe=1&tpDocumento=&selecionaDeseleciona=nao&method=search&"
        f"natureId=1&text=&legislativeNumber={numero}&legislativeYear={ano}&"
        f"natureIdMainDoc=&anoDeExercicio=&strInitialDate=&strFinalDate=&author=&"
        f"supporter=&politicalPartyId=&stageId="
    )
    response = requests.get(url_busca)
    if response.status_code != 200:
        return None
    soup = BeautifulSoup(response.text, 'html.parser')
    quadro = soup.find('div', id='lista_resultado')
    if not quadro:
        return None
    link_pl = quadro.find('a', href=lambda x: x and '/propositura/?id=' in x)
    if link_pl:
        pl_id = link_pl['href'].split('=')[-1]
        pl_link = f"https://www.al.sp.gov.br{link_pl['href']}"
        return pl_link, pl_id
    return None

# Função para extrair detalhes do PL
def extrair_detalhes_pl(pl_id):
    url_pl = f"https://www.al.sp.gov.br/propositura/?id={pl_id}"
    response = requests.get(url_pl)
    if response.status_code != 200:
        return None
    soup = BeautifulSoup(response.text, 'html.parser')
    dados = {}
    tabela = soup.find('table', class_='tabelaDados')
    if tabela:
        for row in tabela.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) == 2:
                chave = cols[0].get_text(strip=True)
                if chave == "Documento":
                    a_tag = cols[1].find('a', href=True)
                    if a_tag:
                        dados["Documento"] = a_tag.get_text(strip=True)
                        dados["pdf_url"] = a_tag['href']
                    else:
                        dados["Documento"] = cols[1].get_text(strip=True)
                else:
                    dados[chave] = cols[1].get_text(" ", strip=True)
    return dados

# Função para baixar o PDF
@st.cache_data(show_spinner=False)
def download_pdf(pdf_url: str) -> bytes:
    if not pdf_url.startswith("http"):
        pdf_url = "https://www.al.sp.gov.br" + pdf_url
    r = requests.get(pdf_url)
    if r.status_code == 200:
        return r.content
    return None

# Função para análise via GEMINI e cache dos resultados
@st.cache_data(show_spinner=True)
def get_analysis_result(pdf_url: str) -> dict:
    pdf_bytes = download_pdf(pdf_url)
    if pdf_bytes is None:
        return None

    temp_pdf_path = "temp_pl.pdf"
    with open(temp_pdf_path, "wb") as f:
        f.write(pdf_bytes)

    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    my_file = client.files.upload(file=temp_pdf_path)

    instructions = (
        "Você é um assessor legislativo artificial da deputada estadual Marina Helou, da Rede Sustentabilidade. "
        "Analise o projeto de lei no documento anexado e realize as seguintes etapas:\n"
        "0. Emoji de Avaliação: Escolha um emoji que represente o sentimento geral da análise.\n"
        "1. **Análise Constitucional**: Avalie a compatibilidade com a Constituição Federal e Estadual, destacando possíveis conflitos legais.\n"
        "2. **Avaliação de Mérito**: Analise impacto social, ambiental e econômico, considerando sustentabilidade e justiça social.\n"
        "3. **Sugestão de Emendas**: Proponha alterações que corrijam inconstitucionalidades ou aprimorem o alinhamento com as pautas do mandato.\n"
        "4. **Recomendação de Voto**: Indique se o voto deve ser favorável, neutro ou contrário, justificando com base nos critérios anteriores."
    )

    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=[instructions, my_file],
        config={'response_mime_type': 'application/json', 'response_schema': ProjectAnalysis}
    )

    return response.parsed

# Sidebar para busca de PL ou upload de CSV
st.sidebar.title("Buscar Projetos de Lei")
modo_busca = st.sidebar.radio("Escolha o método:", ["Busca Única", "Análise em Lote (CSV)"])

if modo_busca == "Busca Única":
    with st.sidebar.form("busca_form"):
        numero_pl = st.text_input("Número do Projeto de Lei")
        ano_pl = st.text_input("Ano do Projeto de Lei")
        submit = st.form_submit_button("Buscar e Analisar")

    if submit:
        resultado = buscar_pl(numero_pl, ano_pl)
        if resultado:
            pl_link, pl_id = resultado
            detalhes = extrair_detalhes_pl(pl_id)
            if detalhes and "pdf_url" in detalhes:
                analysis = get_analysis_result(detalhes["pdf_url"])
                st.session_state["analysis_result"] = analysis
                st.success(f"Projeto encontrado! [Link para o PL]({pl_link})")
                tipo = detalhes.get("Documento", "Tipo desconhecido")
                numero_legislativo = detalhes.get("Número Legislativo", "N/A")
                autor = detalhes.get("Autor(es)", "Autor desconhecido")
                ementa = detalhes.get("Ementa", "Sem ementa")
                try:
                    numero, ano = numero_legislativo.split("/", 1)
                    numero = numero.strip()
                    ano = ano.strip()
                except ValueError:
                    numero = "N/A"
                    ano = "N/A"
                    
                st.header(f"Projeto de Lei: {tipo} {numero}/{ano}")
                st.subheader(f"{autor}")
                st.markdown(f"**Ementa:** {ementa}")
                st.subheader("Resultado da Análise GEMINI: " + analysis.emoji_avaliacao)
                st.markdown(f"**Análise Constitucional:** {analysis.analise_constitucional}")
                st.markdown(f"**Avaliação de Mérito:** {analysis.avaliacao_merito}")
                st.markdown(f"**Sugestão de Emendas:** {analysis.sugestao_emendas}")
                st.markdown(f"**Recomendação de Voto:** {analysis.recomendacao_voto}")
            else:
                st.error("Não foi possível extrair os detalhes do projeto.")
        else:
            st.error("Projeto de Lei não encontrado.")

elif modo_busca == "Análise em Lote (CSV)":
    uploaded_file = st.sidebar.file_uploader("Envie um arquivo CSV", type=["csv"])

    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        if "numero" in df.columns and "ano" in df.columns:
            progress_bar = st.sidebar.progress(0)
            results = []
            
            for index, row in df.iterrows():
                pl_link, pl_id = buscar_pl(row["numero"], row["ano"])
                if pl_id:
                    detalhes = extrair_detalhes_pl(pl_id)
                    if detalhes and "pdf_url" in detalhes:
                        analysis = get_analysis_result(detalhes["pdf_url"])
                        row["analise_constitucional"] = analysis.analise_constitucional
                        row["avaliacao_merito"] = analysis.avaliacao_merito
                        row["sugestao_emendas"] = analysis.sugestao_emendas
                        row["recomendacao_voto"] = analysis.recomendacao_voto
                        row["emoji_avaliacao"] = analysis.emoji_avaliacao
                results.append(row)
                progress_bar.progress((index + 1) / len(df))

            results_df = pd.DataFrame(results)
            st.dataframe(results_df)
            st.sidebar.download_button("Baixar CSV com Análises", results_df.to_csv(index=False), "analise_pls.csv")
            st.sidebar.success("Análise concluída! Faça o download do resultado.")
        else:
            st.sidebar.error("O CSV deve conter as colunas 'numero' e 'ano'.")
