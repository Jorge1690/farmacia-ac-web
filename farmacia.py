import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
from fpdf import FPDF
import uuid
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(
    page_title="Farmacia Ac", 
    layout="wide", 
    page_icon="🏥"
)

# --- 2. BASE DE DATOS (GESTIÓN ROBUSTA) ---

def get_db_connection():
    conn = sqlite3.connect('farmacia.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Crear tablas
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (ID TEXT PRIMARY KEY, Nombre TEXT, Unidad TEXT, Stock INTEGER, StockMinimo INTEGER, Gestion TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS residents
                 (ID TEXT PRIMARY KEY, Nombre TEXT, RUT TEXT, Piso TEXT, Habitacion TEXT, Apoderado TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS movements
                 (ID INTEGER PRIMARY KEY AUTOINCREMENT, Fecha TEXT, Tipo TEXT, ResidenteID TEXT, InsumoID TEXT, NombreInsumo TEXT, Cantidad INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (Username TEXT PRIMARY KEY, Password TEXT, Role TEXT)''')
    
    # Migración: Asegurar columna Gestion
    try:
        c.execute("SELECT Gestion FROM inventory LIMIT 1")
    except sqlite3.OperationalError:
        c.execute("ALTER TABLE inventory ADD COLUMN Gestion TEXT DEFAULT 'Farmacia'")
    
    # Migración: Rellenar nulos antiguos con Farmacia
    c.execute("UPDATE inventory SET Gestion = 'Farmacia' WHERE Gestion IS NULL OR Gestion = ''")
    
    # Usuarios por defecto (Actualizado con los 4 perfiles)
    c.execute('SELECT count(*) FROM users')
    if c.fetchone()[0] == 0:
        users = [
            ("visita", "visita123", "Visita"),
            ("farma", "farma2024", "Farmacia"),
            ("enfermera", "enfermera2024", "Enfermera Jefe"),
            ("admin", "admin2024", "Administrador")
        ]
        c.executemany('INSERT INTO users VALUES (?,?,?)', users)
    
    conn.commit()
    conn.close()

init_db()

# --- 3. LOGICA DE NEGOCIO (FILTRADO PYTHON) ---

def get_data_frames():
    """Extrae toda la data cruda para procesarla con Pandas (Más seguro que SQL complejo)"""
    conn = get_db_connection()
    df_inv = pd.read_sql("SELECT * FROM inventory", conn)
    df_res = pd.read_sql("SELECT * FROM residents", conn)
    df_mov = pd.read_sql("SELECT * FROM movements", conn)
    conn.close()
    return df_inv, df_res, df_mov

def register_consumption(res_id, ins_id, ins_name, qty):
    conn = get_db_connection()
    try:
        # Descontar stock
        conn.execute("UPDATE inventory SET Stock = Stock - ? WHERE ID = ?", (qty, ins_id))
        # Registrar movimiento
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.execute("INSERT INTO movements (Fecha, Tipo, ResidenteID, InsumoID, NombreInsumo, Cantidad) VALUES (?,?,?,?,?,?)",
                     (now, 'CONSUMO', res_id, ins_id, ins_name, qty))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error DB: {e}")
        return False
    finally:
        conn.close()

# --- 4. GENERACIÓN PDF ---

def clean_text(text):
    try:
        return str(text).encode('latin-1', 'replace').decode('latin-1')
    except:
        return str(text)

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Farmacia Ac - Reporte Oficial', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

def generate_pdf(resident_row, df_consumos, start, end, label):
    pdf = PDF()
    pdf.add_page()
    
    # Info Residente
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Residente: {clean_text(resident_row['Nombre'])}", 0, 1)
    
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 6, f"RUT: {resident_row['RUT']}", 0, 1)
    pdf.cell(0, 6, f"Ubicacion: Piso {clean_text(resident_row['Piso'])} - Hab {clean_text(resident_row['Habitacion'])}", 0, 1)
    pdf.cell(0, 6, f"Apoderado: {clean_text(resident_row['Apoderado'])}", 0, 1)
    pdf.ln(3)
    
    pdf.set_font("Arial", 'I', 9)
    pdf.cell(0, 6, f"Reporte: {clean_text(label)} | Del {start} al {end}", 0, 1)
    pdf.ln(5)
    
    # Tabla
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 8, "Fecha", 1)
    pdf.cell(80, 8, "Insumo", 1)
    pdf.cell(40, 8, "Gestion", 1)
    pdf.cell(30, 8, "Cantidad", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=9)
    for _, row in df_consumos.iterrows():
        # Fecha limpia
        f_str = row['Fecha'] if isinstance(row['Fecha'], str) else row['Fecha'].strftime("%Y-%m-%d %H:%M")
        
        pdf.cell(40, 8, str(f_str), 1)
        pdf.cell(80, 8, clean_text(row['NombreInsumo']), 1)
        pdf.cell(40, 8, clean_text(row['Gestion']), 1)
        pdf.cell(30, 8, str(row['Cantidad']), 1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')

def generate_inventory_pdf(df_inv, user):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Inventario General", 0, 1, 'C')
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(0, 10, f"Generado por: {clean_text(user)} | {datetime.now().strftime('%d/%m/%Y')}", 0, 1, 'C')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(70, 8, "Nombre", 1)
    pdf.cell(30, 8, "Gestion", 1)
    pdf.cell(30, 8, "Unidad", 1)
    pdf.cell(30, 8, "Stock", 1)
    pdf.cell(30, 8, "Minimo", 1)
    pdf.ln()
    
    pdf.set_font("Arial", size=9)
    for _, row in df_inv.iterrows():
        pdf.cell(70, 8, clean_text(row['Nombre']), 1)
        pdf.cell(30, 8, clean_text(row['Gestion']), 1)
        pdf.cell(30, 8, clean_text(row['Unidad']), 1)
        pdf.cell(30, 8, str(row['Stock']), 1)
        pdf.cell(30, 8, str(row['StockMinimo']), 1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1')

# --- 5. INTERFAZ Y SESSION STATE ---

if 'role' not in st.session_state: st.session_state.role = None
if 'current_user' not in st.session_state: st.session_state.current_user = None

def login_ui():
    st.markdown("<h1 style='text-align: center;'>🏥 Farmacia Ac</h1>", unsafe_allow_html=True)
    c1,c2,c3 = st.columns([1,2,1])
    with c2:
        with st.form("login"):
            u = st.text_input("Usuario")
            p = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                conn = get_db_connection()
                res = conn.execute("SELECT * FROM users WHERE Username=? AND Password=?", (u,p)).fetchone()
                conn.close()
                if res:
                    st.session_state.role = res['Role']
                    st.session_state.current_user = res['Username']
                    st.rerun()
                else:
                    st.error("Acceso denegado")

if not st.session_state.role:
    login_ui()
else:
    # === APP LOGUEADA ===
    role = st.session_state.role
    user = st.session_state.current_user
    
    # Barra Superior
    c1, c2 = st.columns([6,1])
    with c1: st.title("🏥 Farmacia Ac")
    with c2:
        st.write(f"👤 **{user}** ({role})")
        if st.button("Salir"):
            st.session_state.role = None
            st.session_state.current_user = None
            st.rerun()
            
    # Permisos
    is_admin = role == "Administrador"
    is_farma = role == "Farmacia"
    is_enfermera = role == "Enfermera Jefe"
    
    # Menú
    opts = ["Inventario"]
    if role != "Visita":
        opts.extend(["Cargar insumo a residente", "Reportes"])
    if is_admin or is_farma or is_enfermera:
        opts.append("Gestión")
        
    menu = st.sidebar.radio("Navegación", opts)
    
    # --- PÁGINA: INVENTARIO ---
    if menu == "Inventario":
        st.header("📦 Inventario")
        df_i, _, _ = get_data_frames()
        
        if not df_i.empty:
            st.download_button("📥 Descargar PDF Inventario", 
                               data=generate_inventory_pdf(df_i, user), 
                               file_name="Inventario.pdf", mime="application/pdf")
        
        st.dataframe(df_i, use_container_width=True)
        
        # Admin, Farmacia y Enfermera pueden ver operaciones
        if is_admin or is_farma or is_enfermera:
            st.subheader("Acciones")
            t1, t2, t3 = st.tabs(["Nuevo", "Cargar Stock", "Importar Excel"])
            
            with t1:
                with st.form("new"):
                    c_a, c_b = st.columns(2)
                    nm = c_a.text_input("Nombre")
                    gs = c_a.selectbox("Gestión", ["Farmacia", "Enfermera Jefe"])
                    un = c_b.selectbox("Unidad", ["unidades", "cajas", "ml", "mg"])
                    stk = c_b.number_input("Stock Inicial", min_value=0)
                    stm = c_a.number_input("Mínimo", min_value=1)
                    if st.form_submit_button("Crear"):
                        conn = get_db_connection()
                        try:
                            conn.execute("INSERT INTO inventory VALUES (?,?,?,?,?,?)", 
                                         (generate_id(), nm, un, stk, stm, gs))
                            conn.commit()
                            st.success("Creado")
                            st.rerun()
                        except: st.error("Error")
                        finally: conn.close()
            with t2:
                # Cargar Stock Simple
                all_items = df_i['Nombre'].tolist() if not df_i.empty else []
                if all_items:
                    sel = st.selectbox("Item", all_items)
                    qty = st.number_input("Cantidad", min_value=1)
                    if st.button("Agregar Stock"):
                        conn = get_db_connection()
                        # Buscar ID
                        itm_id = df_i[df_i['Nombre'] == sel].iloc[0]['ID']
                        conn.execute("UPDATE inventory SET Stock = Stock + ? WHERE ID=?", (qty, itm_id))
                        # Registrar entrada como movimiento
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        conn.execute("INSERT INTO movements (Fecha, Tipo, ResidenteID, InsumoID, NombreInsumo, Cantidad) VALUES (?,?,?,?,?,?)",
                                     (now, 'ENTRADA', None, itm_id, sel, qty))
                        conn.commit()
                        conn.close()
                        st.success("Stock actualizado")
                        st.rerun()
            with t3:
                f = st.file_uploader("Excel", type=["xlsx"])
                if f and st.button("Procesar"):
                    try:
                        df = pd.read_excel(f)
                        conn = get_db_connection()
                        c = 0
                        for _, r in df.iterrows():
                            nm = str(r.iloc[0])
                            qt = int(r.iloc[1]) if len(r)>1 else 0
                            gs = str(r.iloc[2]) if len(r)>2 else "Farmacia"
                            
                            ex = conn.execute("SELECT ID FROM inventory WHERE Nombre=?", (nm,)).fetchone()
                            if ex:
                                conn.execute("UPDATE inventory SET Stock = Stock + ? WHERE ID=?", (qt, ex['ID']))
                            else:
                                conn.execute("INSERT INTO inventory VALUES (?,?,?,?,?,?)", 
                                             (generate_id(), nm, "unidades", qt, 5, gs))
                            c += 1
                        conn.commit()
                        conn.close()
                        st.success(f"{c} procesados")
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    # --- PÁGINA: CARGAR INSUMO (UPDATED) ---
    elif menu == "Cargar insumo a residente":
        st.header("💊 Dispensar a Residente")
        
        # 1. Obtener datos frescos de la DB
        conn = get_db_connection()
        try:
            res_rows = conn.execute("SELECT ID, Nombre, RUT FROM residents ORDER BY Nombre").fetchall()
            inv_rows = conn.execute("SELECT ID, Nombre, Stock, Gestion FROM inventory ORDER BY Nombre").fetchall()
        finally:
            conn.close()
            
        if not res_rows or not inv_rows:
            st.warning("Faltan residentes o insumos.")
        else:
            c1, c2, c3 = st.columns([3,3,2])
            
            with c1:
                # Diccionario para Residente
                res_dict = {f"{r['Nombre']} ({r['RUT']})": r['ID'] for r in res_rows}
                res_options = list(res_dict.keys())
                
                # --- MEMORIA DE SELECCIÓN RESIDENTE ---
                idx_res = 0
                if 'last_res_id' in st.session_state:
                    # Buscar el índice del ID guardado
                    for i, name in enumerate(res_options):
                        if res_dict[name] == st.session_state.last_res_id:
                            idx_res = i
                            break
                            
                sel_res_txt = st.selectbox("Residente", res_options, index=idx_res)
                sel_res_id = res_dict[sel_res_txt]
                
            with c2:
                # Diccionario para Insumo con formato (Stock entre paréntesis)
                inv_dict = {}
                for i in inv_rows:
                    display = f"{i['Nombre']} ({i['Gestion']}) (Stock: {i['Stock']})"
                    inv_dict[display] = {'id': i['ID'], 'stk': i['Stock'], 'nm': i['Nombre']}
                
                inv_options = list(inv_dict.keys())
                
                # --- MEMORIA DE SELECCIÓN INSUMO ---
                idx_inv = 0
                if 'last_inv_id' in st.session_state:
                    for i, key in enumerate(inv_options):
                        if inv_dict[key]['id'] == st.session_state.last_inv_id:
                            idx_inv = i
                            break
                            
                sel_inv_txt = st.selectbox("Insumo", inv_options, index=idx_inv)
                sel_inv_data = inv_dict[sel_inv_txt]
                
            with c3:
                cant = st.number_input("Cantidad", min_value=1, value=1)
                
            st.write("")
            if st.button("Confirmar Carga", type="primary"):
                if sel_inv_data['stk'] >= cant:
                    if register_consumption(sel_res_id, sel_inv_data['id'], sel_inv_data['nm'], cant):
                        # Guardar IDs en sesión para recuperar selección tras recarga
                        st.session_state.last_res_id = sel_res_id
                        st.session_state.last_inv_id = sel_inv_data['id']
                        
                        st.success("Registrado correctamente")
                        st.rerun()
                else:
                    st.error("Stock insuficiente")

    # --- PÁGINA: REPORTES (LÓGICA BLINDADA) ---
    elif menu == "Reportes":
        st.header("📄 Reportes de Consumo")
        
        # 1. Filtros
        c1, c2 = st.columns(2)
        today = date.today()
        first = today.replace(day=1)
        d_ini = c1.date_input("Desde", value=first)
        d_fin = c2.date_input("Hasta", value=today)
        
        st.divider()
        
        # 2. Selector de Gestión
        filtro_gestion = st.radio("Filtrar por Gestión:", ["General (Todos)", "Solo Farmacia", "Solo Enfermera Jefe"], horizontal=True)
        
        # 3. Procesamiento de Datos (PANDAS EN MEMORIA PARA SEGURIDAD)
        df_inv, df_res, df_mov = get_data_frames()
        
        if df_mov.empty:
            st.info("No hay movimientos registrados en el sistema.")
        else:
            # Limpieza y preparación para merge
            # Asegurar que Gestion existe y está limpia
            df_inv['Gestion'] = df_inv['Gestion'].fillna('Farmacia').astype(str).str.strip()
            
            # Merge 1: Movimientos + Inventario (Left join para no perder movimientos si borraron insumo)
            df_merged = pd.merge(df_mov, df_inv[['ID', 'Gestion']], left_on='InsumoID', right_on='ID', how='left')
            # Si no cruzó (insumo borrado), asignamos Farmacia por defecto
            df_merged['Gestion'] = df_merged['Gestion'].fillna('Farmacia')
            
            # Filtro Tipo Consumo
            df_consumos = df_merged[df_merged['Tipo'] == 'CONSUMO'].copy()
            
            # Filtro Fechas (Conversión robusta)
            # Convertimos la columna Fecha (string) a datetime object
            df_consumos['FechaDT'] = pd.to_datetime(df_consumos['Fecha'], errors='coerce') # Si falla, NaT
            df_consumos = df_consumos.dropna(subset=['FechaDT']) # Eliminar fechas corruptas
            
            # Aplicar rango
            mask_date = (df_consumos['FechaDT'].dt.date >= d_ini) & (df_consumos['FechaDT'].dt.date <= d_fin)
            df_periodo = df_consumos[mask_date]
            
            # Filtro Gestión
            if filtro_gestion == "Solo Farmacia":
                df_final = df_periodo[df_periodo['Gestion'] == 'Farmacia']
            elif filtro_gestion == "Solo Enfermera Jefe":
                df_final = df_periodo[df_periodo['Gestion'] == 'Enfermera Jefe']
            else:
                df_final = df_periodo # Todos
                
            # Merge 2: Agregar nombres de residentes
            # Asegurar IDs string
            df_final['ResidenteID'] = df_final['ResidenteID'].astype(str)
            df_res['ID'] = df_res['ID'].astype(str)
            
            df_view = pd.merge(df_final, df_res[['ID', 'Nombre', 'RUT', 'Piso', 'Habitacion', 'Apoderado']], 
                               left_on='ResidenteID', right_on='ID', how='left')
            
            # 4. Selector de Residente (SIEMPRE VISIBLE)
            # Lista única de residentes encontrados en la data filtrada
            residentes_encontrados = sorted(df_view['Nombre'].dropna().unique().tolist())
            
            st.subheader("Selección de Residente")
            
            if not residentes_encontrados:
                sel_res = st.selectbox("Residente", ["(No se encontraron consumos con este filtro)"], disabled=True)
                st.warning("No hay datos para mostrar con los filtros seleccionados.")
            else:
                sel_res = st.selectbox("Residente", residentes_encontrados)
                
                # Filtrar data para ese residente específico
                df_res_filtrado = df_view[df_view['Nombre'] == sel_res]
                
                # Mostrar Tabla
                st.info(f"Mostrando: **{filtro_gestion}** para **{sel_res}**")
                st.dataframe(df_res_filtrado[['Fecha', 'NombreInsumo', 'Gestion', 'Cantidad']], use_container_width=True)
                
                # Botón PDF
                res_data = df_res[df_res['Nombre'] == sel_res].iloc[0]
                pdf_bytes = generate_pdf(res_data, df_res_filtrado, d_ini, d_fin, filtro_gestion)
                st.download_button("📥 Descargar Reporte PDF", data=pdf_bytes, file_name=f"Reporte_{sel_res}.pdf", mime="application/pdf")

    # --- PÁGINA: GESTIÓN ---
    elif menu == "Gestión":
        st.header("🛠️ Gestión")
        
        # Tabs dinámicos
        tabs_gestion = []
        if is_admin:
            tabs_gestion.append("Usuarios")
        
        # Residentes: Visible para Admin y Enfermera
        if is_admin or is_enfermera:
            tabs_gestion.append("Residentes")
            
        tabs = st.tabs(tabs_gestion)
        
        # === TAB: USUARIOS (SOLO ADMIN) ===
        if is_admin:
            with tabs[0]:
                conn = get_db_connection()
                df_users = pd.read_sql("SELECT Username, Role FROM users", conn)
                conn.close()
                st.dataframe(df_users, use_container_width=True)
                
                c_create, c_edit = st.columns(2)
                
                with c_create:
                    st.markdown("#### Crear Usuario")
                    with st.form("new_user_form"):
                        nu = st.text_input("Usuario")
                        np = st.text_input("Clave", type="password")
                        nr = st.selectbox("Rol", ["Administrador", "Enfermera Jefe", "Farmacia", "Visita"])
                        if st.form_submit_button("Crear"):
                            conn = get_db_connection()
                            try:
                                conn.execute("INSERT INTO users VALUES (?,?,?)", (nu, np, nr))
                                conn.commit()
                                st.success("Creado")
                                st.rerun()
                            except: st.error("Error/Duplicado")
                            finally: conn.close()
                
                with c_edit:
                    st.markdown("#### Editar / Eliminar")
                    user_edit = st.selectbox("Seleccionar Usuario", df_users['Username'].tolist())
                    if user_edit:
                        conn = get_db_connection()
                        cur_role = conn.execute("SELECT Role FROM users WHERE Username=?", (user_edit,)).fetchone()[0]
                        conn.close()
                        
                        with st.form("edit_user"):
                            er = st.selectbox("Nuevo Rol", ["Administrador", "Enfermera Jefe", "Farmacia", "Visita"], index=["Administrador", "Enfermera Jefe", "Farmacia", "Visita"].index(cur_role))
                            ep = st.text_input("Nueva Clave (opcional)", type="password")
                            c1, c2 = st.columns(2)
                            if c1.form_submit_button("Actualizar"):
                                conn = get_db_connection()
                                if ep: conn.execute("UPDATE users SET Role=?, Password=? WHERE Username=?", (er, ep, user_edit))
                                else: conn.execute("UPDATE users SET Role=? WHERE Username=?", (er, user_edit))
                                conn.commit()
                                conn.close()
                                st.success("Actualizado")
                                st.rerun()
                            if c2.form_submit_button("Eliminar", type="primary"):
                                if user_edit == user: st.error("No puedes eliminarte.")
                                else:
                                    conn = get_db_connection()
                                    conn.execute("DELETE FROM users WHERE Username=?", (user_edit,))
                                    conn.commit()
                                    conn.close()
                                    st.success("Eliminado")
                                    st.rerun()

        # === TAB: RESIDENTES (ADMIN Y ENFERMERA) ===
        # Determinar índice correcto para el tab de residentes
        idx_res_tab = 1 if is_admin else 0 
        
        with tabs[idx_res_tab]:
            _, df_r, _ = get_data_frames()
            st.dataframe(df_r, use_container_width=True)
            
            # Sub-tabs para acciones
            t_m, t_edit, t_e = st.tabs(["Nuevo (Manual)", "Editar / Eliminar", "Cargar Excel"])
            
            # 1. Crear
            with t_m:
                with st.form("nr"):
                    c1,c2 = st.columns(2)
                    nm = c1.text_input("Nombre")
                    rt = c2.text_input("RUT")
                    pi = c1.text_input("Piso")
                    ha = c2.text_input("Habitación")
                    ap = st.text_input("Apoderado")
                    if st.form_submit_button("Guardar") and nm:
                        conn = get_db_connection()
                        conn.execute("INSERT INTO residents VALUES (?,?,?,?,?,?)", (generate_id(), nm, rt, pi, ha, ap))
                        conn.commit()
                        conn.close()
                        st.success("Guardado")
                        st.rerun()
            
            # 2. Editar / Eliminar (NUEVO)
            with t_edit:
                if not df_r.empty:
                    res_to_edit_name = st.selectbox("Seleccionar Residente", df_r['Nombre'].tolist())
                    res_data = df_r[df_r['Nombre'] == res_to_edit_name].iloc[0]
                    
                    with st.form("edit_res_form"):
                        c1, c2 = st.columns(2)
                        enm = c1.text_input("Nombre", value=res_data['Nombre'])
                        ert = c2.text_input("RUT", value=res_data['RUT'])
                        epi = c1.text_input("Piso", value=res_data['Piso'])
                        eha = c2.text_input("Habitación", value=res_data['Habitacion'])
                        eap = st.text_input("Apoderado", value=res_data['Apoderado'])
                        
                        col_upd, col_del = st.columns(2)
                        if col_upd.form_submit_button("Actualizar Datos"):
                            conn = get_db_connection()
                            conn.execute("UPDATE residents SET Nombre=?, RUT=?, Piso=?, Habitacion=?, Apoderado=? WHERE ID=?",
                                         (enm, ert, epi, eha, eap, res_data['ID']))
                            conn.commit()
                            conn.close()
                            st.success("Residente actualizado.")
                            st.rerun()
                            
                        if col_del.form_submit_button("Eliminar Residente", type="primary"):
                            conn = get_db_connection()
                            conn.execute("DELETE FROM residents WHERE ID=?", (res_data['ID'],))
                            conn.commit()
                            conn.close()
                            st.success("Residente eliminado.")
                            st.rerun()
            
            # 3. Carga Excel
            with t_e:
                f = st.file_uploader("Excel", type=["xlsx"])
                if f and st.button("Cargar"):
                    try:
                        d = pd.read_excel(f)
                        conn = get_db_connection()
                        c = 0
                        for _,r in d.iterrows():
                            n = str(r.iloc[0])
                            ex = conn.execute("SELECT ID FROM residents WHERE Nombre=?", (n,)).fetchone()
                            if not ex:
                                conn.execute("INSERT INTO residents VALUES (?,?,?,?,?,?)",
                                             (generate_id(), n, str(r.iloc[1]), str(r.iloc[2]), str(r.iloc[3]), str(r.iloc[4])))
                                c += 1
                        conn.commit()
                        conn.close()
                        st.success(f"{c} cargados")
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")