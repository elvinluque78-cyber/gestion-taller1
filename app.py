from flask import Flask, request, render_template_string, redirect, url_for
import psycopg2
import datetime
import requests
import os
import cloudinary
import cloudinary.uploader
from functools import wraps

app = Flask(__name__)
ADMIN_PASSWORD = "admin123"

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

def generar_codigo():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT codigo FROM reparaciones ORDER BY id DESC LIMIT 1")
    ult = cur.fetchone()
    conn.close()
    num = 1 if not ult else int(ult[0].split('-')[1]) + 1
    return f"E-{num:03d}"

# ==================== WHATSAPP ====================
TWILIO_SID = "AC1eee15ecfd80fc2a2eadaaf00326ea0b"
TWILIO_AUTH = "e0149c3decfd1a4afa945fdf1ee6f1bd"
TWILIO_FROM = "whatsapp:+14155238886"
TECNICO_TO = "whatsapp:+584123697532"

def enviar_whatsapp(mensaje):
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json"
        data = {"From": TWILIO_FROM, "To": TECNICO_TO, "Body": mensaje}
        requests.post(url, data=data, auth=(TWILIO_SID, TWILIO_AUTH), timeout=10)
    except:
        pass

# ==================== HTML ====================
LISTADO_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Listado de Reparaciones</title>
    <style>
        body { font-family: Arial; margin: 20px; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #007bff; color: white; }
        .btn { background: #28a745; color: white; padding: 5px 10px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 2px; }
        .btn-small { background: #007bff; color: white; padding: 3px 8px; text-decoration: none; border-radius: 3px; font-size: 12px; }
    </style>
</head>
<body>
    <h2>📋 Reparaciones</h2>
    <a href="/" class="btn">➕ Nueva</a>
    <hr>
    <div style="overflow-x: auto;">
    <table>
        <thead>
            <tr><th>Código</th><th>Cliente</th><th>Equipo</th><th>Estado</th><th>Entrada</th><th>Acciones</th></tr>
        </thead>
        <tbody>
            {% for r in reparaciones %}
            <tr>
                <td>{{ r[1] }}</td>
                <td>{{ r[2] }}</td>
                <td>{{ r[4] }}</td>
                <td>{{ r[11] }}</td>
                <td>{{ r[9][:10] if r[9] else '-' }}</td>
                <td><a href="/editar/{{ r[0] }}" class="btn-small">✏️ Editar</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    </div>
</body>
</html>
'''

FORMULARIO_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Nuevo Ticket</title>
    <style>
        body { font-family: Arial; margin: 20px; }
        .container { max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; }
        input, textarea { width: 100%; padding: 8px; margin: 5px 0; }
        button { background: #007bff; color: white; padding: 10px; border: none; border-radius: 5px; cursor: pointer; width: 100%; }
    </style>
</head>
<body>
<div class="container">
    <h2>🔧 Nuevo Ticket</h2>
    <form method="POST" enctype="multipart/form-data">
        <input type="text" name="cliente_nombre" placeholder="Cliente" required>
        <input type="text" name="cliente_telefono" placeholder="Teléfono">
        <input type="text" name="equipo" placeholder="Equipo" required>
        <input type="text" name="marca" placeholder="Marca">
        <textarea name="falla" placeholder="Falla" rows="3"></textarea>
        <input type="text" name="tecnico" placeholder="Técnico">
        <input type="file" name="foto">
        <button type="submit">Guardar</button>
    </form>
    <a href="/listado">← Volver</a>
</div>
</body>
</html>
'''

EDITAR_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Editar Ticket</title>
    <style>
        body { font-family: Arial; margin: 20px; }
        .container { max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 10px; }
        input, textarea, select { width: 100%; padding: 8px; margin: 5px 0; }
        button { background: #007bff; color: white; padding: 10px; border: none; border-radius: 5px; cursor: pointer; width: 100%; }
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
        </select>
        <input type="file" name="foto">
        <button type="submit">Guardar cambios</button>
    </form>
    <a href="/listado">← Volver</a>
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
                cloudinary.config(cloud_name="drpmg1lso", api_key="519922232242146", api_secret="kxsPgE73Eu59VQ03qSCvWCeaHw4")
                upload_result = cloudinary.uploader.upload(request.files['foto'])
                foto_url = upload_result.get('secure_url')
            except:
                pass
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute('''INSERT INTO reparaciones (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla, tecnico, fecha_entrada, estado, creado_en, actualizado_en, foto_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
            (codigo, request.form.get('cliente_nombre'), request.form.get('cliente_telefono'),
             request.form.get('equipo'), request.form.get('marca'), request.form.get('falla'),
             request.form.get('tecnico'), ahora, 'en_reparacion', ahora, ahora, foto_url))
        conn.commit()
        conn.close()
        
        enviar_whatsapp(f"🧾 NUEVO TICKET {codigo}\nCliente: {request.form.get('cliente_nombre')}\nEquipo: {request.form.get('equipo')}")
        return redirect(url_for('nueva'))
    return render_template_string(FORMULARIO_HTML)

@app.route("/listado")
@requiere_auth
def listado():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reparaciones ORDER BY id DESC")
    reparaciones = cur.fetchall()
    conn.close()
    return render_template_string(LISTADO_HTML, reparaciones=reparaciones)

@app.route("/editar/<int:id>", methods=["GET", "POST"])
@requiere_auth
def editar(id):
    conn = get_db()
    cur = conn.cursor()
    
    if request.method == "POST":
        nuevo_estado = request.form.get('estado')
        
        cur.execute("SELECT * FROM reparaciones WHERE id = %s", (id,))
        reparacion = cur.fetchone()
        
        if 'foto' in request.files and request.files['foto'].filename:
            try:
                cloudinary.config(cloud_name="drpmg1lso", api_key="519922232242146", api_secret="kxsPgE73Eu59VQ03qSCvWCeaHw4")
                upload_result = cloudinary.uploader.upload(request.files['foto'])
                foto_url = upload_result.get('secure_url')
                cur.execute("UPDATE reparaciones SET foto_url = %s WHERE id = %s", (foto_url, id))
            except:
                pass
        
        cur.execute('''UPDATE reparaciones SET cliente_nombre=%s, cliente_telefono=%s, equipo=%s, marca=%s, falla=%s, tecnico=%s, estado=%s, actualizado_en=%s WHERE id=%s''',
            (request.form.get('cliente_nombre'), request.form.get('cliente_telefono'),
             request.form.get('equipo'), request.form.get('marca'), request.form.get('falla'),
             request.form.get('tecnico'), nuevo_estado, datetime.datetime.now().isoformat(), id))
        
        if nuevo_estado == 'lista' and reparacion[11] != 'lista':
            enviar_whatsapp(f"✅ TICKET LISTO {reparacion[1]}\nCliente: {reparacion[2]}\nEquipo: {reparacion[4]}\nHorario: Lunes a Viernes 9am-4pm")
        
        if nuevo_estado == 'entregado' and reparacion[11] != 'entregado':
            fecha_salida = datetime.datetime.now().isoformat()
            cur.execute("UPDATE reparaciones SET fecha_salida=%s WHERE id=%s", (fecha_salida, id))
            enviar_whatsapp(f"🎉 TICKET ENTREGADO {reparacion[1]}\nCliente: {reparacion[2]}\nEquipo: {reparacion[4]}\nGarantía 2 meses")
        
        conn.commit()
        conn.close()
        return redirect(url_for('listado'))
    
    cur.execute("SELECT * FROM reparaciones WHERE id = %s", (id,))
    reparacion = cur.fetchone()
    conn.close()
    return render_template_string(EDITAR_HTML, reparacion=reparacion)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
