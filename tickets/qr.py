"""QR image generation helpers for event tickets."""

import base64
from io import BytesIO

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def generate_qr_code_base64(token: str) -> str:
    """Return a PNG QR code for ``token`` as a Base64 string.

    The returned value is the Base64 payload only. Use it in an image source as
    ``data:image/png;base64,<payload>``. The image is kept in memory and no
    temporary file is written.
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=8,
        border=4,
    )
    qr.add_data(token)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    return base64.b64encode(image_buffer.getvalue()).decode("ascii")
