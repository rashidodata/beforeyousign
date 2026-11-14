from io import BytesIO
from PIL import Image
from beforeyousign.photo_ai import prepare_photo

def test_photo_serialization():
    image = Image.new('RGB', (800, 600), (220, 218, 206))
    buf = BytesIO()
    image.save(buf, 'PNG')
    assert prepare_photo(buf.getvalue()).startswith('data:image/jpeg;base64,')