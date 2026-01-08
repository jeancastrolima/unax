import streamlit as st
import google.generativeai as genai

st.title("Listagem de Modelos Google Generative AI")

# ===============================
# CONFIGURAÇÃO DA API
# ===============================
API_KEY_GOOGLE = "AIzaSyBKOa0FF9LXL5Y8WKD7njMayBmrrOmIqck"  # Coloque sua chave entre aspas
genai.configure(api_key=API_KEY_GOOGLE)

# ===============================
# LISTAR MODELOS
# ===============================
try:
    # Converte o generator em lista
    modelos = list(genai.list_models())

    st.success(f"Foram encontrados {len(modelos)} modelos disponíveis:\n")
    
    for model in modelos:
        st.write(f"**Nome do modelo:** {model.name}")
        st.write(f"**Métodos suportados:** {model.supported_methods}")
        st.markdown("---")
except Exception as e:
    st.error(f"Erro ao listar modelos: {e}")
