import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis

# Se a variável injetada pelo Docker falhar, o fallback padrão será o nome do serviço no Docker
MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongodb:27017/catalogo")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")

print(f"Conectando no Mongo via: {MONGO_URI}")
print(f"Conectando no Redis via: {REDIS_URL}")

# Foi criado os clientes com timeout explícito de conexão (5 segundos) para não travar a API infinitamente
mongo_client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo_client["catalogo"]

redis_client = aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=5.0)

async def init_db():
    """Garante a criação de índices sem travar o startup"""
    try:
        # Criando de forma explicitamente assíncrona
        await db.produtos.create_index([("nome", "text")])
        await db.produtos.create_index("categoria")
        print("Índices do MongoDB validados com sucesso!")
    except Exception as e:
        print(f"❌ [DIAGNÓSTICO ERRO] Falha ao criar índices no Mongo: {e}")