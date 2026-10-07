"""Espace mobile ORIENTAL24 — page publique de téléchargement + service de l'APK.

Aucune authentification : un livreur doit pouvoir installer l'application avant
même de disposer d'un compte connecté. La page est en arabe (RTL) car elle est
destinée aux livreurs ; le reste de l'application reste en français.

Fichier servi : static/apk/ORIENTAL24-Livreur.apk (application Android signée,
WebView sécurisée — voir le dossier apk-livreur/ pour les sources du build).
"""
import os
from flask import request, Response, send_file, redirect

BASE = os.path.dirname(os.path.abspath(__file__))
APK_CANDIDATES = [
    os.path.join(BASE, 'static', 'apk', 'ORIENTAL24-Livreur.apk'),
    os.path.join(BASE, 'ORIENTAL24-Livreur.apk'),
    os.path.join(BASE, 'static', 'ORIENTAL24-Livreur.apk'),
]
APK_PATH = next((p for p in APK_CANDIDATES if os.path.isfile(p)), APK_CANDIDATES[0])
APK_FILENAME = 'ORIENTAL24-Livreur.apk'
# Lien permanent : l'APK est publié dans les « Releases » GitHub ; il pointe toujours
# vers la dernière version déposée. Utilisé quand le fichier n'est pas dans le dépôt.
RELEASE_URL = ('https://github.com/oriental24h-sys/oriental24/releases/'
               'latest/download/ORIENTAL24-Livreur.apk')
APK_VERSION = '1.0'
APK_MIN_ANDROID = 'Android 5.0 وأكثر'

QR = {
    'web-production-1f5c6.up.railway.app': '<svg viewBox="0 0 41 41"><path stroke="#0b1526" d="M4 4.5h7m1 0h1m1 0h2m1 0h2m1 0h1m1 0h6m2 0h7m-33 1h1m5 0h1m1 0h2m1 0h3m4 0h1m3 0h2m2 0h1m5 0h1m-33 1h1m1 0h3m1 0h1m2 0h2m1 0h1m2 0h1m2 0h1m1 0h1m1 0h1m3 0h1m1 0h3m1 0h1m-33 1h1m1 0h3m1 0h1m1 0h1m1 0h3m1 0h1m1 0h2m1 0h1m2 0h1m3 0h1m1 0h3m1 0h1m-33 1h1m1 0h3m1 0h1m2 0h4m1 0h1m4 0h1m4 0h1m1 0h1m1 0h3m1 0h1m-33 1h1m5 0h1m2 0h2m1 0h3m2 0h3m1 0h2m1 0h1m1 0h1m5 0h1m-33 1h7m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h7m-25 1h2m1 0h1m5 0h1m1 0h2m3 0h1m-25 1h1m1 0h2m1 0h3m1 0h1m1 0h1m2 0h1m1 0h2m1 0h1m1 0h1m1 0h2m1 0h1m2 0h1m1 0h2m-33 1h1m2 0h2m3 0h2m4 0h1m3 0h4m1 0h1m2 0h2m1 0h2m1 0h1m-33 1h1m2 0h5m4 0h1m1 0h1m2 0h2m3 0h3m2 0h3m1 0h2m-31 1h1m1 0h2m1 0h1m1 0h2m1 0h4m2 0h2m4 0h1m2 0h1m1 0h1m1 0h2m-32 1h2m3 0h5m1 0h1m2 0h1m1 0h1m1 0h2m1 0h3m3 0h2m-29 1h2m1 0h1m2 0h1m2 0h4m2 0h1m1 0h2m1 0h1m5 0h1m1 0h1m1 0h1m-32 1h2m3 0h2m1 0h1m1 0h2m3 0h2m1 0h4m4 0h4m-30 1h2m1 0h1m1 0h1m1 0h2m3 0h2m2 0h1m4 0h2m1 0h4m1 0h2m-26 1h2m3 0h2m1 0h1m1 0h2m3 0h4m1 0h2m1 0h3m-30 1h1m3 0h1m1 0h3m1 0h1m3 0h2m1 0h1m1 0h4m2 0h1m1 0h2m2 0h1m-33 1h1m1 0h1m3 0h1m6 0h1m1 0h4m2 0h2m1 0h5m1 0h2m-30 1h2m1 0h1m1 0h1m1 0h1m5 0h1m1 0h1m10 0h1m-29 1h4m1 0h2m4 0h1m1 0h2m4 0h1m1 0h1m2 0h1m4 0h2m1 0h1m-33 1h1m3 0h1m8 0h1m1 0h1m2 0h4m1 0h1m2 0h1m5 0h1m-30 1h2m1 0h4m1 0h2m1 0h1m1 0h2m2 0h1m1 0h2m1 0h4m2 0h2m-32 1h1m3 0h1m3 0h2m1 0h3m1 0h1m1 0h2m2 0h1m3 0h4m2 0h1m-33 1h1m1 0h1m3 0h1m1 0h2m3 0h3m1 0h1m1 0h2m1 0h1m1 0h5m2 0h1m-24 1h1m1 0h2m2 0h4m1 0h1m2 0h3m3 0h2m-30 1h7m1 0h4m7 0h2m2 0h2m1 0h1m1 0h1m2 0h1m-32 1h1m5 0h1m1 0h2m2 0h2m1 0h2m1 0h2m1 0h4m3 0h3m-31 1h1m1 0h3m1 0h1m2 0h2m6 0h1m2 0h9m1 0h1m1 0h1m-33 1h1m1 0h3m1 0h1m1 0h1m1 0h1m1 0h2m6 0h1m1 0h2m3 0h1m1 0h2m1 0h1m-33 1h1m1 0h3m1 0h1m1 0h1m1 0h2m5 0h1m2 0h5m1 0h2m2 0h1m-31 1h1m5 0h1m2 0h1m3 0h1m1 0h3m1 0h2m1 0h1m1 0h1m1 0h3m3 0h1m-33 1h7m1 0h1m2 0h1m2 0h2m1 0h1m1 0h1m1 0h1m1 0h1m4 0h3"/></svg>',
    'web-production-a3fb6.up.railway.app': '<svg viewBox="0 0 41 41"><path stroke="#0b1526" d="M4 4.5h7m2 0h2m1 0h2m1 0h1m2 0h2m3 0h1m2 0h7m-33 1h1m5 0h1m3 0h1m1 0h5m1 0h1m1 0h2m1 0h1m2 0h1m5 0h1m-33 1h1m1 0h3m1 0h1m2 0h5m1 0h1m1 0h1m1 0h2m1 0h3m1 0h1m1 0h3m1 0h1m-33 1h1m1 0h3m1 0h1m3 0h2m1 0h2m1 0h1m1 0h1m3 0h3m1 0h1m1 0h3m1 0h1m-33 1h1m1 0h3m1 0h1m3 0h1m2 0h2m2 0h2m4 0h1m2 0h1m1 0h3m1 0h1m-33 1h1m5 0h1m1 0h2m2 0h2m1 0h6m3 0h1m1 0h1m5 0h1m-33 1h7m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h7m-23 1h2m2 0h4m1 0h1m1 0h2m1 0h1m-25 1h1m2 0h1m1 0h2m1 0h1m1 0h1m2 0h2m1 0h1m1 0h1m2 0h1m3 0h1m1 0h1m-25 1h3m3 0h1m1 0h1m1 0h2m2 0h1m2 0h2m2 0h4m3 0h2m-32 1h2m1 0h1m1 0h2m5 0h2m4 0h1m2 0h1m2 0h1m1 0h2m1 0h1m1 0h1m-31 1h1m2 0h1m1 0h2m2 0h3m2 0h1m1 0h5m1 0h1m1 0h1m1 0h2m1 0h1m-31 1h4m1 0h2m3 0h2m1 0h1m1 0h2m1 0h1m1 0h1m1 0h2m1 0h2m1 0h1m2 0h1m-33 1h2m1 0h1m3 0h3m1 0h2m1 0h2m2 0h3m1 0h1m3 0h1m1 0h2m1 0h2m-32 1h1m2 0h7m1 0h2m1 0h3m2 0h2m1 0h6m1 0h2m-32 1h2m1 0h2m3 0h4m4 0h4m1 0h3m2 0h2m3 0h1m-32 1h1m3 0h1m1 0h2m2 0h1m2 0h5m1 0h4m1 0h1m1 0h1m1 0h1m2 0h1m-28 1h1m2 0h2m14 0h1m3 0h1m1 0h1m-30 1h1m3 0h1m1 0h1m1 0h3m1 0h3m1 0h3m1 0h1m3 0h2m4 0h3m-30 1h3m1 0h2m1 0h2m2 0h1m1 0h2m2 0h3m3 0h2m4 0h1m-30 1h1m2 0h2m3 0h2m1 0h1m2 0h2m2 0h1m1 0h1m1 0h1m5 0h2m-32 1h1m2 0h2m1 0h1m1 0h1m1 0h2m2 0h1m1 0h1m2 0h2m2 0h3m2 0h4m-33 1h2m1 0h1m1 0h2m1 0h1m4 0h2m1 0h1m1 0h3m1 0h1m1 0h1m1 0h5m1 0h1m-32 1h5m2 0h2m2 0h1m2 0h1m2 0h4m7 0h1m-30 1h1m2 0h1m2 0h1m1 0h1m4 0h1m2 0h4m1 0h1m2 0h5m2 0h2m-25 1h2m2 0h1m4 0h5m1 0h2m3 0h2m2 0h1m-33 1h7m2 0h2m1 0h2m2 0h3m1 0h1m3 0h1m1 0h1m1 0h3m-31 1h1m5 0h1m1 0h2m2 0h1m3 0h2m3 0h2m1 0h1m3 0h1m2 0h1m-32 1h1m1 0h3m1 0h1m2 0h5m4 0h5m1 0h6m1 0h2m-33 1h1m1 0h3m1 0h1m1 0h2m2 0h1m1 0h3m4 0h1m1 0h1m2 0h1m1 0h3m-31 1h1m1 0h3m1 0h1m3 0h2m1 0h6m4 0h2m3 0h1m1 0h1m1 0h1m-33 1h1m5 0h1m2 0h1m3 0h1m3 0h3m1 0h1m2 0h1m-25 1h7m1 0h2m2 0h2m1 0h2m4 0h1m2 0h2m2 0h1m2 0h1"/></svg>',
}
QR_DEFAULT = '<svg viewBox="0 0 41 41"><path stroke="#0b1526" d="M4 4.5h7m1 0h1m1 0h2m1 0h2m1 0h1m1 0h6m2 0h7m-33 1h1m5 0h1m1 0h2m1 0h3m4 0h1m3 0h2m2 0h1m5 0h1m-33 1h1m1 0h3m1 0h1m2 0h2m1 0h1m2 0h1m2 0h1m1 0h1m1 0h1m3 0h1m1 0h3m1 0h1m-33 1h1m1 0h3m1 0h1m1 0h1m1 0h3m1 0h1m1 0h2m1 0h1m2 0h1m3 0h1m1 0h3m1 0h1m-33 1h1m1 0h3m1 0h1m2 0h4m1 0h1m4 0h1m4 0h1m1 0h1m1 0h3m1 0h1m-33 1h1m5 0h1m2 0h2m1 0h3m2 0h3m1 0h2m1 0h1m1 0h1m5 0h1m-33 1h7m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h1m1 0h7m-25 1h2m1 0h1m5 0h1m1 0h2m3 0h1m-25 1h1m1 0h2m1 0h3m1 0h1m1 0h1m2 0h1m1 0h2m1 0h1m1 0h1m1 0h2m1 0h1m2 0h1m1 0h2m-33 1h1m2 0h2m3 0h2m4 0h1m3 0h4m1 0h1m2 0h2m1 0h2m1 0h1m-33 1h1m2 0h5m4 0h1m1 0h1m2 0h2m3 0h3m2 0h3m1 0h2m-31 1h1m1 0h2m1 0h1m1 0h2m1 0h4m2 0h2m4 0h1m2 0h1m1 0h1m1 0h2m-32 1h2m3 0h5m1 0h1m2 0h1m1 0h1m1 0h2m1 0h3m3 0h2m-29 1h2m1 0h1m2 0h1m2 0h4m2 0h1m1 0h2m1 0h1m5 0h1m1 0h1m1 0h1m-32 1h2m3 0h2m1 0h1m1 0h2m3 0h2m1 0h4m4 0h4m-30 1h2m1 0h1m1 0h1m1 0h2m3 0h2m2 0h1m4 0h2m1 0h4m1 0h2m-26 1h2m3 0h2m1 0h1m1 0h2m3 0h4m1 0h2m1 0h3m-30 1h1m3 0h1m1 0h3m1 0h1m3 0h2m1 0h1m1 0h4m2 0h1m1 0h2m2 0h1m-33 1h1m1 0h1m3 0h1m6 0h1m1 0h4m2 0h2m1 0h5m1 0h2m-30 1h2m1 0h1m1 0h1m1 0h1m5 0h1m1 0h1m10 0h1m-29 1h4m1 0h2m4 0h1m1 0h2m4 0h1m1 0h1m2 0h1m4 0h2m1 0h1m-33 1h1m3 0h1m8 0h1m1 0h1m2 0h4m1 0h1m2 0h1m5 0h1m-30 1h2m1 0h4m1 0h2m1 0h1m1 0h2m2 0h1m1 0h2m1 0h4m2 0h2m-32 1h1m3 0h1m3 0h2m1 0h3m1 0h1m1 0h2m2 0h1m3 0h4m2 0h1m-33 1h1m1 0h1m3 0h1m1 0h2m3 0h3m1 0h1m1 0h2m1 0h1m1 0h5m2 0h1m-24 1h1m1 0h2m2 0h4m1 0h1m2 0h3m3 0h2m-30 1h7m1 0h4m7 0h2m2 0h2m1 0h1m1 0h1m2 0h1m-32 1h1m5 0h1m1 0h2m2 0h2m1 0h2m1 0h2m1 0h4m3 0h3m-31 1h1m1 0h3m1 0h1m2 0h2m6 0h1m2 0h9m1 0h1m1 0h1m-33 1h1m1 0h3m1 0h1m1 0h1m1 0h1m1 0h2m6 0h1m1 0h2m3 0h1m1 0h2m1 0h1m-33 1h1m1 0h3m1 0h1m1 0h1m1 0h2m5 0h1m2 0h5m1 0h2m2 0h1m-31 1h1m5 0h1m2 0h1m3 0h1m1 0h3m1 0h2m1 0h1m1 0h1m1 0h3m3 0h1m-33 1h7m1 0h1m2 0h1m2 0h2m1 0h1m1 0h1m1 0h1m1 0h1m4 0h3"/></svg>'

PAGE = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>تطبيق الليفرو · ORIENTAL24</title>
<meta name="theme-color" content="#0b1526">
<link rel="icon" href="/static/icon-driver-192.png">
<style>
*{box-sizing:border-box}
body{margin:0;background:#0b1526;color:#e9eef7;font-family:system-ui,-apple-system,"Segoe UI",Tahoma,sans-serif;line-height:1.7}
.wrap{max-width:560px;margin:0 auto;padding:20px 16px 46px}
header{display:flex;align-items:center;gap:14px;padding:16px 0 22px}
header img{width:62px;height:62px;border-radius:16px;box-shadow:0 8px 24px rgba(0,0,0,.35)}
h1{margin:0;font-size:23px}
header p{margin:2px 0 0;color:#9fb0c9;font-size:13px}
.btn{display:block;text-align:center;background:#e4681a;color:#fff;text-decoration:none;
     font-size:20px;font-weight:700;padding:17px 18px;border-radius:16px;margin:6px 0 8px;
     box-shadow:0 10px 26px rgba(228,104,26,.32)}
.btn small{display:block;font-size:12px;font-weight:400;opacity:.9;margin-top:3px}
.hint{color:#9fb0c9;font-size:12.5px;text-align:center;margin:4px 0 0}
.card{background:#17263f;border:1px solid #24395c;border-radius:18px;padding:18px;margin-top:18px}
.card h2{margin:0 0 12px;font-size:16px;color:#fff}
.qr{background:#fff;border-radius:14px;padding:12px;max-width:220px;margin:0 auto}
.qr svg{display:block;width:100%;height:auto}
ol{margin:0;padding:0;list-style:none}
ol li{background:#0f1d33;border:1px solid #24395c;border-radius:13px;padding:12px 13px;margin-bottom:9px;font-size:14.5px}
ol li b:first-child{color:#e4681a}
.mini{display:block;color:#9fb0c9;font-size:12.5px;margin-top:5px}
.alt{display:block;text-align:center;border:1px solid #2a3d5c;color:#cdd8ea;text-decoration:none;
     padding:13px;border-radius:14px;margin-top:14px;font-size:15px}
table{width:100%;border-collapse:collapse;font-size:13.5px}
td{padding:6px 0;border-bottom:1px dashed #24395c;color:#cdd8ea}
td:last-child{text-align:left;color:#fff;font-weight:600}
footer{text-align:center;color:#7c8aa8;font-size:12px;margin-top:26px}
.shield{display:flex;gap:9px;align-items:flex-start;font-size:12.5px;color:#9fb0c9;margin-top:16px}
.shield b{color:#7fe0a8}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <img src="/static/wordmark.png" alt="ORIENTAL24">
    <div>
      <h1>تطبيق الليفرو</h1>
      <p>ORIENTAL24 · الإصدار __VERSION__ · __SIZE__</p>
    </div>
  </header>

  <a class="btn" href="/apk" download>⬇️ حمّل التطبيق دابا
    <small>__SIZE__ · __MIN__</small></a>
  <p class="hint">خاصك تيليفون Android · التطبيق كيتصل غير بالسيرفر الرسمي ديال ORIENTAL24</p>

  <div class="card">
    <h2>ولا سكانّي هاد الكود من تيليفون آخر</h2>
    <div class="qr">__QR__</div>
    <p class="hint">حل الكاميرا → صوّب على الكود → تتفتح ليك هاد الصفحة</p>
  </div>

  <div class="card">
    <h2>كيفاش تركّب التطبيق؟ 3 خطوات</h2>
    <ol>
      <li><b>1.</b> اضغط على زر <b>حمّل التطبيق دابا</b> و تسنّى الملف يكمل.
        <span class="mini">إيلا خرجات ليك رسالة «الملف يمكن يكون خطر» اختار <b>حمّل على أي حال</b> (Download anyway) — هذا عادي فكل التطبيقات خارج Play Store.</span></li>
      <li><b>2.</b> من بعد التحميل اضغط <b>فتح</b>، وإيلا طلب منك الإذن: <b>الإعدادات → السماح بتثبيت تطبيقات من هاد المصدر</b> ✅
        <span class="mini">الاسم فالجهاز غادي يكون: <b>ORIENTAL24 Livreur</b></span></li>
      <li><b>3.</b> حل التطبيق و دخل <b>الإيميل</b> و <b>كلمة السر</b> اللي عطاك المدير.
        <span class="mini">ماعندكش حساب؟ طلبو من المدير ديالك و غادي يتصاوب ليك فدقيقة.</span></li>
    </ol>
  </div>

  <div class="card">
    <h2>معلومات التطبيق</h2>
    <table>
      <tr><td>الإصدار</td><td>__VERSION__</td></tr>
      <tr><td>الحجم</td><td>__SIZE__</td></tr>
      <tr><td>آخر تحديث</td><td>__DATE__</td></tr>
      <tr><td>كيتخدم على</td><td>__MIN__</td></tr>
      <tr><td>الوظائف</td><td>الكوليات ديال اليوم · البحث برقم التيليفون · السكانير · التحصيل · التتبع</td></tr>
    </table>
    <div class="shield"><span>🔒</span><span>كيتوصل التطبيق بغير <b>السيرفر الرسمي</b> ديال ORIENTAL24 عبر HTTPS. الروابط الأخرى كيتحلو فالمتصفح.</span></div>
  </div>

  <a class="alt" href="/app">🌐 بغيتي تخدم بلا تثبيت؟ حل النسخة على المتصفح</a>
  <p class="hint" style="margin-top:14px">عندك iPhone؟ حل النظام من Safari → زر المشاركة → <b>إضافة إلى الشاشة الرئيسية</b>، و غادي يخدم بحال شي تطبيق.</p>

  <footer>ORIENTAL24 · التوصيل حتى لباب الدار · هاد الصفحة مفتوحة بلا حساب لأجل تحميل التطبيق</footer>
</div>
</body>
</html>
"""


def _size_label(path):
    try:
        n = os.path.getsize(path)
    except OSError:
        return '—'
    if n >= 1024 * 1024:
        return '%.1f ميغا' % (n / 1048576.0)
    return '%d كيلوبايت' % max(1, int(round(n / 1024.0)))


def _date_label(path):
    try:
        return __import__('datetime').datetime.fromtimestamp(os.path.getmtime(path)).strftime('%d/%m/%Y')
    except OSError:
        return '—'


def _missing_page():
    html = ('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>ORIENTAL24 — التطبيق ماشي متوفر</title></head>'
            '<body style="font-family:system-ui,sans-serif;background:#0b1526;color:#e9eef7;'
            'display:grid;place-items:center;min-height:100vh;margin:0;text-align:center">'
            '<div style="max-width:420px;padding:20px"><h1>التطبيق ماشي متوفر حالياً</h1>'
            '<p style="color:#9fb0c9">ملف التثبيت ماكاينش على هاد السيرفر. عيط على المدير ديالك '
            'ولا استعمل النسخة على المتصفح من <a style="color:#e4681a" href="/app">هنا</a>.</p></div>'
            '</body></html>')
    return Response(html, 404, content_type='text/html; charset=utf-8')


def register_mobile_app(app, services=None):
    def apk_path():
        return next((p for p in APK_CANDIDATES if os.path.isfile(p)), APK_CANDIDATES[0])

    @app.route('/telecharger')
    def mobile_download_page():
        host = (request.host or '').split(':')[0].lower()
        qr = QR.get(host, QR_DEFAULT)
        html = (PAGE
                .replace('__QR__', qr)
                .replace('__VERSION__', APK_VERSION)
                .replace('__SIZE__', _size_label(apk_path()))
                .replace('__DATE__', _date_label(apk_path()))
                .replace('__MIN__', APK_MIN_ANDROID))
        return Response(html, 200, content_type='text/html; charset=utf-8')

    @app.route('/apk')
    def mobile_download_file():
        if not os.path.isfile(apk_path()):
            # Pas de fichier dans le dépôt : on renvoie vers la page de publication GitHub
            # (toujours la dernière version, aucun binaire à stocker côté serveur).
            return redirect(RELEASE_URL, code=302)
        return send_file(
            apk_path(),
            mimetype='application/vnd.android.package-archive',
            as_attachment=True,
            download_name=APK_FILENAME,
            conditional=True,
            max_age=300,
        )

    @app.route('/app-livreur')
    def mobile_download_short():
        return redirect('/telecharger', code=302)

    return app
