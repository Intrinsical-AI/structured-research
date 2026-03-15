"""product_search plugin declaration."""

from __future__ import annotations

from structured_search.application.core.task_plugin import TaskPlugin
from structured_search.domain.product_search.models import ProductRecord, ProductSearchConstraints

PRODUCT_SEARCH_PLUGIN = TaskPlugin(
    task_id="product_search",
    name="Product Search",
    prompt_namespace="product_search",
    capabilities=frozenset({"prompt", "jsonl_validate", "run"}),
    constraints_model=ProductSearchConstraints,
    record_model=ProductRecord,
    task_runtime_model=None,
    validate_task_runtime=False,
    include_user_profile_in_prompt=True,
    build_runtime=None,
)
