# Gera pasta de entrega com o EXECUTAVEL para o cliente.
# Rode APOS gerar o .exe:  .\.venv\Scripts\python.exe -m PyInstaller --noconfirm PostagemIG.spec
# Uso: powershell -ExecutionPolicy Bypass -File criar_entrega_exe.ps1

$ErrorActionPreference = "Stop"
$origem = $PSScriptRoot
$dist = Join-Path $origem "dist\PostagemIG"
$destino = Join-Path (Split-Path $origem -Parent) "PostagemIG-Entrega"

if (-not (Test-Path (Join-Path $dist "PostagemIG.exe"))) {
    Write-Host "ERRO: PostagemIG.exe nao encontrado em dist\PostagemIG" -ForegroundColor Red
    Write-Host "Gere o executavel primeiro:" -ForegroundColor Yellow
    Write-Host "  .\.venv\Scripts\python.exe -m PyInstaller --noconfirm PostagemIG.spec"
    exit 1
}

Write-Host "Origem (dist): $dist"
Write-Host "Destino      : $destino"

if (Test-Path $destino) {
    Remove-Item $destino -Recurse -Force
}
New-Item -ItemType Directory -Path $destino | Out-Null

robocopy $dist $destino /E /NFL /NDL /NJH /NJS | Out-Null

Copy-Item (Join-Path $origem "LEIA-ME-CLIENTE-EXE.txt") (Join-Path $destino "LEIA-ME.txt") -Force

# data vazia (opcional — o app cria sozinho na 1a execucao)
New-Item -ItemType Directory -Path (Join-Path $destino "data") -Force | Out-Null

$mb = [math]::Round(((Get-ChildItem $destino -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB), 1)
Write-Host ""
Write-Host "Pasta de entrega criada:" -ForegroundColor Green
Write-Host "  $destino" -ForegroundColor Green
Write-Host "  Tamanho: ~$mb MB" -ForegroundColor Green
Write-Host ""
Write-Host "Compacte em .zip e envie ao cliente. Ele so precisa extrair e clicar em PostagemIG.exe" -ForegroundColor Yellow
