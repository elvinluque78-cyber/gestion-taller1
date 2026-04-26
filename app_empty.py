print("✅ La aplicación está cargando")

def app(environ, start_response):
    print("✅ Llegó una petición")
    status = '200 OK'
    headers = [('Content-type', 'text/html; charset=utf-8')]
    start_response(status, headers)
    return [b"✅ El servidor Railway funciona correctamente"]

if __name__ == "__main__":
    print("Servidor ejecutándose...")
