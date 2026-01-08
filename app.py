import streamlit as st
from datetime import datetime, timedelta
import backend
import pandas as pd
from streamlit_cookies_manager import EncryptedCookieManager
import time
import google.generativeai as genai
import json
import re
import fitz  # PyMuPDF
from io import BytesIO

# ===================================================================
# --- 1. CONFIGURAÇÃO DA PÁGINA (DEVE SER O PRIMEIRO COMANDO) ---
# ===================================================================
st.set_page_config(
    page_title="Plataforma AlexExpert",
    page_icon="🔍",
    layout="wide",  # Ativa o modo tela cheia
    initial_sidebar_state="expanded"
)

# --- CSS PARA LARGURA TOTAL E ESTILIZAÇÃO DAS ABAS ---
st.markdown("""
    <style>
        /* Remove margens laterais e aproveita todo o espaço disponível */
        .block-container {
            max-width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            padding-top: 1.5rem !important;
            padding-bottom: 0rem !important;
        }

        /* Faz as abas (tabs) ocuparem a largura total horizontalmente */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
            width: 100%;
        }

        .stTabs [data-baseweb="tab"] {
            height: 60px;
            white-space: pre-wrap;
            background-color: #f8f9fb;
            border-radius: 5px 5px 0px 0px;
            padding: 10px 20px;
            flex-grow: 1; /* Faz as abas crescerem para ocupar o espaço */
            text-align: center;
        }

        .stTabs [data-baseweb="tab"] p {
            font-size: 18px !important;
            font-weight: bold !important;
            color: #31333F;
        }

        /* Destaque para a aba selecionada */
        .stTabs [aria-selected="true"] {
            background-color: #e6e9ef !important;
            border-bottom: 3px solid #ff4b4b !important;
        }
        
        /* Ajuste fino em métricas para não ficarem "espremidas" no wide */
        [data-testid="stMetricValue"] {
            font-size: 1.8rem !important;
        }
    </style>
""", unsafe_allow_html=True)


# ===================================================================
# --- 2. FUNÇÕES DE UI E LÓGICA ---
# ===================================================================

def analyze_image_with_ai(image_file):
    """Usa a IA para extrair informações estruturadas de uma imagem."""
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    image_part = {'mime_type': image_file.type, 'data': image_file.getvalue()}
    
    prompt = [
        """
        Você é um assistente especializado em análise de fluidos. Sua tarefa é ler o texto e entender o contexto visual da imagem a seguir para extrair descrições de diagnósticos ou recomendações para manutenção. Extraia cada condição, seu nome chave, a descrição em português e, se houver, a tradução para o inglês. Identifique se a entrada é um diagnóstico (is_recomendacao=0) ou uma recomendação (is_recomendacao=1).
        Regras de extração:
        - `nome_chave`: Crie um nome curto e único em snake_case (ex: `alto_cobre`, `agua_no_oleo`).
        - `descricao_pt`: A descrição completa da condição em português.
        - `descricao_en`: A tradução da descrição para o inglês. Se não houver, deixe como nulo (`null`).
        - `is_recomendacao`: Valor booleano (0 ou 1). 1 se for uma recomendação. 0 se for um diagnóstico.
        Formato de Saída (JSON Array):
        Retorne uma lista de objetos JSON.
        """,
        image_part
    ]
    
    try:
        response = model.generate_content(prompt)
        json_text_match = re.search(r'\[.*\]', response.text, re.DOTALL)
        if json_text_match:
            return json.loads(json_text_match.group(0))
        return []
    except Exception as e:
        st.error(f"Erro na análise da IA: {e}")
        return None

def process_pdf_with_ai(pdf_file):
    """Processa um PDF, página por página, usando a IA."""
    try:
        doc = fitz.open(stream=pdf_file.getvalue(), filetype="pdf")
        all_results = []
        progress_bar = st.progress(0, text="Processando PDF...")
        for i, page in enumerate(doc):
            pix = page.get_pixmap()
            img_bytes = pix.tobytes("png")
            img_buffer = BytesIO(img_bytes)
            img_buffer.type = "image/png"
            
            ai_result = analyze_image_with_ai(img_buffer)
            if ai_result:
                all_results.extend(ai_result)
            progress_bar.progress((i + 1) / len(doc), text=f"Processando página {i+1}/{len(doc)}")
        progress_bar.empty()
        return all_results
    except Exception as e:
        st.error(f"Erro ao processar o PDF: {e}")
        return None

def exibir_graficos_tendencia(dados_laudo, resultados_analise, contexto_key):
    """Exibe um expansor para gerar e mostrar gráficos de tendência histórica."""
    cliente = dados_laudo.get('ClienteNome')
    unidade = dados_laudo.get('UnidadeNome')
    compartimento = dados_laudo.get('CompartimentoNome')
    session_state_key = f"historical_df_{contexto_key}"

    with st.expander("📊 Ver Gráficos de Tendência Histórica"):
        data_coleta_laudo = pd.to_datetime(dados_laudo.get('DataColeta'), errors='coerce')

        if pd.isna(data_coleta_laudo):
            end_date_default = datetime.now().date()
            start_date_default = end_date_default - pd.DateOffset(months=2)
        else:
            end_date_default = data_coleta_laudo.date()
            data_anterior = backend.get_data_penultima_coleta(cliente, unidade, compartimento, end_date_default)
            start_date_default = data_anterior.date() if data_anterior else (end_date_default - pd.DateOffset(months=2))

        col_start, col_end = st.columns(2)
        with col_start:
            start_date = st.date_input("Data de Início", value=start_date_default, key=f"start_date_{contexto_key}")
        with col_end:
            end_date = st.date_input("Data de Fim", value=end_date_default, key=f"end_date_{contexto_key}")

        if st.button("Gerar Gráficos de Tendência", key=f"btn_gerar_graficos_{contexto_key}"):
            with st.spinner("Buscando histórico..."):
                full_history_df = backend.get_all_historical_data_sincronizado(cliente, unidade, compartimento, start_date, end_date)
                st.session_state[session_state_key] = full_history_df
            st.rerun()

        if session_state_key in st.session_state and not st.session_state[session_state_key].empty:
            df = st.session_state[session_state_key]
            for item in resultados_analise:
                item_analisado = item.get('item')
                if item_analisado:
                    fig = backend.generate_plotly_figure_sincronizado(df, item_analisado)
                    if fig: st.plotly_chart(fig, use_container_width=True)

def exibir_opcao_email(dados_laudo, resultados_analise, dados_ia, contexto_key):
    """Exibe um expansor com opções para enviar o relatório por e-mail."""
    with st.expander("✉️ Enviar Relatório por E-mail"):
        email_destinatario = st.text_input("E-mail do destinatário", key=f"email_{contexto_key}")
        incluir_graficos = st.checkbox("Incluir gráficos de tendência (último ano)", key=f"check_graficos_{contexto_key}")
        
        if st.button("Enviar E-mail", key=f"btn_email_{contexto_key}", use_container_width=True):
            if email_destinatario:
                imagens_para_email = None
                if incluir_graficos:
                    with st.spinner("Gerando gráficos..."):
                        # Lógica de geração simplificada para o exemplo
                        pass 
                
                with st.spinner("Enviando..."):
                    resultado = backend.enviar_email_laudo(email_destinatario, dados_laudo, resultados_analise, dados_ia, imagens_graficos=imagens_para_email)
                    if resultado["success"]: st.success(resultado["message"])
                    else: st.error(resultado["message"])

def formatar_status_com_icone(status):
    if status == "Crítico": return f"🔴 {status}"
    if status == "Alerta": return f"🟡 {status}"
    if status == "Normal": return f"🟢 {status}"
    return f"⚪️ {status}"

# ===================================================================
# --- 3. LOGIN E GERENCIAMENTO DE SESSÃO ---
# ===================================================================
try:
    cookies = EncryptedCookieManager(password=st.secrets["cookies"]["password"])
    if not cookies.ready(): 
        st.info("Aguardando inicialização..."); time.sleep(1); st.rerun()
except Exception as e:
    st.error(f"Erro no CookieManager: {e}"); st.stop()

if 'authenticated' not in st.session_state:
    if cookies.get('authenticated') == 'True':
        st.session_state.update({'authenticated': True, 'user_full_name': cookies.get('user_full_name'), 'is_admin': cookies.get('is_admin') == 'True'})
    else:
        st.session_state.update({'authenticated': False, 'user_full_name': "", 'is_admin': False})

if not st.session_state.get('authenticated', False):
    _, col2, _ = st.columns([1, 1.5, 1])
    with col2:
        st.image("Unax Lab CMYK.png", width=150)
        st.title("Plataforma AlexExpert")
        with st.container(border=True):
            st.header("Login de Acesso", anchor=False)
            u = st.text_input("Usuário", key="login_user")
            p = st.text_input("Senha", type="password", key="login_pass")
            if st.button("Entrar", type="primary", use_container_width=True):
                user_data = backend.verificar_usuario(u, p)
                if user_data:
                    st.session_state.update({'authenticated': True, 'user_full_name': user_data['nome'], 'is_admin': user_data['is_admin']})
                    cookies.update({'authenticated': 'True', 'user_full_name': user_data['nome'], 'is_admin': str(user_data['is_admin'])})
                    cookies.save(); st.rerun()
                else: st.error("Incorreto.")
    st.stop()

# ===================================================================
# --- 4. APP PRINCIPAL (INTERFACE APÓS LOGIN) ---
# ===================================================================
api_key = st.secrets["api_keys"]["google_ai"]
st.image("Unax Lab CMYK.png", width=120)
st.title("Plataforma AlexExpert")

with st.sidebar:
    st.success(f"Logado como:\n**{st.session_state['user_full_name']}**")
    if st.session_state['is_admin']: st.warning("👑 Administrador")
    if st.button("Sair"):
        for k in ['authenticated', 'user_full_name', 'is_admin']: 
            del st.session_state[k]
            if k in cookies: del cookies[k]
        cookies.save(); st.rerun()
    
    st.markdown("---")
    info = backend.get_system_info()
    if info:
        st.caption(f"🚀 **{info.get('system_name')}** v{info.get('version')}")
        st.caption(f"🏢 {info.get('department')}")

# --- ESTRUTURA DE ABAS ---
tab_analisar, tab_consultar, tab_gerenciar, tab_conhecimento, tab_chat = st.tabs([
    "🔍 Analisar Laudos", "📂 Consultar Análises", "⚙️ Gerenciar Parâmetros", "🧠 Base de Conhecimento", "💬 Chat"
])

# --- TAB 1: ANALISAR ---
with tab_analisar:
    st.header("Analisar Laudos Sincronizados")
    empresas = backend.get_sincronizado_empresas()
    empresa = st.selectbox("1. Selecione a Empresa", ["Selecione..."] + empresas)

    if empresa != "Selecione...":
        laudos = backend.get_laudos_sincronizados_por_empresa(empresa)
        laudo = st.selectbox("2. Selecione o Laudo", [None] + laudos, format_func=lambda x: f"ID:{x['ColetaId']} | {x['CompartimentoNome']} | {x['NumeroLaudo']}" if x else "...")
        
        if laudo:
            coleta_id = laudo['ColetaId']
            dados_laudo, resultados = backend.get_detalhes_relatorio_sincronizado_por_coleta_id(coleta_id)
            
            if dados_laudo:
                st.markdown("---")
                st.subheader(f"Resumo do Equipamento (Coleta: {coleta_id})")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Laudo", dados_laudo.get('NumeroLaudo'))
                m2.metric("Equipamento", dados_laudo.get('UnidadeNome'))
                m3.metric("Compartimento", dados_laudo.get('CompartimentoNome'))
                m4.metric("Fluido", dados_laudo.get('FluidoNome'))
                
                # Tabela de Resultados
                df_res = pd.DataFrame(resultados)[['item', 'metodo', 'resultado', 'unidade']].rename(columns={'item':'Elemento','metodo':'Método','resultado':'Resultado','unidade':'Unidade'})
                st.dataframe(df_res, use_container_width=True, hide_index=True)
                
                exibir_graficos_tendencia(dados_laudo, resultados, f"analisar_{coleta_id}")

                if st.button("🚀 Gerar Diagnóstico IA", type="primary", use_container_width=True):
                    with st.spinner("O Alexandrinho está pensando..."):
                        res = backend.gerar_diagnostico_para_laudo_existente(api_key, dados_laudo, resultados)
                        if "error" in res: st.error(res["error"])
                        else:
                            backend.salvar_diagnostico_completo_ia(dados_laudo, res["ai_response"], res["detailed_results"])
                            st.balloons(); st.rerun()

# --- TAB 2: CONSULTAR ---
with tab_consultar:
    st.header("Histórico de Análises")
    analises = backend.get_analises_ia_salvas()
    sel = st.selectbox("Selecione a análise", [None] + analises, format_func=lambda x: f"ID: {x.get('coleta_id')} | {x.get('ClienteNome')} | {x.get('numero_laudo')}" if x else "...")
    
    if sel:
        d_laudo, d_detalhes, d_ia = backend.get_detalhes_completos_analise_ia(sel['id_analise_ia'])
        if d_ia:
            nota = d_ia.get('nota_grade', 'Normal')
            if nota == 'Crítico': st.error(f"Nota: {nota}")
            elif nota == 'Alerta': st.warning(f"Nota: {nota}")
            else: st.success(f"Nota: {nota}")
            
            c1, c2 = st.columns(2)
            c1.info(f"**Diagnóstico (PT)**\n\n{d_ia.get('diagnostico_pt')}")
            c2.info(f"**Diagnosis (EN)**\n\n{d_ia.get('diagnostico_en')}")
            
            df_detalhado = pd.DataFrame(d_detalhes)
            if 'status_calculado' in df_detalhado.columns:
                df_detalhado['status_calculado'] = df_detalhado['status_calculado'].apply(formatar_status_com_icone)
            st.dataframe(df_detalhado, use_container_width=True, hide_index=True)

# --- TAB 3: GERENCIAR ---
with tab_gerenciar:
    st.header("Configuração de Limites")
    emp_ger = st.selectbox("Selecione a Empresa", ["Selecione..."] + empresas, key="sel_ger")
    if emp_ger != "Selecione...":
        params = backend.get_parametros_por_cliente(emp_ger)
        st.dataframe(params, use_container_width=True, hide_index=True)

# --- TAB 4: CONHECIMENTO (ADMIN) ---
with tab_conhecimento:
    if st.session_state['is_admin']:
        t1, t2, t3 = st.tabs(["Manual", "PDF", "Listar"])
        with t2:
            pdf = st.file_uploader("Subir base em PDF", type="pdf")
            if st.button("Processar PDF"):
                items = process_pdf_with_ai(pdf)
                if items: st.dataframe(pd.DataFrame(items), use_container_width=True)
        with t3:
            df_base, _ = backend.get_base_conhecimento_completa()
            if df_base is not None: st.dataframe(df_base, use_container_width=True)
    else: st.error("Acesso Negado.")

# --- TAB 5: CHAT ---
with tab_chat:
    st.header("💬 Chat com Alexandrinho")
    if "messages" not in st.session_state: st.session_state.messages = []
    
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
        
    if p := st.chat_input("Pergunte algo sobre análise de óleo..."):
        st.session_state.messages.append({"role": "user", "content": p})
        with st.chat_message("user"): st.markdown(p)
        
        with st.chat_message("assistant"):
            with st.spinner("Digitando..."):
                resp = backend.ask_gemini_general(p, st.session_state.messages)
                st.markdown(resp)
                st.session_state.messages.append({"role": "assistant", "content": resp})