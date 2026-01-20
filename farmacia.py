import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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

# --- 2. CONEXIÓN GOOGLE SHEETS ---

def get_sheet_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        # Intenta leer desde secrets (Producción)
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Farmacia_DB") 
        return sheet
    except Exception as e:
        st.error(f"Error conectando a Google Sheets: {e}")
        st.stop()

def init_db_sheets():
    """Inicializa las hojas si no existen"""
    try:
        sh = get_sheet_connection()
        try:
            ws_titles = [ws.title for ws in sh.worksheets()]
        except:
            ws_titles = []
            
        tables = {
            "Inventory": ["ID", "Nombre", "Unidad", "Stock", "StockMinimo", "Gestion"],
            "Residents": ["ID", "Nombre", "RUT", "Piso", "Habitacion", "Apoderado"],
            "Movements": ["ID", "Fecha", "Tipo", "ResidenteID", "InsumoID", "NombreInsumo", "Cantidad", "Gestion"],
            "Users": ["Username", "Password", "Role"]
        }
        
        for name, cols in tables.items():
            if name not in ws_titles:
                ws = sh.add_worksheet(title=name, rows=100, cols=20)
                ws.append_row(cols)
                if name == "Users":
                    ws.append_rows([
                        ["visita", "visita123", "Visita"],
                        ["farma", "farma2024", "Farmacia"],
                        ["enfermera", "enfermera2024", "Enfermera Jefe"],
                        ["admin", "admin2024", "Administrador"]
                    ])
    except Exception as e:
        st.error(f"Error inicializando DB: {e}")

# Cache inteligente (TTL corto para ver actualizaciones rápido)
@st.cache_data(ttl=3) 
def load_data():
    sh = get_sheet_connection()
    
    def get_df(ws_name):
        try:
            ws = sh.worksheet(ws_name)
            data = ws.get_all_records()
            df = pd.DataFrame(data)
            # BLINDAJE DE DATOS: Convertir todo a string para evitar errores de tipo
            for col in df.columns:
                df[col] = df[col].astype(str).str.strip()
            return df
        except:
            return pd.DataFrame()

    return get_df("Inventory"), get_df("Residents"), get_df("Movements"), get_df("Users")

# --- FUNCIONES DE ESCRITURA ---
def add_row_to_sheet(ws_name, row_data):
    sh = get_sheet_connection()
    ws = sh.worksheet(ws_name)
    # Convertir a string para consistencia
    row_data = [str(x) for x in row_data]
    ws.append_row(row_data)
    load_data.clear()

def update_stock_sheet(insumo_id, qty, operation="subtract"):
    sh = get_sheet_connection()
    ws = sh.worksheet("Inventory")
    try:
        cell = ws.find(str(insumo_id))
        if cell:
            # Stock en columna 4 (D)
            curr_val = int(ws.cell(cell.row, 4).value)
            new_val = curr_val - qty if operation == "subtract" else curr_val + qty
            ws.update_cell(cell.row, 4, new_val)
            load_data.clear()
            return True
        return False
    except: return False

def update_user_role(username, new_role, new_pass=None):
    sh = get_sheet_connection()
    ws = sh.worksheet("Users")
    try:
        cell = ws.find(str(username))
        if cell:
            ws.update_cell(cell.row, 3, new_role)
            if new_pass:
                ws.update_cell(cell.row, 2, new_pass)
            load_data.clear()
            return True
    except: pass
    return False

def delete_user_row(username):
    sh = get_sheet_connection()
    ws = sh.worksheet("Users")
    try:
        cell = ws.find(str(username))
        if cell:
            ws.delete_rows(cell.row)
            load_data.clear()
            return True
    except: pass
    return False

def delete_resident_row(res_id):
    sh = get_sheet_connection()
    ws = sh.worksheet("Residents")
    try:
        cell = ws.find(str(res_id))
        if cell:
            ws.delete_rows(cell.row)
            load_data.clear()
            return True
    except: pass
    return False

def update_resident_row(res_id, nm, rt, ps, hb, ap):
    sh = get_sheet_connection()
    ws = sh.worksheet("Residents")
    try:
        cell = ws.find(str(res_id))
        if cell:
            r = cell.row
            # Actualizar columnas 2 a 6
            ws.update_cell(r, 2, nm)
            ws.update_cell(r, 3, rt)
            ws.update_cell(r, 4, ps)
            ws.update_cell(r, 5, hb)
            ws.update_cell(r, 6, ap)
            load_data.clear()
            return True
    except: pass
    return False

# --- UTILS ---
def generate_id(): return str(uuid.uuid4())[:8]
def clean_text(t): return str(t).encode('latin-1','replace').decode('latin-1')

# --- PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial','B',15)
        self.cell(0,10,'Farmacia Ac - Reporte Oficial',0,1,'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial','I',8)
        self.cell(0,10,f'Pag {self.page_no()}',0,0,'C')

def make_pdf(res_data, df_mov, start, end, label):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial','B',12)
    pdf.cell(0,10,f"Residente: {clean_text(res_data['Nombre'])}",0,1)
    pdf.set_font('Arial',size=10)
    pdf.cell(0,6,f"RUT: {res_data['RUT']}",0,1)
    pdf.cell(0,6,f"Ubicacion: Piso {clean_text(res_data['Piso'])} - Hab {clean_text(res_data['Habitacion'])}",0,1)
    pdf.cell(0,6,f"Apoderado: {clean_text(res_data['Apoderado'])}",0,1)
    pdf.ln(5)
    pdf.set_font('Arial','I',9)
    s_str = start.strftime('%d/%m/%Y')
    e_str = end.strftime('%d/%m/%Y')
    pdf.cell(0,6,f"Filtro: {clean_text(label)} | {s_str} - {e_str}",0,1)
    pdf.ln(5)
    pdf.set_font('Arial','B',10)
    pdf.cell(40,8,"Fecha",1)
    pdf.cell(70,8,"Insumo",1)
    pdf.cell(40,8,"Gestion",1)
    pdf.cell(30,8,"Cantidad",1)
    pdf.ln()
    pdf.set_font('Arial',size=9)
    for _,r in df_mov.iterrows():
        pdf.cell(40,8,str(r['Fecha'])[:16],1)
        pdf.cell(70,8,clean_text(r['NombreInsumo']),1)
        pdf.cell(40,8,clean_text(r['Gestion']),1)
        pdf.cell(30,8,str(r['Cantidad']),1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

def make_inv_pdf(df_inv, user):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial','B',14)
    pdf.cell(0,10,"Inventario General",0,1,'C')
    pdf.set_font('Arial','I',10)
    pdf.cell(0,10,f"Gen: {clean_text(user)} | {datetime.now().strftime('%d/%m/%Y')}",0,1,'C')
    pdf.ln(5)
    pdf.set_font('Arial','B',9)
    pdf.cell(70,8,"Nombre",1); pdf.cell(30,8,"Gestion",1)
    pdf.cell(30,8,"Unidad",1); pdf.cell(30,8,"Stock",1); pdf.ln()
    pdf.set_font('Arial',size=9)
    for _,r in df_inv.iterrows():
        pdf.cell(70,8,clean_text(r['Nombre']),1)
        pdf.cell(30,8,clean_text(r['Gestion']),1)
        pdf.cell(30,8,clean_text(r['Unidad']),1)
        pdf.cell(30,8,str(r['Stock']),1); pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- LOGICA APP ---
if 'role' not in st.session_state: st.session_state.role = None

if not st.session_state.role:
    init_db_sheets() # Intentar inicializar si es posible
    st.markdown("<h1 style='text-align: center;'>🏥 Farmacia Ac</h1>", unsafe_allow_html=True)
    c1,c2,c3=st.columns([1,2,1])
    with c2:
        with st.form("log"):
            u = st.text_input("Usuario")
            p = st.text_input("Clave", type="password")
            if st.form_submit_button("Entrar", use_container_width=True):
                _, _, _, df_users = load_data()
                if not df_users.empty:
                    # Comparación estricta de strings
                    match = df_users[(df_users['Username']==str(u)) & (df_users['Password']==str(p))]
                    if not match.empty:
                        st.session_state.role = match.iloc[0]['Role']
                        st.session_state.user = match.iloc[0]['Username']
                        st.rerun()
                    else: st.error("Error credenciales")
                else: st.error("Error conectando a DB Usuarios")
else:
    role = st.session_state.role
    user = st.session_state.user
    
    # Carga de datos FRESCOS en cada recarga
    df_inv, df_res, df_mov, df_usr = load_data()
    
    # Header
    c1,c2 = st.columns([6,1])
    with c1: st.title("🏥 Farmacia Ac")
    with c2: 
        st.write(f"👤 **{user}**")
        if st.button("Salir"):
            st.session_state.role = None
            st.rerun()
            
    is_admin = role == "Administrador"
    is_farma = role == "Farmacia"
    is_enfer = role == "Enfermera Jefe"
    
    opts = ["Inventario"]
    if role != "Visita": opts += ["Cargar insumo a residente", "Reportes"]
    if is_admin or is_farma or is_enfer: opts.append("Gestión")
    
    menu = st.sidebar.radio("Navegación", opts)
    
    # --- INVENTARIO ---
    if menu == "Inventario":
        st.header("📦 Inventario")
        if not df_inv.empty:
            st.download_button("📥 PDF Inventario", make_inv_pdf(df_inv, user), "inv.pdf", "application/pdf")
        st.dataframe(df_inv, use_container_width=True)
        
        if role != "Visita":
            t1, t2, t3 = st.tabs(["Nuevo", "Stock", "Excel"])
            with t1:
                with st.form("ni"):
                    c_a,c_b = st.columns(2)
                    nm = c_a.text_input("Nombre")
                    gs = c_a.selectbox("Gestión", ["Farmacia", "Enfermera Jefe"])
                    un = c_b.selectbox("Unidad", ["unidades","cajas","ml"])
                    stk = c_b.number_input("Stock",0)
                    stm = c_a.number_input("Mín", 5)
                    if st.form_submit_button("Crear"):
                        add_row_to_sheet("Inventory", [generate_id(), nm, un, stk, stm, gs])
                        st.success("Creado (Recarga para ver ID)"); st.rerun()
            with t2:
                if not df_inv.empty:
                    items = df_inv['Nombre'].tolist()
                    sel = st.selectbox("Item", items)
                    qty = st.number_input("Cant",1)
                    if st.button("Sumar"):
                        iid = df_inv[df_inv['Nombre']==sel].iloc[0]['ID']
                        ges = df_inv[df_inv['Nombre']==sel].iloc[0]['Gestion']
                        if update_stock_sheet(iid, qty, "add"):
                            add_row_to_sheet("Movements", [generate_id(), str(datetime.now())[:16], "ENTRADA", "", iid, sel, qty, ges])
                            st.success("Ok"); st.rerun()
            with t3:
                f = st.file_uploader("Excel", type=["xlsx"])
                if f and st.button("Procesar"):
                    try:
                        d = pd.read_excel(f)
                        c = 0
                        for _,r in d.iterrows():
                            # Validar que no exista
                            if str(r.iloc[0]) not in df_inv['Nombre'].values:
                                add_row_to_sheet("Inventory", [generate_id(), str(r.iloc[0]), "unidades", int(r.iloc[1]), 5, str(r.iloc[2]) if len(r)>2 else "Farmacia"])
                                c+=1
                        st.success(f"{c} cargados"); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    # --- CARGAR (Con Memoria) ---
    elif menu == "Cargar insumo a residente":
        st.header("💊 Dispensar")
        if df_inv.empty or df_res.empty: 
            st.warning("Sin datos")
        else:
            c1,c2,c3 = st.columns([3,3,2])
            
            # 1. Selector Residente con memoria
            r_dict = {f"{r['Nombre']} ({r['RUT']})": r['ID'] for _,r in df_res.iterrows()}
            r_keys = list(r_dict.keys())
            idx_r = 0
            if 'mem_res_id' in st.session_state:
                # Buscar el key que corresponde al ID guardado
                found = [k for k,v in r_dict.items() if v == st.session_state.mem_res_id]
                if found: idx_r = r_keys.index(found[0])
            
            sel_r_txt = c1.selectbox("Residente", r_keys, index=idx_r)
            rid = r_dict[sel_r_txt]
            
            # 2. Selector Insumo con memoria
            i_dict = {}
            for _,row in df_inv.iterrows():
                lbl = f"{row['Nombre']} ({row['Gestion']}) [Stk:{row['Stock']}]"
                i_dict[lbl] = {'id': row['ID'], 'stk': int(row['Stock']), 'nm': row['Nombre'], 'gs': row['Gestion']}
            i_keys = list(i_dict.keys())
            idx_i = 0
            if 'mem_inv_id' in st.session_state:
                found_i = [k for k,v in i_dict.items() if v['id'] == st.session_state.mem_inv_id]
                if found_i: idx_i = i_keys.index(found_i[0])
                
            sel_i_txt = c2.selectbox("Insumo", i_keys, index=idx_i)
            idata = i_dict[sel_i_txt]
            
            qty = c3.number_input("Cant", 1)
            
            if st.button("Confirmar Carga", type="primary"):
                if idata['stk'] >= qty:
                    if update_stock_sheet(idata['id'], qty, "subtract"):
                        add_row_to_sheet("Movements", [generate_id(), str(datetime.now())[:16], "CONSUMO", rid, idata['id'], idata['nm'], qty, idata['gs']])
                        # Guardar en memoria
                        st.session_state.mem_res_id = rid
                        st.session_state.mem_inv_id = idata['id']
                        st.success("Registrado"); st.rerun()
                else: st.error("Stock bajo")

    # --- REPORTES (CORREGIDO) ---
    elif menu == "Reportes":
        st.header("📄 Reportes")
        c1,c2 = st.columns(2)
        d_i = c1.date_input("Desde", date.today().replace(day=1))
        d_f = c2.date_input("Hasta", date.today())
        
        st.divider()
        filtro = st.radio("Filtro Gestión:", ["General (Todos)", "Solo Farmacia", "Solo Enfermera Jefe"], horizontal=True)
        
        if df_mov.empty: st.info("Sin movimientos")
        else:
            # 1. Merge Movimientos + Inventario (Para asegurar Gestion)
            # Aunque Movimientos ya tiene Gestion (si se grabó bien), hacemos merge por seguridad si son datos antiguos
            df_mov['InsumoID'] = df_mov['InsumoID'].astype(str)
            df_inv['ID'] = df_inv['ID'].astype(str)
            
            # Left join para mantener movimientos aunque se borre insumo
            df_full = pd.merge(df_mov, df_inv[['ID', 'Gestion']], left_on='InsumoID', right_on='ID', how='left', suffixes=('', '_inv'))
            
            # Prioridad: Gestion guardada en movimiento > Gestion del inventario actual > Default Farmacia
            if 'Gestion_inv' in df_full.columns:
                df_full['Gestion'] = df_full['Gestion'].replace('', pd.NA).fillna(df_full['Gestion_inv']).fillna('Farmacia')
            else:
                df_full['Gestion'] = df_full['Gestion'].replace('', 'Farmacia')

            # 2. Filtrar fechas
            df_full['DT'] = pd.to_datetime(df_full['Fecha'], format='mixed', dayfirst=False, errors='coerce')
            df_full = df_full.dropna(subset=['DT'])
            
            mask_date = (df_full['Tipo']=="CONSUMO") & (df_full['DT'].dt.date >= d_i) & (df_full['DT'].dt.date <= d_f)
            df_periodo = df_full[mask_date]
            
            # 3. Filtrar Gestion
            if filtro == "Solo Farmacia":
                df_final = df_periodo[df_periodo['Gestion'] == 'Farmacia']
            elif filtro == "Solo Enfermera Jefe":
                df_final = df_periodo[df_periodo['Gestion'] == 'Enfermera Jefe']
            else:
                df_final = df_periodo
            
            # 4. Unir con nombres de residentes
            df_final['ResidenteID'] = df_final['ResidenteID'].astype(str)
            df_view = pd.merge(df_final, df_res[['ID','Nombre']], left_on='ResidenteID', right_on='ID', how='left')
            
            # 5. Selector
            res_list = sorted(df_view['Nombre'].dropna().unique().tolist())
            
            if not res_list:
                st.selectbox("Residente", ["(Sin datos para este filtro)"], disabled=True)
                st.warning(f"No hay consumos de '{filtro}' en este rango de fechas.")
            else:
                sel_res = st.selectbox("Residente", res_list)
                if sel_res:
                    df_user = df_view[df_view['Nombre'] == sel_res]
                    st.info(f"Mostrando: {filtro} para {sel_res}")
                    st.dataframe(df_user[['Fecha', 'NombreInsumo', 'Gestion', 'Cantidad']], use_container_width=True)
                    
                    # PDF
                    try:
                        res_data = df_res[df_res['Nombre'] == sel_res].iloc[0]
                        st.download_button("📥 PDF", make_pdf(res_data, df_user, d_i, d_f, filtro), f"rep_{sel_res}.pdf", "application/pdf")
                    except: st.error("Error generando PDF (datos incompletos del residente)")

    # --- GESTIÓN ---
    elif menu == "Gestión":
        st.header("🛠️ Gestión")
        t1, t2 = st.tabs(["Usuarios", "Residentes"])
        
        if is_admin:
            with t1:
                st.dataframe(df_usr)
                c_cr, c_ed = st.columns(2)
                with c_cr:
                    with st.form("nu"):
                        u = st.text_input("User"); p = st.text_input("Pass", type="password")
                        r = st.selectbox("Rol", ["Visita","Farmacia","Enfermera Jefe","Administrador"])
                        if st.form_submit_button("Crear"):
                            if str(u) not in df_usr['Username'].values:
                                add_row_to_sheet("Users", [u,p,r]); st.success("Ok"); st.rerun()
                            else: st.error("Existe")
                with c_ed:
                    if not df_usr.empty:
                        ue = st.selectbox("Editar", df_usr['Username'].tolist())
                        if ue:
                            with st.form("edu"):
                                nr = st.selectbox("Rol", ["Visita","Farmacia","Enfermera Jefe","Administrador"])
                                np = st.text_input("Pass (Opcional)", type="password")
                                c_a, c_b = st.columns(2)
                                if c_a.form_submit_button("Update"):
                                    update_user_role(ue, nr, np if np else None)
                                    st.success("Ok"); st.rerun()
                                if c_b.form_submit_button("Delete", type="primary"):
                                    if ue != user: delete_user_row(ue); st.success("Bye"); st.rerun()
                                    else: st.error("No")

        # Tab Residentes (Admin y Enfermera)
        with t2:
            st.dataframe(df_res)
            if is_admin or is_enfer:
                t_m, t_e, t_ed = st.tabs(["Nuevo", "Excel", "Editar"])
                with t_m:
                    with st.form("nr"):
                        n = st.text_input("Nombre"); ru = st.text_input("RUT")
                        p = st.text_input("Piso"); h = st.text_input("Hab")
                        ap = st.text_input("Apod")
                        if st.form_submit_button("Guardar"):
                            add_row_to_sheet("Residents", [generate_id(), n, ru, p, h, ap])
                            st.success("Ok"); st.rerun()
                with t_e:
                    f = st.file_uploader("XLSX", type=["xlsx"])
                    if f and st.button("Cargar"):
                        try:
                            d = pd.read_excel(f)
                            c=0
                            for _,r in d.iterrows():
                                if str(r.iloc[0]) not in df_res['Nombre'].values:
                                    add_row_to_sheet("Residents", [generate_id(), str(r.iloc[0]), str(r.iloc[1]), str(r.iloc[2]), str(r.iloc[3]), str(r.iloc[4])])
                                    c+=1
                            st.success(f"{c} ok"); st.rerun()
                        except: st.error("Error")
                with t_ed:
                    if not df_res.empty:
                        re = st.selectbox("Residente", df_res['Nombre'].tolist())
                        if re:
                            rd = df_res[df_res['Nombre']==re].iloc[0]
                            with st.form("edr"):
                                nn = st.text_input("Nombre", rd['Nombre'])
                                nru = st.text_input("RUT", rd['RUT'])
                                np = st.text_input("Piso", rd['Piso'])
                                nh = st.text_input("Hab", rd['Habitacion'])
                                nap = st.text_input("Apod", rd['Apoderado'])
                                c_up, c_dl = st.columns(2)
                                if c_up.form_submit_button("Actualizar"):
                                    update_resident_row(rd['ID'], nn, nru, np, nh, nap)
                                    st.success("Ok"); st.rerun()
                                if c_dl.form_submit_button("Borrar", type="primary"):
                                    delete_resident_row(rd['ID'])
                                    st.success("Bye"); st.rerun()