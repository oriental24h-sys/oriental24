# ORIENTAL24 v1.4.17 — النشر على Render بوضع الإنتاج

## الملفات الجاهزة (موجودة في المستودع)

| الملف | الدور |
|---|---|
| `render.yaml` | Blueprint كامل: خدمة ويب + قرص SQLite دائم + متغيرات البيئة |
| `Procfile` | أمر التشغيل gunicorn (مرجع لأي منصة أخرى) |
| `runtime.txt` | Python 3.13.5 (نفس نسخة الاختبار) |
| `.env.production.example` | نموذج المتغيرات (لا يُحمّل تلقائياً) |
| `/healthz` | نقطة فحص الصحة (تعيد `{status:"ok", production:true}`) |

## خطوات النشر

1. **ارفع المستودع** على GitHub أو GitLab (أرشيف `ORIENTAL24-v1.4.17-source.zip` يحوي كل شيء).
2. على [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint** → اختر المستودع. Render يقرأ `render.yaml` تلقائياً.
3. Render سيطلب قيمة **`ORIENTAL24_TRUSTED_HOSTS`** (sync:false): ضع اسم النطاق بدون https، مثال: `oriental24.onrender.com` (أو نطاقك الخاص بعد ربطه).
4. باقي المتغيرات محسوبة تلقائياً: `SECRET_KEY` تُولَّد عشوائياً، `DB_PATH=/var/data/oriental24/app.sqlite` على القرص الدائم (صلاحيات 0700 في أمر التشغيل)، `ORIENTAL24_MODE=production`، `ORIENTAL24_PUBLIC_REGISTRATION=0`، `ORIENTAL24_PROXY_HOPS=1` (خلف بروكسي Render).
5. بعد أول نشر، افتح **Shell** من لوحة Render ونفّذ إنشاء المدير الأول (كلمة السر تُكتب تفاعلياً، لا تظهر في الأوامر):
   ```bash
   python manage.py init-admin --email admin@votre-domaine.ma --name "Votre Nom"
   ```
6. أنشئ من حساب المدير: المدن والتعريفات، حسابات العملاء والسائقين — **لا توجد أي بيانات تجريبية في وضع الإنتاج** (`ORIENTAL24_PUBLIC_REGISTRATION=0` يغلق التسجيل العمومي).

## تحققات تمت قبل التسليم (وضع الإنتاج)

- `GET /healthz` → 200 `{production:true, version:"1.4.17"}`
- الصفحة الرئيسية على النطاق الموثوق → 200، أعلام الديمو معطّلة
- مضيف غير موثوق → **400** · API بدون جلسة → **401**
- HTTPS إجباري: أي طلب بلا TLS يُرفض (« HTTPS obligatoire »)
- قاعدة البيانات: ملف جديد فارغ على القرص المستقل، بدون حسابات ديمو

## تنبيهات إلزامية

- **الخطّة Starter**: القرص الدائم (1GB) يتطلب خطة مدفوعة على Render؛ الخطة المجانية تفقد قاعدة البيانات عند كل إعادة نشر.
- **أول دخول**: غيّر كلمة السر، فعّل HTTPS (تلقائي على Render)، وراجع إعدادات المدن والتعريفات مع فريقك قبل أول طرد حقيقي.
- **كلمة السر في Shell من Render تُسجَّل في سجلّات المنصة**: بعد الإنشاء، بدّلها من واجهة المدير (الملف الشخصي).
- **هذه الحزمة ليست شهادة أمان إنتاجية**: قبل الاستغلال التجاري، راجع قائمة « Avant une mise en production » في README (نسخ احتياطية دورية عبر `manage.py backup`، مراقبة، مراجعة أمنية).
- لنطاقك الخاص: أضفه في Render (Custom Domain)، ثم حدّث `ORIENTAL24_TRUSTED_HOSTS` بالنطاق الجديد وفعّل CNAME حسب تعليمات Render.
