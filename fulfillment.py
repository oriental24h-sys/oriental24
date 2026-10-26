"""Stock reservation -> Central Hub parcel creation -> return-palette receipt stock restoration."""
from client_types import tracking_for
import json,re,secrets,hashlib
from datetime import datetime,timedelta
from flask import jsonify,request

def register_fulfillment(app, services):
    conn,auth,user,now,text,number,Error,event=(services[k] for k in ['conn','auth','user','now','text','number','APIError','event'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS fulfillment_orders(id INTEGER PRIMARY KEY,client_id INTEGER NOT NULL REFERENCES users(id),parcel_id INTEGER UNIQUE REFERENCES parcels(id),status TEXT NOT NULL DEFAULT 'Réservé',shipping TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,payload_hash TEXT NOT NULL,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,processed_at TEXT,processed_by INTEGER,reason TEXT);
        CREATE TABLE IF NOT EXISTS fulfillment_lines(id INTEGER PRIMARY KEY,order_id INTEGER NOT NULL REFERENCES fulfillment_orders(id),product_id INTEGER NOT NULL REFERENCES products(id),sku TEXT NOT NULL,name TEXT NOT NULL,quantity INTEGER NOT NULL CHECK(quantity>0),UNIQUE(order_id,product_id));
        CREATE INDEX IF NOT EXISTS fulfillment_stock_reservations ON fulfillment_lines(product_id,order_id);
        ''')
        if 'fulfillment_order_id' not in {r['name'] for r in c.execute('PRAGMA table_info(movements)')}:c.execute('ALTER TABLE movements ADD COLUMN fulfillment_order_id INTEGER REFERENCES fulfillment_orders(id)')
        order_columns={r['name'] for r in c.execute('PRAGMA table_info(fulfillment_orders)')}
        for name,definition in [('dispatch_hub_id','INTEGER REFERENCES ops_hubs(id)'),('stock_deducted_at','TEXT'),('stock_restocked_at','TEXT')]:
            if name not in order_columns:c.execute('ALTER TABLE fulfillment_orders ADD COLUMN '+name+' '+definition)
        c.execute('''UPDATE fulfillment_orders SET stock_deducted_at=(SELECT min(m.created_at) FROM movements m WHERE m.fulfillment_order_id=fulfillment_orders.id AND m.delta<0)
            WHERE stock_deducted_at IS NULL AND EXISTS(SELECT 1 FROM movements m WHERE m.fulfillment_order_id=fulfillment_orders.id AND m.delta<0)''')
        c.execute('''UPDATE fulfillment_orders SET stock_restocked_at=(SELECT min(m.created_at) FROM movements m WHERE m.fulfillment_order_id=fulfillment_orders.id AND m.delta>0)
            WHERE stock_restocked_at IS NULL AND EXISTS(SELECT 1 FROM movements m WHERE m.fulfillment_order_id=fulfillment_orders.id AND m.delta>0)''')
        c.execute('''UPDATE fulfillment_orders SET dispatch_hub_id=(
            SELECT p.origin_hub_id FROM parcels p WHERE p.id=fulfillment_orders.parcel_id)
            WHERE dispatch_hub_id IS NULL AND EXISTS(SELECT 1 FROM parcels p WHERE p.id=fulfillment_orders.parcel_id AND p.origin_hub_id IS NOT NULL)''')
    def reserved(c,pid):return c.execute("SELECT COALESCE(sum(l.quantity),0) FROM fulfillment_lines l JOIN fulfillment_orders o ON o.id=l.order_id WHERE l.product_id=? AND o.status IN ('Réservé','Préparé') AND o.stock_deducted_at IS NULL",(pid,)).fetchone()[0]
    services['reserved_stock']=reserved
    def central_stock_hub(c):
        setting=c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
        try:hub_id=int(setting['value']) if setting and str(setting['value']).isdigit() else None
        except (TypeError,ValueError):hub_id=None
        if not hub_id:return None
        return c.execute('SELECT * FROM ops_hubs WHERE id=? AND active=1',(hub_id,)).fetchone()
    def require_central_agent(c,u):
        if u['role']=='agent':
            central=central_stock_hub(c)
            if not central or u.get('agent_hub_id')!=central['id']:
                raise Error('Préparation stock réservée au responsable du Hub Central.',403)
    def restock_on_return_palette_receive(c,pid,actor,hub_id):
        order=c.execute('SELECT * FROM fulfillment_orders WHERE parcel_id=?',(pid,)).fetchone()
        if not order:return None
        parcel=c.execute('SELECT return_state,current_hub_id FROM parcels WHERE id=?',(pid,)).fetchone()
        if not parcel or parcel['return_state']!='recu_entrepot' or parcel['current_hub_id']!=hub_id:
            return {'restocked':False,'reason':'not_received_return','order_id':order['id']}
        if type(order['dispatch_hub_id']) is not int or hub_id!=order['dispatch_hub_id']:
            return {'restocked':False,'reason':'wrong_hub','order_id':order['id'],'hub_id':order['dispatch_hub_id']}
        if not order['stock_deducted_at']:
            return {'restocked':False,'reason':'not_deducted','order_id':order['id'],'hub_id':hub_id}
        if order['stock_restocked_at']:
            return {'restocked':False,'already_restocked':True,'order_id':order['id'],'hub_id':hub_id}
        lines=c.execute('SELECT * FROM fulfillment_lines WHERE order_id=? ORDER BY id',(order['id'],)).fetchall()
        timestamp=now()
        for line in lines:
            c.execute('UPDATE products SET quantity=quantity+? WHERE id=?',(line['quantity'],line['product_id']))
            c.execute('INSERT INTO movements(product_id,actor_id,delta,note,created_at,fulfillment_order_id) VALUES(?,?,?,?,?,?)',
                      (line['product_id'],actor['id'],line['quantity'],f"Retour palette reçu · PREP-{order['id']:05d} · {line['sku']}",timestamp,order['id']))
        c.execute('UPDATE fulfillment_orders SET stock_restocked_at=? WHERE id=? AND stock_restocked_at IS NULL',(timestamp,order['id']))
        return {'restocked':True,'order_id':order['id'],'hub_id':hub_id,'lines':[dict(sku=l['sku'],quantity=l['quantity']) for l in lines]}
    services['stock_return_palette_receive']=restock_on_return_palette_receive
    def data():
        d=request.get_json()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        return d
    def scope_order(c,oid,u):
        o=c.execute('SELECT o.*,u.company,u.name client,p.tracking,p.status parcel_status FROM fulfillment_orders o JOIN users u ON u.id=o.client_id LEFT JOIN parcels p ON p.id=o.parcel_id WHERE o.id=?',(oid,)).fetchone()
        if not o or (u['role']=='client' and o['client_id']!=u['id']):raise Error('Préparation introuvable.',404)
        if u['role']=='agent':
            require_central_agent(c,u)
            if o['status'] not in ('Réservé','Préparé'):raise Error('Préparation introuvable.',404)
        return {**dict(o),'shipping':json.loads(o['shipping']),'lines':[dict(l) for l in c.execute('SELECT * FROM fulfillment_lines WHERE order_id=? ORDER BY id',(oid,))]}
    @app.get('/api/fulfillment/orders')
    @auth('admin','client','agent')
    def fulfillment_orders():
        u=user()
        with conn() as c:
            if u['role']=='agent':
                require_central_agent(c,u)
                rows=c.execute("SELECT id FROM fulfillment_orders WHERE status IN ('Réservé','Préparé') ORDER BY id DESC LIMIT 500").fetchall()
            else:
                rows=c.execute('SELECT id FROM fulfillment_orders '+('WHERE client_id=?' if u['role']=='client' else '')+' ORDER BY id DESC LIMIT 500',[u['id']] if u['role']=='client' else []).fetchall()
            return jsonify([scope_order(c,r['id'],u) for r in rows])
    @app.post('/api/fulfillment/orders')
    @auth('admin','client')
    def fulfillment_reserve():
        d=data();u=user();key=text(d,'request_key',maxlen=80)
        if not re.fullmatch('[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de saisie invalide.')
        items=d.get('items')
        if not isinstance(items,list) or not 1<=len(items)<=30:raise Error('Ajoutez de 1 à 30 références produit.')
        shipping={k:text(d,k,maxlen=300) for k in ['recipient','phone','address']}
        shipping.update(amount=number(d,'amount'),city_id=number(d,'city_id',1,1000000000,True),note=text(d,'note',False,600))
        if not re.fullmatch(r'\+?[\d\s-]{9,18}',shipping['phone']):raise Error('Téléphone invalide.')
        cid=u['id'] if u['role']=='client' else number(d,'client_id',1,1000000000,True)
        hashed=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            old=c.execute('SELECT * FROM fulfillment_orders WHERE request_key=?',(key,)).fetchone()
            if old:
                if old['created_by']!=u['id'] or old['payload_hash']!=hashed:raise Error('Clé déjà utilisée.',409)
                return jsonify(ok=True,id=old['id'],already_created=True)
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='client' AND active=1",(cid,)).fetchone():raise Error('Client actif requis.')
            shipping['tracking']=tracking_for(c,cid,d.get('tracking'),Error,generate=False)
            if not c.execute('SELECT 1 FROM cities WHERE id=? AND delivery=1',(shipping['city_id'],)).fetchone():raise Error('Ville fermée à la livraison.')
            lines=[];seen=set()
            for item in items:
                if not isinstance(item,dict):raise Error('Ligne produit invalide.')
                pid=number(item,'product_id',1,1000000000,True);qty=number(item,'quantity',1,100000,True)
                if pid in seen:raise Error('Produit répété. Regroupez sa quantité.')
                seen.add(pid);p=c.execute('SELECT * FROM products WHERE id=? AND client_id=?',(pid,cid)).fetchone()
                if not p:raise Error('Produit inaccessible pour ce client.',404)
                if qty>p['quantity']-reserved(c,pid):raise Error('Stock disponible insuffisant pour '+p['reference'],409)
                lines.append((pid,p['reference'],p['name'],qty))
            oid=c.execute('INSERT INTO fulfillment_orders(client_id,shipping,request_key,payload_hash,created_by,created_at) VALUES(?,?,?,?,?,?)',(cid,json.dumps(shipping,ensure_ascii=False),key,hashed,u['id'],now())).lastrowid
            c.executemany('INSERT INTO fulfillment_lines(order_id,product_id,sku,name,quantity) VALUES(?,?,?,?,?)',[(oid,*line) for line in lines])
            return jsonify(ok=True,id=oid,already_created=False)
    @app.get('/api/fulfillment/orders/<int:oid>')
    @auth('admin','client','agent')
    def fulfillment_order(oid):
        with conn() as c:return jsonify(scope_order(c,oid,user()))
    @app.post('/api/fulfillment/orders/<int:oid>/<action>')
    @auth('admin','client','agent')
    def fulfillment_action(oid,action):
        d=data();u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');o=scope_order(c,oid,u)
            if action=='cancel':
                if u['role']=='agent':raise Error('Seul le vendeur ou Admin peut annuler une réservation.',403)
                if o['status']!='Réservé':raise Error('Seule une réservation non préparée peut être annulée.',409)
                reason=text(d,'reason',maxlen=600)
                c.execute("UPDATE fulfillment_orders SET status='Annulé',reason=?,processed_at=?,processed_by=? WHERE id=?",(reason,now(),u['id'],oid))
            elif action=='ship':
                if u['role'] not in ('admin','agent'):raise Error('Préparation réservée à Admin et au responsable du Hub Central.',403)
                if u['role']=='agent':require_central_agent(c,u)
                if o['status']!='Réservé':raise Error('Commande déjà traitée.',409)
                central_setting=c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
                try:central_id=int(central_setting['value']) if central_setting and str(central_setting['value']).isdigit() else None
                except (TypeError,ValueError):central_id=None
                hub=c.execute('SELECT * FROM ops_hubs WHERE id=? AND active=1',(central_id,)).fetchone() if central_id else None
                if not hub:raise Error('Configurez un Hub Central actif pour préparer une commande depuis le stock.',409)
                try:hub_sel=number(d,'hub_id',1,1000000000,True)
                except Exception:hub_sel=None
                if hub_sel!=central_id:raise Error('Le stock des commandes est conservé au Hub Central : sélectionnez ce Hub pour préparer le colis.',409)
                if d.get('checked') is not True:raise Error('Confirmez le contrôle physique des produits.')
                sh=o['shipping'];city=c.execute('SELECT * FROM cities WHERE id=? AND delivery=1',(sh['city_id'],)).fetchone()
                if not city:raise Error('Cette ville n’est plus ouverte. Annulez la réservation pour libérer le stock.',409)
                tracking=tracking_for(c,o['client_id'],sh.get('tracking'),Error,ignore_order=oid);t=now()
                fee,ret=services['tariff_fees_for'](c,o['client_id'],dict(city)) if services.get('tariff_fees_for') else (city['fee'],city['return_fee'])
                pid=c.execute("INSERT INTO parcels(tracking,client_id,recipient,phone,address,city_id,amount,fee,return_fee,status,product,note,created_at,updated_at,current_hub_id) VALUES(?,?,?,?,?,?,?,?,?,'Au hub',?,?,?,?,?)",(tracking,o['client_id'],sh['recipient'],sh['phone'],sh['address'],city['id'],sh['amount'],fee,ret,'; '.join(l['sku']+' × '+str(l['quantity']) for l in o['lines']),sh['note'],t,t,hub['id'])).lastrowid
                for l in o['lines']:
                    p=c.execute('SELECT * FROM products WHERE id=? AND client_id=?',(l['product_id'],o['client_id'])).fetchone()
                    if not p or p['quantity']<reserved(c,p['id']):raise Error('Stock physique incohérent avec les réservations. Contrôle requis.',409)
                for l in o['lines']:
                    c.execute('UPDATE products SET quantity=quantity-? WHERE id=?',(l['quantity'],l['product_id']))
                    c.execute('INSERT INTO movements(product_id,actor_id,delta,note,created_at,fulfillment_order_id) VALUES(?,?,?,?,?,?)',
                              (l['product_id'],u['id'],-l['quantity'],f"CMD stock créée · PREP-{oid:05d} · {l['sku']}",t,oid))
                c.execute("UPDATE fulfillment_orders SET status='Préparé',parcel_id=?,dispatch_hub_id=?,stock_deducted_at=?,processed_at=?,processed_by=? WHERE id=?",(pid,hub['id'],t,t,u['id'],oid))
                event(c,pid,'Au hub','Préparation physique validée · stock déduit · PREP-'+str(oid),u)
            elif action=='restock':
                raise Error('La remise en stock se fait automatiquement au scan de réception de la palette retour au Hub Central.',409)
            else:raise Error('Action inconnue.',404)
            return jsonify(ok=True)

    @app.get('/api/fulfillment/analytics')
    @auth('admin','client')
    def fulfillment_analytics():
        u=user();end=request.args.get('to') or datetime.now().date().isoformat();start=request.args.get('from') or (datetime.now()-timedelta(days=29)).date().isoformat()
        try:
            a,b=datetime.strptime(start,'%Y-%m-%d'),datetime.strptime(end,'%Y-%m-%d')
            if a.strftime('%Y-%m-%d')!=start or b.strftime('%Y-%m-%d')!=end or a>b or (b-a).days>365:raise ValueError()
        except ValueError:raise Error('Période invalide (366 jours maximum).')
        with conn() as c:
            products=[]
            for p in c.execute('SELECT p.*,u.company FROM products p JOIN users u ON u.id=p.client_id '+('WHERE p.client_id=? ' if u['role']=='client' else '')+'ORDER BY p.id DESC',[u['id']] if u['role']=='client' else []).fetchall():
                r=c.execute('SELECT COALESCE(sum(CASE WHEN delta>0 THEN delta ELSE 0 END),0) incoming,COALESCE(sum(CASE WHEN delta<0 THEN -delta ELSE 0 END),0) outgoing,COALESCE(sum(CASE WHEN fulfillment_order_id IS NOT NULL AND delta<0 THEN -delta ELSE 0 END),0) prepared,COALESCE(sum(CASE WHEN fulfillment_order_id IS NOT NULL AND delta>0 THEN delta ELSE 0 END),0) restocked FROM movements WHERE product_id=? AND substr(created_at,1,10) BETWEEN ? AND ?',(p['id'],start,end)).fetchone()
                held=reserved(c,p['id']);products.append({**dict(p),**dict(r),'reserved':held,'available':p['quantity']-held})
            return jsonify(products=products,period_from=start,period_to=end)
