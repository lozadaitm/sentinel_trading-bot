"""Preparacion de los terminales MT5 antes de lanzar los bots (lo llama start_all).

Dos problemas operativos que se repetian en cada alta o reinicio (2026-10-14):

  1. Algo Trading APAGADO. El provisioner escribe [Experts] Enabled=1 en el
     config/common.ini del clon solo antes del PRIMER arranque; el terminal
     reescribe ese archivo y el boton puede quedar apagado. El bot lo detecta
     (APERTURAS BLOQUEADAS / CUENTA MUERTA) pero no opera. Aqui se fuerza
     [Experts] AllowLiveTrading=1 / Enabled=1 en CADA arranque. restart_all mata
     los terminales antes de llamar a start_all, asi que el terminal lo lee al
     abrir. Con el terminal abierto el cambio aplica en su proximo arranque.

  2. Version del terminal vs libreria MetaTrader5 de Python. MT5 se
     autoactualiza; con una actualizacion a medias o una libreria de otra build
     el terminal puede no atender el IPC (-10005). Se compara la build de cada
     terminal64.exe con la de la libreria y se avisa si difieren.

Solo toca clones PORTABLES (MT5_PORTABLE=true + MT5_PATH): el terminal base no
portable guarda su config en %APPDATA% y lo gestiona el operador.

Uso (desde la raiz):  python -m scripts.mt5_prep
"""

import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCES_DIR = os.path.join(ROOT, "instances")

EXPERTS_KEYS = (("AllowLiveTrading", "1"), ("Enabled", "1"))


def read_env(path):
    """KEY=VALUE de un .env (sin dependencia de python-dotenv)."""
    d = {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def active_env_files(instances_dir=INSTANCES_DIR):
    """Los mismos .env que lanza start_all (sin example*, template*, _*)."""
    out = []
    for p in sorted(glob.glob(os.path.join(instances_dir, "*.env"))):
        n = os.path.basename(p)
        if n.startswith(("example", "template", "_")):
            continue
        out.append(p)
    return out


def _read_ini(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-16-le") if b"\x00" in raw[:64] else raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-8", "ignore")


def ensure_algo_trading(ini_path):
    """Deja [Experts] AllowLiveTrading=1 y Enabled=1 en common.ini.

    Conserva el resto de secciones y claves. Crea el archivo si no existe.
    Escribe en UTF-16 (formato de los .ini de MT5). Devuelve True si cambio algo.
    """
    text = _read_ini(ini_path).lstrip("﻿") if os.path.exists(ini_path) else ""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    start = next((i for i, l in enumerate(lines) if l.strip().lower() == "[experts]"), None)
    if start is None:
        new = ["[Experts]"] + [f"{k}={v}" for k, v in EXPERTS_KEYS] + lines
    else:
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")),
                   len(lines))
        section = lines[start + 1:end]
        for key, val in EXPERTS_KEYS:
            idx = next((i for i, l in enumerate(section)
                        if l.split("=", 1)[0].strip().lower() == key.lower()), None)
            if idx is None:
                section.append(f"{key}={val}")
            else:
                section[idx] = f"{key}={val}"
        new = lines[:start + 1] + section + lines[end:]
    if new == lines:
        return False
    os.makedirs(os.path.dirname(ini_path), exist_ok=True)
    with open(ini_path, "w", encoding="utf-16", newline="") as f:
        f.write("\r\n".join(new) + "\r\n")
    return True


def build_of(version):
    """Build de una version MT5: '5.0.0.6230' -> 6230, '5.0.6231' -> 6231."""
    nums = re.findall(r"\d+", str(version or ""))
    return int(nums[-1]) if nums else None


def builds_compatible(terminal_build, lib_build):
    """La libreria publica builds propias (p. ej. 6231 para el terminal 6230):
    se aceptan como compatibles las que difieren en menos de 10."""
    if terminal_build is None or lib_build is None:
        return True
    return abs(terminal_build - lib_build) < 10


def exe_version(path):
    """FileVersion de un .exe via PowerShell (sin pywin32). None si falla."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Item -LiteralPath '{path}').VersionInfo.FileVersion"],
            capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def lib_version():
    try:
        import MetaTrader5 as mt5
        return getattr(mt5, "__version__", None)
    except Exception:  # noqa: BLE001
        return None


def main():
    lib = lib_version()
    lib_build = build_of(lib)
    warnings = 0
    seen = set()
    for env_path in active_env_files():
        env = read_env(env_path)
        name = os.path.basename(env_path)[:8]
        exe = env.get("MT5_PATH", "")
        if not exe or exe in seen:
            continue
        seen.add(exe)
        if env.get("MT5_PORTABLE", "").lower() == "true":
            ini = os.path.join(os.path.dirname(exe), "config", "common.ini")
            changed = ensure_algo_trading(ini)
            print(f"  [OK]    {name}: Algo Trading {'ACTIVADO en config' if changed else 'ya activo en config'}")
        tb = build_of(exe_version(exe))
        if not builds_compatible(tb, lib_build):
            warnings += 1
            print(f"  [AVISO] {name}: terminal build {tb} vs libreria MetaTrader5 {lib}. "
                  f"Si no conecta (IPC timeout), instala la libreria de esa build "
                  f"(python -m pip index versions MetaTrader5).")
    if warnings == 0:
        print(f"  [OK]    versiones de terminal compatibles con MetaTrader5 {lib}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
