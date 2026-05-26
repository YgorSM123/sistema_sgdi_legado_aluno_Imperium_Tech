# SGDI - Sistema de Gestão de Demandas Internas

Sistema para gerenciar demandas internas da empresa.

## Como rodar

```bash
pip install -r requirements.txt
python init_db.py
python app.py
```

- Interface web: http://localhost:5000
- Painel de auditoria: http://localhost:5000/auditoria
- **Swagger (todas as rotas):** http://localhost:5000/apidocs/
  1. Execute **POST /api/auth/login** (Try it out → Execute)
  2. Depois use as outras APIs (token aplicado automaticamente)
  3. Ou clique em **Authorize** e cole `Bearer SEU_TOKEN`

## API REST (integração externa)

A API permite consultar e manipular dados do SGDI com autenticação JWT.

### 1. Obter token

```bash
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"sgdi_integration\",\"client_secret\":\"sgdi_api_secret_change_me\"}"
```

### 2. Usar o token

```bash
curl http://localhost:5000/api/demandas \
  -H "Authorization: Bearer SEU_TOKEN_AQUI"
```

### Endpoints da API

| Método | Rota | Descrição |
|--------|------|-----------|
| POST | `/api/auth/login` | Autenticação (JWT) |
| GET | `/api/demandas` | Listar demandas |
| GET | `/api/demandas/{id}` | Obter demanda |
| POST | `/api/demandas` | Criar demanda |
| PUT | `/api/demandas/{id}` | Atualizar demanda |
| DELETE | `/api/demandas/{id}` | Excluir demanda |
| POST | `/api/demandas/{id}/finalizar` | Finalizar demanda |
| GET | `/api/usuarios` | Listar usuários |
| POST | `/api/usuarios` | Criar usuário |
| GET | `/api/usuarios/{id}` | Obter usuário |
| GET | `/api/comentarios/demanda/{id}` | Listar comentários |
| POST | `/api/comentarios/demanda/{id}` | Adicionar comentário |
| DELETE | `/api/comentarios/{id}` | Excluir comentário |
| GET | `/api/dashboard` | Indicadores (JSON) |
| GET | `/api/audit/events` | Historico de auditoria |

### Auditoria e rastreabilidade

O sistema registra automaticamente acoes importantes na tabela `audit_events` (SQLite): criar/editar/excluir demandas e comentarios, login, exportacao de dashboard, etc.

Cada registro inclui data/hora, acao, entidade, ator (cliente JWT na API ou interface web), IP, metodo, caminho e detalhes em JSON (ex.: antes/depois em atualizacoes).

Consulte via **GET /api/audit/events** (JWT). Filtros: `action`, `entity_type`, `entity_id`, `source` (`api` ou `web`), `limit`, `offset`.

### Variáveis de ambiente (produção)

| Variável | Descrição |
|----------|-----------|
| `SGDI_API_CLIENT_ID` | Client ID da integração |
| `SGDI_API_CLIENT_SECRET` | Client secret (alterar em produção) |
| `SGDI_JWT_SECRET` | Chave para assinar tokens JWT |
| `SECRET_KEY` | Chave Flask (fallback do JWT) |

## Funcionalidades

- Painel web de auditoria (`/auditoria`) com filtros e detalhes JSON
- Log de auditoria centralizado (rastreabilidade de acoes)
- Criar demandas
- Editar demandas
- Deletar demandas
- Visualizar detalhes
- Comentários
- Dashboard gerencial
- API REST documentada (Swagger)

---

*Desenvolvido em 2024 — Imperium Tech*
