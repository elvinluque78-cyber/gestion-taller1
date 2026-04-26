import sqlite3
import os

DB_NAME = "taller.db"

# Eliminar base de datos antigua
if os.path.exists(DB_NAME):
    os.remove(DB_NAME)
    print("✅ Base de datos antigua eliminada")

# Crear nueva base de datos con la tabla correcta
conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE reparaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
print("✅ Nueva tabla creada con columna foto_url")
