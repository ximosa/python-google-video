FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install -r /app/requirements.txt

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg

COPY app.py /app/
# Agrega otras lineas COPY para archivos necesarios (ej, scripts, otros modulos)

CMD ["streamlit", "run", "app.py", "--server.port", "8080", "--server.enableCORS", "false", "--server.headless", "true"]
