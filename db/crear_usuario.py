"""
Crea un usuario para iniciar sesion en el dashboard, o le cambia la contrasena si ya existe.

Uso, desde la carpeta del proyecto y con el entorno virtual activado:
    python db/crear_usuario.py --email admin@pabst.cl --nombre "Administración"
    python db/crear_usuario.py --email lector@pabst.cl --nombre "Contador" --tipo LECTOR

La contrasena se pide por teclado (no se ve al escribirla) y se guarda cifrada.
"""

import argparse
import getpass
import hashlib
import os
import re
import secrets
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
ITERACIONES = 600_000  # debe coincidir con app/security.py


def hash_contrasena(contrasena: str) -> str:
    sal = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), sal.encode(), ITERACIONES)
    return f"pbkdf2_sha256${ITERACIONES}${sal}${digest.hex()}"


def salir(mensaje: str) -> None:
    print(f"\nERROR: {mensaje}")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Crea o actualiza un usuario del dashboard.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--nombre", default="Administración")
    parser.add_argument("--tipo", choices=["ADMINISTRADOR", "LECTOR"], default="ADMINISTRADOR")
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        salir("El email no es válido.")

    contrasena = os.getenv("NUEVA_CONTRASENA") or getpass.getpass("Contraseña nueva: ")
    if not os.getenv("NUEVA_CONTRASENA") and contrasena != getpass.getpass("Repite la contraseña: "):
        salir("Las contraseñas no coinciden.")
    if len(contrasena) < 8:
        salir("La contraseña debe tener al menos 8 caracteres.")

    if not (RAIZ / ".env").exists():
        salir(f"No se encontró {RAIZ / '.env'}.")
    load_dotenv(RAIZ / ".env")
    try:
        con = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"), port=os.getenv("DB_PORT", "5432"),
            user=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASSWORD", ""),
            dbname=os.getenv("DB_NAME", "botilleria"), client_encoding="utf8",
            options=f"-csearch_path={os.getenv('DB_SCHEMA', 'botilleria')}",
        )
    except (psycopg2.OperationalError, UnicodeDecodeError):
        salir("No se pudo conectar a PostgreSQL. Revisa DB_PASSWORD y DB_PORT en el .env.")

    with con, con.cursor() as cur:
        cur.execute("SELECT id_usuario FROM usuario WHERE lower(email) = %s", (email,))
        existe = cur.fetchone()
        if existe:
            cur.execute(
                "UPDATE usuario SET nombre = %s, contrasena_hash = %s, tipo_usuario = %s WHERE id_usuario = %s",
                (args.nombre, hash_contrasena(contrasena), args.tipo, existe[0]),
            )
            print(f"Usuario {email} actualizado.")
        else:
            cur.execute(
                "INSERT INTO usuario (email, nombre, contrasena_hash, tipo_usuario) VALUES (%s, %s, %s, %s)",
                (email, args.nombre, hash_contrasena(contrasena), args.tipo),
            )
            print(f"Usuario {email} creado como {args.tipo}.")
    con.close()


if __name__ == "__main__":
    main()
