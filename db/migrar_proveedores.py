"""Habilita la eliminación del catálogo conservando las facturas."""

from psycopg2 import sql


def agregar_activo(cursor, esquema: str) -> None:
    cursor.execute(
        sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT TRUE")
        .format(sql.Identifier(esquema, "proveedor"))
    )


def main() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.config import DB_SCHEMA
    from app.db import engine

    with engine.begin() as conexion:
        with conexion.connection.cursor() as cursor:
            agregar_activo(cursor, DB_SCHEMA)
    print("Catálogo de proveedores actualizado.")


if __name__ == "__main__":
    main()
