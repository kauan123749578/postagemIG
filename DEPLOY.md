# Deploy na Railway

Guia rápido para subir o **Postagem IG** na Railway e testar publicação de Reels.

## 1. Criar repositório no GitHub

```powershell
cd c:\Users\kauan\Downloads\postagemIG
git init
git add .
git commit -m "Postagem IG - painel Meta API"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/postagemIG.git
git push -u origin main
```

> O `.env` **não vai** pro GitHub (está no `.gitignore`). Configure as variáveis na Railway.

---

## 2. Criar projeto na Railway

1. Acesse [railway.app](https://railway.app) e faça login
2. **New Project** → **Deploy from GitHub repo**
3. Selecione o repositório `postagemIG`
4. A Railway detecta o `Dockerfile` automaticamente

---

## 3. Gerar domínio público

1. No serviço → aba **Settings** → **Networking**
2. Clique em **Generate Domain**
3. Anote a URL: `https://seu-app.up.railway.app`

A variável `RAILWAY_PUBLIC_DOMAIN` é injetada automaticamente — o app usa ela para gerar URLs dos vídeos para a Meta.

---

## 4. PostgreSQL (recomendado — banco persistente)

1. No projeto Railway → **+ New** → **Database** → **PostgreSQL**
2. Abra o serviço **postagemIG** → aba **Variables**
3. **Add Reference** → selecione o Postgres → marque **`DATABASE_URL`**
4. Redeploy o postagemIG

O app detecta `DATABASE_URL` automaticamente e usa PostgreSQL em vez de SQLite.
Contas, tokens, agendamentos, loops e logs ficam no Postgres — **não somem no redeploy**.

---

## 5. Volume persistente para vídeos (obrigatório)

O Postgres guarda só o banco. **Vídeos** precisam de volume no serviço postagemIG:

1. **+ New** → **Volume** → conecte ao serviço **postagemIG**
2. **Mount path:** `/data`
3. Variável: `DATA_DIR=/data`

Isso persiste:
- Vídeos uploadados (`/data/uploads/`)

---

## 6. Variáveis de ambiente

Na aba **Variables** do serviço, adicione:

| Variável | Valor |
|----------|-------|
| `SECRET_KEY` | Chave aleatória longa (ex: output de `openssl rand -hex 32`) |
| `ADMIN_USERNAME` | `admin` |
| `ADMIN_PASSWORD` | Senha forte (mín. 12 caracteres) |
| `DATA_DIR` | `/data` |
| `DATABASE_URL` | Referência automática do serviço Postgres |
| `ENV` | `production` |

Opcional (se quiser forçar URL manualmente):

| Variável | Valor |
|----------|-------|
| `APP_BASE_URL` | `https://seu-app.up.railway.app` |

---

## 7. Deploy e teste

Após o deploy:

1. Acesse `https://seu-app.up.railway.app/login`
2. Entre com `ADMIN_USERNAME` / `ADMIN_PASSWORD`
3. **Contas** → cadastre IG User ID + Access Token
4. **Mídia** → upload do vídeo em lote
5. **Publicar** → Reel → publicar

A Meta vai baixar o vídeo de:
```
https://seu-app.up.railway.app/media/videos/arquivo.mp4
```

---

## Checklist pós-deploy

- [ ] Domínio público gerado
- [ ] Postgres criado e `DATABASE_URL` referenciado no postagemIG
- [ ] Volume montado em `/data` (vídeos)
- [ ] `SECRET_KEY` e `ADMIN_PASSWORD` configurados
- [ ] Login no painel funciona
- [ ] Conta Instagram cadastrada
- [ ] Vídeo aparece em **Mídia** após upload
- [ ] Teste de Reel publicado

---

## Problemas comuns

| Erro | Solução |
|------|---------|
| Erro 2207076 | URL do vídeo inacessível — confirme domínio público e volume |
| 401 no login | Verifique `ADMIN_PASSWORD` nas variáveis Railway |
| Vídeos sumiram | Volume `/data` no serviço postagemIG |
| Contas sumiram | Vincule `DATABASE_URL` do Postgres ao postagemIG |
| Token inválido | Gere novo token no Meta Developers |

---

## Comandos úteis

Ver logs na Railway:
- Aba **Deployments** → clique no deploy → **View Logs**

Redeploy manual:
- **Deployments** → **Redeploy**
