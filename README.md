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

## Actualizar una instalación existente

Antes de iniciar la versión que permite eliminar proveedores del catálogo, ejecuta
`python db/migrar_proveedores.py` desde el directorio del backend con la configuración de la base correspondiente.
La migración se puede repetir y conserva los proveedores y las facturas existentes.
El script `python db/crear_db.py` aplica la misma migración cuando el esquema ya existe.

Para las metas mensuales, ejecuta `python db/migrar_metas.py` (crea la tabla `meta_mensual` si no existe).
`python db/crear_db.py` también la crea cuando el esquema ya existe, y con `--con-catalogos` carga los medios de pago
y temporadas sin borrar datos.

## Endpoints

| Método | Ruta | Qué hace | Requiere |
|---|---|---|---|
| POST | `/auth/login` | Entrega el token de sesión (`{email, password}`) | — |
| GET | `/auth/me` | Datos del usuario conectado | sesión |
| GET | `/usuarios` | Lista las cuentas del dashboard | administrador |
| POST | `/usuarios` | Crea una cuenta con correo, contraseña y rol | administrador |
| PUT | `/usuarios/{id}` | Edita nombre, correo, rol y, opcionalmente, contraseña | administrador |
| DELETE | `/usuarios/{id}` | Elimina una cuenta sin facturas asociadas | administrador |
| POST | `/upload?nombre=archivo.xlsx` | Carga el libro de ventas (cuerpo binario `application/octet-stream`) | administrador |
| GET | `/cargas` | Historial de cargas | sesión |
| DELETE | `/cargas/{id}` | Borra una carga y sus ventas | administrador |
| GET | `/documentos` | Todas las ventas | sesión |
| GET | `/facturas` | Facturas de proveedores | sesión |
| POST | `/facturas` | Registra una factura para un proveedor activo (`{id_proveedor, monto}`) | administrador |
| GET | `/metas` | Metas de ingresos por mes (`[{mes: "2026-03", monto, usuario, actualizado}]`) | sesión |
| PUT | `/metas/{AAAA-MM}` | Crea o reemplaza la meta de ese mes (`{monto}`) | administrador |
| DELETE | `/metas/{AAAA-MM}` | Borra la meta de ese mes | administrador |
| GET | `/conversaciones` | Chats del usuario | sesión |
| GET | `/conversaciones/{id}/mensajes` | Mensajes de un chat | sesión |
| DELETE | `/conversaciones/{id}` | Borra un chat | sesión |
| POST | `/chat` | Pregunta al asistente (`{conversacion_id, mensaje}`) | sesión |
| GET | `/salud` | Revisa la conexión a la base | — |

La sesión se envía en el encabezado `Authorization: Bearer <token>`.

En el dashboard, el acceso **Administrar usuarios** aparece al pie del menú lateral al iniciar sesión como administrador. Las cuentas nuevas pueden tener rol **Lector** o **Administrador**.

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
