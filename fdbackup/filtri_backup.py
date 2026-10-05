"""Filtri deterministici per i backup versionati di FDBackup."""
from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


def rileva_reparse(percorso: Path) -> bool:
    """Rileva link simbolici e, su Windows, oggetti con FILE_ATTRIBUTE_REPARSE_POINT."""
    percorso = Path(percorso)
    try:
        if percorso.is_symlink():
            return True
        if os.name == "nt":
            return bool(percorso.lstat().st_file_attributes & 0x400)  # type: ignore[attr-defined]
    except OSError:
        return False
    return False


@dataclass(slots=True, frozen=True)
class FiltroBackup:
    """Regole include/exclude applicate prima di hashing e copia.

    I pattern usano la sintassi fnmatch sui percorsi relativi POSIX. La politica
    reparse predefinita è conservativa: gli oggetti reparse vengono ignorati.
    """

    includi: tuple[str, ...] = ()
    escludi: tuple[str, ...] = ()
    estensioni_escluse: tuple[str, ...] = ()
    dimensione_massima: int | None = None
    dimensione_minima: int = 0
    escludi_nascosti: bool = False
    escludi_sola_lettura: bool = False
    politica_reparse: str = "ignora"

    def __post_init__(self) -> None:
        if self.dimensione_massima is not None and (type(self.dimensione_massima) is not int or self.dimensione_massima < 0):
            raise ValueError("La dimensione massima deve essere un intero non negativo o None.")
        if type(self.dimensione_minima) is not int or self.dimensione_minima < 0:
            raise ValueError("La dimensione minima deve essere un intero non negativo.")
        if self.dimensione_massima is not None and self.dimensione_minima > self.dimensione_massima:
            raise ValueError("La dimensione minima non può superare quella massima.")
        for raccolta in (self.includi, self.escludi, self.estensioni_escluse):
            if not isinstance(raccolta, tuple) or any(not isinstance(x, str) or not x.strip() for x in raccolta):
                raise TypeError("Le regole filtro devono essere tuple di stringhe non vuote.")
        if self.politica_reparse not in {"ignora", "segui"}:
            raise ValueError("La politica reparse deve essere 'ignora' oppure 'segui'.")

    @staticmethod
    def _nascosto(percorso: Path) -> bool:
        if percorso.name.startswith("."):
            return True
        if os.name == "nt":
            try:
                return bool(percorso.stat().st_file_attributes & 0x2)  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                return False
        return False

    @staticmethod
    def _sola_lettura(percorso: Path) -> bool:
        if os.name == "nt":
            try:
                return bool(percorso.stat().st_file_attributes & 0x1)  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                return False
        try:
            return not bool(percorso.stat().st_mode & 0o200)
        except OSError:
            return False

    @staticmethod
    def _normalizza_regola(regola: str) -> str:
        """Accetta estensioni intuitive come '.txt' senza obbligare l'utente a scrivere '*.txt'."""
        regola = regola.strip()
        if regola.startswith(".") and not any(carattere in regola for carattere in "*?[]/"):
            return "*" + regola
        return regola

    def valuta(self, relativo: str, dimensione: int = 0, reparse: bool = False, percorso: Path | None = None) -> tuple[bool, str | None]:
        """Valuta un file restituendo anche il motivo leggibile dell'eventuale esclusione."""
        relativo = PurePosixPath(relativo).as_posix()
        if reparse and self.politica_reparse == "ignora":
            return False, "reparse"
        if dimensione < self.dimensione_minima:
            return False, "dimensione_minima"
        if self.dimensione_massima is not None and dimensione > self.dimensione_massima:
            return False, "dimensione_massima"
        suffisso = PurePosixPath(relativo).suffix.lower()
        estensioni = {x.lower() if x.startswith(".") else "." + x.lower() for x in self.estensioni_escluse}
        if suffisso and suffisso in estensioni:
            return False, "estensione"
        regole_includi = tuple(self._normalizza_regola(regola) for regola in self.includi)
        if regole_includi and not any(fnmatch.fnmatchcase(relativo, regola) for regola in regole_includi):
            return False, "non_incluso"
        regole_escludi = tuple(self._normalizza_regola(regola) for regola in self.escludi)
        if any(fnmatch.fnmatchcase(relativo, regola) for regola in regole_escludi):
            return False, "pattern_esclusione"
        if percorso is not None and self.escludi_nascosti and self._nascosto(percorso):
            return False, "nascosto"
        if percorso is not None and self.escludi_sola_lettura and self._sola_lettura(percorso):
            return False, "sola_lettura"
        return True, None

    def accetta(self, relativo: str, dimensione: int = 0, reparse: bool = False, percorso: Path | None = None) -> bool:
        """Mantiene l'API booleana storica delegando alla valutazione diagnostica."""
        return self.valuta(relativo, dimensione, reparse, percorso)[0]

    def accetta_cartella(self, relativo: str, percorso: Path | None = None) -> bool:
        relativo = PurePosixPath(relativo).as_posix()
        if percorso is not None and rileva_reparse(percorso) and self.politica_reparse == "ignora":
            return False
        if any(fnmatch.fnmatchcase(relativo, p) or fnmatch.fnmatchcase(relativo + "/", p) for p in self.escludi):
            return False
        if percorso is not None and self.escludi_nascosti and self._nascosto(percorso):
            return False
        return True
