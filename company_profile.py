"""Private, self-service bank details and normalized profile image for company clients."""
import base64
import binascii
import io
import re
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError

FIELDS = {'bank_name', 'bank_rib', 'profile_image'}
MAX_IMAGE_BYTES = 1024 * 1024


def eligible(user):
    return user.get('role') == 'client' and user.get('client_type') == 'societe_livraison'


def ensure_schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS company_profiles(
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        bank_name TEXT NOT NULL DEFAULT '', bank_rib TEXT NOT NULL DEFAULT '',
        profile_image TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
    )''')


def own_profile(c, uid):
    row = c.execute('SELECT bank_name,bank_rib,profile_image FROM company_profiles WHERE user_id=?', (uid,)).fetchone()
    return dict(row) if row else dict(bank_name='', bank_rib='', profile_image='')


def normalize_image(value, Error):
    if value == '':
        return ''
    if not isinstance(value, str) or len(value) > MAX_IMAGE_BYTES * 4 // 3 + 128:
        raise Error('Image trop volumineuse : 1 Mo maximum.')
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', value)
    if not match:
        raise Error('Choisissez une image JPG, PNG ou WebP valide.')
    try:
        raw = base64.b64decode(match[2], validate=True)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError()
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 16000000:
                    raise ValueError()
                if getattr(image, 'n_frames', 1) != 1:
                    raise ValueError()
                image.load()
                clean = ImageOps.exif_transpose(image).convert('RGBA')
                clean.thumbnail((512, 512), Image.Resampling.LANCZOS)
                # Rebuild pixels to strip metadata, including EXIF / GPS and comments.
                output = Image.new('RGBA', clean.size)
                output.paste(clean)
                buffer = io.BytesIO()
                output.save(buffer, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')
    except (ValueError, OSError, binascii.Error, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise Error('Image invalide : JPG, PNG ou WebP non animé, 1 Mo et 16 mégapixels maximum.')


def save_profile(c, user, data, now, Error):
    if not FIELDS.intersection(data):
        return
    if not eligible(user):
        raise Error('Ces champs sont réservés au profil Société de livraison.', 403)
    values = own_profile(c, user['id'])
    if 'bank_name' in data:
        bank = data['bank_name']
        if not isinstance(bank, str) or len(bank.strip()) > 120 or any(ord(ch) < 32 for ch in bank):
            raise Error('Nom de banque invalide (120 caractères maximum).')
        values['bank_name'] = bank.strip()
    if 'bank_rib' in data:
        rib = data['bank_rib']
        if not isinstance(rib, str) or len(rib) > 80:
            raise Error('RIB invalide : saisissez 24 chiffres.')
        rib = re.sub(r'[\s-]', '', rib)
        if rib and not re.fullmatch(r'[0-9]{24}', rib):
            raise Error('Le RIB marocain doit contenir exactement 24 chiffres.')
        values['bank_rib'] = rib
    if 'profile_image' in data:
        values['profile_image'] = normalize_image(data['profile_image'], Error)
    c.execute('''INSERT INTO company_profiles(user_id,bank_name,bank_rib,profile_image,updated_at)
        VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET bank_name=excluded.bank_name,
        bank_rib=excluded.bank_rib,profile_image=excluded.profile_image,updated_at=excluded.updated_at''',
        (user['id'], values['bank_name'], values['bank_rib'], values['profile_image'], now()))
