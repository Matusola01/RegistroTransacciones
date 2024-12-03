# app.py
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from .config import SQLALCHEMY_DATABASE_URI
from .models import db, Transaccion
from flask import jsonify

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
#app.config['SECRET_KEY'] = SECRET_KEY
db.init_app(app)

# Ruta para formulario
@app.route('/registrar', methods=['GET', 'POST'])
# def registrar():
#     if request.method == 'POST':
#         nombre = request.form['nombre_comprador']
#         precio_compra = float(request.form['precio_compra'])
#         precio_venta = float(request.form['precio_venta'])
#         divisa = request.form['divisa']

#         nueva_transaccion = Transaccion(
#             nombre_comprador=nombre,
#             precio_compra=precio_compra,
#             precio_venta=precio_venta,
#             divisa=divisa
#         )
#         db.session.add(nueva_transaccion)
#         db.session.commit()
#         return redirect(url_for('historial'))

#     return render_template('formulario.html')
def registrar():
    if request.method == 'POST':
        nombre = request.form['nombre_comprador']
        precio_compra = float(request.form['precio_compra'])
        precio_venta = float(request.form['precio_venta'])
        divisa = request.form['divisa']
        moneda = request.form['moneda']  # Capturar la moneda

        nueva_transaccion = Transaccion(
            nombre_comprador=nombre,
            precio_compra=precio_compra,
            precio_venta=precio_venta,
            divisa=divisa,
            moneda=moneda
        )
        db.session.add(nueva_transaccion)
        db.session.commit()
        return redirect(url_for('historial'))

    return render_template('formulario.html')

# Ruta para mostrar historial
@app.route('/historial')
def historial():
    filtro = request.args.get('filtro', '')
    if filtro:
        transacciones = Transaccion.query.filter(Transaccion.divisa.contains(filtro)).all()
    else:
        transacciones = Transaccion.query.order_by(Transaccion.fecha.desc()).all()

    return render_template('historial.html', transacciones=transacciones)

# Ruta para el balance 
@app.route('/datos_balance', methods=['GET'])
# def datos_balance():
#     transacciones = Transaccion.query.order_by(Transaccion.fecha).all()
#     datos = {
#         "fechas": [t.fecha.strftime('%Y-%m-%d %H:%M:%S') for t in transacciones],
#         "ganancias_perdidas": [t.precio_venta - t.precio_compra for t in transacciones],
#     }
#     return jsonify(datos)
def datos_balance():
    # Obtener todas las transacciones
    transacciones = Transaccion.query.order_by(Transaccion.fecha).all()

    # Inicializar estructuras para separar ganancias/pérdidas por moneda
    datos_por_moneda = {
        "USD": {
            "fechas": [],
            "ganancias_perdidas": []
        },
        "ARS": {
            "fechas": [],
            "ganancias_perdidas": []
        }
    }

    # Procesar cada transacción
    for t in transacciones:
        moneda = t.moneda  # Moneda de la transacción (USD o ARS)
        diferencia = t.precio_venta - t.precio_compra  # Ganancia/Pérdida

        # Agregar los datos a la moneda correspondiente
        if moneda in datos_por_moneda:
            datos_por_moneda[moneda]["fechas"].append(t.fecha.strftime('%Y-%m-%d %H:%M:%S'))
            datos_por_moneda[moneda]["ganancias_perdidas"].append(diferencia)

    # Retornar los datos como JSON
    return jsonify(datos_por_moneda)

# @app.route('/balance', methods=['GET'])
# def balance():
#     # Obtener todas las transacciones
#     transacciones = Transaccion.query.all()
    
#     # Calcular ganancias/pérdidas por transacción y el total
#     balance_detallado = []
#     total_balance = 0

#     for transaccion in transacciones:
#         diferencia = transaccion.precio_venta - transaccion.precio_compra
#         total_balance += diferencia
#         balance_detallado.append({
#             'nombre': transaccion.nombre_comprador,
#             'divisa': transaccion.divisa,
#             'diferencia': diferencia,
#             'fecha': transaccion.fecha
#         })

#     return render_template('balance.html', balance_detallado=balance_detallado, total_balance=total_balance)
@app.route('/balance', methods=['GET'])
def balance():
    # Obtener todas las transacciones
    transacciones = Transaccion.query.order_by(Transaccion.fecha).all()

    # Inicializar balances por moneda
    balance_por_moneda = {"USD": 0, "ARS": 0}
    balance_detallado = []

    for transaccion in transacciones:
        diferencia = transaccion.precio_venta - transaccion.precio_compra
        balance_por_moneda[transaccion.moneda] += diferencia  # Acumular balance por moneda
        balance_detallado.append({
            'nombre': transaccion.nombre_comprador,
            'divisa': transaccion.divisa,
            'moneda': transaccion.moneda,
            'diferencia': diferencia,
            'fecha': transaccion.fecha
        })

    return render_template('balance.html', balance_detallado=balance_detallado, balance_por_moneda=balance_por_moneda)



@app.before_request
def inicializar_bd():
    if not hasattr(app, 'db_creada'):  # Comprueba si la BD ya se creó
        db.create_all()
        app.db_creada = True  # Marca que la BD ya está inicializada

if __name__ == '__main__':
    app.run(debug=True)
