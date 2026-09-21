"""Private claim attachments. Download only; validation is not an antivirus scan."""
import base64,binascii,hashlib,io,json,re,warnings
from flask import jsonify,send_file
from PIL import Image,UnidentifiedImageError
from werkzeug.utils import secure_filename

CATEGORIES=['Livraison','Ramassage','Facturation','Retour','Autre']
LIMIT=1024*1024

def prepare_claim(d,Error):
    category=d.get('category','Livraison')
    if category not in CATEGORIES:raise Error('Catégorie invalide.')
    for k,limit in [('subject',180),('body',3000)]:
        if not isinstance(d.get(k),str) or not d[k].strip() or len(d[k].strip())>limit:raise Error('Sujet et description obligatoires (180 et 3 000 caractères maximum).')
    key=d.get('request_key')
    if key is not None and (not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key)):raise Error('Clé de requête invalide.')
    files=d.get('attachments',[])
    if not isinstance(files,list) or len(files)>3:raise Error('Trois pièces jointes maximum.')
    prepared=[];total=0
    for f in files:
        if not isinstance(f,dict) or set(f)!={'name','content'}:raise Error('Pièce jointe invalide.')
        if not isinstance(f['name'],str) or len(f['name'])>180:raise Error('Nom de fichier invalide.')
        name=secure_filename(f['name'])
        if not name:raise Error('Nom de fichier invalide.')
        try:
            if not isinstance(f['content'],str) or len(f['content'])>1400000:raise ValueError()
            raw=base64.b64decode(f['content'],validate=True);total+=len(raw)
            if not raw or total>LIMIT:raise ValueError()
        except (ValueError,binascii.Error):raise Error('Pièces jointes invalides ou dépassant 1 Mo au total.')
        if raw.startswith(b'%PDF-') and b'%%EOF' in raw[-2048:]:mime='application/pdf';ext='pdf'
        else:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error',Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as im:
                        if im.format not in ['PNG','JPEG'] or im.width*im.height>8000000:raise ValueError()
                        im.load();buf=io.BytesIO();im.convert('RGB').save(buf,format='JPEG',quality=88);raw=buf.getvalue()
                if len(raw)>LIMIT:raise ValueError()
                mime='image/jpeg';ext='jpg'
            except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):raise Error('Formats acceptés : PDF, JPG et PNG ; images limitées à 8 mégapixels.')
        name=name.rsplit('.',1)[0]+'.'+ext
        prepared.append(dict(name=name,mime=mime,content=raw,sha256=hashlib.sha256(raw).hexdigest(),size=len(raw)))
    if sum(f['size'] for f in prepared)>LIMIT:raise Error('Pièces jointes supérieures à 1 Mo après traitement des images.')
    fingerprint=hashlib.sha256(json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return category,key,fingerprint,prepared

def claim_attachments(c,tid):
    return [dict(r) for r in c.execute('SELECT id,name,mime,size,sha256,created_at FROM claim_attachments WHERE ticket_id=? ORDER BY id',(tid,))]

def register_claims(app,services):
    conn,auth,user,Error=(services[k] for k in ['conn','auth','user','APIError'])
    with conn() as c:c.executescript('''
        CREATE TABLE IF NOT EXISTS claim_attachments(id INTEGER PRIMARY KEY,ticket_id INTEGER NOT NULL REFERENCES tickets(id),name TEXT NOT NULL,mime TEXT NOT NULL,content BLOB NOT NULL,sha256 TEXT NOT NULL,size INTEGER NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS claim_requests(user_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,parcel_id INTEGER NOT NULL REFERENCES parcels(id),fingerprint TEXT NOT NULL,ticket_id INTEGER NOT NULL REFERENCES tickets(id),PRIMARY KEY(user_id,request_key));
    ''')
    @app.get('/api/claim-attachments/<int:fid>')
    @auth()
    def claim_attachment(fid):
        u=user()
        with conn() as c:
            f=c.execute('SELECT a.* FROM claim_attachments a JOIN tickets t ON t.id=a.ticket_id WHERE a.id=? AND (t.user_id=? OR ?=\'admin\')',(fid,u['id'],u['role'])).fetchone()
            if not f:raise Error('Pièce jointe introuvable.',404)
            response=send_file(io.BytesIO(f['content']),mimetype=f['mime'],as_attachment=True,download_name=f['name'],max_age=0)
            response.headers['Cache-Control']='private, no-store';response.headers['X-Content-Type-Options']='nosniff';response.headers['Content-Security-Policy']="sandbox; default-src 'none'";return response
