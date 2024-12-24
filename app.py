import streamlit as st
import os
import json
import logging
import time
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import tempfile
import requests
from io import BytesIO

logging.basicConfig(level=logging.INFO)

# Obtener credenciales de GCP de las variables de entorno
try:
    credentials_str = os.environ.get("GOOGLE_CREDENTIALS")
    if credentials_str:
        credentials = json.loads(credentials_str)
        logging.info("Credenciales de Google Cloud cargadas desde variables de entorno.")
        with open("/app/google_credentials.json", "w") as f:
            json.dump(credentials, f)

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/google_credentials.json"
        logging.info("Variable de entorno GOOGLE_APPLICATION_CREDENTIALS establecida.")
    else:
        raise KeyError("Variable de entorno GOOGLE_CREDENTIALS no está configurada")
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

# Función de creación de texto
def create_text_image(text, size=(1280, 360), font_size=30, line_height=40):
    img = Image.new('RGB', size, 'black')
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)

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

# Nueva función para crear la imagen de suscripción
def create_subscription_image(logo_url,size=(1280, 720), font_size=60):
    img = Image.new('RGB', size, (255, 0, 0))  # Fondo rojo
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)

    # Cargar logo del canal
    try:
        response = requests.get(logo_url)
        response.raise_for_status()
        logo_img = Image.open(BytesIO(response.content)).convert("RGBA")
        logo_img = logo_img.resize((100,100))
        logo_position = (20,20)
        img.paste(logo_img,logo_position,logo_img)
    except Exception as e:
        logging.error(f"Error al cargar el logo: {str(e)}")
        
    text1 = "¡SUSCRÍBETE A LECTOR DE SOMBRAS!"
    left1, top1, right1, bottom1 = draw.textbbox((0, 0), text1, font=font)
    x1 = (size[0] - (right1 - left1)) // 2
    y1 = (size[1] - (bottom1 - top1)) // 2 - (bottom1 - top1) // 2 - 20
    draw.text((x1, y1), text1, font=font, fill="white")
    
    font2 = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size//2)
    text2 = "Dale like y activa la campana 🔔"
    left2, top2, right2, bottom2 = draw.textbbox((0, 0), text2, font=font2)
    x2 = (size[0] - (right2 - left2)) // 2
    y2 = (size[1] - (bottom2 - top2)) // 2 + (bottom1 - top1) // 2 + 20
    draw.text((x2,y2), text2, font=font2, fill="white")

    return np.array(img)

# Función de creación de video
def create_simple_video(texto, nombre_salida, voz, logo_url):
    archivos_temp = []
    clips_audio = []
    clips_finales = []
    temp_dir = "/tmp" # Usando /tmp como directorio temporal
    video_final = None # inicializa video_final a None
    output_path = os.path.join(temp_dir, f"{nombre_salida}.mp4") # Ruta de salida del video en /tmp
    SEGMENT_SIZE = 200
    VIDEO_HEIGHT = 360

    try:
        logging.info("Iniciando proceso de creación de video...")

        # Asegurarse de que el directorio /tmp exista
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir, exist_ok=True)
            logging.info(f"Directorio {temp_dir} creado")

         # Dar permisos de escritura a /tmp si es necesario
        os.chmod(temp_dir, 0o777)
        logging.info(f"Permisos del directorio {temp_dir} establecidos a 777")

        frases = [f.strip() + "." for f in texto.split('.') if f.strip()]
        client = texttospeech.TextToSpeechClient()
        
        tiempo_acumulado = 0
        
        # Agrupamos frases en segmentos
        segmentos_texto = []
        segmento_actual = ""
        for frase in frases:
            if len(segmento_actual) + len(frase) < SEGMENT_SIZE:
                segmento_actual += " " + frase
            else:
                segmentos_texto.append(segmento_actual.strip())
                segmento_actual = frase
        segmentos_texto.append(segmento_actual.strip())
        
        for i, segmento in enumerate(segmentos_texto):
            logging.info(f"Procesando segmento {i+1} de {len(segmentos_texto)}")
            
            synthesis_input = texttospeech.SynthesisInput(text=segmento)
            voice = texttospeech.VoiceSelectionParams(
                language_code="es-ES",
                name=voz,
                ssml_gender=VOCES_DISPONIBLES[voz]
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3
            )
            
            retry_count = 0
            max_retries = 3
            
            while retry_count <= max_retries:
              try:
                response = client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config
                )
                break
              except Exception as e:
                  logging.error(f"Error al solicitar audio (intento {retry_count + 1}): {str(e)}")
                  if "429" in str(e):
                    retry_count +=1
                    time.sleep(2**retry_count)
                  else:
                     raise Exception(f"Error al solicitar audio: {str(e)}")
            
            if retry_count > max_retries:
                raise Exception("Maximos intentos de reintento alcanzado")
            
            # Usar io.BytesIO para guardar el audio en memoria
            temp_audio_buffer = BytesIO(response.audio_content)
            temp_audio_filename = os.path.join(temp_dir, f"temp_audio_{i}.mp3")
            archivos_temp.append(temp_audio_filename)

            try:
               with open(temp_audio_filename, 'wb') as out_file:
                   out_file.write(temp_audio_buffer.getvalue())
               os.chmod(temp_audio_filename, 0o777)
               logging.info(f"Archivo temporal de audio guardado en {temp_audio_filename}")
            except Exception as e:
                logging.error(f"Error al crear el archivo de audio temporal {temp_audio_filename}: {str(e)}")
                raise
            
            audio_clip = None
            try:
                audio_clip = AudioFileClip(temp_audio_filename) # Usa el archivo temporal
                clips_audio.append(audio_clip)
                logging.info(f"Audio cargado desde archivo temporal: {temp_audio_filename}")
            except Exception as e:
                logging.error(f"Error al cargar el archivo de audio {temp_audio_filename}: {str(e)}")
                raise

            duracion = audio_clip.duration
            
            text_img = create_text_image(segmento, size=(1280, VIDEO_HEIGHT)) # Reducir altura de imagen
            txt_clip = (ImageClip(text_img)
                      .set_start(tiempo_acumulado)
                      .set_duration(duracion)
                      .set_position('center'))
            
            video_segment = txt_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
            clips_finales.append(video_segment)
            
            tiempo_acumulado += duracion
            time.sleep(0.2)

        # Añadir clip de suscripción
        subscribe_img = create_subscription_image(logo_url, size=(1280, VIDEO_HEIGHT))
        duracion_subscribe = 5

        subscribe_clip = (ImageClip(subscribe_img)
                        .set_start(tiempo_acumulado)
                        .set_duration(duracion_subscribe)
                        .set_position('center'))

        clips_finales.append(subscribe_clip)

        video_final = concatenate_videoclips(clips_finales, method="compose")

        logging.info(f"Escribiendo video a {output_path}")

        video_final.write_videofile(
            output_path, # Guarda el video en /tmp
            fps=24,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            bitrate="2000k", # Comprimir el video
            threads=4
        )
        
        # Limpiar los clips
        for clip in clips_audio:
            try:
                clip.close()
            except:
                pass
        
        for clip in clips_finales:
            try:
                clip.close()
            except:
                pass
        if video_final:
           video_final.close()
        
        # Limpiar archivos temporales de audio
        for temp_file in archivos_temp:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    logging.info(f"Archivo temporal de audio eliminado {temp_file}")
            except:
               logging.error(f"Error al eliminar el archivo de audio {temp_file}")

        # Leer el archivo en memoria (generador)
        def video_generator():
            try:
               logging.info(f"Leyendo archivo de video {output_path}")
               with open(output_path, 'rb') as file:
                  while True:
                     chunk = file.read(1024*1024) # Lee chunks de 1MB
                     if not chunk:
                        break
                     yield chunk
            except Exception as e:
               logging.error(f"Error al leer el archivo de video: {str(e)}")
               raise

        os.chmod(output_path, 0o777) # Establecer permisos
        logging.info(f"Permisos del archivo {output_path} establecidos a 777")

        # Verificar tamaño del archivo
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logging.info(f"Tamaño del archivo de video {output_path}: {file_size} bytes")
        else:
             logging.error(f"No se encontró el archivo de video {output_path}")
             raise Exception(f"No se encontró el archivo de video {output_path}")

        return True, "Video generado exitosamente", video_generator(), output_path  # Devuelve el generador y la ruta del video
        
    except Exception as e:
        logging.error(f"Error en la creación de video: {str(e)}")
        # Limpiar los clips
        for clip in clips_audio:
            try:
                clip.close()
            except:
                pass
                
        for clip in clips_finales:
            try:
                clip.close()
            except:
                pass
        
        if video_final:
           video_final.close()
            
        # Limpiar archivos temporales de audio
        for temp_file in archivos_temp:
            try:
                if os.path.exists(temp_file):
                   os.remove(temp_file)
                   logging.info(f"Archivo temporal de audio eliminado {temp_file}")
            except:
               logging.error(f"Error al eliminar el archivo de audio {temp_file}")
        
        return False, str(e), None, None

def main():
    st.title("Creador de Videos Automático")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
    logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"
    
    try:
        if uploaded_file:
            texto = uploaded_file.read().decode("utf-8")
            nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
            
            if st.button("Generar Video"):
                with st.spinner('Generando video...'):
                    success, message, video_generator, video_path = create_simple_video(texto, nombre_salida, voz_seleccionada, logo_url)
                    if success:
                      st.success(message)
                      if video_generator:
                        st.video(video_generator) # Muestra el video directamente desde el generador
                        st.download_button(label="Descargar video", file_name=f"{nombre_salida}.mp4", data=b''.join(video_generator))
                      else:
                          st.error("No se pudo leer el contenido del video")

                      # Elimina el archivo del /tmp después de la descarga
                      try:
                           if video_path and os.path.exists(video_path):
                             os.remove(video_path)
                             logging.info(f"Archivo temporal eliminado: {video_path}")
                           else:
                             logging.warning(f"No se pudo eliminar el archivo {video_path}, puede que no exista")
                      except Exception as e:
                           logging.error(f"Error al eliminar el archivo temporal de video: {str(e)}")
                    else:
                        st.error(f"Error al generar video: {message}")

        if st.session_state.get("video_path"):
            st.markdown(f'<a href="https://www.youtube.com/upload" target="_blank">Subir video a YouTube</a>', unsafe_allow_html=True)

        # Limpiar archivos .mp4 del /tmp al finalizar, por seguridad
        for filename in os.listdir('/tmp'):
            if filename.endswith('.mp4'):
                file_path = os.path.join('/tmp', filename)
                try:
                   os.remove(file_path)
                   logging.info(f"Archivo mp4 limpiado al finalizar {file_path}")
                except Exception as e:
                    logging.error(f"Error al limpiar el archivo mp4 {file_path} : {str(e)}")

    except Exception as e:
        logging.error(f"Error en la función main: {str(e)}")
        st.error(f"Error inesperado: {str(e)}")


if __name__ == "__main__":
    # Inicializar session state
    if "video_path" not in st.session_state:
        st.session_state.video_path = None
    main()
