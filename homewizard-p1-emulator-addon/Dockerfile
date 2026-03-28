FROM python:3.11-alpine

# Zorgt dat logs direct in HA verschijnen
ENV PYTHONUNBUFFERED=1

# Installeer direct de benodigde pakketten (apk add is niet meer nodig)
RUN pip3 install --no-cache-dir flask requests zeroconf

# Kopieer ons script naar de container
COPY main.py /main.py

# Start het script
CMD [ "python3", "/main.py" ]