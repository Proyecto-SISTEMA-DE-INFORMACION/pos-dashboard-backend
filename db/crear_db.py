"""
Crea la base de datos del dashboard de la botilleria en PostgreSQL 16.

Lee la conexion desde el archivo .env del proyecto, crea la base si no
existe y ejecuta db/schema.sql (solo estructura, sin datos).

Uso, desde la carpeta del proyecto y con el entorno virtual activado:
    python db/crear_db.py                  crea la base y las tablas
    python db/crear_db.py --con-catalogos  ademas carga medios de pago y temporadas
    python db/crear_db.py --reset          borra el esquema y lo crea de nuevo (pide confirmacion)
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

CARPETA_DB = Path(__file__).resolve().parent
RAIZ_PROYECTO = CARPETA_DB.parent
ARCHIVO_SCHEMA = CARPETA_DB / "schema.sql"
ARCHIVO_CATALOGOS = CARPETA_DB / "seed_catalogos.sql"
VERSION_REQUERIDA = 16


def salir(mensaje: str) -> None:
    print(f"\nERROR: {mensaje}")
    sys.exit(1)


def leer_configuracion() -> dict:
    archivo_env = RAIZ_PROYECTO / ".env"
    if not archivo_env.exists():
        salir(
            f"No se encontro {archivo_env}.\n"
            "Copia .env.example, renombra la copia a .env y completa tus datos."
        )
    load_dotenv(archivo_env)

    config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": os.getenv("DB_PORT", "5432"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", ""),
        "dbname": os.getenv("DB_NAME", "botilleria"),
        "schema": os.getenv("DB_SCHEMA", "botilleria"),
    }
    if not config["password"]:
        salir("DB_PASSWORD esta vacio en el .env.")
    return config


def conectar(config: dict, base: str):
    try:
        conexion = psycopg2.connect(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            dbname=base,
            client_encoding="utf8",
            connect_timeout=10,
        )
    except UnicodeDecodeError:
        # PostgreSQL en espanol envia el error de login en otra codificacion
        salir(
            "No se pudo conectar (probablemente contrasena incorrecta).\n"
            f"Revisa DB_PASSWORD y que DB_PORT={config['port']} sea el puerto de tu PostgreSQL 16."
        )
    except psycopg2.OperationalError as error:
        salir(
            f"No se pudo conectar a {config['host']}:{config['port']}.\n"
            f"Detalle: {str(error).strip()}\n"
            "Revisa DB_PASSWORD y DB_PORT en el .env, y que el servicio de PostgreSQL 16 este corriendo."
        )
    conexion.autocommit = True
    return conexion


def revisar_version(conexion, config: dict) -> None:
    version = conexion.server_version // 10000
    print(f"Conectado a PostgreSQL {version} en {config['host']}:{config['port']}")
    if version != VERSION_REQUERIDA:
        salir(
            f"Este proyecto usa PostgreSQL {VERSION_REQUERIDA}, pero en el puerto {config['port']} "
            f"esta PostgreSQL {version}.\nCambia DB_PORT en el .env al puerto de tu PostgreSQL {VERSION_REQUERIDA}."
        )


def crear_base_si_no_existe(config: dict) -> None:
    conexion = conectar(config, "postgres")
    revisar_version(conexion, config)
    with conexion.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (config["dbname"],))
        if cursor.fetchone():
            print(f"La base '{config['dbname']}' ya existe.")
        else:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config["dbname"])))
            print(f"Base '{config['dbname']}' creada.")
    conexion.close()


def esquema_existe(cursor, esquema: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (esquema,)
    )
    return cursor.fetchone() is not None


def ejecutar_archivo(cursor, archivo: Path) -> None:
    if not archivo.exists():
        salir(f"No se encontro {archivo}.")
    # Sin parametros, psycopg2 envia el archivo completo tal cual
    # (el propio archivo maneja BEGIN y COMMIT).
    cursor.execute(archivo.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea la base de datos de la botilleria.")
    parser.add_argument("--con-catalogos", action="store_true",
                        help="carga los medios de pago y las temporadas iniciales")
    parser.add_argument("--reset", action="store_true",
                        help="borra el esquema y todos sus datos, y lo crea de nuevo")
    args = parser.parse_args()

    config = leer_configuracion()
    crear_base_si_no_existe(config)

    conexion = conectar(config, config["dbname"])
    with conexion.cursor() as cursor:
        if esquema_existe(cursor, config["schema"]):
            if not args.reset:
                print(
                    f"El esquema '{config['schema']}' ya existe: las tablas ya estan creadas.\n"
                    "Para borrarlo y crearlo de nuevo usa: python db/crear_db.py --reset"
                )
                conexion.close()
                return
            respuesta = input(
                f"Se borraran TODAS las tablas y datos de '{config['schema']}'. "
                f"Escribe el nombre de la base ({config['dbname']}) para confirmar: "
            )
            if respuesta.strip() != config["dbname"]:
                print("Cancelado. No se borro nada.")
                conexion.close()
                return
            cursor.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(config["schema"])))
            print(f"Esquema '{config['schema']}' borrado.")

        try:
            ejecutar_archivo(cursor, ARCHIVO_SCHEMA)
            print("Tablas creadas desde schema.sql.")
            if args.con_catalogos:
                ejecutar_archivo(cursor, ARCHIVO_CATALOGOS)
                print("Catalogos cargados desde seed_catalogos.sql.")

            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name",
                (config["schema"],),
            )
            tablas = [fila[0] for fila in cursor.fetchall()]
        except psycopg2.Error as error:
            salir(f"Fallo al ejecutar el SQL.\nDetalle: {str(error).strip()}")

    conexion.close()
    print(f"\nListo: {len(tablas)} tablas en '{config['dbname']}.{config['schema']}':")
    for tabla in tablas:
        print(f"  - {tabla}")


if __name__ == "__main__":
    main()
