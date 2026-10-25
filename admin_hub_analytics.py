"""Read-only Admin analytics, with Hubs (never couriers) as comparison units."""
import csv
import io
from datetime import datetime
from flask import request, jsonify, Response
from hub_manager_analytics import analytics, period, stamp, TZ


def admin_analytics(c,start,end,hub_id=None):
    hubs=[dict(r) for r in c.execute('SELECT id,name,active FROM ops_hubs ORDER BY name,id')]
    selected=[h for h in hubs if hub_id is None or h['id']==hub_id]
    if hub_id is not None and not selected:raise LookupError('Hub introuvable.')
    days=[];rows=[];parcels=[]
    # Reuse the reviewed net-scan and treatment rules, without modifying manager views.
    for h in selected:
        data=analytics(c,h['id'],start,end)
        days=data['days']
        latest={}
        last_assignment={}
        for a in c.execute('''SELECT parcel_id,new_driver_id,created_at FROM ops_assignments
                WHERE hub_id=? AND hma_stamp(created_at)>=? AND hma_stamp(created_at)<=?
                ORDER BY hma_stamp(created_at),id''',(h['id'],start.timestamp(),end.timestamp())):
            last_assignment[a['parcel_id']]=(a['new_driver_id'],stamp(a['created_at']))
        for p in data['parcels']:
            if last_assignment.get(p['parcel_id'])!=(p['driver_id'],stamp(p['assigned_at'])):continue
            old=latest.get(p['parcel_id'])
            if old is None or stamp(p['assigned_at'])>=stamp(old['assigned_at']):latest[p['parcel_id']]=p
        items=[dict(p,hub_id=h['id'],hub_name=h['name'],assigned_day=datetime.fromtimestamp(stamp(p['assigned_at']),TZ).date().isoformat()) for p in latest.values()]
        parcels.extend(items)
        total=len(items);processed=sum(p['processed'] for p in items)
        delivered=sum(p['outcome']=='Livré' for p in items)
        returned=sum(p['outcome']=='Retourné' for p in items)
        daily={day:sum(p['assigned_day']==day for p in items) for day in days}
        rows.append(dict(**h,assigned=total,processed=processed,pending=total-processed,delivered=delivered,
            returned=returned,refused=sum(p['outcome']=='Refusé' for p in items),
            progress=round(processed*100/total,1) if total else 0,
            delivery_rate=round(delivered*100/total,1) if total else 0,
            return_rate=round(returned*100/total,1) if total else 0,
            risk=bool(total and processed*2<total),daily=daily,
            worked_days=sum(bool(n) for n in daily.values()),never_worked=not any(daily.values())))
    if not days:
        from datetime import timedelta
        day=start.date()
        while day<=end.date():days.append(day.isoformat());day+=timedelta(days=1)
    rows.sort(key=lambda r:(-r['progress'],-r['delivered'],r['name'],r['id']))
    total=sum(r['assigned'] for r in rows);processed=sum(r['processed'] for r in rows)
    delivered=sum(r['delivered'] for r in rows);active=sum(bool(r['active']) for r in rows)
    worked=sum(r['worked_days'] for r in rows if r['active'])
    summary=dict(hubs=len(rows),active_hubs=active,assigned=total,processed=processed,pending=total-processed,
        delivered=delivered,risk=sum(r['risk'] for r in rows),progress=round(processed*100/total,1) if total else 0,
        delivery_rate=round(delivered*100/total,1) if total else 0,days=len(days),
        average_hubs=round(worked/len(days),1),inactive_hub_days=active*len(days)-worked,
        never_worked=sum(r['never_worked'] for r in rows if r['active']))
    return dict(hubs=hubs,hub=dict(id=hub_id,name=selected[0]['name'] if hub_id else 'Tous les Hubs'),
        rows=rows,summary=summary,days=days,parcels=parcels,from_date=start.isoformat(),to_date=end.isoformat())


def register_admin_hub_analytics(app,s):
    conn,auth,Error=(s[k] for k in ('conn','auth','APIError'))
    @app.get('/api/admin-hub-analytics')
    @auth('admin')
    def admin_hub_analytics():
        if any(k not in ('from','to','hub_id','format','view') for k in request.args):raise Error('Filtre inconnu.')
        try:
            start,end=period(request.args)
            hid=int(request.args['hub_id']) if request.args.get('hub_id') else None
            if hid is not None and hid<=0:raise ValueError('Hub invalide.')
        except ValueError as e:raise Error(str(e))
        fmt=request.args.get('format','json');view=request.args.get('view','hubs')
        if fmt not in ('json','csv') or view not in ('general','hubs','daily'):raise Error('Format de vue invalide.')
        with conn() as c:
            c.execute('BEGIN')
            try:data=admin_analytics(c,start,end,hid)
            except LookupError as e:raise Error(str(e),404)
        if fmt=='json':return jsonify(data)
        out=io.StringIO();w=csv.writer(out,delimiter=';')
        def safe(v):
            v=str(v)
            return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
        if view=='daily':
            w.writerow(['Hub','Actif','Jours avec affectation',*data['days']])
            for r in data['rows']:w.writerow([safe(r['name']),r['active'],r['worked_days'],*[r['daily'][d] for d in data['days']]])
        elif view=='general':
            w.writerow(['Périmètre','Hubs','Assignés','Traités','En attente','Livrés','Progression %'])
            z=data['summary'];w.writerow([safe(data['hub']['name']),*[z[k] for k in ('hubs','assigned','processed','pending','delivered','progress')]])
        else:
            w.writerow(['Hub','Assignés','Traités','En attente','Livrés','Retournés','Refusés','Progression %'])
            for r in data['rows']:w.writerow([safe(r['name']),*[r[k] for k in ('assigned','processed','pending','delivered','returned','refused','progress')]])
        return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="analytique-admin-hubs.csv"','Cache-Control':'no-store'})
