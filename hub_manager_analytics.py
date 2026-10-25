"""Read-only manager analytics: assignment cohorts, recorded attempts, own active Hub."""
import csv
import io
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from flask import request, jsonify, Response

TZ=ZoneInfo('Africa/Casablanca')

def stamp(value):
    try:
        d=datetime.fromisoformat(value)
        # Operational timestamps use app.now(), i.e. naive server-local time.
        return d.astimezone(TZ).timestamp()
    except (ValueError,TypeError):return None


def period(args):
    today=datetime.now(TZ).date()
    def read(key,default,end=False):
        value=args.get(key) or default
        try:
            d=datetime.fromisoformat(value)
            if len(value)==10:d=datetime.combine(d.date(),time(23,59,59,999999) if end else time.min)
            elif len(value)==16 and end:d+=timedelta(seconds=59,microseconds=999999)
            return d.replace(tzinfo=TZ) if d.tzinfo is None else d.astimezone(TZ)
        except (ValueError,TypeError):raise ValueError('Dates invalides.')
    start=read('from',(today-timedelta(days=6)).isoformat())
    end=read('to',today.isoformat(),True)
    if start>end or (end.date()-start.date()).days>30:raise ValueError('Choisissez une période de 31 jours maximum, dans le bon ordre.')
    return start,end


def analytics(c,hid,start,end,driver_id=None):
    c.create_function('hma_stamp',1,stamp,deterministic=True)
    drivers=[dict(r) for r in c.execute("SELECT id,name,active FROM users WHERE role='livreur' AND driver_hub_id=? ORDER BY name,id",(hid,))]
    if driver_id is not None:
        drivers=[r for r in drivers if r['id']==driver_id]
        if not drivers:raise LookupError('Livreur introuvable dans votre Hub.')
    ids={r['id'] for r in drivers}
    # Unknown Hub snapshots never become local merely because of destination city.
    assignments=[dict(r) for r in c.execute('''SELECT a.*,p.tracking FROM ops_assignments a JOIN parcels p ON p.id=a.parcel_id
        WHERE a.hub_id=? AND hma_stamp(a.created_at)>=? AND hma_stamp(a.created_at)<=?
        ORDER BY hma_stamp(a.created_at),a.id''',(hid,start.timestamp(),end.timestamp())) if r['new_driver_id'] in ids]
    days=[];day=start.date()
    while day<=end.date():days.append(day.isoformat());day+=timedelta(days=1)
    daily={r['id']:{day:set() for day in days} for r in drivers}
    latest={}
    for a in assignments:
        day=datetime.fromtimestamp(stamp(a['created_at']),TZ).date().isoformat()
        daily[a['new_driver_id']][day].add(a['parcel_id'])
        # One parcel per driver in the selected cohort, even after repeated handoffs.
        latest[(a['new_driver_id'],a['parcel_id'])]=a
    detail=[]
    for (did,pid),a in latest.items():
        assigned=stamp(a['created_at'])
        # A later assignment ends this assignment cycle, including a handoff to another Hub.
        nxt=c.execute('''SELECT hma_stamp(created_at) ts FROM ops_assignments WHERE parcel_id=?
            AND (hma_stamp(created_at)>? OR (hma_stamp(created_at)=? AND id>?))
            ORDER BY hma_stamp(created_at),id LIMIT 1''',(pid,assigned,assigned,a['id'])).fetchone()
        until=nxt['ts'] if nxt else end.timestamp()+1
        attempts=c.execute('''SELECT outcome,created_at,id FROM ops_attempts WHERE parcel_id=? AND driver_id=?
            AND operational_hub_id=? AND hma_stamp(created_at)>=? AND hma_stamp(created_at)<=?
            AND (?=0 OR hma_stamp(created_at)<?)
            ORDER BY hma_stamp(created_at) DESC,id DESC LIMIT 1''',
            (pid,did,hid,assigned,end.timestamp(),int(bool(nxt)),until)).fetchone()
        detail.append(dict(parcel_id=pid,tracking=a['tracking'],driver_id=did,assigned_at=a['created_at'],
            processed=bool(attempts),outcome=attempts['outcome'] if attempts else 'Sans tentative',
            attempted_at=attempts['created_at'] if attempts else None))
    rows=[]
    for dr in drivers:
        parcels=[p for p in detail if p['driver_id']==dr['id']]
        total=len(parcels);processed=sum(p['processed'] for p in parcels)
        counts={k:sum(p['outcome']==k for p in parcels) for k in ('Livré','Retourné','Refusé')}
        matrix={d:len(v) for d,v in daily[dr['id']].items()}
        rows.append(dict(**dr,assigned=total,processed=processed,pending=total-processed,
            delivered=counts['Livré'],returned=counts['Retourné'],refused=counts['Refusé'],
            progress=round(processed*100/total,1) if total else 0,
            delivery_rate=round(counts['Livré']*100/total,1) if total else 0,
            return_rate=round(counts['Retourné']*100/total,1) if total else 0,
            risk=bool(total and processed*2<total),daily=matrix,worked_days=sum(bool(n) for n in matrix.values()),
            never_worked=not any(matrix.values())))
    rows.sort(key=lambda r:(-r['progress'],-r['delivered'],r['name'],r['id']))
    total=sum(r['assigned'] for r in rows);processed=sum(r['processed'] for r in rows)
    active=sum(r['active'] for r in rows);worked=sum(sum(bool(n) for n in r['daily'].values()) for r in rows if r['active'])
    summary=dict(drivers=len(rows),active_drivers=active,assigned=total,processed=processed,pending=total-processed,
        delivered=sum(r['delivered'] for r in rows),risk=sum(r['risk'] for r in rows),
        progress=round(processed*100/total,1) if total else 0,
        delivery_rate=round(sum(r['delivered'] for r in rows)*100/total,1) if total else 0,
        days=len(days),average_drivers=round(worked/len(days),1),
        inactive_driver_days=active*len(days)-worked,never_worked=sum(r['never_worked'] for r in rows if r['active']))
    return dict(rows=rows,days=days,summary=summary,parcels=detail,from_date=start.isoformat(),to_date=end.isoformat())


def register_hub_manager_analytics(app,s):
    conn,auth,user,Error=(s[k] for k in ('conn','auth','user','APIError'))
    def load():
        u=user()
        if any(k not in ('from','to','driver_id','format','view','day') for k in request.args):
            raise Error('Filtre inconnu : le Hub est imposé par votre compte.')
        try:
            start,end=period(request.args)
            did=int(request.args['driver_id']) if request.args.get('driver_id') else None
            if did is not None and did<=0:raise ValueError('Livreur invalide.')
        except ValueError as e:raise Error(str(e))
        with conn() as c:
            c.execute('BEGIN')
            hub=c.execute('SELECT id,name FROM ops_hubs WHERE id=? AND active=1',(u.get('agent_hub_id'),)).fetchone()
            if not hub:raise Error('Hub actif requis.',403)
            try:data=analytics(c,hub['id'],start,end,did)
            except LookupError as e:raise Error(str(e),404)
            data['hub']=dict(hub)
        return data
    @app.get('/api/hub-manager-analytics')
    @auth('agent')
    def hub_manager_analytics():
        data=load()
        fmt=request.args.get('format','json');view=request.args.get('view','drivers')
        if fmt not in ('json','csv') or view not in ('drivers','daily','hub'):raise Error('Format de vue invalide.')
        if fmt=='json':return jsonify(data)
        out=io.StringIO();w=csv.writer(out,delimiter=';')
        def safe(v):
            v=str(v)
            return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
        if view=='daily':
            w.writerow(['Livreur','Actif','Jours avec affectation',*data['days']])
            for r in data['rows']:w.writerow([safe(r['name']),r['active'],r['worked_days'],*[r['daily'][d] for d in data['days']]])
        elif view=='hub':
            z=data['summary'];w.writerow(['Hub','Assignés','Traités','En attente','Livrés','Progression %'])
            w.writerow([safe(data['hub']['name']),*[z[k] for k in ('assigned','processed','pending','delivered','progress')]])
        else:
            w.writerow(['Hub','Livreur','Assignés','Traités','En attente','Livrés','Retournés','Refusés','Progression %'])
            for r in data['rows']:w.writerow([safe(data['hub']['name']),safe(r['name']),*[r[k] for k in ('assigned','processed','pending','delivered','returned','refused','progress')]])
        return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="analytique-hub.csv"','Cache-Control':'no-store'})
