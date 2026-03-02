# Authentication Service - FastAPI Microservice

## 📋 Descrição

Serviço de Autenticação para a plataforma **EGS (Event Gamification System)** desenvolvido com **FastAPI**. 

Este serviço gerencia:
- ✅ Registo e autenticação de utilizadores
- 🔐 Geração e validação de tokens JWT
- 🔄 Renovação de tokens
- 🛡️ Validação de tokens (para usar por outros serviços)
- 👤 Gestão de perfis de utilizador

---

## 🚀 Estrutura do Projeto

```
auth-service/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── auth.py                # Endpoints de autenticação
│   ├── core/
│   │   ├── config.py                  # Configurações da aplicação
│   │   ├── security.py                # Utilitários JWT e hashing
│   │   └── dependencies.py            # Dependências HTTP
│   ├── crud/
│   │   └── __init__.py                # Operações de banco de dados
│   ├── db/
│   │   └── __init__.py                # Conexão e inicialização do DB
│   ├── models/
│   │   └── __init__.py                # Modelos SQLAlchemy
│   ├── schemas/
│   │   └── user.py                    # Schemas Pydantic
│   └── main.py                        # Aplicação FastAPI principal
├── .env.example                       # Variáveis de ambiente (exemplo)
├── .gitignore                         # Ficheiros a ignorar no Git
├── requirements.txt                   # Dependências Python
├── Dockerfile                         # Para containerizar a aplicação
├── docker-compose.yml                 # PostgreSQL + Redis + App
├── test_all_endpoints.py              # 🧪 Script de testes completo
├── tests_example.py                   # Exemplos de testes com pytest
├── QUICKSTART.md                      # Guia rápido de instalação
└── README.md                          # Este arquivo (documentação)
```

---

## 🛠️ Instalação

### Pré-requisitos

- **Python 3.10+**
- **PostgreSQL 12+**
- **Redis 6+** (para token denylist em produção)

### Passos

1. **Clone o repositório e entre na pasta:**

```bash
cd auth-service
```

2. **Crie um ambiente virtual:**

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

3. **Instale as dependências:**

```bash
pip install -r requirements.txt
```

4. **Configure as variáveis de ambiente:**

```bash
cp .env.example .env
# Edite .env com suas credenciais
```

5. **Inicie a aplicação:**

```bash
python -m app.main
# ou com reload automático:
uvicorn app.main:app --reload
```

A aplicação estará disponível em `http://localhost:8000`

---

## 🔐 Endpoints da API

### Base URL
```
/api/v1/auth
```

### 1. Registo de Utilizador

```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "strongpassword123",
  "full_name": "André Alexandre",
  "role": "fan"
}
```

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "full_name": "André Alexandre",
  "is_active": true,
  "role": "fan",
  "created_at": "2026-03-02T10:30:00Z"
}
```

---

### 2. Login (Autenticação)

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "strongpassword123"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

### 3. Renovação de Token

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

### 4. Obter Perfil Atual

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

**Response (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "full_name": "André Alexandre",
  "is_active": true,
  "role": "fan",
  "created_at": "2026-03-02T10:30:00Z"
}
```

---

### 5. Logout

```http
POST /api/v1/auth/logout
Authorization: Bearer <access_token>
```

**Response (204 No Content)**

---

### 6. Verificação de Token (Uso Interno)

Endpoint para outros serviços (Inventory, Payment) validarem tokens rapidamente:

```http
POST /api/v1/auth/verify
Content-Type: application/json

{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**
```json
{
  "valid": true,
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "role": "fan",
  "email": "user@example.com"
}
```

---

## 🔑 Estrutura do JWT Token

Os tokens JWT contêm:

```json
{
  "sub": "user_id",           // ID único do utilizador
  "email": "user@example.com", // Email do utilizador
  "role": "fan",               // Função (fan/promoter/admin)
  "type": "access",            // Tipo de token (access/refresh)
  "exp": 1677000000,          // Timestamp de expiração
  "iat": 1676999000           // Timestamp de criação
}
```

**Benefícios para outros serviços:**
- ✅ Sem necessidade de chamar o Auth Service para cada pedido
- ✅ Informações do utilizador disponíveis localmente
- ✅ Performance otimizada para FlashSale

---

## 🗄️ Base de Dados

### Tabela: `users`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | UUID | Chave primária |
| `email` | VARCHAR(255) | Email único |
| `full_name` | VARCHAR(255) | Nome completo |
| `hashed_password` | VARCHAR(255) | Senha com bcrypt |
| `is_active` | BOOLEAN | Status ativo/inativo |
| `role` | ENUM | fan, promoter, admin |
| `created_at` | TIMESTAMP | Data de criação |
| `updated_at` | TIMESTAMP | Data de atualização |

---

## 🔄 Fluxo de Autenticação

```
1. Utilizador → POST /register
   └─→ Cria conta novo

2. Utilizador → POST /login
   └─→ Recebe access_token e refresh_token

3. Utilizador → Utiliza access_token em requests
   └─→ Válido por 30 minutos

4. Access_token expira
   └─→ POST /refresh com refresh_token
       └─→ Novo access_token (válido por 30 min)

5. Outro Serviço → POST /verify com token
   └─→ Valida sem chamar Auth Service novamente
```

---

## 🛡️ Segurança

- ✅ Senhas com **bcrypt** (150,000 rounds)
- ✅ JWT com **HS256** (alterar SECRET_KEY em produção)
- ✅ Validação de email com **Pydantic**
- ✅ CORS configurável
- ✅ Token denylist com **Redis** (implementar conforme necessário)

---

## 🚦 Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "auth-service",
  "version": "1.0.0"
}
```

---

## 📚 Documentação Interativa

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🧪 Testes Automatizados

### Script Completo de Testes

Foi incluído um script Python que testa **todos os 9 cenários** da API de forma automatizada:

**Arquivo**: `test_all_endpoints.py`

#### O que é testado:

1. ✅ **Health Check** - Verifica se o serviço está online
2. ✅ **Register User** - Cria um novo utilizador
3. ✅ **Login** - Autentica e recebe tokens JWT
4. ✅ **Get Profile** - Obtém dados do utilizador logado
5. ✅ **Refresh Token** - Renova o access token
6. ✅ **Verify Token** - Valida token (endpoint para serviços internos)
7. ✅ **Logout** - Termina a sessão
8. ✅ **Invalid Token** - Testa rejeição de tokens inválidos
9. ✅ **Duplicate Email** - Testa rejeição de emails duplicados

#### Como Correr os Testes

**Opção 1: Com Docker (Recomendado)**

```bash
# Certifica-te que o serviço está rodando
docker compose ps

# Se não estiver, inicia:
docker compose up -d

# Espera 10 segundos para os containers iniciarem completamente
sleep 10

# Agora corre os testes
python test_all_endpoints.py
```

**Opção 2: Com Python Local**

```bash
# Entra na pasta do projeto
cd auth-service

# Ativa o ambiente virtual
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Certifica-te que o serviço está rodando:
uvicorn app.main:app --reload  # Em outro terminal

# Em um terminal diferente, corre os testes:
python test_all_endpoints.py
```

#### Saída Esperada

```
╔════════════════════════════════════════════════════════════════╗
║  🔐 AUTH SERVICE - COMPLETE API TEST SUITE                    ║
║  2026-03-02 16:45:30                                          ║
╚════════════════════════════════════════════════════════════════╝

✅ Service is running at http://localhost:8000

══════════════════════════════════════════════════════════════════════
                        Test 1: Health Check
══════════════════════════════════════════════════════════════════════

✅ Health check passed!

══════════════════════════════════════════════════════════════════════
TEST SUMMARY
══════════════════════════════════════════════════════════════════════

1. Health Check: PASS
2. Register User: PASS
3. Login: PASS
4. Get Profile: PASS
5. Refresh Token: PASS
6. Verify Token: PASS
7. Logout: PASS
8. Invalid Token: PASS
9. Duplicate Email: PASS

Total: 9/9 tests passed

🎉 ALL TESTS PASSED! 🎉
```

#### Requisitos para Testes

O ficheiro de testes já inclui `httpx` que está nas dependências do `requirements.txt`:

```bash
pip install -r requirements.txt
```

Se precisares apenas da dependência de teste:

```bash
pip install httpx
```

---

## 📝 Próximos Passos

- [ ] Implementar Redis para token denylist (logout robusto)
- [ ] Adicionar testes unitários com pytest
- [ ] Configurar CI/CD (GitHub Actions)
- [ ] Adicionar rate limiting
- [ ] Implementar 2FA (autenticação dois fatores)
- [ ] Adicionar logging estruturado
- [ ] Docker e Docker Compose

---

## 🤝 Integração com Outros Serviços

### Exemplo: Inventory Service valida token

```python
import httpx

async def validate_user_token(token: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://auth-service:8000/api/v1/auth/verify",
            json={"token": token}
        )
        return response.json()
```

---

## 📧 Suporte

Para questões ou problemas, contacte o desenvolvedor.

---

**Desenvolvido com ❤️ usando FastAPI**
