#utils.py
# Módulo con funciones auxiliares para el procesamiento de audio y llamadas a APIs.

#1-Audio: decodifica, acumula y convierte PCM → WAV.
#2-VAD: detecta si hay voz activa en un fragmento.
#3-ASR: llama a OpenAI Whisper para transcribir el audio.
#4-LLM: llama a ChatGPT para generar respuesta en texto.
#5-TTS: genera audio a partir del texto usando OpenAI TTS.
#6-Twilio: reproduce audio directamente en la llamada.


# Librerías estándar
import base64  # Para decodificar audio en base64
import os      # Para operaciones con archivos
import uuid    # Para generar nombres únicos de archivos
import requests  # Para llamadas HTTP a la API de OpenAI
import subprocess  # Para ejecutar comandos de ffmpeg
from dotenv import load_dotenv  # Para cargar variables de entorno
from twilio.rest import Client  # Cliente REST de Twilio
import webrtcvad  # Para detección de voz (VAD)

# Cargar variables de entorno desde .env
load_dotenv()

# Cargar claves de OpenAI y Twilio desde .env
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")

# Inicializamos el cliente de Twilio
twilio_client = Client(TWILIO_SID, TWILIO_TOKEN)


# Función para decodificar el audio enviado por Twilio (base64 → bytes PCM)
def decode_twilio_media_frame(payload_b64: str) -> bytes:
    return base64.b64decode(payload_b64)


# Función para añadir datos PCM al buffer de audio
def append_pcm_to_buffer(buffer: bytearray, pcm: bytes):
    buffer.extend(pcm)


# Función para guardar audio PCM en un archivo WAV usando ffmpeg
def save_raw_pcm_to_wav(raw_buffer: bytes, in_rate=8000, out_rate=16000) -> str:
    raw_path = f"tmp_{uuid.uuid4()}.raw"  # Archivo temporal PCM
    wav_path = f"tmp_{uuid.uuid4()}.wav"  # Archivo WAV resultante
    with open(raw_path, "wb") as f:
        f.write(raw_buffer)  # Guardamos el PCM en disco

    # Comando ffmpeg para convertir PCM crudo a WAV 16kHz mono
    cmd = [
        "ffmpeg", "-y",
        "-f", "s16le", "-ar", str(in_rate), "-ac", "1", "-i", raw_path,
        "-ar", str(out_rate), "-ac", "1", wav_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # Ejecutamos ffmpeg
    os.remove(raw_path)  # Eliminamos el archivo temporal
    return wav_path  # Devolvemos la ruta del WAV


# Inicializamos el VAD (Voice Activity Detection) de WebRTC
_vad = webrtcvad.Vad(2)  # Agresividad: 0-3, 2 es nivel medio


# Función para detectar si hay voz en un fragmento de PCM
def is_speech_present(pcm_bytes: bytes, sample_rate=8000, frame_ms=30):
    try:
        # Calculamos cuántos bytes corresponden a frame_ms milisegundos
        frame_bytes = int(sample_rate * (frame_ms / 1000.0) * 2)  # 2 bytes por muestra
        if len(pcm_bytes) < frame_bytes:
            return False  # Si el buffer es muy pequeño, no hay voz
        frame = pcm_bytes[:frame_bytes]
        return _vad.is_speech(frame, sample_rate)  # Retorna True si hay voz
    except Exception:
        return False


# Función para transcribir un archivo WAV usando OpenAI Whisper
def transcribe_wav(wav_path: str) -> str:
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}"}
    with open(wav_path, "rb") as f:
        files = {"file": f}
        data = {"model": "whisper-1", "language": "es"}  # Configuración de transcripción
        r = requests.post(url, headers=headers, files=files, data=data)  # Llamada a la API
    if r.status_code != 200:
        raise Exception(f"Transcription failed: {r.status_code} {r.text}")
    j = r.json()
    try:
        os.remove(wav_path)  # Eliminamos el WAV temporal
    except:
        pass
    return j.get("text", "")  # Retornamos el texto transcrito


# Función para enviar historial de conversación a ChatGPT y obtener respuesta
def ask_chatgpt_stream(history):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini",  # Modelo de lenguaje
        "messages": history,      # Historial de mensajes user/assistant
        "max_tokens": 250,        # Limite de tokens de la respuesta
        "temperature": 0.2        # Controla creatividad/respuestas
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)  # Llamada a la API
    if r.status_code != 200:
        raise Exception(f"LLM failed: {r.status_code} {r.text}")
    j = r.json()
    return j["choices"][0]["message"]["content"].strip()  # Retornamos texto limpio


# Función para convertir texto a voz usando OpenAI TTS
def synthesize_tts(text: str) -> str:
    url = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o-mini-tts", "voice": "alloy", "input": text}  # Configuración de TTS
    r = requests.post(url, headers=headers, json=payload, stream=True, timeout=30)
    if r.status_code != 200:
        raise Exception(f"TTS failed: {r.status_code} {r.text}")
    filename = f"{uuid.uuid4()}.mp3"  # Nombre único para el archivo de audio
    path = os.path.join("static", "audio", filename)  # Carpeta de salida
    with open(path, "wb") as f:
        for chunk in r.iter_content(8192):  # Guardamos los chunks que llegan en streaming
            f.write(chunk)
    return filename  # Retornamos el nombre del archivo generado


# Función para reproducir un audio en la llamada usando Twilio (actualiza TwiML)
def twilio_redirect_play(call_sid: str, audio_url: str):
    # Generamos TwiML que reproduce el audio
    twiml = f"<Response><Play>{audio_url}</Play></Response>"
    # Actualizamos la llamada en curso para reproducir el archivo
    twilio_client.calls(call_sid).update(twiml=twiml)
