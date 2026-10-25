# SmartParking

Control de acceso a un estacionamiento con **etiquetas NFC** y **lectura de placas con cámara**.

El conductor se registra con su foto, matrícula, marbete y placa. Recibe una etiqueta NFC. El guardia acerca su celular a la etiqueta, el sistema muestra la ficha del conductor, el guardia fotografía la placa del vehículo y el sistema la lee y la compara con la registrada. **Si la placa no coincide, no pasa, aunque la etiqueta y los datos sean correctos.** Cada intento queda guardado en el historial.

## Qué hace el sistema

| Rol | Qué puede hacer |
|---|---|
| **Conductor** | Registrarse con foto, iniciar sesión y ver su credencial. |
| **Guardia** | Usar la Caseta (leer etiqueta, verificar placa) y ver el historial de accesos. |
| **Administrador** | Todo lo del guardia, más el Resumen y el Padrón (activar o desactivar cuentas, asignar etiquetas). |

Reglas de la caseta. Se evalúan en este orden y se detienen en la primera que falle:

1. La etiqueta no existe: **denegado**.
2. La etiqueta fue reemplazada o desactivada: **denegado**.
3. La cuenta del conductor está desactivada: **denegado**.
4. No se pudo leer ni capturar la placa: no se registra nada y se pide otra foto.
5. La placa leída no coincide con la registrada: **denegado**.
6. Todo coincide: **permitido**.

La entrada y la salida se alternan solas. Si el último acceso permitido del conductor fue una entrada, el siguiente es una salida.

## Tecnologías

Python 3.12, Flask, SQL Server (con `pyodbc`), `fast-alpr` para leer placas, y etiquetas NFC NTAG con la app NFC Tools.

## Estructura del proyecto

```
smart_parking/
├── app.py                 Aplicación principal (rutas y lógica)
├── db.py                  Conexión a SQL Server
├── config.py              Configuración de cada equipo (NO se sube a GitHub)
├── crear_usuarios.py      Crea al administrador y al guardia
├── requirements.txt       Librerías de Python
├── database/              Respaldo (.bak) y script de tablas (.sql)
├── templates/             Páginas HTML
├── static/                CSS, imágenes y JavaScript
└── uploads/
    ├── fotos/             Fotos de perfil de los conductores
    └── placas/            Fotos de placas tomadas en la caseta
```

---

# Cómo correr el sistema, paso a paso

## Paso 1. Instalar lo necesario

En la laptop donde va a correr el sistema:

1. **Python 3.12.** En el instalador marca la casilla **Add Python to PATH**.
2. **SQL Server** (Developer o Express) y **SQL Server Management Studio (SSMS)**.
3. **ODBC Driver 18 for SQL Server**, descargado de microsoft.com.
4. **Git**, desde git-scm.com (opcional si descargas el proyecto en ZIP).
5. **Visual Studio Code** (opcional, pero recomendado).

En el celular del guardia: Android, o iPhone XS o más nuevo, con NFC, y la app gratuita **NFC Tools**.

## Paso 2. Descargar el proyecto

Con Git:

```
git clone https://github.com/TU-USUARIO/smart_parking.git
cd smart_parking
```

O descarga el ZIP del repositorio, descomprímelo y abre una terminal dentro de la carpeta `smart_parking`, la que contiene `app.py`.

## Paso 3. Crear el entorno virtual e instalar las librerías

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Si PowerShell bloquea el `activate`, ejecuta una sola vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve a intentar. Al activar, el nombre `(venv)` aparece al inicio de la línea de la terminal.

Si `requirements.txt` no incluye todo, instala a mano:

```
pip install "Flask>=3.0" "pyodbc>=5.0" "fast-alpr[onnx]"
```

## Paso 4. Crear la base de datos

Elige **una** de las dos opciones.

### Opción A: restaurar el respaldo (la más rápida)

1. Copia `database\smart_parking.bak` a la carpeta de respaldos de SQL Server, por ejemplo `C:\Program Files\Microsoft SQL Server\MSSQL17.MSSQLSERVER\MSSQL\Backup\`.
2. En SSMS: clic derecho en **Bases de datos** > **Restaurar base de datos...** > **Dispositivo** > **...** > **Agregar** > elige el archivo > **Aceptar** > **Aceptar**.

El `.bak` solo se restaura en una versión de SQL Server **igual o más nueva** que la del equipo que lo generó. Si falla por la versión, usa la Opción B.

### Opción B: crear la base desde cero

1. En SSMS abre `database\crear_tablas.sql` y ejecútalo con `F5`.
2. Ejecuta además este script, que agrega las columnas para el reconocimiento facial (reservadas para la siguiente etapa):

```sql
USE smart_parking;
GO

IF COL_LENGTH('Accesos', 'RostroCoincide') IS NULL
    ALTER TABLE Accesos ADD RostroCoincide BIT NULL;
IF COL_LENGTH('Accesos', 'ConfianzaRostro') IS NULL
    ALTER TABLE Accesos ADD ConfianzaRostro DECIMAL(5,2) NULL;
IF COL_LENGTH('Accesos', 'FotoRostro') IS NULL
    ALTER TABLE Accesos ADD FotoRostro NVARCHAR(120) NULL;
GO
```

3. Después se crean el administrador y el guardia (Paso 7).

### Verificar que quedó

```sql
SELECT name FROM smart_parking.sys.tables ORDER BY name;
```

Deben salir 4 tablas: `Accesos`, `Conductores`, `Credenciales` y `Usuarios`.

## Paso 5. Crear `config.py`

Crea el archivo `config.py` en la raíz del proyecto, junto a `app.py`:

```python
DB_SERVER = "localhost"
DB_NAME = "smart_parking"
DB_USER = ""        # vacío = autenticación de Windows
DB_PASSWORD = ""
URL_BASE = "http://192.168.137.1:5000"   # dirección de esta laptop en la red (ver Paso 8)
```

- Si instalaste **SQL Server Express**, el servidor se llama `localhost\\SQLEXPRESS`. Escríbelo con doble diagonal dentro de las comillas.
- Si usas un usuario de SQL Server en lugar de autenticación de Windows, llena `DB_USER` y `DB_PASSWORD`.
- Este archivo es distinto en cada laptop y no se sube a GitHub.

## Paso 6. Probar la conexión

```
python -c "from db import conexion; print(conexion().execute('SELECT COUNT(*) FROM Usuarios').fetchone())"
```

Debe imprimir algo como `(2,)`. Si falla, revisa la sección de problemas comunes.

## Paso 7. Crear al administrador y al guardia

**Solo si creaste la base desde cero** (Opción B). Si restauraste el `.bak`, estos usuarios ya existen con las contraseñas que tenían, y puedes saltar este paso.

```
python crear_usuarios.py
```

Pide una contraseña para `admin` y otra para `guardia` (mínimo 8 caracteres, no se ven al escribirlas). Al final imprime los dos usuarios creados.

## Paso 8. Configurar la red

El celular del guardia y la laptop deben estar **en la misma red**. No hace falta internet para usar el sistema.

### Opción recomendada: zona Wi-Fi de la laptop (IP fija)

Así la dirección es siempre `192.168.137.1`, en cualquier lugar, y las etiquetas grabadas no se invalidan al cambiar de red.

1. **Configuración** > **Red e Internet** > **Zona con cobertura inalámbrica móvil** > **Editar**. Escribe un nombre (por ejemplo `SmartParking`) y una contraseña de 8 o más caracteres. Si aparece **Banda de red**, elige **2.4 GHz**.
2. Activa el interruptor de compartir. Desactiva el ahorro de energía de la zona si aparece esa opción.
3. Conecta el celular a esa red.
4. En `config.py`: `URL_BASE = "http://192.168.137.1:5000"`.

### Alternativa: Wi-Fi existente

1. Conecta laptop y celular a la misma red Wi-Fi.
2. Corre `ipconfig` y copia la **Dirección IPv4** del adaptador Wi-Fi (por ejemplo `192.168.1.76`).
3. Ponla en `URL_BASE`. **Cada vez que cambies de red, la IP cambia**, hay que actualizar `URL_BASE`, reiniciar el servidor y regrabar las etiquetas (ver Paso 11).

### Firewall (una sola vez)

En PowerShell **como administrador**:

```
New-NetFirewallRule -DisplayName "SmartParking 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
```

Si la red Wi-Fi está como **Pública** en Windows, cámbiala a **Privada**.

## Paso 9. Preparar el lector de placas (con internet, una sola vez)

La primera vez que se usa, `fast-alpr` descarga sus modelos. Hazlo **con internet** y antes de la demostración:

1. Guarda una foto de una placa como `prueba.jpeg` en la raíz del proyecto.
2. Corre:

```
python -c "import cv2; from fast_alpr import ALPR; r=ALPR().predict(cv2.imread('prueba.jpeg')); print([(x.ocr.text, x.ocr.confidence) for x in r if x.ocr])"
```

Debe imprimir la placa leída. Después de esto, el lector funciona **sin internet**.

## Paso 10. Arrancar el sistema

```
python app.py
```

Debe mostrar `Running on http://192.168.137.1:5000` (o la IP de tu red). Los avisos en rojo sobre "development server" son normales.

- En la laptop abre `http://127.0.0.1:5000`.
- En el celular, conectado a la misma red, abre `http://192.168.137.1:5000` (o tu IP). Debe salir el login.

Inicia sesión como `admin` para empezar.

## Paso 11. Registrar conductores y grabar etiquetas

**1. Registrar al conductor.** Sin sesión iniciada, abre `/registro` (en el celular o la laptop) y llena los datos: nombre, matrícula (el usuario con el que entra), marbete (solo números), placa, contraseña de 8 o más caracteres y una foto de rostro, clara y de frente. **Revisa la placa letra por letra**, porque una `I` en lugar de un `1` hace que esa persona no pase.

**2. Asignar la etiqueta.** Entra como `admin` > **Padrón** > **Asignar etiqueta**, **una sola vez por conductor**.

**3. Copiar el enlace.** En esa misma fila pulsa **Ver enlace** y cópialo. Debe empezar con la IP que pusiste en `URL_BASE`.

**4. Grabar la etiqueta** con NFC Tools:

1. **Escribir** > **Agregar un registro** > **URL / URI**.
2. En el menú de la izquierda elige **`http://`** (no `https://`). En el campo pega el enlace **sin** el `http://` del inicio.
3. Pulsa **Validar**, luego **Escribir**, y acerca **una sola etiqueta**, separada de la tira.
4. Marca la etiqueta con el nombre del conductor.
5. **No uses la opción de bloquear**, porque es permanente.

Una etiqueta no bloqueada se puede reescribir las veces que haga falta (**Otro** > **Borrar etiqueta**, o simplemente volver a escribir).

**5. Probar.** Cierra NFC Tools por completo. Inicia sesión como `guardia` en el celular, con la pantalla encendida y desbloqueada, y acerca la etiqueta. Debe abrirse la ficha del conductor. Si no tienes sesión iniciada, te manda al login y, al entrar, te lleva directo a la ficha.

## Paso 12. Uso diario en la caseta

1. El conductor llega y el guardia acerca su celular a la etiqueta.
2. Se abre la ficha: foto, nombre, matrícula, marbete y placa registrada.
3. El guardia pulsa **Verificar placa con la cámara** y fotografía la placa del vehículo.
4. El sistema lee la placa y la compara con la registrada:
   - **Paso permitido:** se registra la entrada o la salida y el guardia abre la pluma.
   - **Paso denegado:** la placa no coincide, la etiqueta fue reemplazada o la cuenta está desactivada. Queda guardado con su motivo y la foto.
   - **No se leyó:** pide otra foto, sin registrar nada. Se puede escribir la placa a mano como respaldo.
5. El administrador revisa **Accesos** (historial) y **Resumen** (vehículos dentro, accesos permitidos y denegados de hoy, conductores activos).

Para que la placa se lea bien: fotografíala de frente, a 1 o 2 metros, con buena luz, sin reflejos y con la placa ocupando buena parte de la imagen.

---

# Operación

## Si cambia la red

El token de cada etiqueta **no cambia**, solo la IP del enlace. Para actualizar:

1. Corre `ipconfig` y copia la nueva IPv4.
2. Cámbiala en `URL_BASE` de `config.py` y reinicia el servidor.
3. En el Padrón, pulsa **Ver enlace** de cada conductor y regraba su etiqueta.

**No pulses Asignar etiqueta ni Nueva etiqueta**, porque eso crea otro token e invalida la etiqueta ya grabada. **Nueva etiqueta** solo se usa si una etiqueta se pierde: deja de servir la anterior.

Con la zona Wi-Fi de la laptop (`192.168.137.1`) este paso no hace falta.

## Limpiar los datos de prueba

Hazlo **antes** de registrar a los conductores definitivos y grabar sus etiquetas. Después de grabar las etiquetas definitivas, **no vuelvas a borrar** `Credenciales`, `Conductores` ni `Usuarios`: las etiquetas dejarían de servir. Primero haz un respaldo:

```sql
BACKUP DATABASE smart_parking
TO DISK = 'C:\Temp\smart_parking_antes_de_limpiar.bak'
WITH INIT;
```

Luego limpia. Conserva a `admin` y `guardia`:

```sql
USE smart_parking;
GO

BEGIN TRANSACTION;

DELETE FROM Accesos;
DELETE FROM Credenciales;
DELETE FROM Conductores;
DELETE FROM Usuarios WHERE Rol = 'conductor';

DBCC CHECKIDENT ('Accesos', RESEED, 0);
DBCC CHECKIDENT ('Credenciales', RESEED, 0);
DECLARE @ultimo INT = (SELECT ISNULL(MAX(UsuarioId), 0) FROM Usuarios);
DBCC CHECKIDENT ('Usuarios', RESEED, @ultimo);

COMMIT TRANSACTION;
GO
```

Y borra las fotos de prueba, desde la terminal del proyecto:

```
Get-ChildItem uploads\fotos -File | Where-Object { $_.Name -ne '.gitkeep' } | Remove-Item
Get-ChildItem uploads\placas -File | Remove-Item
```

Para dejar solo el historial vacío, sin tocar conductores ni etiquetas:

```sql
DELETE FROM smart_parking.dbo.Accesos;
DBCC CHECKIDENT ('smart_parking.dbo.Accesos', RESEED, 0);
```

## Respaldar y compartir con el equipo

**La base de datos.** En SSMS: clic derecho en `smart_parking` > **Tareas** > **Copia de seguridad...** > tipo **Completa** > **Aceptar**. Copia el `.bak` a la carpeta `database\` del proyecto. Vuelve a generarlo cada vez que avances.

**El código.**

```
git add .
git commit -m "Descripción del cambio"
git push
```

El equipo baja los cambios con `git pull`. Las fotos de los conductores y `config.py` no viajan por GitHub. Para ver las fotos en otra laptop, copia la carpeta `uploads\fotos` aparte, o registra conductores nuevos allá.

## Seguridad antes de entregar

- En `app.py`, `app.secret_key` debe ser una cadena larga y aleatoria. Genera una con `python -c "import secrets; print(secrets.token_hex(32))"`.
- En el final de `app.py`, usa `app.run(host="0.0.0.0", debug=False)`.
- Las contraseñas se guardan cifradas (hash), nunca en texto plano.
- No subas `config.py` ni datos de personas reales a un repositorio público.
- Las etiquetas guardan solo un token, no datos personales. Si se pierde una, se reemplaza desde el Padrón.

---

# Problemas comunes

| Mensaje o síntoma | Causa y solución |
|---|---|
| `ModuleNotFoundError: No module named 'pyodbc'` | Faltan las librerías. Activa el entorno y corre `pip install -r requirements.txt`. |
| `ModuleNotFoundError: No module named 'config'` | Falta crear `config.py` (Paso 5). |
| `Data source name not found` o `Can't open lib 'ODBC Driver 18...'` | Instala ODBC Driver 18 for SQL Server. |
| `Cannot open database "smart_parking"` | La base no existe en ese equipo. Haz el Paso 4. |
| `Login failed` | El usuario de Windows no tiene acceso a SQL Server. En SSMS: **Seguridad** > **Inicios de sesión** > agrega el usuario, o usa `DB_USER` y `DB_PASSWORD`. |
| `Invalid object name 'Usuarios'` en SSMS | La consulta corre en otra base. Escribe el nombre completo: `smart_parking.dbo.Usuarios`. |
| El celular no carga la página | Revisa que esté en la misma red, que el servidor corra, que la IP sea la de `URL_BASE` y que el firewall tenga abierto el puerto 5000. |
| La laptop no ve la red Wi-Fi "5G" | Su tarjeta solo ve 2.4 GHz. Cambia la banda de la zona a 2.4 GHz. |
| La etiqueta no abre nada | Activa el NFC en el celular, usa la pantalla encendida y desbloqueada, y cierra NFC Tools. Si abre el navegador pero no carga, el enlace tiene otra IP: regraba la etiqueta. |
| El enlace de la etiqueta dice `https://` | En NFC Tools elige `http://` en el menú del prefijo. El sistema no tiene HTTPS. |
| Dice "Etiqueta desactivada" | Se pulsó **Nueva etiqueta** después de grabar. Copia el enlace nuevo con **Ver enlace** y regraba. |
| Dice "Etiqueta no reconocida" | El token no existe. Revisa que el enlace se copió completo, o que no se limpió la base después de grabar. |
| "No se pudo leer la placa" | Foto borrosa, con reflejos o de lejos. Toma otra, o usa **Escribir la placa a mano**. |
| "El lector de placas no está disponible" | Falta `fast-alpr` o no descargó los modelos. Repite el Paso 9 con internet. |
| La placa es correcta pero dice que no coincide | La placa registrada tiene un error de captura (por ejemplo una `I` en lugar de un `1`). Corrígela en la base o vuelve a registrar al conductor. |
| iPhone: hay que tocar un aviso al acercar la etiqueta | Es normal. Apple exige tocar el aviso para abrir el enlace. |
| PowerShell bloquea `venv\Scripts\activate` | Ejecuta `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve a intentar. |

---

# Estado del proyecto

**Funciona**
- Registro de conductores con foto, login por roles y credencial.
- Padrón: activar y desactivar cuentas, asignar etiquetas.
- Lectura de etiquetas NFC en el celular del guardia.
- Lectura de placas con la cámara del celular y verificación contra la registrada.
- Historial de accesos y resumen.

**Siguiente etapa**
- Reconocimiento facial: comparar el rostro con la foto de perfil. La base ya tiene las columnas `RostroCoincide`, `ConfianzaRostro` y `FotoRostro`.
- Prototipo con cámara fija (webcam) que tome la foto de la placa sin intervención del guardia.
- Apertura automática de la pluma.
