# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from .config import SQLALCHEMY_DATABASE_URI, DEFAULT_USERNAME, DEFAULT_PASSWORD, SECRET_KEY
from .models import db, Transaction, Caja
from flask import jsonify
import requests
from .utils import get_dollar_price
import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from markupsafe import Markup

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = SECRET_KEY
db.init_app(app)

def login_required(f):
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route('/')
@login_required
def index():
    dollar_prices = get_dollar_price()
    if dollar_prices is None:
        flash("No se pudo obtener el precio del dólar blue. Intente nuevamente más tarde.", "error")
    cajas = Caja.query.order_by(Caja.fecha_hora.desc()).first()
    return render_template('index.html', 
                           dollar_prices=dollar_prices, 
                           cajas=cajas)


def format_currency(value):
    """
    Formatea un número como moneda.
    """
    return Markup(f"${value:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

app.jinja_env.filters['format_currency'] = format_currency


@app.route('/caja/inicial', methods=['POST'])
@login_required
def set_initial_cash():
    """
    Configura la caja inicial o agrega fondos a una caja existente.
    """
    # Obtener los valores del formulario
    pesos = request.form.get('pesos', type=float, default=0.0)
    dolares = request.form.get('dolares', type=float, default=0.0)

    # Verificar si ya existe una caja
    caja_existente = Caja.query.order_by(Caja.id.desc()).first()

    if caja_existente:
        # Agregar fondos a la caja existente
        caja_existente.pesos += pesos
        caja_existente.dolares += dolares
        db.session.commit()
        flash("Fondos agregados correctamente a la caja.", "success")
    else:
        # Configurar una nueva caja
        nueva_caja = Caja(pesos=pesos, dolares=dolares, fecha_hora=datetime.datetime.now())
        db.session.add(nueva_caja)
        db.session.commit()
        flash("Caja inicial configurada correctamente.", "success")

    return redirect(url_for('manage_caja'))


@app.route('/caja', methods=['GET'])
@login_required
def manage_caja():
    """
    Renderiza la página de gestión de la caja.
    """
    # Obtener el estado actual de la caja
    caja = Caja.query.order_by(Caja.id.desc()).first()
    return render_template('caja.html', caja=caja)


def redondear(valor, precision=2):
    """
    Redondea un valor Decimal a la precisión especificada.
    """
    return float(Decimal(valor).quantize(Decimal(f'1.{"0" * precision}'), rounding=ROUND_HALF_UP))


def calcular_impacto(tipo, monto, tasa_cambio, precio_compra=None, precio_venta=None, comision=0.0):
    """
    Calcula el impacto en la caja para transacciones con comisiones, precios personalizados y márgenes.
    """
    monto = Decimal(monto)
    tasa_cambio = Decimal(tasa_cambio)
    comision = Decimal(comision)

    if tipo == 'compra_dolares':
        # Restamos pesos y sumamos dólares
        pesos_delta = -monto * tasa_cambio
        dolares_delta = monto
        return round(pesos_delta, 2), round(dolares_delta, 2)

    elif tipo == 'venta_dolares':
        margen = Decimal(precio_venta) - Decimal(precio_compra)
        pesos_delta = margen * monto
        dolares_delta = -monto
        return round(pesos_delta, 2), round(dolares_delta, 2)

    elif tipo == 'compra_pesos':
        pesos_delta = monto
        dolares_delta = -monto / tasa_cambio
        return round(pesos_delta, 2), round(dolares_delta, 2)

    elif tipo == 'venta_pesos':
        pesos_delta = -monto
        dolares_delta = monto / tasa_cambio
        return round(pesos_delta, 2), round(dolares_delta, 2)

    elif tipo == 'cable_subida':
        # Se envían dólares y se descuenta la comisión
        comision_dolares = monto * comision
        pesos_delta = -monto * tasa_cambio
        dolares_delta = monto - comision_dolares
        return round(pesos_delta, 2), round(dolares_delta, 2)

    elif tipo == 'cable_bajada':
        # Se reciben dólares y se descuenta la comisión
        comision_dolares = monto * comision
        pesos_delta = monto * tasa_cambio
        dolares_delta = -(monto + comision_dolares)
        return round(pesos_delta, 2), round(dolares_delta, 2)

    elif tipo == 'descuento_cheque':
        pesos_delta = -monto
        return round(pesos_delta, 2), Decimal(0)

    return Decimal(0), Decimal(0)


def revertir_impacto(tipo, monto, tasa_cambio, comision=0.0):
    """
    Reversa el impacto de una transacción, considerando el tipo de transacción, comisión y redondeo.
    """
    return calcular_impacto(tipo, -monto, tasa_cambio, comision=comision)


def aplicar_descuento_cheque(pesos_delta, dolares_delta, descuento_cheque):
    """
    Aplica un descuento personalizado a las transacciones por cheques.
    """
    return pesos_delta * (1 - descuento_cheque), dolares_delta * (1 - descuento_cheque)

def procesar_transaccion_basica(tipo, monto, buy_price, sell_price):
    """
    Procesa transacciones básicas de compra/venta de dólares/pesos.
    Redondea los resultados para evitar errores de precisión en el cálculo.
    """
    if tipo == 'compra_dolares':
        pesos_delta = -round(monto * buy_price, 2)  # Restamos pesos
        dolares_delta = round(monto, 2)            # Sumamos dólares
        return pesos_delta, dolares_delta
    elif tipo == 'venta_dolares':
        pesos_delta = round(monto * sell_price, 2)  # Sumamos pesos
        dolares_delta = -round(monto, 2)           # Restamos dólares
        return pesos_delta, dolares_delta
    elif tipo == 'compra_pesos':
        pesos_delta = round(monto, 2)             # Sumamos pesos
        dolares_delta = -round(monto / sell_price, 2)  # Restamos dólares
        return pesos_delta, dolares_delta
    elif tipo == 'venta_pesos':
        pesos_delta = -round(monto, 2)            # Restamos pesos
        dolares_delta = round(monto / buy_price, 2)  # Sumamos dólares
        return pesos_delta, dolares_delta
    return 0, 0


def procesar_transaccion_cable(tipo, monto, buy_price, sell_price, comision):
    """
    Procesa transacciones de cable con comisión.
    Redondea los resultados para evitar errores de precisión en el cálculo.
    """
    comision_total = round(monto * comision, 2)
    if tipo == 'cable_subida':
        # En "cable_subida", el cliente envía dólares, y se descuenta comisión en pesos.
        pesos_a_enviar = round(monto * buy_price * (1 - comision), 2)  # Pesos después de la comisión
        pesos_delta = -pesos_a_enviar  # Restamos los pesos enviados
        dolares_delta = round(monto, 2)  # Sumamos los dólares enviados por el cliente
        return pesos_delta, dolares_delta
    elif tipo == 'cable_bajada':
        # En "cable_bajada", el cliente recibe dólares, y se descuenta comisión en dólares.
        pesos_delta = round(monto * sell_price, 2)  # Pesos recibidos por el cliente
        dolares_a_enviar = round(monto * (1 + comision), 2)  # Dólares con comisión
        dolares_delta = -dolares_a_enviar  # Restamos los dólares enviados
        return pesos_delta, dolares_delta
    return 0, 0

def obtener_precio_compra_previo(tipo):
    """
    Obtiene el precio de compra previo para calcular el margen en transacciones de venta.
    Se basa en la transacción más reciente del mismo tipo.
    """
    if tipo == 'venta_dolares':
        transaccion_compra = Transaction.query.filter_by(tipo='compra_dolares').order_by(Transaction.fecha_hora.desc()).first()
        return Decimal(transaccion_compra.tasa_cambio) if transaccion_compra else None
    elif tipo == 'venta_pesos':
        transaccion_compra = Transaction.query.filter_by(tipo='compra_pesos').order_by(Transaction.fecha_hora.desc()).first()
        return Decimal(transaccion_compra.tasa_cambio) if transaccion_compra else None
    return None

def safe_decimal(value, default=Decimal(0)):
    """
    Convierte un valor a Decimal de manera segura.
    Si la conversión falla, devuelve un valor predeterminado.
    """
    try:
        return Decimal(value)
    except (ValueError, TypeError, InvalidOperation):
        return default

@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    """
    Manejo de transacciones incluyendo compra/venta de dólares y pesos, subida/bajada por cable, 
    descuento por cheque, y cash to cash.
    """
    if request.method == 'POST':
        try:
            tipo = request.form.get('tipo')
            monto = safe_decimal(request.form.get('monto'))
            concepto = request.form.get('concepto', "").strip()
            comision = safe_decimal(request.form.get('comision')) / 100
            descuento_cheque = safe_decimal(request.form.get('descuento_cheque')) / 100
            precio_compra = safe_decimal(request.form.get('precio_compra')) if 'precio_compra' in request.form else None
            precio_venta = safe_decimal(request.form.get('precio_venta')) if 'precio_venta' in request.form else None
            comision_tipo = request.form.get('comision_tipo', '').strip()
            fecha_hora = datetime.datetime.now()

            if monto <= 0:
                flash("El monto debe ser mayor a cero.", "error")
                return redirect(url_for('transactions'))

            caja = Caja.query.order_by(Caja.id.desc()).first()
            if not caja:
                flash("Primero debes configurar la caja inicial.", "error")
                return redirect(url_for('manage_caja'))

            caja_pesos = safe_decimal(caja.pesos)
            caja_dolares = safe_decimal(caja.dolares)

            if tipo in ['compra_dolares', 'compra_pesos'] and not precio_compra:
                flash("Debe ingresar el precio de compra.", "error")
                return redirect(url_for('transactions'))

            if tipo in ['venta_dolares', 'venta_pesos']:
                if not precio_venta:
                    flash("Debe ingresar el precio de venta.", "error")
                    return redirect(url_for('transactions'))
                precio_compra = obtener_precio_compra_previo(tipo)
                if not precio_compra:
                    flash("No se encontró un precio de compra previo para calcular el margen.", "error")
                    return redirect(url_for('transactions'))

            # Lógica para cash_to_cash
            if tipo == 'cash_to_cash':
                if comision_tipo == 'pagar':
                    dolares_delta = -(monto + (monto * comision))
                elif comision_tipo == 'recibir':
                    dolares_delta = -(monto - (monto * comision))
                else:
                    flash("Debe especificar si paga o recibe comisión.", "error")
                    return redirect(url_for('transactions'))
                pesos_delta = 0  # No hay impacto en pesos para cash_to_cash
            else:
                # Calcular impacto en pesos y dólares para otros tipos de transacción
                pesos_delta, dolares_delta = calcular_impacto(
                    tipo, monto, precio_compra or precio_venta,
                    precio_compra, precio_venta, comision
                )

            if caja_pesos + pesos_delta < 0 or caja_dolares + dolares_delta < 0:
                flash("Fondos insuficientes en la caja.", "error")
                return redirect(url_for('transactions'))

            # Actualizar la caja
            caja.pesos = float(caja_pesos + pesos_delta)
            caja.dolares = float(caja_dolares + dolares_delta)

            # Registrar la transacción
            transaccion = Transaction(
                tipo=tipo,
                monto=float(monto),
                concepto=concepto,
                fecha_hora=fecha_hora,
                tasa_cambio=float(precio_compra if tipo in ['compra_dolares', 'compra_pesos'] else precio_venta),
                comision=float(comision if tipo in ['cable_subida', 'cable_bajada', 'cash_to_cash'] else 0.0),
                descuento_cheque=float(descuento_cheque if tipo == 'descuento_cheque' else 0.0)
            )
            db.session.add(transaccion)
            db.session.commit()
            flash("Transacción registrada correctamente.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error al registrar la transacción: {str(e)}", "error")
        return redirect(url_for('transactions'))

    return render_template('transactions.html')

# @app.route('/transactions/delete/<int:transaction_id>', methods=['POST'])
# @login_required
# def delete_transaction(transaction_id):
#     """
#     Elimina una transacción y revierte su impacto en la caja.
#     """
#     transaction = Transaction.query.get(transaction_id)
#     if not transaction:
#         flash('Transacción no encontrada.', 'error')
#         return redirect(url_for('transactions'))

#     caja = Caja.query.order_by(Caja.id.desc()).first()
#     if not caja:
#         flash("Error: No hay una caja configurada.", "error")
#         return redirect(url_for('transactions'))

#     try:
#         transaction_monto = safe_decimal(transaction.monto)
#         transaction_tasa_cambio = safe_decimal(transaction.tasa_cambio)
#         caja_pesos = safe_decimal(caja.pesos)
#         caja_dolares = safe_decimal(caja.dolares)

#         pesos_delta = 0
#         dolares_delta = 0

#         # Revertir impacto según el tipo de transacción
#         if transaction.tipo == 'compra_dolares':
#             pesos_delta = transaction_monto * transaction_tasa_cambio
#             dolares_delta = -transaction_monto
#         elif transaction.tipo == 'venta_dolares':
#             pesos_delta = -transaction_monto * transaction_tasa_cambio
#             dolares_delta = transaction_monto
#         elif transaction.tipo == 'cash_to_cash':
#             if transaction.comision > 0:  # Si hubo comisión
#                 dolares_delta = transaction.monto + (transaction.monto * transaction.comision)
#             else:
#                 dolares_delta = transaction.monto - (transaction.monto * abs(transaction.comision))

#         # Validar fondos antes de eliminar
#         if caja_pesos + pesos_delta < 0 or caja_dolares + dolares_delta < 0:
#             flash("Error: Fondos insuficientes para revertir esta transacción.", "error")
#             return redirect(url_for('transactions'))

#         # Actualizar la caja
#         caja.pesos = float(caja_pesos + pesos_delta)
#         caja.dolares = float(caja_dolares + dolares_delta)

#         # Eliminar la transacción
#         db.session.delete(transaction)
#         db.session.commit()
#         flash('Transacción eliminada correctamente.', 'success')
#     except Exception as e:
#         db.session.rollback()
#         flash(f'Error al eliminar la transacción: {str(e)}', 'error')

#     return redirect(url_for('transactions'))
@app.route('/transactions/delete/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    """
    Elimina una transacción y revierte su impacto en la caja.
    """
    transaction = Transaction.query.get(transaction_id)
    if not transaction:
        flash('Transacción no encontrada.', 'error')
        return redirect(url_for('transactions'))

    caja = Caja.query.order_by(Caja.id.desc()).first()
    if not caja:
        flash("Error: No hay una caja configurada.", "error")
        return redirect(url_for('transactions'))

    try:
        # Convertir valores a Decimal para operaciones consistentes
        transaction_monto = safe_decimal(transaction.monto)
        transaction_tasa_cambio = safe_decimal(transaction.tasa_cambio)
        transaction_comision = safe_decimal(transaction.comision)
        caja_pesos = safe_decimal(caja.pesos)
        caja_dolares = safe_decimal(caja.dolares)

        pesos_delta = Decimal(0)
        dolares_delta = Decimal(0)

        # Revertir impacto según el tipo de transacción
        if transaction.tipo == 'compra_dolares':
            pesos_delta = transaction_monto * transaction_tasa_cambio
            dolares_delta = -transaction_monto
        elif transaction.tipo == 'venta_dolares':
            pesos_delta = -transaction_monto * transaction_tasa_cambio
            dolares_delta = transaction_monto
        elif transaction.tipo == 'compra_pesos':
            pesos_delta = -transaction_monto
            dolares_delta = transaction_monto / transaction_tasa_cambio
        elif transaction.tipo == 'venta_pesos':
            pesos_delta = transaction_monto
            dolares_delta = -transaction_monto / transaction_tasa_cambio
        elif transaction.tipo == 'cable_subida':
            pesos_delta = transaction_monto * transaction_tasa_cambio
            dolares_delta = -(transaction_monto + (transaction_monto * transaction_comision))
        elif transaction.tipo == 'cable_bajada':
            pesos_delta = -transaction_monto * transaction_tasa_cambio
            dolares_delta = transaction_monto + (transaction_monto * transaction_comision)
        elif transaction.tipo == 'cash_to_cash':
            if transaction_comision > 0:  # Si pagó comisión
                dolares_delta = transaction_monto + (transaction_monto * transaction_comision)
            else:  # Si recibió comisión
                dolares_delta = transaction_monto - (transaction_monto * abs(transaction_comision))
        elif transaction.tipo == 'descuento_cheque':
            pesos_delta = transaction_monto
            dolares_delta = Decimal(0)

        # Validar fondos antes de eliminar
        if caja_pesos + pesos_delta < 0 or caja_dolares + dolares_delta < 0:
            flash("Error: Fondos insuficientes para revertir esta transacción.", "error")
            return redirect(url_for('transactions'))

        # Actualizar la caja
        caja.pesos = float(caja_pesos + pesos_delta)
        caja.dolares = float(caja_dolares + dolares_delta)

        # Eliminar la transacción
        db.session.delete(transaction)
        db.session.commit()
        flash('Transacción eliminada correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar la transacción: {str(e)}', 'error')

    return redirect(url_for('transactions'))


@app.route('/transactions/edit/<int:transaction_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):
    """
    Edita una transacción y ajusta su impacto en la caja, incluyendo cash_to_cash.
    """
    transaction = Transaction.query.get(transaction_id)
    if not transaction:
        flash('Transacción no encontrada.', 'error')
        return redirect(url_for('historial'))

    caja = Caja.query.order_by(Caja.id.desc()).first()
    if not caja:
        flash("Error: No hay una caja configurada.", "error")
        return redirect(url_for('historial'))

    if request.method == 'POST':
        try:
            # Convertir valores de la caja a Decimal
            caja_pesos = safe_decimal(caja.pesos)
            caja_dolares = safe_decimal(caja.dolares)

            # Revertir el impacto de la transacción original
            pesos_delta_original, dolares_delta_original = 0, 0
            if transaction.tipo == 'cash_to_cash':
                if transaction.comision > 0:  # Si pagó comisión
                    dolares_delta_original = transaction.monto + (transaction.monto * transaction.comision)
                else:  # Si recibió comisión
                    dolares_delta_original = transaction.monto - (transaction.monto * abs(transaction.comision))
            else:
                pesos_delta_original, dolares_delta_original = revertir_impacto(
                    transaction.tipo, transaction.monto, transaction.tasa_cambio, transaction.comision or 0
                )

            caja_pesos += pesos_delta_original
            caja_dolares += dolares_delta_original

            # Validar fondos tras revertir
            if caja_pesos < 0 or caja_dolares < 0:
                flash("Error: No se puede revertir la transacción. Fondos insuficientes.", "error")
                return redirect(url_for('historial'))

            # Obtener los nuevos valores desde el formulario
            nuevo_tipo = request.form.get('type')
            nuevo_monto = safe_decimal(request.form.get('amount'), 0)
            nuevo_tasa_cambio = safe_decimal(request.form.get('exchange_rate'), 0)
            nueva_comision = safe_decimal(request.form.get('comision'), 0) / 100
            comision_tipo = request.form.get('comision_tipo', '')
            nuevo_descuento_cheque = safe_decimal(request.form.get('descuento_cheque'), 0) / 100

            # Calcular el impacto con los nuevos valores
            pesos_delta_nuevo, dolares_delta_nuevo = 0, 0
            if nuevo_tipo == 'cash_to_cash':
                if comision_tipo == 'pagar':
                    dolares_delta_nuevo = -(nuevo_monto + (nuevo_monto * nueva_comision))
                elif comision_tipo == 'recibir':
                    dolares_delta_nuevo = -(nuevo_monto - (nuevo_monto * nueva_comision))
                else:
                    flash("Debe especificar si paga o recibe comisión.", "error")
                    return redirect(url_for('edit_transaction', transaction_id=transaction_id))
            else:
                pesos_delta_nuevo, dolares_delta_nuevo = calcular_impacto(
                    nuevo_tipo, nuevo_monto, nuevo_tasa_cambio, comision=nueva_comision
                )

            # Validar que los valores no sean negativos después del nuevo impacto
            if caja_pesos + pesos_delta_nuevo < 0 or caja_dolares + dolares_delta_nuevo < 0:
                flash("Error: No se puede actualizar la transacción. Fondos insuficientes en la caja.", "error")
                return redirect(url_for('edit_transaction', transaction_id=transaction_id))

            # Aplicar los nuevos cambios en la caja
            caja.pesos = float(caja_pesos + pesos_delta_nuevo)
            caja.dolares = float(caja_dolares + dolares_delta_nuevo)

            # Actualizar la transacción
            transaction.tipo = nuevo_tipo
            transaction.monto = float(nuevo_monto)
            transaction.concepto = request.form['concept']
            transaction.tasa_cambio = float(nuevo_tasa_cambio)
            transaction.comision = float(nueva_comision)
            transaction.fecha_hora = datetime.datetime.now()

            # Guardar los cambios en la base de datos
            db.session.commit()
            flash('Transacción actualizada correctamente y caja recalculada.', 'success')
        except InvalidOperation as e:
            db.session.rollback()
            flash("Error al procesar valores numéricos. Verifique los campos ingresados.", "error")
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la transacción: {str(e)}', 'error')

        return redirect(url_for('historial'))

    return render_template('edit_transactions.html', transaction=transaction)


@app.route('/historial')
@login_required
def historial():
    """
    Vista del historial de transacciones con filtros opcionales.
    """
    tipo_filtro = request.args.get('type')
    concepto_filtro = request.args.get('concept')
    fecha_inicio_filtro = request.args.get('start_date')
    fecha_fin_filtro = request.args.get('end_date')

    # Construcción dinámica del query con filtros
    query = Transaction.query
    if tipo_filtro:
        query = query.filter_by(tipo=tipo_filtro)
    if concepto_filtro:
        query = query.filter(Transaction.concepto.contains(concepto_filtro))
    if fecha_inicio_filtro:
        try:
            fecha_inicio = datetime.datetime.strptime(fecha_inicio_filtro, '%Y-%m-%d')
            query = query.filter(Transaction.fecha_hora >= fecha_inicio)
        except ValueError:
            flash("Formato de fecha de inicio inválido.", "error")
    if fecha_fin_filtro:
        try:
            fecha_fin = datetime.datetime.strptime(fecha_fin_filtro, '%Y-%m-%d') + datetime.timedelta(days=1)
            query = query.filter(Transaction.fecha_hora < fecha_fin)
        except ValueError:
            flash("Formato de fecha de fin inválido.", "error")

    # Ordenar por fecha de transacción
    transacciones = query.order_by(Transaction.fecha_hora.desc()).all()

    return render_template(
        'historial.html',
        transacciones=transacciones,
        tipo_filtro=tipo_filtro,
        concepto_filtro=concepto_filtro,
        fecha_inicio_filtro=fecha_inicio_filtro,
        fecha_fin_filtro=fecha_fin_filtro
    )


@app.route('/stats')
@login_required
def stats():
    """
    Genera estadísticas de transacciones filtradas por rango de tiempo.
    """
    rango = request.args.get('range', 'daily')  # Rango por defecto: diario
    hoy = datetime.datetime.utcnow()

    # Determinar rango de tiempo según el filtro
    if rango == 'daily':
        inicio = hoy.replace(hour=0, minute=0, second=0, microsecond=0)
    elif rango == 'weekly':
        inicio = hoy - datetime.timedelta(days=hoy.weekday())  # Inicio de la semana
    elif rango == 'monthly':
        inicio = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif rango == 'yearly':
        inicio = hoy.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        inicio = datetime.datetime.min  # Sin límite inferior

    # Obtener las transacciones dentro del rango
    transacciones = Transaction.query.filter(Transaction.fecha_hora >= inicio).all()

    # Asegurar que las operaciones usan Decimal
    total_dolares_vendidos = sum(Decimal(t.monto) for t in transacciones if t.tipo == "venta_dolares")
    total_pesos_vendidos = sum(Decimal(t.monto) / Decimal(t.tasa_cambio) for t in transacciones if t.tipo == "venta_pesos")
    total_ganancias = sum(
        max(Decimal(0), (Decimal(t.tasa_cambio) - Decimal(obtener_precio_compra_previo(t.tipo))) * Decimal(t.monto))
        for t in transacciones if t.tipo in ["venta_dolares", "venta_pesos"]
    )
    total_perdidas = sum(
        max(Decimal(0), (Decimal(obtener_precio_compra_previo(t.tipo)) - Decimal(t.tasa_cambio)) * Decimal(t.monto))
        for t in transacciones if t.tipo in ["venta_dolares", "venta_pesos"]
    )
    total_comisiones = sum(
        Decimal(t.monto) * Decimal(t.comision) for t in transacciones if t.tipo in ["cable_subida", "cable_bajada"]
    )
    total_descuentos_cheques = sum(
        Decimal(t.monto) for t in transacciones if t.tipo == "descuento_cheque"
    )

    # Crear el diccionario de estadísticas
    estadisticas = {
        "total_dolares_vendidos": total_dolares_vendidos,
        "total_pesos_vendidos": total_pesos_vendidos,
        "total_ganancias": total_ganancias,
        "total_perdidas": total_perdidas,
        "total_comisiones": total_comisiones,
        "total_descuentos_cheques": total_descuentos_cheques,
    }

    return render_template('stats.html', estadisticas=estadisticas, rango=rango)




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))  # Redirige al historial o página principal
        else:
            flash('Usuario o contraseña incorrectos.', 'error')

    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.before_request
def inicializar_bd():
    if not hasattr(app, 'db_creada'):  # Comprueba si la BD ya se creó
        db.create_all()
        app.db_creada = True  # Marca que la BD ya está inicializada

if __name__ == '__main__':
    app.run(debug=True)
