"""Regresion de scripts/mt5_prep.py y de la busqueda del perfil base del
provisioner. No necesita MT5 ni Supabase.

Correr:  python -m tests.test_mt5_prep
"""

import hashlib
import os
import tempfile

from scripts import mt5_prep
from scripts import provision


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  OK  {msg}")


def _read(path):
    with open(path, "rb") as f:
        raw = f.read()
    check(raw[:2] == b"\xff\xfe", "common.ini queda en UTF-16 con BOM")
    return raw.decode("utf-16")


def _write_utf16(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-16", newline="") as f:
        f.write(text)


def test_algo_trading_missing_file():
    with tempfile.TemporaryDirectory() as d:
        ini = os.path.join(d, "config", "common.ini")
        check(mt5_prep.ensure_algo_trading(ini) is True, "sin archivo: lo crea")
        t = _read(ini)
        check("[Experts]" in t and "Enabled=1" in t and "AllowLiveTrading=1" in t,
              "archivo nuevo con [Experts] activo")


def test_algo_trading_section_missing_keeps_rest():
    with tempfile.TemporaryDirectory() as d:
        ini = os.path.join(d, "common.ini")
        _write_utf16(ini, "[Common]\r\nNewsEnable=1\r\n[Charts]\r\nMaxBars=100000\r\n")
        check(mt5_prep.ensure_algo_trading(ini) is True, "sin [Experts]: cambia")
        t = _read(ini)
        check(t.lstrip("\ufeff").startswith("[Experts]\r\nAllowLiveTrading=1\r\nEnabled=1"),
              "[Experts] anadido al principio")
        check("[Common]\r\nNewsEnable=1" in t and "[Charts]\r\nMaxBars=100000" in t,
              "el resto de secciones se conserva intacto")


def test_algo_trading_disabled_is_enabled_preserving_keys():
    with tempfile.TemporaryDirectory() as d:
        ini = os.path.join(d, "common.ini")
        _write_utf16(ini, "[Experts]\r\nAllowLiveTrading=1\r\nAllowDllImport=0\r\nEnabled=0\r\n"
                          "Profile=1\r\n[Common]\r\nProxyEnable=0\r\n")
        check(mt5_prep.ensure_algo_trading(ini) is True, "Enabled=0: cambia")
        t = _read(ini)
        check("Enabled=1" in t and "Enabled=0" not in t, "Enabled pasa a 1")
        check("AllowDllImport=0" in t and "Profile=1" in t, "otras claves de [Experts] intactas")
        check(t.count("[Experts]") == 1, "una sola seccion [Experts]")
        check("[Common]\r\nProxyEnable=0" in t, "[Common] intacta")
        check(mt5_prep.ensure_algo_trading(ini) is False, "segunda pasada: idempotente")


def test_build_compat():
    check(mt5_prep.build_of("5.0.0.6230") == 6230, "build de terminal")
    check(mt5_prep.build_of("5.0.6231") == 6231, "build de libreria")
    check(mt5_prep.builds_compatible(6230, 6231), "6230 vs 6231 compatibles")
    check(not mt5_prep.builds_compatible(6230, 6090), "6230 vs 6090 incompatibles")
    check(mt5_prep.builds_compatible(None, 6090), "build desconocida: no avisa")


def test_active_env_files_filter():
    with tempfile.TemporaryDirectory() as d:
        for n in ("aaa.env", "_retirada.env", "example.env", "template.env", "bbb.env"):
            open(os.path.join(d, n), "w").close()
        names = [os.path.basename(p) for p in mt5_prep.active_env_files(d)]
        check(names == ["aaa.env", "bbb.env"], "solo los .env que lanza start_all")


def _make_profile(terminals_dir, base_dir):
    h = hashlib.md5(os.path.normpath(base_dir).upper().encode("utf-16-le")).hexdigest().upper()
    cfg = os.path.join(terminals_dir, h, "config")
    os.makedirs(cfg)
    return cfg


def test_base_profile_override_env():
    with tempfile.TemporaryDirectory() as d:
        cfg = os.path.join(d, "perfil", "config")
        os.makedirs(cfg)
        old = os.environ.get("MT5_BASE_PROFILE")
        os.environ["MT5_BASE_PROFILE"] = cfg
        try:
            check(provision._base_runtime_config() == cfg, "MT5_BASE_PROFILE manda")
        finally:
            if old is None:
                os.environ.pop("MT5_BASE_PROFILE", None)
            else:
                os.environ["MT5_BASE_PROFILE"] = old


def test_base_profile_found_from_system_account():
    """Como SYSTEM, %APPDATA% no tiene el perfil: se busca en los perfiles de
    los usuarios de Windows (C:\\Users\\*\\AppData\\Roaming\\MetaQuotes\\Terminal)."""
    with tempfile.TemporaryDirectory() as d:
        users = os.path.join(d, "Users")
        terms = os.path.join(users, "Operador", "AppData", "Roaming", "MetaQuotes", "Terminal")
        cfg = _make_profile(terms, provision.MT5_BASE_DIR)
        saved = {k: os.environ.get(k) for k in ("APPDATA", "MT5_BASE_PROFILE", "MT5_USERS_ROOT")}
        os.environ["APPDATA"] = os.path.join(d, "systemprofile", "AppData", "Roaming")
        os.environ.pop("MT5_BASE_PROFILE", None)
        os.environ["MT5_USERS_ROOT"] = users
        try:
            check(provision._base_runtime_config() == cfg,
                  "perfil base encontrado en el perfil de un usuario de Windows")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def test_base_profile_none_when_absent():
    with tempfile.TemporaryDirectory() as d:
        saved = {k: os.environ.get(k) for k in ("APPDATA", "MT5_BASE_PROFILE", "MT5_USERS_ROOT")}
        os.environ["APPDATA"] = os.path.join(d, "nada")
        os.environ.pop("MT5_BASE_PROFILE", None)
        os.environ["MT5_USERS_ROOT"] = os.path.join(d, "Users")
        try:
            check(provision._base_runtime_config() is None, "sin perfil en ningun sitio: None")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


TESTS = [
    test_algo_trading_missing_file,
    test_algo_trading_section_missing_keeps_rest,
    test_algo_trading_disabled_is_enabled_preserving_keys,
    test_build_compat,
    test_active_env_files_filter,
    test_base_profile_override_env,
    test_base_profile_found_from_system_account,
    test_base_profile_none_when_absent,
]


if __name__ == "__main__":
    for t in TESTS:
        print(t.__name__)
        t()
    print("test_mt5_prep: TODO OK")
