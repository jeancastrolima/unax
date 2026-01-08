import os
import pandas as pd
import pymysql
import streamlit as st
from datetime import datetime, timedelta
import google.generativeai as genai
import json
import re
import plotly.graph_objects as go
from io import BytesIO
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import base64
import bcrypt

# ===================================================================
# --- CONFIGURAÇÕES E CONEXÃO COM BANCO DE DADOS ---
# ===================================================================
try:
    DB_CONFIG = {
        "host": st.secrets["database"]["host"],
        "database": st.secrets["database"]["database"],
        "user": st.secrets["database"]["user"],
        "password": st.secrets["database"]["password"],
        "port": 3306
    }
    API_KEY_GOOGLE = st.secrets["api_keys"]["google_ai"]
    genai.configure(api_key=API_KEY_GOOGLE)
except Exception as e:
    st.error(f"Erro de configuração nos secrets do Streamlit: {e}")
    st.stop()

def get_db_connection():
    """Estabelece conexão com o banco de dados."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as e:
        st.error(f"Erro fatal de conexão com a Base de Dados: {e}")
        return None

# ===================================================================
# --- FUNÇÕES DE AUTENTICAÇÃO E IA ---
# ===================================================================
def verificar_usuario(username, password):
    """Verifica credenciais e retorna dados do usuário, incluindo status de admin."""
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT nome, password_hash, is_admin FROM usuarios WHERE username = %s AND is_active = TRUE", (username,))
        user = cursor.fetchone()
        if user:
            stored_hash = user['password_hash'].encode('utf-8')
            if bcrypt.checkpw(password.encode('utf-8'), stored_hash):
                return {"nome": user['nome'], "is_admin": bool(user.get('is_admin', False))}
        return None
    finally:
        if conn: conn.close()

def ask_gemini_general(prompt: str, chat_history: list) -> str:
    """Envia um prompt para a IA e usa o histórico para manter o contexto."""
    try:
        model = genai.GenerativeModel("models/gemini-2.5-flash")


        chat_session = model.start_chat(history=chat_history)
        response = chat_session.send_message(prompt)
        return response.text
    except Exception as e:
        return f"Desculpe, tive um problema para me conectar com a IA: {e}"

def gerar_diagnostico_para_laudo_existente(api_key, dados_laudo, resultados_analise):
    """Gera o diagnóstico completo, com a lógica de fallback e tratamento de erro JSON."""
    model = genai.GenerativeModel("models/gemini-2.5-flash")



    cliente_nome = dados_laudo.get('ClienteNome', '').strip()
    
    df_conhecimento, erro_conhecimento = get_base_conhecimento_completa()
    base_conhecimento_diagnosticos = ""
    base_conhecimento_recomendacoes = ""
    if erro_conhecimento is None and df_conhecimento is not None:
        diagnosticos = df_conhecimento[df_conhecimento['is_recomendacao'] == 0]
        recomendacoes = df_conhecimento[df_conhecimento['is_recomendacao'] == 1]
        base_conhecimento_diagnosticos = "\n".join([f"- {row['nome_chave']}: {row['descricao_pt']}" for _, row in diagnosticos.iterrows()])
        base_conhecimento_recomendacoes = "\n".join([f"- {row['nome_chave']}: {row['descricao_pt']}" for _, row in recomendacoes.iterrows()])

    conn = get_db_connection()
    if not conn: return {"error": "Falha na conexão com a base de dados."}
    
    df_parametros = pd.DataFrame()
    try:
        query = "SELECT e.Nome AS elemento_nome, dp.limite_min_alerta, dp.limite_min_critico, dp.limite_max_alerta, dp.limite_max_critico FROM diagnosticos_parametros dp JOIN elementos e ON dp.id_elemento = e.id_elemento WHERE dp.cliente_nome = %s"
        df_parametros = pd.read_sql(query, conn, params=[cliente_nome])
    finally:
        if conn: conn.close()

    resultados_formatados_prompt, resultados_processados_tabela, nota_final = [], [], "Normal"
    
    for item in resultados_analise:
        elemento, unidade = item.get('item'), item.get('unidade', '')
        valor_real_str = str(item.get('resultado', '')).replace(',', '.')
        parametros_elemento = df_parametros[df_parametros['elemento_nome'] == elemento]
        limites_customizados = parametros_elemento.iloc[0].to_dict() if not parametros_elemento.empty else {}
        status = "Normal"
        limites_finais = {'min_a': None, 'min_c': None, 'max_a': None, 'max_c': None}

        try:
            valor_real_num = float(valor_real_str)
            if not limites_customizados:
                min_s = float(item.get('MinimoColeta')) if pd.notna(item.get('MinimoColeta')) else None
                max_s = float(item.get('MaximoColeta')) if pd.notna(item.get('MaximoColeta')) else None
                limites_finais.update({'min_a': min_s, 'max_a': max_s})
                if min_s is not None and max_s is not None and max_s > min_s:
                    if valor_real_num < min_s or valor_real_num > max_s: status = "Alerta"
                elif max_s is not None and (min_s is None or min_s == 0):
                    if valor_real_num >= max_s: status = "Alerta"
                elif min_s is not None and (max_s is None or max_s == 0):
                    if valor_real_num < min_s: status = "Alerta"
            else:
                min_a = float(limites_customizados.get('limite_min_alerta')) if pd.notna(limites_customizados.get('limite_min_alerta')) and limites_customizados.get('limite_min_alerta') != '' else None
                min_c = float(limites_customizados.get('limite_min_critico')) if pd.notna(limites_customizados.get('limite_min_critico')) and limites_customizados.get('limite_min_critico') != '' else None
                max_a = float(limites_customizados.get('limite_max_alerta')) if pd.notna(limites_customizados.get('limite_max_alerta')) and limites_customizados.get('limite_max_alerta') != '' else None
                max_c = float(limites_customizados.get('limite_max_critico')) if pd.notna(limites_customizados.get('limite_max_critico')) and limites_customizados.get('limite_max_critico') != '' else None
                limites_finais.update({'min_a': min_a, 'min_c': min_c, 'max_a': max_a, 'max_c': max_c})
                
                if (min_c is not None and valor_real_num < min_c) or (max_c is not None and valor_real_num > max_c):
                    status = "Crítico"
                elif (min_a is not None and valor_real_num < min_a) or (max_a is not None and valor_real_num >= max_a):
                    status = "Alerta"
        except (ValueError, TypeError):
             if isinstance(valor_real_str, str) and valor_real_str.lower().strip() in ['ausente', 'límpido', 'normal']: status = "Normal"
             elif isinstance(valor_real_str, str) and '/' in valor_real_str:
                if isinstance(limites_customizados.get('limite_max_alerta'), str) and '/' in limites_customizados.get('limite_max_alerta'):
                    status = avaliar_codigo_iso(valor_real_str, limites_customizados.get('limite_max_alerta'))
                else: status = "Indeterminado (Limite ISO não cadastrado)"
             else: status = "Indeterminado"

        if status == "Crítico": nota_final = "Crítico"
        elif status == "Alerta" and nota_final != "Crítico": nota_final = "Alerta"
        
        resultados_formatados_prompt.append(f"- {elemento}: {valor_real_str} (Status: {status})")
        
        resultados_processados_tabela.append({
            "Elemento": elemento, "Resultado": valor_real_str, "Unidade": unidade, 
            "Status Calculado": status, 
            "Mínimo Alerta": limites_finais['min_a'], "Mínimo Crítico": limites_finais['min_c'],
            "Máximo Alerta": limites_finais['max_a'], "Máximo Crítico": limites_finais['max_c']
        })
    
        # --- PROMPT ATUALIZADO COM INSTRUÇÃO DE PARÁGRAFOS ---
    prompt = f"""
    Você é um especialista sênior em manutenção preditiva e análise de fluidos da Unax Group...
    (Mantenha toda a sua Base de Conhecimento aqui)

    **TAREFA:**
    Com base em TODO o conhecimento acima e nos dados do laudo abaixo, gere um diagnóstico técnico e uma recomendação de manutenção.

    **INSTRUÇÕES DETALHADAS:**
    1.  **Diagnóstico e Recomendação:** Escreva textos claros e bem estruturados. **Use parágrafos (separados por uma linha em branco, `\\n\\n`) para melhorar a legibilidade.**
    2.  **Idioma:** Forneça o diagnóstico e a recomendação em Português (PT) e Inglês (EN).
    3.  **Formato de Saída:** Responda **EXCLUSIVAMENTE** como um objeto JSON.

    **DADOS DO LAUDO:**
    - Empresa: {cliente_nome}
    - Compartimento: {dados_laudo.get('CompartimentoNome', 'N/A')}
    - Nota/Grade Final (já calculada): **{nota_final}**
    - Resultados Detalhados: {"; ".join(resultados_formatados_prompt)}

    **JSON ESTRITAMENTE NESTE FORMATO:**
    {{
      "diagnostico_pt": "Seu diagnóstico técnico em português aqui, dividido em parágrafos.",
      "diagnostico_en": "Your technical analysis in English here, divided into paragraphs.",
      "recomendacao_pt": "Suas recomendações práticas em português aqui, divididas em parágrafos.",
      "recomendacao_en": "Your practical recommendations in English here, divided into paragraphs.",
      "nota_grade": "{nota_final}"
    }}
    """

    try:
        response = model.generate_content(prompt)
        if not response.text or not response.text.strip():
            return {"error": "A IA retornou uma resposta vazia. Isso pode ocorrer devido a filtros de segurança. Tente novamente."}
        
        cleaned_response = response.text.strip()
        match = re.search(r'\{.*\}', cleaned_response, re.DOTALL)
        
        if not match:
            return {"error": f"A IA retornou uma resposta sem um formato JSON detectável. Resposta: {cleaned_response}"}
        
        json_string = match.group(0)
        ai_json_response = json.loads(json_string)
        
        return {"ai_response": ai_json_response, "detailed_results": resultados_processados_tabela}
        
    except json.JSONDecodeError:
        return {"error": f"A IA retornou uma resposta que não pôde ser decodificada como JSON. Resposta: {cleaned_response}"}
    except Exception as e:
        return {"error": f"Erro ao gerar ou processar a resposta da IA: {e}"}

# ===================================================================
# --- FUNÇÃO AUXILIAR PARA CÓDIGOS ISO ---
# ===================================================================
def avaliar_codigo_iso(resultado_str, limite_max_str):
    """Compara um código de resultado ISO 4406 com um limite."""
    try:
        resultado_partes = [int(p) for p in resultado_str.split('/')]
        limite_partes = [int(p) for p in limite_max_str.split('/')]
        if len(resultado_partes) != len(limite_partes): return "Indeterminado"
        
        max_diferenca = max(rp - lp for rp, lp in zip(resultado_partes, limite_partes))
        
        if max_diferenca > 2: return "Crítico"
        elif max_diferenca > 0: return "Alerta"
        else: return "Normal"
    except (ValueError, TypeError):
        return "Indeterminado"

# ===================================================================
# --- FUNÇÕES DE CONSULTA DE DADOS ---
# ===================================================================
@st.cache_data(ttl=300)
def get_sincronizado_empresas():
    conn = get_db_connection()
    if not conn: return []
    try:
        df = pd.read_sql("SELECT DISTINCT ClienteNome FROM laudos_analiticos_sincronizados WHERE ClienteNome IS NOT NULL ORDER BY ClienteNome ASC;", conn)
        return df['ClienteNome'].tolist()
    finally:
        if conn: conn.close()

@st.cache_data(ttl=300)
def get_laudos_sincronizados_por_empresa(nome_empresa):
    conn = get_db_connection()
    if not conn: return []
    try:
        query = "SELECT DISTINCT ColetaId, NumeroLaudo, CompartimentoNome, DataColeta FROM laudos_analiticos_sincronizados WHERE ClienteNome = %s ORDER BY DataColeta DESC;"
        df = pd.read_sql(query, conn, params=[nome_empresa])
        return df.to_dict('records')
    finally:
        if conn: conn.close()

def get_detalhes_relatorio_sincronizado_por_coleta_id(coleta_id):
    conn = get_db_connection()
    if not conn: return None, []
    try:
        df = pd.read_sql("SELECT * FROM laudos_analiticos_sincronizados WHERE ColetaId = %s", conn, params=[coleta_id])
        if df.empty: return None, []
        dados_laudo = df.iloc[0].to_dict()
        resultados_analise = [{"item": r['ElementoNome'], "metodo": r.get('Metodo', 'N/A'), "unidade": r.get('UnidadeMedidaNome', ''), "resultado": r['ValorColeta'], "MinimoColeta": r.get('MinimoColeta'), "MaximoColeta": r.get('MaximoColeta')} for _, r in df.iterrows() if pd.notna(r['ElementoNome']) and pd.notna(r['ValorColeta'])]
        return dados_laudo, resultados_analise
    finally:
        if conn: conn.close()

def get_analises_ia_salvas():
    conn = get_db_connection()
    if not conn: return []
    try:
        df = pd.read_sql("SELECT id_analise_ia, coleta_id, numero_laudo, ClienteNome, data_geracao FROM laudos_ia_gerados ORDER BY data_geracao DESC;", conn)
        return df.to_dict('records')
    finally:
        if conn: conn.close()

def get_detalhes_completos_analise_ia(id_analise_ia):
    conn = get_db_connection()
    if not conn: return None, [], None
    try:
        ia_df = pd.read_sql("SELECT * FROM laudos_ia_gerados WHERE id_analise_ia = %s", conn, params=[id_analise_ia])
        if ia_df.empty: return None, [], None
        dados_ia = ia_df.iloc[0].to_dict()
        coleta_id = dados_ia['coleta_id']
        dados_laudo, _ = get_detalhes_relatorio_sincronizado_por_coleta_id(coleta_id)
        df_resultados_detalhados = pd.read_sql("SELECT * FROM laudos_ia_resultados WHERE id_analise_ia = %s", conn, params=[id_analise_ia])
        resultados_detalhados_salvos = df_resultados_detalhados.to_dict('records')
        return dados_laudo, resultados_detalhados_salvos, dados_ia
    except Exception as e:
        st.error(f"Erro ao buscar detalhes completos da análise: {e}")
        return None, [], None
    finally:
        if conn: conn.close()

# --- FUNÇÃO DE DATA CORRIGIDA PARA BUSCAR A ANTERIOR ---
def get_data_penultima_coleta(cliente_nome, unidade_nome, compartimento_nome, data_coleta_atual):
    """Busca a data da coleta imediatamente ANTERIOR à data atual para um componente específico."""
    conn = get_db_connection()
    if not conn: return None
    cursor = conn.cursor()
    try:
        query = """
            SELECT MAX(DataColeta) 
            FROM laudos_analiticos_sincronizados 
            WHERE ClienteNome = %s AND UnidadeNome = %s AND CompartimentoNome = %s AND DataColeta < %s
        """
        cursor.execute(query, (cliente_nome, unidade_nome, compartimento_nome, data_coleta_atual))
        result = cursor.fetchone()
        return result[0] if result and result[0] else None
    except Exception as e:
        print(f"Erro ao buscar data da penúltima coleta: {e}")
        return None
    finally:
        if conn: conn.close()


# ===================================================================
# --- FUNÇÕES PARA SALVAR E DELETAR DADOS ---
# ===================================================================
def salvar_diagnostico_completo_ia(dados_laudo, ai_response, detailed_results):
    conn = get_db_connection()
    if not conn: return {"success": False, "message": "Falha na conexão com o banco de dados."}
    cursor = conn.cursor()
    try:
        conn.start_transaction()
        query_principal = "INSERT INTO laudos_ia_gerados (coleta_id, numero_laudo, ClienteNome, diagnostico_pt, diagnostico_en, recomendacao_pt, recomendacao_en, nota_grade, data_geracao) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
        dados_principais = (dados_laudo.get('ColetaId'), dados_laudo.get('NumeroLaudo'), dados_laudo.get('ClienteNome'), ai_response.get('diagnostico_pt'), ai_response.get('diagnostico_en'), ai_response.get('recomendacao_pt'), ai_response.get('recomendacao_en'), ai_response.get('nota_grade'), datetime.now())
        cursor.execute(query_principal, dados_principais)
        id_analise_ia = cursor.lastrowid
        if detailed_results:
            query_detalhes = "INSERT INTO laudos_ia_resultados (id_analise_ia, elemento_nome, resultado_valor, unidade, status_calculado, limite_min_alerta_aplicado, limite_min_critico_aplicado, limite_max_alerta_aplicado, limite_max_critico_aplicado) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            dados_detalhes = []
            for item in detailed_results:
                min_a = item.get('Mínimo Alerta')
                min_c = item.get('Mínimo Crítico')
                max_a = item.get('Máximo Alerta')
                max_c = item.get('Máximo Crítico')
                dados_detalhes.append((id_analise_ia, item.get('Elemento'), item.get('Resultado'), item.get('Unidade'), item.get('Status Calculado'), min_a if pd.notna(min_a) else None, min_c if pd.notna(min_c) else None, max_a if pd.notna(max_a) else None, max_c if pd.notna(max_c) else None))
            cursor.executemany(query_detalhes, dados_detalhes)
        conn.commit()
        return {"success": True, "message": "Análise salva com sucesso!"}
    except mysql.connector.Error as e:
        conn.rollback()
        return {"success": False, "message": f"Erro de banco de dados ao salvar: {e}"}
    finally:
        if conn: conn.close()

def deletar_parametro(id_parametro):
    conn = get_db_connection()
    if not conn: return {"success": False, "message": "Falha na conexão."}
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM diagnosticos_parametros WHERE id_parametro = %s", (id_parametro,))
        conn.commit()
        st.cache_data.clear()
        return {"success": True, "message": "Parâmetro deletado!"}
    except mysql.connector.Error as e:
        conn.rollback()
        return {"success": False, "message": f"Erro ao deletar: {e}"}
    finally:
        if conn: conn.close()

# ===================================================================
# --- FUNÇÕES PARA GERENCIAR PARÂMETROS ---
# ===================================================================
@st.cache_data(ttl=300)
def get_elementos():
    conn = get_db_connection()
    if not conn: return []
    try:
        df = pd.read_sql("SELECT id_elemento, nome FROM elementos ORDER BY nome ASC;", conn)
        return df.to_dict('records')
    finally:
        if conn: conn.close()

@st.cache_data(ttl=30)
def get_parametros_por_cliente(cliente_nome):
    conn = get_db_connection()
    if not conn: return pd.DataFrame()
    try:
        query = "SELECT dp.id_parametro, e.nome AS elemento_nome, dp.limite_min_alerta, dp.limite_min_critico, dp.limite_max_alerta, dp.limite_max_critico FROM diagnosticos_parametros dp JOIN elementos e ON dp.id_elemento = e.id_elemento WHERE dp.cliente_nome = %s ORDER BY e.nome ASC;"
        df = pd.read_sql(query, conn, params=[cliente_nome])
        return df
    finally:
        if conn: conn.close()

def salvar_novos_parametros(cliente_nome, novos_parametros):
    conn = get_db_connection()
    if not conn: return {"success": False, "message": "Falha na conexão."}
    cursor = conn.cursor()
    try:
        query = "INSERT INTO diagnosticos_parametros (cliente_nome, id_elemento, limite_min_alerta, limite_min_critico, limite_max_alerta, limite_max_critico) VALUES (%s, %s, %s, %s, %s, %s)"
        dados_para_inserir = []
        for p in novos_parametros:
            def formatar_valor(valor):
                if valor is None or valor == '': return None
                valor_str = str(valor)
                if '/' in valor_str: return valor_str
                return valor_str.replace(',', '.')
            min_a = formatar_valor(p.get('limite_min_alerta'))
            min_c = formatar_valor(p.get('limite_min_critico'))
            max_a = formatar_valor(p.get('limite_max_alerta'))
            max_c = formatar_valor(p.get('limite_max_critico'))
            dados_para_inserir.append((cliente_nome, p['id_elemento'], min_a, min_c, max_a, max_c))
        cursor.executemany(query, dados_para_inserir)
        conn.commit()
        st.cache_data.clear()
        return {"success": True, "message": f"{len(dados_para_inserir)} parâmetro(s) salvo(s)!"}
    except mysql.connector.Error as e:
        conn.rollback()
        if e.errno == 1062: return {"success": False, "message": "Erro: Um ou mais parâmetros para esses elementos já existem."}
        return {"success": False, "message": f"Erro de banco de dados: {e}"}
    finally:
        if conn: conn.close()

# ===================================================================
# --- FUNÇÕES DA BASE DE CONHECIMENTO ---
# ===================================================================
def salvar_item_conhecimento(data):
    """Insere um único registro na tabela diagnosticos_padrao."""
    conn = get_db_connection()
    if not conn: return False, "Falha na conexão com o banco de dados."
    
    try:
        with conn.cursor() as cursor:
            sql = "INSERT INTO diagnosticos_padrao (nome_chave, descricao_pt, descricao_en, is_active, is_recomendacao) VALUES (%s, %s, %s, 1, %s)"
            val = (data['nome_chave'], data['descricao_pt'], data.get('descricao_en'), data['is_recomendacao'])
            cursor.execute(sql, val)
            conn.commit()
            return True, f"'{data['nome_chave']}' adicionado com sucesso!"
    except mysql.connector.Error as err:
        if err.errno == 1062: return False, f"Erro: O nome_chave '{data['nome_chave']}' já existe."
        return False, f"Erro no banco de dados: {err}"
    finally:
        if conn: conn.close()

def get_base_conhecimento_completa():
    """Busca todos os diagnósticos e recomendações da base de conhecimento."""
    conn = get_db_connection()
    if not conn: return None, "Falha na conexão com o banco de dados."
    
    try:
        query = "SELECT nome_chave, descricao_pt, descricao_en, is_recomendacao FROM diagnosticos_padrao WHERE is_active = 1 ORDER BY nome_chave ASC"
        df = pd.read_sql(query, conn)
        return df, None
    except mysql.connector.Error as err:
        return None, f"Erro ao listar a base de conhecimento: {err}"
    finally:
        if conn: conn.close()

# ===================================================================
# --- FUNÇÕES DE GRÁFICOS E E-MAIL ---
# ===================================================================
@st.cache_data(ttl=600)
def get_all_historical_data_sincronizado(cliente_nome, unidade_nome, compartimento_nome, start_date, end_date):
    """Busca o histórico filtrando por Cliente, Unidade e Compartimento."""
    conn = get_db_connection()
    if not conn: return pd.DataFrame()
    try:
        query = """
            SELECT DataColeta, ElementoNome, ValorColeta, MinimoColeta, MaximoColeta, UnidadeMedidaNome 
            FROM laudos_analiticos_sincronizados 
            WHERE ClienteNome = %s AND UnidadeNome = %s AND CompartimentoNome = %s AND DataColeta BETWEEN %s AND %s
            ORDER BY DataColeta ASC;
        """
        df = pd.read_sql(query, conn, params=[cliente_nome, unidade_nome, compartimento_nome, start_date, end_date])
        df['ValorColeta'] = pd.to_numeric(df['ValorColeta'], errors='coerce')
        df.dropna(subset=['DataColeta', 'ValorColeta', 'ElementoNome'], inplace=True)
        return df
    finally:
        if conn: conn.close()

# --- FUNÇÃO DE GRÁFICO ATUALIZADA ---
def generate_plotly_figure_sincronizado(full_history_df, item_analisado):
    """Gera o gráfico de tendência com tooltips detalhados e cores por status."""
    df_item = full_history_df[full_history_df['ElementoNome'] == item_analisado].copy()
    if df_item.empty:
        return None

    # Converte colunas de limite para numérico, tratando erros
    df_item['MinimoColeta'] = pd.to_numeric(df_item['MinimoColeta'], errors='coerce')
    df_item['MaximoColeta'] = pd.to_numeric(df_item['MaximoColeta'], errors='coerce')

    # 1. Define o Status e a Cor para cada ponto no gráfico
    def get_status_e_cor(row):
        status = "Normal"
        cor = "green"
        if pd.notna(row['MaximoColeta']) and row['ValorColeta'] >= row['MaximoColeta']:
            status = "Alerta"
            cor = "orange"
        if pd.notna(row['MinimoColeta']) and row['ValorColeta'] < row['MinimoColeta']:
            status = "Crítico"
            cor = "red"
        # Você pode adicionar uma lógica para Crítico no máximo se desejar, ex: > 1.1 * Maximo
        return status, cor

    df_item[['Status', 'Cor']] = df_item.apply(get_status_e_cor, axis=1, result_type='expand')
    
    unidade = df_item['UnidadeMedidaNome'].iloc[0] if not df_item['UnidadeMedidaNome'].empty else ''

    fig = go.Figure()

    # Adiciona a linha cinza pontilhada que conecta os pontos
    fig.add_trace(go.Scatter(
        x=df_item['DataColeta'], y=df_item['ValorColeta'],
        mode='lines',
        line=dict(color='grey', dash='dot'),
        hoverinfo='none' # Desativa o hover para esta linha
    ))

    # 2. Adiciona os marcadores coloridos com o tooltip (hover) personalizado
    fig.add_trace(go.Scatter(
        x=df_item['DataColeta'],
        y=df_item['ValorColeta'],
        mode='markers',
        marker=dict(
            color=df_item['Cor'],
            size=12,
            line=dict(width=1, color='DarkSlateGrey')
        ),
        # 3. Define o template do tooltip com todas as informações
        hovertemplate=(
            f"<b>{item_analisado}</b><br><br>"
            "<b>Data:</b> %{x|%d/%m/%Y}<br>"
            "<b>Valor:</b> %{y} " + f"{unidade}<br>"
            "<b>Status:</b> %{customdata[0]}<br>"
            "<b>Limite Mínimo:</b> %{customdata[1]}<br>"
            "<b>Limite Máximo:</b> %{customdata[2]}"
            "<extra></extra>" # Remove informações de trace extras
        ),
        # 4. Fornece os dados extras para o tooltip
        customdata=df_item[['Status', 'MinimoColeta', 'MaximoColeta']]
    ))

    # Adiciona as linhas de limite (se existirem no último ponto)
    last_row = df_item.iloc[-1]
    if pd.notna(last_row['MinimoColeta']) and last_row['MinimoColeta'] > 0:
        fig.add_hline(y=last_row['MinimoColeta'], line_dash="dash", line_color="orange", annotation_text=f"Mínimo: {last_row['MinimoColeta']}")
    if pd.notna(last_row['MaximoColeta']) and last_row['MaximoColeta'] > 0:
        fig.add_hline(y=last_row['MaximoColeta'], line_dash="dash", line_color="red", annotation_text=f"Máximo: {last_row['MaximoColeta']}")
    
    fig.update_layout(
        title_text=f'<b>Tendência para: {item_analisado}</b>',
        title_x=0.5,
        showlegend=False,
        xaxis_title="Data da Coleta",
        yaxis_title=f"Valor Medido ({unidade})"
    )
    return fig

def gerar_imagens_graficos(full_history_df, resultados_analise):
    imagens = {}
    for item in resultados_analise:
        item_analisado = item.get('item')
        if item_analisado:
            fig = generate_plotly_figure_sincronizado(full_history_df, item_analisado)
            if fig:
                img_bytes = fig.to_image(format="png", width=800, height=400, scale=2)
                imagens[item_analisado] = img_bytes
    return imagens

def gerar_interpretacao_tendencia_ia(cliente_nome, compartimento_nome, full_history_df):
    model = genai.GenerativeModel("models/gemini-2.5-flash")


    if full_history_df.empty or len(full_history_df['DataColeta'].unique()) < 2:
        return "Não há dados históricos suficientes para uma análise de tendência."
    dados_formatados_prompt = "\n".join([f"- {row['DataColeta'].strftime('%d/%m/%Y')}: {row['ElementoNome']} = {row['ValorColeta']}" for _, row in full_history_df.iterrows()])
    prompt = f"Você é um especialista em manutenção preditiva. Analise os dados históricos para o cliente {cliente_nome}, compartimento {compartimento_nome}. Identifique tendências, anomalias e forneça uma interpretação geral da saúde do equipamento. Dados:\n{dados_formatados_prompt}"
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Ocorreu um erro ao gerar a análise da IA: {e}"

def formatar_html_email(dados_laudo, resultados_analise, dados_ia, imagens_graficos=None):
    html = f"<h1>Relatório de Análise</h1><p>Cliente: {dados_laudo.get('ClienteNome')}</p>"
    # (Adicione aqui a formatação completa do seu e-mail)
    return html

def enviar_email_laudo(destinatario, dados_laudo, resultados_analise, dados_ia, imagens_graficos=None):
    try:
        creds = st.secrets["email_credentials"]
        sender_email, password = creds["sender_email"], creds["sender_password"]
        msg = MIMEMultipart('related')
        msg['Subject'] = f"Análise de Laudo - {dados_laudo.get('ClienteNome')}"
        msg['From'] = sender_email
        msg['To'] = destinatario
        html_body = formatar_html_email(dados_laudo, resultados_analise, dados_ia, imagens_graficos)
        msg.attach(MIMEText(html_body, 'html'))
        if imagens_graficos:
            for i, (nome_item, img_bytes) in enumerate(imagens_graficos.items()):
                img = MIMEImage(img_bytes)
                img.add_header('Content-ID', f'<image{i}>')
                msg.attach(img)
        with smtplib.SMTP(creds["smtp_server"], creds["smtp_port"]) as server:
            server.starttls()
            server.login(sender_email, password)
            server.sendmail(sender_email, destinatario, msg.as_string())
        return {"success": True, "message": f"E-mail enviado para {destinatario}."}
    except Exception as e:
        return {"success": False, "message": f"Falha ao enviar e-mail: {e}"}

def get_system_info():
    """Busca as informações do sistema da tabela sistema_info."""
    conn = get_db_connection()
    if not conn: return {}
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT system_name, description, developer, department, version FROM sistema_info LIMIT 1")
        info = cursor.fetchone()
        return info if info else {}
    except mysql.connector.Error as e:
        print(f"Aviso: Não foi possível buscar informações do sistema. Erro: {e}")
        return {}
    finally:
        if conn: conn.close()
