from pathlib import Path

from PIL import Image


def inspect_document(file_path: str, mime_type: str):
    """
    Inspect an uploaded document and determine
    whether its quality is good enough for processing.
    """

    path = Path(file_path)

    # Make sure the file actually exists
    if not path.exists():
        return {
            "quality_score": 0.0,
            "quality": "BAD",
            "quality_reason": "Uploaded file could not be found.",
            "page_count": 0,
            "file_type": "UNKNOWN",
        }

        # -------------------------------------------------
    # IMAGE INSPECTION
    # -------------------------------------------------

    if mime_type.startswith("image/"):

        try:
            with Image.open(path) as image:
                width, height = image.size

                # Extremely small images are not reliable
                if width < 300 or height < 200:
                    return {
                        "quality_score": 0.2,
                        "quality": "BAD",
                        "quality_reason": (
                            "Image is too small for reliable "
                            "document processing."
                        ),
                        "page_count": 1,
                        "file_type": "IMAGE",
                        "width": width,
                        "height": height,
                    }

                # Small but potentially readable document images
                if width < 800 or height < 600:
                    return {
                        "quality_score": 0.7,
                        "quality": "GOOD",
                        "quality_reason": (
                            "Image resolution is below the preferred "
                            "resolution but may still be suitable "
                            "for document classification."
                        ),
                        "page_count": 1,
                        "file_type": "IMAGE",
                        "width": width,
                        "height": height,
                    }

                # Good resolution
                return {
                    "quality_score": 0.9,
                    "quality": "GOOD",
                    "quality_reason": (
                        "Image resolution is sufficient "
                        "for document processing."
                    ),
                    "page_count": 1,
                    "file_type": "IMAGE",
                    "width": width,
                    "height": height,
                }

        except Exception:
            return {
                "quality_score": 0.0,
                "quality": "BAD",
                "quality_reason": "Image could not be opened or is corrupted.",
                "page_count": 0,
                "file_type": "IMAGE",
            }

    # -------------------------------------------------
    # PDF INSPECTION
    # -------------------------------------------------

    if mime_type == "application/pdf":

        try:
            import fitz

            pdf = fitz.open(path)

            page_count = len(pdf)

            if page_count == 0:
                pdf.close()

                return {
                    "quality_score": 0.0,
                    "quality": "BAD",
                    "quality_reason": "PDF contains no pages.",
                    "page_count": 0,
                    "file_type": "PDF",
                }

            pdf.close()

            return {
                "quality_score": 0.9,
                "quality": "GOOD",
                "quality_reason": (
                    "PDF is valid and contains "
                    f"{page_count} page(s)."
                ),
                "page_count": page_count,
                "file_type": "PDF",
            }

        except Exception:
            return {
                "quality_score": 0.0,
                "quality": "BAD",
                "quality_reason": "PDF could not be opened or is corrupted.",
                "page_count": 0,
                "file_type": "PDF",
            }

    # -------------------------------------------------
    # UNKNOWN FILE
    # -------------------------------------------------

    return {
        "quality_score": 0.0,
        "quality": "BAD",
        "quality_reason": "Unsupported document type.",
        "page_count": 0,
        "file_type": "UNKNOWN",
    }