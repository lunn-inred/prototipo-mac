param(
    [Parameter(Mandatory=$true)][string]$PostgresRoot,
    [Parameter(Mandatory=$true)][string]$TesseractRoot,
    [Parameter(Mandatory=$true)][string]$WebView2Installer,
    [Parameter(Mandatory=$true)][string]$VcRedist,
    [Parameter(Mandatory=$true)][string]$DeploymentConfig,
    [string]$Version = '1.0.0',
    [switch]$Clean,
    [string]$Iscc = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT' -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
    throw 'Execute o build dentro do Windows x64, não no Linux ou ARM.'
}
if ($Version -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') { throw 'Versão inválida.' }
$project = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Set-Location $project
$buildExecutable = Join-Path $project 'dist\MAC Performance\MAC Performance.exe'
if (Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $buildExecutable }) {
    throw 'Feche o aplicativo e seus processos de teste antes de compilar novamente.'
}
python -c "import sys,struct; assert sys.version_info[:2]==(3,11) and struct.calcsize('P')==8, 'Use Python 3.11 x64'"
if ($LASTEXITCODE -ne 0) { throw 'Use Python 3.11 x64 para este build.' }
foreach ($path in @("$PostgresRoot\bin\pg_ctl.exe", "$PostgresRoot\bin\initdb.exe", "$PostgresRoot\bin\pg_dump.exe", "$PostgresRoot\bin\pg_restore.exe", "$TesseractRoot\tesseract.exe", "$TesseractRoot\tessdata\por.traineddata", "$TesseractRoot\tessdata\eng.traineddata", $WebView2Installer, $VcRedist, $Iscc)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Dependência ausente: $path" }
}
if (-not (Test-Path -LiteralPath $DeploymentConfig -PathType Leaf)) { throw 'Arquivo de configuração OAuth Desktop ausente.' }
python -c "import json,sys; p=json.load(open(sys.argv[1],encoding='utf-8-sig')); required={'MAC_GOOGLE_ALLOWED_EMAIL','MAC_GOOGLE_DESKTOP_CLIENT_ID','MAC_GOOGLE_DESKTOP_CLIENT_SECRET','MAC_GOOGLE_BACKUP_FOLDER_ID'}; assert set(p)==required and all(isinstance(v,str) and v.strip() and not any(c in v for c in '\r\n\x00') for v in p.values())" $DeploymentConfig
if ($LASTEXITCODE -ne 0) { throw 'Configuração OAuth Desktop incompleta ou inválida.' }
$postgresVersion = & "$PostgresRoot\bin\pg_ctl.exe" --version
if ($LASTEXITCODE -ne 0 -or $postgresVersion -notmatch 'PostgreSQL\) 17\.') { throw 'Use binários PostgreSQL 17 x64.' }
foreach ($path in @("$PostgresRoot\bin\pg_ctl.exe", "$TesseractRoot\tesseract.exe")) {
    $reader = New-Object System.IO.BinaryReader([System.IO.File]::OpenRead($path))
    try {
        $reader.BaseStream.Position = 0x3c
        $reader.BaseStream.Position = $reader.ReadInt32()
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) { throw "Binário não é PE x64: $path" }
    } finally { $reader.Dispose() }
}
if ((Get-Item -LiteralPath $WebView2Installer).Length -lt 50MB) { throw 'Use o instalador WebView2 Standalone completo, não o bootstrapper.' }
foreach ($path in @($WebView2Installer, $VcRedist)) {
    $signature = Get-AuthenticodeSignature -LiteralPath $path
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
        throw "Assinatura Microsoft não validada: $path"
    }
}
foreach ($root in @($PostgresRoot, $TesseractRoot)) {
    if (-not (Get-ChildItem -LiteralPath $root -File | Where-Object { $_.Name -match 'license|copying|copyright' })) {
        throw "Inclua o arquivo de licença na raiz do fornecedor: $root"
    }
}
$buildArguments = @('-m', 'PyInstaller', '--noconfirm')
if ($Clean) { $buildArguments += '--clean' }
$buildArguments += 'desktop/desktop.spec'
python @buildArguments
if ($LASTEXITCODE -ne 0) { throw 'O build PyInstaller falhou.' }
$app = Join-Path $project 'dist/MAC Performance'
$runtime = Join-Path $app 'runtime'
New-Item -ItemType Directory -Force -Path "$runtime/pgsql", "$runtime/tesseract", "$runtime/prerequisites" | Out-Null
foreach ($folder in @('bin','lib','share')) {
    Copy-Item -LiteralPath "$PostgresRoot/$folder" -Destination "$runtime/pgsql" -Recurse -Force
}
Get-ChildItem -LiteralPath $PostgresRoot -File | Where-Object { $_.Name -match 'license|copying|copyright' } | Copy-Item -Destination "$runtime/pgsql"
Copy-Item -Path "$TesseractRoot/*" -Destination "$runtime/tesseract" -Recurse -Force
Copy-Item -LiteralPath $WebView2Installer -Destination "$runtime/prerequisites/WebView2Setup.exe"
Copy-Item -LiteralPath $VcRedist -Destination "$runtime/prerequisites/VC_redist.x64.exe"
Copy-Item -LiteralPath $DeploymentConfig -Destination "$app/deployment.json"
$files = Get-ChildItem -LiteralPath $runtime -Recurse -File | ForEach-Object {
    @{ file=$_.FullName.Substring($app.Length+1); sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
}
$files | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath "$app/runtime-manifest.json" -Encoding UTF8
Copy-Item -LiteralPath 'infrastructure/windows/THIRD-PARTY-NOTICES.txt' -Destination $app
& $Iscc "/DAppVersion=$Version" "/DAppSource=$app" 'infrastructure/windows/mac.iss'
if ($LASTEXITCODE -ne 0) { throw 'O build do instalador falhou.' }
Get-ChildItem 'dist/installer/*.exe' | Get-FileHash -Algorithm SHA256
