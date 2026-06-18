from __future__ import annotations

from abc import ABC, abstractmethod

from models import RawJob


class JobSource(ABC):
    @abstractmethod
    def fetch(self) -> list[RawJob]:
        ...
