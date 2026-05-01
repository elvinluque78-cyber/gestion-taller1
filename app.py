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
        marca TEXT, falla TEXT, presupuesto REAL, tecnico TEXT,
        fecha_entrada TEXT NOT NULL, fecha_salida TEXT,
        estado TEXT NOT NULL,
        foto_url TEXT,
        creado_en TEXT, actualizado_en TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS garantias (
        id SERIAL PRIMARY KEY,
        codigo TEXT NOT NULL,
        cliente_nombre TEXT NOT NULL,
        cliente_telefono TEXT NOT NULL,
        equipo TEXT NOT NULL, marca TEXT, falla_original TEXT,
        tecnico TEXT,
        fecha_entrada_garantia TEXT NOT NULL,
        fecha_salida_garantia TEXT,
        estado_garantia TEXT NOT NULL,
        foto_url TEXT,
        creado_en TEXT, actualizado_en TEXT
    )''')
    conn.commit()
    conn.close()

CLOUD_NAME, API_KEY, API_SECRET = "drpmg1lso", "519922232242146", "kxsPgE73Eu59VQ03qSCvWCeaHw4"

def enviar_telegram(mensaje):
    t, c = "8742564082:AAGuvUN_q4NjBgUL70hcRsnCkwS-eumS6Sc", "7150902056"
    try:
        requests.post(f"https://api.telegram.org/bot{t}/sendMessage", json={"chat_id": c, "text": mensaje, "parse_mode": "Markdown"})
    except: pass

def enviar_whatsapp(mensaje):
    try:
        sid, auth = os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN")
        if sid and auth:
            Client(sid, auth).messages.create(body=mensaje, from_=os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"), to="whatsapp:+584123697532")
    except: pass

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
<html><head><meta charset="UTF-8"><title>Nueva Reparación</title><style>
body{font-family:Segoe UI;background:#f0f2f5;margin:20px}.container{max-width:600px;margin:auto;background:#fff;padding:30px;border-radius:15px}
input,textarea,select{width:100%;padding:10px;margin:10px 0;border-radius:8px;border:1px solid #ddd}
button{background:#007bff;color:#fff;padding:12px;border:none;border-radius:8px;width:100%}
.btn{background:#28a745;color:#fff;padding:10px 20px;text-decoration:none;border-radius:8px;display:inline-block;margin:5px}
</style></head>
<body><div class=container>
<h1>🔧 Nueva Reparación</h1>
<form method=POST enctype=multipart/form-data>
<input name=cliente_nombre placeholder=Cliente required>
<input name=cliente_telefono placeholder=Teléfono required>
<input name=equipo placeholder=Equipo required>
<input name=marca placeholder=Marca>
<textarea name=falla placeholder=Falla rows=3></textarea>
<input name=presupuesto step=0.01 placeholder=Presupuesto>
<input name=tecnico placeholder=Técnico>
<input type=file name=foto>
<button type=submit>Guardar</button>
</form>
<div style=text-align:center;margin-top:20px>
<a href=/listado class=btn>📋 Listado</a>
<a href=/garantias class=btn>🛡️ Garantías</a>
<a href=/consulta class=btn>🔍 Consultar</a>
</div></div></body></html>
'''

LISTADO = '''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Listado</title><style>
body{font-family:Segoe UI;background:#f0f2f5;margin:20px}.container{background:#fff;padding:20px;border-radius:15px;overflow-x:auto}
table{width:100%;border-collapse:collapse}th,td{border:1px solid #ddd;padding:8px;text-align:left}th{background:#007bff;color:#fff}
.btn{background:#28a745;color:#fff;padding:6px 12px;text-decoration:none;border-radius:5px;display:inline-block;margin:5px}
.btn-small{background:#007bff;color:#fff;padding:4px 8px;text-decoration:none;border-radius:4px}
</style></head>
<body><div class=container>
<h1>📋 Reparaciones</h1>
<a href=/ class=btn>➕ Nueva</a>
<a href=/garantias class=btn>🛡️ Garantías</a>
<a href=/consulta class=btn>🔍 Consultar</a>
<form action=/buscar method=GET style=margin:15px 0>
<input name=q placeholder=Buscar... value="{{ busqueda }}">
<button class=btn-small>Buscar</button>
<a href=/listado class=btn-small>Ver todos</a>
</form>
<table><thead><tr><th>Código</th><th>Cliente</th><th>Equipo</th><th>Estado</th><th>Entrada</th><th>Foto</th><th>Acciones</th></tr></thead>
<tbody>{% for r in reparaciones %}
<tr><td>{{ r[1] }}</td><td>{{ r[2] }}</td><td>{{ r[4] }} {{ r[5] }}</td><td>{{ r[11].replace('_',' ') }}</td><td>{{ r[9][:10] if r[9] else '' }}</td>
<td>{% if r[13] %}<a href="/foto/{{ r[0] }}" target=_blank class=btn-small>📷</a>{% else %}—{% endif %}</td>
<td><a href="/editar/{{ r[0] }}" class=btn-small>✏️</a></td></tr>
{% endfor %}</tbody></table>
</div></body></html>
'''

GARANTIAS_HTML = '''
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Garantías</title><style>
body{font-family:Segoe UI;background:#f0f2f5;margin:20px}.container{background:#fff;padding:20px;border-radius:15px;overflow-x:auto}
th{background:#9c27b0;color:#fff}td,th{border:1px solid #ddd;padding:8px}
.btn{background:#28a745;color:#fff;padding:6px 12px;text-decoration:none;border-radius:5px}
.btn-small{background:#9c27b0;color:#fff;padding:4px 8px;text-decoration:none;border-radius:4px}
</style></head>
<body><div class=container>
<h1>🛡️ Garantías</h1>
<a href=/ class=btn>➕ Nueva</a>
<a href=/listado class=btn>📋 Listado</a>
<a href=/consulta class=btn>🔍 Consultar</a>
<table><thead><tr><th>Código</th><th>Cliente</th><th>Equipo</th><th>Estado</th><th>Entrada</th><th>Foto</th><th>Acciones</th></tr></thead>
<tbody>{% for g in garantias %}
<tr><td>{{ g[1] }}</td><td>{{ g[2] }}</td><td>{{ g[4] }} {{ g[5] }}</td><td>{{ g[8].replace('_',' ') }}</td><td>{{ g[7][:10] if g[7] else '' }}</td>
<td>{% if g[9] %}<a href="/foto_garantia/{{ g[0] }}" target=_blank class=btn-small>📷</a>{% else %}—{% endif %}</td>
<td><a href="/editar_garantia/{{ g[0] }}" class=btn-small>✏️</a></td></tr>
{% endfor %}</tbody></table>
</div></body></html>
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
        cur.execute('''INSERT INTO reparaciones (codigo,cliente_nombre,cliente_telefono,equipo,marca,falla,presupuesto,tecnico,fecha_entrada,estado,creado_en,actualizado_en,foto_url)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (codigo, request.form['cliente_nombre'], request.form['cliente_telefono'], request.form['equipo'], request.form.get('marca'), request.form.get('falla'),
             float(request.form['presupuesto']) if request.form['presupuesto'] else None, request.form.get('tecnico'), ahora, 'en_reparacion', ahora, ahora, foto_url))
        conn.commit()
        conn.close()
        enviar_telegram(f"🆕 Nueva reparación\n📌 {codigo}\n👤 {request.form['cliente_nombre']}")
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
            cur.execute("SELECT codigo, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo=%s", (codigo,))
            t = cur.fetchone()
            if t:
                cur.execute("UPDATE reparaciones SET estado='lista', actualizado_en=%s WHERE codigo=%s", (datetime.datetime.now().isoformat(), codigo))
                conn.commit()
                enviar_telegram(f"✅ EQUIPO LISTO\n📌 {t[0]}\n👤 {t[1]}\n🔧 {t[2]} {t[3]}")
                enviar_whatsapp(f"✅ EQUIPO LISTO\n📌 {t[0]}\n👤 {t[1]}\n🔧 {t[2]} {t[3]}")
            conn.close()
            return '<h3>✅ Marcado como LISTO</h3><a href="/consulta">Volver</a>'
        
        if accion == "marcar_garantia":
            cur.execute("SELECT codigo,cliente_nombre,cliente_telefono,equipo,marca,falla,foto_url FROM reparaciones WHERE codigo=%s", (codigo,))
            t = cur.fetchone()
            if t:
                cur.execute("UPDATE reparaciones SET estado='en_garantia', actualizado_en=%s WHERE codigo=%s", (datetime.datetime.now().isoformat(), codigo))
                ahora = datetime.datetime.now().isoformat()
                cur.execute('''INSERT INTO garantias (codigo,cliente_nombre,cliente_telefono,equipo,marca,falla_original,fecha_entrada_garantia,estado_garantia,foto_url,creado_en,actualizado_en)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (t[0], t[1], t[2], t[3], t[4], t[5], ahora, 'en_reparacion', t[6], ahora, ahora))
                conn.commit()
                enviar_telegram(f"🛡️ EQUIPO EN GARANTÍA\n📌 {t[0]}\n👤 {t[1]}\n🔧 {t[3]} {t[4]}")
                enviar_whatsapp(f"🛡️ EQUIPO EN GARANTÍA\n📌 {t[0]}\n👤 {t[1]}\n🔧 {t[3]} {t[4]}")
            conn.close()
            return '<h3>🛡️ Marcado como GARANTÍA</h3><a href="/consulta">Volver</a>'
        
        cur.execute("SELECT id, codigo, estado, foto_url, cliente_nombre, equipo, marca FROM reparaciones WHERE codigo=%s", (codigo,))
        res = cur.fetchone()
        conn.close()
        if res and res[3]:
            _, cod, estado, foto, cliente, equipo, marca = res
            mostrar_listo = estado not in ['entregado', 'no_procede', 'en_garantia']
            mostrar_garantia = estado not in ['entregado', 'no_procede', 'en_garantia']
            return f'''
            <!DOCTYPE html>
            <html><head><meta charset="UTF-8"><title>Ticket {cod}</title>
            <style>
                body{{font-family:Segoe UI;margin:0;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center}}
                .card{{max-width:550px;background:#fff;border-radius:25px;padding:30px;text-align:center}}
                img{{max-width:100%;border-radius:15px;margin:20px 0}}
                button{{padding:12px 24px;margin:10px;border:none;border-radius:40px;font-weight:bold;cursor:pointer}}
                .btn-listo{{background:#4caf50;color:#fff}}
                .btn-garantia{{background:#9c27b0;color:#fff}}
            </style></head>
            <body>
            <div class=card>
                <h2>🔍 Ticket {cod}</h2>
                <p><strong>👤 Cliente:</strong> {cliente}<br><strong>🔧 Equipo:</strong> {equipo} {marca}<br><strong>📌 Estado:</strong> {estado.replace('_',' ').upper()}</p>
                <img src="{foto}">
                <div>
                    {'<form method="POST"><input type="hidden" name="codigo" value="' + cod + '"><input type="hidden" name="accion" value="cambiar_estado"><button class="btn-listo">✅ LISTO</button></form>' if mostrar_listo else ''}
                    {'<form method="POST"><input type="hidden" name="codigo" value="' + cod + '"><input type="hidden" name="accion" value="marcar_garantia"><button class="btn-garantia">🛡️ GARANTÍA</button></form>' if mostrar_garantia else ''}
                </div>
                <br><a href="/consulta">← Consultar otro</a>
            </div>
            </body></html>
            '''
        return '<h3>Código no encontrado</h3><a href="/consulta">Volver</a>',404
    
    return '''
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><title>Consultar</title>
    <style>body{background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center}.card{background:#fff;padding:40px;border-radius:25px;text-align:center}input{padding:12px;width:80%;margin:15px 0;border-radius:30px;border:1px solid #ccc}</style>
    </head><body><div class=card><h2>🔍 Consultar Ticket</h2>
    <form method=POST><input name=codigo placeholder="Ej: E-001" required><button style="background:#007bff;color:#fff;padding:12px 25px;border:none;border-radius:30px">Ver</button></form>
    </div></body></html>
    '''

@app.route("/editar_garantia/<int:id>", methods=["GET", "POST"])
@requiere_auth
def editar_garantia(id):
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        cur.execute("SELECT codigo,cliente_nombre,equipo,marca FROM garantias WHERE id=%s", (id,))
        g = cur.fetchone()
        estado_nuevo = request.form.get("estado")
        tecnico = request.form.get("tecnico")
        ahora = datetime.datetime.now().isoformat()
        if estado_nuevo == 'lista':
            cur.execute("UPDATE reparaciones SET estado='lista', actualizado_en=%s WHERE codigo=%s", (ahora, g[0]))
            cur.execute("UPDATE garantias SET estado_garantia=%s, tecnico=%s, actualizado_en=%s, fecha_salida_garantia=%s WHERE id=%s", ('lista', tecnico, ahora, ahora, id))
            enviar_telegram(f"🛡️ GARANTÍA LISTA\n📌 {g[0]}\n👤 {g[1]}\n🔧 {g[2]} {g[3]}")
            enviar_whatsapp(f"🛡️ GARANTÍA LISTA\n📌 {g[0]}\n👤 {g[1]}\n🔧 {g[2]} {g[3]}")
        else:
            cur.execute("UPDATE garantias SET estado_garantia=%s, tecnico=%s, actualizado_en=%s WHERE id=%s", (estado_nuevo, tecnico, ahora, id))
        conn.commit()
        conn.close()
        return redirect(url_for('ver_garantias'))
    cur.execute("SELECT * FROM garantias WHERE id=%s", (id,))
    g = cur.fetchone()
    conn.close()
    return f'''
    <!DOCTYPE html><html><body><h2>Editar Garantía {g[1]}</h2>
    <form method=POST>
    Técnico: <input name=tecnico value="{g[6] or ''}"><br>
    Estado: <select name=estado>
        <option value="en_reparacion" {'selected' if g[8]=='en_reparacion' else ''}>En reparación</option>
        <option value="espera_repuesto" {'selected' if g[8]=='espera_repuesto' else ''}>Espera repuesto</option>
        <option value="lista" {'selected' if g[8]=='lista' else ''}>Lista</option>
    </select><br>
    <button>Guardar</button></form></body></html>
    '''

@app.route("/foto/<int:id>")
def foto(id):
    conn=get_db()
    cur=conn.cursor()
    cur.execute("SELECT foto_url FROM reparaciones WHERE id=%s",(id,))
    u=cur.fetchone()
    conn.close()
    return f'<img src="{u[0]}" style="max-width:100%">' if u and u[0] else "Sin foto"

@app.route("/foto_garantia/<int:id>")
def foto_garantia(id):
    conn=get_db()
    cur=conn.cursor()
    cur.execute("SELECT foto_url FROM garantias WHERE id=%s",(id,))
    u=cur.fetchone()
    conn.close()
    return f'<img src="{u[0]}" style="max-width:100%">' if u and u[0] else "Sin foto"

@app.route("/editar/<int:id>", methods=["GET","POST"])
@requiere_auth
def editar(id):
    conn=get_db()
    cur=conn.cursor()
    if request.method=="POST":
        cur.execute("UPDATE reparaciones SET equipo=%s,marca=%s,falla=%s,presupuesto=%s,tecnico=%s,estado=%s WHERE id=%s",
                   (request.form['equipo'],request.form['marca'],request.form['falla'],request.form['presupuesto'],request.form['tecnico'],request.form['estado'],id))
        conn.commit()
        conn.close()
        return redirect(url_for('listado'))
    cur.execute("SELECT * FROM reparaciones WHERE id=%s",(id,))
    r=cur.fetchone()
    conn.close()
    return f'''
    <form method=POST>
    Equipo: <input name=equipo value="{r[4]}"><br>
    Marca: <input name=marca value="{r[5] or ''}"><br>
    Falla: <textarea name=falla>{r[6] or ''}</textarea><br>
    Presupuesto: <input name=presupuesto value="{r[7] or ''}"><br>
    Técnico: <input name=tecnico value="{r[8] or ''}"><br>
    Estado: <select name=estado>
        <option value="en_reparacion" {'selected' if r[11]=='en_reparacion' else ''}>En reparación</option>
        <option value="espera_repuesto" {'selected' if r[11]=='espera_repuesto' else ''}>Espera repuesto</option>
        <option value="lista" {'selected' if r[11]=='lista' else ''}>Listo</option>
        <option value="entregado" {'selected' if r[11]=='entregado' else ''}>Entregado</option>
        <option value="no_procede" {'selected' if r[11]=='no_procede' else ''}>No Procede</option>
    </select><br>
    <button>Guardar</button></form><a href="/listado">Volver</a>
    '''

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
