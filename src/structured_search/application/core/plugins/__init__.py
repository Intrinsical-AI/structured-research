"""Built-in task plugins."""

from structured_search.application.core.plugins.gen_cv import GEN_CV_PLUGIN
from structured_search.application.core.plugins.job_search import JOB_SEARCH_PLUGIN
from structured_search.application.core.plugins.product_search import PRODUCT_SEARCH_PLUGIN

__all__ = ["GEN_CV_PLUGIN", "JOB_SEARCH_PLUGIN", "PRODUCT_SEARCH_PLUGIN"]
