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


def ensure_initial_stock_file() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if INICIAL_OUTPUT.exists():
        return
    rows = [
        {
            "bucket": cfg.bucket,
            "display_name": cfg.display_name,
            "stock_inicial_planchas": 0.0,
        }
        for cfg in TRACKED_PRODUCTS
    ]
    pd.DataFrame(rows).to_csv(INICIAL_OUTPUT, index=False)


def compute_stock_outputs(movimientos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    ensure_initial_stock_file()
    inicial = pd.read_csv(INICIAL_OUTPUT)
    inicial_map = {row["bucket"]: float(row["stock_inicial_planchas"]) for _, row in inicial.iterrows()}

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
        saldo = float(inicial_map.get(bucket, 0.0))
        entradas = float(subset.loc[subset["tipo_movimiento"] == "entrada", "cantidad_planchas"].sum())
        salidas = float(subset.loc[subset["tipo_movimiento"] == "salida", "cantidad_planchas"].sum())
        for _, row in subset.iterrows():
            if row["tipo_movimiento"] == "entrada":
                saldo += float(row["cantidad_planchas"])
            else:
                saldo -= float(row["cantidad_planchas"])
            enriched = row.to_dict()
            enriched["saldo_planchas"] = round(saldo, 4)
            enriched_rows.append(enriched)
        resumen_rows.append(
            {
                "bucket": bucket,
                "display_name": display_name,
                "stock_inicial_planchas": round(inicial_map.get(bucket, 0.0), 4),
                "entradas_planchas": round(entradas, 4),
                "salidas_planchas": round(salidas, 4),
                "stock_actual_planchas": round(inicial_map.get(bucket, 0.0) + entradas - salidas, 4),
            }
        )

    return pd.DataFrame(enriched_rows, columns=[*MOV_COLUMNS, "saldo_planchas"]), pd.DataFrame(resumen_rows)
