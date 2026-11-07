"""SmartParking - Login, registro, caseta con NFC y lectura de placas (SQL Server)."""
import re
import secrets
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from config import URL_BASE
from db import conexion

BASE = Path(__file__).parent
CARPETA_FOTOS = BASE / "uploads" / "fotos"
CARPETA_PLACAS = BASE / "uploads" / "placas"
MAX_FOTO = 3 * 1024 * 1024   # 3 MB para la foto de perfil
MIN_CONFIANZA = 0.5          # por debajo de esto se pide otra foto de la placa
_lector = None

app = Flask(__name__)
app.secret_key = "cambia-esta-clave-antes-de-entregar"
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024


# ----------------------------------------------------------------------------
# Base de datos
# ----------------------------------------------------------------------------
def guardar_conductor(datos, foto_bytes, extension):
    """Guarda la foto en uploads/fotos y al conductor en SQL Server."""
    CARPETA_FOTOS.mkdir(parents=True, exist_ok=True)
    nombre_foto = f"{datos['matricula']}.{extension}"
    ruta_foto = CARPETA_FOTOS / nombre_foto
    ruta_foto.write_bytes(foto_bytes)

    con = conexion()
    try:
        cur = con.cursor()
        usuario_id = cur.execute(
            "INSERT INTO Usuarios (Usuario, PasswordHash, Rol, Nombre) "
            "OUTPUT INSERTED.UsuarioId VALUES (?, ?, 'conductor', ?)",
            datos["matricula"], generate_password_hash(datos["password"]), datos["nombre"],
        ).fetchone()[0]
        cur.execute(
            "INSERT INTO Conductores (UsuarioId, Marbete, Placa, Foto) VALUES (?, ?, ?, ?)",
            usuario_id, datos["marbete"], datos["placa"], nombre_foto,
        )
        con.commit()
    except Exception:
        con.rollback()
        ruta_foto.unlink(missing_ok=True)  # no dejar la foto huérfana
        raise
    finally:
        con.close()


def campos_repetidos(matricula, marbete, placa):
    """Devuelve qué datos ya existen en la base: {'matricula', 'marbete', 'placa'}."""
    con = conexion()
    try:
        cur = con.cursor()
        repetidos = set()
        if cur.execute("SELECT 1 FROM Usuarios WHERE Usuario = ?", matricula).fetchone():
            repetidos.add("matricula")
        if cur.execute("SELECT 1 FROM Conductores WHERE Marbete = ?", marbete).fetchone():
            repetidos.add("marbete")
        if cur.execute("SELECT 1 FROM Conductores WHERE Placa = ?", placa).fetchone():
            repetidos.add("placa")
        return repetidos
    finally:
        con.close()


def buscar_cuenta(usuario, password):
    """Login contra SQL Server: sirve para admin, guardia y conductor."""
    usuario = usuario.strip()
    con = conexion()
    try:
        fila = con.cursor().execute(
            "SELECT Usuario, PasswordHash, Rol, Nombre "
            "FROM Usuarios WHERE Usuario = ? AND Activo = 1",
            usuario,
        ).fetchone()
    finally:
        con.close()
    if fila and check_password_hash(fila.PasswordHash, password):
        return {"usuario": fila.Usuario, "rol": fila.Rol, "nombre": fila.Nombre}
    return None


# ----------------------------------------------------------------------------
# Navegación y permisos
# ----------------------------------------------------------------------------
PAGINA_INICIO = {"admin": "admin", "guardia": "guardia", "conductor": "credencial"}

MENU = [
    {"endpoint": "admin", "etiqueta": "Resumen", "icono": "grid", "roles": ("admin",)},
    {"endpoint": "guardia", "etiqueta": "Caseta", "icono": "caseta", "roles": ("admin", "guardia")},
    {"endpoint": "usuarios", "etiqueta": "Padrón", "icono": "users", "roles": ("admin",)},
    {"endpoint": "historial", "etiqueta": "Accesos", "icono": "clock", "roles": ("admin", "guardia")},
    {"endpoint": "credencial", "etiqueta": "Mi credencial", "icono": "id", "roles": ("conductor",)},
]


def acceso(*roles):
    """Exige sesión iniciada y, si se indican, uno de los roles."""

    def decorador(vista):
        @wraps(vista)
        def envoltura(*args, **kwargs):
            rol = session.get("rol")
            if not rol:
                if request.method == "GET" and request.path.startswith("/c/"):
                    session["siguiente"] = request.path   # volver a la etiqueta tras el login
                return redirect(url_for("login"))
            if roles and rol not in roles:
                return redirect(url_for(PAGINA_INICIO[rol]))
            return vista(*args, **kwargs)

        return envoltura

    return decorador


@app.context_processor
def datos_de_plantilla():
    rol = session.get("rol")
    return {
        "menu": [m for m in MENU if rol in m["roles"]],
        "sesion": {"nombre": session.get("nombre"), "rol": rol},
    }


def iniciar_sesion(cuenta):
    session.clear()
    session["usuario"] = cuenta["usuario"]
    session["rol"] = cuenta["rol"]
    session["nombre"] = cuenta["nombre"]


# ----------------------------------------------------------------------------
# Acceso y registro
# ----------------------------------------------------------------------------
@app.route("/")
def inicio():
    rol = session.get("rol")
    return redirect(url_for(PAGINA_INICIO[rol]) if rol else url_for("login"))


@app.route("/entrar", methods=["GET", "POST"])
def login():
    if session.get("rol"):
        return redirect(url_for("inicio"))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        cuenta = buscar_cuenta(usuario, request.form.get("password", ""))
        if cuenta:
            siguiente = session.get("siguiente", "")
            iniciar_sesion(cuenta)
            if siguiente.startswith("/c/"):
                return redirect(siguiente)
            return redirect(url_for("inicio"))
        error = "Usuario o contraseña incorrectos. Revisa los datos e inténtalo de nuevo."
        return render_template("login.html", error=error, usuario=usuario), 401

    return render_template("login.html", error=None, usuario="")


@app.post("/salir")
def logout():
    session.clear()
    return redirect(url_for("login"))


def tipo_de_imagen(contenido):
    """Detecta el formato real de la imagen por su contenido, no por su nombre."""
    if contenido.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "webp"
    return None


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if session.get("rol"):
        return redirect(url_for("inicio"))
    if request.method == "GET":
        return render_template("registro.html", form={}, errores={})

    form = {c: request.form.get(c, "").strip() for c in ("nombre", "matricula", "marbete", "placa")}
    form["matricula"] = form["matricula"].upper()
    form["placa"] = re.sub(r"\s+", "", form["placa"]).upper()
    password = request.form.get("password", "")
    confirmar = request.form.get("confirmar", "")
    archivo = request.files.get("foto")
    foto = archivo.read() if archivo and archivo.filename else b""
    errores = {}
    repetidos = campos_repetidos(form["matricula"], form["marbete"], form["placa"])

    if not 3 <= len(form["nombre"]) <= 80:
        errores["nombre"] = "Escribe tu nombre completo."
    if not re.fullmatch(r"[A-Z0-9-]{4,20}", form["matricula"]):
        errores["matricula"] = "Usa de 4 a 20 letras, números o guiones, sin espacios."
    elif "matricula" in repetidos:
        errores["matricula"] = "Esta matrícula ya tiene una cuenta. Inicia sesión."
    if not re.fullmatch(r"\d{1,6}", form["marbete"]):
        errores["marbete"] = "El marbete solo lleva números."
    elif "marbete" in repetidos:
        errores["marbete"] = "Este marbete ya está registrado."
    if not re.fullmatch(r"[A-Z0-9-]{5,10}", form["placa"]):
        errores["placa"] = "Escribe la placa sin espacios, por ejemplo ABC-123-D."
    elif "placa" in repetidos:
        errores["placa"] = "Esta placa ya está registrada."
    if len(password) < 8:
        errores["password"] = "Usa al menos 8 caracteres."
    elif password != confirmar:
        errores["confirmar"] = "Las contraseñas no coinciden."

    extension = tipo_de_imagen(foto) if foto else None
    if not foto:
        errores["foto"] = "Agrega una foto de perfil."
    elif len(foto) > MAX_FOTO:
        errores["foto"] = "La foto pesa demasiado. Usa una de menos de 3 MB."
    elif not extension:
        errores["foto"] = "Usa una foto JPG, PNG o WebP."

    if errores:
        return render_template("registro.html", form=form, errores=errores), 400

    guardar_conductor({**form, "password": password}, foto, extension)
    iniciar_sesion({"usuario": form["matricula"], "rol": "conductor", "nombre": form["nombre"]})
    flash("Cuenta creada. Esta es tu credencial.")
    return redirect(url_for("credencial"))


@app.errorhandler(413)
def archivo_muy_grande(_):
    if request.path.startswith("/c/"):
        return "La foto es demasiado grande. Regresa y toma otra.", 413
    errores = {"foto": "La foto pesa demasiado. Usa una de menos de 3 MB."}
    return render_template("registro.html", form={}, errores=errores), 413


# ----------------------------------------------------------------------------
# Lectura de placas
# ----------------------------------------------------------------------------
def limpiar_placa(texto):
    """Mayúsculas, sin espacios ni guiones."""
    return re.sub(r"[^A-Z0-9]", "", (texto or "").upper())


def clave_placa(texto):
    """Para comparar: ignora guiones y espacios, y las confusiones típicas O/0 e I/1."""
    return limpiar_placa(texto).translate(str.maketrans("OI", "01"))


def _promedio(valor):
    try:
        return float(valor)
    except TypeError:
        lista = [float(v) for v in valor]
        return sum(lista) / len(lista) if lista else 0.0


def leer_placa(imagen):
    """Lee la placa de una foto. Devuelve (placa, confianza de 0 a 1)."""
    global _lector
    import cv2
    import numpy as np

    if _lector is None:
        from fast_alpr import ALPR
        _lector = ALPR()
    foto = cv2.imdecode(np.frombuffer(imagen, np.uint8), cv2.IMREAD_COLOR)
    if foto is None:
        return None, 0.0
    mejor, mejor_conf = None, 0.0
    for r in _lector.predict(foto):
        if r.ocr is None or not r.ocr.text:
            continue
        texto = limpiar_placa(r.ocr.text)
        conf = _promedio(r.ocr.confidence)
        if texto and conf >= mejor_conf:
            mejor, mejor_conf = texto, conf
    return mejor, mejor_conf


def guardar_foto_placa(datos, extension):
    CARPETA_PLACAS.mkdir(parents=True, exist_ok=True)
    nombre = f"{datetime.now():%Y%m%d_%H%M%S}_{secrets.token_hex(3)}.{extension}"
    (CARPETA_PLACAS / nombre).write_bytes(datos)
    return nombre


def registrar_acceso(cur, tipo, resultado, motivo, fila, placa=None, coincide=None,
                     confianza=None, foto=None):
    """Guarda el intento en Accesos (permitido o denegado)."""
    cur.execute(
        "INSERT INTO Accesos (Tipo, UsuarioId, CredencialId, PlacaLeida, ConfianzaPlaca, "
        "                     PlacaCoincide, Resultado, Motivo, GuardiaId, FotoPlaca) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, (SELECT UsuarioId FROM Usuarios WHERE Usuario = ?), ?)",
        tipo,
        fila.UsuarioId if fila else None,
        fila.CredencialId if fila else None,
        placa[:10] if placa else None,
        None if confianza is None else round(confianza * 100, 2),
        coincide, resultado, motivo, session["usuario"], foto,
    )


# ----------------------------------------------------------------------------
# Páginas
# ----------------------------------------------------------------------------
@app.route("/caseta")
@acceso("admin", "guardia")
def guardia():
    return render_template("guardia.html")


@app.route("/c/<token>", methods=["GET", "POST"])
@acceso("admin", "guardia")
def caseta_lectura(token):
    """Se abre al leer una etiqueta NFC: muestra al conductor y verifica la placa."""
    con = conexion()
    try:
        cur = con.cursor()
        fila = cur.execute(
            "SELECT cr.CredencialId, cr.Activa, u.UsuarioId, u.Nombre, u.Usuario, u.Activo, "
            "       c.Marbete, c.Placa, c.Foto "
            "FROM Credenciales cr "
            "JOIN Usuarios u ON u.UsuarioId = cr.UsuarioId "
            "JOIN Conductores c ON c.UsuarioId = u.UsuarioId "
            "WHERE cr.Token = ?",
            token,
        ).fetchone()

        motivo = None
        if not fila:
            motivo = "Etiqueta no reconocida"
        elif not fila.Activa:
            motivo = "Etiqueta desactivada"
        elif not fila.Activo:
            motivo = "Cuenta desactivada"

        tipo = "entrada"
        if fila:
            ultimo = cur.execute(
                "SELECT TOP 1 Tipo FROM Accesos "
                "WHERE UsuarioId = ? AND Resultado = 'permitido' "
                "ORDER BY FechaHora DESC, AccesoId DESC",
                fila.UsuarioId,
            ).fetchone()
            if ultimo and ultimo.Tipo == "entrada":
                tipo = "salida"

        resultado = aviso = nombre_foto = confianza = placa = None
        if motivo:
            resultado = "denegado"
            registrar_acceso(cur, tipo, resultado, motivo, fila)
            con.commit()
        elif request.method == "POST":
            archivo = request.files.get("foto")
            datos = archivo.read() if archivo and archivo.filename else b""
            extension = tipo_de_imagen(datos) if datos else None

            if datos and not extension:
                aviso = "Usa una foto JPG, PNG o WebP."
            elif datos:
                try:
                    placa, confianza = leer_placa(datos)
                except Exception as error:
                    print("Error al leer la placa:", error)
                    aviso = "El lector de placas no está disponible. Escribe la placa a mano."
                else:
                    if not placa or confianza < MIN_CONFIANZA:
                        aviso = ("No se pudo leer la placa con claridad. "
                                 "Toma otra foto o escríbela a mano.")
                        placa = confianza = None
            else:
                placa = limpiar_placa(request.form.get("placa", ""))[:10] or None
                if not placa:
                    aviso = "Toma una foto de la placa o escríbela a mano."

            if placa and not aviso:
                coincide = clave_placa(placa) == clave_placa(fila.Placa)
                motivo = None if coincide else "La placa no coincide con la registrada"
                resultado = "permitido" if coincide else "denegado"
                if datos:
                    nombre_foto = guardar_foto_placa(datos, extension)
                registrar_acceso(cur, tipo, resultado, motivo, fila, placa, coincide,
                                 confianza, nombre_foto)
                con.commit()
    finally:
        con.close()

    return render_template("caseta_lectura.html", c=fila, tipo=tipo, resultado=resultado,
                           motivo=motivo, placa=placa, aviso=aviso, confianza=confianza,
                           nombre_foto=nombre_foto)


@app.route("/placas/<nombre>")
@acceso("admin", "guardia")
def foto_placa(nombre):
    return send_from_directory(CARPETA_PLACAS, nombre)


@app.route("/accesos")
@acceso("admin", "guardia")
def historial():
    todos = request.args.get("ver") == "todos"
    filtro = "" if todos else "WHERE CAST(a.FechaHora AS date) = CAST(SYSDATETIME() AS date) "
    con = conexion()
    try:
        accesos = con.cursor().execute(
            "SELECT TOP 200 a.FechaHora, a.Tipo, a.Resultado, a.Motivo, a.PlacaLeida, "
            "       u.Nombre, u.Usuario "
            "FROM Accesos a LEFT JOIN Usuarios u ON u.UsuarioId = a.UsuarioId "
            + filtro +
            "ORDER BY a.FechaHora DESC, a.AccesoId DESC"
        ).fetchall()
    finally:
        con.close()
    return render_template("historial.html", accesos=accesos, todos=todos)


@app.route("/padron")
@acceso("admin")
def usuarios():
    con = conexion()
    try:
        conductores = con.cursor().execute(
            "SELECT u.UsuarioId, u.Nombre, u.Usuario, u.Activo, "
            "       c.Marbete, c.Placa, c.Foto, cr.Token "
            "FROM Usuarios u "
            "JOIN Conductores c ON c.UsuarioId = u.UsuarioId "
            "LEFT JOIN Credenciales cr ON cr.UsuarioId = u.UsuarioId AND cr.Activa = 1 "
            "ORDER BY u.Nombre"
        ).fetchall()
    finally:
        con.close()
    return render_template("usuarios.html", conductores=conductores, url_base=URL_BASE)


@app.post("/padron/<int:usuario_id>/estado")
@acceso("admin")
def cambiar_estado(usuario_id):
    """Activa o desactiva la cuenta de un conductor."""
    con = conexion()
    try:
        con.cursor().execute(
            "UPDATE Usuarios SET Activo = CASE WHEN Activo = 1 THEN 0 ELSE 1 END "
            "WHERE UsuarioId = ? AND Rol = 'conductor'",
            usuario_id,
        )
        con.commit()
    finally:
        con.close()
    return redirect(url_for("usuarios"))


@app.post("/padron/<int:usuario_id>/etiqueta")
@acceso("admin")
def asignar_etiqueta(usuario_id):
    """Crea una etiqueta nueva para el conductor. La anterior deja de servir."""
    token = secrets.token_urlsafe(16)
    con = conexion()
    try:
        cur = con.cursor()
        if not cur.execute("SELECT 1 FROM Conductores WHERE UsuarioId = ?", usuario_id).fetchone():
            abort(404)
        cur.execute("UPDATE Credenciales SET Activa = 0 WHERE UsuarioId = ? AND Activa = 1", usuario_id)
        cur.execute("INSERT INTO Credenciales (UsuarioId, Token) VALUES (?, ?)", usuario_id, token)
        con.commit()
    finally:
        con.close()
    flash("Etiqueta lista. Pulsa «Ver enlace» para copiarlo y grabarlo en la etiqueta.")
    return redirect(url_for("usuarios"))


@app.route("/resumen")
@acceso("admin")
def admin():
    con = conexion()
    try:
        cur = con.cursor()
        dentro = cur.execute(
            "SELECT u.Nombre, u.Usuario, c.Placa, t.FechaHora "
            "FROM (SELECT UsuarioId, Tipo, FechaHora, "
            "             ROW_NUMBER() OVER (PARTITION BY UsuarioId "
            "                                ORDER BY FechaHora DESC, AccesoId DESC) AS rn "
            "      FROM Accesos "
            "      WHERE Resultado = 'permitido' AND UsuarioId IS NOT NULL) t "
            "JOIN Usuarios u ON u.UsuarioId = t.UsuarioId "
            "JOIN Conductores c ON c.UsuarioId = u.UsuarioId "
            "WHERE t.rn = 1 AND t.Tipo = 'entrada' "
            "ORDER BY t.FechaHora"
        ).fetchall()
        hoy = cur.execute(
            "SELECT ISNULL(SUM(CASE WHEN Resultado = 'permitido' THEN 1 ELSE 0 END), 0) AS permitidos, "
            "       ISNULL(SUM(CASE WHEN Resultado = 'denegado' THEN 1 ELSE 0 END), 0) AS denegados "
            "FROM Accesos WHERE CAST(FechaHora AS date) = CAST(SYSDATETIME() AS date)"
        ).fetchone()
        conductores = cur.execute(
            "SELECT COUNT(*) FROM Usuarios WHERE Rol = 'conductor' AND Activo = 1"
        ).fetchone()[0]
    finally:
        con.close()
    return render_template("admin.html", dentro=dentro, hoy=hoy, conductores=conductores)


@app.route("/mi-credencial")
@acceso("conductor")
def credencial():
    con = conexion()
    try:
        fila = con.cursor().execute(
            "SELECT u.Nombre, u.Usuario, c.Marbete, c.Placa, c.Foto "
            "FROM Usuarios u JOIN Conductores c ON c.UsuarioId = u.UsuarioId "
            "WHERE u.Usuario = ? AND u.Activo = 1",
            session["usuario"],
        ).fetchone()
    finally:
        con.close()
    if not fila:
        session.clear()
        return redirect(url_for("login"))
    c = {"nombre": fila.Nombre, "matricula": fila.Usuario, "marbete": fila.Marbete,
         "placa": fila.Placa, "foto": fila.Foto}
    return render_template("credencial.html", c=c)


@app.route("/fotos/<nombre>")
@acceso("admin", "guardia", "conductor")
def foto(nombre):
    if session["rol"] == "conductor" and not nombre.startswith(session["usuario"] + "."):
        abort(403)
    return send_from_directory(CARPETA_FOTOS, nombre)


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)