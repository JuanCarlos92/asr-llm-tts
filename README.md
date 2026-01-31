# ASR-LLM-TTS

ASR-LLM-TTS es un proyecto de automatización con inteligencia artificial que procesa llamadas telefónicas en tiempo real. Utiliza **Python** con **FastAPI**, integra **Whisper** para transcripción de voz, **GPT (LLM)** para generar respuestas y **TTS** para convertir texto en voz.

Este proyecto permite recibir llamadas vía **Twilio**, transcribir la voz del usuario, generar respuestas inteligentes y reproducirlas en tiempo real.

---

## 🔹 Funcionalidades

1. Recibe audio desde Twilio y lo acumula en un buffer.
2. Cuando hay suficiente audio, lo transcribe con Whisper.
3. Envía el texto a GPT (LLM) y obtiene respuesta en lenguaje natural.
4. Convierte la respuesta en voz (TTS) y genera un archivo MP3/WAV.
5. Reproduce el audio al usuario en la llamada vía Twilio.
6. Soporte opcional para **streaming parcial de TTS** mientras llega la respuesta.

---

## ⚙️ Tecnologías usadas

- **Python 3.11+**
- **FastAPI**: framework para el servidor y WebSocket
- **Twilio API**: para llamadas telefónicas y transmisión de audio
- **OpenAI Whisper**: transcripción de audio
- **OpenAI GPT-4o-mini**: generación de respuestas
- **OpenAI TTS**: conversión de texto a voz
- **webrtcvad**: detección de voz activa (VAD)
- **dotenv**: gestión de variables de entorno
- **ffmpeg**: conversión de audio PCM → WAV/MP3
- **ngrok** (opcional): exponer servidor local a Internet

---

## 📁 Estructura del proyecto

```
asr-llm-tts/
├─ main.py               # Servidor FastAPI, endpoints HTTP y WebSocket
├─ session.py            # Gestión de sesiones de llamadas y procesamiento ASR → LLM → TTS
├─ utils.py              # Funciones auxiliares: decodificación, transcripción, GPT, TTS, Twilio
├─ static/
│  └─ audio/             # Carpeta donde se guardan los audios generados
├─ .env                  # Variables de entorno (no subir a GitHub)
├─ .gitignore            # Ignora .env, audios generados y caches
└─ README.md
```

---

## 🛠 Instalación

1. Clonar el repositorio:

```bash
git clone https://github.com/tu-usuario/asr-llm-tts.git
cd asr-llm-tts
```

2. Crear un entorno virtual:

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Instalar dependencias:

```bash
pip install -r requirements.txt
```

> Nota: `requirements.txt` debe incluir:
> ```
> fastapi
> uvicorn
> requests
> python-dotenv
> twilio
> webrtcvad
> ```

4. Instalar **ffmpeg** en tu sistema:

- **Linux**: `sudo apt install ffmpeg`
- **MacOS**: `brew install ffmpeg`
- **Windows**: [Descargar binarios](https://ffmpeg.org/download.html)

---

## ⚙️ Configuración (.env)

Crea un archivo `.env` en la raíz del proyecto con las siguientes variables:

```env
# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_NUMBER=+34xxxxxxxxx

# OpenAI
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Host y rutas
NGROK_HOST=https://xxxx.ngrok.io    # opcional, solo desarrollo local
PUBLIC_HOST=https://tudominio.com   # dominio donde se expondrán audios
MEDIA_WS_PATH=/media                # ruta para el WebSocket de Twilio

# Puerto del servidor
PORT=8000
```

> ⚠️ Nunca subas tu `.env` a GitHub.

### `.gitignore` recomendado:

```
.env
/static/audio/*.mp3
/static/audio/*.wav
__pycache__/
*.pyc
*.pyo
logs/
tmp/
```

---

## 🚀 Ejecución

Ejecuta el servidor con Uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- Para pruebas locales con Twilio, usa **ngrok** para exponer el puerto 8000:

```bash
ngrok http 8000
```

- Configura la URL de **Incoming Call** en Twilio con:

```
https://xxxx.ngrok.io/incoming
```

---

## 📡 Flujo de la llamada

1. Usuario llama al número de Twilio.
2. Twilio transmite el audio al endpoint `/media/{call_sid}`.
3. `session.py` acumula audio → lo transcribe con Whisper.
4. Texto transcrito → GPT → respuesta de texto.
5. Respuesta → TTS → se reproduce en la llamada.
6. Repetir mientras dura la conversación.

---

## 🔐 Buenas prácticas

- **Variables sensibles** en `.env` → nunca subir a GitHub.
- **Audios generados** no subir → incluir en `.gitignore`.
- Revisar logs de errores para detectar problemas de TTS o LLM.

---

## 📌 Notas

- El proyecto soporta **streaming de LLM** y TTS parcial.
- Compatible con **multisesión** → varias llamadas simultáneas.
- Ideal para bots de atención telefónica, asistentes automáticos o pruebas de AI conversacional.

##Estado del proyecto:
El proyecto actualmente funciona, permitiendo recibir llamadas, transcribirlas y generar respuestas TTS, pero ##la integración completa con todas las APIs necesarias aún está pendiente.

---

## ⚡ Licencia

MIT License © Juan Carlos Filter Martín
