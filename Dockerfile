FROM python:3.12-slim

# Non-root user matching docker-compose "user: 1000:100"
RUN useradd -u 1000 -m appuser

WORKDIR /src

COPY src/requirements.txt /src/requirements.txt
RUN pip install --no-cache-dir -r /src/requirements.txt

COPY src/ /src/


USER 1000:100

CMD ["python3", "main.py"]
