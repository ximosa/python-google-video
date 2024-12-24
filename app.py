import streamlit as st
import os
import json
import logging
import time
import subprocess
from google.cloud import texttospeech
from moviepy.editor import AudioFileClip, ImageClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import tempfile
import requests
from io import BytesIO
import threading
import queue
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
        raise KeyError("Variable de entorno GOOGLE_CREDENTIALS no configurada")
except KeyError as e:
    logging.error(f"Error al cargar credenciales: {str(e)}")
    st.error(f"Error al cargar credenciales: {str(e)}")

# Variable de entorno para el bucket de GCS
BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
if not BUCKET_NAME:
    logging.error("Variable de entorno GCS_BUCKET_NAME no configurada")
    st.error("Variable de entorno GCS_BUCKET_NAME no configurada")

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
    try:
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
    except Exception as e:
        logging.error(f"Error en create_text_image: {str(e)}")
        return None

# Nueva función para crear la imagen de suscripción
def create_subscription_image(logo_url,size=(1280, 720), font_size=60):
    try:
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
    except Exception as e:
      logging.error(f"Error en create_subscription_image: {str(e)}")
      return None
def audio_segment_generator(texto, voz, logo_url):
    archivos_temp = []
    video_files_list = []
    try:
        logging.info("Iniciando proceso de generación de audio...")
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
                logging.error(f"Máximos intentos de reintento alcanzados para segmento: {segmento}")
                continue
            
            temp_filename = f"temp_audio_{i}.mp3"
            archivos_temp.append(temp_filename)
            with open(temp_filename, "wb") as out:
                out.write(response.audio_content)
            
            audio_clip = AudioFileClip(temp_filename)
            duracion = audio_clip.duration
            
            text_img = create_text_image(segmento)
            if text_img is None:
                logging.error(f"Error: la imagen de texto es None para segmento: {segmento}")
                audio_clip.close()
                continue
            
            txt_clip = (ImageClip(text_img)
                      .set_start(tiempo_acumulado)
                      .set_duration(duracion)
                      .set_position('center'))
            
            video_segment = txt_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
            
            if video_segment is None:
              logging.error(f"Error al crear video segmento. video_segment es None")
              audio_clip.close()
              txt_clip.close()
              continue
            
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video_file:
                video_segment.write_videofile(
                    temp_video_file.name,
                    fps=24,
                    codec='libx264',
                    audio_codec='aac',
                    preset='ultrafast',
                    threads=4
                )
                video_files_list.append(temp_video_file.name)
            
            audio_clip.close()
            txt_clip.close()
            video_segment.close()
            
            tiempo_acumulado += duracion
            time.sleep(0.2)

        # Añadir clip de suscripción
        subscribe_img = create_subscription_image(logo_url) # Usamos la función creada
        if subscribe_img is None:
          logging.error(f"Error: la imagen de subscripción es None")
        else:
          duracion_subscribe = 5
          subscribe_clip = (ImageClip(subscribe_img)
                          .set_start(tiempo_acumulado)
                          .set_duration(duracion_subscribe)
                          .set_position('center'))
          if subscribe_clip is None:
            logging.error("Error al crear el clip de suscripción: subscribe_clip es None.")
          else:
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video_file:
                subscribe_clip.write_videofile(
                  temp_video_file.name,
                    fps=24,
                    codec='libx264',
                    audio_codec='aac',
                    preset='ultrafast',
                    threads=4
                )
                video_files_list.append(temp_video_file.name)
            subscribe_clip.close()
        yield video_files_list
    except Exception as e:
        logging.error(f"Error en generador de audio: {str(e)}")
        raise
    finally:
       for temp_file in archivos_temp:
            try:
                if os.path.exists(temp_file):
                    os.close(os.open(temp_file, os.O_RDONLY))
                    os.remove(temp_file)
            except:
                pass
def create_video_thread(texto, nombre_salida, voz, logo_url, result_queue):
    try:
        logging.info("Iniciando creación del video en segundo plano...")
        video_files_lists_gen = audio_segment_generator(texto,voz,logo_url)
        
        all_video_files = []
        for video_files in video_files_lists_gen:
          if video_files is None:
            logging.error("Error, lista de vídeos temporales es None")
            result_queue.put((False, "Error al generar video: No se han podido generar los vídeos temporales.", None))
            return
          all_video_files.extend(video_files)

        if not all_video_files:
            logging.error("No se han generado ficheros temporales.")
            result_queue.put((False, "Error al generar video: No se han generado los ficheros de vídeo temporales.", None))
            return
          
        # Concatenar archivos en lotes
        batch_size = 10
        batch_files = [all_video_files[i:i + batch_size] for i in range(0, len(all_video_files), batch_size)]
        intermediate_files = []

        for i, batch in enumerate(batch_files):
            with tempfile.NamedTemporaryFile(suffix=f"intermediate_{i}.mp4", delete=False) as temp_intermediate_file:
              temp_intermediate_filename = temp_intermediate_file.name
              command = ["ffmpeg", "-y"]
              for file in batch:
                  command.extend(["-i", file])
              command.extend(["-filter_complex", "concat=n=" + str(len(batch)) + ":v=1:a=1", temp_intermediate_filename])
              try:
                  subprocess.run(command, check=True, capture_output=True)
                  logging.info(f"Lote {i} concatenado con ffmpeg correctamente")
                  intermediate_files.append(temp_intermediate_filename)
              except subprocess.CalledProcessError as e:
                  logging.error(f"Error al concatenar el lote {i} con ffmpeg: {e} - {e.stderr.decode()}")
                  result_queue.put((False, f"Error al concatenar el lote {i} con ffmpeg: {e}", None))
                  return
        
        # Concatenar archivos intermedios
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_final_video_file:
          temp_final_video_filename = temp_final_video_file.name
            
          command = ["ffmpeg", "-y"]
          for file in intermediate_files:
             command.extend(["-i", file])
          command.extend(["-filter_complex", "concat=n=" + str(len(intermediate_files)) + ":v=1:a=1", temp_final_video_filename])
          try:
              subprocess.run(command, check=True, capture_output=True)
              logging.info("Vídeo concatenado con ffmpeg correctamente")
          except subprocess.CalledProcessError as e:
              logging.error(f"Error al concatenar el vídeo con ffmpeg: {e} - {e.stderr.decode()}")
              result_queue.put((False, f"Error al concatenar el vídeo con ffmpeg: {e}", None))
              return
          
          # Inicializar cliente de GCS
          storage_client = storage.Client()
          bucket = storage_client.bucket(BUCKET_NAME)
          blob = bucket.blob(nombre_salida)
            
          # Subir video a GCS
          blob.upload_from_filename(temp_final_video_filename)
          os.remove(temp_final_video_filename)
          for file in all_video_files:
            os.remove(file)
          for file in intermediate_files:
            os.remove(file)
          logging.info("Video subido a GCS exitosamente.")
          
        
        
        result_queue.put((True, "Video generado y subido a GCS exitosamente", f"https://storage.googleapis.com/{BUCKET_NAME}/{nombre_salida}"))
    except Exception as e:
        logging.error(f"Error durante creación del video: {str(e)}")
        result_queue.put((False, str(e),None))

def main():
    st.title("Creador de Videos Automático")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
    logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"
    
    if uploaded_file:
        texto = uploaded_file.read().decode("utf-8")
        nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado.mp4")
        
        if st.button("Generar Video"):
          with st.spinner('Generando video...'):
            
            result_queue = queue.Queue()
            video_thread = threading.Thread(target=create_video_thread, 
                                             args=(texto, nombre_salida, voz_seleccionada, logo_url, result_queue))
            video_thread.start()
            
            while video_thread.is_alive():
                time.sleep(1)
            
            success, message, video_url = result_queue.get()
            if success:
                st.session_state.video_url = video_url
                st.success(message)
                st.video(video_url)
                st.markdown(f'<a href="{video_url}" target="_blank">Descargar video desde GCS</a>', unsafe_allow_html=True)
            else:
              st.error(f"Error al generar video: {message}")

        if st.session_state.get("video_url"):
            st.success("Video disponible")
            st.video(st.session_state.video_url)
            st.markdown(f'<a href="{st.session_state.video_url}" target="_blank">Descargar video desde GCS</a>', unsafe_allow_html=True)
            st.markdown(f'<a href="https://www.youtube.com/upload" target="_blank">Subir video a YouTube</a>', unsafe_allow_html=True)

if __name__ == "__main__":
    # Inicializar session state
    if "video_url" not in st.session_state:
        st.session_state.video_url = None
    main()
