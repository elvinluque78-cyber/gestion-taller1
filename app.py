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

def requiere_auth(f):
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
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS reparaciones (
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
        foto_url TEXT,
        video_url TEXT,
        testigo_tecnico BOOLEAN DEFAULT FALSE,
        fecha_prueba TEXT,
        creado_en TEXT NOT NULL,
        actualizado_en TEXT NOT NULL
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS garantias (
        id SERIAL PRIMARY KEY,
        codigo TEXT NOT NULL,
        cliente_nombre TEXT NOT NULL,
        cliente_telefono TEXT NOT NULL,
        equipo TEXT NOT NULL,
        marca TEXT,
        falla_original TEXT,
        tecnico TEXT,
        fecha_entrada_garantia TEXT NOT NULL,
        fecha_salida_garantia TEXT,
        estado_garantia TEXT NOT NULL,
        foto_url TEXT,
        creado_en TEXT,
        actualizado_en TEXT
    )''')
    conn.commit()
    conn.close()
    print("✅ Base de datos lista")

# ==================== CLOUDINARY ====================
CLOUD_NAME = "drpmg1lso"
API_KEY = "519922232242146"
API_SECRET = "kxsPgE73Eu59VQ03qSCvWCeaHw4"

# ==================== WHATSAPP (Credenciales directas) ====================
TWILIO_SID = "AC1eee15ecfd80fc2a2eadaaf00326ea0b"
TWILIO_AUTH = "e0149c3decfd1a4afa945fdf1ee6f1bd"
TWILIO_FROM = "whatsapp:+14155238886"
TECNICO_TO = "whatsapp:+584123697532"

def enviar_whatsapp(mensaje):
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
        data = {"From": TWILIO_FROM, "To": TECNICO_TO, "Body": mensaje}
        response = requests.post(url, data=data, auth=(TWILIO_SID, TWILIO_AUTH), timeout=10)
        print(f"WhatsApp response: {response.status_code}")
    except Exception as e:
        print(f"Error WhatsApp: {e}")

def enviar_telegram(mensaje):
    token = "8742564082:AAGpNhCm06UoVks-5Jk7_jattokUSAkKXKI"
    chat_id = "7150902056"
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})
    except:
        pass

def generar_codigo():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT codigo FROM reparaciones ORDER BY id DESC LIMIT 1")
    ult = cur.fetchone()
    conn.close()
    num = 1 if not ult else int(ult[0].split('-')[1]) + 1
    return f"E-{num:03d}"

def limpiar_numero_telefono(numero):
    if not numero:
        return None
    numero_limpio = re.sub(r'\D', '', numero)
    if numero_limpio.startswith('0'):
        numero_limpio = '58' + numero_limpio[1:]
    elif len(numero_limpio) == 11 and not numero_limpio.startswith('58'):
        numero_limpio = '58' + numero_limpio
    elif len(numero_limpio) == 10:
        numero_limpio = '58' + numero_limpio
    return numero_limpio

# ==================== HTML ====================
FORMULARIO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Nueva Reparación</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; margin: 20px; }
        .container { max-width: 650px; margin: 0 auto; background: white; padding: 40px; border-radius: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); }
        h1 { text-align: center; color: #1a1a2e; margin-bottom: 30px; font-size: 32px; }
        input, textarea, select { width: 100%; padding: 14px; margin: 12px 0; border-radius: 12px; border: 1px solid #ddd; font-size: 16px; }
        button { background: linear-gradient(135deg, #007bff, #0056b3); color: white; padding: 14px; border: none; border-radius: 50px; cursor: pointer; width: 100%; font-size: 18px; font-weight: bold; transition: 0.3s; }
        button:hover { transform: scale(1.02); }
        .btn { display: inline-block; background: #28a745; color: white; padding: 12px 24px; text-decoration: none; border-radius: 50px; margin: 10px 5px; font-size: 16px; }
        .btn-group { text-align: center; margin-top: 25px; }
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
            <button type="submit">Guardar reparación</button>
        </form>
        <div class="btn-group">
            <a href="/listado" class="btn">📋 Ver listado</a>
            <a href="/garantias" class="btn">🛡️ Garantías</a>
            <a href="/consulta" class="btn">🔍 Consultar ticket</a>
        </div>
    </div>
</body>
</html>
'''

LISTADO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=yes">
    <title>Listado de Reparaciones</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; margin: 0; padding: 15px; }
        .container { max-width: 100%; margin: 0 auto; background: white; padding: 15px; border-radius: 20px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); overflow-x: auto; }
        h1 { color: #1a1a2e; margin: 0 0 15px 0; font-size: 22px; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 15px; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 50px; font-size: 13px; font-weight: bold; }
        .btn-small { padding: 6px 12px; font-size: 11px; background: #007bff; color: white; text-decoration: none; border-radius: 25px; display: inline-block; }
        .buscar-form { margin: 15px 0; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
        .buscar-form input { padding: 8px 12px; border: 1px solid #ddd; border-radius: 50px; flex: 1; min-width: 180px; font-size: 13px; }
        table { width: 100%; border-collapse: collapse; font-size: 12px; min-width: 800px; }
        th, td { border: 1px solid #ddd; padding: 8px 6px; text-align: left; vertical-align: middle; }
        th { background: #007bff; color: white; font-weight: bold; font-size: 12px; white-space: nowrap; }
        tr:nth-child(even) { background: #f8f9fa; }
        .estado-en_reparacion { color: #ff9800; font-weight: bold; }
        .estado-espera_repuesto { color: #f44336; font-weight: bold; }
        .estado-lista { color: #4caf50; font-weight: bold; }
        .estado-entregado { color: #2196f3; font-weight: bold; }
        .estado-en_garantia { color: #9c27b0; font-weight: bold; }
        .foto { max-width: 80px; height: auto; border-radius: 5px; }
        .oculto { display: none; }
        .btn-foto { background: #17a2b8; color: white; padding: 6px 12px; border: none; border-radius: 25px; cursor: pointer; font-size: 11px; margin-bottom: 15px; }
        @media (max-width: 768px) {
            body { padding: 10px; }
            .container { padding: 10px; }
            th, td { padding: 6px 4px; font-size: 10px; }
            .btn { padding: 5px 10px; font-size: 11px; }
            h1 { font-size: 18px; }
        }
    </style>
    <script>
        function toggleFotos() {
            var fotos = document.querySelectorAll('.foto-ticket');
            fotos.forEach(function(foto) {
                foto.classList.toggle('oculto');
            });
        }
    </script>
</head>
<body>
<div class="container">
    <h1>📋 Listado de Reparaciones</h1>
    <div class="btn-group">
        <a href="/" class="btn">➕ Nueva reparación</a>
        <a href="/garantias" class="btn">🛡️ Garantías</a>
        <a href="/consulta" class="btn">🔍 Consultar ticket</a>
    </div>
    <button class="btn-foto" onclick="toggleFotos()">📸 Mostrar/Ocultar Fotos</button>
    <form action="/buscar" method="GET" class="buscar-form">
        <input type="text" name="q" placeholder="🔍 Buscar por nombre de cliente..." value="{{ busqueda }}">
        <button type="submit" class="btn-small">Buscar</button>
        <a href="/listado" class="btn-small" style="background:#dc3545;">Ver todos</a>
    </form>
    <div style="overflow-x: auto;">
    <table>
        <thead>
            <tr>
                <th>Código</th><th>Cliente</th><th>Teléfono</th>
                <th>Equipo</th><th>Marca</th><th>Falla</th>
                <th>Estado</th><th>Entrada</th><th>Salida</th>
                <th>Técnico</th><th>Foto</th><th>Video</th><th>Acciones</th>
            </tr>
        </thead>
        <tbody>
            {% for r in reparaciones %}
            <tr>
                <td>{{ r[1] }}</td>
                <td>{{ r[2] }}</td>
                <td>{{ r[3] }}</td>
                <td>{{ r[4] }}</td>
                <td>{{ r[5] if r[5] else '-' }}</td>
                <td>{{ r[6][:40] if r[6] else '-' }}{% if r[6] and r[6]|length > 40 %}...{% endif %}</td>
                <td class="estado-{{ r[11] }}">{{ r[11].replace('_', ' ') }}</td>
                <td>{{ r[9][:10] if r[9] else '-' }}</td>
                <td>{% if r[10] %}{{ r[10][:10] }}{% else %}-{% endif %}</td>
                <td>{{ r[8] if r[8] else '-' }}</td>
                <td class="foto-ticket oculto">{% if r[13] %}<img src="{{ r[13] }}" class="foto">{% else %}-{% endif %}</td>
                <td>{% if r[14] %}<a href="{{ r[14] }}" target="_blank">🎥</a>{% else %}-{% endif %}</td>
                <td><a href="/editar/{{ r[0] }}" class="btn-small">✏️ Editar</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
    {% if not reparaciones %}
    <p style="text-align:center;color:#666;padding:30px;">No hay reparaciones registradas.</p>
    {% endif %}
</div>
</body>
</html>
'''

GARANTIAS_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=yes">
    <title>Garantías</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }
        .container { max-width: 1300px; margin: 0 auto; background: white; padding: 25px; border-radius: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); overflow-x: auto; }
        h1 { color: #9c27b0; margin: 0 0 20px 0; font-size: 32px; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 10px 24px; text-decoration: none; border-radius: 50px; margin: 0; font-size: 14px; font-weight: bold; }
        .btn-small { padding: 8px 16px; font-size: 12px; background: #9c27b0; color: white; text-decoration: none; border-radius: 25px; display: inline-block; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; min-width: 900px; }
        th, td { border: 1px solid #e0e0e0; padding: 12px 10px; text-align: left; }
        th { background: linear-gradient(135deg, #9c27b0, #7b1fa2); color: white; }
        tr:nth-child(even) { background: #f8f9fa; }
        tr:hover { background: #f1f1f1; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ Gestión de Garantías</h1>
        <div class="btn-group">
            <a href="/" class="btn">➕ Nueva reparación</a>
            <a href="/listado" class="btn">📋 Listado</a>
            <a href="/consulta" class="btn">🔍 Consultar ticket</a>
        </div>
        </table>
            <thead>
                <tr>
                    <th>Código</th><th>Cliente</th><th>Equipo</th><th>Estado</th>
                    <th>Entrada Garantía</th><th>Salida Garantía</th><th>Técnico</th><th>Foto</th><th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                {% for g in garantias %}
                <tr>
                    <td>{{ g[1] }}</td>
                    <td>{{ g[2] }}</td>
                    <td>{{ g[4] }} {{ g[5] }}</td>
                    <td>{{ g[8].replace('_', ' ') }}</td>
                    <td>{{ g[7][:10] if g[7] else '' }}</td>
                    <td>{% if g[10] %}{{ g[10][:10] }}{% else %}—{% endif %}</td>
                    <td>{{ g[6] if g[6] else '—' }}</td>
                    <td>{% if g[9] %}<a href="/foto_garantia/{{ g[0] }}" target="_blank" class="btn-small">📷 Ver</a>{% else %}—{% endif %}</td>
                    <td><a href="/editar_garantia/{{ g[0] }}" class="btn-small">✏️ Editar</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
'''

@app.route("/", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        codigo = generar_codigo()
        ahora = datetime.datetime.now().isoformat()
        
        foto_url = None
        if 'foto' in request.files and request.files['foto'].filename:
            try:
                cloudinary.config(cloud_name=CLOUD_NAME, api_key=API_KEY, api_secret=API_SECRET)
                upload_result = cloudinary.uploader.upload(request.files['foto'])
                foto_url = upload_result.get('secure_url')
            except Exception as e:
                print(f"⚠️ Error al subir foto: {e}")
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reparaciones (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla, presupuesto, tecnico, fecha_entrada, estado, creado_en, actualizado_en, foto_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (codigo, request.form.get('cliente_nombre'), request.form.get('cliente_telefono'),
              request.form.get('equipo'), request.form.get('marca'), request.form.get('falla'),
              float(request.form.get('presupuesto')) if request.form.get('presupuesto') else None,
              request.form.get('tecnico'), ahora, 'en_reparacion', ahora, ahora, foto_url))
        conn.commit()
        conn.close()
        
        mensaje_telegram = f"🆕 *Nueva reparación*\n📌 Código: {codigo}\n👤 Cliente: {request.form.get('cliente_nombre')}\n📞 Tel: {request.form.get('cliente_telefono')}\n🔧 Equipo: {request.form.get('equipo')} {request.form.get('marca')}\n⚠️ Falla: {request.form.get('falla')}\n💰 Presupuesto: {request.form.get('presupuesto')}\n👨‍🔧 Técnico: {request.form.get('tecnico')}"
        if foto_url:
            mensaje_telegram += f"\n📸 Foto: {foto_url}"
        enviar_telegram(mensaje_telegram)
        
        mensaje_whatsapp = f"🧾 NUEVO TICKET {codigo}\nCliente: {request.form.get('cliente_nombre')}\nEquipo: {request.form.get('equipo')}\n✅ REENVIA ESTE MENSAJE AL CLIENTE"
        enviar_whatsapp(mensaje_whatsapp)
        
        return redirect(url_for('nueva'))
    return render_template_string(FORMULARIO)

@app.route("/listado")
@requiere_auth
def listado():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reparaciones ORDER BY id DESC")
    reparaciones = cursor.fetchall()
    conn.close()
    return render_template_string(LISTADO, reparaciones=reparaciones, busqueda='')

@app.route("/buscar")
@requiere_auth
def buscar():
    busqueda = request.args.get('q', '')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reparaciones WHERE cliente_nombre ILIKE %s ORDER BY id DESC", (f'%{busqueda}%',))
    resultados = cursor.fetchall()
    conn.close()
    return render_template_string(LISTADO, reparaciones=resultados, busqueda=busqueda)

@app.route("/garantias")
@requiere_auth
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
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reparaciones WHERE codigo = %s", (codigo,))
        reparacion = cursor.fetchone()
        conn.close()
        if reparacion:
            return render_template_string(DETALLE_TICKET, reparacion=reparacion)
        else:
            return '''
            <script>
                alert("❌ No se encontró el ticket.");
                window.location.href = "/consulta";
            </script>
            '''
    return render_template_string(CONSULTA_HTML)

CONSULTA_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Consultar Ticket</title>
    <style>
        body { font-family: Arial; background: #f0f2f5; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .container { background: white; padding: 40px; border-radius: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); text-align: center; max-width: 400px; width: 90%; }
        input { width: 100%; padding: 14px; margin: 20px 0; border-radius: 12px; border: 1px solid #ddd; font-size: 16px; }
        button { background: #007bff; color: white; padding: 14px; border: none; border-radius: 50px; cursor: pointer; width: 100%; font-size: 16px; }
        button:hover { background: #0056b3; }
        .btn-volver { display: block; margin-top: 15px; color: #666; text-decoration: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🔍 Consultar Ticket</h2>
        <form method="POST">
            <input type="text" name="codigo" placeholder="Ejemplo: E-001" required>
            <button type="submit">Buscar</button>
        </form>
        <a href="/" class="btn-volver">← Volver al inicio</a>
    </div>
</body>
</html>
'''

DETALLE_TICKET = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Ticket {{ reparacion[1] }}</title>
    <style>
        body { font-family: Arial; background: #f0f2f5; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; padding: 20px; }
        .container { background: white; padding: 30px; border-radius: 25px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); max-width: 600px; width: 100%; }
        h2 { color: #007bff; margin-top: 0; }
        .info { margin: 10px 0; }
        .label { font-weight: bold; display: inline-block; width: 120px; }
        .foto { margin-top: 20px; text-align: center; }
        .foto img { max-width: 100%; border-radius: 10px; }
        .volver { display: inline-block; margin-top: 20px; color: #007bff; text-decoration: none; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🔍 Ticket {{ reparacion[1] }}</h2>
        <div class="info"><span class="label">Cliente:</span> {{ reparacion[2] }}</div>
        <div class="info"><span class="label">Teléfono:</span> {{ reparacion[3] }}</div>
        <div class="info"><span class="label">Equipo:</span> {{ reparacion[4] }} {{ reparacion[5] }}</div>
        <div class="info"><span class="label">Falla:</span> {{ reparacion[6] }}</div>
        <div class="info"><span class="label">Estado:</span> {{ reparacion[11].replace('_', ' ') }}</div>
        <div class="info"><span class="label">Ingreso:</span> {{ reparacion[9][:10] if reparacion[9] else '-' }}</div>
        {% if reparacion[14] %}
        <div class="info"><span class="label">Video:</span> <a href="{{ reparacion[14] }}" target="_blank">Ver video</a></div>
        {% endif %}
        {% if reparacion[13] %}
        <div class="foto"><img src="{{ reparacion[13] }}" alt="Foto del equipo"></div>
        {% endif %}
        <a href="/consulta" class="volver">← Nueva consulta</a>
    </div>
</body>
</html>
'''

@app.route("/editar/<int:id>", methods=["GET", "POST"])
@requiere_auth
def editar(id):
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == "POST":
        nuevo_estado = request.form.get('estado')
        equipo = request.form.get('equipo')
        marca = request.form.get('marca')
        falla = request.form.get('falla')
        tecnico = request.form.get('tecnico')
        cliente_nombre = request.form.get('cliente_nombre')
        cliente_telefono = request.form.get('cliente_telefono')
        
        # Obtener datos actuales para notificaciones
        cursor.execute("SELECT * FROM reparaciones WHERE id = %s", (id,))
        reparacion = cursor.fetchone()
        
        # Actualizar foto si se subió
        if 'foto' in request.files and request.files['foto'].filename:
            try:
                cloudinary.config(cloud_name=CLOUD_NAME, api_key=API_KEY, api_secret=API_SECRET)
                upload_result = cloudinary.uploader.upload(request.files['foto'])
                foto_url = upload_result.get('secure_url')
                cursor.execute("UPDATE reparaciones SET foto_url = %s WHERE id = %s", (foto_url, id))
            except Exception as e:
                print(f"⚠️ Error al subir foto: {e}")
        
        # Actualizar datos
        cursor.execute('''
            UPDATE reparaciones 
            SET cliente_nombre = %s, cliente_telefono = %s, equipo = %s, marca = %s, falla = %s, 
                tecnico = %s, estado = %s, actualizado_en = %s
            WHERE id = %s
        ''', (cliente_nombre, cliente_telefono, equipo, marca, falla, tecnico, nuevo_estado, 
              datetime.datetime.now().isoformat(), id))
        
        # Si cambió a LISTO
        if nuevo_estado == 'lista' and reparacion[11] != 'lista':
            mensaje = f"✅ TICKET LISTO {reparacion[1]}\nCliente: {reparacion[2]}\nEquipo: {reparacion[4]}\nHorario retiro: Lunes a Viernes 9am-4pm"
            enviar_whatsapp(mensaje)
            enviar_telegram(mensaje)
        
        # Si cambió a ENTREGADO
        if nuevo_estado == 'entregado' and reparacion[11] != 'entregado':
            fecha_salida = datetime.datetime.now().isoformat()
            cursor.execute("UPDATE reparaciones SET fecha_salida = %s WHERE id = %s", (fecha_salida, id))
            mensaje = f"🎉 TICKET ENTREGADO {reparacion[1]}\nCliente: {reparacion[2]}\nEquipo: {reparacion[4]}\nGarantía 2 meses"
            enviar_whatsapp(mensaje)
            enviar_telegram(mensaje)
            
            # Insertar en garantías
            cursor.execute('''
                INSERT INTO garantias (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla_original, tecnico, fecha_entrada_garantia, fecha_salida_garantia, estado_garantia, foto_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (reparacion[1], reparacion[2], reparacion[3], reparacion[4], reparacion[5], reparacion[6], reparacion[8], reparacion[9], fecha_salida, 'activa', reparacion[13]))
        
        conn.commit()
        conn.close()
        return redirect(url_for('listado'))
    
    cursor.execute("SELECT * FROM reparaciones WHERE id = %s", (id,))
    reparacion = cursor.fetchone()
    conn.close()
    return render_template_string(EDITAR_TICKET, reparacion=reparacion)

EDITAR_TICKET = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Editar Ticket</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; margin: 20px; }
        .container { max-width: 650px; margin: 0 auto; background: white; padding: 40px; border-radius: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); }
        h2 { color: #1a1a2e; margin-bottom: 30px; }
        input, textarea, select { width: 100%; padding: 14px; margin: 12px 0; border-radius: 12px; border: 1px solid #ddd; font-size: 16px; }
        button { background: linear-gradient(135deg, #007bff, #0056b3); color: white; padding: 14px; border: none; border-radius: 50px; cursor: pointer; width: 100%; font-size: 18px; font-weight: bold; }
        .btn-volver { display: inline-block; background: #6c757d; color: white; padding: 12px 24px; text-decoration: none; border-radius: 50px; margin-top: 20px; text-align: center; }
        .foto-actual { margin: 15px 0; }
        .foto-actual img { max-width: 200px; border-radius: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h2>✏️ Editar Ticket {{ reparacion[1] }}</h2>
        <form method="POST" enctype="multipart/form-data">
            <input type="text" name="cliente_nombre" value="{{ reparacion[2] }}" required>
            <input type="text" name="cliente_telefono" value="{{ reparacion[3] }}">
            <input type="text" name="equipo" value="{{ reparacion[4] }}" required>
            <input type="text" name="marca" value="{{ reparacion[5] or '' }}">
            <textarea name="falla" rows="3">{{ reparacion[6] or '' }}</textarea>
            <input type="text" name="tecnico" value="{{ reparacion[8] or '' }}">
            <select name="estado">
                <option value="en_reparacion" {% if reparacion[11] == 'en_reparacion' %}selected{% endif %}>En Reparación</option>
                <option value="lista" {% if reparacion[11] == 'lista' %}selected{% endif %}>Listo</option>
                <option value="entregado" {% if reparacion[11] == 'entregado' %}selected{% endif %}>Entregado</option>
                <option value="espera_repuesto" {% if reparacion[11] == 'espera_repuesto' %}selected{% endif %}>Espera Repuesto</option>
                <option value="no_procede" {% if reparacion[11] == 'no_procede' %}selected{% endif %}>No Procede</option>
            </select>
            <input type="file" name="foto" accept="image/*">
            {% if reparacion[13] %}
            <div class="foto-actual">
                <p>Foto actual:</p>
                <img src="{{ reparacion[13] }}">
            </div>
            {% endif %}
            <button type="submit">Guardar cambios</button>
        </form>
        <a href="/listado" class="btn-volver">← Volver al listado</a>
    </div>
</body>
</html>
'''

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
