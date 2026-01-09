import streamlit as st
from datetime import datetime, timedelta
import backend  # Certifique-se que o backend.py está na mesma pasta
import pandas as pd
from streamlit_cookies_manager import EncryptedCookieManager
import time
import google.generativeai as genai
import json
import re
import fitz  # PyMuPDF
from io import BytesIO

# ===================================================================
# --- CONFIGURAÇÃO DA PÁGINA E CSS (ESTILO BOOTSTRAP) ---
# ===================================================================
st.set_page_config(
    page_title="Alexpert | Unax Lab",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

def local_css():
    st.markdown("""
        <style>
        /* Importando fonte moderna */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        /* Estilo para simular Cards do Bootstrap */
        div[data-testid="stVerticalBlock"] > div[style*="border"] {
            background-color: #ffffff;
            border: 1px solid #e6e9ef !important;
            border-radius: 12px !important;
            padding: 20px !important;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
            margin-bottom: 15px;
        }

        /* Melhorando botões */
        .stButton>button {
            border-radius: 8px;
            transition: all 0.3s ease;
            font-weight: 600;
        }
        
        .stButton>button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }

        /* Status Colors */
        .status-normal { color: #28a745; font-weight: bold; }
        .status-alerta { color: #ffc107; font-weight: bold; }
        .status-critico { color: #dc3545; font-weight: bold; }

        /* Sidebar custom */
        [data-testid="stSidebar"] {
            background-color: #f8f9fa;
            border-right: 1px solid #dee2e6;
        }
        
        /* Sidebar footer fix */
        .sidebar-footer {
            position: fixed;
            bottom: 20px;
            left: 20px;
            width: 260px;
            font-size: 0.8rem;
            color: #6c757d;
        }
        </style>
    """, unsafe_allow_html=True)

local_css()



# ===================================================================
# --- FUNÇÕES DE UI E LÓGICA ---
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
        
        # --- LÓGICA DE DATAS CORRIGIDA FINAL ---
        data_coleta_laudo = pd.to_datetime(dados_laudo.get('DataColeta'), errors='coerce')

        if pd.isna(data_coleta_laudo):
            end_date_default = datetime.now().date()
            start_date_default = end_date_default - pd.DateOffset(months=2)
            st.info("Não foi possível determinar a data do laudo. Sugerindo os últimos 2 meses.")
        else:
            # A data de FIM padrão é a data do próprio laudo que estamos vendo.
            end_date_default = data_coleta_laudo.date()
            
            # Busca a data da coleta ANTERIOR
            data_anterior = backend.get_data_penultima_coleta(cliente, unidade, compartimento, end_date_default)
            
            if data_anterior:
                # Se encontrou, a data de INÍCIO é a data anterior.
                start_date_default = data_anterior.date()
                st.info(f"Período sugerido: da coleta anterior ({start_date_default.strftime('%d/%m/%Y')}) até a coleta atual.")
            else:
                # Plano B: se não houver coleta anterior, sugere os últimos 2 meses.
                start_date_default = end_date_default - pd.DateOffset(months=2)
                st.info("Nenhuma coleta anterior encontrada. Sugerindo os últimos 2 meses.")

        col_start, col_end = st.columns(2)
        with col_start:
            start_date = st.date_input("Data de Início", value=start_date_default, key=f"start_date_{contexto_key}")
        with col_end:
            end_date = st.date_input("Data de Fim", value=end_date_default, key=f"end_date_{contexto_key}")
        # --- FIM DA LÓGICA DE DATAS ---

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
        elif session_state_key in st.session_state and st.session_state[session_state_key].empty:
             st.info("Nenhum dado histórico encontrado para o período selecionado.")

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
                    resultado = backend.enviar_email_laudo(
                        email_destinatario, dados_laudo, resultados_analise, dados_ia,
                        imagens_graficos=imagens_para_email
                    )
                if resultado["success"]:
                    st.success(resultado["message"])
                else:
                    st.error(resultado["message"])
            else:
                st.warning("Por favor, insira um e-mail válido.")

def formatar_status_com_icone(status):
    """Adiciona um ícone a um texto de status para destaque visual."""
    if status == "Crítico":
        return f"🔴 {status}"
    if status == "Alerta":
        return f"🟡 {status}"
    if status == "Normal":
        return f"🟢 {status}"
    return f"⚪️ {status}" # Para "Indeterminado" ou outros

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
        
        
        st.title("Plataforma Alexpert")
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
                else:
                    st.error("Usuário ou senha inválidos.")
else:
    api_key = st.secrets["api_keys"]["google_ai"]
    st.image("Unax Lab CMYK.png", width=120)
    st.title("Plataforma Alexpert")

    with st.sidebar:
        st.success(f"Bem-vindo(a),\n**{st.session_state['user_full_name']}**!")
        if st.session_state.get('is_admin', False):
            st.warning("👑 Acesso de Administrador")
        if st.button("Logout"):
            if 'authenticated' in st.session_state: del st.session_state['authenticated']
            if 'user_full_name' in st.session_state: del st.session_state['user_full_name']
            if 'is_admin' in st.session_state: del st.session_state['is_admin']
            
            if 'authenticated' in cookies: del cookies['authenticated']
            if 'user_full_name' in cookies: del cookies['user_full_name']
            if 'is_admin' in cookies: del cookies['is_admin']
            
            cookies.save()
            st.rerun()

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
                    st.dataframe(df_display, width='stretch', hide_index=True)
                    
                    exibir_graficos_tendencia(dados_laudo, resultados_analise, f"analisar_{coleta_id}")

                    if st.button("Gerar e Guardar Diagnóstico de IA", type="primary", key=f"btn_gerar_{coleta_id}"):
                    if st.button("Gerar e Guardar Diagnóstico de IA", type="primary", key=f"btn_gerar_{coleta_id}"):

    robot_placeholder = st.empty()

    robot_placeholder.markdown(
        """
        <div style="display:flex; justify-content:center; margin-top:20px;">
            <img src="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExbDIzdGkxNmp2dnFwdTJ6M3ZyNXE1amh4ejhwMWg2MnRmbHpuYXV4diZlcD12MV9naWZzX3NlYXJjaCZjdD1n/uV6R7IyafWXtWkCkYW/giphy.gif"
                 width="180">
        </div>
        <p style="text-align:center; font-weight:600;">🤖 Alexandrinho analisando...</p>
        """,
        unsafe_allow_html=True
    )

    analysis_result = backend.gerar_diagnostico_para_laudo_existente(
        api_key, dados_laudo, resultados_analise
    )

    robot_placeholder.empty()

                        
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