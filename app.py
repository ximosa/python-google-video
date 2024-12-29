import streamlit as st
import os
import json
import logging
import time
import re
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import requests
from io import BytesIO
import tempfile

logging.basicConfig(level=logging.INFO)

# Configuración de credenciales GCP
try:
    credentials_str = os.environ.get("GOOGLE_CREDENTIALS")
    if credentials_str:
        credentials = json.loads(credentials_str)
        with open("/tmp/google_credentials.json", "w") as f:
            json.dump(credentials, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/tmp/google_credentials.json"
    else:
        if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
           raise KeyError("Variable de entorno GOOGLE_APPLICATION_CREDENTIALS no configurada")
except KeyError as e:
    logging.error(f"Error al cargar credenciales: {str(e)}")
    st.error(f"Error al cargar credenciales: {str(e)}")


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

def create_text_image(text, size=(1280, 360), font_size=30, line_height=40):
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

def create_subscription_image(logo_url, size=(1280, 720), font_size=60):
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
    draw.text((x2,y2), text2, font=font2, fill="white")

    return np.array(img)

def split_text_into_segments(text, max_segment_length=300):
    frases = [f.strip() + "." for f in text.split('.') if f.strip()]
    segments = []
    current_segment = ""
    for frase in frases:
        if len(current_segment) + len(frase) <= max_segment_length:
            current_segment += " " + frase
        else:
            segments.append(current_segment.strip())
            current_segment = frase
    if current_segment:
        segments.append(current_segment.strip())
    return segments

def sanitize_filename(filename):
    # Elimina caracteres no válidos
    return re.sub(r'[<>:"/\\|?*]', '', filename).strip()

def generate_video(texto, nombre_salida, voz, logo_url):
        archivos_temp = []
        clips_audio = []
        clips_finales = []
        temp_dir = "/tmp"
        
        try:
            logging.info("Iniciando proceso de creación de video...")
            segments = split_text_into_segments(texto)
            client = texttospeech.TextToSpeechClient()
            total_segments = len(segments)
            
            tiempo_acumulado = 0
            for i, segment in enumerate(segments):
                logging.info(f"Procesando segmento {i+1} de {total_segments}")
                
                synthesis_input = texttospeech.SynthesisInput(text=segment)
                voice = texttospeech.VoiceSelectionParams(
                    language_code="es-ES",
                    name=voz,
                    ssml_gender=VOCES_DISPONIBLES[voz]
                )
                audio_config = texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3
                )
                
                response = client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config
                )
                
                temp_filename = os.path.join(temp_dir, f"temp_audio_{i}.mp3")
                archivos_temp.append(temp_filename)
                
                with open(temp_filename, "wb") as out:
                    out.write(response.audio_content)
                
                audio_clip = AudioFileClip(temp_filename)
                clips_audio.append(audio_clip)
                
                duracion = audio_clip.duration
                text_img = create_text_image(segment)
                txt_clip = (ImageClip(text_img)
                        .set_start(tiempo_acumulado)
                        .set_duration(duracion)
                        .set_position('center'))
                
                video_segment = txt_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
                clips_finales.append(video_segment)
                
                tiempo_acumulado += duracion
                time.sleep(0.2)

            subscribe_img = create_subscription_image(logo_url)
            duracion_subscribe = 5
            
            subscribe_clip = (ImageClip(subscribe_img)
                            .set_start(tiempo_acumulado)
                            .set_duration(duracion_subscribe)
                            .set_position('center'))
            
            clips_finales.append(subscribe_clip)
            
            video_final = concatenate_videoclips(clips_finales, method="compose")
            
            
            video_buffer = BytesIO()
            video_final.write_videofile(
                video_buffer,
                fps=24,
                codec='libx264',
                audio_codec='aac',
                preset='ultrafast',
                threads=2,
                logger = None
            )
            video_buffer.seek(0)
            video_bytes = video_buffer.read()
        
            video_final.close()
            for clip in clips_audio + clips_finales:
                try:
                    clip.close()
                except Exception as e:
                    logging.error(f"Error al cerrar clip: {str(e)}")
            
            for temp_file in archivos_temp:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logging.error(f"Error al eliminar archivo temporal {temp_file}: {str(e)}")
            
            logging.info("create_simple_video - Finaliza con exito")
            return True, video_bytes

        except Exception as e:
            logging.error(f"Error en la creación de video: {str(e)}")
            for clip in clips_audio + clips_finales:
                try:
                    clip.close()
                except Exception as e:
                    logging.error(f"Error al cerrar clip: {str(e)}")
            
            for temp_file in archivos_temp:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    logging.error(f"Error al eliminar archivo temporal {temp_file}: {str(e)}")
            
            return False, str(e)



def main():
    st.title("Creador de Videos Automático")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
    nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
    logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"
    
    if uploaded_file:
        texto = uploaded_file.read().decode("utf-8")
        if st.button("Generar Video"):
            with st.spinner('Generando video...'):
                logging.info("Generar Video - boton presionado")
                
                 # Sanitiza el nombre del archivo
                nombre_archivo_sanitizado = sanitize_filename(nombre_salida)
                 
                success, video_bytes = generate_video(texto, nombre_archivo_sanitizado + ".mp4", voz_seleccionada, logo_url)
                
                if success:
                    logging.info("Generar Video - video generado con exito")
                    st.success("Video generado exitosamente")
                    st.video(video_bytes)
                    st.download_button(label="Descargar video", data=video_bytes, file_name=f"{nombre_archivo_sanitizado}.mp4", mime="video/mp4")
                      
                else:
                    logging.error(f"Generar Video - Error: {video_bytes}")
                    st.error(f"Error al generar video: {video_bytes}")

if __name__ == "__main__":
    main()
