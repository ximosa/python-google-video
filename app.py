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
    # Crear un directorio temporal en /tmp que es accesible en Cloud Run
    temp_dir = tempfile.mkdtemp(dir="/tmp")
    
    try:
        # ... (resto del código igual hasta la generación del video)

        # Modificar la ruta de salida para usar /tmp
        nombre_salida_completo = os.path.join("/tmp", nombre_salida)
        
        video_final.write_videofile(
            nombre_salida_completo,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            threads=2,
            logger=None
        )
        
        # Asegurarse de que el archivo tiene los permisos correctos
        os.chmod(nombre_salida_completo, 0o666)
        
        # ... (resto de la limpieza igual)
        
        return True, nombre_salida_completo  # Retornar la ruta completa del archivo

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
            if len(texto) > 50000:
                st.warning("El texto es muy largo. Por favor, divídelo en partes más pequeñas.")
                return
            
            nombre_salida = st.text_input("Nombre del Video (sin extensión)", "video_generado")
            
            if st.button("Generar Video"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                with st.spinner('Generando video...'):
                    nombre_salida_completo = f"{nombre_salida}.mp4"
                    success, file_path = create_simple_video(texto, nombre_salida_completo, voz_seleccionada, logo_url)
                    
                    if success:
                        st.success("Video generado exitosamente")
                        
                        try:
                            # Leer el archivo en memoria antes de mostrarlo
                            with open(file_path, 'rb') as file:
                                video_bytes = file.read()
                            
                            # Mostrar el video
                            st.video(video_bytes)
                            
                            # Botón de descarga
                            st.download_button(
                                label="Descargar video",
                                data=video_bytes,
                                file_name=nombre_salida_completo,
                                mime="video/mp4"
                            )
                            
                        except Exception as e:
                            st.error(f"Error al acceder al video: {str(e)}")
                            logging.error(f"Error al acceder al video: {str(e)}")
                    else:
                        st.error(f"Error al generar video: {file_path}")  # file_path contendrá el mensaje de error en este caso

    except Exception as e:
        logging.error(f"Error en la función main: {str(e)}")
        st.error(f"Error inesperado: {str(e)}")
        
    finally:
        # Limpiar archivos temporales si existen
        try:
            for root, dirs, files in os.walk("/tmp", topdown=False):
                for name in files:
                    if name.endswith(".mp4"):
                        try:
                            os.remove(os.path.join(root, name))
                        except:
                            pass
        except:
            pass

if __name__ == "__main__":
    if "video_path" not in st.session_state:
        st.session_state.video_path = None
    main()
