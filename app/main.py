from fastapi import FastAPI, Query, status
from contextlib import asynccontextmanager
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

# Importar conexões e modelos
from app.database import db, init_db, redis_client
from app.models import ProdutoCreate, ProdutoResponse, VendaCreate


#(gemini)
# O lifespan gerencia o que acontece quando a API liga e desliga
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Quando a API liga: cria os índices no MongoDB automaticamente
    await init_db()
    yield
    # Quando a API desliga: fecha a conexão com o Redis
    await redis_client.close()

# Inicializa o FastAPI aplicando o ciclo de vida (lifespan)
app = FastAPI(title="Catálogo - MongoDB & Redis", lifespan=lifespan)

# Converter esse objeto e os dados em um dicionário Python simples.
def produto_helper(doc) -> dict:
    return {
        "id": str(doc["_id"]),
        "nome": doc["nome"],
        "categoria": doc["categoria"],
        "preco": doc["preco"],
        "estoque": doc["estoque"],
        "createdAt": doc["createdAt"]
    }


# POST /produtos -> Cadastra um novo produto no MongoDB
@app.post("/produtos", response_model=ProdutoResponse, status_code=status.HTTP_201_CREATED)
async def criar_produto(produto: ProdutoCreate):
    # Converte o modelo do Pydantic para um dicionário Python
    novo_produto = produto.model_dump()
    # Adiciona a data e hora atual no formato UTC
    novo_produto["createdAt"] = datetime.utcnow()
    
    # Salva no MongoDB dentro da coleção 'produtos'
    result = await db.produtos.insert_one(novo_produto)
    
    # Recupera o ID gerado pelo MongoDB e coloca no dicionário
    novo_produto["_id"] = result.inserted_id
    
    # Retorna o produto formatado de volta para o usuário
    return produto_helper(novo_produto)


# GET /produtos -> Lista todos os produtos com Paginação e Filtros
@app.get("/produtos", response_model=List[ProdutoResponse])
async def listar_produtos(
    limit: int = Query(10, le=100),
    skip: int = Query(0, ge=0),     
    categoria: Optional[str] = None, # Filtro opcional por categoria
    busca: Optional[str] = None      # Filtro opcional de busca por texto no nome
):
    filtro = {}
    
    # Se o usuário passou uma categoria na URL, adiciona no filtro do Mongo
    if categoria:
        filtro["categoria"] = categoria
        
    # Se o usuário passou um termo de busca, usa o Índice de Texto do database.py
    if busca:
        filtro["$text"] = {"$search": busca}
        
    # Faz a busca no banco aplicando os filtros
    cursor = db.produtos.find(filtro).skip(skip).limit(limit)
    produtos_do_banco = await cursor.to_list(length=limit)
    
    # Converte a lista do banco usando o helper e retorna
    return [produto_helper(p) for p in produtos_do_banco]


import json # Precisamos do json para converter o dicionário em texto para o Redis
from fastapi import HTTPException


# GET /produtos/{id} -> Detalhe do produto usando Cache-Aside
@app.get("/produtos/{id}", response_model=ProdutoResponse)
async def obter_produto(id: str, sem_cache: bool = Query(False)):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=404, detail="ID do produto inválido")
    
    chave_cache = f"produto:{id}"
    
    # Se o parâmetro 'sem_cache' for True, pulamos o Redis de propósito para testar o MongoDB
    if not sem_cache:
        # PASSO A: Consultar primeiro o Redis
        produto_cached = await redis_client.get(chave_cache)
        if produto_cached:
            return json.loads(produto_cached)
    else:
        print(f"[BYPASS] k6 solicitou busca direta no MongoDB para testes.")
    
    # PASSO B: Buscar no MongoDB
    produto_db = await db.produtos.find_one({"_id": ObjectId(id)})
    if not produto_db:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    produto_formatado = produto_helper(produto_db)
    
    # Só salva no cache se não estivermos simulando o "sem cache"
    if not sem_cache:
        await redis_client.setex(chave_cache, time=300, value=json.dumps(produto_formatado, default=str))
    
    return produto_formatado

# 4. PUT /produtos/{id} -> Atualiza o produto e INVALIDA o cache antigo
@app.put("/produtos/{id}", response_model=ProdutoResponse)
async def atualizar_produto(id: str, produto_atualizado: ProdutoCreate):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=404, detail="ID inválido")
        
    # Atualiza na fonte de verdade (MongoDB)
    dados_novos = produto_atualizado.model_dump()
    result = await db.produtos.update_one(
        {"_id": ObjectId(id)}, 
        {"$set": dados_novos}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
        
    # INVALIDAÇÃO DE CACHE (Obrigatório! Evita que a API retorne dados velhos)
    chave_cache = f"produto:{id}"
    await redis_client.delete(chave_cache)
    print(f"Chave {chave_cache} removida do Redis devido a uma mudança de chave")
    
    # Busca o produto atualizado para retornar na API
    doc = await db.produtos.find_one({"_id": ObjectId(id)})
    return produto_helper(doc)


# DELETE /produtos/{id} -> Remove o produto e INVALIDA o cache
@app.delete("/produtos/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_produto(id: str):
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=404, detail="ID inválido")
        
    # Remove do MongoDB
    result = await db.produtos.delete_one({"_id": ObjectId(id)})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
        
    #INVALIDAÇÃO DE CACHE
    chave_cache = f"produto:{id}"
    await redis_client.delete(chave_cache)
    print(f"🔥 [INVALIDAÇÃO] Produto deletado! Chave {chave_cache} removida do Redis.")
    
    return None

# 6. POST /vendas -> Registra uma venda no MongoDB e incrementa o ranking no Redis
@app.post("/vendas", status_code=status.HTTP_201_CREATED)
async def registrar_venda(venda: VendaCreate):
    # 1. Valida se o ID do produto enviado é válido
    if not ObjectId.is_valid(venda.produto_id):
        raise HTTPException(status_code=400, detail="ID do produto inválido")
    
    # 2. Verifica se o produto de fato existe no MongoDB e se tem estoque
    produto = await db.produtos.find_one({"_id": ObjectId(venda.produto_id)})
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    
    if produto["estoque"] < venda.quantidade:
        raise HTTPException(status_code=400, detail="Estoque insuficiente para realizar a venda")
        
    # 3. Calcula o valor total da venda
    valor_total = produto["preco"] * venda.quantidade
    
    # 4. Deduz a quantidade vendida do estoque do produto lá no MongoDB
    await db.produtos.update_one(
        {"_id": ObjectId(venda.produto_id)},
        {"$inc": {"estoque": -venda.quantidade}} # $inc com valor negativo subtrai
    )
    
    # 5. Salva o documento da venda na coleção 'vendas' do MongoDB
    nova_venda = {
        "produto_id": venda.produto_id,
        "quantidade": venda.quantidade,
        "valor_total": valor_total,
        "data": datetime.utcnow()
    }
    await db.vendas.insert_one(nova_venda)
    print("[MONGODB] Venda salva e estoque atualizado.")
    
    # 6. ATUALIZA O RANKING NO REDIS (Sorted Set)
     # A chave 'ranking:produtos' será usada para o Sorted Set
    await redis_client.zincrby(
        name="ranking:produtos", 
        amount=venda.quantidade, 
        value=venda.produto_id
    )
    print(f"[REDIS] Ranking atualizado! Produto {venda.produto_id} ganhou +{venda.quantidade} pontos.")
    
    # Invalida o cache do produto individual
    await redis_client.delete(f"produto:{venda.produto_id}")
    
    return {"mensagem": "Venda registrada com sucesso!", "valor_total": valor_total}


# 7. GET /ranking/mais-vendidos -> Retorna o top-N produtos do Sorted Set do Redis
@app.get("/ranking/mais-vendidos")
async def obter_ranking(n: int = Query(5, ge=1, le=50)):
    # Buscamos do Redis os N elementos com as maiores pontuações
    # ZREVRANGE lê do maior score para o menor (ordem decrescente)
    # withscores=True nos traz o ID do produto e a quantidade total que foi vendida dele
    ranking_cru = await redis_client.zrevrange("ranking:produtos", 0, n - 1, withscores=True)
    
    # Formatamos o resultado para ficar amigável na API
    ranking_formatado = []
    for produto_id, score in ranking_cru:
        ranking_formatado.append({
            "produto_id": produto_id,
            "quantidade_vendida": int(score)
        })
        
    return {
        "contexto": f"Top {n} produtos mais vendidos em tempo real",
        "ranking": ranking_formatado
    }

# 8. GET /relatorios/vendas -> Relatório agregado de faturamento usando Aggregation Pipeline
@app.get("/relatorios/vendas")
async def obter_relatorio_vendas():
    # 1º Estágio ($match): Poderia filtrar por data, mas aqui pegará todas as vendas do banco
    # 2º Estágio ($group): Agrupa tudo em um único bloco (id=None) e faz as somas
    # 3º Estágio ($project): Formata a saída limpando campos desnecessários
    pipeline = [
        {
            "$group": {
                "_id": None, # Agrupa todos os documentos de vendas juntos
                "faturamento_total": {"$sum": "$valor_total"}, # Soma o campo valor_total
                "total_unidades_vendidas": {"$sum": "$quantidade"}, # Soma as quantidades
                "total_de_pedidos": {"$count": {}} # Conta quantos documentos de vendas existem
            }
        },
        {
            "$project": {
                "_id": 0, # Remove o campo _id da resposta visual
                "faturamento_total": 1,
                "total_unidades_vendidas": 1,
                "total_de_pedidos": 1
            }
        }
    ]
    
    # Executa a pipeline na coleção de vendas
    cursor = db.vendas.aggregate(pipeline)
    resultado = await cursor.to_list(length=1)
    
    # Se ainda não houver vendas cadastradas, retorna valores zerados
    if not resultado:
        return {
            "faturamento_total": 0.0,
            "total_unidades_vendidas": 0,
            "total_de_pedidos": 0
        }
        
    return resultado[0]