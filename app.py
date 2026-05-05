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
        creado_en TEXT,
        actualizado_en TEXT
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

CLOUD_NAME = "drpmg1lso"
API_KEY = "519922232242146"
API_SECRET = "kxsPgE73Eu59VQ03qSCvWCeaHw4"

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
        sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth = os.environ.get("TWILIO_AUTH_TOKEN")
        if sid and auth:
            Client(sid, auth).messages.create(
                body=mensaje,
                from_=os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
                to="whatsapp:+584123697532"
            )
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

# ---------- FORMULARIO NUEVA REPARACIÓN ----------
FORMULARIO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Nueva Reparación</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; min-height: 100vh; display: flex; justify-content: center; align-items: center; }
        .container { max-width: 650px; width: 100%; margin: auto; background: white; padding: 40px; border-radius: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); }
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

# ---------- LISTADO DE REPARACIONES ----------
LISTADO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=yes">
    <title>Listado de Reparaciones</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f0f2f5; margin: 0; padding: 20px; }
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 25px; border-radius: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); overflow-x: auto; }
        h1 { color: #1a1a2e; margin: 0 0 20px 0; font-size: 32px; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 10px 24px; text-decoration: none; border-radius: 50px; margin: 0; font-size: 14px; font-weight: bold; transition: 0.3s; }
        .btn:hover { transform: scale(1.02); }
        .btn-small { padding: 8px 16px; font-size: 12px; background: #007bff; color: white; text-decoration: none; border-radius: 25px; display: inline-block; transition: 0.3s; }
        .btn-small:hover { transform: scale(1.02); }
        .buscar-form { margin: 20px 0; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
        .buscar-form input { padding: 10px 18px; border: 1px solid #ddd; border-radius: 50px; width: 260px; font-size: 14px; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; min-width: 1000px; }
        th, td { border: 1px solid #e0e0e0; padding: 12px 10px; text-align: left; vertical-align: middle; }
        th { background: linear-gradient(135deg, #007bff, #0056b3); color: white; font-weight: bold; position: sticky; top: 0; }
        tr:nth-child(even) { background: #f8f9fa; }
        tr:hover { background: #f1f1f1; }
        .estado-en_reparacion { color: #ff9800; font-weight: bold; }
        .estado-espera_repuesto { color: #f44336; font-weight: bold; }
        .estado-lista { color: #4caf50; font-weight: bold; }
        .estado-entregado { color: #2196f3; font-weight: bold; }
        .estado-en_garantia { color: #9c27b0; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Listado de Reparaciones</h1>
        <div class="btn-group">
            <a href="/" class="btn">➕ Nueva reparación</a>
            <a href="/garantias" class="btn">🛡️ Garantías</a>
            <a href="/consulta" class="btn">🔍 Consultar ticket</a>
        </div>
        <form action="/buscar" method="GET" class="buscar-form">
            <input type="text" name="q" placeholder="🔍 Buscar por nombre de cliente..." value="{{ busqueda }}">
            <button type="submit" class="btn-small" style="background: #007bff; border: none; cursor: pointer;">Buscar</button>
            <a href="/listado" class="btn-small" style="background: #dc3545;">Ver todos</a>
        </form>
        <div style="overflow-x: auto;">
        <table>
            <thead>
                <tr>
                    <th>Código</th><th>Cliente</th><th>Teléfono</th><th>Equipo</th><th>Marca</th><th>Falla</th>
                    <th>Estado</th><th>Entrada</th><th>Salida</th><th>Técnico</th><th>Foto</th><th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                {% for r in reparaciones %}
                <tr>
                    <td>{{ r[1] }}</td>
                    <td>{{ r[2] }}</td>
                    <td>{{ r[3] }}</td>
                    <td>{{ r[4] }}</td>
                    <td>{{ r[5] if r[5] else '' }}</td>
                    <td>{{ r[6][:50] if r[6] else '' }}{% if r[6] and r[6]|length > 50 %}...{% endif %}</td>
                    <td class="estado-{{ r[11] }}">{{ r[11].replace('_', ' ') }}</td>
                    <td>{{ r[9][:10] if r[9] else '' }}</td>
                    <td>{% if r[10] %}{{ r[10][:10] }}{% else %}—{% endif %}</td>
                    <td>{{ r[8] if r[8] else '—' }}</td>
                    <td>{% if r[13] %}<a href="/foto/{{ r[0] }}" target="_blank" class="btn-small">📷 Ver</a>{% else %}—{% endif %}</td>
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

# ---------- LISTADO DE GARANTÍAS ----------
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
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 25px; border-radius: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); overflow-x: auto; }
        h1 { color: #9c27b0; margin: 0 0 20px 0; font-size: 32px; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 10px 24px; text-decoration: none; border-radius: 50px; margin: 0; font-size: 14px; font-weight: bold; }
        .btn-small { padding: 8px 16px; font-size: 12px; background: #9c27b0; color: white; text-decoration: none; border-radius: 25px; display: inline-block; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; min-width: 1200px; }
        th, td { border: 1px solid #e0e0e0; padding: 12px 10px; text-align: left; vertical-align: top; }
        th { background: linear-gradient(135deg, #9c27b0, #7b1fa2); color: white; font-weight: bold; position: sticky; top: 0; }
        tr:nth-child(even) { background: #f8f9fa; }
        tr:hover { background: #f1f1f1; }
        .estado-en_reparacion { color: #ff9800; font-weight: bold; }
        .estado-espera_repuesto { color: #f44336; font-weight: bold; }
        .estado-lista { color: #4caf50; font-weight: bold; }
        .foto-link { font-size: 11px; }
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
        <div style="overflow-x: auto;">
        <table>
            <thead>
                <tr>
                    <th>Código</th><th>Cliente</th><th>Teléfono</th><th>Equipo</th><th>Marca</th><th>Falla Original</th>
                    <th>Estado</th><th>Entrada Garantía</th><th>Salida Garantía</th><th>Técnico</th><th>Foto</th><th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                {% for g in garantias %}
                <tr>
                    <td>{{ g[1] }}</a></td>
                    <td>{{ g[2] }}</a></td>
                    <td>{{ g[3] if g[3] else '-' }}</a></td>
                    <td>{{ g[4] }}</a></td>
                    <td>{{ g[5] if g[5] else '-' }}</a></td>
                    <td>{{ g[6][:60] if g[6] else '-' }}{% if g[6] and g[6]|length > 60 %}...{% endif %}</a></td>
                    <td class="estado-{{ g[8] }}">{{ g[8].replace('_', ' ') if g[8] else '-' }}</a></td>
                    <td>{{ g[7][:10] if g[7] else '-' }}</a></td>
                    <td>{% if g[10] %}{{ g[10][:10] }}{% else %}-{% endif %}</a></td>
                    <td>{{ g[6] if g[6] else '-' }}</a></td>
                    <td>{% if g[9] %}<a href="/foto_garantia/{{ g[0] }}" target="_blank" class="foto-link">📷 Ver</a>{% else %}-{% endif %}</a></td>
                    <td><a href="/editar_garantia/{{ g[0] }}" class="btn-small">✏️ Editar</a></a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        </div>
        {% if not garantias %}
        <p style="text-align:center;color:#666;padding:40px;">No hay garantías registradas aún.</p>
        {% endif %}
    </div>
</body>
</html>
'''

# ---------- RUTA PRINCIPAL ----------
@app.route("/", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        codigo = generar_codigo()
        ahora = datetime.datetime.now().isoformat()
        foto_url = None
        if 'foto' in request.files:
            f = request.files['foto']
            if f and f.filename:
                cloudinary.config(cloud_name=CLOUD_NAME, api_key=API_KEY, api_secret=API_SECRET)
                foto_url = cloudinary.uploader.upload(f).get('secure_url')
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''INSERT INTO reparaciones 
            (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla, presupuesto, tecnico, fecha_entrada, estado, creado_en, actualizado_en, foto_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (codigo, request.form['cliente_nombre'], request.form['cliente_telefono'],
             request.form['equipo'], request.form.get('marca'), request.form.get('falla'),
             float(request.form['presupuesto']) if request.form['presupuesto'] else None,
             request.form.get('tecnico'), ahora, 'en_reparacion', ahora, ahora, foto_url))
        conn.commit()
        conn.close()
        
        # MENSAJES NUEVO TICKET
        cliente = request.form['cliente_nombre']
        telefono = request.form['cliente_telefono']
        equipo = request.form['equipo']
        marca = request.form.get('marca', '')
        falla = request.form.get('falla', '')
        presupuesto = request.form.get('presupuesto', 'Pendiente')
        tecnico = request.form.get('tecnico', 'Por asignar')
        
        msg_telegram = f"""🆕 *NUEVA REPARACIÓN - ELVIN TECHNOLOGY*

📌 *Código:* {codigo}
👤 *Cliente:* {cliente}
📞 *Teléfono:* {telefono}
🔧 *Equipo:* {equipo} {marca}
⚠️ *Falla:* {falla}
💰 *Presupuesto:* {presupuesto}
👨‍🔧 *Técnico:* {tecnico}
📅 *Fecha ingreso:* {ahora[:10]}"""
        if foto_url:
            msg_telegram += f"\n📸 *Foto:* {foto_url}"
        enviar_telegram(msg_telegram)
        
        msg_whatsapp = f"""🧾 *NUEVO TICKET - PARA REENVIAR AL CLIENTE*

🔧 *Elvin Technology*
📌 *Código:* {codigo}
👤 *Cliente:* {cliente}
📞 *Teléfono:* {telefono}
🔧 *Equipo:* {equipo} {marca}
⚠️ *Falla:* {falla}
💰 *Presupuesto:* {presupuesto}
📅 *Fecha ingreso:* {ahora[:10]}
📸 *Foto:* {foto_url if foto_url else 'Sin foto'}

📞 *Contacto taller:* +58 412 3697532

✅ *REENVÍA ESTE MENSAJE AL CLIENTE*"""
        enviar_whatsapp(msg_whatsapp)
        
        return redirect(url_for('nueva'))
    return render_template_string(FORMULARIO)

# ---------- LISTADO Y BÚSQUEDA ----------
@app.route("/listado")
@requiere_auth
def listado():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reparaciones ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()
    return render_template_string(LISTADO, reparaciones=data, busqueda='')

@app.route("/buscar")
@requiere_auth
def buscar():
    q = request.args.get('q', '')
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reparaciones WHERE cliente_nombre ILIKE %s ORDER BY id DESC", (f'%{q}%',))
    data = cur.fetchall()
    conn.close()
    return render_template_string(LISTADO, reparaciones=data, busqueda=q)

@app.route("/garantias")
@requiere_auth
def ver_garantias():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM garantias ORDER BY id DESC")
    data = cur.fetchall()
    conn.close()
    return render_template_string(GARANTIAS_HTML, garantias=data)

# ---------- CONSULTA PÚBLICA ----------
@app.route("/consulta", methods=["GET", "POST"])
def consulta():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        accion = request.form.get("accion", "")
        conn = get_db()
        cur = conn.cursor()
        
        # LISTO
        if accion == "cambiar_estado":
            cur.execute("SELECT codigo, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo=%s", (codigo,))
            t = cur.fetchone()
            if t:
                cur.execute("UPDATE reparaciones SET estado='lista', actualizado_en=%s WHERE codigo=%s",
                           (datetime.datetime.now().isoformat(), codigo))
                conn.commit()
                cod, cliente, equipo, marca = t
                msg_telegram = f"""✅ *EQUIPO LISTO - ELVIN TECHNOLOGY*

📌 *Código:* {cod}
👤 *Cliente:* {cliente}
🔧 *Equipo:* {equipo} {marca}
🏁 *Estado:* LISTO PARA RETIRAR

⏰ *Horario de retiro:* Lunes a Sábado 9am-4pm
📞 *Contacto:* +58 412 3697532"""
                enviar_telegram(msg_telegram)
                
                msg_whatsapp = f"""✅ *EQUIPO LISTO - PARA REENVIAR AL CLIENTE*

🔧 *Elvin Technology*
📌 *Código:* {cod}
👤 *Cliente:* {cliente}
🔧 *Equipo:* {equipo} {marca}

🏁 *El equipo ya está listo para retirar.*

⏰ *Horario de retiro:*
📍 Lunes a Sábado
🕘 9:00 am a 4:00 pm

📞 *Contacto:* +58 412 3697532

✅ *REENVÍA ESTE MENSAJE AL CLIENTE*"""
                enviar_whatsapp(msg_whatsapp)
            conn.close()
            return '<div style="text-align:center;margin-top:50px;"><h3>✅ Ticket marcado como LISTO</h3><a href="/consulta">Volver</a></div>'
        
        # GARANTÍA
        if accion == "marcar_garantia":
            cur.execute("SELECT codigo, cliente_nombre, cliente_telefono, equipo, marca, falla, foto_url FROM reparaciones WHERE codigo=%s", (codigo,))
            t = cur.fetchone()
            if t:
                cur.execute("UPDATE reparaciones SET estado='en_garantia', actualizado_en=%s WHERE codigo=%s",
                           (datetime.datetime.now().isoformat(), codigo))
                ahora = datetime.datetime.now().isoformat()
                cur.execute('''INSERT INTO garantias 
                    (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla_original, 
                     fecha_entrada_garantia, estado_garantia, foto_url, creado_en, actualizado_en)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                    (t[0], t[1], t[2], t[3], t[4], t[5], ahora, 'en_reparacion', t[6], ahora, ahora))
                conn.commit()
                msg_telegram = f"🛡️ *EQUIPO EN GARANTÍA*\n📌 Código: {t[0]}\n👤 Cliente: {t[1]}\n🔧 Equipo: {t[3]} {t[4]}"
                enviar_telegram(msg_telegram)
                enviar_whatsapp(msg_telegram)
            conn.close()
            return '<div style="text-align:center;margin-top:50px;"><h3>🛡️ Ticket marcado como GARANTÍA</h3><a href="/consulta">Volver</a></div>'
        
        # Mostrar ticket
        cur.execute("SELECT id, codigo, estado, foto_url, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo=%s", (codigo,))
        res = cur.fetchone()
        conn.close()
        if res and res[3]:
            _, cod, estado, foto, cliente, equipo, marca = res
            mostrar_listo = True
            mostrar_garantia = estado != 'en_garantia'
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Ticket {cod}</title>
                <style>
                    * {{ box-sizing: border-box; }}
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }}
                    .card {{ max-width: 700px; width: 100%; background: white; border-radius: 35px; padding: 45px; box-shadow: 0 25px 50px rgba(0,0,0,0.2); text-align: center; }}
                    h1 {{ color: #1a1a2e; margin-bottom: 25px; font-size: 36px; }}
                    .info {{ background: #f8f9fa; padding: 25px; border-radius: 20px; margin: 25px 0; text-align: left; font-size: 18px; }}
                    .info p {{ margin: 15px 0; }}
                    .estado {{ display: inline-block; padding: 12px 35px; border-radius: 50px; font-weight: bold; margin: 20px 0; font-size: 20px; }}
                    .estado-en_reparacion {{ background: #fff3e0; color: #ff9800; }}
                    .estado-espera_repuesto {{ background: #ffebee; color: #f44336; }}
                    .estado-lista {{ background: #e8f5e9; color: #4caf50; }}
                    .estado-entregado {{ background: #e3f2fd; color: #2196f3; }}
                    .estado-en_garantia {{ background: #f3e5f5; color: #9c27b0; }}
                    img {{ max-width: 100%; max-height: 350px; object-fit: contain; border-radius: 20px; margin: 20px 0; border: 2px solid #ddd; }}
                    button {{ padding: 16px 40px; margin: 15px 12px; border: none; border-radius: 50px; cursor: pointer; font-size: 18px; font-weight: bold; transition: 0.3s; }}
                    button:hover {{ transform: scale(1.05); }}
                    .btn-listo {{ background: linear-gradient(135deg, #4caf50, #388e3c); color: white; }}
                    .btn-garantia {{ background: linear-gradient(135deg, #9c27b0, #7b1fa2); color: white; }}
                    .btn-volver {{ display: inline-block; background: #6c757d; color: white; padding: 12px 30px; text-decoration: none; border-radius: 50px; margin-top: 20px; font-size: 16px; transition: 0.3s; }}
                    .btn-volver:hover {{ background: #5a6268; }}
                    @media (max-width: 600px) {{
                        .card {{ padding: 25px; }}
                        h1 {{ font-size: 28px; }}
                        .info {{ font-size: 14px; padding: 15px; }}
                        button {{ padding: 12px 25px; font-size: 14px; }}
                    }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>🔍 Ticket {cod}</h1>
                    <div class="estado estado-{estado}">
                        📌 Estado: <strong>{estado.replace('_', ' ').upper()}</strong>
                    </div>
                    <div class="info">
                        <p><strong>👤 Cliente:</strong> {cliente}</p>
                        <p><strong>🔧 Equipo:</strong> {equipo} {marca}</p>
                    </div>
                    <img src="{foto}" alt="Foto del equipo">
                    <div style="display: flex; gap: 20px; justify-content: center; flex-wrap: wrap;">
                        {'<form method="POST" style="display: inline;"><input type="hidden" name="codigo" value="' + cod + '"><input type="hidden" name="accion" value="cambiar_estado"><button class="btn-listo">✅ LISTO</button></form>' if mostrar_listo else ''}
                        {'<form method="POST" style="display: inline;"><input type="hidden" name="codigo" value="' + cod + '"><input type="hidden" name="accion" value="marcar_garantia"><button class="btn-garantia">🛡️ GARANTÍA</button></form>' if mostrar_garantia else ''}
                    </div>
                    <br>
                    <a href="/consulta" class="btn-volver">← Consultar otro ticket</a>
                </div>
            </body>
            </html>
            '''
        return '<div style="text-align:center;margin-top:50px;"><h3>❌ Código no encontrado</h3><a href="/consulta">Volver</a></div>', 404
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Consultar Ticket</title>
        <style>
            * { box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
            .container { max-width: 550px; width: 100%; background: white; padding: 50px; border-radius: 35px; box-shadow: 0 25px 50px rgba(0,0,0,0.2); text-align: center; }
            h1 { color: #1a1a2e; margin-bottom: 35px; font-size: 36px; }
            input { width: 100%; padding: 18px; margin: 25px 0; border: 2px solid #e0e0e0; border-radius: 60px; font-size: 18px; text-align: center; transition: 0.3s; background: white; }
            input:focus { outline: none; border-color: #667eea; transform: scale(1.01); }
            button { width: 100%; padding: 18px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 60px; cursor: pointer; font-size: 20px; font-weight: bold; transition: 0.3s; }
            button:hover { transform: scale(1.02); }
            @media (max-width: 600px) {
                .container { padding: 30px; }
                h1 { font-size: 28px; }
                input { padding: 14px; font-size: 16px; }
                button { padding: 14px; font-size: 18px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 Consultar Ticket</h1>
            <form method="POST">
                <input type="text" name="codigo" placeholder="Ej: E-001" required autofocus>
                <button type="submit">Ver estado y foto</button>
            </form>
        </div>
    </body>
    </html>
    '''

# ---------- EDICIÓN DE REPARACIONES (CON CLIENTE Y TELÉFONO EDITABLES) ----------
@app.route("/editar/<int:id>", methods=["GET", "POST"])
@requiere_auth
def editar(id):
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        # Obtener estado anterior
        cur.execute("SELECT estado FROM reparaciones WHERE id=%s", (id,))
        estado_anterior = cur.fetchone()[0]
        
        # Datos del formulario (AHORA INCLUYE CLIENTE Y TELÉFONO)
        cliente_nombre = request.form.get("cliente_nombre")
        cliente_telefono = request.form.get("cliente_telefono")
        equipo = request.form.get("equipo")
        marca = request.form.get("marca")
        falla = request.form.get("falla")
        presupuesto = request.form.get("presupuesto")
        tecnico = request.form.get("tecnico")
        estado_nuevo = request.form.get("estado")
        actualizado = datetime.datetime.now().isoformat()
        
        # Obtener código para notificaciones
        cur.execute("SELECT codigo FROM reparaciones WHERE id=%s", (id,))
        codigo = cur.fetchone()[0]
        
        # ENTREGADO (con garantía)
        if estado_nuevo == 'entregado' and estado_anterior != 'entregado':
            fecha_salida = actualizado
            fecha_entrega_obj = datetime.datetime.strptime(fecha_salida[:10], "%Y-%m-%d")
            fecha_fin = fecha_entrega_obj + datetime.timedelta(days=60)
            fecha_fin_str = fecha_fin.strftime("%d/%m/%Y")
            fecha_entrega_str = fecha_entrega_obj.strftime("%d/%m/%Y")
            
            msg_telegram = f"""✅ *EQUIPO ENTREGADO - GARANTÍA 2 MESES*

🔧 *Elvin Technology*
📌 *Código:* {codigo}
👤 *Cliente:* {cliente_nombre}
🔧 *Equipo:* {equipo} {marca}

📅 *Fecha de entrega:* {fecha_entrega_str}

🛡️ *GARANTÍA VÁLIDA HASTA:* {fecha_fin_str}
*Cobertura:* Mano de obra y repuestos (excepto mal uso)

📞 *Contacto:* +58 412 3697532"""
            enviar_telegram(msg_telegram)
            
            msg_whatsapp = f"""✅ *EQUIPO ENTREGADO - GARANTÍA 2 MESES*

🔧 *Elvin Technology*
📌 *Código:* {codigo}
👤 *Cliente:* {cliente_nombre}
🔧 *Equipo:* {equipo} {marca}

📅 *Fecha de entrega:* {fecha_entrega_str}

🛡️ *GARANTÍA VÁLIDA HASTA:* {fecha_fin_str}

Cubre: mano de obra y repuestos (excepto mal uso o daños externos)

📞 *Contacto:* +58 412 3697532"""
            enviar_whatsapp(msg_whatsapp)
            
            cur.execute("""UPDATE reparaciones 
                SET cliente_nombre=%s, cliente_telefono=%s, equipo=%s, marca=%s, falla=%s, 
                    presupuesto=%s, tecnico=%s, estado=%s, actualizado_en=%s, fecha_salida=%s
                WHERE id=%s""",
                (cliente_nombre, cliente_telefono, equipo, marca, falla,
                 presupuesto, tecnico, estado_nuevo, actualizado, fecha_salida, id))
        
        # LISTO
        elif estado_nuevo == 'lista' and estado_anterior != 'lista':
            msg_telegram = f"""✅ *EQUIPO LISTO - ELVIN TECHNOLOGY*

📌 *Código:* {codigo}
👤 *Cliente:* {cliente_nombre}
🔧 *Equipo:* {equipo} {marca}
🏁 *Estado:* LISTO PARA RETIRAR

⏰ *Horario de retiro:* Lunes a Sábado 9am-4pm
📞 *Contacto:* +58 412 3697532"""
            enviar_telegram(msg_telegram)
            
            msg_whatsapp = f"""✅ *EQUIPO LISTO - PARA REENVIAR AL CLIENTE*

🔧 *Elvin Technology*
📌 *Código:* {codigo}
👤 *Cliente:* {cliente_nombre}
🔧 *Equipo:* {equipo} {marca}

🏁 *El equipo ya está listo para retirar.*

⏰ *Horario de retiro:*
📍 Lunes a Sábado
🕘 9:00 am a 4:00 pm

📞 *Contacto:* +58 412 3697532

✅ *REENVÍA ESTE MENSAJE AL CLIENTE*"""
            enviar_whatsapp(msg_whatsapp)
            
            cur.execute("""UPDATE reparaciones 
                SET cliente_nombre=%s, cliente_telefono=%s, equipo=%s, marca=%s, falla=%s, 
                    presupuesto=%s, tecnico=%s, estado=%s, actualizado_en=%s
                WHERE id=%s""",
                (cliente_nombre, cliente_telefono, equipo, marca, falla,
                 presupuesto, tecnico, estado_nuevo, actualizado, id))
        
        # OTROS ESTADOS (sin notificaciones)
        else:
            cur.execute("""UPDATE reparaciones 
                SET cliente_nombre=%s, cliente_telefono=%s, equipo=%s, marca=%s, falla=%s, 
                    presupuesto=%s, tecnico=%s, estado=%s, actualizado_en=%s
                WHERE id=%s""",
                (cliente_nombre, cliente_telefono, equipo, marca, falla,
                 presupuesto, tecnico, estado_nuevo, actualizado, id))
        
        conn.commit()
        conn.close()
        return redirect(url_for('listado'))
    
    # GET: mostrar formulario de edición (con campos habilitados)
    cur.execute("SELECT * FROM reparaciones WHERE id=%s", (id,))
    r = cur.fetchone()
    conn.close()
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Editar Reparación</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; margin: 0; padding: 20px; min-height: 100vh; display: flex; justify-content: center; align-items: center; }}
            .container {{ max-width: 600px; width: 100%; margin: auto; background: white; padding: 35px; border-radius: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); }}
            h2 {{ color: #1a1a2e; margin-bottom: 25px; font-size: 28px; text-align: center; }}
            label {{ font-weight: bold; display: block; margin-top: 15px; margin-bottom: 5px; }}
            input, textarea, select {{ width: 100%; padding: 12px; margin: 5px 0 10px 0; border-radius: 12px; border: 1px solid #ddd; font-size: 15px; }}
            button {{ background: linear-gradient(135deg, #007bff, #0056b3); color: white; padding: 14px; border: none; border-radius: 50px; cursor: pointer; width: 100%; font-size: 16px; font-weight: bold; margin-top: 10px; }}
            .btn {{ display: inline-block; background: #6c757d; color: white; padding: 12px 24px; text-decoration: none; border-radius: 50px; text-align: center; margin-top: 15px; width: 100%; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✏️ Editar {r[1]}</h2>
            <form method="POST">
                <label>Código:</label>
                <input type="text" value="{r[1]}" disabled style="background:#e9ecef">
                <label>Cliente:</label>
                <input type="text" name="cliente_nombre" value="{r[2]}" required>
                <label>Teléfono:</label>
                <input type="text" name="cliente_telefono" value="{r[3]}" required>
                <label>Equipo:</label>
                <input name="equipo" value="{r[4]}" required>
                <label>Marca:</label>
                <input name="marca" value="{r[5] or ''}">
                <label>Falla:</label>
                <textarea name="falla" rows="3">{r[6] or ''}</textarea>
                <label>Presupuesto:</label>
                <input name="presupuesto" step="0.01" value="{r[7] or ''}">
                <label>Técnico:</label>
                <input name="tecnico" value="{r[8] or ''}">
                <label>Estado:</label>
                <select name="estado">
                    <option value="en_reparacion" {'selected' if r[11] == 'en_reparacion' else ''}>En reparación</option>
                    <option value="espera_repuesto" {'selected' if r[11] == 'espera_repuesto' else ''}>Espera repuesto</option>
                    <option value="lista" {'selected' if r[11] == 'lista' else ''}>Listo</option>
                    <option value="entregado" {'selected' if r[11] == 'entregado' else ''}>Entregado</option>
                    <option value="no_procede" {'selected' if r[11] == 'no_procede' else ''}>No Procede</option>
                </select>
                <button type="submit">💾 Guardar cambios</button>
                <a href="/listado" class="btn">← Volver al listado</a>
            </form>
        </div>
    </body>
    </html>
    '''

# ---------- EDICIÓN DE GARANTÍAS ----------
@app.route("/editar_garantia/<int:id>", methods=["GET", "POST"])
@requiere_auth
def editar_garantia(id):
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        cur.execute("SELECT codigo, cliente_nombre, equipo, marca FROM garantias WHERE id=%s", (id,))
        g = cur.fetchone()
        estado_nuevo = request.form.get("estado")
        tecnico = request.form.get("tecnico")
        ahora = datetime.datetime.now().isoformat()
        if estado_nuevo == 'lista':
            cur.execute("UPDATE reparaciones SET estado='lista', actualizado_en=%s WHERE codigo=%s", (ahora, g[0]))
            cur.execute("UPDATE garantias SET estado_garantia=%s, tecnico=%s, actualizado_en=%s, fecha_salida_garantia=%s WHERE id=%s",
                       ('lista', tecnico, ahora, ahora, id))
            msg_telegram = f"🛡️ *GARANTÍA LISTA - ELVIN TECHNOLOGY*\n📌 Código: {g[0]}\n👤 Cliente: {g[1]}\n🔧 Equipo: {g[2]} {g[3]}\n\n🏁 El equipo en garantía ya está listo para retirar."
            enviar_telegram(msg_telegram)
            enviar_whatsapp(msg_telegram)
        else:
            cur.execute("UPDATE garantias SET estado_garantia=%s, tecnico=%s, actualizado_en=%s WHERE id=%s",
                       (estado_nuevo, tecnico, ahora, id))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_garantias'))
    cur.execute("SELECT * FROM garantias WHERE id=%s", (id,))
    g = cur.fetchone()
    conn.close()
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Editar Garantía</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: 'Segoe UI', sans-serif; background: #f0f2f5; margin: 0; padding: 20px; min-height: 100vh; display: flex; justify-content: center; align-items: center; }}
            .container {{ max-width: 550px; width: 100%; margin: auto; background: white; padding: 35px; border-radius: 25px; box-shadow: 0 15px 35px rgba(0,0,0,0.1); }}
            h2 {{ color: #9c27b0; margin-bottom: 25px; font-size: 28px; text-align: center; }}
            label {{ font-weight: bold; display: block; margin-top: 15px; margin-bottom: 5px; }}
            input, select {{ width: 100%; padding: 12px; margin: 5px 0 10px 0; border-radius: 12px; border: 1px solid #ddd; font-size: 15px; }}
            button {{ background: linear-gradient(135deg, #9c27b0, #7b1fa2); color: white; padding: 14px; border: none; border-radius: 50px; cursor: pointer; width: 100%; font-size: 16px; font-weight: bold; margin-top: 10px; }}
            .btn {{ display: inline-block; background: #6c757d; color: white; padding: 12px 24px; text-decoration: none; border-radius: 50px; text-align: center; margin-top: 15px; width: 100%; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✏️ Editar Garantía {g[1]}</h2>
            <form method="POST">
                <label>Técnico:</label>
                <input name="tecnico" value="{g[6] if g[6] else ''}">
                <label>Estado:</label>
                <select name="estado">
                    <option value="en_reparacion" {'selected' if g[8] == 'en_reparacion' else ''}>En reparación</option>
                    <option value="espera_repuesto" {'selected' if g[8] == 'espera_repuesto' else ''}>Espera repuesto</option>
                    <option value="lista" {'selected' if g[8] == 'lista' else ''}>Lista</option>
                </select>
                <button type="submit">💾 Guardar cambios</button>
                <a href="/garantias" class="btn">← Volver a garantías</a>
            </form>
        </div>
    </body>
    </html>
    '''

# ---------- FOTOS ----------
@app.route("/foto/<int:id>")
def foto(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT foto_url FROM reparaciones WHERE id=%s", (id,))
    r = cur.fetchone()
    conn.close()
    if r and r[0]:
        return f'<html><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;"><img src="{r[0]}" style="max-width:90%;max-height:90vh;border-radius:20px;"></body></html>'
    return "Sin foto", 404

@app.route("/foto_garantia/<int:id>")
def foto_garantia(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT foto_url FROM garantias WHERE id=%s", (id,))
    r = cur.fetchone()
    conn.close()
    if r and r[0]:
        return f'<html><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0;"><img src="{r[0]}" style="max-width:90%;max-height:90vh;border-radius:20px;"></body></html>'
    return "Sin foto", 404

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
