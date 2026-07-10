# Catálogo de Produtos com Cache-Aside e Alta Concorrência

API assíncrona de alta performance desenvolvida em FastAP para o gerenciamento de um catálogo de produtos e registros de vendas. O objetivo deste projeto é modelar e avaliar uma arquitetura híbrida de bancos de dados NoSQL, integrando a persistência orientada a documentos do MongoDB com a velocidade de armazenamento em memória RAM do Redis através da estratégia de cache Cache-Aside.

Toda a infraestrutura é orquestrada utilizando microsserviços isolados através do Docker Compose, permitindo simular cenários reais de estresse e alta concorrência.

Como Rodar
1. Estrutura de Arquivos
Certifique-se de que a raiz do seu projeto possui a seguinte árvore:
quarta_prova/
├── app/
│   ├── database.py       
│   ├── main.py           
│   └── models.py         
├── k6/
│   ├── cenario_com_cache.js  
│   ├── cenario_sem_cache.js  
├── docker-compose.yml   
└── Dockerfile           

2. Subir os Containers via Docker Compose
Para construir a imagem da API e iniciar os serviços integrados (API, MongoDB e Redis), execute o comando na raiz do projeto:

docker compose up --build


A API estará disponível para receber conexões em http://localhost:8000. A documentação interativa (Swagger UI) para validação visual dos endpoints pode ser acessada em http://localhost:8000/docs.

Lógica de Invalidação e Consistência do Cache
Para garantir que a camada de cache não entregue dados obsoletos (stale data), foram implementados gatilhos automáticos de invalidação baseados nos verbos HTTP:

Estratégia de Leitura (GET /produtos/{id}): A API tenta ler do Redis. Se houver falha, busca no MongoDB e popula o cache do Redis com um tempo de expiração (TTL) de 300 segundos.

Estratégia de Escrita e Mutação (POST, PUT e Vendas): Sempre que um novo produto é criado, atualizado ou uma venda é registrada, comandos explícitos de deleção (await redis_client.delete) limpam as chaves afetadas (produtos:todos, produto:{id} e ranking:mais_vendidos). Isso força a próxima requisição de leitura a buscar o dado atualizado diretamente da fonte da verdade (MongoDB).

3. Métricas de Performance e Testes de Carga (k6)
Para validar empiricamente a robustez da arquitetura sob estresse, foram realizados testes utilizando a ferramenta k6, simulando um cenário de alta concorrência com 200 usuários virtuais simultâneos (VUs) atacando a rota de busca por ID de produto.

### Quantidade e Sucesso das Requisições
Esta tabela apresenta o volume total de tráfego que cada cenário conseguiu escoar durante o tempo estipulado do teste:

| Cenário de Teste             | Total de Requisições | Taxa de Sucesso (Checks) | Falhas / Erros |

| Com Cache Ativo (Redis)      | 7.358 passes         | 100.00% (HTTP 200)       | 0 |
| Sem Cache (Direct Mongo)     | 6.628 passes         | 100.00% (HTTP 200)       | 0 |

---

### Latência e Tempos de Resposta
A tabela abaixo detalha o comportamento do tempo de resposta da API sob alta concorrência, medido em milissegundos (ms):

| Métrica de Tempo      | Com Cache (Redis) | Sem Cache (MongoDB) | Otimização Arquitetural |

| Tempo Mínimo (Min)    | 1.99 ms           | 2.62 ms             | Resposta imediata em RAM |
| Tempo Médio (Avg)     | 11.56 ms          | 16.20 ms            | Redis é um pouco mais rápido |
| Percentil 95 (P95)    | 42.29 ms          | 54.00 ms            | Maior estabilidade sob stress |
| Tempo Máximo (Max)    | 140.55 ms         | 180.95 ms           | Redução drástica de picos |

---

## Conclusão

1.  A infraestrutura utilizando o Redis conseguiu processar +730 requisições a mais dentro do mesmo intervalo de tempo, provando que operações baseadas em memória liberam as threads de execução do FastAPI  mais rápido sendo obsevado um Ganho de Vazão (Throughput)
2. No pior cenário de concorrência (Max), as consultas diretas ao MongoDB chegaram a 180.95 ms devido ao custo de processamento de busca em ficheiros de disco. O cache do Redis estabilizou o teto de lentidão em 140.55 ms. 
O que se observou que não houve um ganho tão grande entre os bancos Redis e Mongo, mas essa observação se dá devido às limitações da simulação e ao ajuste de parametros d epopulação dos bancos.
