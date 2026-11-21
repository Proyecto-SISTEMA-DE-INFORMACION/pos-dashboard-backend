# Pabst BI — Backend

API en FastAPI para el dashboard del libro de ventas de la botillería El Faro.
Usa solo las librerías de `requirements.txt` y PostgreSQL 16.

## Puesta en marcha

1. Activa el entorno virtual e instala las dependencias:
   ```powershell
   pip install -r requirements.txt
   ```
2. Copia `.env.example` como `.env` y completa `DB_PASSWORD`, `DB_PORT`, `SECRET_KEY` y `AI_API_KEY`.
3. Crea la base de datos con los catálogos (medios de pago y temporadas):
   ```powershell
   python db\crear_db.py --con-catalogos
   ```
4. Crea tu usuario para iniciar sesión (pide la contraseña por teclado):
   ```powershell
   python db\crear_usuario.py --email admin@pabst.cl --nombre "Administración"
   ```
5. Enciende la API:
   ```powershell
   uvicorn app.main:app --reload
   ```
   Queda en http://localhost:8000 y la documentación interactiva en http://localhost:8000/docs

## Endpoints

| Método | Ruta | Qué hace | Requiere |
|---|---|---|---|
| POST | `/auth/login` | Entrega el token de sesión (`{email, password}`) | — |
| GET | `/auth/me` | Datos del usuario conectado | sesión |
| POST | `/upload?nombre=archivo.xlsx` | Carga el libro de ventas (cuerpo binario `application/octet-stream`) | administrador |
| GET | `/cargas` | Historial de cargas | sesión |
| DELETE | `/cargas/{id}` | Borra una carga y sus ventas | administrador |
| GET | `/documentos` | Todas las ventas | sesión |
| GET | `/facturas` | Facturas de proveedores | sesión |
| POST | `/facturas` | Registra una factura (`{proveedor, monto}`) | administrador |
| GET | `/conversaciones` | Chats del usuario | sesión |
| GET | `/conversaciones/{id}/mensajes` | Mensajes de un chat | sesión |
| DELETE | `/conversaciones/{id}` | Borra un chat | sesión |
| POST | `/chat` | Pregunta al asistente (`{conversacion_id, mensaje}`) | sesión |
| GET | `/salud` | Revisa la conexión a la base | — |

La sesión se envía en el encabezado `Authorization: Bearer <token>`.

## Libro de ventas

Solo se acepta el libro real (hoja LIBROV): encabezado con `FECHA`, `NRO.BOL`, `NETO`, `IVA`, `TOTAL`,
`FORMA 1`, `MONTO 1`… Las filas de título y la fila final de totales se descartan solas.

- Efectivo y tarjeta tienen numeraciones distintas: una boleta se identifica por serie + número.
- Si una boleta ya existe, se omite y se cuenta en "omitidos".
- Si un medio de pago no está en la tabla `medio_pago`, la carga se rechaza indicando cuál es.
- Las temporadas (julio a junio) que falten se crean automáticamente.

## Estructura

```
app/
├── main.py        # crea la API, CORS y rutas
├── config.py      # lee el .env
├── db.py          # conexión y tablas
├── security.py    # contraseñas cifradas (PBKDF2) y tokens firmados (HMAC)
├── etl.py         # lectura del Excel con pandas
├── analisis.py    # resumen financiero que se envía a Gemini
├── gemini.py      # llamada a Gemini con requests
├── formato.py     # fechas y montos en formato chileno
└── routers/       # auth, ventas, facturas, chat
db/
├── schema.sql          # estructura de la base, sin datos
├── seed_catalogos.sql  # medios de pago y temporadas
├── crear_db.py         # crea la base y ejecuta los SQL
└── crear_usuario.py    # crea o actualiza un usuario
```
