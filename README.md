# Postagem IG

Painel web para publicar no Instagram via **API oficial da Meta** — Reels, Stories, loop automático e multi-conta.

## Deploy na Railway

Guia completo: **[DEPLOY.md](DEPLOY.md)**

Resumo:
1. Push do código no GitHub
2. Railway → Deploy from GitHub
3. Gerar domínio público
4. Montar volume em `/data`
5. Configurar `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`

## Rodar local

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python run.py
```

> Localhost **não funciona** para publicar — a Meta precisa de URL pública. Use Railway ou ngrok.

## Login padrão

Configure no `.env`:
```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=sua-senha-forte
```
