import pyodbc
import mysql.connector
from datetime import datetime

# --- Conexão SQL Server ---
SQLSERVER_CONFIG = {
    "driver": "{ODBC Driver 17 for SQL Server}",
    "server": "localhost",
    "database": "DB_9F5EFD_unax",
    "uid": "etm",
    "pwd": "Bi@unax"
}

def get_sqlserver_connection():
    conn_str = (
        f"DRIVER={SQLSERVER_CONFIG['driver']};"
        f"SERVER={SQLSERVER_CONFIG['server']};"
        f"DATABASE={SQLSERVER_CONFIG['database']};"
        f"UID={SQLSERVER_CONFIG['uid']};"
        f"PWD={SQLSERVER_CONFIG['pwd']}"
    )
    return pyodbc.connect(conn_str)

# --- Conexão MySQL ---
MYSQL_CONFIG = {
    "host": "199.193.117.162",
    "database": "rxuffavj_laboratorio_db",
    "user": "rxuffavj",
    "password": "R4S68C0Id1ir29",
    "port": 3306
}

def get_mysql_connection():
    return mysql.connector.connect(**MYSQL_CONFIG)

# --- Função de sincronização ---
def sincronizar_elementos():
    # 1️⃣ Pega elementos do SQL Server
    sqlserver_conn = get_sqlserver_connection()
    cursor_sql = sqlserver_conn.cursor()
    cursor_sql.execute("""
        SELECT Id, Nome, UnidadeMedida
        FROM Elemento
    """)
    colunas = [col[0] for col in cursor_sql.description]  # nomes das colunas
    elementos = [dict(zip(colunas, row)) for row in cursor_sql.fetchall()]
    sqlserver_conn.close()

    if not elementos:
        print("Nenhum elemento encontrado no SQL Server.")
        return

    # 2️⃣ Insere/atualiza elementos na tabela MySQL 'elementos'
    mysql_conn = get_mysql_connection()
    cursor_mysql = mysql_conn.cursor()
    
    inseridos = 0
    atualizados = 0
    for elem in elementos:
        # Evita duplicados
        cursor_mysql.execute("SELECT 1 FROM elementos WHERE id_elemento = %s", (elem['Id'],))
        if cursor_mysql.fetchone():
            # Atualiza nome/unidade se já existir
            cursor_mysql.execute("""
                UPDATE elementos
                SET nome = %s, unidade_medida = %s, updated_at = %s
                WHERE id_elemento = %s
            """, (elem['Nome'], elem['UnidadeMedida'], datetime.now(), elem['Id']))
            atualizados += 1
            continue
        
        # Inserir novo registro
        cursor_mysql.execute("""
            INSERT INTO elementos
            (id_elemento, nome, unidade_medida, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            elem['Id'],
            elem['Nome'],
            elem['UnidadeMedida'],
            datetime.now(),
            datetime.now()
        ))
        inseridos += 1

    mysql_conn.commit()
    cursor_mysql.close()
    mysql_conn.close()
    print(f"Sincronização concluída. {inseridos} elementos inseridos, {atualizados} atualizados na tabela 'elementos'.")

# --- Executa ---
sincronizar_elementos()
