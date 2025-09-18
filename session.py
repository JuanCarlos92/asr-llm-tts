#session.py
# Módulo que gestiona las sesiones de llamadas activas y el procesamiento de audio/texto.

#1-Recibe audio desde Twilio → lo acumula en buffer.
#2-Cuando hay suficiente audio → lo transcribe con Whisper.
#3-Envía el texto a GPT → obtiene respuesta en lenguaje natural.
#4-Convierte la respuesta en voz (TTS) → genera un MP3/WAV.
#5-Reproduce el audio al usuario en la llamada vía Twilio.


# Librerías estándar
import json
import asyncio
import os
from collections import deque
import requests
from dotenv import load_dotenv

# Importamos funciones auxiliares desde utils.py
from utils import (
    decode_twilio_media_frame,  # Decodifica el audio enviado por Twilio (base64 → PCM)
    append_pcm_to_buffer,       # Añade los bytes de audio a un buffer
    save_raw_pcm_to_wav,        # Convierte el audio PCM a un archivo WAV
    transcribe_wav,             # Transcribe el audio usando Whisper
    synthesize_tts,             # Convierte la respuesta en voz (TTS)
    twilio_redirect_play,       # Hace que Twilio reproduzca el archivo de audio al usuario
    is_speech_present,          # Detecta si hay voz en el fragmento de audio (Voice Activity Detection)
)

# Cargar variables de entorno desde .env
load_dotenv()

# Configuración de tamaños y tiempos para el procesamiento del audio
CHUNK_MS = 800              # Tamaño de cada "bloque" de audio en milisegundos
MAX_BUFFER_SECONDS = 20     # Máximo de segundos de audio que guardamos en memoria
SILENCE_TIMEOUT = 1.0       # Tiempo máximo de silencio antes de procesar un turno


# Clase que representa una sesión activa de llamada (un usuario hablando con la IA)
class Session:
    def __init__(self, call_sid, websocket):
        self.call_sid = call_sid  # ID único de la llamada (lo da Twilio)
        self.ws = websocket       # Conexión WebSocket asociada a Twilio
        self.buffer = bytearray() # Buffer donde acumulamos los datos de audio (PCM crudo)
        self.lock = asyncio.Lock() # Para evitar que se procesen varios turnos en paralelo
        self.last_voice_ts = None  # Última marca de tiempo donde se detectó voz
        self.vad_queue = deque()   # Cola para analizar la detección de voz
        self.processing = False    # Flag para saber si ya estamos procesando un turno
        self.conversation_history = []  # Historial de la conversación (user/assistant)
        self._silence_timer = None      # Temporizador para detectar silencios

    # Método que se ejecuta cada vez que recibimos un mensaje desde Twilio (WebSocket)
    async def on_message(self, raw_text):
        msg = json.loads(raw_text)  # Twilio envía datos en JSON
        event = msg.get("event")    # Extraemos el tipo de evento

        # Caso: evento "media" → contiene un fragmento de audio
        if event == "media":
            payload_b64 = msg["media"]["payload"]  # Extraemos el audio en base64
            pcm = decode_twilio_media_frame(payload_b64)  # Lo convertimos a PCM crudo
            append_pcm_to_buffer(self.buffer, pcm)  # Lo añadimos al buffer de audio

            # Si detectamos voz en el fragmento, actualizamos la marca de tiempo
            if is_speech_present(pcm):
                self.last_voice_ts = asyncio.get_event_loop().time()

            # Si tenemos suficiente audio acumulado, lanzamos el procesamiento
            if len(self.buffer) >= 16000 * 2 * (CHUNK_MS / 1000.0):
                if not self.processing:
                    asyncio.create_task(self._process_turn())

        # Caso: evento "stop" → Twilio indica que terminó la transmisión de audio
        elif event == "stop":
            await self._process_turn()

    # Método que procesa un turno completo (audio → texto → IA → voz → reproducir)
    async def _process_turn(self):
        async with self.lock:  # Bloqueamos para no procesar dos turnos a la vez
            self.processing = True
            if len(self.buffer) == 0:
                self.processing = False
                return  # Si no hay audio, no hacemos nada

            # Guardamos el audio en un archivo WAV
            wav_path = save_raw_pcm_to_wav(self.buffer)
            # Vaciamos el buffer para acumular nuevo audio
            self.buffer = bytearray()

            # Paso 1: Transcripción con Whisper
            try:
                text = transcribe_wav(wav_path)
            except Exception as e:
                print("Transcription error:", e)
                text = ""

            # Si no hay texto válido, salimos
            if not text.strip():
                self.processing = False
                return

            # Mostramos el texto transcrito en consola
            print(f"[{self.call_sid}] Transcribed: {text}")
            # Guardamos el mensaje del usuario en el historial
            self.conversation_history.append({"role": "user", "content": text})

            # Paso 2: Generación de respuesta con GPT (STREAMING + TTS parcial)
            try:
                response_text = ""
                partial_text = ""  # Texto acumulado para TTS parcial
                min_words_per_chunk = 5  # Generar TTS cada 5 palabras

                # Llamada a API streaming (SSE)
                url = "https://api.openai.com/v1/chat/completions"
                headers = {
                    "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": self.conversation_history,
                    "max_tokens": 250,
                    "temperature": 0.2,
                    "stream": True  # Activamos streaming
                }

                with requests.post(url, headers=headers, json=payload, stream=True, timeout=60) as r:
                    if r.status_code != 200:
                        raise Exception(f"LLM streaming failed: {r.status_code} {r.text}")
                    # Iteramos sobre los deltas que llegan
                    for line in r.iter_lines(decode_unicode=True):
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            if data_str:
                                data_json = json.loads(data_str)
                                delta = data_json.get("choices")[0].get("delta", {}).get("content", "")
                                if delta:
                                    response_text += delta
                                    partial_text += delta
                                    # Cada X palabras, generamos TTS parcial
                                    if len(partial_text.split()) >= min_words_per_chunk:
                                        try:
                                            filename = synthesize_tts(partial_text)
                                            audio_url = f"{os.getenv('PUBLIC_HOST')}/audio/{filename}"
                                            twilio_redirect_play(self.call_sid, audio_url)
                                        except Exception as e:
                                            print("Partial TTS/play error:", e)
                                        partial_text = ""  # Reiniciamos buffer parcial

                # Si queda texto parcial sin reproducir, lo convertimos en audio final
                if partial_text.strip():
                    try:
                        filename = synthesize_tts(partial_text)
                        audio_url = f"{os.getenv('PUBLIC_HOST')}/audio/{filename}"
                        twilio_redirect_play(self.call_sid, audio_url)
                    except Exception as e:
                        print("Final TTS/play error:", e)

                # Guardamos toda la respuesta completa en el historial
                self.conversation_history.append({"role": "assistant", "content": response_text})

            except Exception as e:
                print("LLM streaming error:", e)
                response_text = "Lo siento, ha ocurrido un error procesando tu petición."

            print(f"[{self.call_sid}] LLM: {response_text[:120]}")

            # Marcamos como terminado el procesamiento del turno
            self.processing = False

    # Método que se ejecuta cuando la sesión se desconecta
    async def on_disconnect(self):
        await self._process_turn()  # Procesamos lo que quede pendiente
        print(f"Session {self.call_sid} disconnected.")


# Clase que gestiona todas las sesiones (puede haber varias llamadas al mismo tiempo)
class SessionManager:
    def __init__(self):
        self.sessions = {}  # Diccionario: call_sid → Session

    # Crear una nueva sesión para una llamada
    def create_session(self, call_sid, websocket):
        s = Session(call_sid, websocket)
        self.sessions[call_sid] = s
        return s

    # Recuperar una sesión existente
    def get_session(self, call_sid):
        return self.sessions.get(call_sid)
