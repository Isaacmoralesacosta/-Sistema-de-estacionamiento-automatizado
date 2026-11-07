import pyodbc
from config import DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD


def conexion():
    cadena = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={DB_SERVER};DATABASE={DB_NAME};"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    if DB_USER:
        cadena += f"UID={DB_USER};PWD={{{DB_PASSWORD}}};"
    else:
        cadena += "Trusted_Connection=yes;"
    return pyodbc.connect(cadena)