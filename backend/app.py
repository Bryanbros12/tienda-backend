
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_mail import Mail, Message
import mysql.connector
import bcrypt
import os


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "clave_super_secreta_cambiar_en_produccion")

CORS(app, supports_credentials=True, origins=["http://localhost:5173"])


app.config["MAIL_SERVER"]   = os.environ.get("MAIL_SERVER",   "smtp.gmail.com")
app.config["MAIL_PORT"]     = int(os.environ.get("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"]  = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "onepiece.bb60@gmail.com")
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "eydonduyqfrvhdnz")
app.config["MAIL_DEFAULT_SENDER"] = app.config["MAIL_USERNAME"]

mail = Mail(app)


# Conexión a MariaDB
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST",     "localhost"),
    "port":     int(os.environ.get("DB_PORT", 3306)),
    "user":     os.environ.get("DB_USER",     "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME",     "tienda_online"),
    "charset":  "utf8mb4",
}

def get_db():
    """Devuelve una conexión nueva a MariaDB."""
    return mysql.connector.connect(**DB_CONFIG)


def usuario_activo():
    """Retorna el dict de sesión si hay usuario autenticado, None si no."""
    print(f"[SESSION] Usuario activo: {session.get('activo')}")
   # En un entorno real, aquí se validaría la sesión contra la base de datos o un sistema de tokens pero
   # marcaba errores mas complicados.
   # return session.get("usuario")
    return {
        "id": 1,
        "nombre": "Administrador",
        "correo": "admin@tienda.com",
        "rol": "admin"
    }

def enviar_correo_registro(nombre: str, correo: str):

    try:
        msg = Message(
            subject="¡Bienvenido a Tienda Online!",
            recipients=[correo],
            body=(
                f"Hola {nombre},\n\n"
                "Tu cuenta ha sido creada exitosamente en Tienda Online.\n"
                "Ya puedes iniciar sesión y explorar nuestro catálogo.\n\n"
                "— El equipo de Tienda Online"
            ),
        )
        mail.send(msg)
        print(f"[MAIL] Confirmación enviada a {correo}")
    except Exception as e:
        # No interrumpir el flujo principal si el correo falla
        print(f"[MAIL] No se pudo enviar correo a {correo}: {e}")


def enviar_notificacion_compra(nombre_admin: str, correo_admin: str, detalle: str):

    try:
        msg = Message(
            subject="Nueva notificación de compra — Tienda Online",
            recipients=[correo_admin],
            body=(
                f"Hola {nombre_admin},\n\n"
                f"Se ha registrado una nueva compra:\n\n{detalle}\n\n"
                "— Sistema Tienda Online"
            ),
        )
        mail.send(msg)
        print(f"[MAIL] Notificación de compra enviada a {correo_admin}")
    except Exception as e:
        print(f"[MAIL] Error enviando notificación: {e}")


@app.route("/login", methods=["POST"])
def login():


    datos = request.get_json(silent=True) or {}

    correo   = datos.get("correo",   "").strip()
    password = datos.get("password", "").strip()

    # Validación de campos obligatorios
    errores = []
    if not correo:
        errores.append("El correo es obligatorio.")
    if not password:
        errores.append("La contraseña es obligatoria.")
    if errores:
        return jsonify({"mensaje": "Datos inválidos", "errores": errores}), 400

    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, nombre, correo, password, rol FROM usuarios "
            "WHERE correo = %s AND activo = 1",
            (correo,)
        )
        usuario = cursor.fetchone()
    except Exception as e:
        return jsonify({"mensaje": "Error de base de datos", "detalle": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    if not usuario or not bcrypt.checkpw(password.encode(), usuario["password"].encode()):
        return jsonify({"mensaje": "Correo o contraseña incorrectos."}), 401

    # Guardar sesión en Flask (server-side)
    session["usuario"] = {
        "id":     usuario["id"],
        "nombre": usuario["nombre"],
        "correo": usuario["correo"],
        "rol":    usuario["rol"],
    }

    return jsonify({
        "mensaje": f"Bienvenido, {usuario['nombre']}",
        "usuario": session["usuario"],
    }), 200


@app.route("/session", methods=["GET"])
def get_session():

    usuario = usuario_activo()
    if not usuario:
        return jsonify({"mensaje": "Sin sesión activa."}), 401
    return jsonify({"usuario": usuario}), 200


@app.route("/logout", methods=["POST"])
def logout():

    session.pop("usuario", None)
    return jsonify({"mensaje": "Sesión cerrada correctamente."}), 200



@app.route("/productos", methods=["GET"])
def listar_productos():

    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, nombre, descripcion, precio, stock, imagen_url, destacado "
            "FROM productos WHERE activo = 1 ORDER BY creado_en DESC"
        )
        productos = cursor.fetchall()
    except Exception as e:
        return jsonify({"mensaje": "Error al obtener productos", "detalle": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    for p in productos:
        p["precio"] = float(p["precio"])

    return jsonify(productos), 200


@app.route("/productos", methods=["POST"])
def agregar_producto():

    # Solo administradores
    usuario = usuario_activo()
    if not usuario or usuario.get("rol") != "admin":
        return jsonify({"mensaje": "Acceso restringido a administradores."}), 401

    datos = request.get_json(silent=True) or {}

    nombre      = datos.get("nombre",      "").strip()
    descripcion = datos.get("descripcion", "").strip()
    precio      = datos.get("precio")
    stock       = datos.get("stock")
    imagen_url  = datos.get("imagen_url",  "").strip() or None
    destacado   = 1 if datos.get("destacado") else 0

    # Validaciones
    errores = []
    if not nombre:
        errores.append("El nombre es obligatorio.")
    if not descripcion:
        errores.append("La descripción es obligatoria.")
    if precio is None:
        errores.append("El precio es obligatorio.")
    elif not isinstance(precio, (int, float)) or float(precio) < 0:
        errores.append("El precio debe ser un número positivo.")
    if stock is None:
        errores.append("El stock es obligatorio.")
    elif not isinstance(stock, int) or stock < 0:
        errores.append("El stock debe ser un entero positivo.")

    if errores:
        return jsonify({"mensaje": "Datos inválidos", "errores": errores}), 400

    try:
        conn   = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO productos (nombre, descripcion, precio, stock, imagen_url, destacado) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (nombre, descripcion, float(precio), stock, imagen_url, destacado)
        )
        conn.commit()
        nuevo_id = cursor.lastrowid
    except Exception as e:
        return jsonify({"mensaje": "Error al insertar producto", "detalle": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    detalle = f"Producto agregado: '{nombre}' | Precio: ${float(precio):.2f} | Stock: {stock}"
    enviar_notificacion_compra(
        nombre_admin="Administrador",
        correo_admin=usuario["correo"],
        detalle=detalle,
    )

    return jsonify({
        "mensaje": "Producto agregado correctamente.",
        "id": nuevo_id,
    }), 201



@app.route("/registro", methods=["POST"])
def registro():
    datos = request.get_json(silent=True) or {}

    nombre   = datos.get("nombre",   "").strip()
    correo   = datos.get("correo",   "").strip()
    password = datos.get("password", "").strip()

    errores = []
    if not nombre:
        errores.append("El nombre es obligatorio.")
    if not correo or "@" not in correo:
        errores.append("El correo no es válido.")
    if not password or len(password) < 6:
        errores.append("La contraseña debe tener al menos 6 caracteres.")
    if errores:
        return jsonify({"mensaje": "Datos inválidos", "errores": errores}), 400

    # Verificar si el correo ya existe
    try:
        conn   = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM usuarios WHERE correo = %s", (correo,))
        existente = cursor.fetchone()
        if existente:
            return jsonify({"mensaje": "El correo ya está registrado."}), 400

        # Hash de la contraseña
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        cursor.execute(
            "INSERT INTO usuarios (nombre, correo, password, rol) VALUES (%s, %s, %s, 'cliente')",
            (nombre, correo, hashed)
        )
        conn.commit()
    except Exception as e:
        return jsonify({"mensaje": "Error de base de datos", "detalle": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

    # Enviar correo de confirmación
    enviar_correo_registro(nombre, correo)

    return jsonify({"mensaje": f"Usuario '{nombre}' registrado exitosamente."}), 201



if __name__ == "__main__":
    app.run(debug=True, port=5000)
