from flask import Flask, render_template, request, redirect, url_for
import pymysql
from datetime import datetime

app = Flask(__name__)

def conectar_db():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='',
        database='smartparking_tesoem'
    )

@app.route('/')
def index():
    conexion = conectar_db()
    registros = []
    with conexion.cursor() as cursor:
        cursor.execute("SELECT * FROM registros_acceso ORDER BY id DESC")
        registros = cursor.fetchall()
    conexion.close()
    return render_template('index.html', registros=registros)

@app.route('/registrar', methods=['POST'])
def registrar():
    marbete = request.form['marbete']
    matricula = request.form['matricula']
    nombre = request.form['nombre']
    placa = request.form['placa']
    
    fecha_actual = datetime.now().strftime('%Y-%m-%d')
    hora_actual = datetime.now().strftime('%H:%M:%S')

    conexion = conectar_db()
    with conexion.cursor() as cursor:
        sql = """INSERT INTO registros_acceso 
                 (marbete, matricula, nombre_conductor, placa_vehiculo, fecha_entrada, hora_entrada, estado) 
                 VALUES (%s, %s, %s, %s, %s, %s, 'Dentro')"""
        cursor.execute(sql, (marbete, matricula, nombre, placa, fecha_actual, hora_actual))
        conexion.commit()
    conexion.close()

    return redirect(url_for('index'))

# NUEVA RUTA: Limpia la tabla por completo y reinicia el ID en 1
@app.route('/limpiar', methods=['POST'])
def limpiar():
    conexion = conectar_db()
    with conexion.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE registros_acceso")
        conexion.commit()
    conexion.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)