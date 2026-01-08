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
# --- CONFIGURAÇÃO DA PÁGINA (DEVE SER O PRIMEIRO COMANDO ST) ---
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
        /* Remove margens laterais e aproveita todo o espaço */
        .block-container {
            max-width: 100% !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 1rem !important;
        }

        /* Faz as abas ocuparem a largura total e aumenta a fonte */
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
            width: 100%;
        }

        .stTabs [data-baseweb="tab"] {
            height: 60px;
            white-space: pre-wrap;
            background-color: #f8f9fb;
            border-radius: 5px 5px 0px 0px;
            padding: 10px 20px;
            flex-grow: 1; /* Faz cada aba crescer proporcionalmente */
            text-align: center;
        }

        .stTabs [data-baseweb="tab"] p {
            font-size: 18px !important;
            font-weight: bold !important;
            color: #31333F;
        }

        /* Cor da aba selecionada */
        .stTabs [aria-selected="true"] {
            background-color: #e6e9ef !important;
            border-bottom: 3px solid #ff4b4b !important;
        }
    </style>
""", unsafe_allow_html=True)

# ===================================================================
# --- RESTANTE DAS FUNÇÕES DE UI E LÓGICA ---
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
        Retorne uma lista de objetos JSON. EXEMPLO:
        [{"nome_chave": "alto_cobre", "descricao_pt": "Níveis elevados de cobre podem indicar desgaste de buchas.", "descricao_en": "High copper levels may indicate wear on bushings.", "is_recomendacao": 0}]
        Se a imagem não contiver informações relevantes, retorne uma lista vazia `[]`.
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
        st.warning("O arquivo PDF pode estar corrompido. Tente usar a função 'Salvar como PDF' do seu navegador para recriar o arquivo e tente novamente.")
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
            st.info("Não foi possível determinar a data do laudo. Sugerindo os últimos 2 meses.")
        else:
            end_date_default = data_coleta_laudo.date()
            data_anterior = backend.get_data_penultima_coleta(cliente, unidade, compartimento, end_date_default)
            if data_anterior:
                start_date_default = data_anterior.date()
                st.info(f"Período sugerido: da coleta anterior ({start_date_default.strftime('%d/%m/%Y')}) até a coleta atual.")
            else:
                start_date_default = end_date_default - pd.DateOffset(months=2)
                st.info("Nenhuma coleta anterior encontrada. Sugerindo os últimos 2 meses.")

        col_start, col_end = st.columns(2)
        with col_start:
            start_date = st.date_input("Data de Início", value=start_date_default, key=f"start_date_{contexto_key}")
        with col_end:
            end_date = st.date_input("Data de Fim", value=end_date_default, key=f"end_date_{contexto_key}")

        if st.button("Gerar Gráficos de Tendência", key=f"btn_gerar_graficos_{contexto_key}"):
            if start_date > end_date:
                st.error("Erro: A data de início não pode ser posterior à data de fim.")
                return
            if not resultados_analise:
                st.warning("Não há itens de análise para gerar gráficos.")
                return
            if cliente and unidade and compartimento:
                with st.spinner("Buscando histórico..."):
                    full_history_df = backend.get_all_historical_data_sincronizado(cliente, unidade, compartimento, start_date, end_date)
                st.session_state[session_state_key] = full_history_df
                st.rerun()

        if session_state_key in st.session_state and not st.session_state[session_state_key].empty:
            full_history_df = st.session_state[session_state_key]
            if len(full_history_df['DataColeta'].unique()) < 2:
                st.info("Não há dados históricos suficientes para gerar gráficos de tendência.")
            else:
                st.write(f"Exibindo histórico para: **{cliente} / {unidade} / {compartimento}**")
                for item in resultados_analise:
                    item_analisado = item.get('item')
                    if item_analisado:
                        fig = backend.generate_plotly_figure_sincronizado(full_history_df, item_analisado)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)

def exibir_opcao_email(dados_laudo, resultados_analise, dados_ia, contexto_key):
    """Exibe um expansor com opções para enviar o relatório por e-mail."""
    with st.expander("✉️ Enviar Relatório por E-mail"):
        email_destinatario = st.text_input("E-mail do destinatário", key=f"email_{contexto_key}")
        incluir_graficos = st.checkbox("Incluir gráficos de tendência no e-mail (último ano)", key=f"check_graficos_{contexto_key}")
        if st.button("Enviar E-mail", key=f"btn_email_{contexto_key}", use_container_width=True):
            if email_destinatario:
                imagens_para_email = None
                if incluir_graficos:
                    with st.spinner("Gerando imagens dos gráficos para o e-mail..."):
                        end_date_email = pd.to_datetime(dados_laudo.get('DataColeta')).date() if pd.notna(dados_laudo.get('DataColeta')) else datetime.now().date()
                        start_date_email = end_date_email - timedelta(days=365)
                        full_history_df = backend.get_all_historical_data_sincronizado(
                            dados_laudo.get('ClienteNome'),
                            dados_laudo.get('CompartimentoNome'),
                            start_date=start_date_email,
                            end_date=end_date_email
                        )
                        if not full_history_df.empty:
                            imagens_para_email = backend.gerar_imagens_graficos(full_history_df, resultados_analise)
                with st.spinner("Enviando e-mail..."):
                    resultado = backend.enviar_email_laudo(email_destinatario, dados_laudo, resultados_analise, dados_ia, imagens_graficos=imagens_para_email)
                if resultado["success"]: st.success(resultado["message"])
                else: st.error(resultado["message"])
            else: st.warning("Por favor, insira um e-mail válido.")

def formatar_status_com_icone(status):
    if status == "Crítico": return f"🔴 {status}"
    if status == "Alerta": return f"🟡 {status}"
    if status == "Normal": return f"🟢 {status}"
    return f"⚪️ {status}"

# ===================================================================
# --- LOGIN E ESTRUTURA PRINCIPAL DO APP ---
# ===================================================================
try:
    cookies = EncryptedCookieManager(password=st.secrets["cookies"]["password"])
    if not cookies.ready(): 
        st.info("Aguardando inicialização da sessão...")
        time.sleep(1); st.rerun()
except Exception as e:
    st.error(f"Erro ao carregar o gerenciador de cookies: {e}"); st.stop()

if 'authenticated' not in st.session_state:
    if cookies.get('authenticated') == 'True':
        st.session_state['authenticated'] = True
        st.session_state['user_full_name'] = cookies.get('user_full_name')
        st.session_state['is_admin'] = cookies.get('is_admin') == 'True'
    else:
        st.session_state['authenticated'] = False
        st.session_state['user_full_name'] = ""
        st.session_state['is_admin'] = False

if not st.session_state.get('authenticated', False):
    _, col2, _ = st.columns([1, 1.5, 1])
    with col2:
        st.image("Unax Lab CMYK.png", width=120)
        st.title("Plataforma AlexExpert")
        with st.container(border=True):
            st.header("Login de Acesso", anchor=False)
            username = st.text_input("Usuário", key="login_user")
            password = st.text_input("Senha", type="password", key="login_pass")
            if st.button("Entrar", type="primary", use_container_width=True):
                with st.spinner("Verificando..."):
                    user_data = backend.verificar_usuario(username, password)
                if user_data:
                    st.session_state['authenticated'] = True
                    st.session_state['user_full_name'] = user_data['nome']
                    st.session_state['is_admin'] = user_data['is_admin']
                    cookies['authenticated'] = 'True'
                    cookies['user_full_name'] = user_data['nome']
                    cookies['is_admin'] = str(user_data['is_admin'])
                    cookies.save(); st.rerun()
                else: st.error("Usuário ou senha inválidos.")
else:
    api_key = st.secrets["api_keys"]["google_ai"]
    st.image("Unax Lab CMYK.png", width=120)
    st.title("Plataforma AlexExpert")

    with st.sidebar:
        st.success(f"Bem-vindo(a),\n**{st.session_state['user_full_name']}**!")
        if st.session_state.get('is_admin', False): st.warning("👑 Acesso de Administrador")
        if st.button("Logout"):
            for key in ['authenticated', 'user_full_name', 'is_admin']:
                if key in st.session_state: del st.session_state[key]
                if key in cookies: del cookies[key]
            cookies.save(); st.rerun()

        st.markdown("""<style>.sidebar-bottom {position: absolute; bottom: 10px; width: 90%;}</style>""", unsafe_allow_html=True)
        with st.container():
            st.markdown('<div class="sidebar-bottom">', unsafe_allow_html=True)
            info = backend.get_system_info()
            if info:
                st.markdown("---")
                st.caption(f"🚀 **Sistema:** {info.get('system_name', 'N/A')} (v{info.get('version', '1.0')})")
                st.caption(f"👨‍💻 **Desenvolvedor:** {info.get('developer', 'N/A')}")
                st.caption(f"🏢 **Departamento:** {info.get('department', 'N/A')}")
            st.markdown('</div>', unsafe_allow_html=True)

    # --- ABAS QUE AGORA OCUPAM TODA A LARGURA ---
    tab_analisar, tab_consultar, tab_gerenciar, tab_conhecimento, tab_chat = st.tabs([
        "🔍 Analisar Laudos", "📂 Consultar Análises", "⚙️ Gerenciar Parâmetros", "🧠 Base de Conhecimento", "💬 Chat"
    ])
    
    with tab_analisar:
        st.header("Analisar Laudos Sincronizados")
        empresas_sinc = backend.get_sincronizado_empresas()
        empresa_escolhida = st.selectbox("1. Selecione a Empresa", ["Selecione..."] + empresas_sinc, key="select_empresa_analisar")

        if empresa_escolhida and empresa_escolhida != "Selecione...":
            laudos = backend.get_laudos_sincronizados_por_empresa(empresa_escolhida)
            laudo_selecionado = st.selectbox("2. Selecione o Laudo", [None] + laudos, format_func=lambda x: f"ID:{x['ColetaId']} | {x['CompartimentoNome']} | Laudo: {x['NumeroLaudo']}" if x else "...", key="select_laudo_analisar")
            if laudo_selecionado:
                coleta_id = laudo_selecionado['ColetaId']
                dados_laudo, resultados_analise = backend.get_detalhes_relatorio_sincronizado_por_coleta_id(coleta_id)
                if dados_laudo and resultados_analise:
                    st.markdown("---")
                    st.subheader(f"Detalhes do Laudo Selecionado (Coleta ID: {coleta_id})")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Número do Laudo", dados_laudo.get('NumeroLaudo', 'N/A'))
                        st.metric("Unidade/Equipamento", dados_laudo.get('UnidadeNome', 'N/A'))
                        st.metric("Compartimento", dados_laudo.get('CompartimentoNome', 'N/A'))
                    with col2:
                        st.metric("Horímetro do Compartimento", f"{dados_laudo.get('HorimetroCompartimento', 0):.1f} h")
                        st.metric("Horímetro do Lubrificante", f"{dados_laudo.get('HorimetroLubrificante', 0):.1f} h")
                    with col3:
                        st.metric("Fluido", dados_laudo.get('FluidoNome', 'N/A'))
                        st.metric("Marca do Fluido", dados_laudo.get('MarcaNome', 'N/A'))
                    with col4:
                        st.metric("Categoria", dados_laudo.get('CategoriaNome', 'N/A'))
                        st.metric("SubCategoria", dados_laudo.get('SubCategoriaNome', 'N/A'))
                    
                    st.markdown("---")
                    st.subheader("Resultados da Análise")
                    df_bruto = pd.DataFrame(resultados_analise)
                    df_display = df_bruto[['item', 'metodo', 'resultado', 'unidade']].rename(columns={'item': 'Elemento', 'metodo': 'Método', 'resultado': 'Resultado', 'unidade': 'Unidade'})
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                    
                    exibir_graficos_tendencia(dados_laudo, resultados_analise, f"analisar_{coleta_id}")

                    if st.button("Gerar e Guardar Diagnóstico de IA", type="primary", key=f"btn_gerar_{coleta_id}"):
                        with st.spinner("Gerando diagnóstico com Alexandrinho..."):
                            analysis_result = backend.gerar_diagnostico_para_laudo_existente(api_key, dados_laudo, resultados_analise)
                        
                        if "error" in analysis_result: st.error(analysis_result['error'])
                        else:
                            ai_response = analysis_result.get("ai_response", {})
                            detailed_results = analysis_result.get("detailed_results", [])
                            backend.salvar_diagnostico_completo_ia(dados_laudo, ai_response, detailed_results)
                            st.balloons()
                            
                            col_pt, col_en = st.columns(2)
                            with col_pt:
                                st.info(f"**Diagnóstico (PT):**\n\n{ai_response.get('diagnostico_pt','N/A')}")
                                st.info(f"**Recomendação (PT):**\n\n{ai_response.get('recomendacao_pt','N/A')}")
                            with col_en:
                                st.info(f"**Diagnosis (EN):**\n\n{ai_response.get('diagnostico_en','N/A')}")
                                st.info(f"**Recomendation (EN):**\n\n{ai_response.get('recomendacao_en','N/A')}")

                            df_detalhado = pd.DataFrame(detailed_results)
                            if 'Status Calculado' in df_detalhado.columns:
                                df_detalhado['Status Calculado'] = df_detalhado['Status Calculado'].apply(formatar_status_com_icone)
                            st.dataframe(df_detalhado, use_container_width=True, hide_index=True)

    with tab_consultar:
        st.header("Consultar Análises Salvas")
        analises = backend.get_analises_ia_salvas()
        analise_selecionada = st.selectbox("Selecione uma análise", [None] + analises, format_func=lambda x: f"ID Coleta: {x.get('coleta_id')} | {x.get('ClienteNome')} | Laudo: {x.get('numero_laudo')}" if x else "...", key="select_analise_consulta")
        if analise_selecionada:
            id_analise = analise_selecionada['id_analise_ia']
            dados_laudo, resultados_detalhados, dados_ia = backend.get_detalhes_completos_analise_ia(id_analise)
            if dados_laudo:
                st.subheader(f"Detalhes do Laudo (Coleta ID: {dados_laudo['ColetaId']})")
                col_pt, col_en = st.columns(2)
                with col_pt:
                    st.info(f"**Diagnóstico (PT):**\n\n{dados_ia.get('diagnostico_pt','N/A')}")
                with col_en:
                    st.info(f"**Diagnosis (EN):**\n\n{dados_ia.get('diagnostico_en','N/A')}")
                df_detalhado = pd.DataFrame(resultados_detalhados)
                st.dataframe(df_detalhado, use_container_width=True, hide_index=True)

    with tab_gerenciar:
        st.header("Gerenciar Parâmetros de Diagnóstico por Cliente")
        empresas = backend.get_sincronizado_empresas()
        cliente_selecionado = st.selectbox("1. Selecione a Empresa", ["Selecione..."] + empresas, key="select_empresa_gerenciar")
        if cliente_selecionado and cliente_selecionado != "Selecione...":
            parametros_atuais = backend.get_parametros_por_cliente(cliente_selecionado)
            st.dataframe(parametros_atuais, use_container_width=True)

    with tab_conhecimento:
        if st.session_state.get('is_admin', False):
            tab_add, tab_pdf, tab_list = st.tabs(["➕ Inserção Manual", "📄 Extrair de PDF", "📊 Listar Base"])
            with tab_list:
                df, error = backend.get_base_conhecimento_completa()
                if df is not None: st.dataframe(df, use_container_width=True)
        else: st.error("Acesso reservado para administradores.")

    with tab_chat:
        st.header("💬 Chat com Alexandrinho")
        if "messages" not in st.session_state: st.session_state.messages = []
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        if prompt := st.chat_input("Sua mensagem..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("assistant"):
                response = backend.ask_gemini_general(prompt, st.session_state.messages)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})