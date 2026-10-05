FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

VOLUME /app/data

EXPOSE 3031
EXPOSE 4210/udp

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3031"]
