"""API del dashboard Pabst BI.

Ejecutar desde la raiz del proyecto, con el entorno virtual activado:
    uvicorn app.main:app --reload
Documentacion interactiva: http://localhost:8000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text

from app import config
from app.db import engine
from app.routers import auth, chat, facturas, proveedores, usuarios, ventas

app = FastAPI(title="Pabst BI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
# /documentos devuelve miles de filas: comprimirlas reduce mucho lo que viaja al navegador
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(auth.router)
app.include_router(ventas.router)
app.include_router(facturas.router)
app.include_router(proveedores.router)
app.include_router(usuarios.router)
app.include_router(chat.router)


@app.get("/salud", tags=["salud"])
def salud():
    with engine.connect() as con:
        con.execute(text("SELECT 1 FROM usuario LIMIT 1"))
    return {"estado": "ok"}
