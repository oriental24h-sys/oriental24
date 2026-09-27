"""Downloadable A4 PDF; scoped invoice data only, no network fetches or browser process."""
from pathlib import Path
from io import BytesIO
from html import escape
import re
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer,Image,KeepTogether
from reportlab.pdfgen.canvas import Canvas
ROOT=Path(__file__).resolve().parent
for name,file in [('O24','DejaVuSans.ttf'),('O24Bold','DejaVuSans-Bold.ttf')]:pdfmetrics.registerFont(TTFont(name,str(ROOT/'static/fonts'/file)))
pdfmetrics.registerFontFamily('O24',normal='O24',bold='O24Bold',italic='O24',boldItalic='O24Bold')
NAVY=colors.HexColor('#0b223f');GREY=colors.HexColor('#667383');LINE=colors.HexColor('#bdc5cf')
def invoice_pdf(d):
    r=d['invoice'];issuer=d['issuer'];rec=d['recipient'];record=d['record'];width=178*mm
    normal=ParagraphStyle('body',fontName='O24',fontSize=8,leading=12,textColor=NAVY,spaceAfter=0,wordWrap='CJK')
    small=ParagraphStyle('small',parent=normal,fontSize=6.5,leading=9,textColor=GREY)
    right=ParagraphStyle('right',parent=normal,alignment=TA_RIGHT)
    def clean(v):
        v=str(v if v is not None else '')
        if re.search('[\u0600-\u06ff]',v):v=get_display(arabic_reshaper.reshape(v))
        return escape(v).replace('\n','<br/>')
    def p(v,style=normal):return Paragraph(clean(v),style)
    def bold(v):return Paragraph('<b>'+clean(v)+'</b>',normal)
    def money(v):return f'{v/100:,.2f}'.replace(',',' ').replace('.',',')+' MAD'
    legal=' · '.join(label+' : '+issuer[k] for k,label in [('ice','ICE'),('rc','RC'),('if_number','IF'),('tp','TP'),('cnss','CNSS')] if issuer.get(k))
    legal_p=p(legal,small);_,legal_h=legal_p.wrap(width,100*mm)
    footer_h=legal_h+17*mm
    class NumberedCanvas(Canvas):
        def __init__(self,*a,**kw):super().__init__(*a,**kw);self.pages=[]
        def showPage(self):self.pages.append(dict(self.__dict__));self._startPage()
        def save(self):
            count=len(self.pages)
            for state in self.pages:
                self.__dict__.update(state);self.setStrokeColor(LINE);self.line(16*mm,footer_h-2*mm,A4[0]-16*mm,footer_h-2*mm)
                self.setFont('O24',6.5);self.setFillColor(GREY);self.drawString(16*mm,footer_h-7*mm,'Relevé interne non assimilable à une facture fiscale'+(' · ANNULÉ' if r['state']=='Annulé' else ''))
                self.setFont('O24Bold',7);self.drawRightString(A4[0]-16*mm,footer_h-7*mm,f'Page : {self._pageNumber} / {count}')
                if legal:legal_p.drawOn(self,16*mm,9*mm)
                self.setFont('O24',6);self.drawString(16*mm,5.5*mm,'Mouvements déclaratifs · Aucun virement bancaire exécuté par ORIENTAL24')
                super().showPage()
            super().save()
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=16*mm,rightMargin=16*mm,topMargin=16*mm,bottomMargin=footer_h+4*mm,title='ORIENTAL24 '+r['reference'],author='ORIENTAL24')
    story=[]
    def tab(headers,rows,widths,title=None):
        data=[[bold(h) for h in headers]]+[[v if isinstance(v,Paragraph) else p(v) for v in row] for row in rows]
        t=Table(data,colWidths=[width*x/100 for x in widths],repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('LINEBELOW',(0,0),(-1,0),1,NAVY),('LINEBELOW',(0,1),(-1,-1),.4,LINE)]))
        if title:story.extend([Spacer(1,4*mm),Paragraph('<b>'+clean(title)+'</b>',ParagraphStyle('section',parent=normal,keepWithNext=True))])
        story.extend([t,Spacer(1,4*mm)])
    org='\n'.join(filter(None,[issuer.get('legal_name') or 'ORIENTAL24',issuer.get('address'),issuer.get('city'),issuer.get('phone'),issuer.get('email')]))
    logo=Image(str(ROOT/'static/wordmark.png'),width=47*mm,height=13*mm,kind='proportional');logo.hAlign='LEFT'
    top=Table([[logo,p(org,right)]],colWidths=[width*.48,width*.52]);top.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]));story.extend([top,Spacer(1,9*mm),Paragraph('Facture',ParagraphStyle('title',parent=normal,fontSize=23,leading=30)),Spacer(1,3*mm)])
    subject='Livreur' if r['kind']=='livreur' else 'Client'
    meta=f"Facture N° : {r['reference']}\nDate : {(r['created_at'] or '')[:10]}\nÉtat : {r['state']}\nNombre de colis : {r['parcel_count']}"
    who='\n'.join(filter(None,[subject+' : '+r['name'],rec.get('driver_address'),rec.get('city'),rec.get('phone'),r['email']]))
    m=Table([[p(meta),p(who)]],colWidths=[width*.49,width*.51]);m.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),1,NAVY),('LINEBELOW',(0,0),(-1,0),.5,LINE),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]));story.append(m)
    if r['state']=='Annulé':story.extend([Spacer(1,4*mm),bold('ANNULÉ · '+record.get('cancel_reason',''))])
    groups={}
    for row in d['lines']:key=(row['status'],row['fees_cents']);groups[key]=groups.get(key,0)+1
    rows=[[status,p(money(fee),right),p(n,right),p(money(fee*n),right)] for (status,fee),n in groups.items()]
    tab(['Désignation','Prix unitaire','Quantité','Total'],rows,[40,23,12,25],'Récapitulatif des prestations')
    totals=Table([[p(label),p(money(r[k]),right)] for label,k in [('Total COD livré','cod_cents'),('Frais / commissions' if r['kind']=='livreur' else 'Frais de service','fees_cents'),('Total Net','net_cents')]],colWidths=[width*.65,width*.35]);totals.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('LINEABOVE',(0,2),(-1,2),.5,LINE)]));story.extend([totals,Spacer(1,4*mm)])
    if r['kind']=='livreur':
        settlement=f"{'Remise nette' if record['mode']=='net' else 'Remise intégrale'} · Retenue autorisée : {money(record['retained_cents'])}\nCOD restant à remettre par le livreur : {money(r['incoming_cents'])}\nCommission restant à payer au livreur : {money(r['outgoing_cents'])}\nLe Total Net = COD livré − commissions ; il ne remplace pas ces deux soldes."
    else:settlement=f"Solde restant à verser au client : {money(r['outgoing_cents'])}\nSolde restant à recevoir du client : {money(r['incoming_cents'])}\n{'Sans flux : net nul.' if not r['net_cents'] else 'Règlements réellement déclarés, distincts du montant net initial.'}"
    if issuer.get('payment_terms') and r['kind']=='livreur':settlement+='\n'+issuer['payment_terms']
    if r['kind']=='client':settlement+='\nCoordonnées entreprise actuelles ; aucun délai de paiement présumé.'
    story.extend([p(settlement,small),Spacer(1,3*mm)])
    rows=[[l['tracking'],l['city'],l['phone'] or '—',p(money(l['amount_cents']).replace(' MAD','') if l['amount_cents'] is not None else '—',right),l['status'],p(money(l['fees_cents']).replace(' MAD',''),right)] for l in d['lines']]
    tab(['ID de suivi','Ville','Téléphone','COD¹','Statut','Frais'],rows,[30,18,17,13,12,10],'Détail des colis · montants MAD')
    story.append(p('¹ COD nominal du colis ; seul le COD des Livrés entre dans le Total COD livré. Un tiret indique une donnée non archivée. Les prix unitaires sont regroupés par tarif exact.',small))
    if d['transactions']:
        rows=[]
        for t in d['transactions']:
            flow=('Remise COD' if t.get('kind')=='cash' else 'Commission') if r['kind']=='livreur' else ('Vers le client' if r['net_cents']>0 else 'Reçu du client')
            rows.append([t.get('paid_on') or t.get('payment_date') or 'Date inconnue',flow,money(t['amount_cents']),t['method']+'\n'+t['reference'],'Annulé : '+(t.get('void_reason') or '') if t['voided_at'] else 'Enregistré'])
        tab(['Date','Flux','Montant','Mode / Référence','État'],rows,[15,17,20,28,20],'Journal des règlements')
    else:story.extend([Spacer(1,4*mm),p('Aucun règlement enregistré.',small)])
    def continued(canvas,doc):
        canvas.saveState();canvas.setFont('O24Bold',8);canvas.setFillColor(NAVY);canvas.drawString(16*mm,A4[1]-10*mm,'ORIENTAL24 · '+r['reference']+(' · ANNULÉ' if r['state']=='Annulé' else ''));canvas.restoreState()
    doc.build(story,onLaterPages=continued,canvasmaker=NumberedCanvas)
    return out.getvalue()
