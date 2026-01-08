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
    page_title="AlexExpert | Unax Lab",
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
    model = genai.GenerativeModel("models/gemini-2.0-flash") # Atualizado para versão estável atual
    image_part = {'mime_type': image_file.type, 'data': image_file.getvalue()}
    
    prompt = [
        """
        Você é um assistente especializado em análise de fluidos. Extraia descrições de diagnósticos/recomendações.
        Formato de Saída (JSON Array):
        [{"nome_chave": "snake_case", "descricao_pt": "...", "descricao_en": "...", "is_recomendacao": 0/1}]
        """,
        image_part
    ]
    
    try:
        response = model.generate_content(prompt)
        json_text_match = re.search(r'\[.*\]', response.text, re.DOTALL)
        return json.loads(json_text_match.group(0)) if json_text_match else []
    except Exception as e:
        st.error(f"Erro na análise da IA: {e}")
        return None

def formatar_status_com_icone(status):
    icons = {"Crítico": "🔴", "Alerta": "🟡", "Normal": "🟢"}
    return f"{icons.get(status, '⚪️')} {status}"

# ===================================================================
# --- SISTEMA DE AUTENTICAÇÃO ---
# ===================================================================
try:
    cookies = EncryptedCookieManager(password=st.secrets["cookies"]["password"])
    if not cookies.ready(): 
        st.stop()
except Exception:
    st.error("Erro no Gerenciador de Cookies. Verifique secrets."); st.stop()

if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = cookies.get('authenticated') == 'True'

# --- TELA DE LOGIN ---
if not st.session_state['authenticated']:
    _, col2, _ = st.columns([1, 1.2, 1])
    with col2:
        st.image("https://via.placeholder.com/150x50?text=Unax+Lab", width=150) # Substituir pela sua logo
        with st.container(border=True):
            st.title("🔒 Login")
            st.markdown("Acesse a plataforma **AlexExpert**")
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            if st.button("Entrar", type="primary", use_container_width=True):
                user_data = backend.verificar_usuario(username, password)
                if user_data:
                    st.session_state.update({
                        'authenticated': True,
                        'user_full_name': user_data['nome'],
                        'is_admin': user_data['is_admin']
                    })
                    cookies.update({'authenticated': 'True', 'user_full_name': user_data['nome']})
                    cookies.save()
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")
    st.stop()

# ===================================================================
# --- INTERFACE PRINCIPAL ---
# ===================================================================
api_key = st.secrets["api_keys"]["google_ai"]

# --- SIDEBAR PROFISSIONAL ---
with st.sidebar:
    st.image("https://via.placeholder.com/150x50?text=Unax+Lab", width=120)
    st.divider()
    st.markdown(f"👤 **{st.session_state.get('user_full_name')}**")
    if st.session_state.get('is_admin'):
        st.caption("🛡️ Administrador")
    
    if st.button("Sair", icon="🚀"):
        cookies['authenticated'] = 'False'
        cookies.save()
        st.session_state.clear()
        st.rerun()

    st.markdown('<div class="sidebar-footer">AlexExpert v2.0<br>Unax Lab - Inteligência em Fluidos</div>', unsafe_allow_html=True)

# --- TABS COM ÍCONES ---
tab_analisar, tab_consultar, tab_gerenciar, tab_chat = st.tabs([
    "🔍 Analisar Laudos", "📂 Consultar Histórico", "⚙️ Parâmetros", "💬 Chat IA"
])

# --- CONTEÚDO: ANALISAR ---
with tab_analisar:
    st.subheader("Análise de Laudos Sincronizados")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            empresas_sinc = backend.get_sincronizado_empresas()
            empresa = st.selectbox("Selecione a Empresa", ["Selecione..."] + empresas_sinc)
        with c2:
            laudos = backend.get_laudos_sincronizados_por_empresa(empresa) if empresa != "Selecione..." else []
            laudo_selecionado = st.selectbox("Selecione o Laudo", [None] + laudos, 
                                            format_func=lambda x: f"ID:{x['ColetaId']} | {x['NumeroLaudo']}" if x else "Aguardando...")

    if laudo_selecionado:
        coleta_id = laudo_selecionado['ColetaId']
        dados_laudo, resultados_analise = backend.get_detalhes_relatorio_sincronizado_por_coleta_id(coleta_id)
        
        # --- CARDS DE MÉTRICAS ---
        st.markdown("#### 📋 Dados do Equipamento")
        cols = st.columns(4)
        metadados = [
            ("Laudo", dados_laudo.get('NumeroLaudo')),
            ("Unidade", dados_laudo.get('UnidadeNome')),
            ("Compartimento", dados_laudo.get('CompartimentoNome')),
            ("Fluido", dados_laudo.get('FluidoNome'))
        ]
        for i, (label, value) in enumerate(metadados):
            with cols[i]:
                with st.container(border=True):
                    st.caption(label)
                    st.markdown(f"**{value}**")

        # --- TABELA DE RESULTADOS ---
        with st.container(border=True):
            st.markdown("#### 🧪 Resultados Laboratoriais")
            df_display = pd.DataFrame(resultados_analise)[['item', 'resultado', 'unidade']]
            st.dataframe(df_display, use_container_width=True, hide_index=True)
            
            if st.button("✨ Gerar Diagnóstico Inteligente", type="primary", use_container_width=True):
                with st.spinner("O Alexandrinho está analisando os dados..."):
                    analysis_result = backend.gerar_diagnostico_para_laudo_existente(api_key, dados_laudo, resultados_analise)
                    
                    if "error" not in analysis_result:
                        ai_resp = analysis_result['ai_response']
                        st.toast("Análise concluída!", icon="✅")
                        
                        # Exibição do Resultado da IA
                        st.divider()
                        nota = ai_resp.get('nota_grade', 'Normal')
                        st.markdown(f"### Status Final: {formatar_status_com_icone(nota)}")
                        
                        col_pt, col_en = st.columns(2)
                        with col_pt:
                            st.success(f"**Diagnóstico:**\n{ai_resp.get('diagnostico_pt')}")
                        with col_en:
                            st.info(f"**Diagnosis:**\n{ai_resp.get('diagnostico_en')}")

# --- CONTEÚDO: CHAT ---
with tab_chat:
    st.subheader("💬 Chat com Alexandrinho")
    # Estilo de chat Bootstrap
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Olá! Sou o Alexandrinho. Como posso ajudar com suas análises hoje?"}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Dúvida sobre um elemento químico ou limite?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Processando..."):
                response = backend.ask_gemini_general(prompt, st.session_state.messages)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

# --- PRÓXIMOS PASSOS ---
# 1. Adicionar lógica de Gráficos Plotly dentro de containers específicos.
# 2. Implementar o envio de e-mail como um Modal ou Popover.