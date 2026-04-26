from flask import Flask, request, render_template_string, redirect, url_for
import sqlite3
import datetime
import requests
import os
import re
from twilio.rest import Client

app = Flask(__name__)
DB_NAME = "taller.db"

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
        input, textarea { display: block; margin: 10px 0; padding: 10px; width: 100%; max-width: 400px; border-radius: 5px; border: 1px solid #ccc; }
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
        <form method="POST">
            <input type="text" name="cliente_nombre" placeholder="Nombre del cliente" required>
            <input type="text" name="cliente_telefono" placeholder="Teléfono (ej: 04123697532)" required>
            <input type="text" name="equipo" placeholder="Equipo (ej: Lavadora)" required>
            <input type="text" name="marca" placeholder="Marca">
            <textarea name="falla" placeholder="Falla o código de error" rows="3"></textarea>
            <input type="number" step="0.01" name="presupuesto" placeholder="Presupuesto (opcional)">
            <input type="text" name="tecnico" placeholder="Técnico">
            <button type="submit">Guardar reparación</button>
        </form>
        <a href="/listado" class="btn">📋 Ver listado</a>
    </div>
</body>
</html>
'''

# HTML para el listado
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
        .btn { display: inline-block; background: #007bff; color: white; padding: 8px 15px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        .btn:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 Listado de Reparaciones</h1>
        <a href="/" class="btn">➕ Nueva reparación</a>
        <table>
            <tr>
                <th>Código</th>
                <th>Cliente</th>
                <th>Teléfono</th>
                <th>Equipo</th>
                <th>Falla</th>
                <th>Estado</th>
                <th>Entrada</th>
                <th>Técnico</th>
            </tr>
            {% for r in reparaciones %}
            <tr>
                <td>{{ r[1] }}</td>
                <td>{{ r[2] }}</td>
                <td>{{ r[3] }}</td>
                <td>{{ r[4] }} {{ r[5] }}</td>
                <td>{{ r[6][:50] }}{% if r[6]|length > 50 %}...{% endif %}</td>
                <td class="estado-{{ r[11] }}">{{ r[11] }}</td>
                <td>{{ r[9][:10] if r[9] else '' }}</td>
                <td>{{ r[10] if r[10] else '' }}</td>
            </tr>
            {% endfor %}
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

def generar_codigo():
    conn = sqlite3.connect(DB_NAME)
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
    """Limpia el número de teléfono: elimina espacios, guiones, +, y deja solo dígitos."""
    if not numero:
        return None
    # Eliminar todo excepto dígitos
    numero_limpio = re.sub(r'\D', '', numero)
    # Si tiene 11 dígitos y empieza con 0 (ej: 04123697532), lo formatea con 58
    if len(numero_limpio) == 11 and numero_limpio.startswith('0'):
        numero_limpio = '58' + numero_limpio[1:]
    # Si tiene 10 dígitos, agregar 58 al inicio
    elif len(numero_limpio) == 10:
        numero_limpio = '58' + numero_limpio
    # Si tiene 11 dígitos pero no empieza con 58
    elif len(numero_limpio) == 11 and not numero_limpio.startswith('58'):
        numero_limpio = '58' + numero_limpio
    return numero_limpio

@app.route("/", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        codigo = generar_codigo()
        ahora = datetime.datetime.now().isoformat()
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reparaciones (codigo, cliente_nombre, cliente_telefono, equipo, marca, falla, presupuesto, tecnico, fecha_entrada, estado, creado_en, actualizado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (codigo, request.form.get('cliente_nombre'), request.form.get('cliente_telefono'),
              request.form.get('equipo'), request.form.get('marca'), request.form.get('falla'),
              float(request.form.get('presupuesto')) if request.form.get('presupuesto') else None,
              request.form.get('tecnico'), ahora, 'en_reparacion', ahora, ahora))
        conn.commit()
        conn.close()
        
        # Enviar Telegram al técnico
        mensaje_telegram = f"🆕 *Nueva reparación*\n📌 Código: {codigo}\n👤 Cliente: {request.form.get('cliente_nombre')}\n📞 Tel: {request.form.get('cliente_telefono')}\n🔧 Equipo: {request.form.get('equipo')} {request.form.get('marca')}\n👨‍🔧 Técnico: {request.form.get('tecnico')}"
        enviar_telegram(mensaje_telegram)
        
        # Enviar WhatsApp al cliente (usando variables de entorno)
        try:
            twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
            twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
            twilio_whatsapp_from = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
            
            if not twilio_account_sid or not twilio_auth_token:
                print("⚠️ Twilio no configurado: faltan variables de entorno")
            else:
                twilio_client = Client(twilio_account_sid, twilio_auth_token)

                numero_original = request.form.get('cliente_telefono')
                numero_limpio = limpiar_numero_telefono(numero_original)
                cliente_whatsapp = f"whatsapp:+{numero_limpio}"
                
                print(f"DEBUG: Número original: {numero_original}")
                print(f"DEBUG: Número limpio: {numero_limpio}")
                print(f"DEBUG: WhatsApp final: {cliente_whatsapp}")

                mensaje_whatsapp = f"""🧾 *Ticket de ingreso – Elvin Tech*
📌 N° de ticket: *{codigo}*
👤 Cliente: {request.form.get('cliente_nombre')}
📞 Teléfono: {request.form.get('cliente_telefono')}
🔧 Equipo: {request.form.get('equipo')} {request.form.get('marca')}
⚠️ Falla: {request.form.get('falla')}
💰 Presupuesto: {request.form.get('presupuesto')}
📅 Fecha ingreso: {ahora[:10]}

*Guardá este número.* Podés consultar el estado de tu equipo con él.

Gracias por confiar en nosotros."""

                twilio_client.messages.create(
                    body=mensaje_whatsapp,
                    from_=twilio_whatsapp_from,
                    to=cliente_whatsapp
                )
                print(f"✅ WhatsApp enviado a {cliente_whatsapp}")
        except Exception as e:
            print(f"⚠️ Error al enviar WhatsApp: {e}")
        
        return redirect(url_for('nueva'))
    return render_template_string(FORMULARIO)

@app.route("/listado")
def listado():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reparaciones ORDER BY id DESC")
    reparaciones = cursor.fetchall()
    conn.close()
    return render_template_string(LISTADO, reparaciones=reparaciones)

if __name__ == "__main__":
    if not os.path.exists(DB_NAME):
        import db
        db.init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
