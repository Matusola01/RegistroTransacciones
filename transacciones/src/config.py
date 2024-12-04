# config.py
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "transacciones.db")}'
SQLALCHEMY_TRACK_MODIFICATIONS = False
DEFAULT_USERNAME = os.getenv('DEFAULT_USERNAME')
DEFAULT_PASSWORD = os.getenv('DEFAULT_PASSWORD')
SECRET_KEY = os.getenv('SECRET_KEY')