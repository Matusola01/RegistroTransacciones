# config.py
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "transacciones.db")}'
SQLALCHEMY_TRACK_MODIFICATIONS = False
SECRET_KEY = 'e3489bc37e57410f8d1bc3c75e097a6fd37ef2db9180125dc4e6a907d934b6d9'
DEFAULT_USERNAME = "Admin"
DEFAULT_PASSWORD = "43640797"