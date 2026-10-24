"""Estado persistente del motor e2 (tres patas).

Guarda en JSON las patas abiertas/cerradas/omitidas para sobrevivir reinicios:
no reabrir una pata el mismo día y seguir gestionando salidas pendientes.
Sin dependencia de MT5.
"""

import json
import os

DAY_S = 86400


def key(leg: str, day: int) -> str:
    """Clave de una pata: '<leg>:<día de la señal>' (día = epoch // 86400)."""
    return f"{leg}:{day}"


class E2State:
    def __init__(self, path: str):
        self.path = path
        self.legs: dict[str, dict] = {}
        self.load_error: str | None = None

    def load(self) -> None:
        """Carga el archivo. Ausente o corrupto -> estado vacío (load_error lo explica)."""
        self.legs = {}
        self.load_error = None
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("el JSON raíz no es un objeto")
            self.legs = data
        except Exception as e:
            self.legs = {}
            self.load_error = f"{type(e).__name__}: {e}"

    def save(self) -> None:
        """Escritura atómica: tmp en el mismo directorio y os.replace."""
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.legs, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def put(self, entry: dict) -> str:
        """Inserta/actualiza una pata; la clave sale de leg y entry_epoch // 86400."""
        k = key(entry["leg"], int(entry["entry_epoch"]) // DAY_S)
        self.legs[k] = entry
        return k

    def entered(self, leg: str, day: int) -> bool:
        """True si la pata ya existe ese día, con cualquier estado."""
        return key(leg, day) in self.legs

    def active(self) -> list[dict]:
        """Patas con estado open o locked."""
        return [e for e in self.legs.values() if e.get("status") in ("open", "locked")]

    def prune(self, before_day: int) -> None:
        """Borra patas closed/skipped cuyo día de clave es < before_day."""
        for k in list(self.legs):
            try:
                day = int(k.rsplit(":", 1)[1])
            except (IndexError, ValueError):
                continue
            if day < before_day and self.legs[k].get("status") in ("closed", "skipped"):
                del self.legs[k]
