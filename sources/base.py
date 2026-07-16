from __future__ import annotations

from abc import ABC, abstractmethod

from models import RawJob


class JobSource(ABC):
    """Abstract interface implemented by all job-board sources."""

    @abstractmethod
    def fetch(self) -> list[RawJob]:
        """Return normalized raw vacancies from the source."""
        ...
