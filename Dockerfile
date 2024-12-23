FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN apt-get update && apt-get install -y ffmpeg # Aseguramos la instalación de ffmpeg
RUN pip install -r requirements.txt

CMD ["streamlit", "run", "app.py", "--server.port", "8080", "--server.enableCORS", "false", "--server.headless", "true"]
