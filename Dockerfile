# Usa un'immagine Python ufficiale e leggera
FROM python:3.9-slim

# Imposta la directory di lavoro all'interno del container
WORKDIR /app

# Installa le dipendenze necessarie
RUN pip install requests python-dotenv

# Copia lo script del controllore nella directory di lavoro
COPY dhcp_controller.py .

# Comando per eseguire lo script quando il container viene avviato
CMD ["python", "-u", "dhcp_controller.py"]
