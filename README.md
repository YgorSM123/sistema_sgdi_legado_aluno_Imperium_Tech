# SGDI - Sistema de Gestão de Demandas Internas

Sistema para gerenciar demandas internas da empresa.

## Como rodar

```bash
pip install -r requirements.txt
python init_db.py
python app.py
```

- Interface web: http://localhost:5000
- **Swagger (todas as rotas):** http://localhost:5000/apidocs/

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

### Variáveis de ambiente (produção)

| Variável | Descrição |
|----------|-----------|
| `SGDI_API_CLIENT_ID` | Client ID da integração |
| `SGDI_API_CLIENT_SECRET` | Client secret (alterar em produção) |
| `SGDI_JWT_SECRET` | Chave para assinar tokens JWT |
| `SECRET_KEY` | Chave Flask (fallback do JWT) |

## Funcionalidades

- Criar demandas
- Editar demandas
- Deletar demandas
- Visualizar detalhes
- Comentários
- Dashboard gerencial
- API REST documentada (Swagger)

---

*Desenvolvido em 2024 — Imperium Tech*
