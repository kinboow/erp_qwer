import zxingcpp
from PIL import Image
from sqlalchemy import text
from app.database import SessionLocal
from app.services.picking_print import _generate_qr_image

db = SessionLocal()
row = db.execute(text("SELECT barcode_content FROM picking_print_pages ORDER BY id DESC LIMIT 1")).mappings().first()
db.close()

content = row['barcode_content']
print('barcode_content:', content)

qr_buf = _generate_qr_image(content, box_size=8, border=2)
img = Image.open(qr_buf).convert('RGB')
print('generated_qr_size:', img.size)

res = zxingcpp.read_barcodes(
    img,
    formats=zxingcpp.BarcodeFormat.QRCode,
    try_rotate=True,
    try_downscale=True,
    try_invert=True,
)
print('zxing_generated:', [r.text for r in res])
