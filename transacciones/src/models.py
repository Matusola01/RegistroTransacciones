# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Transaccion(db.Model):
    __tablename__ = 'transacciones'

    id = db.Column(db.Integer, primary_key=True)
    nombre_comprador = db.Column(db.String(100), nullable=False)
    precio_compra = db.Column(db.Float, nullable=False)
    precio_venta = db.Column(db.Float, nullable=False)
    divisa = db.Column(db.String(50), nullable=False)
    moneda = db.Column(db.String(10), nullable=False)  # Nueva columna para registrar la moneda (USD/ARS)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)