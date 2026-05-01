from flask import Flask, request, render_template_string, redirect, url_for
import psycopg2
import datetime
import requests
import os
import re
import cloudinary
import cloudinary.uploader
from twilio.rest import Client
from functools import wraps

app = Flask(__name__)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

def requiere_autenticacion(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != ADMIN_PASSWORD:
            return 'Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
    return decorador

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabla reparaciones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reparaciones (
            id SERIAL PRIMARY KEY,
            codigo TEXT UNIQUE NOT NULL,
            cliente_nombre TEXT NOT NULL,
            cliente_telefono TEXT NOT NULL,
            equipo TEXT NOT NULL,
            marca TEXT,
            falla TEXT,
            presupuesto REAL,
            tecnico TEXT,
            fecha_entrada TEXT NOT NULL,
            fecha_salida TEXT,
            estado TEXT NOT NULL,
            notificado_24h INTEGER DEFAULT 0,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL,
            foto_url TEXT
        )
    ''')
    
    # Tabla garantías
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS garantias (
            id SERIAL PRIMARY KEY,
            codigo TEXT NOT NULL,
            cliente_nombre TEXT NOT NULL,
            cliente_telefono TEXT NOT NULL,
            equipo TEXT NOT NULL,
            marca TEXT,
            falla_original TEXT,
            tecnico TEXT,
            fecha_entrada TEXT NOT NULL,
            fecha_salida TEXT,
            estado TEXT NOT NULL,
            foto_url TEXT,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Base de datos lista")

# Cloudinary
CLOUD_NAME = "drpmg1lso"
API_KEY = "519922232242146"
API_SECRET = "kxsPgE73Eu59VQ03qSCvWCeaHw4"

# FORMULARIO
FORMULARIO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Nueva Reparación</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        input, textarea, select { display: block; margin: 10px 0; padding: 10px; width: 100%; max-width: 400px; border-radius: 5px; border: 1px solid #ccc; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0056b3; }
        h1 { color: #333; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin-top: 20px; }
        .btn:hover { background: #1e7e34; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 Nueva Reparación</h1>
        <form method="POST" enctype="multipart/form-data">
            <input type="text" name="cliente_nombre" placeholder="Nombre del cliente" required>
            <input type="text" name="cliente_telefono" placeholder="Teléfono" required>
            <input type="text" name="equipo" placeholder="Equipo" required>
            <input type="text" name="marca" placeholder="Marca">
            <textarea name="falla" placeholder="Falla" rows="3"></textarea>
            <input type="number" step="0.01" name="presupuesto" placeholder="Presupuesto">
            <input type="text" name="tecnico" placeholder="Técnico">
            <input type="file" name="foto" accept="image/*">
            <button type="submit">Guardar</button>
        </form>
        <a href="/listado" class="btn">📋 Listado</a>
        <a href="/garantias" class="btn">🛡️ Garantías</a>
        <a href="/consulta" class="btn">🔍 Consultar</a>
    </div>
</body>
</html>
'''

# LISTADO REPARACIONES
LISTADO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Listado</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 100%; margin: 0 auto; background: white; padding: 15px; border-radius: 10px; overflow-x: auto; }
        table { border-collapse: collapse; width: 100%; font-size: 13px; }
        th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
        th { background: #007bff; color: white; }
        .estado-en_reparacion { color: #ff9800; font-weight: bold; }
        .estado-espera_repuesto { color: #f44336; font-weight: bold; }
        .estado-lista { color: #4caf50; font-weight: bold; }
        .estado-entregado { color: #2196f3; font-weight: bold; }
        .estado-en_garantia { color: #9c27b0; font-weight: bold; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 6px 12px; text-decoration: none; border-radius: 5px; margin: 5px 0; font-size: 13px; }
        .btn-small { padding: 3px 8px; font-size: 11px; background: #007bff; color: white; text-decoration: none; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Reparaciones</h1>
        <a href="/" class="btn">➕ Nueva</a>
        <a href="/garantias" class="btn">🛡️ Garantías</a>
        <a href="/consulta" class="btn">🔍 Consultar</a>
        <form action="/buscar" method="GET" style="margin: 15px 0;">
            <input type="text" name="q" placeholder="Buscar..." value="{{ busqueda }}" style="padding: 5px; width: 200px;">
            <button type="submit" class="btn-small">Buscar</button>
            <a href="/listado" class="btn-small">Ver todos</a>
        </form>
        <div style="overflow-x: auto;">
        <table>
            <thead>
                <tr><th>Código</th><th>Cliente</th><th>Equipo</th><th>Estado</th><th>Entrada</th><th>Técnico</th><th>Foto</th><th>Acciones</th></tr>
            </thead>
            <tbody>
                {% for r in reparaciones %}
                <tr>
                    <td>{{ r[1] }}</td>
                    <td>{{ r[2] }}</td>
                    <td>{{ r[4] }} {{ r[5] }}</td>
                    <td class="estado-{{ r[11] }}">{{ r[11].replace('_', ' ') }}</td>
                    <td>{{ r[9][:10] if r[9] else '' }}</td>
                    <td>{{ r[8] if r[8] else '—' }}</td>
                    <td>{% if r[13] %}<a href="/foto/{{ r[0] }}" target="_blank" class="btn-small">📷</a>{% else %}—{% endif %}</td>
                    <td><a href="/editar/{{ r[0] }}" class="btn-small">✏️</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        </div>
    </div>
</body>
</html>
'''

# LISTADO GARANTÍAS
GARANTIAS_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Garantías</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 100%; margin: 0 auto; background: white; padding: 15px; border-radius: 10px; overflow-x: auto; }
        table { border-collapse: collapse; width: 100%; font-size: 13px; }
        th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }
        th { background: #9c27b0; color: white; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 6px 12px; text-decoration: none; border-radius: 5px; margin: 5px 0; font-size: 13px; }
        .btn-small { padding: 3px 8px; font-size: 11px; background: #9c27b0; color: white; text-decoration: none; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ Garantías</h1>
        <a href="/" class="btn">➕ Nueva</a>
        <a href="/listado" class="btn">📋 Listado</a>
        <a href="/consulta" class="btn">🔍 Consultar</a>
        <table>
            <thead>
                <tr><th>Código</th><th>Cliente</th><th>Equipo</th><th>Estado</th><th>Entrada</th><th>Técnico</th><th>Foto</th><th>Acciones</th></tr>
            </thead>
            <tbody>
                {% for g in garantias %}
                <tr>
                    <td>{{ g[1] }}</td>
                    <td>{{ g[2] }}</td>
                    <td>{{ g[4] }} {{ g[5] }}</td>
                    <td>{{ g[8].replace('_', ' ') }}</td>
                    <td>{{ g[7][:10] if g[7] else '' }}</td>
                    <td>{{ g[6] if g[6] else '—' }}</td>
                    <td>{% if g[9] %}<a href="/foto_garantia/{{ g[0] }}" target="_blank" class="btn-small">📷</a>{% else %}—{% endif %}</td>
                    <td><a href="/editar_garantia/{{ g[0] }}" class="btn-small">✏️</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
'''

# WHATSAPP Y TELEGRAM
def enviar_telegram(mensaje):
    token = "8742564082:AAGuvUN_q4NjBgUL70hcRsnCkwS-eumS6Sc"
    chat_id = "7150902056"
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})
    except:
        pass

def enviar_whatsapp(mensaje):
    try:
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        from_whatsapp = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        to_whatsapp = "whatsapp:+584123697532"
        if account_sid and auth_token:
            client = Client(account_sid, auth_token)
            client.messages.create(body=mensaje, from_=from_whatsapp, to=to_whatsapp)
    except:
        pass

def generar_codigo():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT codigo FROM reparaciones ORDER BY id DESC LIMIT 1")
    ultimo = cursor.fetchone()
    conn.close()
    if ultimo and ultimo[0].startswith('E-'):
        num = int(ultimo[0].split('-')[1]) + 1
    else:
        num = 1
    return f"E-{num:03d}"

def limpiar_telefono(numero):
    if not numero:
        return None
    limpio = re.sub(r'\D', '', numero)
    if limpio.startswith('0'):
        limpio = '58' + limpio[1:]
    elif len(limpio) == 11 and not limpio.startswith('58'):
        limpio = '58' + limpio
    elif len(limpio) == 10:
        limpio = '58' + limpio
    return limpio

# RUTAS
@app.route("/", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        codigo = generar_codigo()
        ahora = datetime.datetime.now().isoformat()
        foto_url = None
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto and foto.filename:
                cloudinary.config(cloud_name=CLOUD_NAME, api_key=API_KEY, api_secret=API_SECRET)
                upload = cloudinary.uploader.upload(foto)
                foto_url = upload.get('secure_url')
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reparaciones (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla, presupuesto, tecnico, fecha_entrada, estado, creado_en, actualizado_en, foto_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (codigo, request.form['cliente_nombre'], request.form['cliente_telefono'],
              request.form['equipo'], request.form.get('marca'), request.form.get('falla'),
              float(request.form['presupuesto']) if request.form['presupuesto'] else None,
              request.form.get('tecnico'), ahora, 'en_reparacion', ahora, ahora, foto_url))
        conn.commit()
        conn.close()
        mensaje = f"🆕 *Nueva reparación*\n📌 Código: {codigo}\n👤 Cliente: {request.form['cliente_nombre']}"
        enviar_telegram(mensaje)
        return redirect(url_for('nueva'))
    return render_template_string(FORMULARIO)

@app.route("/listado")
@requiere_autenticacion
def listado():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reparaciones ORDER BY id DESC")
    reparaciones = cursor.fetchall()
    conn.close()
    return render_template_string(LISTADO, reparaciones=reparaciones, busqueda='')

@app.route("/buscar")
@requiere_autenticacion
def buscar():
    busqueda = request.args.get('q', '')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reparaciones WHERE cliente_nombre ILIKE %s ORDER BY id DESC", (f'%{busqueda}%',))
    resultados = cursor.fetchall()
    conn.close()
    return render_template_string(LISTADO, reparaciones=resultados, busqueda=busqueda)

@app.route("/garantias")
@requiere_autenticacion
def ver_garantias():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM garantias ORDER BY id DESC")
    garantias = cursor.fetchall()
    conn.close()
    return render_template_string(GARANTIAS_HTML, garantias=garantias)

@app.route("/consulta", methods=["GET", "POST"])
def consulta():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        accion = request.form.get("accion", "")
        conn = get_db()
        cursor = conn.cursor()
        
        if accion == "cambiar_estado":
            cursor.execute("SELECT codigo, cliente_nombre, cliente_telefono, equipo, marca FROM reparaciones WHERE codigo = %s", (codigo,))
            ticket = cursor.fetchone()
            if ticket:
                cursor.execute("UPDATE reparaciones SET estado = 'lista', actualizado_en = %s WHERE codigo = %s", (datetime.datetime.now().isoformat(), codigo))
                conn.commit()
                mensaje = f"✅ *EQUIPO LISTO*\n📌 Código: {ticket[0]}\n👤 Cliente: {ticket[1]}\n🔧 Equipo: {ticket[3]} {ticket[4]}"
                enviar_telegram(mensaje)
                enviar_whatsapp(mensaje)
            conn.close()
            return '<h3>✅ Ticket marcado como LISTO</h3><a href="/consulta">Volver</a>'
        
        if accion == "marcar_garantia":
            cursor.execute("SELECT codigo, cliente_nombre, cliente_telefono, equipo, marca, falla FROM reparaciones WHERE codigo = %s", (codigo,))
            ticket = cursor.fetchone()
            if ticket:
                cursor.execute("UPDATE reparaciones SET estado = 'en_garantia', actualizado_en = %s WHERE codigo = %s", (datetime.datetime.now().isoformat(), codigo))
                ahora = datetime.datetime.now().isoformat()
                cursor.execute('''
                    INSERT INTO garantias (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla_original, tecnico, fecha_entrada, estado, creado_en, actualizado_en)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (ticket[0], ticket[1], ticket[2], ticket[3], ticket[4], ticket[5], None, ahora, 'en_reparacion', ahora, ahora))
                conn.commit()
                mensaje = f"🛡️ *EQUIPO EN GARANTÍA*\n📌 Código: {ticket[0]}\n👤 Cliente: {ticket[1]}\n🔧 Equipo: {ticket[3]} {ticket[4]}"
                enviar_telegram(mensaje)
                enviar_whatsapp(mensaje)
            conn.close()
            return '<h3>🛡️ Ticket marcado como GARANTÍA</h3><a href="/consulta">Volver</a>'
        
        cursor.execute("SELECT id, codigo, estado, foto_url, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo = %s", (codigo,))
        resultado = cursor.fetchone()
        conn.close()
        if resultado and resultado[3]:
            foto_url = resultado[3]
            estado = resultado[2]
            mostrar_listo = (estado in ['en_reparacion', 'espera_repuesto'])
            mostrar_garantia = (estado not in ['entregado', 'no_procede', 'en_garantia'])
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Ticket {codigo}</title>
                <style>
                    body {{ font-family: sans-serif; margin: 20px; background: #f0f2f5; text-align: center; }}
                    .container {{ max-width: 500px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
                    img {{ max-width: 100%; border-radius: 10px; margin: 20px 0; }}
                    .estado {{ font-size: 18px; margin: 10px 0; padding: 8px; border-radius: 5px; }}
                    .estado-en_reparacion {{ background: #fff3e0; color: #ff9800; }}
                    .estado-espera_repuesto {{ background: #ffebee; color: #f44336; }}
                    .estado-lista {{ background: #e8f5e9; color: #4caf50; }}
                    .estado-entregado {{ background: #e3f2fd; color: #2196f3; }}
                    .estado-en_garantia {{ background: #f3e5f5; color: #9c27b0; }}
                    button {{ background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; margin: 10px 5px; }}
                    button:hover {{ background: #0056b3; }}
                    .btn-garantia {{ background: #9c27b0; }}
                    .btn-garantia:hover {{ background: #7b1fa2; }}
                    .btn-volver {{ display: inline-block; background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 15px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🔍 Ticket {codigo}</h1>
                    <div class="estado estado-{estado}">
                        📌 Estado: {estado.replace('_', ' ').upper()}
                    </div>
                    <img src="{foto_url}" alt="Foto">
                    <div style="display: flex; gap: 15px; justify-content: center; flex-wrap: wrap; margin: 20px 0;">
                        {'<form method="POST"><input type="hidden" name="codigo" value="' + codigo + '"><input type="hidden" name="accion" value="cambiar_estado"><button type="submit">✅ LISTO</button></form>' if mostrar_listo else ''}
                        {'<form method="POST"><input type="hidden" name="codigo" value="' + codigo + '"><input type="hidden" name="accion" value="marcar_garantia"><button type="submit" class="btn-garantia">🛡️ GARANTÍA</button></form>' if mostrar_garantia else ''}
                    </div>
                    <a href="/consulta" class="btn-volver">← Volver</a>
                </div>
            </body>
            </html>
            '''
        else:
            return '<h3>❌ Código no encontrado</h3><a href="/consulta">Volver</a>', 404
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Consultar</title>
        <style>
            body { font-family: sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; }
            .container { max-width: 400px; background: white; padding: 30px; border-radius: 15px; text-align: center; }
            input { width: 90%; padding: 12px; margin: 10px 0; border: 2px solid #e0e0e0; border-radius: 8px; }
            button { width: 100%; padding: 12px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Consultar Ticket</h1>
            <form method="POST">
                <input type="text" name="codigo" placeholder="Ej: E-001" required>
                <button type="submit">Ver</button>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route("/foto/<int:id>")
def foto(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT foto_url FROM reparaciones WHERE id = %s", (id,))
    resultado = cursor.fetchone()
    conn.close()
    if resultado and resultado[0]:
        return f'<html><body style="text-align:center;margin-top:50px;"><img src="{resultado[0]}" style="max-width:90%;"></body></html>'
    return "Sin foto", 404

@app.route("/foto_garantia/<int:id>")
def foto_garantia(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT foto_url FROM garantias WHERE id = %s", (id,))
    resultado = cursor.fetchone()
    conn.close()
    if resultado and resultado[0]:
        return f'<html><body style="text-align:center;margin-top:50px;"><img src="{resultado[0]}" style="max-width:90%;"></body></html>'
    return "Sin foto", 404

@app.route("/editar_garantia/<int:id>", methods=["GET", "POST"])
@requiere_autenticacion
def editar_garantia(id):
    conn = get_db()
    cursor = conn.cursor()
    if request.method == "POST":
        cursor.execute("SELECT codigo, cliente_nombre, equipo, marca, cliente_telefono FROM garantias WHERE id = %s", (id,))
        garantia = cursor.fetchone()
        estado_nuevo = request.form.get("estado")
        tecnico = request.form.get("tecnico")
        actualizado = datetime.datetime.now().isoformat()
        if estado_nuevo == 'lista':
            cursor.execute("UPDATE reparaciones SET estado = 'lista', actualizado_en = %s WHERE codigo = %s", (actualizado, garantia[0]))
            cursor.execute("UPDATE garantias SET estado = %s, tecnico = %s, actualizado_en = %s, fecha_salida = %s WHERE id = %s", ('lista', tecnico, actualizado, actualizado, id))
            mensaje = f"🛡️ *GARANTÍA LISTA*\n📌 Código: {garantia[0]}\n👤 Cliente: {garantia[1]}\n🔧 Equipo: {garantia[2]} {garantia[3]}"
            enviar_telegram(mensaje)
            enviar_whatsapp(mensaje)
        else:
            cursor.execute("UPDATE garantias SET estado = %s, tecnico = %s, actualizado_en = %s WHERE id = %s", (estado_nuevo, tecnico, actualizado, id))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_garantias'))
    cursor.execute("SELECT * FROM garantias WHERE id = %s", (id,))
    g = cursor.fetchone()
    conn.close()
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Editar Garantía</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
            input, select {{ display: block; margin: 10px 0; padding: 8px; width: 100%; }}
            button {{ background: #9c27b0; color: white; padding: 10px; border: none; border-radius: 5px; cursor: pointer; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✏️ Editar Garantía</h1>
            <form method="POST">
                <label>Técnico:</label>
                <input type="text" name="tecnico" value="{g[6] or ''}">
                <label>Estado:</label>
                <select name="estado">
                    <option value="en_reparacion" {'selected' if g[8] == 'en_reparacion' else ''}>En reparación</option>
                    <option value="espera_repuesto" {'selected' if g[8] == 'espera_repuesto' else ''}>Espera repuesto</option>
                    <option value="lista" {'selected' if g[8] == 'lista' else ''}>Lista</option>
                </select>
                <button type="submit">Guardar</button>
                <a href="/garantias">Volver</a>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route("/editar/<int:id>", methods=["GET", "POST"])
@requiere_autenticacion
def editar(id):
    conn = get_db()
    cursor = conn.cursor()
    if request.method == "POST":
        equipo = request.form.get("equipo")
        marca = request.form.get("marca")
        falla = request.form.get("falla")
        presupuesto = request.form.get("presupuesto")
        tecnico = request.form.get("tecnico")
        estado = request.form.get("estado")
        actualizado = datetime.datetime.now().isoformat()
        cursor.execute('''
            UPDATE reparaciones SET equipo=%s, marca=%s, falla=%s, presupuesto=%s, tecnico=%s, estado=%s, actualizado_en=%s WHERE id=%s
        ''', (equipo, marca, falla, presupuesto, tecnico, estado, actualizado, id))
        conn.commit()
        conn.close()
        return redirect(url_for('listado'))
    cursor.execute("SELECT * FROM reparaciones WHERE id = %s", (id,))
    r = cursor.fetchone()
    conn.close()
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Editar</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
            input, textarea, select {{ display: block; margin: 10px 0; padding: 8px; width: 100%; }}
            button {{ background: #007bff; color: white; padding: 10px; border: none; border-radius: 5px; cursor: pointer; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✏️ Editar {r[1]}</h1>
            <form method="POST">
                <label>Equipo:</label>
                <input type="text" name="equipo" value="{r[4]}">
                <label>Marca:</label>
                <input type="text" name="marca" value="{r[5] or ''}">
                <label>Falla:</label>
                <textarea name="falla" rows="3">{r[6] or ''}</textarea>
                <label>Presupuesto:</label>
                <input type="number" step="0.01" name="presupuesto" value="{r[7] or ''}">
                <label>Técnico:</label>
                <input type="text" name="tecnico" value="{r[8] or ''}">
                <label>Estado:</label>
                <select name="estado">
                    <option value="en_reparacion" {'selected' if r[11] == 'en_reparacion' else ''}>En reparación</option>
                    <option value="espera_repuesto" {'selected' if r[11] == 'espera_repuesto' else ''}>Espera repuesto</option>
                    <option value="lista" {'selected' if r[11] == 'lista' else ''}>Listo</option>
                    <option value="entregado" {'selected' if r[11] == 'entregado' else ''}>Entregado</option>
                    <option value="no_procede" {'selected' if r[11] == 'no_procede' else ''}>No Procede</option>
                </select>
                <button type="submit">Guardar</button>
                <a href="/listado">Volver</a>
            </form>
        </div>
    </body>
    </html>
    '''

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
