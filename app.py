from flask import Flask, request, render_template_string, redirect, url_for, session
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
app.secret_key = os.environ.get("SECRET_KEY", "clave_super_secreta_garantias_2025")

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
    
    # Tabla de reparaciones
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
    
    # Tabla de garantías
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
            actualizado_en TEXT NOT NULL,
            FOREIGN KEY (codigo) REFERENCES reparaciones(codigo)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Base de datos PostgreSQL inicializada (reparaciones + garantias)")

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
        <a href="/garantias" class="btn">🛡️ Garantías</a>
        <a href="/consulta" class="btn">🔍 Consultar ticket</a>
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
        print("✅ Telegram enviado")
    except Exception as e:
        print(f"⚠️ Error en Telegram: {e}")

def enviar_telegram_garantia_lista(codigo, cliente_nombre, equipo, marca):
    token = "8742564082:AAGuvUN_q4NjBgUL70hcRsnCkwS-eumS6Sc"
    chat_id = "7150902056"
    mensaje = f"🛡️ *GARANTÍA LISTA*\n📌 Código: {codigo}\n👤 Cliente: {cliente_nombre}\n🔧 Equipo: {equipo} {marca}\n\n🏁 El equipo en garantía ya está listo para retirar."
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})
        print("✅ Telegram GARANTÍA LISTO enviado")
    except Exception as e:
        print(f"⚠️ Error en Telegram GARANTÍA LISTO: {e}")

def enviar_whatsapp_garantia_lista(codigo, cliente_nombre, equipo, marca, telefono_cliente):
    """Envía WhatsApp al técnico cuando garantía está lista"""
    try:
        twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_whatsapp_from = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        
        print(f"📱 Intentando enviar WhatsApp GARANTÍA LISTA")
        
        if not twilio_account_sid or not twilio_auth_token:
            print("⚠️ Faltan credenciales de Twilio")
            return False
        
        twilio_client = Client(twilio_account_sid, twilio_auth_token)
        tecnico_whatsapp = "whatsapp:+584123697532"
        
        mensaje = f"""🛡️ *GARANTÍA LISTA - PARA REENVIAR AL CLIENTE*

🔧 *Elvin Technology*
📌 Código: *{codigo}*
👤 Cliente: {cliente_nombre}
🔧 Equipo: {equipo} {marca}

🏁 El equipo en garantía ya está listo para retirar.

⏰ *Horario de retiro:*
📍 Lunes a Sábado
🕘 9:00 am a 4:00 pm

📞 Contacto: +58 412 3697532"""
        
        message = twilio_client.messages.create(
            body=mensaje,
            from_=twilio_whatsapp_from,
            to=tecnico_whatsapp
        )
        print(f"✅ WhatsApp GARANTÍA LISTA enviado - SID: {message.sid}")
        return True
    except Exception as e:
        print(f"⚠️ Error enviando WhatsApp GARANTÍA LISTA: {e}")
        return False

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
        
        # Telegram nuevo ticket
        mensaje_telegram = f"🆕 *Nueva reparación*\n📌 Código: {codigo}\n👤 Cliente: {request.form.get('cliente_nombre')}\n📞 Tel: {request.form.get('cliente_telefono')}\n🔧 Equipo: {request.form.get('equipo')} {request.form.get('marca')}\n⚠️ Falla: {request.form.get('falla')}\n💰 Presupuesto: {request.form.get('presupuesto')}\n👨‍🔧 Técnico: {request.form.get('tecnico')}"
        if foto_url:
            mensaje_telegram += f"\n📸 Foto: {foto_url}"
        enviar_telegram(mensaje_telegram)
        
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
    
    # HTML del listado (lo mismo que antes, omito por longitud)
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Listado de Reparaciones</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; background: #f0f2f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; overflow-x: auto; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background: #007bff; color: white; }}
            .btn {{ display: inline-block; background: #28a745; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
            .btn-small {{ background: #007bff; color: white; padding: 4px 8px; text-decoration: none; border-radius: 3px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📋 Listado de Reparaciones</h1>
            <a href="/" class="btn">➕ Nueva</a>
            <a href="/garantias" class="btn">🛡️ Garantías</a>
            <a href="/consulta" class="btn">🔍 Consultar</a>
            <table>
                <thead><tr><th>Código</th><th>Cliente</th><th>Equipo</th><th>Estado</th><th>Acciones</th></tr></thead>
                <tbody>
                    {"".join(f"<tr><td>{r[1]}</td><td>{r[2]}</td><td>{r[4]}</td><td>{r[11]}</td><td><a href='/editar/{r[0]}' class='btn-small'>✏️</a></td></tr>" for r in reparaciones)}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    '''

@app.route("/garantias", methods=["GET", "POST"])
@requiere_autenticacion
def garantias():
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == "POST":
        # Crear nueva garantía
        codigo = request.form.get("codigo", "").strip().upper()
        tecnico = request.form.get("tecnico")
        ahora = datetime.datetime.now().isoformat()
        
        # Obtener datos del ticket original
        cursor.execute("SELECT cliente_nombre, cliente_telefono, equipo, marca, falla FROM reparaciones WHERE codigo = %s", (codigo,))
        ticket = cursor.fetchone()
        
        if not ticket:
            conn.close()
            return '<h3>❌ Código no encontrado</h3><a href="/garantias">Volver</a>'
        
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
                    print(f"✅ Foto garantía subida: {foto_url}")
                except Exception as e:
                    print(f"⚠️ Error al subir foto garantía: {e}")
        
        cursor.execute('''
            INSERT INTO garantias (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla_original, tecnico, fecha_entrada, estado, foto_url, creado_en, actualizado_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (codigo, ticket[0], ticket[1], ticket[2], ticket[3], ticket[4], tecnico, ahora, 'en_reparacion', foto_url, ahora, ahora))
        
        conn.commit()
        conn.close()
        return redirect(url_for('garantias'))
    
    # GET: mostrar listado de garantías
    cursor.execute("SELECT * FROM garantias ORDER BY id DESC")
    garantias_lista = cursor.fetchall()
    conn.close()
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Garantías</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; background: #f0f2f5; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; overflow-x: auto; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background: #007bff; color: white; }}
            .btn {{ display: inline-block; background: #28a745; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
            .btn-small {{ background: #007bff; color: white; padding: 4px 8px; text-decoration: none; border-radius: 3px; }}
            input {{ padding: 8px; margin: 5px; }}
            select {{ padding: 8px; margin: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🛡️ Garantías</h1>
            <a href="/" class="btn">➕ Nueva reparación</a>
            <a href="/listado" class="btn">📋 Listado</a>
            <a href="/consulta" class="btn">🔍 Consultar</a>
            
            <h2>📝 Nueva garantía</h2>
            <form method="POST" enctype="multipart/form-data">
                <input type="text" name="codigo" placeholder="Código del ticket (E-001)" required>
                <input type="text" name="tecnico" placeholder="Técnico">
                <input type="file" name="foto" accept="image/*">
                <button type="submit">➕ Agregar garantía</button>
            </form>
            
            <h2>📋 Listado de garantías</h2>
            <table>
                <thead>
                    <tr>
                        <th>Código</th>
                        <th>Cliente</th>
                        <th>Equipo</th>
                        <th>Estado</th>
                        <th>Entrada</th>
                        <th>Foto</th>
                        <th>Acciones</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(f"<tr><td>{g[1]}</td><td>{g[2]}</td><td>{g[4]}</td><td>{g[8]}</td><td>{g[7][:10] if g[7] else ''}</td><td>{'<a href=\"/foto_garantia/\"' + str(g[0]) + '\" target=\"_blank\">📷</a>' if g[9] else '—'}</td><td><a href=\"/editar_garantia/{g[0]}\" class=\"btn-small\">✏️ Editar</a></td></tr>" for g in garantias_lista)}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    '''

@app.route("/editar_garantia/<int:id>", methods=["GET", "POST"])
@requiere_autenticacion
def editar_garantia(id):
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == "POST":
        # Obtener estado anterior
        cursor.execute("SELECT estado, codigo, cliente_nombre, equipo, marca, cliente_telefono FROM garantias WHERE id = %s", (id,))
        garantia_anterior = cursor.fetchone()
        estado_anterior = garantia_anterior[0]
        codigo = garantia_anterior[1]
        cliente_nombre = garantia_anterior[2]
        equipo = garantia_anterior[3]
        marca = garantia_anterior[4]
        cliente_telefono = garantia_anterior[5]
        
        # Obtener nuevos datos
        estado_nuevo = request.form.get("estado")
        tecnico = request.form.get("tecnico")
        actualizado = datetime.datetime.now().isoformat()
        
        # Si cambia a "lista", enviar notificaciones
        if estado_nuevo == 'lista' and estado_anterior != 'lista':
            print(f"📢 Garantía {codigo} cambiada a LISTA - Enviando notificaciones")
            enviar_telegram_garantia_lista(codigo, cliente_nombre, equipo, marca)
            enviar_whatsapp_garantia_lista(codigo, cliente_nombre, equipo, marca, cliente_telefono)
        
        # Actualizar garantía
        cursor.execute('''
            UPDATE garantias 
            SET estado = %s, tecnico = %s, actualizado_en = %s
            WHERE id = %s
        ''', (estado_nuevo, tecnico, actualizado, id))
        
        # Si cambia a "lista", también registrar fecha_salida
        if estado_nuevo == 'lista' and estado_anterior != 'lista':
            cursor.execute('''
                UPDATE garantias SET fecha_salida = %s WHERE id = %s
            ''', (actualizado, id))
        
        conn.commit()
        conn.close()
        return redirect(url_for('garantias'))
    
    # GET: mostrar formulario de edición
    cursor.execute("SELECT * FROM garantias WHERE id = %s", (id,))
    garantia = cursor.fetchone()
    conn.close()
    
    if not garantia:
        return "Garantía no encontrada", 404
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Editar Garantía</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; background: #f0f2f5; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
            input, textarea, select {{ display: block; margin: 10px 0; padding: 10px; width: 100%; max-width: 400px; border-radius: 5px; border: 1px solid #ccc; }}
            button {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
            .btn {{ display: inline-block; background: #28a745; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✏️ Editar Garantía</h1>
            <label>Código:</label>
            <input type="text" value="{garantia[1]}" disabled>
            <label>Cliente:</label>
            <input type="text" value="{garantia[2]}" disabled>
            <label>Equipo:</label>
            <input type="text" value="{garantia[4]}" disabled>
            <form method="POST">
                <label>Técnico:</label>
                <input type="text" name="tecnico" value="{garantia[6] if garantia[6] else ''}">
                <label>Estado:</label>
                <select name="estado">
                    <option value="en_reparacion" {'selected' if garantia[8] == 'en_reparacion' else ''}>En reparación</option>
                    <option value="espera_repuesto" {'selected' if garantia[8] == 'espera_repuesto' else ''}>Espera repuesto</option>
                    <option value="lista" {'selected' if garantia[8] == 'lista' else ''}>Lista</option>
                </select>
                <button type="submit">💾 Guardar cambios</button>
                <a href="/garantias" class="btn">← Cancelar</a>
            </form>
        </div>
    </body>
    </html>
    '''

@app.route("/foto_garantia/<int:id>")
def foto_garantia(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT foto_url FROM garantias WHERE id = %s", (id,))
    resultado = cursor.fetchone()
    conn.close()
    
    if resultado and resultado[0]:
        foto_url = resultado[0]
        return f'<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Foto</title><style>body {{ display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f0f2f5; }} img {{ max-width: 100%; max-height: 100vh; }}</style></head><body><img src="{foto_url}" alt="Foto del equipo en garantía"></body></html>'
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
            cursor.execute("SELECT codigo, cliente_nombre, cliente_telefono, equipo, marca FROM reparaciones WHERE codigo = %s", (codigo,))
            ticket = cursor.fetchone()
            
            if ticket:
                cursor.execute("UPDATE reparaciones SET estado = 'lista', actualizado_en = %s WHERE codigo = %s AND estado = 'en_reparacion'", 
                              (datetime.datetime.now().isoformat(), codigo))
                conn.commit()
                enviar_telegram_listo(ticket[0], ticket[1], ticket[2], ticket[3])
                enviar_whatsapp_listo(ticket[0], ticket[1], ticket[2], ticket[3], ticket[2])
            
            conn.close()
            return '<h3>✅ Ticket marcado como LISTO</h3><a href="/consulta">Volver</a>'
        
        cursor.execute("SELECT id, codigo, estado, foto_url, cliente_nombre, cliente_telefono, equipo, marca FROM reparaciones WHERE codigo = %s", (codigo,))
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
        equipo = request.form.get("equipo")
        marca = request.form.get("marca")
        falla = request.form.get("falla")
        presupuesto = request.form.get("presupuesto")
        tecnico = request.form.get("tecnico")
        estado_nuevo = request.form.get("estado")
        actualizado = datetime.datetime.now().isoformat()
        
        # Obtener estado anterior
        cursor.execute("SELECT estado, codigo, cliente_nombre, cliente_telefono, equipo, marca FROM reparaciones WHERE id = %s", (id,))
        resultado = cursor.fetchone()
        estado_anterior = resultado[0]
        codigo = resultado[1]
        cliente_nombre = resultado[2]
        cliente_telefono = resultado[3]
        equipo_old = resultado[4]
        marca_old = resultado[5]
        
        # Si cambia a "entregado", registrar fecha_salida
        fecha_salida = None
        if estado_nuevo == 'entregado' and estado_anterior != 'entregado':
            fecha_salida = datetime.datetime.now().isoformat()
            print(f"✅ Ticket {id} marcado como ENTREGADO - Fecha salida: {fecha_salida}")
            enviar_telegram_entregado(codigo, cliente_nombre, equipo_old, marca_old, cliente_telefono, fecha_salida)
        
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
    
    cursor.execute("SELECT * FROM reparaciones WHERE id = %s", (id,))
    reparacion = cursor.fetchone()
    conn.close()
    
    if reparacion is None:
        return "Reparación no encontrada", 404
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Editar Reparación</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; background: #f0f2f5; }}
            .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }}
            input, textarea, select {{ display: block; margin: 10px 0; padding: 10px; width: 100%; max-width: 400px; border-radius: 5px; border: 1px solid #ccc; }}
            button {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }}
            .btn {{ display: inline-block; background: #28a745; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✏️ Editar Reparación</h1>
            <form method="POST">
                <label>Código:</label>
                <input type="text" value="{reparacion[1]}" disabled>
                <label>Cliente:</label>
                <input type="text" value="{reparacion[2]}" disabled>
                <label>Teléfono:</label>
                <input type="text" value="{reparacion[3]}" disabled>
                <label>Equipo:</label>
                <input type="text" name="equipo" value="{reparacion[4]}" required>
                <label>Marca:</label>
                <input type="text" name="marca" value="{reparacion[5] if reparacion[5] else ''}">
                <label>Falla:</label>
                <textarea name="falla" rows="3">{reparacion[6] if reparacion[6] else ''}</textarea>
                <label>Presupuesto:</label>
                <input type="number" step="0.01" name="presupuesto" value="{reparacion[7] if reparacion[7] else ''}">
                <label>Técnico:</label>
                <input type="text" name="tecnico" value="{reparacion[8] if reparacion[8] else ''}">
                <label>Estado:</label>
                <select name="estado">
                    <option value="en_reparacion" {'selected' if reparacion[11] == 'en_reparacion' else ''}>En reparación</option>
                    <option value="espera_repuesto" {'selected' if reparacion[11] == 'espera_repuesto' else ''}>Espera repuesto</option>
                    <option value="lista" {'selected' if reparacion[11] == 'lista' else ''}>Listo</option>
                    <option value="entregado" {'selected' if reparacion[11] == 'entregado' else ''}>Entregado</option>
                    <option value="no_procede" {'selected' if reparacion[11] == 'no_procede' else ''}>No Procede</option>
                </select>
                <button type="submit">💾 Guardar cambios</button>
                <a href="/listado" class="btn">← Cancelar</a>
            </form>
        </div>
    </body>
    </html>
    '''

def enviar_telegram_listo(codigo, cliente_nombre, equipo, marca):
    token = "8742564082:AAGuvUN_q4NjBgUL70hcRsnCkwS-eumS6Sc"
    chat_id = "7150902056"
    mensaje = f"✅ *EQUIPO LISTO*\n📌 Código: {codigo}\n👤 Cliente: {cliente_nombre}\n🔧 Equipo: {equipo} {marca}\n\n🏁 El equipo está listo para ser entregado al cliente."
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})
        print("✅ Telegram LISTO enviado")
    except Exception as e:
        print(f"⚠️ Error en Telegram LISTO: {e}")

def enviar_whatsapp_listo(codigo, cliente_nombre, equipo, marca, telefono_cliente):
    try:
        twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_whatsapp_from = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        
        if not twilio_account_sid or not twilio_auth_token:
            print("⚠️ Faltan credenciales de Twilio")
            return False
        
        twilio_client = Client(twilio_account_sid, twilio_auth_token)
        tecnico_whatsapp = "whatsapp:+584123697532"
        
        mensaje = f"""✅ *EQUIPO LISTO*

🔧 *Elvin Technology*
📌 Código: *{codigo}*
👤 Cliente: {cliente_nombre}
🔧 Equipo: {equipo} {marca}

🏁 El equipo ya está listo para retirar.
📞 Contacto: +58 412 3697532"""
        
        message = twilio_client.messages.create(
            body=mensaje,
            from_=twilio_whatsapp_from,
            to=tecnico_whatsapp
        )
        print(f"✅ WhatsApp de LISTO enviado - SID: {message.sid}")
        return True
    except Exception as e:
        print(f"⚠️ Error enviando WhatsApp de LISTO: {e}")
        return False

def enviar_telegram_entregado(codigo, cliente_nombre, equipo, marca, telefono_cliente, fecha_entrega):
    fecha_entrega_obj = datetime.datetime.strptime(fecha_entrega[:10], "%Y-%m-%d")
    fecha_fin = fecha_entrega_obj + datetime.timedelta(days=60)
    fecha_fin_str = fecha_fin.strftime("%d/%m/%Y")
    fecha_entrega_str = fecha_entrega_obj.strftime("%d/%m/%Y")
    
    token = "8742564082:AAGuvUN_q4NjBgUL70hcRsnCkwS-eumS6Sc"
    chat_id = "7150902056"
    mensaje = f"✅ *EQUIPO ENTREGADO - GARANTÍA 2 MESES*\n📌 Código: {codigo}\n👤 Cliente: {cliente_nombre}\n🔧 Equipo: {equipo} {marca}\n📅 Entrega: {fecha_entrega_str}\n🛡️ Garantía hasta: {fecha_fin_str}"
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})
        print("✅ Telegram ENTREGADO enviado")
    except Exception as e:
        print(f"⚠️ Error en Telegram ENTREGADO: {e}")

def enviar_whatsapp_entregado(codigo, cliente_nombre, equipo, marca, telefono_cliente, fecha_entrega):
    try:
        twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_whatsapp_from = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
        
        if not twilio_account_sid or not twilio_auth_token:
            print("⚠️ Faltan credenciales de Twilio")
            return False
        
        twilio_client = Client(twilio_account_sid, twilio_auth_token)
        tecnico_whatsapp = "whatsapp:+584123697532"
        
        fecha_entrega_obj = datetime.datetime.strptime(fecha_entrega[:10], "%Y-%m-%d")
        fecha_fin = fecha_entrega_obj + datetime.timedelta(days=60)
        fecha_fin_str = fecha_fin.strftime("%d/%m/%Y")
        fecha_entrega_str = fecha_entrega_obj.strftime("%d/%m/%Y")
        
        mensaje = f"""✅ *EQUIPO ENTREGADO - GARANTÍA ACTIVADA*

🔧 *Elvin Technology*
📌 Código: *{codigo}*
👤 Cliente: {cliente_nombre}
🔧 Equipo: {equipo} {marca}

📅 *Fecha de entrega:* {fecha_entrega_str}

🛡️ *GARANTÍA: 2 MESES*
Válida hasta: {fecha_fin_str}

Cubre: mano de obra y repuestos (excepto mal uso)

📞 Contacto: +58 412 3697532"""
        
        message = twilio_client.messages.create(
            body=mensaje,
            from_=twilio_whatsapp_from,
            to=tecnico_whatsapp
        )
        print(f"✅ WhatsApp de ENTREGADO enviado - SID: {message.sid}")
        return True
    except Exception as e:
        print(f"⚠️ Error enviando WhatsApp de ENTREGADO: {e}")
        return False

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
