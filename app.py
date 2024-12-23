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
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

logging.basicConfig(level=logging.INFO)

# ... (mantener la configuración de credenciales y voces igual)

def process_text_chunk(chunk, client, voz, temp_dir, chunk_index):
    """Procesa un chunk individual de texto"""
    try:
        synthesis_input = texttospeech.SynthesisInput(text=chunk)
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
                if "429" in str(e):
                    retry_count += 1
                    time.sleep(2**retry_count)
                else:
                    raise
        
        if retry_count > max_retries:
            raise Exception("Máximo número de reintentos alcanzado")
            
        temp_filename = os.path.join(temp_dir, f"temp_audio_{chunk_index}.mp3")
        
        with open(temp_filename, "wb") as out:
            out.write(response.audio_content)
        os.chmod(temp_filename, 0o777)
        
        return {
            'index': chunk_index,
            'filename': temp_filename,
            'text': chunk
        }
        
    except Exception as e:
        logging.error(f"Error procesando chunk {chunk_index}: {str(e)}")
        raise

def create_simple_video(texto, nombre_salida, voz, logo_url):
    archivos_temp = []
    clips = []
    temp_dir = tempfile.mkdtemp(dir="/dev/shm")
    
    try:
        logging.info("Iniciando proceso de creación de video...")
        
        # Dividir el texto en chunks más pequeños
        MAX_CHARS_PER_CHUNK = 250
        palabras = texto.split()
        chunks = []
        chunk_actual = []
        
        for palabra in palabras:
            chunk_actual.append(palabra)
            chunk_texto = ' '.join(chunk_actual)
            
            if len(chunk_texto) >= MAX_CHARS_PER_CHUNK or palabra == palabras[-1]:
                if chunk_texto.strip():
                    chunks.append(chunk_texto.strip())
                chunk_actual = []
        
        client = texttospeech.TextToSpeechClient()
        tiempo_acumulado = 0
        
        # Procesar chunks en paralelo
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for i, chunk in enumerate(chunks):
                future = executor.submit(
                    process_text_chunk,
                    chunk,
                    client,
                    voz,
                    temp_dir,
                    i
                )
                futures.append(future)
            
            # Recolectar resultados
            results = []
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logging.error(f"Error en proceso paralelo: {str(e)}")
                    raise
            
            # Ordenar resultados por índice
            results.sort(key=lambda x: x['index'])
            
            # Crear clips
            for result in results:
                try:
                    audio_clip = AudioFileClip(result['filename'])
                    archivos_temp.append(result['filename'])
                    
                    duracion = audio_clip.duration
                    text_img = create_text_image(result['text'])
                    
                    txt_clip = (ImageClip(text_img)
                              .set_start(tiempo_acumulado)
                              .set_duration(duracion)
                              .set_position('center'))
                    
                    video_segment = txt_clip.set_audio(audio_clip.set_start(tiempo_acumulado))
                    clips.append(video_segment)
                    
                    tiempo_acumulado += duracion
                    
                except Exception as e:
                    logging.error(f"Error procesando clip: {str(e)}")
                    raise
        
        # Añadir clip de suscripción
        subscribe_img = create_subscription_image(logo_url)
        duracion_subscribe = 5
        
        subscribe_clip = (ImageClip(subscribe_img)
                         .set_start(tiempo_acumulado)
                         .set_duration(duracion_subscribe)
                         .set_position('center'))
        
        clips.append(subscribe_clip)
        
        # Generar video final con menos uso de memoria
        video_final = concatenate_videoclips(clips, method="compose")
        
        video_final.write_videofile(
            nombre_salida,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=2,
            logger=None
        )
        
        # Limpieza de recursos
        video_final.close()
        
        for clip in clips:
            try:
                clip.close()
            except:
                pass
        
        for temp_file in archivos_temp:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        
        try:
            os.rmdir(temp_dir)
        except:
            pass
        
        return True, "Video generado exitosamente"
        
    except Exception as e:
        logging.error(f"Error en la creación de video: {str(e)}")
        
        # Limpieza en caso de error
        for clip in clips:
            try:
                clip.close()
            except:
                pass
        
        for temp_file in archivos_temp:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        
        try:
            os.rmdir(temp_dir)
        except:
            pass
        
        return False, str(e)

def main():
    st.title("Creador de Videos Automático")
    
    # Aumentar límite de tamaño de archivo
    st.set_page_config(layout="wide")
    
    uploaded_file = st.file_uploader("Carga un archivo de texto", type="txt")
    voz_seleccionada = st.selectbox("Selecciona la voz", options=list(VOCES_DISPONIBLES.keys()))
    logo_url = "https://yt3.ggpht.com/pBI3iT87_fX91PGHS5gZtbQi53nuRBIvOsuc-Z-hXaE3GxyRQF8-vEIDYOzFz93dsKUEjoHEwQ=s176-c-k-c0x00ffffff-no-rj"
    
    try:
        if uploaded_file:
            texto = uploaded_file.read().decode("utf-8")
            
            # Validar tamaño del texto
            if len(texto) > 50000:  # aproximadamente 10000 palabras
                st.warning("El texto es muy largo. Por favor, divídelo en partes más pequeñas.")
                return
            
            nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
            
            if st.button("Generar Video"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                with st.spinner('Generando video...'):
                    nombre_salida_completo = f"{nombre_salida}.mp4"
                    success, message = create_simple_video(texto, nombre_salida_completo, voz_seleccionada, logo_url)
                    
                    if success:
                        st.success(message)
                        st.video(nombre_salida_completo)
                        
                        if os.path.exists(nombre_salida_completo):
                            with open(nombre_salida_completo, 'rb') as file:
                                st.download_button(
                                    label="Descargar video",
                                    data=file,
                                    file_name=nombre_salida_completo,
                                    mime="video/mp4"
                                )
                        else:
                            st.error("No se encontró el archivo")
                    else:
                        st.error(f"Error al generar video: {message}")

    except Exception as e:
        logging.error(f"Error en la función main: {str(e)}")
        st.error(f"Error inesperado: {str(e)}")

if __name__ == "__main__":
    if "video_path" not in st.session_state:
        st.session_state.video_path = None
    main()
