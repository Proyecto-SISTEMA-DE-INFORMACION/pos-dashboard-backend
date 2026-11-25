"""Crea la tabla de metas mensuales en una base que ya tiene datos."""

from psycopg2 import sql

SQL_META_MENSUAL = """
CREATE TABLE IF NOT EXISTS {tabla} (
    mes                  DATE        NOT NULL,
    monto                BIGINT      NOT NULL,
    id_usuario           INTEGER,
    fecha_actualizacion  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_meta_mensual PRIMARY KEY (mes),
    CONSTRAINT ck_meta_mensual_dia CHECK (EXTRACT(DAY FROM mes) = 1),
    CONSTRAINT ck_meta_mensual_monto CHECK (monto > 0),
    CONSTRAINT fk_meta_mensual_usuario FOREIGN KEY (id_usuario)
        REFERENCES {usuario} (id_usuario) ON DELETE SET NULL
)
"""


def crear_meta_mensual(cursor, esquema: str) -> None:
    cursor.execute(
        sql.SQL(SQL_META_MENSUAL).format(
            tabla=sql.Identifier(esquema, "meta_mensual"),
            usuario=sql.Identifier(esquema, "usuario"),
        )
    )


def main() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.config import DB_SCHEMA
    from app.db import engine

    with engine.begin() as conexion:
        with conexion.connection.cursor() as cursor:
            crear_meta_mensual(cursor, DB_SCHEMA)
    print("Tabla de metas mensuales lista.")


if __name__ == "__main__":
    main()
