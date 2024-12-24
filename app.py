import streamlit as st
import os
import json
import logging
import time
from google.cloud import texttospeech, storage
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import tempfile
import requests
from io import BytesIO
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)

# Configuración de credenciales GCP
try:
    credentials_str = os.environ.get("GOOGLE_CREDENTIALS")
    if credentials_str:
        credentials = json.loads(credentials_str)
        with open("/app/google_credentials.json", "w") as f:
            json.dump(credentials, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/google_credentials.json"
    else:
        raise KeyError("Variable de entorno GOOGLE_CREDENTIALS no configurada")
except KeyError as e:
    logging.error(f"Error al cargar credenciales: {str(e)}")
    st.error(f"Error al cargar credenciales: {str(e)}")

# Configuración de voces
VOCES_DISPONIBLES = {
    'es-ES-Journey-D': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Journey-F': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Journey-O': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Neural2-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-E': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-F': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Polyglot-1': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Standard-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Standard-C': texttospeech.SsmlVoiceGender.FEMALE
}
def dividir_texto(texto, max_caracteres=5000):
    palabras = texto.split()
    chunks = []
    chunk_actual = []
    longitud_actual = 0
    
    for palabra in palabras:
        if longitud_actual + len(palabra) > max_caracteres:
            chunks.append(' '.join(chunk_actual))
            chunk_actual = [palabra]
            longitud_actual = len(palabra)
        else:
            chunk_actual.append(palabra)
            longitud_actual += len(palabra)
    
    if chunk_actual:
        chunks.append(' '.join(chunk_actual))
    return chunks

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def sintetizar_voz_con_reintento(cliente, texto_entrada, voz, config_audio):
    return cliente.synthesize_speech(
        input=texto_entrada,
        voice=voz,
        audio_config=config_audio
    )

def create_text_image(text, size=(1280, 320), font_size=30, line_height=40):
    img = Image.new('RGB', size, 'black')
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
    except:
        font = ImageFont.load_default()

    words = text.split()
    lines = []
    current_line = []

    for word in words:
        current_line.append(word)
        test_line = ' '.join(current_line)
        left, top, right, bottom = draw.textbbox((0, 0), test_line, font=font)
        if right > size[0] - 60:
            current_line.pop()
            lines.append(' '.join(current_line))
            current_line = [word]
    lines.append(' '.join(current_line))

    total_height = len(lines) * line_height
    y = (size[1] - total_height) // 2

    for line in lines:
        left, top, right, bottom = draw.textbbox((0, 0), line, font=font)
        x = (size[0] - (right - left)) // 2
        draw.text((x, y), line, font=font, fill="white")
        y += line_height

    return np.array(img)

def create_subscription_image(logo_url, size=(1280, 320), font_size=60):
    img = Image.new('RGB', size, (255, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        font2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size//2)
    except:
        font = ImageFont.load_default()
        font2 = ImageFont.load_default()

    try:
        response = requests.get(logo_url)
        response.raise_for_status()
        logo_img = Image.open(BytesIO(response.content)).convert("RGBA")
        logo_img = logo_img.resize((100,100))
        logo_position = (20,20)
        img.paste(logo_img, logo_position, logo_img)
    except Exception as e:
        logging.error(f"Error al cargar el logo: {str(e)}")

    text1 = "¡SUSCRÍBETE A LECTOR DE SOMBRAS!"
    left1, top1, right1, bottom1 = draw.textbbox((0, 0), text1, font=font)
    x1 = (size[0] - (right1 - left1)) // 2
    y1 = (size[1] - (bottom1 - top1)) // 2 - (bottom1 - top1) // 2 - 20
    draw.text((x1, y1), text1, font=font, fill="white")

    text2 = "Dale like y activa la campana 🔔"
    left2, top2, right2, bottom2 = draw.textbbox((0, 0), text2, font=font2)
    x2 = (size[0] - (right2 - left2)) // 2
    y2 = (size[1] - (bottom2 - top2)) // 2 + (bottom1 - top1) // 2 + 20
    draw.text((x2, y2), text2, font=font2, fill="white")

    return np.array(img)

def create_simple_video(texto, nombre_salida, voz, logo_url, progress_bar=None):
    SEGMENT_SIZE = 500
    VIDEO_HEIGHT = 320
    VIDEO_BITRATE = "1500k"
    
    archivos_temp = []
    clips_audio = []
    clips_finales = []
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            logging.info("Iniciando proceso de creación de video...")
            chunks_texto = dividir_texto(texto)
            client = texttospeech.TextToSpeechClient()
            tiempo_acumulado = 0
            
            total_chunks = len(chunks_texto)
            for i, chunk in enumerate(chunks_texto):
                if progress_bar:
                    progress_bar.progress((i + 1) / (total_chunks + 1))
                
                synthesis_input = texttospeech.SynthesisInput(text=chunk)
                voice = texttospeech.VoiceSelectionParams(
                    language_code="es-ES",
                    name=voz,
                    ssml_gender=VOCES_DISPONIBLES[voz]
                )
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3
                )
                
                response = sintetizar_voz_con_reintento(client, synthesis_input, voice, audio_config)
                
                temp_audio_filename = os.path.join(temp_dir, f"temp_audio_{i}.mp3")
                archivos_temp.append(temp_audio_filename)
                
                with open(temp_audio_filename, "wb") as out:
                    out.write(response.audio_content)
                
                audio_clip = AudioFileClip(temp_audio_filename)
                clips_audio.append(audio_clip)
                
                duracion = audio_clip.duration
                text_img = create_text_image(chunk, size=(1280, VIDEO_HEIGHT))
                txt_clip = (ImageClip(text_img)
                          .set_start(tiempo_acumulado)
                          .set_duration(duracion)
                          .set_position('center'))
                
                video_segment = txt_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
                clips_finales.append(video_segment)
                
                tiempo_acumulado += duracion
                time.sleep(0.2)

            subscribe_img = create_subscription_image(logo_url, size=(1280, VIDEO_HEIGHT))
            subscribe_clip = (ImageClip(subscribe_img)
                            .set_start(tiempo_acumulado)
                            .set_duration(5)
                            .set_position('center'))
            
            clips_finales.append(subscribe_clip)
            
            video_final = concatenate_videoclips(clips_finales, method="compose")
            output_path = os.path.join(temp_dir, f"{nombre_salida}.mp4")
            
            video_final.write_videofile(
                output_path,
                fps=24,
                codec='libx264',
                audio_codec='aac',
                preset='ultrafast',
                bitrate=VIDEO_BITRATE,
                threads=4
            )
            
            # Leer el archivo de video
            with open(output_path, 'rb') as video_file:
                video_bytes = video_file.read()
            
            return True, "Video generado exitosamente", video_bytes
            
        except Exception as e:
            logging.error(f"Error en la creación de video: {str(e)}")
            return False, str(e), None

def main():
    st.title("Creador de Videos Automático")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
    logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"
    
    if uploaded_file:
        texto = uploaded_file.read().decode("utf-8")
        if len(texto) > 10000:
            st.warning("Texto largo detectado - el procesamiento puede tomar más tiempo")
            
        nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
        
        if st.button("Generar Video"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            with st.spinner('Generando video...'):
                success, message, video_bytes = create_simple_video(
                    texto, 
                    nombre_salida, 
                    voz_seleccionada, 
                    logo_url,
                    progress_bar
                )
                
                if success and video_bytes:
                    st.success(message)
                    st.download_button(
                        label="Descargar Video",
                        data=video_bytes,
                        file_name=f"{nombre_salida}.mp4",
                        mime="video/mp4"
                    )
                else:
                    st.error(f"Error al generar video: {message}")

if __name__ == "__main__":
    main()
