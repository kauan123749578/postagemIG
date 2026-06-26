# Postagem IG

Painel web para publicar no Instagram via **instagrapi** — Reels, Stories, loop automático e multi-conta.

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

## Login das contas Instagram

No painel **Contas**, conecte cada perfil com **sessionid** do navegador (recomendado) ou usuário/senha (+ 2FA se pedir). Use **proxy residencial** por conta em produção.

## Login do painel

Configure no `.env`:
```
ADMIN_USERNAME=admin
ADMIN_PASSWORD=sua-senha-forte
```
