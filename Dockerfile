FROM python:3.11-alpine

RUN apk add --no-cache gcc musl-dev linux-headers

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Sem a flag --reload dentro do Docker para evitar loops do reloader no Alpine
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]