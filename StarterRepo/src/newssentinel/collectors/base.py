from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Iterable
from ..models.schema import NormalizedItem

class Collector(ABC):
    name: str

    @abstractmethod
    async def collect(self) -> Iterable[NormalizedItem]:
        raise NotImplementedError
