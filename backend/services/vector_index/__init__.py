# Copyright (c) 2026 徐泽宇
from services.vector_index.backend import VectorIndexBackend, get_vector_index_backend
from services.vector_index.types import VectorRecord

__all__ = [
    "VectorIndexBackend",
    "VectorRecord",
    "get_vector_index_backend",
]
