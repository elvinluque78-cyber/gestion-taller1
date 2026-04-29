from flask import Flask, request, render_template_string, redirect, url_for
import psycopg2
import datetime
import requests
import os
import re
import json
import cloudinary
import cloudinary.uploader
from twilio.rest import Client
from functools import wraps

app = Flask(__name__)

# Configuración de autenticación
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

def requiere_autenticacion(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != ADMIN_PASSWORD:
            return 'Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
    return decorador

# PostgreSQL desde variable de entorno
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()
    print("✅ Base de datos PostgreSQL inicializada")

# Credenciales de Cloudinary
CLOUD_NAME = "drpmg1lso"
API_KEY = "519922232242146"
API_SECRET = "kxsPgE73Eu59VQ03qSCvWCeaHw4"

# HTML para el formulario
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
            <input type="text" name="cliente_telefono" placeholder="Teléfono (ej: 04123697532)" required>
            <input type="text" name="equipo" placeholder="Equipo (ej: Lavadora)" required>
            <input type="text" name="marca" placeholder="Marca">
            <textarea name="falla" placeholder="Falla o código de error" rows="3"></textarea>
            <input type="number" step="0.01" name="presupuesto" placeholder="Presupuesto (opcional)">
            <input type="text" name="tecnico" placeholder="Técnico">
            <input type="file" name="foto" accept="image/*">
            <button type="submit">Guardar reparación</button>
        </form>
        <a href="/listado" class="btn">📋 Ver listado</a>
        <a href="/consulta" class="btn">🔍 Consultar ticket</a>
    </div>
</body>
</html>
'''

# HTML para el listado (con técnico visible solo internamente)
LISTADO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Listado de Reparaciones</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background: #007bff; color: white; }
        .estado-en_reparacion { color: orange; font-weight: bold; }
        .estado-espera_repuesto { color: red; font-weight: bold; }
        .estado-lista { color: green; font-weight: bold; }
        .estado-entregado { color: blue; font-weight: bold; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        .btn:hover { background: #1e7e34; }
        .btn-small { padding: 4px 10px; font-size: 14px; background: #007bff; }
        .btn-small:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Listado de Reparaciones</h1>
        <a href="/" class="btn">➕ Nueva reparación</a>
        <a href="/dashboard" class="btn">📊 Dashboard</a>
        <a href="/consulta" class="btn">🔍 Consultar ticket</a>
        <form action="/buscar" method="GET" style="margin: 20px 0;">
            <input type="text" name="q" placeholder="🔍 Buscar por nombre de cliente..." value="{{ busqueda }}" style="padding: 8px; width: 300px;">
            <button type="submit" class="btn-small">Buscar</button>
            <a href="/listado" class="btn-small">Ver todos</a>
        </form>
        <div style="overflow-x: auto;">
        <table>
            <thead>
                <tr>
                    <th>Código</th>
                    <th>Cliente</th>
                    <th>Teléfono</th>
                    <th>Equipo</th>
                    <th>Marca</th>
                    <th>Falla</th>
                    <th>Estado</th>
                    <th>Entrada</th>
                    <th>Salida</th>
                    <th>Técnico</th>
                    <th>Foto</th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                {% for r in reparaciones %}
                <tr>
                    <td>{{ r[1] }}</td>
                    <td>{{ r[2] }}</td>
                    <td>{{ r[3] }}</td>
                    <td>{{ r[4] }} </td>
                    <td>{{ r[5] }}</td>
                    <td>{{ r[6][:50] }}{% if r[6]|length > 50 %}...{% endif %}</td>
                    <td class="estado-{{ r[11] }}">{{ r[11].replace('_', ' ') }}</td>
                    <td>{{ r[9][:10] if r[9] else '' }}</td>
                    <td>{% if r[10] %}{{ r[10][:10] }}{% else %}—{% endif %}</td>
                    <td>{{ r[8] if r[8] else '—' }}</td>
                    <td>
                        {% if r[13] %}
                            <a href="/foto/{{ r[0] }}" target="_blank" class="btn-small">📷 Ver foto</a>
                        {% else %}
                            <span style="color: gray;">Sin foto</span>
                        {% endif %}
                    </td>
                    <td><a href="/editar/{{ r[0] }}" class="btn-small">✏️ Editar</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        </div>
    </div>
</body>
</html>
'''

# HTML para el formulario de edición
EDITAR_FORMULARIO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Editar Reparación</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        input, textarea, select { display: block; margin: 10px 0; padding: 10px; width: 100%; max-width: 400px; border-radius: 5px; border: 1px solid #ccc; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }
        button:hover { background: #0056b3; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin-top: 20px; }
        .btn:hover { background: #1e7e34; }
        h1 { color: #333; }
    </style>
</head>
<body>
    <div class="container">
        <h1>✏️ Editar Reparación</h1>
        <form method="POST">
            <label>Código:</label>
            <input type="text" value="{{ r[1] }}" disabled style="background: #e9ecef; width: 100%; padding: 10px; margin-bottom: 10px;">
            <label>Cliente:</label>
            <input type="text" value="{{ r[2] }}" disabled style="background: #e9ecef; width: 100%; padding: 10px; margin-bottom: 10px;">
            <label>Teléfono:</label>
            <input type="text" value="{{ r[3] }}" disabled style="background: #e9ecef; width: 100%; padding: 10px; margin-bottom: 10px;">
            <label>Equipo:</label>
            <input type="text" name="equipo" value="{{ r[4] }}" required style="width: 100%; padding: 10px; margin-bottom: 10px;">
            <label>Marca:</label>
            <input type="text" name="marca" value="{{ r[5] }}" style="width: 100%; padding: 10px; margin-bottom: 10px;">
            <label>Falla:</label>
            <textarea name="falla" rows="3" required style="width: 100%; padding: 10px; margin-bottom: 10px;">{{ r[6] }}</textarea>
            <label>Presupuesto:</label>
            <input type="number" step="0.01" name="presupuesto" value="{{ r[7] }}" style="width: 100%; padding: 10px; margin-bottom: 10px;">
            <label>Técnico:</label>
            <input type="text" name="tecnico" value="{{ r[8] }}" style="width: 100%; padding: 10px; margin-bottom: 10px;">
            <label>Estado:</label>
            <select name="estado" style="width: 100%; padding: 10px; margin-bottom: 10px;">
                <option value="en_reparacion" {% if r[11] == 'en_reparacion' %}selected{% endif %}>En reparación</option>
                <option value="espera_repuesto" {% if r[11] == 'espera_repuesto' %}selected{% endif %}>Espera repuesto</option>
                <option value="lista" {% if r[11] == 'lista' %}selected{% endif %}>Listo</option>
                <option value="entregado" {% if r[11] == 'entregado' %}selected{% endif %}>Entregado</option>
            </select>
            <button type="submit">💾 Guardar cambios</button>
            <a href="/listado" class="btn">← Cancelar</a>
        </form>
    </div>
</body>
</html>
'''

# HTML para el dashboard
DASHBOARD = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Dashboard</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
        .btn { display: inline-block; background: #007bff; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        .btn:hover { background: #0056b3; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background: #007bff; color: white; }
        .total { font-size: 24px; font-weight: bold; color: green; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Dashboard de Ingresos</h1>
        <a href="/listado" class="btn">← Volver al listado</a>
        <div class="total">💰 Total general: ${{ total_general }}</div>
        <h2>Ingresos por técnico:</h2>
        <table>
            <thead>
                <tr><th>Técnico</th><th>Cantidad de tickets</th><th>Total facturado</th></tr>
            </thead>
            <tbody>
                {% for t in tecnicos %}
                <tr><td>{{ t[0] if t[0] else 'Sin asignar' }}</td><td>{{ t[1] }}</td><td>${{ t[2] }}</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
'''

def enviar_telegram(mensaje):
    token = "8742564082:AAGuvUN_q4NjBgUL70hcRsnCkwS-eumS6Sc"
    chat_id = "7150902056"
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})
    except:
        pass

def enviar_telegram_listo(codigo, cliente_nombre, equipo, marca):
    token = "8742564082:AAGuvUN_q4NjBgUL70hcRsnCkwS-eumS6Sc"
    chat_id = "7150902056"
    mensaje = f"✅ *EQUIPO LISTO*\n📌 Código: {codigo}\n👤 Cliente: {cliente_nombre}\n🔧 Equipo: {equipo} {marca}\n\n🏁 El equipo está listo para ser entregado al cliente."
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})
    except:
        pass

def generar_codigo():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT codigo FROM reparaciones ORDER BY id DESC LIMIT 1")
    ultimo = cursor.fetchone()
    conn.close()
    
    if ultimo and ultimo[0].startswith('E-'):
        try:
            num = int(ultimo[0].split('-')[1]) + 1
        except:
            num = 1
    else:
        num = 1
    
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

@app.route("/", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        codigo = generar_codigo()
        ahora = datetime.datetime.now().isoformat()
        
        # Subir foto
        foto_url = None
        if 'foto' in request.files:
            foto = request.files['foto']
            if foto and foto.filename != '':
                try:
                    cloudinary.config(
                        cloud_name=CLOUD_NAME,
                        api_key=API_KEY,
                        api_secret=API_SECRET
                    )
                    upload_result = cloudinary.uploader.upload(foto)
                    foto_url = upload_result.get('secure_url')
                    print(f"✅ Foto subida: {foto_url}")
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
        
        # Telegram
        mensaje_telegram = f"🆕 *Nueva reparación*\n📌 Código: {codigo}\n👤 Cliente: {request.form.get('cliente_nombre')}\n📞 Tel: {request.form.get('cliente_telefono')}\n🔧 Equipo: {request.form.get('equipo')} {request.form.get('marca')}\n⚠️ Falla: {request.form.get('falla')}\n💰 Presupuesto: {request.form.get('presupuesto')}\n👨‍🔧 Técnico: {request.form.get('tecnico')}"
        if foto_url:
            mensaje_telegram += f"\n📸 Foto: {foto_url}"
        enviar_telegram(mensaje_telegram)
        
        # WhatsApp
        try:
            twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
            twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
            twilio_whatsapp_from = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
            
            if twilio_account_sid and twilio_auth_token:
                twilio_client = Client(twilio_account_sid, twilio_auth_token)
                numero_cliente = limpiar_numero_telefono(request.form.get('cliente_telefono'))
                if numero_cliente:
                    cliente_whatsapp = f"whatsapp:+{numero_cliente}"
                    mensaje_whatsapp = f"""🧾 *Ticket de ingreso – Elvin Tech*
📌 N° de ticket: *{codigo}*
👤 Cliente: {request.form.get('cliente_nombre')}
🔧 Equipo: {request.form.get('equipo')} {request.form.get('marca')}
⚠️ Falla: {request.form.get('falla')}
💰 Presupuesto: {request.form.get('presupuesto')}
📅 Fecha ingreso: {ahora[:10]}

📞 Contacto taller: +58 412 3697532

Gracias por confiar en nosotros."""
                    
                    twilio_client.messages.create(
                        body=mensaje_whatsapp,
                        from_=twilio_whatsapp_from,
                        to=cliente_whatsapp
                    )
                    print(f"✅ WhatsApp enviado a {cliente_whatsapp}")
        except Exception as e:
            print(f"⚠️ Error en WhatsApp: {e}")
        
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

@app.route("/dashboard")
@requiere_autenticacion
def dashboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT tecnico, COUNT(*), SUM(presupuesto) FROM reparaciones WHERE estado = 'entregado' GROUP BY tecnico")
    tecnicos = cursor.fetchall()
    cursor.execute("SELECT SUM(presupuesto) FROM reparaciones WHERE estado = 'entregado'")
    total = cursor.fetchone()[0] or 0
    conn.close()
    return render_template_string(DASHBOARD, tecnicos=tecnicos, total_general=total)

@app.route("/foto/<int:id>")
def foto(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT foto_url FROM reparaciones WHERE id = %s", (id,))
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado and resultado[0]:
        foto_url = resultado[0]
        return f'<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Foto</title><style>body {{ display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f0f2f5; }} img {{ max-width: 100%; max-height: 100vh; }}</style></head><body><img src="{foto_url}" alt="Foto del equipo"></body></html>'
    else:
        return "Sin foto", 404

@app.route("/consulta", methods=["GET", "POST"])
def consulta():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        accion = request.form.get("accion", "")
        
        conn = get_db()
        cursor = conn.cursor()
        
        if accion == "cambiar_estado":
            cursor.execute("SELECT codigo, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo = %s", (codigo,))
            ticket = cursor.fetchone()
            
            if ticket:
                cursor.execute("UPDATE reparaciones SET estado = 'lista', actualizado_en = %s WHERE codigo = %s AND estado = 'en_reparacion'", 
                              (datetime.datetime.now().isoformat(), codigo))
                conn.commit()
                enviar_telegram_listo(ticket[0], ticket[1], ticket[2], ticket[3])
            
            conn.close()
            return '<h3>✅ Ticket marcado como LISTO</h3><a href="/consulta">Volver</a>'
        
        cursor.execute("SELECT id, codigo, estado, foto_url, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo = %s", (codigo,))
        resultado = cursor.fetchone()
        conn.close()
        
        if resultado and resultado[3]:
            foto_url = resultado[3]
            estado = resultado[2]
            mostrar_boton = (estado == 'en_reparacion')
            
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
                    .estado {{ font-size: 18px; margin: 10px 0; }}
                    .estado-en_reparacion {{ color: orange; font-weight: bold; }}
                    .estado-lista {{ color: green; font-weight: bold; }}
                    button {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; }}
                    button:hover {{ background: #0056b3; }}
                    .btn {{ display: inline-block; background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🔍 Ticket {codigo}</h1>
                    <div class="estado">
                        Estado actual: <span class="estado-{estado}">{estado.replace('_', ' ').upper()}</span>
                    </div>
                    <img src="{foto_url}" alt="Foto del equipo">
                    {'<form method="POST"><input type="hidden" name="codigo" value="' + codigo + '"><input type="hidden" name="accion" value="cambiar_estado"><button type="submit">✅ Marcar como LISTO</button></form>' if mostrar_boton else '<p>✔️ Este equipo ya está listo para retirar</p>'}
                    <br>
                    <a href="/consulta" class="btn">← Consultar otro ticket</a>
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
        <title>Consultar Ticket</title>
        <style>
            body { font-family: sans-serif; margin: 20px; background: #f0f2f5; }
            .container { max-width: 400px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; text-align: center; }
            input, button { padding: 10px; margin: 10px 0; width: 100%; border-radius: 5px; border: 1px solid #ccc; }
            button { background: #007bff; color: white; cursor: pointer; }
            h1 { color: #333; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Consultar Ticket</h1>
            <form method="POST">
                <input type="text" name="codigo" placeholder="Ej: E-001" required>
                <button type="submit">Ver estado y foto</button>
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
        # Obtener estado anterior
        cursor.execute("SELECT estado FROM reparaciones WHERE id = %s", (id,))
        estado_anterior = cursor.fetchone()[0]
        
        # Datos del formulario
        equipo = request.form.get("equipo")
        marca = request.form.get("marca")
        falla = request.form.get("falla")
        presupuesto = request.form.get("presupuesto")
        tecnico = request.form.get("tecnico")
        estado_nuevo = request.form.get("estado")
        actualizado = datetime.datetime.now().isoformat()
        
        # Si cambia a "entregado", registrar fecha_salida
        fecha_salida = None
        if estado_nuevo == 'entregado' and estado_anterior != 'entregado':
            fecha_salida = datetime.datetime.now().isoformat()
            print(f"✅ Ticket {id} marcado como ENTREGADO - Fecha salida: {fecha_salida}")
        
        # Actualizar según corresponda
        if fecha_salida:
            cursor.execute('''
                UPDATE reparaciones 
                SET equipo = %s, marca = %s, falla = %s, presupuesto = %s, 
                    tecnico = %s, estado = %s, actualizado_en = %s, fecha_salida = %s
                WHERE id = %s
            ''', (equipo, marca, falla, presupuesto, tecnico, estado_nuevo, actualizado, fecha_salida, id))
        else:
            cursor.execute('''
                UPDATE reparaciones 
                SET equipo = %s, marca = %s, falla = %s, presupuesto = %s, 
                    tecnico = %s, estado = %s, actualizado_en = %s
                WHERE id = %s
            ''', (equipo, marca, falla, presupuesto, tecnico, estado_nuevo, actualizado, id))
        
        conn.commit()
        conn.close()
        return redirect(url_for('listado'))
    
    # GET: mostrar formulario de edición
    cursor.execute("SELECT * FROM reparaciones WHERE id = %s", (id,))
    reparacion = cursor.fetchone()
    conn.close()
    
    if reparacion is None:
        return "Reparación no encontrada", 404
    
    return render_template_string(EDITAR_FORMULARIO, r=reparacion)

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
