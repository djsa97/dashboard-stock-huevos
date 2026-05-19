from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
from pandas.errors import EmptyDataError

try:
    from stock_huevos_dashboard.core import (
        BUCKET_ORDER,
        CONFIG_OUTPUT,
        compute_stock_outputs,
        ENTRADAS_OUTPUT,
        INICIAL_OUTPUT,
        MOV_COLUMNS,
        MOVIMIENTOS_OUTPUT,
        RESUMEN_OUTPUT,
        SALIDAS_OUTPUT,
    )
except ModuleNotFoundError:
    from core import (  # type: ignore
        BUCKET_ORDER,
        CONFIG_OUTPUT,
        compute_stock_outputs,
        ENTRADAS_OUTPUT,
        INICIAL_OUTPUT,
        MOV_COLUMNS,
        MOVIMIENTOS_OUTPUT,
        RESUMEN_OUTPUT,
        SALIDAS_OUTPUT,
    )


PALETTE = {
    "bg": "#f4f7fb",
    "panel": "#ffffff",
    "border": "#d9e2ef",
    "text": "#122033",
    "muted": "#52657d",
    "blue": "#0f6fff",
    "green": "#35c88a",
    "amber": "#f2b84b",
    "red": "#e45d5d",
}


ORDER_LABELS = {
    "TIPO_A": "Plancha de 30 Tipo A",
    "SUPER": "PLANCHA 30 SUPER",
    "TIPO_B": "PLANCHA 30 TIPO B",
    "JUMBO": "PLANCHAS 30 JUMBO",
    "TIPO_C": "PLANCHAS TIPO C",
    "PICADO": "PLANCHA 30 HUEVOS PICADO",
    "SUCIOS": "Sucios",
    "ROTOS": "Rotos",
    "SIN_CLASIFICAR": "Sin clasificar",
    "DE_6": "De 6",
    "DE_12": "De 12",
    "DE_20": "De 20",
}


st.set_page_config(
    page_title="Stock de huevos",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    f"""
    <style>
        .stApp {{
            background: {PALETTE["bg"]};
            color: {PALETTE["text"]};
        }}
        .block-container {{
            max-width: 1600px;
            padding-top: 1.2rem;
            padding-bottom: 2rem;
        }}
        h1, h2, h3 {{
            color: {PALETTE["text"]};
        }}
        .stock-grid {{
            display: grid;
            grid-template-columns: repeat(8, minmax(120px, 1fr));
            gap: 10px;
            margin-bottom: 1rem;
        }}
        .stock-card {{
            background: {PALETTE["panel"]};
            border: 1px solid {PALETTE["border"]};
            border-radius: 12px;
            padding: 14px 12px;
            min-height: 108px;
        }}
        .stock-title {{
            font-size: 0.95rem;
            color: {PALETTE["text"]};
            font-weight: 700;
            min-height: 48px;
        }}
        .stock-value {{
            font-size: 1.9rem;
            font-weight: 800;
            margin-top: 8px;
        }}
        .stock-ok {{
            color: {PALETTE["green"]};
        }}
        .stock-bad {{
            color: {PALETTE["red"]};
        }}
        .section-panel {{
            background: {PALETTE["panel"]};
            border: 1px solid {PALETTE["border"]};
            border-radius: 12px;
            padding: 16px;
        }}
        div[data-testid="stDataFrame"] {{
            border: 1px solid {PALETTE["border"]};
            border-radius: 10px;
            overflow: hidden;
        }}
        .small-note {{
            color: {PALETTE["muted"]};
            font-size: 0.9rem;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except EmptyDataError:
        return pd.DataFrame()


def save_initial_stock(df: pd.DataFrame) -> None:
    df.to_csv(INICIAL_OUTPUT, index=False)
    movimientos = load_csv(MOVIMIENTOS_OUTPUT)
    if movimientos.empty:
        resumen = pd.DataFrame(
            [
                {
                    "bucket": row["bucket"],
                    "display_name": row["display_name"],
                    "stock_inicial_planchas": float(row["stock_inicial_planchas"]),
                    "entradas_planchas": 0.0,
                    "salidas_planchas": 0.0,
                    "stock_actual_planchas": float(row["stock_inicial_planchas"]),
                }
                for _, row in df.iterrows()
            ]
        )
        resumen.to_csv(RESUMEN_OUTPUT, index=False)
        return

    movimientos_enriched, resumen = compute_stock_outputs(movimientos[MOV_COLUMNS] if "saldo_planchas" in movimientos.columns else movimientos)
    movimientos_enriched.to_csv(MOVIMIENTOS_OUTPUT, index=False)
    resumen.to_csv(RESUMEN_OUTPUT, index=False)


def order_key(bucket: str) -> int:
    try:
        return BUCKET_ORDER.index(bucket)
    except ValueError:
        return len(BUCKET_ORDER) + 1


def ordered_labels_from_summary(resumen: pd.DataFrame) -> list[str]:
    ordered = (
        resumen[["bucket", "display_name"]]
        .drop_duplicates()
        .assign(order=lambda df: df["bucket"].map(order_key))
        .sort_values(["order", "display_name"])
    )
    return ordered["display_name"].tolist()


def format_qty(value) -> str:
    if value is None or pd.isna(value):
        return "0"
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def extract_client_from_detail(detail: str) -> str:
    text = str(detail or "").strip()
    if "·" in text:
        return text.split("·", 1)[1].strip()
    return text


def extract_order_from_detail(detail: str) -> str:
    text = str(detail or "").strip()
    if "·" in text:
        return text.split("·", 1)[0].strip()
    return ""


def render_stock_cards(resumen: pd.DataFrame, ordered_labels: list[str]) -> None:
    values = {row["display_name"]: row["stock_actual_planchas"] for _, row in resumen.iterrows()}
    cards_per_row = 8
    for start in range(0, len(ordered_labels), cards_per_row):
        chunk = ordered_labels[start : start + cards_per_row]
        cols = st.columns(len(chunk))
        for col, label in zip(cols, chunk):
            value = float(values.get(label, 0.0))
            with col:
                with st.container(border=True):
                    st.markdown(f"**{label}**")
                    color = PALETTE["green"] if value >= 0 else PALETTE["red"]
                    st.markdown(
                        f"<div style='font-size:2rem;font-weight:800;color:{color};margin-top:8px'>{format_qty(value)}</div>",
                        unsafe_allow_html=True,
                    )


def align_initial_stock(stock_inicial: pd.DataFrame, resumen: pd.DataFrame) -> pd.DataFrame:
    template = (
        resumen[["bucket", "display_name"]]
        .drop_duplicates()
        .assign(order=lambda df: df["bucket"].map(order_key))
        .sort_values(["order", "display_name"])
        .drop(columns=["order"])
        .reset_index(drop=True)
    )
    if template.empty:
        return stock_inicial

    if stock_inicial.empty:
        aligned = template.copy()
        aligned["stock_inicial_planchas"] = 0.0
        save_initial_stock(aligned)
        return aligned

    base = stock_inicial.copy()
    if "bucket" not in base.columns:
        base["bucket"] = ""
    if "stock_inicial_planchas" not in base.columns:
        base["stock_inicial_planchas"] = 0.0

    base = base[["bucket", "stock_inicial_planchas"]].drop_duplicates(subset=["bucket"], keep="last")
    aligned = template.merge(base, on="bucket", how="left")
    aligned["stock_inicial_planchas"] = aligned["stock_inicial_planchas"].fillna(0.0)

    labels_changed = not stock_inicial[["bucket", "display_name"]].fillna("").equals(
        aligned[["bucket", "display_name"]].fillna("")
    ) if {"bucket", "display_name"}.issubset(stock_inicial.columns) else True
    missing_values = aligned["stock_inicial_planchas"].isna().any()

    if labels_changed or missing_values or len(aligned) != len(stock_inicial):
        save_initial_stock(aligned)

    return aligned


def build_pivot(df: pd.DataFrame, ordered_labels: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Fecha", *ordered_labels])
    pivot = (
        df.pivot_table(
            index="fecha",
            columns="display_name",
            values="cantidad_planchas",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
        .rename(columns={"fecha": "Fecha"})
    )
    for label in ordered_labels:
        if label not in pivot.columns:
            pivot[label] = 0.0
    pivot = pivot[["Fecha", *ordered_labels]]
    for label in ordered_labels:
        pivot[label] = pivot[label].map(format_qty)
    return pivot


def prepare_client_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["Cliente", "Salidas en planchas"])
    rows = []
    for detail, qty in df.groupby("detalle")["cantidad_planchas"].sum().items():
        client = extract_client_from_detail(detail)
        if not client:
            client = "Cliente sin nombre"
        rows.append({"Cliente": client, "Salidas en planchas": round(float(qty), 4)})
    summary = pd.DataFrame(rows).groupby("Cliente", as_index=False)["Salidas en planchas"].sum()
    summary = summary.sort_values("Salidas en planchas", ascending=False)
    summary["Salidas en planchas"] = summary["Salidas en planchas"].map(format_qty)
    return summary


def prepare_client_detail(df: pd.DataFrame, client_name: str) -> pd.DataFrame:
    if df.empty or not client_name:
        return pd.DataFrame(
            columns=["Fecha", "Pedido", "Tipo origen", "Cliente original", "Producto", "Salidas en planchas"]
        )

    subset = df.copy()
    subset["cliente_consolidado"] = subset["detalle"].map(extract_client_from_detail)
    if "detalle_original" not in subset.columns:
        subset["detalle_original"] = subset["detalle"]
    subset["cliente_original"] = subset["detalle_original"].map(extract_client_from_detail)
    subset["pedido_original"] = subset["detalle_original"].map(extract_order_from_detail)
    subset = subset[subset["cliente_consolidado"].astype(str).str.upper() == str(client_name).upper()]
    if subset.empty:
        return pd.DataFrame(
            columns=["Fecha", "Pedido", "Tipo origen", "Cliente original", "Producto", "Salidas en planchas"]
        )
    # Si el cliente actúa como "matriz" de consolidación (por ejemplo REPARTO),
    # primero mostramos solo los subclientes absorbidos. Las filas directas ERP
    # del mismo nombre se muestran aparte para no mezclar ambas lecturas.
    subset["es_directo_erp"] = (
        subset["cliente_original"].astype(str).str.upper()
        == subset["cliente_consolidado"].astype(str).str.upper()
    )
    has_consolidated_rows = (~subset["es_directo_erp"]).any()
    if has_consolidated_rows:
        subset = subset[~subset["es_directo_erp"]].copy()

    detail = (
        subset.groupby(["fecha", "pedido_original", "cliente_original", "producto_fuente"], as_index=False)["cantidad_planchas"]
        .sum()
        .sort_values(["fecha", "cliente_original", "cantidad_planchas"], ascending=[True, True, False])
    )
    rows = []
    for _, row in detail.iterrows():
        cliente_original = row["cliente_original"] or client_name
        rows.append(
            {
                "Fecha": pd.to_datetime(row["fecha"]).strftime("%d/%m/%Y"),
                "Pedido": row["pedido_original"] or "-",
                "Tipo origen": "Consolidado" if has_consolidated_rows else "Directo ERP",
                "Cliente original": cliente_original,
                "Producto": row["producto_fuente"],
                "Salidas en planchas": format_qty(row["cantidad_planchas"]),
            }
        )
    return pd.DataFrame(rows)


def prepare_client_direct_detail(df: pd.DataFrame, client_name: str) -> pd.DataFrame:
    if df.empty or not client_name:
        return pd.DataFrame(columns=["Fecha", "Pedido", "Producto", "Salidas en planchas"])

    subset = df.copy()
    subset["cliente_consolidado"] = subset["detalle"].map(extract_client_from_detail)
    if "detalle_original" not in subset.columns:
        subset["detalle_original"] = subset["detalle"]
    subset["cliente_original"] = subset["detalle_original"].map(extract_client_from_detail)
    subset["pedido_original"] = subset["detalle_original"].map(extract_order_from_detail)
    subset = subset[subset["cliente_consolidado"].astype(str).str.upper() == str(client_name).upper()]
    subset = subset[
        subset["cliente_original"].astype(str).str.upper() == subset["cliente_consolidado"].astype(str).str.upper()
    ]
    if subset.empty:
        return pd.DataFrame(columns=["Fecha", "Pedido", "Producto", "Salidas en planchas"])

    detail = (
        subset.groupby(["fecha", "pedido_original", "producto_fuente"], as_index=False)["cantidad_planchas"]
        .sum()
        .sort_values(["fecha", "cantidad_planchas"], ascending=[True, False])
    )
    rows = []
    for _, row in detail.iterrows():
        rows.append(
            {
                "Fecha": pd.to_datetime(row["fecha"]).strftime("%d/%m/%Y"),
                "Pedido": row["pedido_original"] or "-",
                "Producto": row["producto_fuente"],
                "Salidas en planchas": format_qty(row["cantidad_planchas"]),
            }
        )
    return pd.DataFrame(rows)


entradas = load_csv(ENTRADAS_OUTPUT)
salidas = load_csv(SALIDAS_OUTPUT)
movimientos = load_csv(MOVIMIENTOS_OUTPUT)
resumen = load_csv(RESUMEN_OUTPUT)
config = load_csv(CONFIG_OUTPUT)
stock_inicial = load_csv(INICIAL_OUTPUT)

st.title("Stock de huevos")
st.caption("Desde mayo 2026. Todo el seguimiento se muestra en planchas equivalentes.")

if resumen.empty:
    st.warning("Todavía no hay datos calculados. Ejecutá la tarea `A - Stock de huevos` desde ERP Launcher.")
    st.stop()

stock_inicial = align_initial_stock(stock_inicial, resumen)
ordered_labels = ordered_labels_from_summary(resumen)

with st.sidebar:
    st.subheader("Stock inicial")
    if not stock_inicial.empty:
        editor_df = stock_inicial.copy()
        edited = st.data_editor(
            editor_df,
            key="stock_inicial_editor",
            hide_index=True,
            width="stretch",
            column_config={
                "bucket": st.column_config.TextColumn("Bucket", disabled=True),
                "display_name": st.column_config.TextColumn("Producto", disabled=True),
                "stock_inicial_planchas": st.column_config.NumberColumn("Inicial (planchas)", step=0.1),
            },
        )
        if st.button("Guardar stock inicial", width="stretch"):
            save_initial_stock(edited)
            st.success("Stock inicial guardado.")
            st.rerun()

    st.subheader("Archivos")
    st.write(f"Entradas: `{ENTRADAS_OUTPUT.name}`")
    st.write(f"Salidas: `{SALIDAS_OUTPUT.name}`")
    st.write(f"Resumen: `{RESUMEN_OUTPUT.name}`")


st.subheader("Vista de stock")
render_stock_cards(resumen, ordered_labels)

left_btn, right_btn = st.columns([1, 1])
if "stock_mode" not in st.session_state:
    st.session_state["stock_mode"] = "entrada"

with left_btn:
    if st.button("Entrada", width="stretch", type="primary" if st.session_state["stock_mode"] == "entrada" else "secondary"):
        st.session_state["stock_mode"] = "entrada"
with right_btn:
    if st.button("Salida", width="stretch", type="primary" if st.session_state["stock_mode"] == "salida" else "secondary"):
        st.session_state["stock_mode"] = "salida"


if st.session_state["stock_mode"] == "entrada":
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.subheader("Vista 1: Entradas")
    st.markdown('<div class="small-note">Producción diaria en planchas equivalentes.</div>', unsafe_allow_html=True)
    entrada_pivot = build_pivot(entradas, ordered_labels)
    st.dataframe(entrada_pivot, width="stretch", hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)
else:
    st.markdown('<div class="section-panel">', unsafe_allow_html=True)
    st.subheader("Vista 2: Salidas")
    fechas_salidas = (
        pd.to_datetime(salidas["fecha"], errors="coerce").dropna().dt.date.sort_values().unique().tolist()
        if not salidas.empty
        else []
    )
    if fechas_salidas:
        fecha_options = {fecha.strftime("%d/%m/%Y"): fecha for fecha in fechas_salidas}
        default_label = list(fecha_options.keys())[-1]
        fechas_labels_sel = st.multiselect(
            "Fechas",
            options=list(fecha_options.keys()),
            default=[default_label],
            help="Podés seleccionar una o varias fechas para ver las salidas juntas.",
        )
        fechas_iso_sel = [fecha_options[label].isoformat() for label in fechas_labels_sel]
        salidas_dia = salidas[salidas["fecha"].isin(fechas_iso_sel)].copy()
        resumen_clientes = prepare_client_summary(salidas_dia)
        st.markdown(
            '<div class="small-note">Al seleccionar una o varias fechas, vas a ver todos los clientes que tuvieron salidas. Si un cliente fue consolidado como REPARTO, DIEGO SOLJANCIC u otro, arriba se ve el bucket consolidado y en el detalle solo se ven los nombres originales absorbidos.</div>',
            unsafe_allow_html=True,
        )
        if resumen_clientes.empty:
            st.info("No hay salidas para las fechas seleccionadas.")
        else:
            event = st.dataframe(
                resumen_clientes,
                width="stretch",
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )
            cliente_default = resumen_clientes.iloc[0]["Cliente"]
            selected_rows = event.selection.rows if hasattr(event, "selection") else []
            cliente_sel = cliente_default
            if selected_rows:
                cliente_sel = resumen_clientes.iloc[selected_rows[0]]["Cliente"]
            cliente_sel = st.selectbox(
                "Cliente",
                resumen_clientes["Cliente"].tolist(),
                index=resumen_clientes["Cliente"].tolist().index(cliente_sel),
            )
            st.markdown(f"**Detalle de salidas en planchas: {cliente_sel}**")
            detalle_cliente = prepare_client_detail(salidas_dia, cliente_sel)
            st.dataframe(detalle_cliente, width="stretch", hide_index=True)
    else:
        st.info("No hay salidas registradas todavía.")
    st.markdown("</div>", unsafe_allow_html=True)


with st.expander("Ver movimientos consolidados"):
    mov_show = movimientos.copy()
    if mov_show.empty:
        st.info("No hay movimientos.")
    else:
        mov_show["cantidad_planchas"] = mov_show["cantidad_planchas"].map(format_qty)
        if "saldo_planchas" in mov_show.columns:
            mov_show["saldo_planchas"] = mov_show["saldo_planchas"].map(format_qty)
        st.dataframe(
            mov_show.rename(
                columns={
                    "fecha": "Fecha",
                    "tipo_movimiento": "Tipo",
                    "display_name": "Bucket",
                    "producto_fuente": "Producto fuente",
                    "producto_sku": "SKU ERP",
                    "cantidad_planchas": "Cantidad (planchas)",
                    "saldo_planchas": "Saldo",
                    "detalle": "Detalle",
                    "origen": "Origen",
                }
            ),
            width="stretch",
            hide_index=True,
        )

with st.expander("Ver reglas de conversión"):
    st.caption("Los productos marcados con `x` se convierten a planchas equivalentes antes de descontar stock.")
    st.dataframe(
        config.rename(
            columns={
                "display_name": "Bucket",
                "sku_name": "Producto ERP",
                "family": "Familia",
                "factor_to_plancha": "Factor a plancha",
                "marked_x": "Marcado x",
            }
        ),
        width="stretch",
        hide_index=True,
    )
