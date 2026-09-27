import streamlit as st
import pandas as pd
from datetime import datetime
import io
from sqlalchemy import create_engine, text
import sqlalchemy

# 1. CONEXIÓN A LA BASE DE DATOS EN LA NUBE (Supabase)
# Reemplaza TU_CONTRASEÑA_AQUI con tu contraseña real
DB_URL = "postgresql+psycopg2://postgres.thwypnuvywoewzgdklcl:TIENDAELISA2526@aws-0-us-east-2.pooler.supabase.com:6543/postgres"

@st.cache_resource
def init_connection():
    return create_engine(DB_URL)

engine = init_connection()

# 2. INTERFAZ WEB CON STREAMLIT
st.set_page_config(page_title="Gestión de Cuentas", page_icon="📓", layout="centered")
st.title("📓 Cuaderno Digital de Fiados")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Venta", "💵 Pago", "💰 Cuentas", "📄 Detalle/Excel", "👤 Cliente"])

# --- EXTRAER LISTA DE CLIENTES ---
df_clientes = pd.read_sql_query("SELECT * FROM clientes", engine)

# --- PESTAÑA 5: CREAR CLIENTE ---
with tab5:
    st.subheader("Agregar un nuevo cliente")
    with st.form("form_nuevo_cliente", clear_on_submit=True):
        nombre = st.text_input("Nombre completo o apodo del cliente:")
        if st.form_submit_button("Guardar Cliente") and nombre:
            try:
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO clientes (nombre) VALUES (:nombre)"), {"nombre": nombre.strip()})
                st.success(f"✅ Cliente '{nombre}' agregado. Recarga la página para verlo.")
            except sqlalchemy.exc.IntegrityError:
                st.error("⚠️ Ese cliente ya está registrado.")

# --- PESTAÑA 1: REGISTRAR FIADO (CARGO) ---
with tab1:
    st.subheader("Anotar nuevo producto fiado")
    if not df_clientes.empty:
        cliente_seleccionado = st.selectbox("Selecciona el cliente:", df_clientes['nombre'].tolist(), key="sel_venta")
        with st.form("form_nuevo_fiado", clear_on_submit=True):
            detalle = st.text_input("¿Qué se llevó? (Ej: 1kg Arroz, 2 atunes, etc.)")
            monto = st.number_input("Costo Total (S/.)", min_value=0.1, step=0.50, format="%.2f")
            
            if st.form_submit_button("Anotar en la cuenta") and detalle:
                id_c = int(df_clientes.loc[df_clientes['nombre'] == cliente_seleccionado, 'id_cliente'].values[0])
                fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO movimientos (id_cliente, fecha, tipo, detalle, monto) 
                        VALUES (:id_c, :fecha, 'Cargo', :detalle, :monto)
                    """), {"id_c": id_c, "fecha": fecha_actual, "detalle": detalle, "monto": monto})
                st.success(f"✅ S/ {monto} anotados a la cuenta de {cliente_seleccionado}")
    else:
        st.info("Primero registra a un cliente en la pestaña '👤 Cliente'.")

# --- PESTAÑA 2: REGISTRAR PAGO O ADELANTO (ABONO) ---
with tab2:
    st.subheader("Registrar un adelanto o pago")
    if not df_clientes.empty:
        with st.form("form_nuevo_pago", clear_on_submit=True):
            cliente_pago = st.selectbox("Selecciona el cliente que pagó:", df_clientes['nombre'].tolist(), key="sel_pago")
            monto_pago = st.number_input("Monto pagado (S/.)", min_value=0.1, step=0.50, format="%.2f", key="num_pago")
            detalle_pago = st.text_input("Detalle (Opcional):", value="Adelanto a cuenta", key="det_pago")
            
            if st.form_submit_button("Registrar Pago"):
                id_c_pago = int(df_clientes.loc[df_clientes['nombre'] == cliente_pago, 'id_cliente'].values[0])
                fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO movimientos (id_cliente, fecha, tipo, detalle, monto) 
                        VALUES (:id_c, :fecha, 'Abono', :detalle, :monto)
                    """), {"id_c": id_c_pago, "fecha": fecha_actual, "detalle": detalle_pago, "monto": monto_pago})
                st.success(f"✅ Pago de S/ {monto_pago} registrado a {cliente_pago}")

# --- PESTAÑA 3: VER CUENTAS GENERALES ---
with tab3:
    st.subheader("Estado de Cuentas")
    query_saldos = """
    SELECT c.nombre as "Cliente", 
           ROUND(SUM(CASE WHEN m.tipo = 'Cargo' THEN m.monto ELSE 0 END) - 
           SUM(CASE WHEN m.tipo = 'Abono' THEN m.monto ELSE 0 END), 2) as "Deuda (S/.)"
    FROM clientes c LEFT JOIN movimientos m ON c.id_cliente = m.id_cliente
    GROUP BY c.id_cliente
    """
    df_saldos = pd.read_sql_query(query_saldos, engine).fillna(0)
    df_deudores = df_saldos[df_saldos['Deuda (S/.)'] > 0]
    
    if not df_deudores.empty:
        st.dataframe(df_deudores, use_container_width=True, hide_index=True)
    else:
        st.info("Nadie debe nada por el momento. ¡Genial!")
        
    st.divider()
    
    with st.expander("🛠️ Mantenimiento: Depurar Cuentas Pagadas"):
        st.write("Elimina el historial antiguo de los clientes con saldo exactamente en **S/ 0.00**.")
        if st.button("🧹 Limpiar historiales pagados"):
            query_limpieza = """
            SELECT id_cliente FROM movimientos 
            GROUP BY id_cliente 
            HAVING ROUND(SUM(CASE WHEN tipo = 'Cargo' THEN monto ELSE 0 END) - 
                         SUM(CASE WHEN tipo = 'Abono' THEN monto ELSE 0 END), 2) = 0
            """
            df_limpieza = pd.read_sql_query(query_limpieza, engine)
            if not df_limpieza.empty:
                ids_a_limpiar = tuple(df_limpieza['id_cliente'].tolist())
                with engine.begin() as conn:
                    if len(ids_a_limpiar) == 1:
                        conn.execute(text("DELETE FROM movimientos WHERE id_cliente = :id"), {"id": ids_a_limpiar[0]})
                    else:
                        conn.execute(text("DELETE FROM movimientos WHERE id_cliente IN :ids"), {"ids": ids_a_limpiar})
                st.success(f"✅ Historial limpiado para {len(ids_a_limpiar)} clientes.")
            else:
                st.info("No hay cuentas en S/ 0.00 para limpiar.")

# --- PESTAÑA 4: DETALLE DEL CLIENTE Y EXCEL ---
with tab4:
    st.subheader("Historial detallado y Exportación")
    if not df_clientes.empty:
        cliente_historial = st.selectbox("Selecciona el cliente:", df_clientes['nombre'].tolist(), key="sel_historial")
        id_c_historial = int(df_clientes.loc[df_clientes['nombre'] == cliente_historial, 'id_cliente'].values[0])
        
        query_movs = f"""
        SELECT fecha as "Fecha", tipo as "Tipo", detalle as "Detalle", monto as "Monto" 
        FROM movimientos WHERE id_cliente = {id_c_historial} ORDER BY fecha ASC
        """
        df_movs = pd.read_sql_query(query_movs, engine)
        
        if not df_movs.empty:
            cargos = df_movs[df_movs['Tipo'] == 'Cargo']['Monto'].sum()
            abonos = df_movs[df_movs['Tipo'] == 'Abono']['Monto'].sum()
            saldo_actual = cargos - abonos
            
            st.metric(label=f"Saldo Pendiente de {cliente_historial}", value=f"S/ {saldo_actual:.2f}")
            
            fila_total = pd.DataFrame([{'Fecha': '', 'Tipo': '', 'Detalle': 'SALDO TOTAL A PAGAR --->', 'Monto': round(saldo_actual, 2)}])
            df_exportar = pd.concat([df_movs, fila_total], ignore_index=True)
            
            st.dataframe(df_exportar, use_container_width=True, hide_index=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df_exportar.to_excel(writer, index=False, sheet_name='Historial')
                
            st.download_button(
                label="📥 Descargar en Excel",
                data=buffer.getvalue(),
                file_name=f"cuenta_{cliente_historial}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Este cliente no tiene compras ni pagos registrados.")