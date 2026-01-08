import mariadb
import bcrypt
import getpass

# --- ATENÇÃO: COPIE A SUA CONFIGURAÇÃO DE CONEXÃO DE backend.py PARA CÁ ---
# Temporariamente, vamos precisar da configuração aqui.
# Em um projeto real, isso ficaria em um arquivo de configuração central.
class DBManager:
    def __init__(self, secrets):
        self.secrets = secrets

    def get_db_connection(self):
        try:
            conn = mariadb.connect(
                user=self.secrets['database']['user'],
                password=self.secrets['database']['password'],
                host=self.secrets['database']['host'],
                port=3306,
                database=self.secrets['database']['database']
            )
            return conn
        except mariadb.Error as e:
            print(f"Erro ao conectar ao MariaDB: {e}")
            return None

# Simula a estrutura de segredos do Streamlit para uso local
# PREENCHA COM SUAS CREDENCIAIS REAIS DO BANCO DE DADOS
local_secrets = {
    "database": {
        "user": "rxuffavj",
        "password": "R4S68C0Id1ir29",
        "host": "199.193.117.162",
        "database": "rxuffavj_laboratorio_db"
    }
}

db_manager = DBManager(local_secrets)

def add_user():
    """Script para adicionar um novo usuário ao banco de dados."""
    print("--- Cadastro de Novo Usuário ---")
    nome = input("Nome completo do usuário: ")
    username = input("Nome de usuário (para login): ")
    password = getpass.getpass("Digite a senha: ")
    password_confirm = getpass.getpass("Confirme a senha: ")

    if password != password_confirm:
        print("\nAs senhas não coincidem. Operação cancelada.")
        return

    # Criptografar a senha
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    conn = db_manager.get_db_connection()
    if not conn:
        return

    cursor = conn.cursor()
    try:
        query = "INSERT INTO usuarios (nome, username, password_hash) VALUES (?, ?, ?)"
        cursor.execute(query, (nome, username, hashed_password.decode('utf-8')))
        conn.commit()
        print(f"\nUsuário '{username}' criado com sucesso!")
    except mariadb.Error as e:
        print(f"\nErro ao inserir usuário: {e}")
        print("Verifique se o nome de usuário já existe.")
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    add_user()