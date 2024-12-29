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
from google.cloud import storage

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

# Configuración de voces
VOCES_DISPONIBLES = {
    'es-ES-Standard-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Standard-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-E': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Standard-F': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Neural2-A': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Neural2-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-E': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Neural2-F': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Polyglot-1': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Studio-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Studio-F': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Wavenet-B': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Wavenet-C': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Wavenet-D': texttospeech.SsmlVoiceGender.FEMALE,
    'es-ES-Wavenet-E': texttospeech.SsmlVoiceGender.MALE,
    'es-ES-Wavenet-F': texttospeech.SsmlVoiceGender.FEMALE,
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
def create_simple_video(texto, nombre_salida, voz, logo_url, bucket_name="datosblog-4095b.appspot.com"):
    clips_audio = []
    clips_finales = []
    video_temp_file = None
    audio_temp_files = []
    try:
        logging.info("Iniciando proceso de creación de video...")
        frases = [f.strip() + "." for f in texto.split('.') if f.strip()]
        client = texttospeech.TextToSpeechClient()
        
        tiempo_acumulado = 0
        
        # Agrupamos frases en segmentos
        segmentos_texto = []
        segmento_actual = ""
        for frase in frases:
          if len(segmento_actual) + len(frase) < 300:
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
                    raise
            
            if retry_count > max_retries:
                raise Exception("Maximos intentos de reintento alcanzado")
            
            # Usar tempfile para el archivo de audio
            try:
                temp_audio_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                temp_audio_file.write(response.audio_content)
                audio_clip = AudioFileClip(temp_audio_file.name)
                clips_audio.append(audio_clip)
                audio_temp_files.append(temp_audio_file.name)
                duracion = audio_clip.duration
                
                text_img = create_text_image(segmento)
                txt_clip = (ImageClip(text_img)
                        .set_start(tiempo_acumulado)
                        .set_duration(duracion)
                        .set_position('center'))
                
                video_segment = txt_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
                clips_finales.append(video_segment)
                
                tiempo_acumulado += duracion
                time.sleep(0.2)
            except Exception as e:
              logging.error(f"Error al crear archivo de audio temporal o clip: {str(e)}")
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
              if temp_audio_file:
                try:
                  os.close(os.open(temp_audio_file.name, os.O_RDONLY))
                  os.remove(temp_audio_file.name)
                except:
                    pass
              raise
        # Añadir clip de suscripción
        try:
            subscribe_img = create_subscription_image(logo_url) # Usamos la función creada
            duracion_subscribe = 5

            subscribe_clip = (ImageClip(subscribe_img)
                            .set_start(tiempo_acumulado)
                            .set_duration(duracion_subscribe)
                            .set_position('center'))

            clips_finales.append(subscribe_clip)
        except Exception as e:
            logging.error(f"Error al crear imagen de suscripcion: {str(e)}")
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
            raise
        
        try:
            video_final = concatenate_videoclips(clips_finales, method="compose")
        except Exception as e:
          logging.error(f"Error al concatenar clips: {str(e)}")
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
          raise
        # Usar tempfile para el archivo de video
        try:
           video_temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
           video_final.write_videofile(
                video_temp_file.name,
                fps=24,
                codec='libx264',
                audio_codec='aac',
                preset='ultrafast',
                threads=4
            )
        
           video_final.close()
        
           for clip in clips_audio:
             clip.close()
        
           for clip in clips_finales:
             clip.close()
           
           logging.info(f"Video creado correctamente en: {video_temp_file.name}")
           
           # Subir a Google Cloud Storage
           try:
             storage_client = storage.Client()
             bucket = storage_client.bucket(bucket_name)
             blob = bucket.blob(f"videos/{nombre_salida}.mp4")
             logging.info(f"Subiendo video a gs://{bucket_name}/videos/{nombre_salida}.mp4")
             blob.upload_from_filename(video_temp_file.name)
             logging.info(f"Video subido correctamente a gs://{bucket_name}/videos/{nombre_salida}.mp4")
             blob.make_public()
             url_video = blob.public_url
             logging.info(f"URL del video: {url_video}")
             return True, "Video generado exitosamente", url_video, audio_temp_files
           except Exception as e:
             logging.error(f"Error al subir a Cloud Storage: {str(e)}")
             return False, f"Error al subir a Cloud Storage: {str(e)}", None, None
        except Exception as e:
           logging.error(f"Error al crear el video: {str(e)}")
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
           if video_temp_file:
                try:
                  os.close(os.open(video_temp_file.name, os.O_RDONLY))
                  os.remove(video_temp_file.name)
                except:
                    pass
           raise
        
    except Exception as e:
        logging.error(f"Error en la creación del video: {str(e)}")
        return False, f"Error al generar video: {str(e)}", None, None

def main():
    st.title("Creador de Videos Automático")
    
    #Eliminar archivos temporales al iniciar
    if "video_path" in st.session_state:
        try:
           os.close(os.open(st.session_state.video_path, os.O_RDONLY))
           os.remove(st.session_state.video_path)
           st.session_state.video_path = None
        except Exception as e:
           logging.error(f"Error al eliminar video temporal al inicio: {str(e)}")
           st.session_state.video_path = None
    if "audio_files" in st.session_state and st.session_state.audio_files is not None:
        for file_path in st.session_state.audio_files:
          try:
             os.close(os.open(file_path, os.O_RDONLY))
             os.remove(file_path)
          except Exception as e:
            logging.error(f"Error al eliminar audio temporal al inicio: {str(e)}")
          
        st.session_state.audio_files = None
    if "video_path" not in st.session_state:
        st.session_state.video_path = None
    if "audio_files" not in st.session_state:
       st.session_state.audio_files = None

    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
    logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"
    bucket_name = st.text_input("Nombre del Bucket de Cloud Storage", "datosblog-4095b.appspot.com")
    
    if uploaded_file:
        texto = uploaded_file.read().decode("utf-8")
        nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
        
        if st.button("Generar Video"):
            with st.spinner('Generando video...'):
                nombre_salida_completo = f"{nombre_salida}.mp4"
                try:
                  success, message, video_url, audio_files = create_simple_video(texto, nombre_salida_completo, voz_seleccionada, logo_url, bucket_name)
                  if success:
                    st.success(message)
                    st.video(video_url)
                    st.markdown(f'<a href="{video_url}" target="_blank">Descargar video</a>', unsafe_allow_html=True)
                    st.session_state.video_path = video_url
                    st.session_state.audio_files = audio_files
                  else:
                    st.error(message)
                except Exception as e:
                  st.error(f"Ocurrió un error inesperado: {str(e)}")

        if st.session_state.get("video_path"):
            st.markdown(f'<a href="https://www.youtube.com/upload" target="_blank">Subir video a YouTube</a>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
