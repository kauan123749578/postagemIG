# Gera uma pasta de entrega ZERADA para o cliente.
# Copia somente o codigo-fonte necessario, sem dados, sessoes, senhas ou ambiente virtual.
# Uso: clique direito > "Executar com PowerShell"  (ou)  powershell -ExecutionPolicy Bypass -File criar_entrega.ps1

$ErrorActionPreference = "Stop"
$origem = $PSScriptRoot
$destino = Join-Path (Split-Path $origem -Parent) "PostagemIG-Entrega"

Write-Host "Origem : $origem"
Write-Host "Destino: $destino"

if (Test-Path $destino) {
    Remove-Item $destino -Recurse -Force
}
New-Item -ItemType Directory -Path $destino | Out-Null

# Itens que SEMPRE ficam de fora (dados do desenvolvedor / lixo)
$excluir = @(
    "data", ".venv", "build", "dist", "__pycache__",
    "session.json", "*.pyc", "*.mp4", "*.jpg", "*.jpeg", "*.png",
    "*.spec", "PostagemIG-Entrega", ".git"
)

robocopy $origem $destino /E /XD ".git" ".venv" "data" "build" "dist" "__pycache__" /XF "session.json" "*.pyc" "*.mp4" "*.jpg" "*.jpeg" "*.png" "*.spec" | Out-Null

# Remove qualquer __pycache__ residual
Get-ChildItem $destino -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# Garante que a pasta data comece vazia no cliente
New-Item -ItemType Directory -Path (Join-Path $destino "data") -Force | Out-Null

Write-Host ""
Write-Host "Pasta de entrega criada com sucesso em:" -ForegroundColor Green
Write-Host "  $destino" -ForegroundColor Green
Write-Host ""
Write-Host "Entregue essa pasta ao cliente. Ele so precisa dar duplo clique em 'iniciar.bat'." -ForegroundColor Yellow
