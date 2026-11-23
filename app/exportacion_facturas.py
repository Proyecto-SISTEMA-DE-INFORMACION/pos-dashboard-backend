"""Libro Excel de compras con gráficos editables y datos de origen."""

from collections import defaultdict
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def _hoja(libro, nombre, encabezados, filas, anchos):
    hoja = libro.create_sheet(nombre)
    hoja.append(encabezados)
    for fila in filas:
        hoja.append(fila)
        for celda, valor in zip(hoja[hoja.max_row], fila):
            if isinstance(valor, str):
                celda.data_type = "s"
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    for indice, ancho in enumerate(anchos, 1):
        hoja.column_dimensions[get_column_letter(indice)].width = ancho
    hoja.freeze_panes = "B2"
    return hoja


def _grafico(hoja, titulo, columna, unidad, posicion):
    if hoja.max_row < 2:
        return
    grafico = BarChart()
    grafico.type = "bar"
    grafico.title = titulo
    grafico.y_axis.title = unidad
    grafico.legend = None
    grafico.width = 23
    grafico.height = min(30, max(8, (hoja.max_row - 1) * 0.55 + 4))
    grafico.add_data(Reference(hoja, min_col=columna, min_row=1, max_row=hoja.max_row), titles_from_data=True)
    grafico.set_categories(Reference(hoja, min_col=1, min_row=2, max_row=hoja.max_row))
    hoja.add_chart(grafico, posicion)


def generar_excel(facturas, debito):
    compras = defaultdict(lambda: [0, 0])
    for factura in facturas:
        total = compras[factura["prov"]]
        total[0] += 1
        total[1] += factura["monto"]
    credito = sum(total[1] for total in compras.values()) * 19 / 119

    libro = Workbook()
    libro.remove(libro.active)
    iva = _hoja(libro, "IVA", ["Concepto", "Monto CLP"], [
        ["IVA débito de ventas vigentes", debito],
        ["IVA crédito estimado de compras", credito],
        ["Saldo estimado", debito - credito],
    ], [42, 20])
    iva["A6"] = "Histórico registrado. Crédito estimado aplicando 19/119 al monto bruto."
    _grafico(iva, "Comparación de IVA", 2, "CLP", "D2")

    proveedores = sorted(compras.items(), key=lambda item: (-item[1][1], item[0]))
    for nombre, encabezado, columna, unidad in [
        ("Cantidad por proveedor", "Facturas", 0, "Facturas"),
        ("Compras por proveedor", "Monto bruto CLP", 1, "CLP"),
        ("Crédito por proveedor", "IVA crédito estimado CLP", 1, "CLP"),
    ]:
        filas = [(proveedor, totales[columna] * 19 / 119 if nombre == "Crédito por proveedor" else totales[columna])
                 for proveedor, totales in proveedores]
        hoja = _hoja(libro, nombre, ["Proveedor", encabezado], filas, [40, 27])
        _grafico(hoja, nombre, 2, unidad, "D2")

    _hoja(libro, "Facturas", ["Proveedor", "Fecha de registro", "Monto bruto CLP", "IVA crédito estimado CLP"],
          [(f["prov"], f["fecha"], f["monto"], f["monto"] * 19 / 119) for f in facturas], [40, 25, 20, 29])
    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()
