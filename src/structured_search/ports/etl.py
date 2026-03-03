"""Generic ETL pipeline port.

Defines BaseETLService — the shared load → parse → score → export pattern
reusable across all tasks without code duplication.

To add a new domain, subclass BaseETLService and implement _parse() and
_to_scored(). The run() and process_phase() orchestration is shared.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import ValidationError

from structured_search.domain.models import BaseConstraints, BaseResult
from structured_search.domain.scoring import ScoredResult
from structured_search.ports.exporting import ExportingPort
from structured_search.ports.loading import LoadingPort
from structured_search.ports.scoring import ScoringPort

logger = logging.getLogger(__name__)

C = TypeVar("C", bound=BaseConstraints)
R = TypeVar("R", bound=BaseResult)
S = TypeVar("S", bound=ScoredResult)


@dataclass(frozen=True)
class ETLError:
    line_no: int
    kind: str
    message: str


class BaseETLService(ABC, Generic[C, R, S]):
    """Generic Extract → Transform → Load pipeline.

    Subclass and implement _parse() and _to_scored() for each task domain.
    The run() and process_phase() orchestration is shared and never modified.

    Type parameters:
        C: Constraints type (subclass of BaseConstraints)
        R: Record type (subclass of BaseResult)
        S: Scored record type (subclass of ScoredResult)

    Example::

        class ETLApartmentSearch(
            BaseETLService[ApartmentConstraints, Apartment, ScoredApartment]
        ):
            def _parse(self, raw: dict) -> Apartment:
                return Apartment.model_validate(raw)

            def _to_scored(self, scored: ScoredResult) -> ScoredApartment:
                return ScoredApartment.model_validate(scored.model_dump())
    """

    def __init__(
        self,
        loader: LoadingPort,
        scorer: ScoringPort,
        exporter: ExportingPort,
        constraints: C,
    ):
        self.loader = loader
        self.scorer = scorer
        self.exporter = exporter
        self.constraints = constraints
        self.last_errors: list[ETLError] = []

    @abstractmethod
    def _parse(self, raw: dict) -> R:
        """Parse a raw dict into the domain record type."""
        ...

    @abstractmethod
    def _to_scored(self, scored: ScoredResult) -> S:
        """Cast a generic ScoredResult to the task-specific scored type."""
        ...

    def run(self, input_path: str, output_path: str) -> dict:
        """Execute full ETL pipeline: load → parse → score → export.

        Returns:
            {"loaded": int, "processed": int, "skipped": int, "output": str}
        """
        logger.info(f"ETL: {input_path} → {output_path}")
        raw = self.loader.load(input_path)
        results, skipped = self.process_phase(raw)
        self.exporter.export(results, output_path)
        return {
            "loaded": len(raw),
            "processed": len(results),
            "skipped": skipped,
            "output": str(output_path),
            "errors": [e.__dict__ for e in self.last_errors],
        }

    def process_phase(self, raw_records: list[dict]) -> tuple[list[S], int]:
        """Parse → validate → score each raw record.

        Returns:
            (results, skipped_count)
        """
        results: list[S] = []
        skipped = 0
        self.last_errors = []
        for idx, raw in enumerate(raw_records, start=1):
            try:
                record = self._parse(raw)
                scored = self.scorer.score(record, self.constraints)
                results.append(self._to_scored(scored))
            except ValidationError as e:
                message = str(e.errors(include_url=False))
                self.last_errors.append(
                    ETLError(
                        line_no=idx,
                        kind="validation_error",
                        message=message,
                    )
                )
                logger.warning("Record %s skipped (validation): %s", idx, message)
                skipped += 1
            except (ValueError, TypeError) as e:
                self.last_errors.append(
                    ETLError(
                        line_no=idx,
                        kind="processing_error",
                        message=str(e),
                    )
                )
                logger.warning("Record %s skipped (processing): %s", idx, e)
                skipped += 1
        return results, skipped
