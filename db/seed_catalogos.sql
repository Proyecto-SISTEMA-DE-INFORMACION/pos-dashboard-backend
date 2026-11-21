-- =====================================================================
-- Catalogos iniciales: Dashboard libro de ventas botilleria
-- Ejecutar despues de schema.sql. Sin estos datos no se pueden cargar
-- ventas: cada venta necesita su medio de pago y su temporada.
-- Se puede ejecutar mas de una vez: no duplica filas.
-- =====================================================================

BEGIN;

SET search_path TO botilleria;

INSERT INTO medio_pago (nombre_medio, serie, cuenta_como_ingreso) VALUES
    ('EFECTIVO',          'EFECTIVO', TRUE),
    ('T. DEBITO',         'TARJETA',  TRUE),
    ('T. CREDITO',        'TARJETA',  TRUE),
    ('PENDIENTE DE PAGO', 'EFECTIVO', FALSE),
    ('PAN ENCARGADO',     'EFECTIVO', FALSE)
ON CONFLICT (nombre_medio) DO NOTHING;

-- Temporadas de julio a junio (cada verano queda completo en una temporada)
INSERT INTO temporada (nombre, fecha_inicio, fecha_fin) VALUES
    ('2023-2024', DATE '2023-07-01', DATE '2024-06-30'),
    ('2024-2025', DATE '2024-07-01', DATE '2025-06-30'),
    ('2025-2026', DATE '2025-07-01', DATE '2026-06-30'),
    ('2026-2027', DATE '2026-07-01', DATE '2027-06-30')
ON CONFLICT (nombre) DO NOTHING;

COMMIT;
