from io import BytesIO
from photo_proxy import jpeg_for_cached_listing, PhotoUnavailable

ID='112592538'
PHOTO='https://img4.idealista.com/photo/123.jpg'
ENTRY={'status':'imported','listing_id':ID,'photo_urls':[PHOTO]}

def image_bytes():
    im=Image.new('RGB',(900,450),(123,150,174))
    out=BytesIO(); im.save(out,'JPEG'); return out.getvalue()

def test_proxy_valid_cached_image_and_resizes():
    data=jpeg_for_cached_listing(ID,0,lookup=lambda x:ENTRY,fetch=lambda url:image_bytes())
    im=Image.open(BytesIO(data))
    assert im.size==(768,384)
    assert im.format=='JPEG'
    assert len(data)<=2_000_000

def test_proxy_rejects_cache_missing_or_wrong_id():
    with pytest.raises(PhotoUnavailable):
        jpeg_for_cached_listing(ID,0,lookup=lambda x:None,fetch=lambda url:None)
    with pytest.raises(PhotoUnavailable):
        jpeg_for_cached_listing(ID,0,lookup=lambda x:{**ENTRY,'listing_id':'999999'},fetch=lambda url:None)

def test_proxy_forbids_other_hosts_and_indices():
    with pytest.raises(PhotoUnavailable):
        jpeg_for_cached_listing(ID,0,lookup=lambda x:{**ENTRY,'photo_urls':['https://example.com/img.jpg']},fetch=lambda x:None)
    with pytest.raises(ValueError):
        jpeg_for_cached_listing(ID,8,lookup=lambda x:ENTRY)
    with pytest.raises(ValueError):
        jpeg_for_cached_listing('abc',0,lookup=lambda x:ENTRY)

def test_proxy_invalid_image_not_returned():
    with pytest.raises(PhotoUnavailable):
        jpeg_for_cached_listing(ID,0,lookup=lambda x:ENTRY,fetch=lambda x:b'not an image')