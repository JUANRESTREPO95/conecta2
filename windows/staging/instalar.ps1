# Instalador del Agente Conecta2
# Instala Python 32 bits y el driver DBISAM si faltan, pregunta la ruta del A2
# y la conexion al panel, copia el agente a C:\Conecta2\agente y crea el acceso
# directo. Ejecutar con el .bat que esta al lado (pide permisos de admin).

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

$AQUI = Split-Path -Parent $MyInvocation.MyCommand.Path
$DESTINO = "C:\Conecta2\agente"
$PYTHON_DIR = "C:\Conecta2\python32"

function Aviso($texto, $titulo = "Conecta2") {
    [Microsoft.VisualBasic.Interaction]::MsgBox($texto, "OKOnly,Information", $titulo) | Out-Null
}
function Pregunta($texto, $defecto = "") {
    [Microsoft.VisualBasic.Interaction]::InputBox($texto, "Conecta2 - configuracion", $defecto)
}

# --- 1. permisos de administrador ---
$identidad = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identidad)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Aviso "Este instalador necesita permisos de administrador. Se abrira de nuevo; acepta el aviso de Windows."
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        "-STA", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
    exit
}

Aviso "Instalador del Agente Conecta2.`n`nInstala Python y el driver de A2 si faltan, y deja el agente configurado."

# --- 2. Python 32 bits ---
$python = Join-Path $PYTHON_DIR "python.exe"
if (-not (Test-Path $python)) {
    $instalador = Join-Path $AQUI "instaladores\python-3.11.9-32.exe"
    if (-not (Test-Path $instalador)) {
        Aviso "No encuentro instaladores\python-3.11.9-32.exe junto al instalador."
        exit 1
    }
    Aviso "Instalando Python 3.11 (32 bits)... puede tardar un minuto."
    Start-Process -FilePath $instalador -Wait -ArgumentList @(
        "/quiet", "InstallAllUsers=1", "PrependPath=0", "Include_launcher=0",
        "TargetDir=$PYTHON_DIR")
}

# --- 3. pyodbc ---
$py = Join-Path $PYTHON_DIR "python.exe"
& $py -m pip install --quiet pyodbc 2>$null
& $py -c "import pyodbc" 2>$null
if ($LASTEXITCODE -ne 0) {
    Aviso "No se pudo instalar pyodbc (?sin internet?). El agente no podra leer A2."
}

# --- 4. driver DBISAM ODBC (32 bits) ---
$drivers = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI\ODBC Drivers" -ErrorAction SilentlyContinue
if (-not ($drivers.PSObject.Properties.Name -contains "DBISAM 4 ODBC Driver")) {
    $dbisam = Join-Path $AQUI "instaladores\DBISAM_ODBC_429b132bit.exe"
    if (Test-Path $dbisam) {
        Aviso "Instalando el driver DBISAM ODBC (32 bits)..."
        Start-Process -FilePath $dbisam -Wait -ArgumentList @("/VERYSILENT", "/NORESTART")
    } else {
        Aviso "No encuentro el instalador del driver DBISAM; instalalo a mano."
    }
}

# --- 5. datos de conexion ---
$url = Pregunta "URL del panel (ejemplo: https://panel.tudominio.com)"
if (-not $url) { exit }
$token = Pregunta "TOKEN del agente (lo ves en el panel: Empresas  Token del agente)"
if (-not $token) { exit }

$carpeta = New-Object System.Windows.Forms.FolderBrowserDialog
$carpeta.Description = "Selecciona la carpeta Data de A2 (...\Empre001\Data)"
if ($carpeta.ShowDialog() -ne "OK") { exit }

$deposito = Pregunta "Deposito para los pedidos (1 o 2). Dejalo en 1 si no sabes." "1"
if (-not $deposito) { $deposito = "1" }

# --- 6. copiar el agente ---
New-Item -ItemType Directory -Force -Path $DESTINO | Out-Null
Copy-Item (Join-Path $AQUI "agente\agente.py") $DESTINO -Force
Copy-Item (Join-Path $AQUI "agente\a2.py") $DESTINO -Force
Copy-Item (Join-Path $AQUI "agente\agente_grafico.py") $DESTINO -Force

$config = @{
    api       = $url.Trim().TrimEnd("/")
    token     = $token.Trim()
    a2_data   = $carpeta.SelectedPath
    deposito  = [int]$deposito
} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $DESTINO "config_agente.json"), $config, [Text.Encoding]::UTF8)

# --- 7. probar la conexion ---
$probado = "No se pudo probar la conexion ahora."
try {
    $urlSaludo = $url.Trim().TrimEnd("/") + "/api/saludo"
    $resp = Invoke-RestMethod -Uri $urlSaludo `
        -Headers @{ Authorization = "Bearer $($token.Trim())" } -TimeoutSec 15
    if ($resp.ok) { $probado = "Conexion con el panel: OK (empresa $($resp.empresa))." }
} catch { $probado = "El panel no respondio todavia: revisa la URL/token." }

# --- 8. acceso directo en el escritorio ---
$pythonw = "C:\Conecta2\python32\pythonw.exe"
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Conecta2 Agente.lnk"
$shell = New-Object -ComObject WScript.Shell
$acceso = $shell.CreateShortcut($lnk)
$acceso.TargetPath = $pythonw
$acceso.Arguments = "`"$DESTINO\agente_grafico.py`""
$acceso.WorkingDirectory = $DESTINO
$acceso.Description = "Agente Conecta2 (A2)"
$acceso.Save()

Aviso "Listo. El agente quedo en C:\Conecta2\agente y hay un acceso directo en el Escritorio.`n`n$probado`n`nAbrelo con el acceso directo: queda en la bandeja junto al reloj."
