import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time 
# Configuración inicial
st.set_page_config(page_title="El Galpón - Gestión", layout="wide", page_icon="🍻")





# ==========================================================
# 🔐 EL PORTERO (SISTEMA DE LOGIN CON FORMULARIO)
# ==========================================================
def check_password():
    """Retorna True si el usuario ingresó la clave correcta."""

    # 1. Si ya validó antes, pase nomás
    if st.session_state.get("password_correct", False):
        return True

    # 2. Si no, mostramos el formulario de login
    st.title("🔒 Acceso Restringido")
    
    with st.form("login_form"):
        st.markdown("##### Ingresá la contraseña para acceder al sistema")
        
        # El input de contraseña
        password_input = st.text_input(
            "Contraseña", 
            type="password", 
            placeholder="Escribí la clave acá..."
        )
        
        # El botón de Entrar
        submit_button = st.form_submit_button("🚀 Entrar al Sistema")

        if submit_button:
            # Validamos solo cuando aprieta el botón
            if password_input == st.secrets["general"]["admin_password"]:
                st.session_state["password_correct"] = True
                st.rerun()  # Recargamos para que entre de una
            else:
                st.error("⛔ Clave incorrecta. Probá de nuevo.")

    # Frenamos todo hasta que se loguee
    return False

# SI EL PORTERO DICE QUE NO, PARAMOS TODO ACÁ
if not check_password():
    st.stop()




# --- CONEXIÓN ---
@st.cache_resource
def get_engine():
    c = st.secrets["postgres"]
    return create_engine(f"postgresql://{c['user']}:{c['password']}@{c['host']}:{c['port']}/{c['database']}")

engine = get_engine()

# --- INICIALIZACIÓN DE MEMORIA ---
if 'carrito_compra' not in st.session_state:
    st.session_state.carrito_compra = []

if 'carrito_venta' not in st.session_state:
    st.session_state.carrito_venta = []
    
if 'carrito_concesion' not in st.session_state:
    st.session_state.carrito_concesion = []

# --- FUNCIONES AUXILIARES ---
def calcular_costo_real(id_producto):
    """Obtiene el costo promedio ponderado del producto"""
    query = text("""
        SELECT precio_costo_promedio 
        FROM productos 
        WHERE id_producto = :id_prod
    """)
    with engine.connect() as conn:
        result = conn.execute(query, {"id_prod": id_producto}).fetchone()
        return float(result[0]) if result else 0.0

def obtener_kpis():
    """Obtiene los KPIs actualizados con lógica de formatos y márgenes reales"""
    query = text("""
        WITH VentasCalculadas AS (
            SELECT 
                -- Calculamos las unidades reales vendidas (unidades x factor de caja)
                (dv.cantidad_formato * CASE WHEN dv.formato_venta = 'Caja' THEN p.unidades_por_caja ELSE 1 END) as unidades_reales,
                dv.precio_unitario_historico,
                p.precio_costo_promedio
            FROM detalle_ventas dv
            JOIN ventas v ON dv.id_venta = v.id_venta
            JOIN productos p ON dv.id_producto = p.id_producto
            WHERE v.fecha >= CURRENT_DATE - INTERVAL '30 days'
        ),
        VentasTotales AS (
            SELECT 
                SUM(unidades_reales * precio_unitario_historico) as total_ventas,
                SUM(unidades_reales * precio_costo_promedio) as costo_total
            FROM VentasCalculadas
        ),
        StockValorizado AS (
            SELECT SUM(stock_actual * precio_costo_promedio) as valor_inventario
            FROM productos
        )
        SELECT 
            COALESCE(vt.total_ventas, 0) as ventas_mes,
            COALESCE(vt.total_ventas - vt.costo_total, 0) as margen_bruto,
            COALESCE(sv.valor_inventario, 0) as valor_stock,
            (SELECT COUNT(*) FROM productos WHERE stock_actual <= stock_minimo) as productos_criticos
        FROM VentasTotales vt, StockValorizado sv
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query).fetchone()
        return {
            'ventas_mes': float(result[0]),
            'margen_bruto': float(result[1]),
            'valor_stock': float(result[2]),
            'productos_criticos': int(result[3])
        }


# --- TABS PRINCIPALES ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7= st.tabs([
    "📊 Dashboard", 
    "💰 Registrar Venta", 
    "🚚 Cargar Compra",
    "🤝 Concesiones",
    "📈 Análisis",
    "🔍 Auditoría",
    "📂 Carga de Datos"
    
])

# ==========================================================
# TAB 1: DASHBOARD MEJORADO
# ==========================================================
with tab1:
    st.title("📈 Dashboard - El Galpón")
    
    # KPIs principales
    kpis = obtener_kpis()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Ventas (30 días)", 
            f"${kpis['ventas_mes']:,.0f}",
            delta=None
        )
    
    with col2:
        margen_val = kpis['margen_bruto']
        # El delta ahora será rojo si es negativo automáticamente
        st.metric(
            "Margen Bruto", 
            f"${margen_val:,.0f}",
            delta=f"{(margen_val/kpis['ventas_mes']*100 if kpis['ventas_mes'] != 0 else 0):.1f}%",
            delta_color="normal" # "normal" pone verde si sube y rojo si baja de 0
        )
    
    with col3:
        st.metric(
            "Valor en Stock", 
            f"${kpis['valor_stock']:,.0f}"
        )
    
    with col4:
        st.metric(
            "Productos Críticos", 
            kpis['productos_criticos'],
            delta="Reponer" if kpis['productos_criticos'] > 0 else "OK",
            delta_color="inverse"
        )
    
    st.markdown("---")
    
    # Query principal mejorada
    query_master = text("""
    WITH VentasTotales AS (
        SELECT id_producto, 
               SUM(cantidad_formato) as total_vendido,
               MAX(v.fecha) as ultima_venta
        FROM detalle_ventas dv
        JOIN ventas v ON dv.id_venta = v.id_venta
        GROUP BY id_producto
    ),
    VentasRecientes AS (
        SELECT id_producto, SUM(cantidad_formato) as vendido_30d
        FROM detalle_ventas dv
        JOIN ventas v ON dv.id_venta = v.id_venta
        WHERE v.fecha >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY id_producto
    )
    SELECT 
        p.id_producto,
        p.nombre AS "Producto", 
        m.nombre AS "Marca",
        p.stock_actual AS "Stock",
        COALESCE(vr.vendido_30d, 0) AS "Venta 30d",
        COALESCE(vt.total_vendido, 0) AS "Total Vendido",
        ROUND(p.precio_costo_promedio, 2) AS "Costo Prorr",
        p.precio_venta AS "Precio",
        ROUND(((p.precio_venta - p.precio_costo_promedio) / NULLIF(p.precio_venta, 0) * 100), 1) AS "Margen %",
        ROUND(p.stock_actual * p.precio_costo_promedio, 2) AS "Valor Stock",
        CASE 
            WHEN p.stock_actual <= 0 THEN '🔴 SIN STOCK'
            WHEN p.stock_actual <= p.stock_minimo THEN '🟡 BAJO'
            WHEN COALESCE(vr.vendido_30d, 0) = 0 AND p.stock_actual > 0 THEN '⚪ SIN ROTACIÓN'
            ELSE '🟢 OK' 
        END AS "Estado",
        CASE 
            WHEN COALESCE(vr.vendido_30d, 0) > 0 
            THEN ROUND(p.stock_actual::numeric / (vr.vendido_30d / 30.0), 1)
            ELSE NULL 
        END AS "Días Stock"
    FROM productos p 
    JOIN marcas m ON p.id_marca = m.id_marca
    LEFT JOIN VentasTotales vt ON p.id_producto = vt.id_producto
    LEFT JOIN VentasRecientes vr ON p.id_producto = vr.id_producto
    ORDER BY "Venta 30d" DESC NULLS LAST
""")

    with engine.connect() as conn:
        df_master = pd.read_sql(query_master, conn)

    df_master['Venta 30d'] = pd.to_numeric(df_master['Venta 30d'])
    df_master['Total Vendido'] = pd.to_numeric(df_master['Total Vendido'])
    df_master['Stock'] = pd.to_numeric(df_master['Stock'])
    
    # Filtros
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        filtro_estado = st.multiselect(
            "Filtrar por estado:",
            options=df_master['Estado'].unique(),
            default=None
        )
    
    with col_f2:
        filtro_marca = st.multiselect(
            "Filtrar por marca:",
            options=df_master['Marca'].unique(),
            default=None
        )
    
    with col_f3:
        mostrar_sin_rotacion = st.checkbox("Mostrar solo sin rotación", value=False)
    
    # Aplicar filtros
    df_filtrado = df_master.copy()
    
    if filtro_estado:
        df_filtrado = df_filtrado[df_filtrado['Estado'].isin(filtro_estado)]
    
    if filtro_marca:
        df_filtrado = df_filtrado[df_filtrado['Marca'].isin(filtro_marca)]
    
    if mostrar_sin_rotacion:
        df_filtrado = df_filtrado[df_filtrado['Estado'] == '⚪ SIN ROTACIÓN']
    
    # Gráficos
    col_g1, col_g2 = st.columns(2)
    
    with col_g1:
        # Top 10 productos por venta
        df_top = df_filtrado.nlargest(10, 'Venta 30d')
        fig1 = px.bar(
            df_top, 
            x='Producto', 
            y='Venta 30d',
            color='Marca',
            title="🏆 Top 10 Productos (últimos 30 días)",
            template="plotly_white"
        )
        fig1.update_layout(showlegend=True, height=400)
        st.plotly_chart(fig1, width='stretch', config={'scrollZoom': False})
    
    with col_g2:
        # Distribución de márgenes
        fig2 = px.histogram(
            df_filtrado[df_filtrado['Margen %'].notna()], 
            x='Margen %',
            nbins=20,
            title="📊 Distribución de Márgenes",
            template="plotly_white"
        )
        fig2.update_layout(height=400)
        st.plotly_chart(fig2, width='stretch', config={'scrollZoom': False})
    
    # Tabla principal con formato mejorado
    st.subheader("📦 Inventario Completo")
    
    # Columnas a mostrar
    columnas_mostrar = ['Producto', 'Marca', 'Stock', 'Venta 30d', 'Precio', 'Costo Prorr','Margen %', 'Valor Stock', 'Estado', 'Días Stock']
    
    st.dataframe(
        df_filtrado[columnas_mostrar],
        width='stretch',
        hide_index=True,
        column_config={
            "Precio": st.column_config.NumberColumn(format="$%.2f"),
            "Margen %": st.column_config.NumberColumn(format="%.1f%%"),
            "Valor Stock": st.column_config.NumberColumn(format="$%.2f"),
            "Días Stock": st.column_config.NumberColumn(format="%.0f días"),
            "Costo Prorr": st.column_config.NumberColumn(format="$%.2f")
        }
    )
    
    # Resumen de alertas
    st.markdown("---")
    st.subheader("⚠️ Alertas y Recomendaciones")
    
    col_a1, col_a2, col_a3 = st.columns(3)
    
    with col_a1:
        sin_stock = len(df_master[df_master['Estado'] == '🔴 SIN STOCK'])
        st.warning(f"**{sin_stock}** productos sin stock")
        if sin_stock > 0:
            st.dataframe(
                df_master[df_master['Estado'] == '🔴 SIN STOCK'][['Producto', 'Venta 30d']],
                hide_index=True,
                width='stretch'
            )
    
    with col_a2:
        bajo_stock = len(df_master[df_master['Estado'] == '🟡 BAJO'])
        st.info(f"**{bajo_stock}** productos con stock bajo")
        if bajo_stock > 0:
            st.dataframe(
                df_master[df_master['Estado'] == '🟡 BAJO'][['Producto', 'Stock', 'Venta 30d']],
                hide_index=True,
                width='stretch'
            )
    
    with col_a3:
        sin_rotacion = len(df_master[df_master['Estado'] == '⚪ SIN ROTACIÓN'])
        st.error(f"**{sin_rotacion}** productos sin movimiento")
        if sin_rotacion > 0:
            df_sin_rot = df_master[df_master['Estado'] == '⚪ SIN ROTACIÓN'][['Producto', 'Stock', 'Valor Stock']]
            st.dataframe(df_sin_rot, hide_index=True, width='stretch')
            st.caption(f"💰 Inmovilizado: ${df_sin_rot['Valor Stock'].sum():,.2f}")

#==========================================================
# FIX COMPLETO DEL SISTEMA DE VENTAS V2
# Reemplazá TODA la sección del TAB 2 con esto
# ==========================================================

with tab2:
    st.header("🛒 Armar Pedido de Venta")
    
    with engine.connect() as conn:
        clientes = pd.read_sql(text("SELECT id_cliente, razon_social FROM clientes"), conn)
        prods = pd.read_sql(text("""
        SELECT p.id_producto, p.nombre, m.nombre as marca, p.precio_venta, 
               p.precio_venta_caja, p.stock_actual, p.unidades_por_caja,
               p.precio_costo_promedio
        FROM productos p
        JOIN marcas m ON p.id_marca = m.id_marca
        ORDER BY p.nombre
        """), conn)
        
   
    
    # Selector de producto mejorado
    with st.expander("🍻 Selección de Producto", expanded=True):
        if not prods.empty:
            col_p, col_st = st.columns([3, 1])
            
            prod_sel = col_p.selectbox(
                "Elegí el producto", 
                options=prods['id_producto'].tolist(), 
                format_func=lambda x: f"{prods[prods['id_producto']==x]['nombre'].values[0]} ({prods[prods['id_producto']==x]['marca'].values[0]})",
                key="sel_prod_v"
            )
            
            # Buscamos la info del producto elegido
            df_seleccionado = prods[prods['id_producto'] == prod_sel]
            
            if not df_seleccionado.empty:
                info_prod = df_seleccionado.iloc[0] # <--- ESTO YA NO FALLA
                stk = info_prod['stock_actual']
                u_caja = info_prod['unidades_por_caja']
                precio_unidad = float(info_prod['precio_venta'])
                costo_unitario = float(info_prod['precio_costo_promedio'])
                
                # Burbuja de stock
                col_st.metric("Stock Real", f"{stk} un.", delta=f"{int(stk // u_caja)} cajas", delta_color="normal")
        st.markdown("---")
        
        # NUEVA INTERFAZ MÁS CLARA
        col_f, col_c = st.columns([2, 2])
        
        formato = col_f.radio("Formato de Venta", ["Unidad", "Caja"], horizontal=True, key="formato_v")
        cantidad = col_c.number_input(
            f"Cantidad de {formato}s", 
            min_value=1, 
            step=1, 
            key="cant_v"
        )
        
        # Calcular unidades totales
        if formato == "Unidad":
            unidades_totales = cantidad
        else:
            unidades_totales = cantidad * u_caja
        
        st.markdown("---")
        
        # SIEMPRE mostrar precio por UNIDAD
        col_pre, col_info = st.columns([2, 2])
        
        with col_pre:
            st.markdown("**💵 Precio por Unidad:**")
            precio_por_unidad = st.number_input(
                "Precio unitario ($)",
                min_value=0.0,
                value=float(precio_unidad),
                step=10.0,
                key="precio_unitario_input",
                label_visibility="collapsed"
            )
        
        with col_info:
            # Mostrar info útil según el formato
            if formato == "Caja":
                precio_caja_calculado = precio_por_unidad * u_caja
                st.metric(
                    "Precio por Caja", 
                    f"${precio_caja_calculado:,.2f}",
                    help=f"{u_caja} unidades × ${precio_por_unidad:,.2f}"
                )
            else:
                st.metric(
                    "Precio sugerido", 
                    f"${precio_por_unidad:,.2f}"
                )
        
        # Calcular subtotal
        subtotal = unidades_totales * precio_por_unidad
        
        # Calcular margen
        costo_total_item = unidades_totales * costo_unitario
        margen_real = ((subtotal - costo_total_item) / subtotal * 100) if subtotal > 0 else 0
        
        # Mostrar resumen antes de agregar
        st.markdown("---")
        col_r1, col_r2, col_r3 = st.columns(3)
        
        col_r1.metric("Unidades Totales", f"{unidades_totales}")
        col_r2.metric("Subtotal", f"${subtotal:,.2f}")
        
        # Margen con colores
        if margen_real < 0:
            col_r3.metric("Margen", f"{margen_real:.1f}%", delta="PÉRDIDA", delta_color="inverse")
        elif margen_real < 10:
            col_r3.metric("Margen", f"{margen_real:.1f}%", delta="BAJO", delta_color="off")
        else:
            col_r3.metric("Margen", f"{margen_real:.1f}%", delta="OK", delta_color="normal")
        
        # Validación de stock
        if unidades_totales > stk:
            st.error(f"⚠️ Stock insuficiente: intentás vender {unidades_totales} unidades pero solo hay {stk} disponibles.")
            puede_agregar = False
        else:
            puede_agregar = True
        
        # Botón agregar
        if st.button("🛒 Agregar al Pedido", width='stretch', disabled=not puede_agregar):
            st.session_state.carrito_venta.append({
                "id_producto": prod_sel,
                "Producto": f"{info_prod['nombre']} ({info_prod['marca']})",
                "Formato": formato,
                "Cantidad": cantidad,
                "PrecioUnidad": float(precio_por_unidad),
                "UnidadesTotales": unidades_totales,
                "Subtotal": float(subtotal),
                "Costo": float(costo_total_item),
                "Margen": margen_real
            })
            

    # Detalle del carrito
    if st.session_state.carrito_venta:
        st.subheader("📝 Detalle de la Venta")
        
        # Crear DataFrame para mostrar
        df_mostrar = []
        for item in st.session_state.carrito_venta:
            df_mostrar.append({
                "Producto": item["Producto"],
                "Formato": f"{item['Cantidad']} {item['Formato']}",
                "Unidades": item["UnidadesTotales"],
                "Precio Unit.": item["PrecioUnidad"],
                "Margen %": item["Margen"],
                "Subtotal": item["Subtotal"]
            })
        
        df_v = pd.DataFrame(df_mostrar)
        
        st.dataframe(
            df_v,
            hide_index=True,
            width='stretch',
            column_config={
                "Precio Unit.": st.column_config.NumberColumn(format="$%.2f"),
                "Margen %": st.column_config.NumberColumn(format="%.1f%%"),
                "Subtotal": st.column_config.NumberColumn(format="$%.2f")
            }
        )
        
        total_venta_final = sum(item["Subtotal"] for item in st.session_state.carrito_venta)
        costo_total = sum(item["Costo"] for item in st.session_state.carrito_venta)
        margen_total = ((total_venta_final - costo_total) / total_venta_final * 100) if total_venta_final > 0 else 0
        
        col_t1, col_t2, col_t3 = st.columns(3)
        col_t1.metric("Total a Cobrar", f"${total_venta_final:,.2f}")
        col_t2.metric("Costo Total", f"${costo_total:,.2f}")
        col_t3.metric("Margen", f"{margen_total:.1f}%", delta="Ganancia" if margen_total > 0 else "Pérdida")

        with st.form("form_finalizar_venta"):
            st.write("📝 Datos de la Operación")
            
            # Fila 1: Factura y Cliente
            col_f, col_c = st.columns(2)
            nro_fac = col_f.text_input("N° de Factura / Ticket")
            cliente_sel = col_c.selectbox(
                "Cliente", 
                options=clientes['id_cliente'].tolist(), 
                format_func=lambda x: clientes[clientes['id_cliente']==x]['razon_social'].values[0]
            )
            
            # Fila 2: NUEVO CAMPO DE DESCRIPCIÓN (Para poner el nombre del consumidor final, etc)
            descripcion_venta = st.text_input(
                "Observaciones / Nombre Cliente (Opcional)", 
                placeholder="Ej: Juan Pérez, Retira mañana, etc..."
            )
            
            if st.form_submit_button("🚀 Confirmar Venta Completa", width='stretch'):
                try:
                    with engine.begin() as conn:
                        # 1. Creamos la cabecera de la venta
                        res = conn.execute(text("""
                            INSERT INTO ventas (id_cliente, total_venta, nro_factura) 
                            VALUES (:id_c, :total, :fac) RETURNING id_venta
                        """), {"id_c": cliente_sel, "total": float(total_venta_final), "fac": nro_fac})
                        
                        id_v_new = res.fetchone()[0]
                        
                        # 2. Guardamos cada producto con la descripción nueva
                        for item in st.session_state.carrito_venta:
                            conn.execute(text("""
                                INSERT INTO detalle_ventas (
                                    id_venta, id_producto, formato_venta, 
                                    cantidad_formato, precio_unitario_historico, descripcion
                                )
                                VALUES (:id_v, :id_p, :formato, :cant, :precio, :desc)
                            """), {
                                "id_v": id_v_new, 
                                "id_p": item['id_producto'], 
                                "formato": item['Formato'], 
                                "cant": item['Cantidad'], 
                                "precio": float(item['PrecioUnidad']),
                                "desc": descripcion_venta # <--- ACÁ SE GUARDA LO QUE ESCRIBISTE
                            })
                    
                    st.success(f"✅ ¡Venta N° {id_v_new} registrada! Margen: {margen_total:.1f}% (${total_venta_final - costo_total:,.2f})")
                    st.session_state.carrito_venta = []
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        if st.button("🗑️ Vaciar Pedido"):
            st.session_state.carrito_venta = []
            st.rerun()

    # Historial
    st.markdown("---")
    st.subheader("📜 Historial de Ventas")
    
    query_hist_v = text("""
        SELECT 
            v.id_venta AS "N°",
            v.nro_factura AS "Factura",
            TO_CHAR(v.fecha, 'DD/MM/YY HH24:MI') AS "Fecha",
            c.razon_social AS "Cliente",
            p.nombre || ' (' || m.nombre || ')' AS "Producto",
            dv.cantidad_formato || ' ' || dv.formato_venta AS "Cant.",
            dv.precio_unitario_historico AS "Precio Unit.",
            ROUND(dv.cantidad_formato * 
                CASE 
                    WHEN dv.formato_venta = 'Caja' 
                    THEN (dv.precio_unitario_historico * p.unidades_por_caja)
                    ELSE dv.precio_unitario_historico 
                END, 2
            ) AS "Subtotal"
        FROM ventas v
        JOIN clientes c ON v.id_cliente = c.id_cliente
        JOIN detalle_ventas dv ON v.id_venta = dv.id_venta
        JOIN productos p ON dv.id_producto = p.id_producto
        JOIN marcas m ON p.id_marca = m.id_marca
        ORDER BY v.fecha DESC
        LIMIT 100
    """)
    
    with engine.connect() as conn:
        df_hv = pd.read_sql(query_hist_v, conn)
    
    st.dataframe(
        df_hv,
        width='stretch',
        hide_index=True,
        column_config={
            "Precio Unit.": st.column_config.NumberColumn(format="$%.2f"),
            "Subtotal": st.column_config.NumberColumn(format="$%.2f")
        }
    )
    
    with st.expander("⚠️ Cancelar una Venta"):
        if len(df_hv) > 0:
            id_v_del = st.selectbox("Elegí el N° de Venta a borrar", options=df_hv["N°"].unique())
            if st.button("❌ Eliminar Venta", type="primary"):
                try:
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM detalle_ventas WHERE id_venta = :id"), {"id": int(id_v_del)})
                        conn.execute(text("DELETE FROM ventas WHERE id_venta = :id"), {"id": int(id_v_del)})
                    st.success(f"Venta N° {id_v_del} eliminada y stock recompuesto.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"No se pudo borrar: {e}")
        else:
            st.info("No hay ventas para cancelar")
            

# ESTA PARTE VA DESPUÉS DEL TAB 2 EN TU APP PRINCIPAL
# Copiá desde acá y pegalo reemplazando el tab3 en adelante

# ==========================================================
# TAB 3: GESTIÓN DE STOCK Y PRECIOS
# ==========================================================
with tab3:
    st.title("📦 Gestión de Stock y Precios")

    # Inicialización de conexión y carga de datos básicos para los selectores
    with engine.connect() as conn:
        provs = pd.read_sql(text("SELECT id_proveedor, nombre FROM proveedores ORDER BY nombre"), conn)
        prods_all = pd.read_sql(text("SELECT id_producto, nombre FROM productos ORDER BY nombre"), conn)

    # ----------------------------------------------------------------------
    # SECCIÓN 1: INGRESO DE MERCADERÍA (COMPRAS) - "Lo de siempre"
    # ----------------------------------------------------------------------
    st.subheader("🚚 Ingreso de Mercadería por Lote")

    with st.expander("➕ Agregar producto al pedido", expanded=True):
        col_p2, col_c2, col_pre = st.columns(3)
        
        prod_sel = col_p2.selectbox(
            "Producto", 
            options=prods_all['id_producto'].tolist(), 
            format_func=lambda x: prods_all[prods_all['id_producto']==x]['nombre'].values[0], 
            key="sel_prod_c"
        )
        
        cant_c = col_c2.number_input("Cantidad Unidades", min_value=1, step=1, key="cant_prod_c")
        precio_c = col_pre.number_input("Costo Unitario Neto ($)", min_value=0.0, step=0.1, key="pre_prod_c")
        
        # CORRECCIÓN IMPORTANTE: Sacamos el st.rerun() de acá para que no salte la página
        if st.button("🛒 Agregar al listado"):
            nombre_p = prods_all[prods_all['id_producto'] == prod_sel]['nombre'].values[0]
            st.session_state.carrito_compra.append({
                "id_producto": prod_sel,
                "Producto": nombre_p,
                "Cantidad": cant_c,
                "Costo Neto": precio_c,
                "Subtotal": cant_c * precio_c
            })
            # Sin st.rerun(), el script sigue y muestra el carrito actualizado abajo

    if st.session_state.carrito_compra:
        st.info("📋 Detalle del Pedido Actual")
        df_carrito = pd.DataFrame(st.session_state.carrito_compra)
        st.dataframe(
            df_carrito[["Producto", "Cantidad", "Costo Neto", "Subtotal"]],
            hide_index=True,
            width='stretch',
            column_config={
                "Costo Neto": st.column_config.NumberColumn(format="$%.2f"),
                "Subtotal": st.column_config.NumberColumn(format="$%.2f")
            }
        )
        
        total_neto = df_carrito["Subtotal"].sum()
        st.write(f"**Total Neto de Mercadería: ${total_neto:,.2f}**")

        with st.form("form_finalizar_compra"):
            col_f, col_pr, col_fl = st.columns(3)
            nro_fac = col_f.text_input("N° Factura / Remito")
            prov_sel = col_pr.selectbox(
                "Proveedor", 
                options=provs['id_proveedor'].tolist(), 
                format_func=lambda x: provs[provs['id_proveedor']==x]['nombre'].values[0]
            )
            flete_total = col_fl.number_input("Flete Total de la Factura ($)", min_value=0.0)
            
            if st.form_submit_button("💾 Guardar Compra Completa", width='stretch'):
                try:
                    total_final = float(total_neto + flete_total)
                    with engine.begin() as conn:
                        # 1. Guardar Cabecera Compra
                        res = conn.execute(text("""
                            INSERT INTO compras (id_proveedor, total_compra, costo_flete, nro_factura) 
                            VALUES (:id_p, :total, :flete, :fac) RETURNING id_compra
                        """), {"id_p": prov_sel, "total": total_final, "flete": float(flete_total), "fac": nro_fac})
                        id_compra_new = res.fetchone()[0]
                        
                        # 2. Guardar Detalles
                        for item in st.session_state.carrito_compra:
                            conn.execute(text("""
                                INSERT INTO detalle_compras (id_compra, id_producto, cantidad_unidades, precio_compra_neto)
                                VALUES (:id_c, :id_p, :cant, :precio)
                            """), {
                                "id_c": id_compra_new, 
                                "id_p": item['id_producto'], 
                                "cant": item['Cantidad'], 
                                "precio": float(item['Costo Neto'])
                            })
                    
                    st.success(f"✅ ¡Compra N° {id_compra_new} guardada con éxito!")
                    st.session_state.carrito_compra = []
                    st.cache_data.clear()
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al guardar: {e}")
        
        if st.button("🗑️ Vaciar Carrito"):
            st.session_state.carrito_compra = []
            st.rerun()

    st.markdown("---")

    # ----------------------------------------------------------------------
    # SECCIÓN 2: ACTUALIZADOR DE PRECIOS (Lo Nuevo)
    # ----------------------------------------------------------------------
    with st.expander("💲 Actualizar Precio de Venta", expanded=False):
        st.caption("Seleccioná un producto para modificar su precio de venta al público.")
        
        with engine.connect() as conn:
            # CORRECCIÓN APLICADA: JOIN con marcas para evitar el error de columna
            query_selector = text("""
                SELECT 
                    p.id_producto, 
                    p.nombre, 
                    m.nombre as marca, 
                    p.precio_venta 
                FROM productos p
                JOIN marcas m ON p.id_marca = m.id_marca
                ORDER BY p.nombre
            """)
            df_prod_precios = pd.read_sql(query_selector, conn)
        
        c_p1, c_p2, c_p3 = st.columns([3, 2, 2])
        
        # 1. Selector buscador
        prod_a_cambiar = c_p1.selectbox(
            "Buscar Producto a Actualizar", 
            df_prod_precios['id_producto'].tolist(),
            format_func=lambda x: f"{df_prod_precios[df_prod_precios['id_producto']==x]['nombre'].values[0]} ({df_prod_precios[df_prod_precios['id_producto']==x]['marca'].values[0]})",
            key="sel_update_price"
        )
        
        # Datos del seleccionado
        datos_prod = df_prod_precios[df_prod_precios['id_producto'] == prod_a_cambiar].iloc[0]
        precio_viejo = float(datos_prod['precio_venta'])
        
        # 2. Precio Actual Visual
        c_p2.metric("Precio Actual", f"${precio_viejo:,.2f}")
        
        # 3. Nuevo Precio
        nuevo_precio = c_p3.number_input("Nuevo Precio", min_value=0.0, value=precio_viejo, step=50.0, key="input_new_price")
        
        if st.button("💾 Actualizar Precio", width='stretch', key="btn_save_price"):
            if nuevo_precio != precio_viejo:
                try:
                    with engine.begin() as conn:
                        # A. Actualizar Producto
                        conn.execute(text("UPDATE productos SET precio_venta = :np WHERE id_producto = :idp"), 
                                   {"np": nuevo_precio, "idp": prod_a_cambiar})
                        
                        # B. Guardar Historial (Bitácora)
                        conn.execute(text("""
                            INSERT INTO historial_precios (id_producto, precio_anterior, precio_nuevo)
                            VALUES (:idp, :pv, :pn)
                        """), {"idp": prod_a_cambiar, "pv": precio_viejo, "pn": nuevo_precio})
                        
                    st.success(f"✅ ¡Hecho! {datos_prod['nombre']} pasó de ${precio_viejo:,.2f} a ${nuevo_precio:,.2f}")
                    time.sleep(0.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("El precio nuevo es igual al actual. Modificalo primero.")

    st.markdown("---")

    # ----------------------------------------------------------------------
    # SECCIÓN 3: HISTORIAL DE INGRESOS (Lo de abajo de todo)
    # ----------------------------------------------------------------------
    st.subheader("🚛 Historial de Ingresos")
    
    query_hist_c = text("""
        SELECT 
            comp.id_compra AS "N°",
            comp.nro_factura AS "Factura", 
            TO_CHAR(comp.fecha, 'DD/MM/YY') AS "Fecha",
            prov.nombre AS "Proveedor", 
            prod.nombre AS "Producto",
            dc.cantidad_unidades AS "Unid.",
            dc.precio_compra_neto AS "Costo Lista",
            ROUND(dc.precio_compra_neto * (1 + (comp.costo_flete / NULLIF(comp.total_compra - comp.costo_flete, 0))), 2) AS "Costo Real",
            (dc.cantidad_unidades * dc.precio_compra_neto) AS "Subtotal Neto",
            comp.costo_flete AS "Flete Total"
        FROM compras comp
        JOIN proveedores prov ON comp.id_proveedor = prov.id_proveedor
        JOIN detalle_compras dc ON comp.id_compra = dc.id_compra
        JOIN productos prod ON dc.id_producto = prod.id_producto
        ORDER BY comp.id_compra DESC
        LIMIT 100
    """)
    
    with engine.connect() as conn:
        df_hc = pd.read_sql(query_hist_c, conn)
    
    st.dataframe(
        df_hc,
        width='stretch',
        hide_index=True,
        column_config={
            "Costo Lista": st.column_config.NumberColumn(format="$%.2f"),
            "Costo Real": st.column_config.NumberColumn(format="$%.2f"),
            "Subtotal Neto": st.column_config.NumberColumn(format="$%.2f"),
            "Flete Total": st.column_config.NumberColumn(format="$%.2f")
        }
    )
    
    with st.expander("⚠️ Cancelar un Ingreso de Stock"):
        if len(df_hc) > 0:
            id_c_del = st.selectbox("Elegí el N° de Compra a borrar", options=df_hc["N°"].unique())
            if st.button("🗑️ Eliminar Compra", type="primary"):
                try:
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM detalle_compras WHERE id_compra = :id"), {"id": int(id_c_del)})
                        conn.execute(text("DELETE FROM compras WHERE id_compra = :id"), {"id": int(id_c_del)})
                    st.success(f"Compra N° {id_c_del} eliminada. Stock ajustado.")
                    st.cache_data.clear()
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.info("No hay compras para cancelar")


# ==========================================================
# TAB 4: GESTIÓN DE CONCESIONES
# ==========================================================
with tab4:
    st.title("🤝 Gestión de Mercadería en Consignación")

    # --- KPIs DE LA CALLE ---
    query_kpi_concesion = text("""
        SELECT 
            COALESCE(SUM(stock_concesion), 0) as unidades_calle,
            COALESCE(SUM(stock_concesion * precio_costo_promedio), 0) as capital_riesgo,
            COALESCE(SUM(stock_concesion * precio_venta), 0) as venta_potencial
        FROM productos
    """)
    
    with engine.connect() as conn:
        kpis_c = conn.execute(query_kpi_concesion).fetchone()
    
    col_k1, col_k2, col_k3 = st.columns(3)
    col_k1.metric("📦 Unidades en la Calle", f"{kpis_c[0]:,.0f}")
    col_k2.metric("💸 Capital en Riesgo (Costo)", f"${kpis_c[1]:,.2f}", help="Plata tuya invertida que está en locales de otros.")
    col_k3.metric("💰 Venta Potencial", f"${kpis_c[2]:,.2f}", help="Lo que cobrarías si vendés todo hoy.")
    
    st.markdown("---")

    # --- SECCIÓN 1: NUEVA ENTREGA ---
    with st.expander("🚚 Nueva Entrega en Concesión", expanded=False):
        
        with engine.connect() as conn:
            # Traemos clientes y productos
            cli_conc = pd.read_sql(text("SELECT id_cliente, razon_social FROM clientes ORDER BY razon_social"), conn)
            # Solo traemos productos que tengan stock físico > 0
            prod_conc = pd.read_sql(text("""
                SELECT id_producto, nombre, stock_actual 
                FROM productos 
                WHERE stock_actual > 0 
                ORDER BY nombre
            """), conn)

        c1, c2, c3 = st.columns([2, 2, 1])
        
        # Selectores
        prod_sel_c = c1.selectbox("Producto a entregar", prod_conc['id_producto'].tolist(), 
                                format_func=lambda x: f"{prod_conc[prod_conc['id_producto']==x]['nombre'].values[0]} (Stock: {prod_conc[prod_conc['id_producto']==x]['stock_actual'].values[0]})",
                                key="p_conc")
        
        # Validamos stock disponible para el input
        stock_disp = prod_conc[prod_conc['id_producto']==prod_sel_c]['stock_actual'].values[0] if not prod_conc.empty else 0
        
        cant_c = c2.number_input("Cantidad a dejar", min_value=1, max_value=int(stock_disp) if stock_disp > 0 else 1, step=1, key="cant_conc")
        
        if c3.button("➕ Agregar", width='stretch'):
            nombre_p = prod_conc[prod_conc['id_producto'] == prod_sel_c]['nombre'].values[0]
            st.session_state.carrito_concesion.append({
                "id": prod_sel_c,
                "nombre": nombre_p,
                "cantidad": cant_c
            })
            

        # Visualizar Carrito Concesión
        if st.session_state.carrito_concesion:
            st.info("🛒 Lista para entregar:")
            df_curr_conc = pd.DataFrame(st.session_state.carrito_concesion)
            st.dataframe(df_curr_conc, width='stretch', hide_index=True)
            
            col_confirm_1, col_confirm_2 = st.columns(2)
            cliente_final = col_confirm_1.selectbox("Cliente / Local", cli_conc['id_cliente'].tolist(), 
                                                  format_func=lambda x: cli_conc[cli_conc['id_cliente']==x]['razon_social'].values[0])
            
            if col_confirm_2.button("🚀 Confirmar Entrega", type="primary", width='stretch'):
                try:
                    with engine.begin() as conn:
                        # 1. Crear Cabecera
                        res = conn.execute(text("INSERT INTO concesiones (id_cliente) VALUES (:id_c) RETURNING id_concesion"), {"id_c": cliente_final})
                        id_new_conc = res.fetchone()[0]
                        
                        # 2. Insertar Detalles (El trigger moverá el stock solo)
                        for item in st.session_state.carrito_concesion:
                            conn.execute(text("""
                                INSERT INTO detalle_concesiones (id_concesion, id_producto, cantidad)
                                VALUES (:id_con, :id_prod, :cant)
                            """), {"id_con": id_new_conc, "id_prod": item['id'], "cant": item['cantidad']})
                    
                    st.success(f"✅ ¡Concesión N° {id_new_conc} registrada! El stock se movió a 'En Concesión'.")
                    st.session_state.carrito_concesion = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    st.markdown("---")

    # --- SECCIÓN 2: SEMÁFORO DE CONTROL ---
    st.subheader("📋 Estado de Mercadería en Locales")
    
    # Query inteligente con cálculo de días
    query_estado_conc = text("""
        SELECT 
            c.razon_social AS "Local",
            p.nombre AS "Producto",
            dc.cantidad AS "Unidades",
            TO_CHAR(conc.fecha, 'DD/MM/YY') AS "Fecha Entrega",
            EXTRACT(DAY FROM NOW() - conc.fecha)::int AS "Días Pasados",
            CASE 
                WHEN EXTRACT(DAY FROM NOW() - conc.fecha) <= 15 THEN '🟢 Reciente'
                WHEN EXTRACT(DAY FROM NOW() - conc.fecha) <= 30 THEN '🟡 Atención'
                ELSE '🔴 Vencido'
            END AS "Estado"
        FROM detalle_concesiones dc
        JOIN concesiones conc ON dc.id_concesion = conc.id_concesion
        JOIN productos p ON dc.id_producto = p.id_producto
        JOIN clientes c ON conc.id_cliente = c.id_cliente
        WHERE conc.estado = 'ACTIVA'
        ORDER BY "Días Pasados" DESC
    """)
    
    with engine.connect() as conn:
        df_estado = pd.read_sql(query_estado_conc, conn)
    
    if not df_estado.empty:
        # Filtros rápidos
        filtro_local = st.multiselect("Filtrar por Local", df_estado["Local"].unique())
        if filtro_local:
            df_estado = df_estado[df_estado["Local"].isin(filtro_local)]

        st.dataframe(
            df_estado,
            width='stretch',
            hide_index=True,
            column_config={
                "Unidades": st.column_config.NumberColumn(format="%d"),
                "Días Pasados": st.column_config.NumberColumn(format="%d días"),
                "Estado": st.column_config.TextColumn(width="medium")
            }
        )
    else:
        st.info("No hay mercadería pendiente en concesión.")


    st.markdown("---")
    st.header("🔄 Procesar Concesión (Liquidar o Devolver)")

    # 1. Seleccionar Cliente con Deuda
    with engine.connect() as conn:
        # Buscamos clientes que tengan cosas activas en la tabla detalle_concesiones
        clientes_con_deuda = pd.read_sql(text("""
            SELECT DISTINCT c.id_cliente, c.razon_social 
            FROM concesiones conc
            JOIN clientes c ON conc.id_cliente = c.id_cliente
            WHERE conc.estado = 'ACTIVA'
        """), conn)

    if not clientes_con_deuda.empty:
        cli_proc = st.selectbox("Seleccionar Local para gestionar", 
                              clientes_con_deuda['id_cliente'].tolist(),
                              format_func=lambda x: clientes_con_deuda[clientes_con_deuda['id_cliente']==x]['razon_social'].values[0])
        
        # 2. Ver qué tiene ese cliente
        if cli_proc:
            query_items_cli = text("""
                SELECT 
                    dc.id_detalle,
                    p.id_producto,
                    p.nombre,
                    dc.cantidad as entregado,
                    p.precio_venta,
                    p.unidades_por_caja
                FROM detalle_concesiones dc
                JOIN concesiones c ON dc.id_concesion = c.id_concesion
                JOIN productos p ON dc.id_producto = p.id_producto
                WHERE c.id_cliente = :idc AND c.estado = 'ACTIVA'
            """)
            with engine.connect() as conn:
                items_cli = pd.read_sql(query_items_cli, conn, params={"idc": cli_proc})
            
            if not items_cli.empty:
                st.info(f"Artículos pendientes en: {clientes_con_deuda[clientes_con_deuda['id_cliente']==cli_proc]['razon_social'].values[0]}")
                
                # Iteramos por cada producto que tiene el cliente
                for index, row in items_cli.iterrows():
                    with st.container():
                        # Agrandamos un cachito las columnas para que entre el precio
                        c_prod, c_accion, c_cant, c_precio, c_boton = st.columns([2.5, 2, 1.2, 1.5, 1.5])
                        
                        # Nombre del producto
                        c_prod.markdown(f"**{row['nombre']}**\n\n<small>Stock allá: {row['entregado']}</small>", unsafe_allow_html=True)
                        
                        # Radio Button (Vender vs Devolver)
                        accion = c_accion.radio(
                            "Acción", 
                            ["💰 COBRAR", "🔙 DEVOLVER"], 
                            key=f"act_{row['id_detalle']}", 
                            label_visibility="collapsed"
                        )
                        
                        # Input de Cantidad
                        cant_gest = c_cant.number_input(
                            "Cant.", 
                            min_value=1, 
                            max_value=row['entregado'], 
                            step=1, 
                            key=f"cant_{row['id_detalle']}"
                        )

                        # --- CAMBIO CLAVE: Input de Precio (Editable) ---
                        # Por defecto trae el precio de lista (row['precio_venta']), pero lo podés tocar.
                        precio_final = c_precio.number_input(
                            "Precio $",
                            min_value=0.0,
                            value=float(row['precio_venta']),
                            step=50.0,
                            key=f"precio_{row['id_detalle']}"
                        )
                        
                        # Botón Aplicar
                        if c_boton.button("Aplicar", key=f"btn_{row['id_detalle']}", width='stretch'):
                            try:
                                with engine.begin() as conn:
                                    # CASO A: VENTA (El cliente vendió y paga)
                                    if "COBRAR" in accion:
                                        # 1. Crear Venta Oficial
                                        # ACÁ USAMOS EL PRECIO EDITADO (precio_final)
                                        total_operacion = float(cant_gest * precio_final)
                                        
                                        res = conn.execute(text("INSERT INTO ventas (id_cliente, total_venta, nro_factura) VALUES (:idc, :tot, 'CONCESION') RETURNING id_venta"), 
                                                         {"idc": cli_proc, "tot": total_operacion})
                                        id_v_new = res.fetchone()[0]
                                        
                                        # 2. Insertar Detalle con FLAG es_concesion = TRUE
                                        # ACÁ TAMBIÉN USAMOS EL PRECIO EDITADO
                                        conn.execute(text("""
                                            INSERT INTO detalle_ventas (id_venta, id_producto, formato_venta, cantidad_formato, precio_unitario_historico, es_concesion)
                                            VALUES (:idv, :idp, 'Unidad', :cant, :precio, desc, TRUE)
                                        """), {
                                            "idv": id_v_new,
                                            "idp": row['id_producto'],
                                            "cant": cant_gest,
                                            "precio": precio_final,
                                            "desc": descripcion_venta# <--- Usamos el manual
                                        })
                                        msg = f"✅ ¡Cobrado! {cant_gest} un. a ${precio_final:,.2f} c/u. Total: ${total_operacion:,.2f}"

                                    # CASO B: DEVOLUCIÓN (El cliente te devuelve la mercadería)
                                    else:
                                        # Devolvemos stock: Resta de Concesión, Suma a Físico
                                        conn.execute(text("""
                                            UPDATE productos 
                                            SET stock_concesion = stock_concesion - :cant,
                                                stock_actual = stock_actual + :cant
                                            WHERE id_producto = :idp
                                        """), {"cant": cant_gest, "idp": row['id_producto']})
                                        
                                        # Auditoría manual
                                        conn.execute(text("""
                                            INSERT INTO inventario_movimientos (id_producto, tipo, cantidad, fecha)
                                            VALUES (:idp, 'DEVOLUCION_CONCESION', :cant, NOW())
                                        """), {"idp": row['id_producto'], "cant": cant_gest})
                                        msg = f"🔙 ¡Retornado! {cant_gest} unidades volvieron al galpón."

                                    # FINAL COMÚN: Actualizar tabla de concesiones
                                    if cant_gest == row['entregado']:
                                        conn.execute(text("DELETE FROM detalle_concesiones WHERE id_detalle = :idd"), {"idd": row['id_detalle']})
                                    else:
                                        conn.execute(text("UPDATE detalle_concesiones SET cantidad = cantidad - :cant WHERE id_detalle = :idd"), 
                                                   {"cant": cant_gest, "idd": row['id_detalle']})
                                    
                                    # Limpieza de cabeceras vacías
                                    conn.execute(text("DELETE FROM concesiones WHERE id_concesion NOT IN (SELECT DISTINCT id_concesion FROM detalle_concesiones)"))
                                
                                st.success(msg)
                                time.sleep(0.5) # Un segundito para leer el mensaje
                                st.rerun()
                                
                            except Exception as e:
                                st.error(f"Error al procesar: {e}")
                        
                        st.divider()
            else:
                st.warning("Este cliente no tiene productos cargados actualmente.")
    else:
        st.success("¡Todo al día! No hay concesiones activas pendientes.")






# ==========================================================
# TAB 5: ANÁLISIS Y REPORTES
# ==========================================================
with tab5:
    st.title("📈 Análisis y Reportes")
    
    # Selector de período
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        dias_analisis = st.selectbox("Período de análisis", [7, 30, 60, 90, 180, 365], index=1)
    with col_p2:
        st.metric("Analizando últimos", f"{dias_analisis} días")
    
    st.markdown("---")
    
    # 1. RENTABILIDAD POR PRODUCTO
    st.subheader("💰 Rentabilidad por Producto")
    
    query_rentabilidad = text("""
    WITH VentasPeriodo AS (
        SELECT 
            dv.id_producto,
            SUM(dv.cantidad_formato) as unidades_vendidas,
            SUM(dv.cantidad_formato * dv.precio_unitario_historico) as ingresos,
            SUM(dv.cantidad_formato * p.precio_costo_promedio) as costos
        FROM detalle_ventas dv
        JOIN ventas v ON dv.id_venta = v.id_venta
        JOIN productos p ON dv.id_producto = p.id_producto
        WHERE v.fecha >= CURRENT_DATE - INTERVAL ':dias days'
        GROUP BY dv.id_producto
    )
    SELECT 
        p.nombre AS "Producto",
        m.nombre AS "Marca",
        vp.unidades_vendidas AS "Unidades",
        vp.ingresos AS "Ingresos",
        vp.costos AS "Costos",
        (vp.ingresos - vp.costos) AS "Ganancia",
        ROUND(((vp.ingresos - vp.costos) / NULLIF(vp.ingresos, 0) * 100), 1) AS "Margen %",
        ROUND((vp.ingresos - vp.costos) / NULLIF(vp.unidades_vendidas, 0), 2) AS "Ganancia/Unidad"
    FROM VentasPeriodo vp
    JOIN productos p ON vp.id_producto = p.id_producto
    JOIN marcas m ON p.id_marca = m.id_marca
    WHERE vp.unidades_vendidas > 0
    ORDER BY "Ganancia" DESC
""")

    
    with engine.connect() as conn:
        df_rent = pd.read_sql(query_rentabilidad.bindparams(dias=dias_analisis), conn)
    
    if len(df_rent) > 0:
        # Métricas resumen
        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        
        total_ingresos = df_rent['Ingresos'].sum()
        total_costos = df_rent['Costos'].sum()
        total_ganancia = df_rent['Ganancia'].sum()
        margen_promedio = (total_ganancia / total_ingresos * 100) if total_ingresos > 0 else 0
        
        col_r1.metric("Ingresos Totales", f"${total_ingresos:,.0f}")
        col_r2.metric("Costos Totales", f"${total_costos:,.0f}")
        col_r3.metric("Ganancia Neta", f"${total_ganancia:,.0f}")
        col_r4.metric("Margen Promedio", f"{margen_promedio:.1f}%")
        
        # Gráficos
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            # Top productos por ganancia
            df_top_ganancia = df_rent.nlargest(10, 'Ganancia')
            fig_ganancia = px.bar(
                df_top_ganancia,
                x='Producto',
                y='Ganancia',
                color='Margen %',
                title="🏆 Top 10 Productos por Ganancia",
                template="plotly_white",
                color_continuous_scale='RdYlGn'
            )
            fig_ganancia.update_layout(height=400)
            st.plotly_chart(fig_ganancia, width='stretch')
        
        with col_g2:
            # Productos con pérdida o bajo margen
            df_problema = df_rent[df_rent['Margen %'] < 15].sort_values('Ganancia')
            if len(df_problema) > 0:
                fig_problema = px.bar(
                    df_problema.head(10),
                    x='Producto',
                    y='Margen %',
                    title="⚠️ Productos con Margen < 15%",
                    template="plotly_white",
                    color='Margen %',
                    color_continuous_scale='RdYlGn'
                )
                fig_problema.update_layout(height=400)
                st.plotly_chart(fig_problema, width='stretch')
            else:
                st.success("✅ Todos los productos tienen buen margen!")
        
        # Tabla detallada
        st.dataframe(
            df_rent,
            width='stretch',
            hide_index=True,
            column_config={
                "Ingresos": st.column_config.NumberColumn(format="$%.0f"),
                "Costos": st.column_config.NumberColumn(format="$%.0f"),
                "Ganancia": st.column_config.NumberColumn(format="$%.0f"),
                "Margen %": st.column_config.NumberColumn(format="%.1f%%"),
                "Ganancia/Unidad": st.column_config.NumberColumn(format="$%.2f")
            }
        )
    else:
        st.info(f"No hay ventas en los últimos {dias_analisis} días para analizar.")
    
    st.markdown("---")
    
    # 2. EVOLUCIÓN DE VENTAS
    st.subheader("📊 Evolución de Ventas")
    
    query_evolucion = text("""
        SELECT 
            DATE_TRUNC('day', v.fecha) AS fecha,
            SUM(v.total_venta) as ventas_dia,
            COUNT(DISTINCT v.id_venta) as num_ventas
        FROM ventas v
        WHERE v.fecha >= CURRENT_DATE - INTERVAL ':dias days'
        GROUP BY DATE_TRUNC('day', v.fecha)
        ORDER BY fecha
    """)
    
    with engine.connect() as conn:
        df_evol = pd.read_sql(query_evolucion.bindparams(dias=dias_analisis), conn)
    
    if len(df_evol) > 0:
        fig_evol = go.Figure()
        
        fig_evol.add_trace(go.Scatter(
            x=df_evol['fecha'],
            y=df_evol['ventas_dia'],
            mode='lines+markers',
            name='Ventas',
            line=dict(color='#2E86AB', width=3),
            fill='tozeroy'
        ))
        
        fig_evol.update_layout(
            title="Ventas Diarias",
            xaxis_title="Fecha",
            yaxis_title="Ventas ($)",
            template="plotly_white",
            height=400
        )
        
        st.plotly_chart(fig_evol, width='stretch')
        
        # Métricas de tendencia
        col_t1, col_t2, col_t3 = st.columns(3)
        
        promedio_dia = df_evol['ventas_dia'].mean()
        mejor_dia = df_evol.loc[df_evol['ventas_dia'].idxmax()]
        total_ventas_periodo = df_evol['num_ventas'].sum()
        
        col_t1.metric("Promedio Diario", f"${promedio_dia:,.0f}")
        col_t2.metric("Mejor Día", f"${mejor_dia['ventas_dia']:,.0f}", delta=mejor_dia['fecha'].strftime('%d/%m'))
        col_t3.metric("Total Operaciones", f"{int(total_ventas_periodo)}")
    
    st.markdown("---")
    
    # 3. ANÁLISIS POR MARCA
    st.subheader("🏷️ Rendimiento por Marca")
    
    query_marcas = text("""
        SELECT 
            m.nombre AS "Marca",
            COUNT(DISTINCT p.id_producto) AS "Productos",
            SUM(dv.cantidad_formato) AS "Unidades Vendidas",
            SUM(dv.cantidad_formato * dv.precio_unitario_historico) AS "Ingresos"
        FROM detalle_ventas dv
        JOIN ventas v ON dv.id_venta = v.id_venta
        JOIN productos p ON dv.id_producto = p.id_producto
        JOIN marcas m ON p.id_marca = m.id_marca
        WHERE v.fecha >= CURRENT_DATE - INTERVAL ':dias days'
        GROUP BY m.nombre
        ORDER BY "Ingresos" DESC
    """)
    
    with engine.connect() as conn:
        df_marcas = pd.read_sql(query_marcas.bindparams(dias=dias_analisis), conn)
    
    if len(df_marcas) > 0:
        col_m1, col_m2 = st.columns(2)
        
        with col_m1:
            fig_marcas = px.pie(
                df_marcas,
                values='Ingresos',
                names='Marca',
                title='Distribución de Ingresos por Marca',
                template='plotly_white'
            )
            st.plotly_chart(fig_marcas, width='stretch')
        
        with col_m2:
            st.dataframe(
                df_marcas,
                width='stretch',
                hide_index=True,
                column_config={
                    "Ingresos": st.column_config.NumberColumn(format="$%.0f")
                }
            )
    st.markdown("---")
    st.subheader("💱 Variación de Costos")  

    st.info("📊 Comparación entre el costo promedio histórico y el precio de la última compra") 

    query_variacion = text("""
        SELECT * FROM v_comparacion_costos
        WHERE stock_actual > 0
        LIMIT 50
    """)    

    with engine.connect() as conn:
        df_var = pd.read_sql(query_variacion, conn) 

    if len(df_var) > 0:
        # Resaltar productos con alta variación
        df_alta_var = df_var[abs(df_var['variacion_porcentual']) > 10]
        
        if len(df_alta_var) > 0:
            st.warning(f"⚠️ {len(df_alta_var)} productos con variación de costo > 10%")
            
            col_v1, col_v2 = st.columns(2)
            
            with col_v1:
                # Productos que subieron mucho
                df_subidas = df_alta_var[df_alta_var['variacion_porcentual'] > 10].nlargest(10, 'variacion_porcentual')
                if len(df_subidas) > 0:
                    st.markdown("**📈 Mayores Subidas de Costo:**")
                    st.dataframe(
                        df_subidas[['nombre', 'costo_promedio', 'costo_ultima_compra', 'variacion_porcentual']],
                        hide_index=True,
                        width='stretch',
                        column_config={
                            "nombre": "Producto",
                            "costo_promedio": st.column_config.NumberColumn("Costo Promedio", format="$%.2f"),
                            "costo_ultima_compra": st.column_config.NumberColumn("Última Compra", format="$%.2f"),
                            "variacion_porcentual": st.column_config.NumberColumn("Variación", format="%.1f%%")
                        }
                    )
            
            with col_v2:
                # Productos que bajaron mucho
                df_bajadas = df_alta_var[df_alta_var['variacion_porcentual'] < -10].nsmallest(10, 'variacion_porcentual')
                if len(df_bajadas) > 0:
                    st.markdown("**📉 Mayores Bajadas de Costo:**")
                    st.dataframe(
                        df_bajadas[['nombre', 'costo_promedio', 'costo_ultima_compra', 'variacion_porcentual']],
                        hide_index=True,
                        width='stretch',
                        column_config={
                            "nombre": "Producto",
                            "costo_promedio": st.column_config.NumberColumn("Costo Promedio", format="$%.2f"),
                            "costo_ultima_compra": st.column_config.NumberColumn("Última Compra", format="$%.2f"),
                            "variacion_porcentual": st.column_config.NumberColumn("Variación", format="%.1f%%")
                        }
                    )
        else:
            st.success("✅ Los costos se mantienen estables")
        
        # Tabla completa
        with st.expander("Ver comparación completa"):
            st.dataframe(
                df_var,
                hide_index=True,
                width='stretch',
                column_config={
                    "costo_promedio": st.column_config.NumberColumn(format="$%.2f"),
                    "costo_ultima_compra": st.column_config.NumberColumn(format="$%.2f"),
                    "diferencia": st.column_config.NumberColumn(format="$%.2f"),
                    "variacion_porcentual": st.column_config.NumberColumn(format="%.1f%%")
                }
            )
# ==========================================================
# TAB 6: AUDITORÍA
# ==========================================================
with tab6:
    st.title("🔍 Auditoría de Movimientos")
    
    st.info("💡 Esta sección te muestra todos los movimientos de stock registrados automáticamente por el sistema.")
    
    # Filtros
    col_f1, col_f2 = st.columns(2)
    
    with col_f1:
        dias_auditoria = st.selectbox("Mostrar últimos", [7, 15, 30, 60, 90], index=2, key="dias_audit")
    
    # Query de auditoría (Lista general)
    query_audit = text("""
        SELECT 
            im.id_movimiento AS "N° Mov",
            TO_CHAR(im.fecha, 'DD/MM/YY HH24:MI') AS "Fecha/Hora",
            p.nombre AS "Producto",
            m.nombre AS "Marca",
            im.tipo AS "Tipo",
            im.cantidad AS "Cantidad",
            p.stock_actual AS "Stock Actual"
        FROM inventario_movimientos im
        JOIN productos p ON im.id_producto = p.id_producto
        JOIN marcas m ON p.id_marca = m.id_marca
        WHERE im.fecha >= CURRENT_DATE - INTERVAL ':dias days'
        ORDER BY im.fecha DESC
        LIMIT 500
    """)
    
    with engine.connect() as conn:
        df_audit = pd.read_sql(query_audit.bindparams(dias=dias_auditoria), conn)
    
    if len(df_audit) > 0:
        # Filtro por tipo
        with col_f2:
            tipos_disponibles = ['Todos'] + df_audit['Tipo'].unique().tolist()
            tipo_filtro = st.selectbox("Filtrar por tipo", tipos_disponibles)
        
        df_mostrar = df_audit if tipo_filtro == 'Todos' else df_audit[df_audit['Tipo'] == tipo_filtro]
        
        # Resumen numérico
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        
        compras = len(df_audit[df_audit['Tipo'] == 'COMPRA'])
        ventas = len(df_audit[df_audit['Tipo'] == 'VENTA'])
        cancelaciones = len(df_audit[df_audit['Tipo'].str.contains('CANCELACIÓN')])
        
        col_s1.metric("Total Movimientos", len(df_audit))
        col_s2.metric("Compras", compras)
        col_s3.metric("Ventas", ventas)
        col_s4.metric("Cancelaciones", cancelaciones)
        
        st.markdown("---")
        
        # Tabla de auditoría
        st.dataframe(
            df_mostrar,
            width='stretch',
            hide_index=True,
            column_config={
                "Cantidad": st.column_config.NumberColumn(format="%d")
            }
        )
        
        st.markdown("---")

        # ==============================================================================
        # ACÁ EMPIEZA EL GRÁFICO NUEVO (Reemplazamos el gráfico simple por el APILADO)
        # ==============================================================================
        st.subheader("🕵️ Análisis de Calidad de Movimientos")
        st.caption("Este gráfico desglosa si el movimiento es venta real (Verde) o logística de ida y vuelta (Amarillo/Naranja).")

        # 1. Consulta SQL Inteligente: Agrupa por Tipo y Producto
        query_audit_stack = text("""
            SELECT 
                p.nombre as "Producto",
                CASE 
                    WHEN im.tipo = 'VENTA' THEN 'Venta Directa'
                    WHEN im.tipo = 'VENTA_CONCESION' THEN 'Venta (Concesión)'
                    WHEN im.tipo = 'COMPRA' THEN 'Reposición (Compra)'
                    WHEN im.tipo = 'ENTREGA_CONCESION' THEN 'Entrega a Local'
                    WHEN im.tipo = 'DEVOLUCION_CONCESION' THEN 'Devolución de Local'
                    ELSE im.tipo 
                END as "Operación",
                SUM(ABS(im.cantidad)) as "Volumen"
            FROM inventario_movimientos im
            JOIN productos p ON im.id_producto = p.id_producto
            GROUP BY p.nombre, im.tipo
        """)
        
        with engine.connect() as conn:
            df_stack = pd.read_sql(query_audit_stack, conn)
        
        if not df_stack.empty:
            # 2. Filtro: Nos quedamos solo con los 10 productos que más se mueven en TOTAL
            ranking_productos = df_stack.groupby('Producto')['Volumen'].sum().nlargest(10).index
            df_final_stack = df_stack[df_stack['Producto'].isin(ranking_productos)]
            
            # 3. El Gráfico Revelador
            fig_audit = px.bar(
                df_final_stack, 
                x="Producto", 
                y="Volumen", 
                color="Operación",
                title="Top 10 Productos con Mayor Tráfico Logístico",
                text_auto=True,
                # Colores Semánticos
                color_discrete_map={
                    "Venta Directa": "#2ecc71",       # Verde Claro
                    "Venta (Concesión)": "#27ae60",   # Verde Oscuro
                    "Reposición (Compra)": "#3498db", # Azul
                    "Entrega a Local": "#f1c40f",     # Amarillo
                    "Devolución de Local": "#e67e22"  # Naranja
                }
            )
            
            fig_audit.update_layout(
                barmode='stack', 
                xaxis={'categoryorder':'total descending'}, 
                yaxis_title="Unidades Movidas (Absoluto)",
                legend_title_text="Tipo de Movimiento"
            )
            
            st.plotly_chart(fig_audit, width='stretch')
        else:
            st.info("Aún no hay suficientes datos para generar el gráfico de auditoría.")
        # ==============================================================================
        # FIN DEL GRÁFICO NUEVO
        # ==============================================================================
        
    else:
        st.warning(f"No hay movimientos registrados en los últimos {dias_auditoria} días.")
    
    # Sección de inconsistencias (CORREGIDA PARA CONCESIONES)
    st.markdown("---")
    st.subheader("⚠️ Verificación de Integridad")
    
    # Esta query ahora es más inteligente: suma todo movimiento positivo y resta negativo
    query_inconsistencias = text("""
        SELECT 
            p.nombre AS "Producto",
            p.stock_actual AS "Stock Actual",
            -- CORRECCIÓN: Excluimos 'VENTA_CONCESION' porque eso descuenta stock del cliente, no del galpón.
            COALESCE(SUM(CASE WHEN im.tipo != 'VENTA_CONCESION' THEN im.cantidad ELSE 0 END), 0) AS "Stock Calculado", 
            
            -- Desglose visual
            COALESCE(SUM(CASE WHEN im.tipo = 'COMPRA' THEN im.cantidad ELSE 0 END), 0) AS "Compras",
            COALESCE(SUM(CASE WHEN im.tipo = 'VENTA' THEN ABS(im.cantidad) ELSE 0 END), 0) AS "Ventas",
            -- Mostramos entregas netas (Entregas - Devoluciones) para que se entienda mejor
            COALESCE(SUM(CASE WHEN im.tipo = 'ENTREGA_CONCESION' THEN ABS(im.cantidad) ELSE 0 END), 0) 
            - COALESCE(SUM(CASE WHEN im.tipo = 'DEVOLUCION_CONCESION' THEN ABS(im.cantidad) ELSE 0 END), 0) AS "En Concesión (Neto)"
        FROM productos p
        LEFT JOIN inventario_movimientos im ON p.id_producto = im.id_producto
        GROUP BY p.id_producto, p.nombre, p.stock_actual
        HAVING COUNT(im.id_movimiento) > 0
    """)
    
    with engine.connect() as conn:
        df_verif = pd.read_sql(query_inconsistencias, conn)
    
    if len(df_verif) > 0:
        # El "Stock Calculado" viene de sumar (+Compras -Ventas -Concesiones) directo de la base
        df_verif['Diferencia'] = df_verif['Stock Actual'] - df_verif['Stock Calculado']
        
        # Mostrar solo si hay diferencias
        df_problemas = df_verif[df_verif['Diferencia'] != 0]
        
        if len(df_problemas) > 0:
            st.error(f"⚠️ Se encontraron {len(df_problemas)} inconsistencias graves")
            # Mostramos el desglose para que entiendas dónde está el lío
            st.dataframe(
                df_problemas[['Producto', 'Stock Actual', 'Stock Calculado', 'Diferencia', 'Compras', 'Ventas', 'En Concesión']],
                width='stretch',
                hide_index=True
            )
        else:
            st.success("✅ ¡Cierre Perfecto! El stock físico coincide con todos los movimientos (incluyendo concesiones).")
    else:
        st.info("No hay suficiente información para verificar integridad")
        
    # ==========================================================
# TAB 7: PANEL DE CONTROL Y ALTAS (PARA QUE CARGUEN ELLOS)
# ==========================================================
with tab7:
    # Cambiamos el título y la descripción
    st.header("📂 Carga de Datos y Maestros") 
    st.markdown("Desde acá podés dar de alta Marcas, Clientes, Proveedores y Productos.")

    # Dividimos en dos columnas para que quede prolijo
    col_izq, col_der = st.columns(2)

    # --- COLUMNA IZQUIERDA: Marcas y Proveedores ---
    with col_izq:
        st.subheader("1️⃣ Crear Marca")
        st.caption("Ej: Coca-Cola, Arcor, Villavicencio")
        with st.form("form_alta_marca", clear_on_submit=True):
            nueva_marca = st.text_input("Nombre de la Marca")
            if st.form_submit_button("💾 Guardar Marca"):
                if nueva_marca:
                    try:
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO marcas (nombre) VALUES (:n)"), {"n": nueva_marca})
                        st.success(f"✅ Marca '{nueva_marca}' creada.")
                        time.sleep(1) # Pequeña pausa para que se vea el mensaje
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                else:
                    st.warning("Escribí un nombre primero.")

        st.divider()

        st.subheader("2️⃣ Crear Proveedor")
        with st.form("form_alta_prov", clear_on_submit=True):
            nom_prov = st.text_input("Nombre del Proveedor")
            tel_prov = st.text_input("Teléfono / Contacto")
            email_prov = st.text_input("Email (Opcional)")
            if st.form_submit_button("💾 Guardar Proveedor"):
                if nom_prov:
                    try:
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO proveedores (nombre, telefono, email) VALUES (:n, :t, :e)"), 
                                       {"n": nom_prov, "t": tel_prov, "e": email_prov})
                        st.success(f"✅ Proveedor '{nom_prov}' guardado.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- COLUMNA DERECHA: Clientes y PRODUCTOS ---
    with col_der:
        st.subheader("3️⃣ Crear Cliente")
        with st.form("form_alta_cliente", clear_on_submit=True):
            razon_social = st.text_input("Nombre / Razón Social")
            domicilio = st.text_input("Dirección")
            telefono = st.text_input("Teléfono")
            if st.form_submit_button("💾 Guardar Cliente"):
                if razon_social:
                    try:
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO clientes (razon_social, direccion, telefono) VALUES (:r, :d, :t)"), 
                                       {"r": razon_social, "d": domicilio, "t": telefono})
                        st.success(f"✅ Cliente '{razon_social}' creado.")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        
    st.divider()

    # --- SECCIÓN ESPECIAL: PRODUCTOS (Ocupa todo el ancho) ---
    st.subheader("4️⃣ Crear PRODUCTO NUEVO")
    st.info("Para crear un producto, necesitás haber creado la MARCA primero.")
    
    # Traemos las marcas para el selector
    with engine.connect() as conn:
        df_marcas = pd.read_sql(text("SELECT id_marca, nombre FROM marcas ORDER BY nombre"), conn)
    
    if df_marcas.empty:
        st.warning("⚠️ No podés cargar productos porque no hay MARCAS cargadas. Creá una marca arriba a la izquierda.")
    else:
        # Sacamos el clear_on_submit para que no borre si hay error
        with st.form("form_alta_producto", clear_on_submit=False):
            col_a, col_b = st.columns(2)
            nombre_prod = col_a.text_input("Nombre del Producto (Ej: Coca Cola 1.5L)")
            
            # Selector de Marca
            id_marca_sel = col_b.selectbox("Marca", df_marcas['id_marca'].tolist(), 
                                         format_func=lambda x: df_marcas[df_marcas['id_marca']==x]['nombre'].values[0])
            
            col_c, col_d, col_e = st.columns(3)
            precio_vta = col_c.number_input("Precio de Venta Unitario ($)", min_value=0.0)
            costo_ref = col_d.number_input("Costo de Compra Unitario ($)", min_value=0.0)
            stock_ini = col_e.number_input("Stock Inicial (si ya tenés)", min_value=0, step=1)
            
            st.markdown("**Datos del Pack / Bulto**")
            # Dejamos sola la columna de unidades, sacamos el input de precio caja
            unid_caja = st.number_input("Unidades por Caja/Bulto", min_value=1, value=1)
            
            # Botón de envío
            enviado = st.form_submit_button("🚀 CREAR PRODUCTO")

            if enviado:
                if not nombre_prod:
                    st.error("⚠️ ¡Falta el nombre! Escribí algo antes de guardar.")
                
                elif precio_vta <= 0:
                    st.warning("⚠️ ¡Ojo! El precio está en $0. Poné un precio real.")
                
                else:
                    # --- CÁLCULO AUTOMÁTICO DEL PRECIO CAJA ---
                    # Multiplicamos el precio unitario por la cantidad que trae la caja
                    precio_caja_calculado = precio_vta * unid_caja

                    try:
                        with engine.begin() as conn:
                            # 1. Insertamos el producto (usamos la variable calculada)
                            conn.execute(text("""
                                INSERT INTO productos 
                                (nombre, id_marca, precio_venta, precio_costo_promedio, stock_actual, unidades_por_caja, precio_venta_caja)
                                VALUES (:nom, :m, :pv, :pc, :stk, :upc, :pvc)
                            """), {
                                "nom": nombre_prod, "m": id_marca_sel, "pv": precio_vta, 
                                "pc": costo_ref, "stk": stock_ini, "upc": unid_caja, 
                                "pvc": precio_caja_calculado  # <--- ACÁ VA EL CÁLCULO
                            })
                            
                            # 2. Movimiento inicial si hay stock
                            if stock_ini > 0:
                                id_new = conn.execute(text("SELECT MAX(id_producto) FROM productos")).fetchone()[0]
                                conn.execute(text("""
                                    INSERT INTO inventario_movimientos (id_producto, tipo, cantidad, fecha)
                                    VALUES (:id, 'STOCK_INICIAL', :cant, NOW())
                                """), {"id": id_new, "cant": stock_ini})

                        st.success(f"✅ Producto '{nombre_prod}' creado. (Precio Caja autocalculado: ${precio_caja_calculado:,.2f})")
                        time.sleep(1.5) # Un poquito más de tiempo para que lean el precio calculado
                        st.rerun()
                    except Exception as e:
                        st.error(f"Hubo un error al crear: {e}")