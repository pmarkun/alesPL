import streamlit as st
import requests
from bs4 import BeautifulSoup
from google import genai
from pydantic import BaseModel

# Schema para a análise do projeto de lei
class ProjectAnalysis(BaseModel):
    analise_constitucional: str
    avaliacao_merito: str
    sugestao_emendas: str
    recomendacao_voto: str
    emoji_avaliacao: str

# Função para buscar o PL pela combinação de número e ano
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
    # Procura o link que contenha "/propositura/?id=" para identificar o PL
    link_pl = quadro.find('a', href=lambda x: x and '/propositura/?id=' in x)
    if link_pl:
        pl_id = link_pl['href'].split('=')[-1]
        pl_link = f"https://www.al.sp.gov.br{link_pl['href']}"
        return pl_link, pl_id
    return None

# Função para extrair os detalhes do PL a partir do seu ID
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

# Função que baixa o PDF e salva em cache (retornando o conteúdo binário)
@st.cache_data(show_spinner=False)
def download_pdf(pdf_url: str) -> bytes:
    if not pdf_url.startswith("http"):
        pdf_url = "https://www.al.sp.gov.br" + pdf_url
    r = requests.get(pdf_url)
    if r.status_code == 200:
        return r.content
    return None

# Função que realiza a análise via GEMINI e salva o resultado em cache
@st.cache_data(show_spinner=True)
def get_analysis_result(pdf_url: str) -> dict:
    pdf_bytes = download_pdf(pdf_url)
    if pdf_bytes is None:
        return None
    # Salva temporariamente o PDF para upload
    temp_pdf_path = "temp_pl.pdf"
    with open(temp_pdf_path, "wb") as f:
        f.write(pdf_bytes)
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    my_file = client.files.upload(file=temp_pdf_path)

    instructions = (
    "Você é um assessor legislativo artificial da deputada estadual Marina Helou, da Rede Sustentabilidade. "
    "Sua análise deve estar alinhada às diretrizes do mandato, que é pautado pela sustentabilidade ambiental, "
    "direitos das mulheres, proteção da primeira infância e combate às desigualdades sociais. "
    "Temos como princípios a transparência, a participação social e a inovação, num espectro político progressista. "
    "Projetos que não dialoguem com essas áreas podem ser avaliados de maneira mais breve e objetiva. "
    "As recomendações devem ser baseadas em evidências, garantindo embasamento técnico e legal, promovendo diálogo e evitando polarização. "
    
    "Analise integralmente o projeto de lei contido no documento PDF anexado e realize as seguintes etapas: "
    
    "0. Emoji de Avaliação: Escolha um Emoji que represente o sentimento geral da análise. "
    "1. **Análise Constitucional**: Verifique a compatibilidade do projeto com a Constituição Federal e a Constituição Estadual de São Paulo, "
    "destacando eventuais conflitos normativos e riscos jurídicos. Caso haja trechos questionáveis, sugira ajustes para garantir conformidade legal. "
    
    "2. **Avaliação de Mérito**:" 
    "Considere os efeitos práticos da implementação da medida e possíveis impactos. "
    
    "3. **Sugestão de Emendas**: Identifique pontos do texto que podem ser aprimorados para corrigir inconstitucionalidades, "
    "reforçar a efetividade da política pública e garantir maior alinhamento com as pautas do mandato. Se possível, proponha redações alternativas. "
    
    "4. **Recomendação de Voto**: Sugira uma posição sobre o projeto (favorável, abstenção ou contrária) com uma justificativa embasada. "
    "Explique os principais pontos positivos e negativos, considerando viabilidade, impacto social e alinhamento com os valores do mandato. "
    
    "Sua análise deve ser objetiva, técnica e construtiva, buscando sempre contribuir para um debate qualificado e soluções eficazes. "
    "Use markdown para formatar o texto e incluir links, imagens e citações e \ para marcar quebras de linhas"
    )

    
    # Observe que o arquivo é enviado diretamente (sem encapsulá-lo em um dicionário)
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=[instructions, my_file],
        config={
            'response_mime_type': 'application/json',
            'response_schema': ProjectAnalysis,
        }
    )
    return response.parsed

# Inicializa as variáveis no session_state para preservar dados entre interações
if "detalhes" not in st.session_state:
    st.session_state["detalhes"] = None
if "pdf_url" not in st.session_state:
    st.session_state["pdf_url"] = None
if "analysis_result" not in st.session_state:
    st.session_state["analysis_result"] = None

st.set_page_config(layout="wide")
st.title("Análise Integrada de Projetos de Lei - ALESP")

#define sidebar para busca
st.sidebar.title("Busca de Projetos de Lei")

with st.sidebar:
    # Formulário para buscar e analisar o PL
    with st.form("busca_form"):
        numero_pl = st.text_input("Número do Projeto de Lei")
        ano_pl = st.text_input("Ano do Projeto de Lei")
        submit = st.form_submit_button("Buscar e Analisar")
        if submit:
            resultado = buscar_pl(numero_pl, ano_pl)
            if resultado:
                pl_link, pl_id = resultado
                detalhes = extrair_detalhes_pl(pl_id)
                if detalhes:
                    st.session_state["detalhes"] = detalhes
                    if "pdf_url" in detalhes:
                        st.session_state["pdf_url"] = detalhes["pdf_url"]
                    st.success(f"Projeto encontrado! [Link para o PL]({pl_link})")
                else:
                    st.error("Não foi possível extrair os detalhes do projeto.")
            else:
                st.error("Projeto de Lei não encontrado.")

# Se os detalhes foram encontrados, exibe a ficha simplificada e aciona a análise
if st.session_state["detalhes"]:
    detalhes = st.session_state["detalhes"]
    # Exibe informações simplificadas: TIPO NUMERO/ANO - Autor e Ementa
    tipo = detalhes.get("Documento", "Tipo desconhecido")
    numero_legislativo = detalhes.get("Número Legislativo", "N/A")
    #extrai numero e ano do numero legislativo, fazendo strip
    numero, ano = numero_legislativo.split("/", 1)
    ano = ano.strip()
    numero = numero.strip()
    autor = detalhes.get("Autor(es)", "Autor desconhecido")
    ementa = detalhes.get("Ementa", "Sem ementa")

    print(f"Projeto de Lei: {tipo} {numero}-{ano}")
    st.header(f"Projeto de Lei: {tipo} {numero}/{ano}")
    st.subheader(f"{autor}")
    st.markdown(f"**Ementa:** {ementa}")
    
    # Se houver PDF, realiza a análise integrada (utilizando cache para PDF e resultado)
    pdf_url = st.session_state.get("pdf_url")
    if pdf_url:
        analysis = get_analysis_result(pdf_url)
        st.session_state["analysis_result"] = analysis
        st.subheader("Resultado da Análise GEMINI:" + analysis.emoji_avaliacao)
        
        st.markdown(f"**Análise Constitucional:** {analysis.analise_constitucional}")
        st.markdown(f"**Avaliação de Mérito:** {analysis.avaliacao_merito}")
        st.markdown(f"**Sugestão de Emendas:** {analysis.sugestao_emendas}")
        st.markdown(f"**Recomendação de Voto:** {analysis.recomendacao_voto}")
        

        
    else:
        st.error("PDF não disponível para análise.")
