# Postagem IG — App Desktop (instagrapi)

Painel desktop para publicar Reels no Instagram usando a biblioteca **instagrapi**, rodando **localmente** na sua máquina (login sai do seu IP residencial, evitando os bloqueios que aconteciam na nuvem).

## Funções

- **Contas**: conectar várias contas por usuário/senha (com popup de **2FA**) ou **sessionid** do navegador. Sessão salva e reaproveitada.
- **Publicar**: enviar um Reel (vídeo + legenda + capa opcional) na hora.
- **Loop contínuo**: publica uma lista de vídeos em sequência, repetindo no intervalo definido.
- **Agendamentos**: programa Reels para um horário futuro.
- **Mídia**: importa e organiza vídeos/imagens (ficam em `data/`).
- **Logs** e **Dashboard**: histórico de publicações e visão geral.
- Limites por conta (máx/dia e máx/hora) e proxy por conta.

## Como rodar (desenvolvimento)

Pré-requisito: Python 3.10+ instalado.

```powershell
cd instagramm
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install --no-deps moviepy==2.2.1
.venv\Scripts\python.exe main.py
```

Ou simplesmente dê duplo clique em **`iniciar.bat`** (cria o ambiente na primeira vez e abre o painel).

> O `moviepy` é instalado com `--no-deps` porque a instagrapi 2.16 usa Pillow 12 e o moviepy declara um limite antigo de Pillow — na prática funciona junto.

## Dados

Tudo fica na pasta `data/` ao lado do programa:
- `data/app.db` — banco SQLite (contas, loops, agendamentos, logs)
- `data/uploads/` — vídeos e imagens importados
- `data/secret.key` — chave que cifra as senhas das contas
- `data/sessions/` — reservado para sessões

Faça backup da pasta `data/` para não perder suas contas.

## Gerar o executável (.exe)

Será feito com **PyInstaller** ao final do projeto:

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --name "PostagemIG" main.py
```

O executável sai em `dist/PostagemIG/`.

## Dicas para evitar bloqueio do Instagram

- Prefira conectar por **sessionid** quando possível.
- Use **proxy** por conta se for rodar muitas contas.
- Respeite intervalos (o loop tem intervalo mínimo de 30s) e os limites por dia/hora.
