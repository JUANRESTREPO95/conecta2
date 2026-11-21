# Instalador del Agente Conecta2 (solo el .exe del agente)
# NO instala Python ni pyodbc: el agente ya los lleva embebidos.
# El driver DBISAM ODBC (32 bits) se instala aparte, a mano.
# Copia Conecta2Agente.exe a C:\Conecta2\agente, escribe la configuracion,
# prueba la conexion y crea el acceso directo en el Escritorio.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName Microsoft.VisualBasic

$AQUI = Split-Path -Parent $MyInvocation.MyCommand.Path
$DESTINO = "C:\Conecta2\agente"
$LOG = "C:\Conecta2\instalador.log"
New-Item -ItemType Directory -Force -Path "C:\Conecta2" | Out-Null
function Log($texto) {
    Add-Content -Path $LOG -Value ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $texto) -Encoding UTF8
}
Log "=== Instalacion del agente Conecta2 ==="
Log "Windows: $([Environment]::OSVersion.VersionString) | 64 bits: $([Environment]::Is64BitOperatingSystem)"

function Aviso($texto, $titulo = "Conecta2") {
    [Microsoft.VisualBasic.Interaction]::MsgBox($texto, "OKOnly,Information", $titulo) | Out-Null
}
function Pregunta($texto, $defecto = "") {
    [Microsoft.VisualBasic.Interaction]::InputBox($texto, "Conecta2 - configuracion", $defecto)
}

# --- 1. permisos de administrador (para crear C:\Conecta2) ---
$identidad = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identidad)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Aviso "Este instalador necesita permisos de administrador. Se abrira de nuevo; acepta el aviso de Windows."
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        "-STA", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
    exit
}

# --- 2. el driver DBISAM debe estar instalado (lo pone Juan aparte) ---
$drivers = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\ODBC\ODBCINST.INI\ODBC Drivers" -ErrorAction SilentlyContinue
$tieneDriver = $false
if ($drivers) {
    $tieneDriver = $drivers.PSObject.Properties.Name -contains "DBISAM 4 ODBC Driver"
}
Log "Driver DBISAM 32 bits instalado: $tieneDriver"
if (-not $tieneDriver) {
    $seguir = [Microsoft.VisualBasic.Interaction]::MsgBox(
        "No encuentro el driver DBISAM ODBC (32 bits) en este PC.`n`nEl agente no podra leer A2 sin el. Instalalo y vuelve a ejecutar este instalador.`n`nQuieres continuar de todos modos?",
        "YesNo,Question", "Conecta2")
    if ($seguir -ne "Yes") { exit }
}

# --- 3. datos de conexion ---
$url = Pregunta "URL del panel (ejemplo: https://pedidos.tudominio.com)"
if (-not $url) { exit }
$token = Pregunta "TOKEN del agente (panel -> Empresas -> Token del agente -> Copiar)"
if (-not $token) { exit }

$carpeta = New-Object System.Windows.Forms.FolderBrowserDialog
$carpeta.Description = "Selecciona la carpeta Data de A2 (...\Empre001\Data)"
if ($carpeta.ShowDialog() -ne "OK") { exit }

$deposito = Pregunta "Deposito para los pedidos (1 o 2). Deja 1 si no sabes." "1"
if (-not $deposito) { $deposito = "1" }

# --- 4. copiar el agente ---
New-Item -ItemType Directory -Force -Path $DESTINO | Out-Null
Copy-Item (Join-Path $AQUI "Conecta2Agente.exe") (Join-Path $DESTINO "Conecta2Agente.exe") -Force
Log "Agente copiado a $DESTINO"

$config = @{
    api      = $url.Trim().TrimEnd("/")
    token    = $token.Trim()
    a2_data  = $carpeta.SelectedPath
    deposito = [int]$deposito
} | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $DESTINO "config_agente.json"), $config, [Text.Encoding]::UTF8)
Log "Config guardada"

# --- 5. probar la conexion ---
$probado = "No se pudo probar la conexion ahora."
try {
    $urlSaludo = $url.Trim().TrimEnd("/") + "/api/saludo"
    $resp = Invoke-RestMethod -Uri $urlSaludo `
        -Headers @{ Authorization = "Bearer $($token.Trim())" } -TimeoutSec 15
    if ($resp.ok) { $probado = "Conexion con el panel: OK (empresa $($resp.empresa))." }
} catch { $probado = "El panel no respondio todavia: revisa la URL/token." }

# --- 6. acceso directo en el Escritorio ---
$exe = Join-Path $DESTINO "Conecta2Agente.exe"
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "Conecta2 Agente.lnk"
$shell = New-Object -ComObject WScript.Shell
$acceso = $shell.CreateShortcut($lnk)
$acceso.TargetPath = $exe
$acceso.Arguments = ""
$acceso.WorkingDirectory = $DESTINO
$acceso.Description = "Agente Conecta2 (A2)"
$acceso.Save()

Log "Listo. api=$($url.Trim()) deposito=$deposito a2=$($carpeta.SelectedPath)"
Log $probado
Log "Acceso directo: $lnk"

$abrir = [Microsoft.VisualBasic.Interaction]::MsgBox(
    "Listo. El agente quedo en C:\Conecta2\agente.`n`n$probado`n`nQuieres abrir el agente ahora?",
    "YesNo,Question", "Conecta2")
if ($abrir -eq "Yes") {
    Start-Process -FilePath $exe -WorkingDirectory $DESTINO
} else {
    Aviso "Abrelo con el acceso directo 'Conecta2 Agente' del Escritorio.`n`nRegistro: $LOG"
}
