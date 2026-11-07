from getpass import getpass

from werkzeug.security import generate_password_hash

from db import conexion

CUENTAS = [
    # (usuario, rol, nombre que se muestra)
    ("admin", "admin", "Administración"),
    ("guardia", "guardia", "Caseta principal"),
]


def pedir_password(usuario):
    while True:
        p1 = getpass(f"Contraseña para '{usuario}' (mínimo 8 caracteres): ")
        if len(p1) < 8:
            print("  Muy corta, usa al menos 8 caracteres.")
            continue
        if p1 != getpass("  Repítela: "):
            print("  No coinciden, intenta de nuevo.")
            continue
        return p1


def main():
    con = conexion()
    cur = con.cursor()
    for usuario, rol, nombre in CUENTAS:
        cur.execute("SELECT 1 FROM Usuarios WHERE Usuario = ?", usuario)
        if cur.fetchone():
            print(f"'{usuario}' ya existe, se omite.")
            continue
        hash_ = generate_password_hash(pedir_password(usuario))
        cur.execute(
            "INSERT INTO Usuarios (Usuario, PasswordHash, Rol, Nombre) VALUES (?, ?, ?, ?)",
            usuario, hash_, rol, nombre,
        )
        print(f"'{usuario}' creado con rol {rol}.")
    con.commit()
    cur.execute("SELECT UsuarioId, Usuario, Rol, Nombre, Activo FROM Usuarios")
    for fila in cur.fetchall():
        print(tuple(fila))
    con.close()


if __name__ == "__main__":
    main()