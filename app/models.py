from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

# Como a API envia os dados
class ProdutoCreate(BaseModel):
    nome: str
    categoria: str
    preco: float = Field(gt=0, description="O preço deve ser maior que zero")
    estoque: int = Field(ge=0, description="O estoque não pode ser negativo")

# Como a APi recebe os dados
class ProdutoResponse(BaseModel):
    id: str
    nome: str
    categoria: str
    preco: float
    estoque: int
    createdAt: datetime

class VendaCreate(BaseModel):
    produto_id: str
    quantidade: int = Field(gt=0, description="A quantidade deve ser maior que zero")