from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Caja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pesos = db.Column(db.Float, nullable=False)  # Saldo en pesos
    dolares = db.Column(db.Float, nullable=False)  # Saldo en dólares
    fecha_hora = db.Column(db.DateTime, nullable=False)  # Fecha y hora de configuración

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10), nullable=False)  # "compra" o "venta"
    monto = db.Column(db.Float, nullable=False)
    concepto = db.Column(db.String(255), nullable=True)
    fecha_hora = db.Column(db.DateTime, nullable=False)
    tasa_cambio = db.Column(db.Float, nullable=False)  # Tipo de cambio
    comision = db.Column(db.Float, nullable=True, default=0.0)  # Porcentaje de comisión (para cable)
    descuento_cheque = db.Column(db.Float, nullable=True, default=0.0)  # Porcentaje de descuento (para cheques) 
    precio_compra = db.Column(db.Float, nullable=True)  # Precio al que se compró (opcional)
    precio_venta = db.Column(db.Float, nullable=True)  # Precio al que se vendió (opcional)  