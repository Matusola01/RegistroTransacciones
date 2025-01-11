# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from .config import SQLALCHEMY_DATABASE_URI, DEFAULT_USERNAME, DEFAULT_PASSWORD, SECRET_KEY
from .models import db, Transaction, Caja
from flask import jsonify
import requests
from .utils import get_dollar_price
import datetime

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

@app.route('/caja/inicial', methods=['POST'])
def set_initial_cash():
    pesos = request.form.get('pesos', type=float)
    dolares = request.form.get('dolares', type=float)
    caja = Caja(pesos=pesos, dolares=dolares, fecha_hora=datetime.datetime.now())
    db.session.add(caja)
    db.session.commit()
    flash("Caja inicial configurada.")
    return redirect(url_for('index'))

@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    if request.method == 'POST':
        tipo = request.form.get('tipo')  # "compra" o "venta"
        monto = request.form.get('monto', type=float)
        concepto = request.form.get('concepto')
        calculo = request.form.get('calculo')  # "dolar_blue" o "valores_personalizados"
        fecha_hora = datetime.datetime.now()

        # Obtener precios según el método de cálculo seleccionado
        if calculo == 'dolar_blue':
            dollar_prices = get_dollar_price()
            if not dollar_prices:
                flash("No se pudo obtener el precio del dólar blue. Intente nuevamente más tarde.", "error")
                return redirect(url_for('transactions'))
            buy_price = dollar_prices['buy']
            sell_price = dollar_prices['sell']
        elif calculo == 'valores_personalizados':
            buy_price = request.form.get('precio_compra', type=float)
            sell_price = request.form.get('precio_venta', type=float)
            if not buy_price or not sell_price:
                flash("Debes ingresar precios personalizados válidos.", "error")
                return redirect(url_for('transactions'))

        # Verificar que la caja exista
        caja = Caja.query.order_by(Caja.id.desc()).first()
        if not caja:
            flash("Primero debes configurar la caja inicial.", "error")
            return redirect(url_for('index'))

        # Manejar compra
        if tipo == 'compra':
            if monto > caja.pesos:
                flash("No tienes suficientes pesos para realizar esta compra.", "error")
                return redirect(url_for('transactions'))
            caja.pesos -= monto
            caja.dolares += monto / buy_price
        # Manejar venta
        elif tipo == 'venta':
            if monto > caja.dolares:
                flash("No tienes suficientes dólares para realizar esta venta.", "error")
                return redirect(url_for('transactions'))
            caja.dolares -= monto
            caja.pesos += monto * sell_price

        # Registrar transacción
        transaccion = Transaction(
            tipo=tipo,
            monto=monto,
            concepto=concepto,
            fecha_hora=fecha_hora,
            tasa_cambio=buy_price if tipo == 'compra' else sell_price
        )
        db.session.add(transaccion)

        # Actualizar caja
        db.session.commit()
        flash("Transacción registrada correctamente.", "success")
        return redirect(url_for('transactions'))

    # Manejo de filtros GET
    tipo_filtro = request.args.get('type')  # Filtro por tipo de transacción
    concepto_filtro = request.args.get('concept')  # Filtro por concepto
    fecha_inicio_filtro = request.args.get('start_date')  # Filtro por fecha de inicio

    # Obtener transacciones
    transacciones_query = Transaction.query.order_by(Transaction.fecha_hora.desc())

    # Aplicar filtros
    if tipo_filtro:
        transacciones_query = transacciones_query.filter(Transaction.tipo == tipo_filtro)
    if concepto_filtro:
        transacciones_query = transacciones_query.filter(Transaction.concepto.ilike(f"%{concepto_filtro}%"))
    if fecha_inicio_filtro:
        try:
            fecha_inicio = datetime.datetime.strptime(fecha_inicio_filtro, '%Y-%m-%d')
            transacciones_query = transacciones_query.filter(Transaction.fecha_hora >= fecha_inicio)
        except ValueError as e:
            flash(f"Formato de fecha inválido: {fecha_inicio_filtro}. Use el formato YYYY-MM-DD.", "error")
            print("Error de formato de fecha:", e)
            return redirect(url_for('transactions'))
    # Ejecutar la consulta
    transacciones = transacciones_query.all()

    return render_template(
        'transactions.html',
        transacciones=transacciones,
        tipo_filtro=tipo_filtro,
        concepto_filtro=concepto_filtro,
        fecha_inicio_filtro=fecha_inicio_filtro
    )


@app.route('/transactions/delete/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    # Buscar la transacción por ID
    transaction = Transaction.query.get(transaction_id)
    if not transaction:
        flash('Transacción no encontrada.', 'error')
        return redirect(url_for('transactions'))

    # Revertir el impacto de la transacción en la caja
    caja = Caja.query.order_by(Caja.id.desc()).first()
    if not caja:
        flash("Error: Caja no configurada.", "error")
        return redirect(url_for('transactions'))

    if transaction.tipo == 'compra':
        caja.pesos += transaction.monto
        caja.dolares -= transaction.monto / transaction.tasa_cambio
    elif transaction.tipo == 'venta':
        caja.dolares += transaction.monto
        caja.pesos -= transaction.monto * transaction.tasa_cambio

    # Eliminar la transacción
    db.session.delete(transaction)
    db.session.commit()

    flash('Transacción eliminada correctamente y cajas actualizadas.', 'success')
    return redirect(url_for('transactions'))

@app.route('/transactions/edit/<int:transaction_id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(transaction_id):
    # Obtener la transacción por ID desde la base de datos
    transaction = Transaction.query.get(transaction_id)
    if not transaction:
        flash('Transacción no encontrada.', 'error')
        return redirect(url_for('transactions'))

    # Obtener la instancia de la caja (asumiendo que solo hay una)
    caja = Caja.query.first()
    if not caja:
        flash('Caja no configurada. Por favor, inicialice la caja primero.', 'error')
        return redirect(url_for('transactions'))

    if request.method == 'POST':
        # Revertir el impacto de la transacción original en las cajas
        if transaction.tipo == 'compra':
            caja.pesos += transaction.monto
            caja.dolares -= transaction.monto / transaction.tasa_cambio
        elif transaction.tipo == 'venta':
            caja.dolares += transaction.monto
            caja.pesos -= transaction.monto * transaction.tasa_cambio

        # Actualizar los valores de la transacción
        transaction.tipo = request.form['type']
        transaction.concepto = request.form['concept']
        transaction.monto = float(request.form['amount'])
        transaction.tasa_cambio = float(request.form.get('exchange_rate', 0))
        transaction.fecha_hora = datetime.datetime.now()

        # Aplicar el impacto de los nuevos valores en las cajas
        if transaction.tipo == 'compra':
            caja.pesos -= transaction.monto
            caja.dolares += transaction.monto / transaction.tasa_cambio
        elif transaction.tipo == 'venta':
            caja.dolares -= transaction.monto
            caja.pesos += transaction.monto * transaction.tasa_cambio

        # Guardar los cambios en la base de datos
        try:
            db.session.commit()
            flash('Transacción actualizada correctamente y cajas recalculadas.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la transacción: {str(e)}', 'error')

        return redirect(url_for('transactions'))

    return render_template('edit_transactions.html', transaction=transaction)

@app.route('/historial')
@login_required
def historial():
    tipo_filtro = request.args.get('type')
    concepto_filtro = request.args.get('concept')

    # Aplicar filtros si están presentes
    query = Transaction.query
    if tipo_filtro:
        query = query.filter_by(tipo=tipo_filtro)
    if concepto_filtro:
        query = query.filter(Transaction.concepto.contains(concepto_filtro))

    transacciones = query.order_by(Transaction.fecha_hora.desc()).all()

    return render_template('historial.html', transacciones=transacciones, tipo_filtro=tipo_filtro, concepto_filtro=concepto_filtro)


@app.route('/chart')
@login_required
def chart():
    transacciones = Transaction.query.all()
    ganancias = sum(t.monto for t in transacciones if t.tipo == 'venta')
    perdidas = sum(t.monto for t in transacciones if t.tipo == 'compra')
    return render_template('chart.html', ganancias=ganancias, perdidas=perdidas)



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('transactions'))  # Redirige al historial o página principal
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
