"""Conexion a PostgreSQL y definicion de las tablas (deben coincidir con db/schema.sql)."""

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, Integer, MetaData, String, Table, Text,
    create_engine, true,
)
from sqlalchemy.engine import URL

from app import config

url = URL.create(
    "postgresql+psycopg2",
    username=config.DB_USER,
    password=config.DB_PASSWORD,
    host=config.DB_HOST,
    port=config.DB_PORT,
    database=config.DB_NAME,
)

engine = create_engine(
    url,
    pool_pre_ping=True,
    connect_args={
        "options": f"-csearch_path={config.DB_SCHEMA}",
        "client_encoding": "utf8",
    },
)

metadata = MetaData()

usuario = Table(
    "usuario", metadata,
    Column("id_usuario", Integer, primary_key=True),
    Column("email", String(255)),
    Column("nombre", String(100)),
    Column("contrasena_hash", String(255)),
    Column("tipo_usuario", String(20)),
)

conversacion = Table(
    "conversacion", metadata,
    Column("id_conversacion", Integer, primary_key=True),
    Column("id_usuario", Integer),
    Column("titulo", String(100)),
    Column("fecha_inicio", DateTime(timezone=True)),
    Column("fecha_ultimo_mensaje", DateTime(timezone=True)),
)

mensaje = Table(
    "mensaje", metadata,
    Column("id_mensaje", BigInteger, primary_key=True),
    Column("id_conversacion", Integer),
    Column("rol", String(10)),
    Column("contenido", Text),
    Column("fecha", DateTime(timezone=True)),
    Column("modelo", String(50)),
    Column("estado", String(10)),
    Column("mensaje_error", Text),
    Column("datos_enviados", Text),
    Column("tiempo_respuesta_ms", Integer),
    Column("tokens", Integer),
)

temporada = Table(
    "temporada", metadata,
    Column("id_temporada", Integer, primary_key=True),
    Column("nombre", String(20)),
    Column("fecha_inicio", Date),
    Column("fecha_fin", Date),
)

medio_pago = Table(
    "medio_pago", metadata,
    Column("id_medio", Integer, primary_key=True),
    Column("nombre_medio", String(30)),
    Column("serie", String(10)),
    Column("cuenta_como_ingreso", Boolean),
)

archivo = Table(
    "archivo", metadata,
    Column("id_carga", Integer, primary_key=True),
    Column("nombre_archivo", String(255)),
    Column("fecha_carga", DateTime(timezone=True)),
    Column("registros_nuevos", Integer),
    Column("registros_omitidos", Integer),
)

venta = Table(
    "venta", metadata,
    Column("id_venta", BigInteger, primary_key=True),
    Column("serie", String(10)),
    Column("numero_boleta", String(10)),
    Column("fecha", Date),
    Column("valor_neto", Integer),
    Column("valor_iva", Integer),
    Column("valor_total", Integer),
    Column("id_medio", Integer),
    Column("id_carga", Integer),
    Column("id_temporada", Integer),
)

proveedor = Table(
    "proveedor", metadata,
    Column("id_proveedor", Integer, primary_key=True),
    Column("nombre", String(100)),
    Column("activo", Boolean, nullable=False, server_default=true()),
)

factura = Table(
    "factura", metadata,
    Column("id_factura", Integer, primary_key=True),
    Column("id_proveedor", Integer),
    Column("monto_bruto", Integer),
    Column("fecha_factura", Date),
    Column("id_usuario", Integer),
    Column("fecha_ingreso", DateTime(timezone=True)),
    Column("id_temporada", Integer),
)

meta_mensual = Table(
    "meta_mensual", metadata,
    Column("mes", Date, primary_key=True),
    Column("monto", BigInteger),
    Column("id_usuario", Integer),
    Column("fecha_actualizacion", DateTime(timezone=True)),
)
