"""M3 - Image Preprocessing.

Quality gate (Laplacian blur, exposure, contrast, colour) followed by CLAHE
lighting normalisation and gray-world colour constancy. Each stage is
independently importable and testable.
"""

from ml.preprocessing.blur import laplacian_variance, tenengrad_score
from ml.preprocessing.color import gray_world
from ml.preprocessing.features import (
    ImageFeatures,
    digest_seed,
    extract_features,
    image_digest,
    ripeness_colour_index,
)
from ml.preprocessing.lighting import apply_clahe
from ml.preprocessing.pipeline import (
    DEFAULT_PREPROCESSING,
    PreprocessResult,
    Preprocessor,
    decode_image,
    preprocess_bytes,
    resize_for_inference,
)
from ml.preprocessing.quality import (
    DEFAULT_QUALITY_GATE,
    QualityMetrics,
    QualityReport,
    evaluate_quality,
    measure,
    resolve_thresholds,
)

__all__ = [
    "DEFAULT_PREPROCESSING",
    "DEFAULT_QUALITY_GATE",
    "ImageFeatures",
    "PreprocessResult",
    "Preprocessor",
    "QualityMetrics",
    "QualityReport",
    "apply_clahe",
    "decode_image",
    "digest_seed",
    "evaluate_quality",
    "extract_features",
    "gray_world",
    "image_digest",
    "laplacian_variance",
    "measure",
    "preprocess_bytes",
    "resize_for_inference",
    "resolve_thresholds",
    "ripeness_colour_index",
    "tenengrad_score",
]
