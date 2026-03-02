# 🚀 Quick Start Guide - Auth Service

Bem-vindo ao **Auth Service**! Este guia te ajudará a colocar o serviço em funcionamento em poucos minutos.

---

## ⚡ Setup Rápido (5 minutos)

### 1️⃣ Clonar e Entrar na Pasta

```bash
cd auth-service
```

### 2️⃣ Criar Ambiente Virtual

```bash
python -m venv venv

# Linux/Mac:
source venv/bin/activate

# Windows:
venv\Scripts\activate
```

### 3️⃣ Instalar Dependências

```bash
pip install -r requirements.txt
```

### 4️⃣ Configurar Variáveis de Ambiente

```bash
cp .env.example .env
```

⚠️ **Para desenvolvimento rápido**, edite `.env`:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/auth_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=meu-segredo-super-secreto-mudar-em-producao
DEBUG=True
```

---

## 🐘 Setup de Base de Dados (PostgreSQL + Redis)

### Opção A: Docker Compose (Recomendado)

```bash
docker-compose up -d
```

Espera ~30 segundos para os serviços iniciarem.

### Opção B: Manual (PostgreSQL)

```bash
# macOS (Homebrew)
brew install postgresql
brew services start postgresql

# Linux (Ubuntu)
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql

# Windows: Download em https://www.postgresql.org/download/windows/
```

Depois cria a base de dados:

```bash
createdb -U user auth_db
```

### Opção B.2: Redis (Opcional, para Logout avançado)

```bash
# macOS
brew install redis
brew services start redis

# Linux
sudo apt install redis-server
sudo systemctl start redis-server

# Docker
docker run -d -p 6379:6379 redis:7-alpine
```

---

## ▶️ Executar o Serviço

```bash
# Modo desenvolvimento (auto-reload):
uvicorn app.main:app --reload

# Modo produção:
python -m app.main
```

✅ Serviço rodando em: http://localhost:8000

---

## 📚 Acessar a Documentação

Abra no teu browser:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

---

## 🧪 Testar com cURL

### 1. Registo de Utilizador

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "andre@example.com",
    "password": "senha123456",
    "full_name": "André Alexandre",
    "role": "fan"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "andre@example.com",
  "full_name": "André Alexandre",
  "is_active": true,
  "role": "fan",
  "created_at": "2026-03-02T..."
}
```

---

### 2. Login

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "andre@example.com",
    "password": "senha123456"
  }'
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Guarda o `access_token`! Vais precisar dele.

---

### 3. Obter Perfil Atual

```bash
# Substitui TOKEN pelo access_token que recebeste
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X GET "http://localhost:8000/api/v1/auth/me" \
  -H "Authorization: Bearer $TOKEN"
```

---

### 4. Renovar Token

```bash
REFRESH_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}"
```

---

### 5. Validar Token (Outro Serviço)

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X POST "http://localhost:8000/api/v1/auth/verify" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$TOKEN\"}"
```

**Response:**
```json
{
  "valid": true,
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "fan",
  "email": "andre@example.com"
}
```

---

### 6. Logout

```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X POST "http://localhost:8000/api/v1/auth/logout" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🧪 Testar com Python

```python
import httpx
import asyncio

async def main():
    base_url = "http://localhost:8000"
    
    # 1. Registar
    response = await httpx.AsyncClient().post(
        f"{base_url}/api/v1/auth/register",
        json={
            "email": "andre@example.com",
            "password": "senha123456",
            "full_name": "André Alexandre",
            "role": "fan"
        }
    )
    print("Registo:", response.json())
    
    # 2. Login
    response = await httpx.AsyncClient().post(
        f"{base_url}/api/v1/auth/login",
        json={
            "email": "andre@example.com",
            "password": "senha123456"
        }
    )
    tokens = response.json()
    print("Login:", tokens)
    
    # 3. Obter Perfil
    response = await httpx.AsyncClient().get(
        f"{base_url}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    print("Perfil:", response.json())

asyncio.run(main())
```

---

## 📁 Estrutura de Ficheiros

```
auth-service/
├── app/
│   ├── api/v1/auth.py          ← Endpoints
│   ├── core/security.py         ← JWT e hashing
│   ├── models/__init__.py       ← User model
│   ├── schemas/user.py          ← Pydantic schemas
│   ├── crud/__init__.py         ← Database operations
│   ├── db/__init__.py           ← Database connection
│   └── main.py                  ← FastAPI app
├── .env                         ← Variáveis (criar de .env.example)
├── requirements.txt             ← Dependências
└── README.md                    ← Documentação completa
```

---

## ❌ Troubleshooting

### Erro: `ModuleNotFoundError: No module named 'app'`

```bash
# Certifica-te que estás na pasta auth-service:
cd auth-service

# E que o ambiente virtual está ativado:
source venv/bin/activate
```

### Erro: `postgresql://user:password@localhost:5432/auth_db`

```bash
# Verifica se PostgreSQL está rodando:
psql -U user -d auth_db

# Se não, inicia:
docker-compose up -d postgres
```

### Erro: `Connection refused` (Redis)

Jest a usar a denylist de tokens? Redis é opcional. Se não precisas, comentar em `.env`:

```env
# REDIS_URL=redis://localhost:6379/0
```

---

## 🔗 Próximos Passos

1. ✅ Serviço rodando
2. 📚 Lê a documentação em `/docs`
3. 🧪 Testa os endpoints
4. 🔌 Integra com outros serviços (Inventory, Payment)
5. 🚀 Deploy!

---

## 📧 Suporte

Problemas? Verifica o `README.md` para mais informações.

---

**Pronto para começar? Boa sorte, André! 🚀**
