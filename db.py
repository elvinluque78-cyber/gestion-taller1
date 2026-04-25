import sqlite3
import datetime
import os

DB_NAME = "taller.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reparaciones (
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
            actualizado_en TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Base de datos inicializada")

if __name__ == "__main__":
    if not os.path.exists(DB_NAME):
        init_db()
    else:
        print("✅ Base de datos ya existe")
