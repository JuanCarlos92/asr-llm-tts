#main.py

# Importamos librerías necesarias
import os
import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from twilio.twiml.voice_response import VoiceResponse
from dotenv import load_dotenv
from session import SessionManager

# Cargar las variables de entorno desde el archivo .env
load_dotenv()

# Obtenemos las variables de entorno necesarias
PUBLIC_HOST = os.getenv("PUBLIC_HOST")  # Dirección pública donde se expone la API (dominio o ngrok)
MEDIA_WS_PATH = os.getenv("MEDIA_WS_PATH", "/media")  # Ruta del WebSocket para la transmisión de audio
PORT = int(os.getenv("PORT", "8000"))  # Puerto donde se ejecutará FastAPI (por defecto 8000)

# Inicializamos la aplicación FastAPI
app = FastAPI()

# Montamos la carpeta "static/audio" para servir archivos de audio generados por el TTS
app.mount("/audio", StaticFiles(directory="static/audio"), name="audio")

# Inicializamos el administrador de sesiones para manejar múltiples llamadas
manager = SessionManager()


# Endpoint que Twilio invoca cuando entra una llamada
@app.post("/incoming")
async def incoming_call(request: Request):
    # Obtenemos los datos enviados por Twilio en el formulario
    form = await request.form()
    call_sid = form.get("CallSid")  # Identificador único de la llamada

    # Si no está configurado el host público, devolvemos un error en la respuesta TwiML
    if not PUBLIC_HOST:
        return Response("<Response><Say>Servidor no configurado</Say></Response>", media_type="text/xml")

    # Twilio necesita una URL segura (wss://) para transmitir el audio en tiempo real
    host = PUBLIC_HOST.replace("https://", "").replace("http://", "")
    ws_url = f"wss://{host}{MEDIA_WS_PATH}/{call_sid}"

    # Construimos la respuesta para Twilio en formato XML (TwiML)
    resp = VoiceResponse()
    resp.start().stream(url=ws_url)  # Iniciamos la transmisión de audio hacia nuestro servidor
    resp.say("Conectando con el asistente automatizado. Espere un momento por favor.")  # Mensaje inicial
    return Response(str(resp), media_type="text/xml")


# Endpoint WebSocket donde Twilio enviará los datos de audio de la llamada
@app.websocket("/media/{call_sid}")
async def media_ws(websocket: WebSocket, call_sid: str):
    await websocket.accept()  # Aceptamos la conexión WebSocket
    session = manager.create_session(call_sid, websocket)  # Creamos una sesión para esa llamada

    try:
        while True:
            # Recibimos datos del WebSocket en formato texto (JSON de Twilio)
            data = await websocket.receive_text()
            # Pasamos los datos a la sesión para procesarlos (audio → transcripción → respuesta IA → TTS)
            await session.on_message(data)
    except WebSocketDisconnect:
        # Si la llamada se desconecta, cerramos la sesión
        await session.on_disconnect()
    except Exception as e:
        # Capturamos errores y cerramos la sesión
        print("WS error:", e)
        await session.on_disconnect()


# Endpoint simple de salud para verificar si el servidor está funcionando
@app.get("/health")
async def health():
    return {"status": "ok"}


# Endpoint para servir archivos de audio generados (respuesta de la IA en TTS)
@app.get("/audiofile/{filename}")
async def get_audiofile(filename: str):
    path = f"static/audio/{filename}"  # Ruta del archivo en disco
    if os.path.exists(path):
        # Si existe, lo devolvemos como un archivo MP3
        return FileResponse(path, media_type="audio/mpeg")
    # Si no existe, devolvemos error 404
    return Response(status_code=404)
