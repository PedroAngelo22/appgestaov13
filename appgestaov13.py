import os
import shutil
import base64
import hashlib
from datetime import datetime
import streamlit as st
import sqlite3
import re
import fitz

# Banco de dados SQLite
conn = sqlite3.connect('document_manager.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    projects TEXT,
    permissions TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS logs (
    timestamp TEXT,
    user TEXT,
    action TEXT,
    file TEXT
)''')
c.execute('''CREATE TABLE IF NOT EXISTS clients (
    name TEXT PRIMARY KEY
)''')
c.execute('''CREATE TABLE IF NOT EXISTS projects (
    name TEXT PRIMARY KEY,
    client TEXT
)''')
# Tabela de comentários
c.execute('''
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT,
    username TEXT,
    timestamp TEXT,
    comment TEXT
)
''')
conn.commit()
BASE_DIR = "uploads"
os.makedirs(BASE_DIR, exist_ok=True)

if "disciplinas" not in st.session_state:
    st.session_state.disciplinas = ["GES", "PRO", "MEC", "MET", "CIV", "ELE", "AEI"]
if "fases" not in st.session_state:
    st.session_state.fases = ["FEL1", "FEL2", "FEL3", "Executivo"]
if "projetos_registrados" not in st.session_state:
    st.session_state.projetos_registrados = []
if "clientes_registrados" not in st.session_state:
    st.session_state.clientes_registrados = []

def get_project_path(project, discipline, phase):
    path = os.path.join(BASE_DIR, project, discipline, phase)
    os.makedirs(path, exist_ok=True)
    return path

def log_action(user, action, file, note=None):
    log_entry = f"{file} ({note})" if note else file
    c.execute("INSERT INTO logs (timestamp, user, action, file) VALUES (?, ?, ?, ?)",
              (datetime.now().isoformat(), user, action, log_entry))
    conn.commit()

def file_icon(file_name):
    if file_name.lower().endswith(".pdf"):
        return "📄"
    elif file_name.lower().endswith((".jpg", ".jpeg", ".png")):
        return "🖼️"
    else:
        return "📁"

def hash_key(text):
    return hashlib.md5(text.encode()).hexdigest()

def extrair_info_arquivo(nome_arquivo):
    padrao = r"(.+?)r(\d+)v(\d+).*?\.\w+$"
    match = re.match(padrao, nome_arquivo)
    if match:
        nome_base = match.group(1).rstrip(" _-")
        revisao = f"r{match.group(2)}"
        versao = f"v{match.group(3)}"
        return nome_base, revisao, versao
    return None, None, None

def salvar_comentario(file_path, username, comment):
    timestamp = datetime.now().isoformat()
    c.execute('''INSERT INTO comments (file_path, username, timestamp, comment)
                 VALUES (?, ?, ?, ?)''', (file_path, username, timestamp, comment))
    conn.commit()
    log_action(username, "comentário", file_path)

def obter_comentarios(file_path):
    return c.execute('''SELECT username, timestamp, comment
                        FROM comments
                        WHERE file_path=?
                        ORDER BY timestamp DESC''', (file_path,)).fetchall()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "registration_mode" not in st.session_state:
    st.session_state.registration_mode = False
if "registration_unlocked" not in st.session_state:
    st.session_state.registration_unlocked = False
if "admin_mode" not in st.session_state:
    st.session_state.admin_mode = False
if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

st.title("📁 Gerenciador de Documentos Inteligente")
# LOGIN
if not st.session_state.authenticated and not st.session_state.registration_mode and not st.session_state.admin_mode:
    st.subheader("Login")
    login_user = st.text_input("Usuário")
    login_pass = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        result = c.execute("SELECT * FROM users WHERE username=? AND password=?", (login_user, login_pass)).fetchone()
        if result:
            st.session_state.authenticated = True
            st.session_state.username = login_user
            st.rerun()
        else:
            st.error("Credenciais inválidas.")

    if st.button("Registrar novo usuário"):
        st.session_state.registration_mode = True
        st.rerun()

    if st.button("Painel Administrativo"):
        st.session_state.admin_mode = True
        st.rerun()

# REGISTRO
elif st.session_state.registration_mode and not st.session_state.authenticated:
    st.subheader("Registro de Novo Usuário")
    master_pass = st.text_input("Senha Mestra", type="password")
    if st.button("Liberar Acesso"):
        if master_pass == "#Heisenberg7":
            st.session_state.registration_unlocked = True
            st.success("Acesso liberado. Preencha os dados do novo usuário.")
        else:
            st.error("Senha Mestra incorreta.")

    if st.session_state.registration_unlocked:
        new_user = st.text_input("Novo Usuário")
        new_pass = st.text_input("Nova Senha", type="password")
        if st.button("Criar usuário"):
            if c.execute("SELECT * FROM users WHERE username=?", (new_user,)).fetchone():
                st.error("Usuário já existe.")
            else:
                c.execute("INSERT INTO users (username, password, projects, permissions) VALUES (?, ?, ?, ?)",
                          (new_user, new_pass, '', 'upload,view'))
                conn.commit()
                st.success("Usuário registrado com permissões padrão [upload, view].")
                st.session_state.registration_mode = False
                st.session_state.registration_unlocked = False
                st.rerun()

    if st.button("Voltar ao Login"):
        st.session_state.registration_mode = False
        st.session_state.registration_unlocked = False
        st.rerun()

# AUTENTICAÇÃO ADMINISTRADOR
elif st.session_state.admin_mode and not st.session_state.admin_authenticated:
    st.subheader("Autenticação do Administrador")
    master = st.text_input("Senha Mestra", type="password")
    if st.button("Liberar Painel Admin"):
        if master == "#Heisenberg7":
            st.session_state.admin_authenticated = True
            st.success("Acesso concedido.")
            st.rerun()
        else:
            st.error("Senha incorreta.")

# PAINEL ADMINISTRATIVO
elif st.session_state.admin_mode and st.session_state.admin_authenticated:
    st.subheader("Painel Administrativo")

    st.markdown("### ➕ Cadastrar Cliente")
    novo_cliente = st.text_input("Novo Cliente")
    if st.button("Adicionar Cliente") and novo_cliente:
        if not c.execute("SELECT * FROM clients WHERE name=?", (novo_cliente,)).fetchone():
            c.execute("INSERT INTO clients (name) VALUES (?)", (novo_cliente,))
            conn.commit()
            st.success(f"Cliente '{novo_cliente}' adicionado.")
        else:
            st.warning("Cliente já existe.")

    st.markdown("### ➕ Cadastrar Projeto")
    novo_proj = st.text_input("Novo Projeto")
    clientes = [row[0] for row in c.execute("SELECT name FROM clients").fetchall()]
    cliente_selecionado = st.selectbox("Cliente do Projeto", clientes) if clientes else None

    if st.button("Adicionar Projeto") and novo_proj and cliente_selecionado:
        if not c.execute("SELECT * FROM projects WHERE name=?", (novo_proj,)).fetchone():
            c.execute("INSERT INTO projects (name, client) VALUES (?, ?)", (novo_proj, cliente_selecionado))
            conn.commit()
            st.session_state.projetos_registrados.append(novo_proj)
            st.success(f"Projeto '{novo_proj}' vinculado ao cliente '{cliente_selecionado}' adicionado.")
        else:
            st.warning("Projeto já existe.")

    nova_disc = st.text_input("Nova Disciplina")
    if st.button("Adicionar Disciplina") and nova_disc:
        if nova_disc not in st.session_state.disciplinas:
            st.session_state.disciplinas.append(nova_disc)
            st.success(f"Disciplina '{nova_disc}' adicionada.")
        else:
            st.warning("Disciplina já existe.")

    nova_fase = st.text_input("Nova Fase")
    if st.button("Adicionar Fase") and nova_fase:
        if nova_fase not in st.session_state.fases:
            st.session_state.fases.append(nova_fase)
            st.success(f"Fase '{nova_fase}' adicionada.")
        else:
            st.warning("Fase já existe.")

    filtro = st.text_input("🔍 Filtrar usuários por nome")
    usuarios = c.execute("SELECT username, projects, permissions FROM users").fetchall()
    usuarios = [u for u in usuarios if filtro.lower() in u[0].lower()] if filtro else usuarios

    for user, projetos_atuais, permissoes_atuais in usuarios:
        st.markdown(f"#### 👤 {user}")
        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button(f"Excluir {user}", key=hash_key(f"del_{user}")):
                c.execute("DELETE FROM users WHERE username=?", (user,))
                conn.commit()
                st.success(f"Usuário {user} removido.")
                st.rerun()
        with col2:
            projetos = st.multiselect(f"Projetos ({user})",
                                      options=[p[0] for p in c.execute("SELECT name FROM projects").fetchall()],
                                      default=projetos_atuais.split(',') if projetos_atuais else [],
                                      key=hash_key(f"proj_{user}"))
            permissoes = st.multiselect(f"Permissões ({user})",
                                        options=["upload", "download", "view"],
                                        default=permissoes_atuais.split(',') if permissoes_atuais else [],
                                        key=hash_key(f"perm_{user}"))
            nova_senha = st.text_input(f"Nova senha ({user})", key=hash_key(f"senha_{user}"))
            if st.button(f"Atualizar permissões/projetos {user}", key=hash_key(f"update_perm_{user}")):
                if nova_senha:
                    c.execute("UPDATE users SET password=?, projects=?, permissions=? WHERE username=?",
                              (nova_senha, ','.join(projetos), ','.join(permissoes), user))
                else:
                    c.execute("UPDATE users SET projects=?, permissions=? WHERE username=?",
                              (','.join(projetos), ','.join(permissoes), user))
                conn.commit()
                st.success(f"Permissões/projetos atualizados para {user}.")
                st.rerun()

    if st.button("Sair do Painel Admin"):
        st.session_state.admin_authenticated = False
        st.session_state.admin_mode = False
        st.rerun()

# USUÁRIO AUTENTICADO
elif st.session_state.authenticated:
    username = st.session_state.username
    user_data = c.execute("SELECT projects, permissions FROM users WHERE username=?", (username,)).fetchone()
    user_projects = user_data[0].split(',') if user_data and user_data[0] else []
    user_permissions = user_data[1].split(',') if user_data and user_data[1] else []

    st.sidebar.markdown(f"🔐 Logado como: **{username}**")
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.rerun()

    # UPLOAD
    if "upload" in user_permissions:
        st.markdown("### ⬆️ Upload de Arquivos")
        with st.form("upload_form"):
            if not user_projects:
                st.warning("Você ainda não tem projetos atribuídos.")
            else:
                project = st.selectbox("Projeto", user_projects)
                discipline = st.selectbox("Disciplina", st.session_state.disciplinas)
                phase = st.selectbox("Fase", st.session_state.fases)
                uploaded_file = st.file_uploader("Escolha o arquivo")
                confirmar_mesma_revisao = st.checkbox("Confirmo que estou mantendo a mesma revisão e subindo nova versão")

                if uploaded_file:
                    nome_base, revisao, versao = extrair_info_arquivo(uploaded_file.name)
                    if nome_base and revisao and versao:
                        st.info(f"🧠 Detecção automática: `{uploaded_file.name}` → Revisão: **{revisao}**, Versão: **{versao}**")
                    else:
                        st.error("❌ Nome do arquivo deve conter rXvY (ex: r1v2).")

                submitted = st.form_submit_button("Enviar")
                if submitted and uploaded_file:
                    filename = uploaded_file.name
                    path = get_project_path(project, discipline, phase)
                    file_path = os.path.join(path, filename)

                    nome_base, revisao, versao = extrair_info_arquivo(filename)
                    if not nome_base:
                        st.error("Nome do arquivo deve conter rXvY.")
                        st.stop()
                    else:
                        arquivos_existentes = os.listdir(path)
                        nomes_existentes = [f for f in arquivos_existentes if f.startswith(nome_base)]

                        revisoes_anteriores = []
                        for f in nomes_existentes:
                            base_ant, rev_ant, ver_ant = extrair_info_arquivo(f)
                            if base_ant == nome_base:
                                revisoes_anteriores.append((f, rev_ant, ver_ant))

                        # Verificar também revisões na pasta Revisoes/{nome_base}
                        pasta_revisoes = os.path.join(path, "Revisoes", nome_base)
                        if os.path.isdir(pasta_revisoes):
                            for f in os.listdir(pasta_revisoes):
                                base_ant, rev_ant, ver_ant = extrair_info_arquivo(f)
                                if base_ant == nome_base:
                                    revisoes_anteriores.append((f, rev_ant, ver_ant))

                        revisoes_existentes = [int(r[1][1:]) for r in revisoes_anteriores if r[1] and r[1].startswith('r')]
                        rev_max = max(revisoes_existentes) if revisoes_existentes else -1
                        rev_atual = int(revisao[1:])

                        if rev_atual < rev_max:
                            st.error(f"❌ Revisão {revisao} menor que revisão máxima existente (r{rev_max}). Upload não permitido.")
                            st.stop()

                        if filename in arquivos_existentes:
                            st.error("Arquivo com este nome completo já existe.")
                            st.stop()
                        else:
                            existe_revisao_anterior = any(r[1] != revisao for r in revisoes_anteriores)
                            mesma_revisao_outras_versoes = any(r[1] == revisao and r[2] != versao for r in revisoes_anteriores)

                            if existe_revisao_anterior:
                                pasta_revisao = os.path.join(path, "Revisoes", nome_base)
                                os.makedirs(pasta_revisao, exist_ok=True)
                                for f, _, _ in revisoes_anteriores:
                                    origem = os.path.join(path, f)
                                    destino = os.path.join(pasta_revisao, f)
                                    if os.path.exists(origem):
                                        shutil.move(origem, destino)
                                st.info(f"🗂️ Arquivos da revisão anterior movidos para `{pasta_revisao}`")

                            elif mesma_revisao_outras_versoes and not confirmar_mesma_revisao:
                                st.warning("⚠️ Mesma revisão detectada com nova versão. Confirme a caixa para prosseguir.")
                                st.stop()

                            with open(file_path, "wb") as f:
                                f.write(uploaded_file.read())

                            st.success(f"✅ Arquivo `{filename}` salvo com sucesso.")
                            log_action(username, "upload", file_path)
                            
    # NAVEGAÇÃO NA SIDEBAR: "Meus Projetos" e "Meus Clientes"
    st.sidebar.markdown("### 🔎 Navegação Rápida")

    if st.sidebar.button("📁 Meus Projetos"):
        for proj in sorted(user_projects):
            proj_path = os.path.join(BASE_DIR, proj)
            if not os.path.isdir(proj_path):
                continue

            with st.expander(f"📁 Projeto: {proj}", expanded=False):
                for disc in sorted(os.listdir(proj_path)):
                    disc_path = os.path.join(proj_path, disc)
                    if not os.path.isdir(disc_path):
                        continue

                    with st.expander(f"📂 Disciplina: {disc}", expanded=False):
                        for fase in sorted(os.listdir(disc_path)):
                            fase_path = os.path.join(disc_path, fase)
                            if not os.path.isdir(fase_path):
                                continue

                            with st.expander(f"📄 Fase: {fase}", expanded=False):
                                for file in sorted(os.listdir(fase_path)):
                                    full_path = os.path.join(fase_path, file)
                                    if os.path.isdir(full_path):
                                        continue

                                    st.markdown(f"- `{file}`")
                                    with open(full_path, "rb") as f:
                                        if file.lower().endswith(".pdf"):
                                            b64 = base64.b64encode(f.read()).decode("utf-8")
                                            href = f'<a href="data:application/pdf;base64,{b64}" target="_blank">👁️ Visualizar PDF</a>'
                                            st.markdown(href, unsafe_allow_html=True)
                                        f.seek(0)
                                        if "download" in user_permissions:
                                            st.download_button("📥 Baixar", f, file_name=file, key=hash_key(f"dl_{full_path}"))

                                    # Seção de Comentários
                                    with st.expander("💬 Comentários", expanded=False):
                                        comentario_key = hash_key("coment_" + full_path)
                                        botao_key = hash_key("btn_com_" + full_path)
                                    
                                        st.markdown("##### Novo Comentário")
                                        novo_coment = st.text_area("Digite seu comentário", key=comentario_key)
                                    
                                        if st.button("Enviar comentário", key=botao_key):
                                            if novo_coment.strip():
                                                salvar_comentario(full_path, username, novo_coment.strip())
                                                st.success("Comentário salvo com sucesso.")
                                                st.experimental_rerun()
                                            else:
                                                st.warning("Comentário vazio não será salvo.")
                                    
                                        st.markdown("##### Comentários Anteriores")
                                        comentarios = obter_comentarios(full_path)
                                        if comentarios:
                                            for user, time, text in comentarios:
                                                st.markdown(f"**{user}** ({time[:19]}):")
                                                st.markdown(f"> {text}")
                                                st.markdown("---")
                                        else:
                                            st.info("Nenhum comentário ainda.")
        
    if st.sidebar.button("🏢 Meus Clientes"):
        meus_clientes = set()
        for proj in user_projects:
            res = c.execute("SELECT client FROM projects WHERE name=?", (proj,)).fetchone()
            if res:
                meus_clientes.add(res[0])

        for cliente in sorted(meus_clientes):
            with st.expander(f"🏢 Cliente: {cliente}", expanded=False):
                projetos_cliente = [p[0] for p in c.execute("SELECT name FROM projects WHERE client=?", (cliente,)).fetchall()]
                projetos_cliente = [p for p in projetos_cliente if p in user_projects]

                for proj in sorted(projetos_cliente):
                    proj_path = os.path.join(BASE_DIR, proj)
                    if not os.path.isdir(proj_path):
                        continue

                    with st.expander(f"📁 Projeto: {proj}", expanded=False):
                        for disc in sorted(os.listdir(proj_path)):
                            disc_path = os.path.join(proj_path, disc)
                            if not os.path.isdir(disc_path):
                                continue

                            with st.expander(f"📂 Disciplina: {disc}", expanded=False):
                                for fase in sorted(os.listdir(disc_path)):
                                    fase_path = os.path.join(disc_path, fase)
                                    if not os.path.isdir(fase_path):
                                        continue

                                    with st.expander(f"📄 Fase: {fase}", expanded=False):
                                        for file in sorted(os.listdir(fase_path)):
                                            full_path = os.path.join(fase_path, file)
                                            if os.path.isdir(full_path):
                                                continue

                                    st.markdown(f"- `{file}`")
                                    with open(full_path, "rb") as f:
                                        if file.lower().endswith(".pdf"):
                                            b64 = base64.b64encode(f.read()).decode("utf-8")
                                            href = f'<a href="data:application/pdf;base64,{b64}" target="_blank">👁️ Visualizar PDF</a>'
                                            st.markdown(href, unsafe_allow_html=True)
                                        f.seek(0)
                                        if "download" in user_permissions:
                                            st.download_button("📥 Baixar", f, file_name=file, key=hash_key(f"dl_{full_path}"))

                                            # Seção de Comentários
                                            with st.expander("💬 Comentários", expanded=False):
                                                comentario_key = hash_key("coment_" + full_path)
                                                botao_key = hash_key("btn_com_" + full_path)
                                            
                                                st.markdown("##### Novo Comentário")
                                                novo_coment = st.text_area("Digite seu comentário", key=comentario_key)
                                            
                                                if st.button("Enviar comentário", key=botao_key):
                                                    if novo_coment.strip():
                                                        salvar_comentario(full_path, username, novo_coment.strip())
                                                        st.success("Comentário salvo com sucesso.")
                                                        st.experimental_rerun()
                                                    else:
                                                        st.warning("Comentário vazio não será salvo.")
                                            
                                                st.markdown("##### Comentários Anteriores")
                                                comentarios = obter_comentarios(full_path)
                                                if comentarios:
                                                    for user, time, text in comentarios:
                                                        st.markdown(f"**{user}** ({time[:19]}):")
                                                        st.markdown(f"> {text}")
                                                        st.markdown("---")
                                                else:
                                                    st.info("Nenhum comentário ainda.")
        
    # PESQUISA POR PALAVRA-CHAVE (NOME + CONTEÚDO PDF)
    if "download" in user_permissions or "view" in user_permissions:
        st.markdown("### 🔍 Pesquisa de Documentos")
        keyword = st.text_input("Buscar por palavra-chave")
        if keyword:
            matched = []
            for root, dirs, files in os.walk(BASE_DIR):
                for file in files:
                    full_path = os.path.join(root, file)
                    if not os.path.isfile(full_path):
                        continue

                    rel_path_parts = os.path.relpath(full_path, BASE_DIR).split(os.sep)
                    if rel_path_parts[0] not in user_projects:
                        continue

                    match_found = False
                    if keyword.lower() in file.lower():
                        match_found = True
                    elif file.lower().endswith(".pdf"):
                        try:
                            doc = fitz.open(full_path)
                            text = ""
                            for page in doc:
                                text += page.get_text()
                            doc.close()
                            if keyword.lower() in text.lower():
                                match_found = True
                        except Exception as e:
                            st.warning(f"Erro ao ler PDF `{file}`: {str(e)}")

                    if match_found:
                        matched.append(full_path)

            if matched:
                for file in matched:
                    st.write(f"📄 {os.path.relpath(file, BASE_DIR)}")
                    with open(file, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                        if file.lower().endswith(".pdf"):
                            href = f'<a href="data:application/pdf;base64,{b64}" target="_blank">👁️ Visualizar PDF</a>'
                            if st.button("👁️ Visualizar PDF", key=hash_key("btnk_" + file)):
                                st.markdown(href, unsafe_allow_html=True)
                            f.seek(0)
                            if "download" in user_permissions:
                                st.download_button("📥 Baixar PDF", f, file_name=os.path.basename(file), mime="application/pdf", key=hash_key("dlk_" + file))
                        elif file.lower().endswith(('.jpg', '.jpeg', '.png')):
                            st.image(f.read(), caption=os.path.basename(file))
                            f.seek(0)
                            if "download" in user_permissions:
                                st.download_button("📥 Baixar Imagem", f, file_name=os.path.basename(file), key=hash_key("imgk_" + file))
                        else:
                            if "download" in user_permissions:
                                st.download_button("📥 Baixar Arquivo", f, file_name=os.path.basename(file), key=hash_key("othk_" + file))
                    log_action(username, "visualizar", file)
            else:
                st.warning("Nenhum arquivo encontrado.")

    # HISTÓRICO DE AÇÕES (disponível para autenticados)
    st.markdown("### 📜 Histórico de Ações")
    if st.checkbox("Mostrar log"):
        logs = c.execute("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 50").fetchall()
        for row in logs:
            st.write(f"{row[0]} | Usuário: {row[1]} | Ação: {row[2]} | Arquivo: {row[3]}")
