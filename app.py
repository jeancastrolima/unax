import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import backend
import fitz  # PyMuPDF
import re
import json
import google.generativeai as genai
from streamlit_cookies_manager import EncryptedCookieManager
from datetime import timedelta
import time

# ===================================================================
# --- CSS GLOBAL COM BOOTSTRAP + ROBOTO + ESTILO MODERNO ---
# ===================================================================
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
html, body, [class*="css"]  { font-family: 'Roboto', sans-serif; }

/* Layout principal */
.stApp {
    max-width: 100% !important;
    padding: 1rem 2rem 2rem 2rem;
    background-color: #f5f6fa;
}

/* Containers principais */
.stContainer, .stFrame {
    background-color: #ffffff;
    padding: 1.2rem 1.5rem;
    border-radius: 12px;
    box-shadow: 0 6px 16px rgba(0,0,0,0.05);
    margin-bottom: 1.5rem;
}

/* Cabeçalhos */
h1, h2, h3, h4, h5, h6 { font-weight: 500; color: #212529; }

/* Inputs e selects */
input, select, textarea, .stTextInput>div>input {
    border-radius: 8px !important;
    border: 1px solid #ced4da !important;
    padding: 0.55rem !important;
    font-size: 0.95rem !important;
}
.stSelectbox>div>div>div { border-radius: 8px !important; }
.stMultiSelect>div>div>div { border-radius: 8px !important; }

/* Botões */
button, .stButton>button {
    background-color: #0d6efd !important;
    color: white !important;
    border-radius: 8px !important;
    padding: 0.5rem 1rem !important;
    font-weight: 500 !important;
}
button:hover, .stButton>button:hover { background-color: #0b5ed7 !important; }

/* Tabelas */
.dataframe-container, .stDataFrame>div>div { width: 100% !important; overflow-x: auto !important; }

/* Sidebar */
.sidebar .sidebar-content {
    background-color: #ffffff !important;
    padding: 1rem;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}

/* Expansores */
.stExpander {
    background-color: #ffffff;
    border-radius: 10px;
    padding: 0.75rem 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 6px rgba(0,0,0,0.05);
}

/* Métricas */
.stMetric {
    background-color: #e9ecef;
    border-radius: 10px;
    padding: 0.75rem;
    text-align: center;
}

/* Chatbox */
.stChatMessage {
    border-radius: 12px;
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.5rem;
}
</style>
""", unsafe_allow_html=True)

# ===================================================================
# --- FUNÇÕES AUXILIARES (IA, PDF, Gráficos, E-mail) ---
# ===================================================================
def analyze_image_with_ai(image_file):
    """Usa IA para extrair informações estruturadas de uma imagem."""
    model = genai.GenerativeModel("models/gemini-2.5-flash")
    image_part = {'mime_type': image_file.type, 'data': image_file.getvalue()}
    
    prompt = [
        """
        Você é um assistente especializado em análise de fluidos. 
        Extraia cada condição em JSON: nome_chave (snake_case), descricao_pt, descricao_en, is_recomendacao (0=diagnóstico, 1=recomendação)
        Retorne [] se não houver informação relevante.
        """,
        image_part
    ]
    
    try:
        response = model.generate_content(prompt)
        match = re.search(r'\[.*\]', response.text, re.DOTALL)
        return json.loads(match.group(0)) if match else []
    except Exception as e:
        st.error(f"Erro IA: {e}")
        return []

def process_pdf_with_ai(pdf_file):
    """Processa PDF página a página usando IA."""
    try:
        doc = fitz.open(stream=pdf_file.getvalue(), filetype="pdf")
        all_results = []
        progress_bar = st.progress(0, text="Processando PDF...")
        for i, page in enumerate(doc):
            pix = page.get_pixmap()
            img_bytes = pix.tobytes("png")
            img_buffer = BytesIO(img_bytes)
            img_buffer.type = "image/png"
            result = analyze_image_with_ai(img_buffer)
            if result: all_results.extend(result)
            progress_bar.progress((i+1)/len(doc), text=f"Página {i+1}/{len(doc)}")
        progress_bar.empty()
        return all_results
    except Exception as e:
        st.error(f"Erro PDF: {e}")
        return None

def formatar_status_com_icone(status):
    if status == "Crítico": return f"🔴 {status}"
    if status == "Alerta": return f"🟡 {status}"
    if status == "Normal": return f"🟢 {status}"
    return f"⚪️ {status}"

# ===================================================================
# --- LOGIN / SESSÃO ---
# ===================================================================
try:
    cookies = EncryptedCookieManager(password=st.secrets["cookies"]["password"])
    if not cookies.ready(): st.info("Inicializando sessão..."); time.sleep(1); st.rerun()
except Exception as e:
    st.error(f"Erro cookies: {e}"); st.stop()

if 'authenticated' not in st.session_state:
    if cookies.get('authenticated') == 'True':
        st.session_state['authenticated'] = True
        st.session_state['user_full_name'] = cookies.get('user_full_name')
        st.session_state['is_admin'] = cookies.get('is_admin') == 'True'
    else:
        st.session_state['authenticated'] = False
        st.session_state['user_full_name'] = ""
        st.session_state['is_admin'] = False

# --- LOGIN UI ---
if not st.session_state.get('authenticated', False):
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.image("Unax Lab CMYK.png", width=140)
        st.title("Plataforma AlexExpert")
        with st.container():
            st.header("Login")
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            if st.button("Entrar", type="primary", use_container_width=True):
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
    st.image("Unax Lab CMYK.png", width=140)
    st.title("Plataforma AlexExpert")

    # --- SIDEBAR ---
    with st.sidebar:
        st.success(f"Bem-vindo(a), **{st.session_state['user_full_name']}**!")
        if st.session_state.get('is_admin', False): st.warning("👑 Administrador")
        if st.button("Logout"):
            for key in ['authenticated','user_full_name','is_admin']:
                st.session_state.pop(key, None)
                if key in cookies: del cookies[key]
            cookies.save(); st.rerun()
        st.markdown("---")
        info = backend.get_system_info()
        if info:
            st.caption(f"🚀 Sistema: {info.get('system_name','N/A')} (v{info.get('version','1.0')})")
            st.caption(f"👨‍💻 Desenvolvedor: {info.get('developer','N/A')}")
            st.caption(f"🏢 Departamento: {info.get('department','N/A')}")

    # --- TABS PRINCIPAIS ---
    tab_analisar, tab_consultar, tab_gerenciar, tab_conhecimento, tab_chat = st.tabs([
        "🔍 Analisar Laudos", "📂 Consultar", "⚙️ Gerenciar", "🧠 Base Conhecimento", "💬 Chat"
    ])

    # Aqui você pode adicionar o resto da lógica de cada aba, mantendo as funções existentes
    # Todos os inputs, selectboxes, file uploaders e botões agora terão o estilo moderno
    # Tabelas DataFrame e expansores já estão estilizados e responsivos

    
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
                    st.dataframe(df_display, width='stretch', hide_index=True)
                    
                    exibir_graficos_tendencia(dados_laudo, resultados_analise, f"analisar_{coleta_id}")

                    if st.button("Gerar e Guardar Diagnóstico de IA", type="primary", key=f"btn_gerar_{coleta_id}"):
                        with st.spinner("Gerando diagnóstico com Alexandrinho..."):
                            
                            analysis_result = backend.gerar_diagnostico_para_laudo_existente(api_key, dados_laudo, resultados_analise)
                        
                        if "error" in analysis_result:
                            st.error(analysis_result['error'])
                        else:
                            ai_response, detailed_results = analysis_result.get("ai_response", {}), analysis_result.get("detailed_results", [])
                            with st.spinner("Guardando análise no banco de dados..."):
                                save_status = backend.salvar_diagnostico_completo_ia(dados_laudo, ai_response, detailed_results)
                            
                            if save_status["success"]:
                                st.success(save_status["message"])
                                st.balloons()
                            else:
                                st.error(save_status["message"])
                            
                            nota_g = ai_response.get('nota_grade', 'Normal')
                            if nota_g == 'Crítico': st.error(f"**Nota:** {nota_g}")
                            elif nota_g == 'Alerta': st.warning(f"**Nota:** {nota_g}")
                            else: st.success(f"**Nota:** {nota_g}")

                            col_pt, col_en = st.columns(2)
                            with col_pt:
                                st.info(f"**Diagnóstico (PT):**\n\n{ai_response.get('diagnostico_pt','N/A')}")
                                st.info(f"**Recomendação (PT):**\n\n{ai_response.get('recomendacao_pt','N/A')}")
                            with col_en:
                                st.info(f"**Diagnosis (EN):**\n\n{ai_response.get('diagnostico_en','N/A')}")
                                st.info(f"**Recomendation (EN):**\n\n{ai_response.get('recomendacao_en','N/A')}")

                            st.markdown("---")
                            st.subheader("Resultados Detalhados com Limites Aplicados")
                            df_detalhado = pd.DataFrame(detailed_results)
                            if 'Status Calculado' in df_detalhado.columns:
                                df_detalhado['Status Calculado'] = df_detalhado['Status Calculado'].apply(formatar_status_com_icone)
                            st.dataframe(df_detalhado, width='stretch', hide_index=True)
                            exibir_opcao_email(dados_laudo, resultados_analise, ai_response, f"email_analisar_{coleta_id}")

    with tab_consultar:
        st.header("Consultar Análises Salvas")
        analises = backend.get_analises_ia_salvas()
        analise_selecionada = st.selectbox("Selecione uma análise", [None] + analises, format_func=lambda x: f"ID Coleta: {x.get('coleta_id')} | {x.get('ClienteNome')} | Laudo: {x.get('numero_laudo')}" if x else "...", key="select_analise_consulta")
        if analise_selecionada:
            id_analise = analise_selecionada['id_analise_ia']
            dados_laudo, resultados_detalhados, dados_ia = backend.get_detalhes_completos_analise_ia(id_analise)
            if dados_laudo:
                st.markdown("---")
                st.subheader(f"Detalhes do Laudo (Coleta ID: {dados_laudo['ColetaId']})")
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
                nota_g = dados_ia.get('nota_grade', 'Normal')
                if nota_g == 'Crítico': st.error(f"**Nota:** {nota_g}")
                elif nota_g == 'Alerta': st.warning(f"**Nota:** {nota_g}")
                else: st.success(f"**Nota:** {nota_g}")

                col_pt, col_en = st.columns(2)
                with col_pt:
                    st.info(f"**Diagnóstico (PT):**\n\n{dados_ia.get('diagnostico_pt','N/A')}")
                    st.info(f"**Recomendação (PT):**\n\n{dados_ia.get('recomendacao_pt','N/A')}")
                with col_en:
                    st.info(f"**Diagnosis (EN):**\n\n{dados_ia.get('diagnostico_en','N/A')}")
                    st.info(f"**Recomendation (EN):**\n\n{dados_ia.get('recomendacao_en','N/A')}")

                st.markdown("---")
                st.subheader("Resultados Detalhados da Análise Salva")
                df_detalhado = pd.DataFrame(resultados_detalhados)
                colunas_rename_db = {
                    'elemento_nome': 'Elemento', 'resultado_valor': 'Resultado', 'unidade': 'Unidade',
                    'status_calculado': 'Status', 
                    'limite_min_alerta_aplicado': 'Mínimo Alerta', 'limite_min_critico_aplicado': 'Mínimo Crítico',
                    'limite_max_alerta_aplicado': 'Máximo Alerta', 'limite_max_critico_aplicado': 'Máximo Crítico'
                }
                df_detalhado_display = df_detalhado.rename(columns=colunas_rename_db)
                if 'Status' in df_detalhado_display.columns:
                    df_detalhado_display['Status'] = df_detalhado_display['Status'].apply(formatar_status_com_icone)
                st.dataframe(df_detalhado_display, width='stretch', hide_index=True)

                _, resultados_brutos = backend.get_detalhes_relatorio_sincronizado_por_coleta_id(dados_laudo['ColetaId'])
                exibir_graficos_tendencia(dados_laudo, resultados_brutos, f"consultar_{id_analise}")
                exibir_opcao_email(dados_laudo, resultados_brutos, dados_ia, f"consultar_email_{id_analise}")

    with tab_gerenciar:
        st.header("Gerenciar Parâmetros de Diagnóstico por Cliente")
        empresas = backend.get_sincronizado_empresas()
        cliente_selecionado = st.selectbox("1. Selecione a Empresa", ["Selecione..."] + empresas, key="select_empresa_gerenciar")

        if cliente_selecionado and cliente_selecionado != "Selecione...":
            st.markdown("---")
            st.subheader(f"Parâmetros Atuais para: **{cliente_selecionado}**")
            parametros_atuais = backend.get_parametros_por_cliente(cliente_selecionado)
            if parametros_atuais.empty:
                st.info("Nenhum parâmetro customizado encontrado.")
            else:
                for _, row in parametros_atuais.iterrows():
                    st.markdown(f"##### {row['elemento_nome']}")
                    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
                    c1.metric("Mínimo Alerta", str(row['limite_min_alerta']) if pd.notna(row['limite_min_alerta']) else "N/A")
                    c2.metric("Mínimo Crítico", str(row['limite_min_critico']) if pd.notna(row['limite_min_critico']) else "N/A")
                    c3.metric("Máximo Alerta", str(row['limite_max_alerta']) if pd.notna(row['limite_max_alerta']) else "N/A")
                    c4.metric("Máximo Crítico", str(row['limite_max_critico']) if pd.notna(row['limite_max_critico']) else "N/A")
                    if c5.button("Deletar", key=f"del_{row['id_parametro']}", use_container_width=True):
                        backend.deletar_parametro(row['id_parametro']); st.rerun()
            
            st.markdown("---")
            st.subheader(f"Adicionar Novos Parâmetros para: **{cliente_selecionado}**")
            
            elementos_disponiveis = backend.get_elementos()
            if not elementos_disponiveis:
                st.error("ERRO: A tabela 'elementos' está vazia. Adicione os elementos de análise primeiro.")
            else:
                with st.form("novo_parametro_form"):
                    elementos_existentes = parametros_atuais['elemento_nome'].tolist() if not parametros_atuais.empty else []
                    elementos_filtrados = [e for e in elementos_disponiveis if e['nome'] not in elementos_existentes]
                    if not elementos_filtrados:
                        st.warning("Todos os elementos disponíveis já possuem parâmetros definidos para este cliente.")
                        st.form_submit_button("Salvar", disabled=True)
                    else:
                        elementos_selecionados = st.multiselect("Selecione os elementos", elementos_filtrados, format_func=lambda x: x['nome'])
                        novos_parametros = []
                        if elementos_selecionados:
                            for el in elementos_selecionados:
                                st.write(f"**{el['nome']}**")
                                c1, c2 = st.columns(2)
                                c3, c4 = st.columns(2)
                                
                                is_text_input = 'iso' in el['nome'].lower() or 'nas' in el['nome'].lower()
                                
                                if is_text_input:
                                    min_a = c1.text_input("Mínimo Alerta", key=f"min_a_{el['id_elemento']}", placeholder="N/A")
                                    min_c = c2.text_input("Mínimo Crítico", key=f"min_c_{el['id_elemento']}", placeholder="N/A")
                                    max_a = c3.text_input("Máximo Alerta", key=f"max_a_{el['id_elemento']}", placeholder="Ex: 18/16/13")
                                    max_c = c4.text_input("Máximo Crítico", key=f"max_c_{el['id_elemento']}", placeholder="Ex: 20/18/15")
                                else:
                                    min_a = c1.text_input("Mínimo Alerta", key=f"min_a_{el['id_elemento']}", placeholder="Ex: 115.2 ou 115,2")
                                    min_c = c2.text_input("Mínimo Crítico", key=f"min_c_{el['id_elemento']}", placeholder="Ex: 100.0 ou 100,0")
                                    max_a = c3.text_input("Máximo Alerta", key=f"max_a_{el['id_elemento']}", placeholder="Ex: 140.8 ou 140,8")
                                    max_c = c4.text_input("Máximo Crítico", key=f"max_c_{el['id_elemento']}", placeholder="Ex: 150.0 ou 150,0")
                                
                                novos_parametros.append({
                                    "id_elemento": el['id_elemento'],
                                    "limite_min_alerta": min_a or None, "limite_min_critico": min_c or None,
                                    "limite_max_alerta": max_a or None, "limite_max_critico": max_c or None
                                })
                        
                        if st.form_submit_button("Salvar Novos Parâmetros"):
                            params_validos = [p for p in novos_parametros if p['limite_min_alerta'] or p['limite_min_critico'] or p['limite_max_alerta'] or p['limite_max_critico']]
                            if not params_validos:
                                st.warning("Defina ao menos um limite para os elementos.")
                            else:
                                result = backend.salvar_novos_parametros(cliente_selecionado, params_validos)
                                if result['success']: st.success(result['message']); st.rerun()
                                else: st.error(result['message'])

    with tab_conhecimento:
        
        if st.session_state.get('is_admin', False):
            tab_add, tab_pdf, tab_list = st.tabs(["➕ Inserção Manual", "📄 Extrair de PDF", "📊 Listar Base"])
            with tab_add:
                with st.form("form_inserir_diagnostico"):
                    nome_chave = st.text_input("Nome Chave (Ex: 'alto_cobre')")
                    descricao_pt = st.text_area("Descrição em Português")
                    descricao_en = st.text_area("Descrição em Inglês (Opcional)")
                    is_recomendacao = st.checkbox("Marque se isto for uma RECOMENDAÇÃO")
                    if st.form_submit_button("Salvar na Base de Conhecimento"):
                        if not nome_chave or not descricao_pt:
                            st.error("Nome Chave e Descrição (PT) são obrigatórios.")
                        else:
                            data = {"nome_chave": nome_chave, "descricao_pt": descricao_pt, "descricao_en": descricao_en, "is_recomendacao": 1 if is_recomendacao else 0}
                            success, message = backend.salvar_item_conhecimento(data)
                            if success: st.success(message)
                            else: st.error(message)

            with tab_pdf:
                if 'ai_result_pdf' not in st.session_state: st.session_state.ai_result_pdf = None
                pdf_file = st.file_uploader("Carregar PDF", type=["pdf"])
                if st.button("Processar PDF com IA"):
                    if pdf_file:
                        st.session_state.ai_result_pdf = process_pdf_with_ai(pdf_file)
                    else:
                        st.warning("Carregue um arquivo PDF primeiro.")
                if st.session_state.ai_result_pdf:
                    st.dataframe(pd.DataFrame(st.session_state.ai_result_pdf), width='stretch')
                    if st.button("Salvar Itens Extraídos no DB", type="primary"):
                        with st.spinner("Salvando..."):
                            for item in st.session_state.ai_result_pdf:
                                _, message = backend.salvar_item_conhecimento(item)
                                st.info(message)
                        st.session_state.ai_result_pdf = None; st.rerun()

            with tab_list:
                st.subheader("Base de Conhecimento Salva")
                df, error = backend.get_base_conhecimento_completa()
                if error: st.error(error)
                elif df is not None and not df.empty:
                    df['is_recomendacao'] = df['is_recomendacao'].apply(lambda x: 'Sim' if x else 'Não')
                    df = df.rename(columns={'nome_chave': 'Nome Chave', 'descricao_pt': 'Descrição (PT)', 'descricao_en': 'Descrição (EN)', 'is_recomendacao': 'É Recomendação?'})
                    st.dataframe(df, width='stretch')
                else:
                    st.info("A base de conhecimento está vazia.")
        else:
            
            st.error("Esta área é reservada para administradores do sistema.")
            

    with tab_chat:
        st.header("💬 Chat com Alexandrinho")
        st.image("70e48960-7759-4d1d-ad26-3ff4e7bc7787 (1).jpeg", width=120)
        if "messages" not in st.session_state: st.session_state.messages = [{"role": "assistant", "content": f"Olá, {st.session_state.get('user_full_name', '')}! Como posso ajudar?"}]
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        if prompt := st.chat_input("Sua mensagem..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.chat_message("user").markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Pensando..."):
                    history = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in st.session_state.messages]
                    response = backend.ask_gemini_general(prompt, history)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})