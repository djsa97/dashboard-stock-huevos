from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
ENTRADAS_OUTPUT = DATA_DIR / "entradas_normalizadas.csv"
SALIDAS_OUTPUT = DATA_DIR / "salidas_normalizadas.csv"
MOVIMIENTOS_OUTPUT = DATA_DIR / "movimientos_stock.csv"
RESUMEN_OUTPUT = DATA_DIR / "resumen_stock.csv"
INICIAL_OUTPUT = DATA_DIR / "stock_inicial.csv"
CONFIG_OUTPUT = DATA_DIR / "config_productos.csv"
TRACKING_START_DATE = pd.Timestamp("2026-05-19")

MOV_COLUMNS = [
    "fecha",
    "tipo_movimiento",
    "bucket",
    "display_name",
    "producto_fuente",
    "producto_sku",
    "cantidad_planchas",
    "detalle",
    "detalle_original",
    "origen",
]

ADJUSTMENT_COLUMN = "restar_salida_manual_planchas"

BUCKET_ORDER = [
    "TIPO_A",
    "SUPER",
    "TIPO_B",
    "JUMBO",
    "TIPO_C",
    "PICADO",
    "SUCIOS",
    "ROTOS",
    "SIN_CLASIFICAR",
    "DE_6",
    "DE_12",
    "DE_20",
]


@dataclass(frozen=True)
class BucketConfig:
    bucket: str
    display_name: str


TRACKED_PRODUCTS = [
    BucketConfig("TIPO_A", "Plancha de 30 Tipo A"),
    BucketConfig("PICADO", "PLANCHA 30 HUEVOS PICADO"),
    BucketConfig("SUPER", "PLANCHA 30 SUPER"),
    BucketConfig("TIPO_B", "PLANCHA 30 TIPO B"),
    BucketConfig("JUMBO", "PLANCHAS 30 JUMBO"),
    BucketConfig("TIPO_C", "PLANCHAS TIPO C"),
    BucketConfig("SUCIOS", "Sucios"),
    BucketConfig("ROTOS", "Rotos"),
    BucketConfig("SIN_CLASIFICAR", "Sin clasificar"),
    BucketConfig("DE_6", "De 6"),
    BucketConfig("DE_12", "De 12"),
    BucketConfig("DE_20", "De 20"),
]

PACKAGED_TYPE_A_SKUS = {
    "PLANCHA 6 HUEVOS TIPO A COD. 7848000130043": ("DE_6", "De 6", 6 / 30),
    "PLANCHA 12 HUEVOS TIPO A COD.7848000130036": ("DE_12", "De 12", 12 / 30),
    "PLANCHAS 20 HUEVOS TIPO A COD.7848000130074": ("DE_20", "De 20", 20 / 30),
}

def _normalize_sku(value: str) -> str:
    return " ".join(str(value or "").upper().replace(".", " ").split())


def _extract_client_from_detail(detail: str) -> str:
    text = str(detail or "").strip()
    if "·" in text:
        return text.split("·", 1)[1].strip()
    return text


def _is_stock_effective(row: pd.Series) -> bool:
    if row.get("tipo_movimiento") != "salida":
        return True
    if row.get("origen") != "ERP Pedidos":
        return True
    detalle = row.get("detalle", "")
    detalle_original = row.get("detalle_original", detalle)
    cliente_consolidado = _extract_client_from_detail(detalle).upper()
    cliente_original = _extract_client_from_detail(detalle_original).upper()
    return cliente_original == cliente_consolidado


def ensure_initial_stock_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if INICIAL_OUTPUT.exists():
        return
    rows = [
        {
            "bucket": cfg.bucket,
            "display_name": cfg.display_name,
            "stock_inicial_planchas": 0.0,
            ADJUSTMENT_COLUMN: 0.0,
        }
        for cfg in TRACKED_PRODUCTS
    ]
    pd.DataFrame(rows).to_csv(INICIAL_OUTPUT, index=False)


def _allocate_packaged_type_a_sales(movimientos: pd.DataFrame, inicial_map: dict[str, float]) -> pd.DataFrame:
    if movimientos.empty:
        return movimientos

    remaining_packaged_stock = {
        bucket: float(inicial_map.get(bucket, 0.0))
        for bucket, _, _ in PACKAGED_TYPE_A_SKUS.values()
    }
    adjusted_rows: list[dict] = []
    movimientos_sorted = movimientos.copy()
    movimientos_sorted["fecha"] = pd.to_datetime(movimientos_sorted["fecha"], errors="coerce")
    movimientos_sorted = movimientos_sorted.sort_values(["fecha", "tipo_movimiento", "producto_fuente"])

    for _, row in movimientos_sorted.iterrows():
        row_dict = row.to_dict()
        sku = str(row_dict.get("producto_sku", "") or "").strip()
        package_config = next(
            (config for sku_name, config in PACKAGED_TYPE_A_SKUS.items() if _normalize_sku(sku_name) == _normalize_sku(sku)),
            None,
        )

        if row_dict.get("tipo_movimiento") != "salida" or row_dict.get("bucket") != "TIPO_A" or package_config is None:
            if row_dict.get("tipo_movimiento") == "entrada" and row_dict.get("bucket") in remaining_packaged_stock:
                remaining_packaged_stock[row_dict["bucket"]] += float(row_dict.get("cantidad_planchas", 0.0) or 0.0)
            adjusted_rows.append(row_dict)
            continue

        package_bucket, package_display, factor_to_plancha = package_config
        package_qty = float(row_dict.get("cantidad_planchas", 0.0) or 0.0) / factor_to_plancha
        available_qty = max(remaining_packaged_stock.get(package_bucket, 0.0), 0.0)
        packaged_qty = min(package_qty, available_qty)
        fallback_qty = package_qty - packaged_qty

        if packaged_qty > 0:
            packaged_row = row_dict.copy()
            packaged_row["bucket"] = package_bucket
            packaged_row["display_name"] = package_display
            packaged_row["cantidad_planchas"] = round(packaged_qty, 4)
            adjusted_rows.append(packaged_row)
            remaining_packaged_stock[package_bucket] = available_qty - packaged_qty

        if fallback_qty > 0:
            fallback_row = row_dict.copy()
            fallback_row["cantidad_planchas"] = round(fallback_qty * factor_to_plancha, 4)
            adjusted_rows.append(fallback_row)

    return pd.DataFrame(adjusted_rows, columns=movimientos.columns)


def compute_stock_outputs(movimientos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ensure_initial_stock_file()
    inicial = pd.read_csv(INICIAL_OUTPUT)
    if ADJUSTMENT_COLUMN not in inicial.columns:
        inicial[ADJUSTMENT_COLUMN] = 0.0
    inicial_map = {row["bucket"]: float(row["stock_inicial_planchas"]) for _, row in inicial.iterrows()}
    adjustment_map = {row["bucket"]: float(row.get(ADJUSTMENT_COLUMN, 0.0) or 0.0) for _, row in inicial.iterrows()}
    if not movimientos.empty:
        movimientos = movimientos.copy()
        movimientos["fecha"] = pd.to_datetime(movimientos["fecha"], errors="coerce")
        movimientos = movimientos[movimientos["fecha"].ge(TRACKING_START_DATE)].copy()
    movimientos = _allocate_packaged_type_a_sales(movimientos, inicial_map)

    display_by_bucket = {cfg.bucket: cfg.display_name for cfg in TRACKED_PRODUCTS}
    bucket_map = display_by_bucket.copy()
    if not movimientos.empty:
        for _, row in movimientos[["bucket", "display_name"]].drop_duplicates().iterrows():
            bucket_map[str(row["bucket"])] = str(row["display_name"])

    ordered_buckets = [bucket for bucket in BUCKET_ORDER if bucket in bucket_map]
    ordered_buckets.extend(bucket for bucket in bucket_map if bucket not in ordered_buckets)
    buckets = [{"bucket": bucket, "display_name": bucket_map[bucket]} for bucket in ordered_buckets]

    resumen_rows: list[dict] = []
    movimientos_sorted = movimientos.copy()
    if movimientos_sorted.empty:
        movimientos_sorted = pd.DataFrame(columns=MOV_COLUMNS)
    movimientos_sorted["fecha"] = pd.to_datetime(movimientos_sorted["fecha"], errors="coerce")
    movimientos_sorted = movimientos_sorted.sort_values(["bucket", "fecha", "tipo_movimiento", "producto_fuente"])

    enriched_rows: list[dict] = []
    for bucket_info in buckets:
        bucket = bucket_info["bucket"]
        display_name = bucket_info["display_name"]
        subset = movimientos_sorted[movimientos_sorted["bucket"] == bucket].copy()
        ajuste_salida = float(adjustment_map.get(bucket, 0.0))
        saldo = float(inicial_map.get(bucket, 0.0)) + ajuste_salida
        entradas = float(subset.loc[subset["tipo_movimiento"] == "entrada", "cantidad_planchas"].sum())
        stock_effective = subset.apply(_is_stock_effective, axis=1) if not subset.empty else pd.Series(dtype=bool)
        salidas_brutas = float(
            subset.loc[(subset["tipo_movimiento"] == "salida") & stock_effective, "cantidad_planchas"].sum()
        )
        salidas = salidas_brutas - ajuste_salida
        for _, row in subset.iterrows():
            if row["tipo_movimiento"] == "entrada":
                saldo += float(row["cantidad_planchas"])
            elif _is_stock_effective(row):
                saldo -= float(row["cantidad_planchas"])
            enriched = row.to_dict()
            enriched["saldo_planchas"] = round(saldo, 4)
            enriched_rows.append(enriched)
        resumen_rows.append(
            {
                "bucket": bucket,
                "display_name": display_name,
                "stock_inicial_planchas": round(inicial_map.get(bucket, 0.0), 4),
                ADJUSTMENT_COLUMN: round(ajuste_salida, 4),
                "entradas_planchas": round(entradas, 4),
                "salidas_planchas": round(salidas, 4),
                "stock_actual_planchas": round(inicial_map.get(bucket, 0.0) + entradas - salidas, 4),
            }
        )

    return pd.DataFrame(enriched_rows, columns=[*MOV_COLUMNS, "saldo_planchas"]), pd.DataFrame(resumen_rows)
