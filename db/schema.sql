-- =====================================================================
-- Esquema: Dashboard libro de ventas botilleria
-- Motor: PostgreSQL 16
-- Crea solo la estructura (tablas, restricciones, indices, triggers y
-- vista), sin datos. Los catalogos iniciales estan en seed_catalogos.sql.
--
-- Uso:
--   createdb botilleria
--   psql -U postgres -d botilleria -f db/schema.sql
--   psql -U postgres -d botilleria -f db/seed_catalogos.sql
-- =====================================================================

BEGIN;

-- Para recrear el esquema desde cero (BORRA TODOS LOS DATOS), descomente:
-- DROP SCHEMA IF EXISTS botilleria CASCADE;


CREATE SCHEMA botilleria;
SET search_path TO botilleria;

-- ---------------------------------------------------------------------
-- 1. USUARIO: personas que usan el software
-- ---------------------------------------------------------------------
CREATE TABLE usuario (
    id_usuario       INTEGER      GENERATED ALWAYS AS IDENTITY,
    email            VARCHAR(255) NOT NULL,
    nombre           VARCHAR(100) NOT NULL,
    contrasena_hash  VARCHAR(255) NOT NULL,
    tipo_usuario     VARCHAR(20)  NOT NULL DEFAULT 'LECTOR',
    CONSTRAINT pk_usuario PRIMARY KEY (id_usuario),
    CONSTRAINT ck_usuario_tipo CHECK (tipo_usuario IN ('ADMINISTRADOR', 'LECTOR')),
    CONSTRAINT ck_usuario_email CHECK (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
    CONSTRAINT ck_usuario_nombre_no_vacio CHECK (btrim(nombre) <> '')
);

-- El login es por email: "Admin@Pabst.cl" y "admin@pabst.cl" son el mismo usuario
CREATE UNIQUE INDEX uq_usuario_email ON usuario (lower(email));

-- ---------------------------------------------------------------------
-- 2. CONVERSACION: cada chat con la IA
-- ---------------------------------------------------------------------
CREATE TABLE conversacion (
    id_conversacion       INTEGER      GENERATED ALWAYS AS IDENTITY,
    id_usuario            INTEGER      NOT NULL,
    titulo                VARCHAR(100) NOT NULL DEFAULT 'Nueva conversación',
    fecha_inicio          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    fecha_ultimo_mensaje  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT pk_conversacion PRIMARY KEY (id_conversacion),
    CONSTRAINT fk_conversacion_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuario (id_usuario) ON DELETE CASCADE,
    CONSTRAINT ck_conversacion_fechas CHECK (fecha_ultimo_mensaje >= fecha_inicio)
);

CREATE INDEX ix_conversacion_usuario_fecha
    ON conversacion (id_usuario, fecha_ultimo_mensaje DESC);

-- ---------------------------------------------------------------------
-- 3. MENSAJE: cada mensaje de una conversacion (usuario o IA)
-- ---------------------------------------------------------------------
CREATE TABLE mensaje (
    id_mensaje           BIGINT       GENERATED ALWAYS AS IDENTITY,
    id_conversacion      INTEGER      NOT NULL,
    rol                  VARCHAR(10)  NOT NULL,
    contenido            TEXT,
    fecha                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    modelo               VARCHAR(50),
    estado               VARCHAR(10)  NOT NULL DEFAULT 'OK',
    mensaje_error        TEXT,
    datos_enviados       TEXT,
    tiempo_respuesta_ms  INTEGER,
    tokens               INTEGER,
    CONSTRAINT pk_mensaje PRIMARY KEY (id_mensaje),
    CONSTRAINT fk_mensaje_conversacion FOREIGN KEY (id_conversacion)
        REFERENCES conversacion (id_conversacion) ON DELETE CASCADE,
    CONSTRAINT ck_mensaje_rol CHECK (rol IN ('USUARIO', 'IA')),
    CONSTRAINT ck_mensaje_estado CHECK (estado IN ('OK', 'ERROR', 'LIMITE')),
    -- Un mensaje correcto siempre tiene texto; uno fallido debe explicar el error
    CONSTRAINT ck_mensaje_contenido_ok CHECK (estado <> 'OK' OR contenido IS NOT NULL),
    CONSTRAINT ck_mensaje_error CHECK (estado = 'OK' OR mensaje_error IS NOT NULL),
    -- Los mensajes del usuario siempre se guardan con estado OK y sin datos de la IA
    CONSTRAINT ck_mensaje_usuario CHECK (
        rol = 'IA' OR (estado = 'OK' AND modelo IS NULL AND tiempo_respuesta_ms IS NULL)
    ),
    CONSTRAINT ck_mensaje_tiempo CHECK (tiempo_respuesta_ms IS NULL OR tiempo_respuesta_ms >= 0),
    CONSTRAINT ck_mensaje_tokens CHECK (tokens IS NULL OR tokens >= 0)
);

CREATE INDEX ix_mensaje_conversacion_fecha ON mensaje (id_conversacion, fecha);

-- ---------------------------------------------------------------------
-- 4. TEMPORADA: periodos de analisis (cruzan dos anios calendario)
-- ---------------------------------------------------------------------
CREATE TABLE temporada (
    id_temporada  INTEGER     GENERATED ALWAYS AS IDENTITY,
    nombre        VARCHAR(20) NOT NULL,
    fecha_inicio  DATE        NOT NULL,
    fecha_fin     DATE        NOT NULL,
    CONSTRAINT pk_temporada PRIMARY KEY (id_temporada),
    CONSTRAINT uq_temporada_nombre UNIQUE (nombre),
    CONSTRAINT ck_temporada_fechas CHECK (fecha_fin >= fecha_inicio),
    -- Dos temporadas no pueden cubrir el mismo dia
    CONSTRAINT ex_temporada_sin_traslape EXCLUDE USING gist (
        daterange(fecha_inicio, fecha_fin, '[]') WITH &&
    )
);

-- ---------------------------------------------------------------------
-- 5. MEDIO_PAGO: catalogo de medios de pago
-- ---------------------------------------------------------------------
CREATE TABLE medio_pago (
    id_medio             INTEGER     GENERATED ALWAYS AS IDENTITY,
    nombre_medio         VARCHAR(30) NOT NULL,
    serie                VARCHAR(10) NOT NULL,
    cuenta_como_ingreso  BOOLEAN     NOT NULL DEFAULT TRUE,
    CONSTRAINT pk_medio_pago PRIMARY KEY (id_medio),
    CONSTRAINT uq_medio_pago_nombre UNIQUE (nombre_medio),
    CONSTRAINT ck_medio_pago_serie CHECK (serie IN ('EFECTIVO', 'TARJETA')),
    -- Permite que VENTA verifique que su serie coincide con la del medio de pago
    CONSTRAINT uq_medio_pago_id_serie UNIQUE (id_medio, serie)
);

-- ---------------------------------------------------------------------
-- 6. ARCHIVO: cada carga de un Excel del libro de ventas
-- ---------------------------------------------------------------------
CREATE TABLE archivo (
    id_carga            INTEGER      GENERATED ALWAYS AS IDENTITY,
    nombre_archivo      VARCHAR(255) NOT NULL,
    fecha_carga         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    registros_nuevos    INTEGER      NOT NULL DEFAULT 0,
    registros_omitidos  INTEGER      NOT NULL DEFAULT 0,
    CONSTRAINT pk_archivo PRIMARY KEY (id_carga),
    CONSTRAINT ck_archivo_nuevos CHECK (registros_nuevos >= 0),
    CONSTRAINT ck_archivo_omitidos CHECK (registros_omitidos >= 0)
);

-- ---------------------------------------------------------------------
-- 7. VENTA: una fila por boleta
-- ---------------------------------------------------------------------
CREATE TABLE venta (
    id_venta       BIGINT      GENERATED ALWAYS AS IDENTITY,
    serie          VARCHAR(10) NOT NULL,
    numero_boleta  VARCHAR(10) NOT NULL,
    fecha          DATE        NOT NULL,
    valor_neto     INTEGER     NOT NULL,
    valor_iva      INTEGER     NOT NULL,
    valor_total    INTEGER     NOT NULL,
    id_medio       INTEGER     NOT NULL,
    id_carga       INTEGER     NOT NULL,
    id_temporada   INTEGER     NOT NULL,
    CONSTRAINT pk_venta PRIMARY KEY (id_venta),
    -- Efectivo y tarjeta tienen numeraciones independientes
    CONSTRAINT uq_venta_serie_numero UNIQUE (serie, numero_boleta),
    CONSTRAINT ck_venta_serie CHECK (serie IN ('EFECTIVO', 'TARJETA')),
    CONSTRAINT ck_venta_numero CHECK (numero_boleta ~ '^[0-9]{1,10}$'),
    CONSTRAINT ck_venta_montos_positivos CHECK (valor_neto >= 0 AND valor_iva >= 0 AND valor_total >= 0),
    CONSTRAINT ck_venta_total CHECK (valor_neto + valor_iva = valor_total),
    -- La serie de la venta debe ser la misma de su medio de pago
    CONSTRAINT fk_venta_medio_pago FOREIGN KEY (id_medio, serie)
        REFERENCES medio_pago (id_medio, serie) ON DELETE RESTRICT,
    CONSTRAINT fk_venta_archivo FOREIGN KEY (id_carga)
        REFERENCES archivo (id_carga) ON DELETE RESTRICT,
    CONSTRAINT fk_venta_temporada FOREIGN KEY (id_temporada)
        REFERENCES temporada (id_temporada) ON DELETE RESTRICT
);

CREATE INDEX ix_venta_fecha     ON venta (fecha);
CREATE INDEX ix_venta_temporada ON venta (id_temporada);
CREATE INDEX ix_venta_medio     ON venta (id_medio);
CREATE INDEX ix_venta_carga     ON venta (id_carga);

-- ---------------------------------------------------------------------
-- 8. PROVEEDOR: catalogo de proveedores
-- ---------------------------------------------------------------------
CREATE TABLE proveedor (
    id_proveedor  INTEGER      GENERATED ALWAYS AS IDENTITY,
    nombre        VARCHAR(100) NOT NULL,
    CONSTRAINT pk_proveedor PRIMARY KEY (id_proveedor),
    CONSTRAINT ck_proveedor_nombre_no_vacio CHECK (btrim(nombre) <> '')
);

-- "CCU", "ccu" y " Ccu " se consideran el mismo proveedor
CREATE UNIQUE INDEX uq_proveedor_nombre ON proveedor (upper(btrim(nombre)));

-- ---------------------------------------------------------------------
-- 9. FACTURA: compras ingresadas manualmente
-- ---------------------------------------------------------------------
CREATE TABLE factura (
    id_factura     INTEGER     GENERATED ALWAYS AS IDENTITY,
    id_proveedor   INTEGER     NOT NULL,
    monto_bruto    INTEGER     NOT NULL,
    fecha_factura  DATE        NOT NULL DEFAULT CURRENT_DATE,
    id_usuario     INTEGER     NOT NULL,
    fecha_ingreso  TIMESTAMPTZ NOT NULL DEFAULT now(),
    id_temporada   INTEGER     NOT NULL,
    CONSTRAINT pk_factura PRIMARY KEY (id_factura),
    CONSTRAINT ck_factura_monto CHECK (monto_bruto > 0),
    CONSTRAINT fk_factura_proveedor FOREIGN KEY (id_proveedor)
        REFERENCES proveedor (id_proveedor) ON DELETE RESTRICT,
    CONSTRAINT fk_factura_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuario (id_usuario) ON DELETE RESTRICT,
    CONSTRAINT fk_factura_temporada FOREIGN KEY (id_temporada)
        REFERENCES temporada (id_temporada) ON DELETE RESTRICT
);

CREATE INDEX ix_factura_temporada ON factura (id_temporada);
CREATE INDEX ix_factura_proveedor ON factura (id_proveedor);
CREATE INDEX ix_factura_fecha     ON factura (fecha_factura);

-- ---------------------------------------------------------------------
-- Trigger: asigna id_temporada segun la fecha de la venta o factura
-- (el software no necesita enviarlo)
-- ---------------------------------------------------------------------
CREATE FUNCTION asignar_temporada() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_fecha DATE;
BEGIN
    IF TG_TABLE_NAME = 'venta' THEN
        v_fecha := NEW.fecha;
    ELSE
        v_fecha := NEW.fecha_factura;
    END IF;

    SELECT t.id_temporada INTO NEW.id_temporada
    FROM temporada t
    WHERE v_fecha BETWEEN t.fecha_inicio AND t.fecha_fin;

    IF NEW.id_temporada IS NULL THEN
        RAISE EXCEPTION 'No existe una temporada que contenga la fecha %', v_fecha
            USING HINT = 'Agregue la temporada en la tabla temporada antes de cargar el dato.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER tg_venta_temporada
    BEFORE INSERT OR UPDATE OF fecha ON venta
    FOR EACH ROW EXECUTE FUNCTION asignar_temporada();

CREATE TRIGGER tg_factura_temporada
    BEFORE INSERT OR UPDATE OF fecha_factura ON factura
    FOR EACH ROW EXECUTE FUNCTION asignar_temporada();

-- ---------------------------------------------------------------------
-- Trigger: actualiza fecha_ultimo_mensaje al guardar un mensaje
-- ---------------------------------------------------------------------
CREATE FUNCTION actualizar_ultimo_mensaje() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE conversacion
       SET fecha_ultimo_mensaje = GREATEST(fecha_ultimo_mensaje, NEW.fecha)
     WHERE id_conversacion = NEW.id_conversacion;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tg_mensaje_ultimo
    AFTER INSERT ON mensaje
    FOR EACH ROW EXECUTE FUNCTION actualizar_ultimo_mensaje();

-- ---------------------------------------------------------------------
-- Vista para el dashboard: ventas, compras y diferencia por temporada
-- ---------------------------------------------------------------------
CREATE VIEW v_resumen_temporada AS
SELECT t.id_temporada,
       t.nombre AS temporada,
       COALESCE(v.ventas_ingreso, 0)  AS ventas_ingreso,
       COALESCE(v.ventas_pendientes, 0) AS ventas_no_ingreso,
       COALESCE(v.cantidad_boletas, 0) AS cantidad_boletas,
       COALESCE(f.compras, 0)         AS compras,
       COALESCE(v.ventas_ingreso, 0) - COALESCE(f.compras, 0) AS diferencia
FROM temporada t
LEFT JOIN (
    SELECT ve.id_temporada,
           SUM(ve.valor_total) FILTER (WHERE mp.cuenta_como_ingreso)     AS ventas_ingreso,
           SUM(ve.valor_total) FILTER (WHERE NOT mp.cuenta_como_ingreso) AS ventas_pendientes,
           COUNT(*) AS cantidad_boletas
    FROM venta ve
    JOIN medio_pago mp ON mp.id_medio = ve.id_medio
    GROUP BY ve.id_temporada
) v ON v.id_temporada = t.id_temporada
LEFT JOIN (
    SELECT id_temporada, SUM(monto_bruto) AS compras
    FROM factura
    GROUP BY id_temporada
) f ON f.id_temporada = t.id_temporada;

COMMIT;
