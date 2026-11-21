"""Resumen financiero calculado en PostgreSQL que se envia a Gemini como contexto.

La IA no recibe boletas una por una: solo totales agregados.
"""

from sqlalchemy import text

from app.formato import DIAS, MESES, clp

_SQL_MESES = text("""
    SELECT to_char(v.fecha, 'YYYY-MM') AS mes,
           COUNT(*) FILTER (WHERE mp.cuenta_como_ingreso)              AS boletas,
           COALESCE(SUM(v.valor_total) FILTER (WHERE mp.cuenta_como_ingreso), 0) AS total,
           COALESCE(SUM(v.valor_neto)  FILTER (WHERE mp.cuenta_como_ingreso), 0) AS neto,
           COALESCE(SUM(v.valor_iva)   FILTER (WHERE mp.cuenta_como_ingreso), 0) AS iva,
           COALESCE(SUM(v.valor_total) FILTER (WHERE NOT mp.cuenta_como_ingreso), 0) AS no_ingreso
    FROM venta v JOIN medio_pago mp ON mp.id_medio = v.id_medio
    GROUP BY 1 ORDER BY 1
""")

_SQL_MEDIOS = text("""
    SELECT mp.nombre_medio, mp.cuenta_como_ingreso, COUNT(*) AS boletas, SUM(v.valor_total) AS total
    FROM venta v JOIN medio_pago mp ON mp.id_medio = v.id_medio
    GROUP BY 1, 2 ORDER BY total DESC
""")

_SQL_DIAS = text("""
    SELECT EXTRACT(ISODOW FROM v.fecha)::int AS dia, COUNT(*) AS boletas, SUM(v.valor_total) AS total,
           COUNT(DISTINCT v.fecha) AS jornadas
    FROM venta v JOIN medio_pago mp ON mp.id_medio = v.id_medio
    WHERE mp.cuenta_como_ingreso
    GROUP BY 1 ORDER BY 1
""")

_SQL_MEJORES_DIAS = text("""
    SELECT v.fecha, SUM(v.valor_total) AS total, COUNT(*) AS boletas
    FROM venta v JOIN medio_pago mp ON mp.id_medio = v.id_medio
    WHERE mp.cuenta_como_ingreso
    GROUP BY 1 ORDER BY total DESC LIMIT 5
""")

_SQL_TEMPORADAS = text("""
    SELECT temporada, ventas_ingreso, ventas_no_ingreso, cantidad_boletas, compras, diferencia
    FROM v_resumen_temporada
    WHERE cantidad_boletas > 0 OR compras > 0
    ORDER BY temporada
""")

_SQL_FACTURAS = text("""
    SELECT to_char(f.fecha_factura, 'YYYY-MM') AS mes, COUNT(*) AS cantidad, SUM(f.monto_bruto) AS total
    FROM factura f GROUP BY 1 ORDER BY 1
""")

_SQL_PROVEEDORES = text("""
    SELECT p.nombre, COUNT(*) AS cantidad, SUM(f.monto_bruto) AS total
    FROM factura f JOIN proveedor p ON p.id_proveedor = f.id_proveedor
    GROUP BY 1 ORDER BY total DESC LIMIT 10
""")


def _mes(clave: str) -> str:
    anio, mes = clave.split("-")
    return f"{MESES[int(mes) - 1]} {anio}"


def resumen_financiero(con) -> str:
    meses = con.execute(_SQL_MESES).mappings().all()
    if not meses:
        return "No hay ventas cargadas todavía."

    lineas = []
    total = sum(m["total"] for m in meses)
    boletas = sum(m["boletas"] for m in meses)
    lineas.append("== VENTAS (solo medios que cuentan como ingreso; montos en CLP con IVA) ==")
    lineas.append(f"Período con datos: {_mes(meses[0]['mes'])} a {_mes(meses[-1]['mes'])}")
    lineas.append(f"Total vendido: {clp(total)} en {boletas} boletas. "
                  f"Ticket promedio: {clp(total / boletas if boletas else 0)}")
    lineas.append("Por mes (mes | boletas | total | neto | IVA débito | pendiente/no ingreso):")
    for m in meses:
        lineas.append(f"- {_mes(m['mes'])} | {m['boletas']} | {clp(m['total'])} | {clp(m['neto'])} | "
                      f"{clp(m['iva'])} | {clp(m['no_ingreso'])}")

    lineas.append("\n== POR TEMPORADA (julio a junio) ==")
    for t in con.execute(_SQL_TEMPORADAS).mappings():
        lineas.append(f"- {t['temporada']}: ventas {clp(t['ventas_ingreso'])}, boletas {t['cantidad_boletas']}, "
                      f"no ingreso {clp(t['ventas_no_ingreso'])}, compras {clp(t['compras'])}, "
                      f"diferencia ventas - compras {clp(t['diferencia'])}")

    lineas.append("\n== POR MEDIO DE PAGO ==")
    for m in con.execute(_SQL_MEDIOS).mappings():
        nota = "" if m["cuenta_como_ingreso"] else " (no cuenta como ingreso)"
        lineas.append(f"- {m['nombre_medio']}{nota}: {m['boletas']} boletas, {clp(m['total'])}")

    lineas.append("\n== POR DÍA DE LA SEMANA (todo el período) ==")
    for d in con.execute(_SQL_DIAS).mappings():
        promedio = d["total"] / d["jornadas"] if d["jornadas"] else 0
        lineas.append(f"- {DIAS[d['dia'] - 1]}: {clp(d['total'])} en {d['boletas']} boletas, "
                      f"promedio por jornada {clp(promedio)}")

    lineas.append("\n== 5 MEJORES DÍAS ==")
    for d in con.execute(_SQL_MEJORES_DIAS).mappings():
        lineas.append(f"- {d['fecha'].strftime('%d-%m-%Y')} ({DIAS[d['fecha'].weekday()]}): "
                      f"{clp(d['total'])} en {d['boletas']} boletas")

    facturas = con.execute(_SQL_FACTURAS).mappings().all()
    lineas.append("\n== FACTURAS DE PROVEEDORES (compras, montos brutos con IVA) ==")
    if not facturas:
        lineas.append("No hay facturas registradas.")
    else:
        bruto = sum(f["total"] for f in facturas)
        lineas.append(f"Total: {sum(f['cantidad'] for f in facturas)} facturas por {clp(bruto)}. "
                      f"Crédito fiscal estimado (bruto/1,19*0,19): {clp(bruto / 1.19 * 0.19)}")
        for f in facturas:
            lineas.append(f"- {_mes(f['mes'])}: {f['cantidad']} facturas, {clp(f['total'])}, "
                          f"crédito fiscal estimado {clp(f['total'] / 1.19 * 0.19)}")
        lineas.append("Principales proveedores:")
        for p in con.execute(_SQL_PROVEEDORES).mappings():
            lineas.append(f"- {p['nombre']}: {p['cantidad']} facturas, {clp(p['total'])}")

    return "\n".join(lineas)
