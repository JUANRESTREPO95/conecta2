"""Conecta2 — Agente gráfico.

Al abrirlo queda escondido en la bandeja (junto al reloj/wifi), con un
ícono propio. Doble clic en el ícono = ventana con estado en vivo.
Corre sus ciclos solo mientras esté abierto; al darle "Salir" se para.

La configuración (URL del panel, TOKEN del agente, carpeta de datos de A2
y depósito) se edita desde la ventana "Configuración" del propio programa;
se guarda en config_agente.json.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import pathlib
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from datetime import datetime

CARPETA = (pathlib.Path(sys.executable).resolve().parent
           if getattr(sys, "frozen", False)
           else pathlib.Path(__file__).resolve().parent)
sys.path.insert(0, str(CARPETA))

# estilo "Vibrante & Por bloques" (ui-ux-pro-max)
AZUL = "#1e40af"          # bloque principal
AZUL_OSCURO = "#173380"
FONDO = "#eef2f8"         # fondo con tinte
SUPERFICIE = "#ffffff"
TEXTO = "#0f172a"
SUAVE = "#47566b"
VERDE = "#16a34a"
ROJO = "#dc2626"
AMARILLO = "#f59e0b"
FUENTE = "Segoe UI"

ARCHIVO_CONFIG = CARPETA / "config_agente.json"
RUTA_ICONO = str(CARPETA / "icono_agente.ico")
WM_APP = 32768
WM_TRAY = WM_APP + 1000
MENU_ABRIR, MENU_CICLO, MENU_CONFIG, MENU_SALIR = (
    WM_TRAY + 1, WM_TRAY + 2, WM_TRAY + 3, WM_TRAY + 4)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


# piezas de ctypes.wintypes que no vienen en esta versión
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
IMAGE_ICON, LR_DEFAULTSIZE, LR_LOADFROMFILE = 1, 0x0040, 0x0010


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR), ("lpszClassName", wt.LPCWSTR)]


def crear_icono() -> str:
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(30, 64, 175, 255))
    d.ellipse((32, 10, 54, 32), fill=(147, 197, 253, 255))
    d.ellipse((10, 24, 32, 46), fill=(59, 130, 246, 255))
    d.ellipse((22, 38, 44, 60), fill=(191, 219, 254, 255))
    d.rounded_rectangle((6, 6, 58, 58), radius=12, outline="white", width=2)
    img.save(RUTA_ICONO, sizes=[(16, 16), (32, 32), (64, 64)])
    return RUTA_ICONO


class BandejaWin:
    """Ícono en la bandeja del sistema con menú (Shell_NotifyIcon puro)."""

    def __init__(self, app: "App"):
        self.app = app
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32
        self._ref_wndproc = WNDPROC(self._wndproc)  # conserva la referencia

        clase = WNDCLASSW()
        clase.lpfnWndProc = self._ref_wndproc
        clase.lpszClassName = "Conecta2AgenteTray"
        clase.hInstance = self.kernel32.GetModuleHandleW(None)
        self.user32.RegisterClassW(ctypes.byref(clase))
        self.hwnd = self.user32.CreateWindowExW(
            0, clase.lpszClassName, "Conecta2 Agente", 0, 0, 0, 0, 0,
            None, None, clase.hInstance, None)
        self.hicon = wt.HICON(self.user32.LoadImageW(
            None, RUTA_ICONO, IMAGE_ICON, 0, 0,
            LR_DEFAULTSIZE | LR_LOADFROMFILE))
        self._agregar()
        self.menu = self.user32.CreatePopupMenu()
        self.user32.AppendMenuW(self.menu, 0, MENU_ABRIR, "Abrir panel")
        self.user32.AppendMenuW(self.menu, 0, MENU_CONFIG, "Configuración")
        self.user32.AppendMenuW(self.menu, 0, MENU_CICLO, "Correr ciclo ahora")
        self.user32.AppendMenuW(self.menu, 0x800, 0, None)
        self.user32.AppendMenuW(self.menu, 0, MENU_SALIR, "Salir")

        threading.Thread(target=self._bombea, daemon=True).start()

    class NID(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND),
                    ("uID", wt.UINT), ("uFlags", wt.UINT),
                    ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON),
                    ("szTip", wt.WCHAR * 128), ("dwState", wt.DWORD),
                    ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                    ("uVersion", wt.DWORD), ("szInfoTitle", wt.WCHAR * 64),
                    ("dwInfoFlags", wt.DWORD), ("guidItem", GUID)]

    def _nid(self) -> "BandejaWin.NID":
        guid = GUID()
        ctypes.windll.ole32.CLSIDFromString(
            "{5C36A9F0-D2C4-4F2C-B24E-1A2B3C4D5E6F}", ctypes.byref(guid))
        nid = self.NID()
        nid.cbSize = ctypes.sizeof(self.NID)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = 0x1 | 0x2 | 0x4      # MESSAGE | ICON | TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self.hicon
        nid.szTip = "Conecta2 Agente"
        nid.guidItem = guid
        return nid

    def _agregar(self) -> None:
        shell32 = ctypes.windll.shell32
        self.registrado = bool(
            shell32.Shell_NotifyIconW(0, ctypes.byref(self._nid())))

    def _quitar(self) -> None:
        ctypes.windll.shell32.Shell_NotifyIconW(2, ctypes.byref(self._nid()))

    def _bombea(self) -> None:
        msg = wt.MSG()
        while self.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            self.user32.TranslateMessage(ctypes.byref(msg))
            self.user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam) -> int:  # noqa: ARG002
        def avisa(accion: str) -> None:
            self.app.cola.put(("ACCION", accion))
        if msg == WM_TRAY:
            evento = lparam & 0xFFFF
            if evento in (0x0202, 0x0203):
                avisa("abrir")
            elif evento == 0x0205:
                punto = wt.POINT()
                self.user32.GetCursorPos(ctypes.byref(punto))
                self.user32.SetForegroundWindow(self.hwnd)
                self.user32.TrackPopupMenu(self.menu, 0x0000,
                                           punto.x, punto.y, 0, self.hwnd, None)
        elif msg == MENU_ABRIR:
            avisa("abrir")
        elif msg == MENU_CONFIG:
            avisa("config")
        elif msg == MENU_CICLO:
            avisa("ciclo")
        elif msg == MENU_SALIR:
            avisa("salir")
            return 0
        return self.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def cerrar(self) -> None:
        self._quitar()


class App:
    def __init__(self) -> None:
        self.config = self._leer_config()
        for clave, var in (("api", "CONECTA2_API_URL"), ("token", "CONECTA2_TOKEN"),
                           ("a2_data", "CONECTA2_A2_DATA")):
            os.environ[var] = str(self.config.get(clave) or "")
        os.environ["CONECTA2_DEPOSITO"] = str(self.config.get("deposito") or 1)

        try:
            import agente as modulo_agente
        except Exception as error:
            import tkinter.messagebox as _mb
            _mb.showerror(
                "Conecta2 Agente",
                "El agente no pudo iniciar:\n\n" + str(error) +
                "\n\nSi dice pyodbc, instalalo con:\n"
                "python -m pip install pyodbc")
            raise SystemExit(1)
        self.ag = modulo_agente
        self.cola = queue.Queue()
        self.ag.COLAS.append(self.cola)

        self.root = tk.Tk()
        self.root.title("Conecta2 — Agente")
        self.root.geometry("660x480")
        self.root.protocol("WM_DELETE_WINDOW", self.a_bandeja)
        self.root.configure(bg=FONDO)

        cabecera = tk.Frame(self.root, bg=AZUL)
        cabecera.pack(fill="x")
        tk.Label(cabecera, text="Conecta2", bg=AZUL, fg="white",
                 font=(FUENTE, 18, "bold"), anchor="w").pack(
            anchor="w", padx=16, pady=(12, 0))
        tk.Label(cabecera, text="Agente de A2 — pedidos y catálogo",
                 bg=AZUL, fg="#dbe4ff", font=(FUENTE, 10), anchor="w").pack(
            anchor="w", padx=16, pady=(0, 12))

        panel = tk.Frame(self.root, bg=FONDO)
        panel.pack(fill="x", padx=12, pady=8)
        self.chip_panel = self._chip(panel, "PANEL / API", 0, 0)
        self.chip_ultimo = self._chip(panel, "ÚLTIMO CICLO", 0, 2)
        self.chip_montados = self._chip(panel, "PEDIDOS MONTADOS", 1, 0)
        self.chip_errores = self._chip(panel, "ERRORES", 1, 2)
        for columna in range(4):
            panel.columnconfigure(columna, weight=1)

        botones = tk.Frame(self.root, bg=FONDO)
        botones.pack(fill="x", padx=12, pady=6)
        self._boton(botones, "Correr ciclo ahora", self.ciclo_manual, AZUL).pack(side="left")
        self._boton(botones, "Configuración", self.abrir_config, SUPERFICIE,
                    tinta=AZUL, borde=AZUL).pack(side="left", padx=8)
        self._boton(botones, "Guardar en la bandeja", self.a_bandeja, SUPERFICIE,
                    tinta=SUAVE).pack(side="left")
        self._boton(botones, "Salir", self.pide_salir, ROJO).pack(side="right")

        tk.Label(self.root, text="Registro de actividad", bg=FONDO, fg=SUAVE,
                 font=(FUENTE, 9, "bold"), anchor="w").pack(fill="x", padx=14)
        self.log = scrolledtext.ScrolledText(self.root, height=13, state="disabled",
                                             font=("Consolas", 9), bg="#0f172a",
                                             fg="#e2e8f0", relief="flat",
                                             padx=10, pady=8)
        self.log.pack(fill="both", expand=True, padx=12, pady=(2, 12))

        crear_icono()
        self.bandeja = BandejaWin(self)
        if getattr(self.bandeja, "registrado", True):
            self.root.withdraw()
        threading.Thread(target=self._bucle_ciclos, daemon=True).start()
        self.root.after(400, self._refresca)

        if not self.config.get("token") or not self.config.get("a2_data"):
            self.abrir_ventana()
            self.abrir_config()

    # ---------- configuración ----------

    def _leer_config(self) -> dict:
        try:
            return json.loads(ARCHIVO_CONFIG.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _guardar_config(self, valores: dict) -> None:
        ARCHIVO_CONFIG.write_text(json.dumps(valores, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        self.config.update(valores)
        # aplicar en caliente (sin reiniciar)
        self.ag.API = valores["api"].rstrip("/")
        self.ag.TOKEN = valores["token"]
        self.ag.A2_DATA = valores["a2_data"]
        self.ag.DEPOSITO = int(valores.get("deposito") or 1)

    def abrir_config(self) -> None:
        self.abrir_ventana()
        if getattr(self, "_config_win", None) and tk.Toplevel.winfo_exists(self._config_win):
            self._config_win.lift()
            return
        v = tk.Toplevel(self.root)
        self._config_win = v
        v.title("Configuración del agente")
        v.geometry("560x420")
        v.configure(bg="white")
        v.transient(self.root)

        c = self.config
        campos = {}
        for fila, (etiqueta, clave, ancho) in enumerate([
                ("URL del panel (https://...)", "api", 46),
                ("TOKEN del agente (lo da el panel en Empresas)", "token", 46),
                ("Carpeta de datos de A2 (Empre001\\Data)", "a2_data", 36),
                ("Depósito para los pedidos (1 o 2)", "deposito", 6)]):
            tk.Label(v, text=etiqueta, bg="white", anchor="w",
                     font=("Segoe UI", 9, "bold")).grid(
                row=fila * 2, column=0, columnspan=2, sticky="w", padx=14,
                pady=(12 if fila == 0 else 8, 0))
            e = tk.Entry(v, width=ancho, font=("Consolas", 10))
            e.grid(row=fila * 2 + 1, column=0, sticky="we", padx=14, pady=2)
            e.insert(0, str(c.get(clave) or ""))
            campos[clave] = e
            if clave == "a2_data":
                tk.Button(v, text="Buscar…", command=lambda e=e: self._elegir_carpeta(e)
                          ).grid(row=fila * 2 + 1, column=1, padx=(0, 14))
        v.columnconfigure(0, weight=1)

        estado = tk.Label(v, text="", bg="white", fg="#0f172a", anchor="w",
                          font=("Segoe UI", 9))
        estado.grid(row=8, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 0))

        def probar():
            import urllib.request, urllib.error
            url = campos["api"].get().strip().rstrip("/")
            token = campos["token"].get().strip()
            estado.config(text="Probando…", fg="#0f172a")
            v.update_idletasks()
            try:
                req = urllib.request.Request(url + "/api/saludo")
                req.add_header("Authorization", "Bearer " + token)
                try:
                    resp = urllib.request.urlopen(req, timeout=15)
                except Exception:
                    import ssl as _ssl
                    ctx = _ssl.create_default_context()
                    ctx.maximum_version = _ssl.TLSVersion.TLSv1_2
                    resp = urllib.request.urlopen(req, timeout=15, context=ctx)
                with resp as r:
                    d = json.loads(r.read().decode())
                estado.config(text=f"✓ Conectado — empresa {d.get('empresa')}",
                              fg="#15803d")
            except urllib.error.HTTPError as e:
                estado.config(text=f"El panel respondió {e.code} (¿token)?",
                              fg="#b91c1c")
            except Exception as e:
                estado.config(text=f"No conecta: {str(e)[:80]}", fg="#b91c1c")

        def guardar():
            valores = {k: e.get().strip() for k, e in campos.items()}
            if not valores["api"] or not valores["token"] or not valores["a2_data"]:
                estado.config(text="Faltan datos: URL, token y carpeta de A2.",
                              fg="#b91c1c")
                return
            try:
                valores["deposito"] = int(valores.get("deposito") or 1)
            except ValueError:
                valores["deposito"] = 1
            self._guardar_config(valores)
            estado.config(text="Guardado. El agente ya usa esta configuración.",
                          fg="#15803d")

        barra = tk.Frame(v, bg="white")
        barra.grid(row=9, column=0, columnspan=2, sticky="we", padx=14, pady=12)
        tk.Button(barra, text="Probar conexión", command=probar).pack(side="left")
        tk.Button(barra, text="Guardar", command=guardar, bg="#1e40af",
                  fg="white", relief="flat").pack(side="left", padx=8)
        tk.Button(barra, text="Cerrar", command=v.destroy).pack(side="right")

    def _elegir_carpeta(self, entry) -> None:
        ruta = filedialog.askdirectory(title="Carpeta Data de A2 (Empre001\\Data)")
        if ruta:
            entry.delete(0, "end")
            entry.insert(0, ruta.replace("/", "\\"))

    # ---------- interfaz ----------

    def _boton(self, padre, texto: str, orden, color: str,
               tinta: str = "white", borde: str = "") -> tk.Button:
        return tk.Button(padre, text=texto, command=orden, bg=color, fg=tinta,
                         activebackground=color, activeforeground=tinta,
                         bd=0, relief="flat", padx=14, pady=6, cursor="hand2",
                         font=(FUENTE, 9, "bold"),
                         highlightthickness=1 if borde else 0,
                         highlightbackground=borde or color)

    def _chip(self, padre, titulo: str, fila: int, col: int) -> tk.Label:
        caja = tk.Frame(padre, bg=SUPERFICIE, highlightbackground="#d9e2ef",
                        highlightthickness=1)
        caja.grid(row=fila, column=col, sticky="we", padx=6, pady=4)
        tarjeta = tk.Frame(caja, bg=SUPERFICIE)
        tarjeta.pack(fill="both", expand=True, padx=12, pady=8)
        tk.Label(tarjeta, text=titulo, bg=SUPERFICIE, fg=SUAVE,
                 font=(FUENTE, 8, "bold"), anchor="w").pack(fill="x")
        chip = tk.Label(tarjeta, text="—", bg=SUPERFICIE, fg=TEXTO,
                        font=(FUENTE, 12, "bold"), anchor="w")
        chip.pack(fill="x")
        return chip

    def _bucle_ciclos(self) -> None:
        import time
        while True:
            try:
                self.ag.ciclo()
            except Exception as e:
                self.cola.put((datetime.now().strftime("%H:%M:%S"),
                               f"ERROR del ciclo: {str(e)[:150]}"))
            time.sleep(30)

    def _correr_ciclo(self, primera: bool = False) -> None:
        try:
            self.ag.ciclo(primera=primera)
        except Exception as e:
            self.cola.put((datetime.now().strftime("%H:%M:%S"),
                           f"ERROR del ciclo: {str(e)[:150]}"))

    def pide_salir(self) -> None:
        """Muestra la ventana y pregunta si de verdad desea salir."""
        self.abrir_ventana()
        if messagebox.askyesno(
                "Salir del agente",
                "¿Desea salir del agente?\n\n"
                "Mientras esté cerrado no se montarán pedidos en A2 "
                "ni se sincronizará el catálogo.",
                parent=self.root):
            self.salir()

    def ciclo_manual(self) -> None:
        threading.Thread(target=lambda: self._correr_ciclo(primera=True),
                         daemon=True).start()

    def _refresca(self) -> None:
        e = self.ag.ESTADO
        conectado = e["panel"] == "conectado"
        self.chip_panel.config(
            text="conectado" if conectado else "sin conexión",
            fg="#16a34a" if conectado else "#dc2626")
        self.chip_ultimo.config(text=e["ultimo_ciclo"] or "—")
        self.chip_montados.config(text=str(e["montados"]))
        self.chip_errores.config(text=str(e["errores"]),
                                 fg="#dc2626" if e["errores"] else "#0f172a")
        try:
            while True:
                item = self.cola.get_nowait()
                if item[0] == "ACCION":
                    if item[1] == "abrir":
                        self.abrir_ventana()
                    elif item[1] == "config":
                        self.abrir_config()
                    elif item[1] == "ciclo":
                        self.ciclo_manual()
                    elif item[1] == "salir":
                        self.pide_salir()
                        continue
                    continue
                hora, texto = item
                self.log.config(state="normal")
                self.log.insert("end", f"{hora}  {texto}\n")
                self.log.yview_moveto(1.0)
                self.log.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(400, self._refresca)

    def abrir_ventana(self) -> None:
        self.root.deiconify()
        self.root.lift()

    def a_bandeja(self) -> None:
        self.root.withdraw()

    def salir(self) -> None:
        try:
            if self.bandeja:
                self.bandeja.cerrar()
        finally:
            self.root.destroy()
            os._exit(0)

    def correr(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    App().correr()
