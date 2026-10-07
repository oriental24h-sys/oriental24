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
5. **أول مدير (حسب الخطة)** :
   - **خطة مدفوعة (Shell متاح)** : من Shell ديال Render نفّذ `python manage.py init-admin --email admin@votre-domaine.ma --name "Votre Nom"` (كلمة السر تُكتب تفاعلياً).
   - **خطة مجانية (بلا Shell)** : أضف قبل Deploy المتغير `ORIENTAL24_BOOTSTRAP_ADMIN` بالشكل `votre-email@domaine.ma|Votre Nom|MotDePasse>=12` — يُنشأ المدير تلقائياً عند أول تشغيل فقط. ⚠️ لا تستعمل ايميلات الديمو (`admin@/client@/livreur@oriental24.ma`) — مرفوضة. بعد أول دخول ناجح: بدّل كلمة السر من الملف الشخصي ثم احذف المتغير (الخطة المجانية: أبقِه إن أردت استرجاع الحساب بعد مسح البيانات المؤقتة).
6. أنشئ من حساب المدير: المدن والتعريفات، حسابات العملاء والسائقين — **لا توجد أي بيانات تجريبية في وضع الإنتاج** (`ORIENTAL24_PUBLIC_REGISTRATION=0` يغلق التسجيل العمومي).
NOTE: في النشر اليدوي (New Web Service) بدل Blueprint: Build=`pip install -r requirements.txt` · Start=`mkdir -p /var/data/oriental24 && chmod 700 /var/data/oriental24 && gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 60 app:app` · المتغيرات الستة أعلاه تُضاف يدوياً (الخطة المجانية: بدون قرص — البيانات مؤقتة وتُمسح عند إعادة النشر).

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

## ترحيل v1.8.x (GPS · Tour de contrôle · OTP · Messagerie guidée)

- **لا حاجة لأي ترحيل يدوي**: عند الإقلاع يُنشئ التطبيق تلقائيًا (بصيغة مكررة/آمنة) جدولي
  `driver_positions` (آخر 49 موقعًا لكل سائق) و`parcel_messages` (رسائل جاهزة للعميل)،
  ويضيف أعمدة `otp_required` و`otp_code` و`otp_verified_at` إلى جدول `parcels`.
- **ملفات ثابتة جديدة** يجب نشرها مع الكود: `static/tour-control.js` (v1.8.0) و`static/qrcode-gen.js` (v1.7.2).
- **Service Worker** لتطبيق السائق: الإصدار `o24-driver-1.8.1` (يُحدَّث تلقائيًا عند أول فتح بعد النشر).
- **نقاط API جديدة**: `GET /api/control-tower` و`GET /api/dispatch/suggest` (Admin) و
  `POST /api/driver/position` (سائق) و`POST /api/parcels/<id>/otp` و`POST /api/parcels/<id>/messages` و
  `GET /api/public/track/<tracking>` (بدون جلسة، 30 طلبًا/دقيقة/IP، بدون عنوان أو مبلغ أو اسم مستلم).

## ترحيل v1.9.x « التقنيات المتقدمة »

عند الترقية من v1.8.x إلى v1.9.0 تُنشأ **تلقائياً عند أول إقلاع** (بدون أي تدخل يدوي في القاعدة):

- جداول جديدة: `outbox` (صندوق إرسال WhatsApp/SMS)، `parcel_telemetry` (مستشعرات IoT)،
  `proof_seals` (أختام سلسلة البلوك تشين)، `geofence_hits` (تنبيهات السياج الجغرافي)،
  `sort_zones` (مناطق الفرز، تُزرع 4 مناطق افتراضياً: A الشرقي، B الشمال، C الوسط، D الجنوب).
- ملفات ثابتة جديدة: `static/advanced.js` + `offline/advanced.js` (مرآة العرض دون إنترنت).
- خدمة العامل (Service Worker) تُحدَّث إلى `o24-driver-1.9.0` (تنظيف تلقائي للنسخ القديمة).
- مسارات API جديدة: `GET /api/outbox` · `POST /api/outbox/<id>/sent` · `POST /api/parcels/<id>/notify` ·
  `GET|POST /api/parcels/<id>/telemetry` · `GET /api/parcels/<id>/proof` · `POST /api/parcels/<id>/proof/seal` ·
  `GET /api/insights` · `GET|POST /api/sort-zones` · `GET /api/parcels/<id>/zone` · `POST /api/public/assistant`.
- **لا اعتماد على أي خارج**: روابط WhatsApp/SMS تُفتح على هاتف المستخدم (wa.me / sms:)؛
  بوابة المزوّد المدفوع (WhatsApp Business / SMS) تُركّب لاحقاً على جدول `outbox` دون تغيير الكود.
- الـ ETA التنبؤي يتعلّم من تاريخ التسليمات الموجود؛ ما دام التاريخ ضئيلاً يعود تلقائياً
  إلى المعادلة الشفافة (18 دقيقة/توقف + 1.875 دقيقة/كم).

## ترحيل إلى الإصدار v1.10.0 (الأسطول المتصل والتسليم المطوّر)

1. `git am oriental24-v1.9.0-to-v1.10.0.patch` (أو نسخ الملفات من `oriental24-v1.10.0-full.zip`).
2. أعد تشغيل الخدمة : الجداول الجديدة تُنشأ تلقائياً (`vehicles`, `service_logs`, `pickup_points`,
   `locker_assignments`, `payment_requests`) مع عمود `state` في `vehicles` وعمود `pickup_point_id`
   في `parcels` (ترحيل ALTER آمن).
3. البيانات المرجعية : تُزرع 3 نقاط تسليم ذكية (إن وُجدت جدول المدن) — بدون مدن تبقى `city_id` فارغة.
4. لا مفتاح خارجي مطلوب : لا دفع عبر أطراف ثالثة، لا خرائط — الروابط تُرسل عبر WhatsApp/SMS.
5. التحقق : `GET /healthz` → `{"version":"1.10.0"}` ثم `python3 -m pytest -q` (326 اختباراً) و
   `python3 qa/smart_delivery_workflow.py` (41 تحكماً).

## ترحيل إلى الإصدار v1.11.0 (المستودع الذكي والروبوتات)

1. `git am oriental24-v1.10.0-to-v1.11.0.patch` (أو نسخ الملفات من `oriental24-v1.11.0-full.zip`).
2. أعد تشغيل الخدمة : الجداول الجديدة تُنشأ تلقائياً (`warehouses`, `warehouse_slots`,
   `parcel_storage`, `warehouse_bots`, `bot_missions`, `reception_checks`, `sync_snapshots`) مع
   عمودي `delivery_mode` و`weight_kg` في `parcels` (ترحيل ALTER آمن).
3. البيانات المرجعية : يُنشأ مستودع « Oujda » بـ 30 موضعاً (A-01-1 … C-05-2) عند أول إقلاع.
4. مزامنة الوكالات : `GET /api/sync/export` ثم `POST /api/sync/import` على الوكالة الأخرى —
   التوقيع SHA-256 يُرفض عند العبث (رمز 400).
5. التحقق : `GET /healthz` → `{"version":"1.11.0"}` ثم `python3 -m pytest -q` (339 اختباراً).

### ترحيل إلى الإصدار v1.12.0
- تكنولوجيات RFID والتتبع والتنفيذ الميداني : تحميل `oriental24-v1.11.0-to-v1.12.0.patch` أو `oriental24-v1.12.0-full.zip`.
- التحقق : `python3 -m pytest -q` ثم `python3 qa/connected_ops_workflow.py` (44 تحكماً) ثم `python3 qa/smart_warehouse_workflow.py`.
- الواجهة : لوحة « Exécution terrain & RFID » (التقاط الأبعاد، RFID، الالتقاط الموجه، خطة التحميل، الصوت). الصوت يتطلب Web Speech API (Chrome/Edge) وإلا يعود إلى اللمس.
- لا يتطلب أي وسيط RFID أو خدمة صوتية خارجية.
