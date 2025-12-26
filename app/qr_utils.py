import io
import qrcode
from PIL import Image

def make_qr_png(data: str) -> bytes:
    qr = qrcode.QRCode(version=2, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img: Image.Image = qr.make_image(fill_color="black", back_color="white")  # type: ignore
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
