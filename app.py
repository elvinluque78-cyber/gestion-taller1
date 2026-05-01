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

FORMULARIO = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Nueva Reparación</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
        h1 { color: #1a1a2e; text-align: center; margin-bottom: 30px; }
        input, textarea, select { display: block; margin: 15px 0; padding: 12px; width: 100%; border-radius: 8px; border: 1px solid #ddd; font-size: 14px; }
        button { background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); color: white; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; width: 100%; }
        button:hover { transform: scale(1.02); }
        .btn { display: inline-block; background: #28a745; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; margin: 10px 5px; text-align: center; }
        .btn:hover { background: #1e7e34; }
        .btn-group { text-align: center; margin-top: 20px; }
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
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Listado de Reparaciones</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); overflow-x: auto; }
        h1 { color: #1a1a2e; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { border: 1px solid #ddd; padding: 12px 8px; text-align: left; }
        th { background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); color: white; font-weight: bold; }
        tr:nth-child(even) { background: #f8f9fa; }
        tr:hover { background: #f1f1f1; }
        .estado-en_reparacion { color: #ff9800; font-weight: bold; }
        .estado-espera_repuesto { color: #f44336; font-weight: bold; }
        .estado-lista { color: #4caf50; font-weight: bold; }
        .estado-entregado { color: #2196f3; font-weight: bold; }
        .estado-en_garantia { color: #9c27b0; font-weight: bold; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 6px; margin: 5px; font-size: 14px; }
        .btn:hover { background: #1e7e34; }
        .btn-small { padding: 4px 10px; font-size: 12px; background: #007bff; color: white; text-decoration: none; border-radius: 4px; }
        .btn-small:hover { background: #0056b3; }
        .buscar-form { margin: 20px 0; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .buscar-form input { padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; width: 250px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Listado de Reparaciones</h1>
        <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px;">
            <a href="/" class="btn">➕ Nueva reparación</a>
            <a href="/garantias" class="btn">🛡️ Garantías</a>
            <a href="/consulta" class="btn">🔍 Consultar ticket</a>
        </div>
        <form action="/buscar" method="GET" class="buscar-form">
            <input type="text" name="q" placeholder="🔍 Buscar por nombre de cliente..." value="{{ busqueda }}">
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

GARANTIAS_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Garantías</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background: #f0f2f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 15px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); overflow-x: auto; }
        h1 { color: #9c27b0; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; font-size: 14px; }
        th, td { border: 1px solid #ddd; padding: 12px 8px; text-align: left; }
        th { background: linear-gradient(135deg, #9c27b0 0%, #7b1fa2 100%); color: white; }
        .btn { display: inline-block; background: #28a745; color: white; padding: 8px 16px; text-decoration: none; border-radius: 6px; margin: 5px; }
        .btn-small { padding: 4px 10px; font-size: 12px; background: #9c27b0; color: white; text-decoration: none; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🛡️ Gestión de Garantías</h1>
        <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px;">
            <a href="/" class="btn">➕ Nueva reparación</a>
            <a href="/listado" class="btn">📋 Listado</a>
            <a href="/consulta" class="btn">🔍 Consultar ticket</a>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Código</th>
                    <th>Cliente</th>
                    <th>Equipo</th>
                    <th>Estado</th>
                    <th>Entrada Garantía</th>
                    <th>Salida Garantía</th>
                    <th>Técnico</th>
                    <th>Foto</th>
                    <th>Acciones</th>
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
        enviar_telegram(f"🆕 *Nueva reparación*\n📌 Código: {codigo}\n👤 Cliente: {request.form['cliente_nombre']}")
        return redirect(url_for('nueva'))
    return render_template_string(FORMULARIO)

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

@app.route("/consulta", methods=["GET", "POST"])
def consulta():
    if request.method == "POST":
        codigo = request.form.get("codigo", "").strip().upper()
        accion = request.form.get("accion", "")
        conn = get_db()
        cur = conn.cursor()
        
        if accion == "cambiar_estado":
            cur.execute("SELECT codigo, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo = %s", (codigo,))
            ticket = cur.fetchone()
            if ticket:
                cur.execute("UPDATE reparaciones SET estado = 'lista', actualizado_en = %s WHERE codigo = %s",
                           (datetime.datetime.now().isoformat(), codigo))
                conn.commit()
                msg = f"✅ *EQUIPO LISTO*\n📌 Código: {ticket[0]}\n👤 Cliente: {ticket[1]}\n🔧 Equipo: {ticket[2]} {ticket[3]}"
                enviar_telegram(msg)
                enviar_whatsapp(msg)
            conn.close()
            return '<div style="text-align:center;margin-top:50px;"><h3>✅ Ticket marcado como LISTO</h3><a href="/consulta">Volver</a></div>'
        
        if accion == "marcar_garantia":
            cur.execute("SELECT codigo, cliente_nombre, cliente_telefono, equipo, marca, falla, foto_url FROM reparaciones WHERE codigo = %s", (codigo,))
            t = cur.fetchone()
            if t:
                cur.execute("UPDATE reparaciones SET estado = 'en_garantia', actualizado_en = %s WHERE codigo = %s",
                           (datetime.datetime.now().isoformat(), codigo))
                ahora = datetime.datetime.now().isoformat()
                cur.execute('''INSERT INTO garantias
                    (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla_original,
                     fecha_entrada_garantia, estado_garantia, foto_url, creado_en, actualizado_en)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                    (t[0], t[1], t[2], t[3], t[4], t[5], ahora, 'en_reparacion', t[6], ahora, ahora))
                conn.commit()
                msg = f"🛡️ *EQUIPO EN GARANTÍA*\n📌 Código: {t[0]}\n👤 Cliente: {t[1]}\n🔧 Equipo: {t[3]} {t[4]}"
                enviar_telegram(msg)
                enviar_whatsapp(msg)
            conn.close()
            return '<div style="text-align:center;margin-top:50px;"><h3>🛡️ Ticket marcado como GARANTÍA</h3><a href="/consulta">Volver</a></div>'
        
        # Mostrar ticket
        cur.execute("SELECT id, codigo, estado, foto_url, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo = %s", (codigo,))
        res = cur.fetchone()
        conn.close()
        if res:
            id_tkt, codigo, estado, foto_url, cliente, equipo, marca = res
            mostrar_listo = estado in ['en_reparacion', 'espera_repuesto', 'lista']
            mostrar_garantia = estado not in ['entregado', 'no_procede', 'en_garantia']
            return f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>Ticket {codigo}</title>
                <style>
                    body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }}
                    .container {{ max-width: 550px; width: 100%; background: white; border-radius: 20px; padding: 30px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); text-align: center; }}
                    h1 {{ color: #1a1a2e; margin-bottom: 20px; }}
                    .info {{ background: #f8f9fa; padding: 15px; border-radius: 10px; margin: 20px 0; text-align: left; }}
                    .info p {{ margin: 8px 0; font-size: 16px; }}
                    .estado {{ display: inline-block; padding: 8px 20px; border-radius: 20px; font-weight: bold; margin: 15px 0; }}
                    .estado-en_reparacion {{ background: #fff3e0; color: #ff9800; }}
                    .estado-espera_repuesto {{ background: #ffebee; color: #f44336; }}
                    .estado-lista {{ background: #e8f5e9; color: #4caf50; }}
                    .estado-entregado {{ background: #e3f2fd; color: #2196f3; }}
                    .estado-en_garantia {{ background: #f3e5f5; color: #9c27b0; }}
                    img {{ max-width: 100%; border-radius: 10px; margin: 20px 0; border: 2px solid #ddd; }}
                    button {{ background: linear-gradient(135deg, #007bff 0%, #0056b3 100%); color: white; padding: 12px 28px; border: none; border-radius: 30px; cursor: pointer; font-size: 16px; margin: 10px 8px; transition: 0.3s; }}
                    button:hover {{ transform: scale(1.05); }}
                    .btn-garantia {{ background: linear-gradient(135deg, #9c27b0 0%, #7b1fa2 100%); }}
                    .btn-volver {{ display: inline-block; background: #6c757d; color: white; padding: 10px 25px; text-decoration: none; border-radius: 30px; margin-top: 20px; }}
                    .btn-volver:hover {{ background: #5a6268; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🔍 Ticket {codigo}</h1>
                    <div class="estado estado-{estado}">
                        📌 Estado actual: <strong>{estado.replace('_', ' ').upper()}</strong>
                    </div>
                    <div class="info">
                        <p><strong>👤 Cliente:</strong> {cliente}</p>
                        <p><strong>🔧 Equipo:</strong> {equipo} {marca}</p>
                    </div>
                    <img src="{foto_url}" alt="Foto del equipo">
                    <div style="display: flex; gap: 15px; justify-content: center; flex-wrap: wrap;">
                        {'<form method="POST"><input type="hidden" name="codigo" value="' + codigo + '"><input type="hidden" name="accion" value="cambiar_estado"><button type="submit">✅ LISTO</button></form>' if mostrar_listo else ''}
                        {'<form method="POST"><input type="hidden" name="codigo" value="' + codigo + '"><input type="hidden" name="accion" value="marcar_garantia"><button type="submit" class="btn-garantia">🛡️ GARANTÍA</button></form>' if mostrar_garantia else ''}
                    </div>
                    <br>
                    <a href="/consulta" class="btn-volver">← Consultar otro ticket</a>
                </div>
            </body>
            </html>
            '''
        else:
            return '<div style="text-align:center;margin-top:50px;"><h3>❌ Código no encontrado</h3><a href="/consulta">Volver</a></div>', 404
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Consultar Ticket</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; }
            .container { max-width: 450px; width: 100%; background: white; padding: 40px; border-radius: 20px; box-shadow: 0 20px 40px rgba(0,0,0,0.2); text-align: center; }
            h1 { color: #1a1a2e; margin-bottom: 30px; }
            input { width: 90%; padding: 14px; margin: 15px 0; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 16px; transition: 0.3s; }
            input:focus { outline: none; border-color: #667eea; }
            button { width: 100%; padding: 14px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 10px; cursor: pointer; font-size: 16px; font-weight: bold; transition: 0.3s; }
            button:hover { transform: scale(1.02); }
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

@app.route("/editar_garantia/<int:id>", methods=["GET", "POST"])
@requiere_auth
def editar_garantia(id):
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        cur.execute("SELECT codigo, cliente_nombre, equipo, marca, cliente_telefono FROM garantias WHERE id = %s", (id,))
        g = cur.fetchone()
        estado_nuevo = request.form.get("estado")
        tecnico = request.form.get("tecnico")
        actualizado = datetime.datetime.now().isoformat()
        if estado_nuevo == 'lista':
            cur.execute("UPDATE reparaciones SET estado = 'lista', actualizado_en = %s WHERE codigo = %s", (actualizado, g[0]))
            cur.execute("UPDATE garantias SET estado_garantia = %s, tecnico = %s, actualizado_en = %s, fecha_salida_garantia = %s WHERE id = %s",
                       ('lista', tecnico, actualizado, actualizado, id))
            msg = f"🛡️ *GARANTÍA LISTA*\n📌 Código: {g[0]}\n👤 Cliente: {g[1]}\n🔧 Equipo: {g[2]} {g[3]}"
            enviar_telegram(msg)
            enviar_whatsapp(msg)
        else:
            cur.execute("UPDATE garantias SET estado_garantia = %s, tecnico = %s, actualizado_en = %s WHERE id = %s",
                       (estado_nuevo, tecnico, actualizado, id))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_garantias'))
    cur.execute("SELECT * FROM garantias WHERE id = %s", (id,))
    g = cur.fetchone()
    conn.close()
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Editar Garantía</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background: #f0f2f5; }}
            .container {{ max-width: 500px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; }}
            input, select {{ display: block; margin: 15px 0; padding: 12px; width: 100%; border-radius: 8px; border: 1px solid #ddd; }}
            button {{ background: #9c27b0; color: white; padding: 12px 20px; border: none; border-radius: 8px; cursor: pointer; width: 100%; }}
            .btn {{ display: inline-block; background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; margin-top: 15px; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✏️ Editar Garantía {g[1]}</h2>
            <form method="POST">
                <label>Técnico:</label>
                <input type="text" name="tecnico" value="{g[6] if g[6] else ''}">
                <label>Estado:</label>
                <select name="estado">
                    <option value="en_reparacion" {'selected' if g[8] == 'en_reparacion' else ''}>En reparación</option>
                    <option value="espera_repuesto" {'selected' if g[8] == 'espera_repuesto' else ''}>Espera repuesto</option>
                    <option value="lista" {'selected' if g[8] == 'lista' else ''}>Lista</option>
                </select>
                <button type="submit">💾 Guardar cambios</button>
                <a href="/garantias" class="btn">← Volver</a>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route("/foto/<int:id>")
def foto(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT foto_url FROM reparaciones WHERE id = %s", (id,))
    res = cur.fetchone()
    conn.close()
    if res and res[0]:
        return f'<html><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;"><img src="{res[0]}" style="max-width:90%;border-radius:10px;"></body></html>'
    return "Sin foto", 404

@app.route("/foto_garantia/<int:id>")
def foto_garantia(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT foto_url FROM garantias WHERE id = %s", (id,))
    res = cur.fetchone()
    conn.close()
    if res and res[0]:
        return f'<html><body style="display:flex;justify-content:center;align-items:center;min-height:100vh;"><img src="{res[0]}" style="max-width:90%;border-radius:10px;"></body></html>'
    return "Sin foto", 404

@app.route("/editar/<int:id>", methods=["GET", "POST"])
@requiere_auth
def editar(id):
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        cur.execute('''UPDATE reparaciones 
            SET equipo=%s, marca=%s, falla=%s, presupuesto=%s, tecnico=%s, estado=%s
            WHERE id=%s''',
            (request.form['equipo'], request.form['marca'], request.form['falla'],
             request.form['presupuesto'], request.form['tecnico'], request.form['estado'], id))
        conn.commit()
        conn.close()
        return redirect(url_for('listado'))
    cur.execute("SELECT * FROM reparaciones WHERE id = %s", (id,))
    r = cur.fetchone()
    conn.close()
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Editar Reparación</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background: #f0f2f5; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 15px; }}
            input, textarea, select {{ display: block; margin: 15px 0; padding: 12px; width: 100%; border-radius: 8px; border: 1px solid #ddd; }}
            button {{ background: #007bff; color: white; padding: 12px 20px; border: none; border-radius: 8px; cursor: pointer; width: 100%; }}
            .btn {{ display: inline-block; background: #6c757d; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; margin-top: 15px; text-align: center; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✏️ Editar {r[1]}</h2>
            <form method="POST">
                <label>Equipo:</label>
                <input name="equipo" value="{r[4]}">
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
                <a href="/listado" class="btn">← Volver</a>
            </form>
        </div>
    </body>
    </html>
    '''

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
