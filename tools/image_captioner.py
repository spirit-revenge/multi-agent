"""
Image captioning using a local BLIP model via transformers.
Generates Chinese text descriptions for extracted images.
"""

import logging
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)

_captioner = None
_FALLBACK_SENTINEL = object()  # marks that loading failed; don't retry


def _get_captioner():
    """Lazy-load the BLIP image captioning model."""
    global _captioner
    if _captioner is None:
        try:
            from transformers import pipeline
            logger.info("Loading BLIP image captioning model (this may take a moment)...")
            _captioner = pipeline(
                "image-text-to-text",
                model="Salesforce/blip-image-captioning-base",
            )
            logger.info("BLIP model loaded.")
        except Exception as e:
            logger.warning(
                "Failed to load BLIP model: %s. "
                "Image descriptions will be placeholders.", e
            )
            _captioner = _FALLBACK_SENTINEL
    return _captioner


def describe_image(image: Image.Image, max_length: int = 50) -> str:
    """Generate a text description of a PIL Image.

    Uses BLIP (blip-image-captioning-base) for captioning.
    Falls back to a simple placeholder if model is unavailable.
    """
    captioner = _get_captioner()
    if captioner is None or captioner is _FALLBACK_SENTINEL:
        # Fallback: basic metadata
        w, h = image.size
        return f"[图片：{w}x{h} 像素]"

    try:
        # image-text-to-text pipeline expects (image, text='') for captioning
        result = captioner(image, text='', max_new_tokens=max_length)
        if result and isinstance(result, list) and 'generated_text' in result[0]:
            caption = result[0]['generated_text'].strip()
            return f"[图片描述] {caption}"
        return "[图片：无法生成描述]"
    except Exception as e:
        logger.debug("Image captioning failed: %s", e)
        return "[图片：描述生成失败]"


def describe_images_batch(
    images: list,
    max_length: int = 50,
) -> list:
    """Generate descriptions for a batch of images.

    Args:
        images: List of (PIL.Image, filename) tuples.

    Returns:
        List of (description, PIL.Image, filename) tuples.
    """
    results = []
    for img, filename in images:
        desc = describe_image(img, max_length)
        results.append((desc, img, filename))
    return results
