/* ORIENTAL24 UI language support — stored per browser; API values remain French/backend-native. */
(function () {
  'use strict';

  const LANGUAGE_KEY = 'o24.language';
  const LANGUAGES = {
    fr: { short: 'FR', native: 'Français', tag: 'fr', dir: 'ltr', flag: '🇫🇷' },
    en: { short: 'EN', native: 'English', tag: 'en', dir: 'ltr', flag: '🇺🇸' },
    ar: { short: 'AR', native: 'العربية', tag: 'ar', dir: 'rtl', flag: '🇲🇦' },
  };

  // French is the source language used by the existing screens. Keep API/status values untouched.
  const ENTRIES = [
    ['Tableau de bord', 'Dashboard', 'لوحة التحكم'],
    ['ORIENTAL24 — Votre livraison, notre proximité.', 'ORIENTAL24 — Your delivery, closer to you.', 'ORIENTAL24 — توصيلكم أقرب إليكم.'],
    ['Votre espace se prépare…', 'Your workspace is getting ready…', 'مساحتك قيد التجهيز…'],
    ['Vue d’ensemble', 'Overview', 'نظرة عامة'],
    ['VUE D’ENSEMBLE', 'OVERVIEW', 'نظرة عامة'],
    ['EXPÉDITIONS', 'SHIPMENTS', 'الشحنات'],
    ['GESTION', 'MANAGEMENT', 'الإدارة'],
    ['ESPACE PERSONNEL', 'PERSONAL SPACE', 'المساحة الشخصية'],
    ['Gestion des colis', 'Parcel management', 'إدارة الطرود'],
    ['Mes colis', 'My parcels', 'طرودي'],
    ['Mon app', 'My app', 'تطبيقي'],
    ['Mon app livreur', 'My courier app', 'تطبيق المندوب'],
    ['Mon espace', 'My workspace', 'مساحتي'], 
    ['Ramassages', 'Pickups', 'عمليات الاستلام'],
    ['Palettes', 'Pallets', 'المنصات'],
    ['Stock & produits', 'Stock & products', 'المخزون والمنتجات'],
    ['Impression', 'Print', 'الطباعة'],
    ['Facturation', 'Billing', 'الفوترة'],
    ['Factures clients et livreurs · PDF, CSV et règlements suivis au même endroit.', 'Client and courier invoices · PDF, CSV, and payments tracked in one place.', 'فواتير العملاء والمندوبين · متابعة ملفات PDF وCSV والمدفوعات في مكان واحد.'],
    ['Vos factures Paid restent disponibles dans Archives Paid.', 'Your paid invoices remain available in the paid-invoices archive.', 'تبقى فواتيرك المدفوعة متاحة في أرشيف الفواتير المدفوعة.', 'Vos factures réglées restent disponibles dans les archives des factures réglées.'],
    ['Confirmer Paid', 'Confirm payment', 'تأكيد الدفع', 'Confirmer le paiement'],
    ['Confirmer Not Paid', 'Confirm unpaid status', 'تأكيد عدم الدفع', 'Confirmer le statut impayé'],
    ['Actualisez la liste Aging.', 'Refresh the overdue-invoices list.', 'حدّث قائمة الفواتير المتأخرة.', 'Actualisez la liste des créances échues.'],
    ['Bon de reception', 'Goods-receipt slip', 'إيصال الاستلام', 'Bon de réception'],
    ['Tracking code (sac / assemblage, facultatif)', 'Tracking code (bag/assembly, optional)', 'رمز التتبع (الحقيبة/التجميع، اختياري)', 'Code de suivi (sac/assemblage, facultatif)'],
    ['Print Sticker', 'Print label', 'طباعة الملصق', 'Imprimer l’étiquette'],
    ['Select a transport', 'Select a transport', 'اختر وسيلة نقل', 'Choisir un transport'],
    ['Select a destination', 'Select a destination', 'اختر وجهة', 'Choisir une destination'],
    ['Tracking Code', 'Tracking Code', 'رمز التتبع', 'Code de suivi'],
    ['Enter number of lots', 'Enter number of lots', 'أدخل عدد الطرود', 'Saisissez le nombre de lots'],
    ['TRACKING ID', 'TRACKING ID', 'رقم التتبع', 'ID DE SUIVI'],
    ['EN ROUTE', 'ON THE WAY', 'في الطريق', 'EN TOURNÉE'],
    ['Tracking', 'Tracking', 'التتبع', 'Suivi'],
    ['Colis / Package', 'Package', 'طرد', 'Colis'],
    ['🔌 Charge', '🔌 Charge', '🔌 الشحن', '🔌 Recharge'],
    ['🚁 drone express', '🚁 Express drone', '🚁 طائرة مسيرة سريعة', '🚁 drone express'],
    ['· charge →', '· load →', '· الحمولة ←', '· charge →'],
    ['Caisse livreurs', 'Courier cash desk', 'صندوق المندوبين'],
    ['Livreurs', 'Couriers', 'المندوبون'],
    ['Clients', 'Clients', 'العملاء'],
    ['Comptes Support', 'Support accounts', 'حسابات الدعم'],
    ['Supports', 'Support agents', 'موظفو الدعم'],
    ['Contact support', 'Contact support', 'الاتصال بالدعم', 'Contacter le support'],
    ['Suivre les commandes', 'Track orders', 'تتبع الطلبات'],
    ['Journal d’audit', 'Audit log', 'سجل التدقيق'],
    ['Demandes', 'Requests', 'الطلبات'],
    ['Réclamations', 'Support requests', 'طلبات الدعم'],
    ['Paramètres', 'Settings', 'الإعدادات'],
    ['Mon profil', 'My profile', 'ملفي الشخصي'],
    ['Tour de contrôle', 'Control tower', 'مركز المراقبة'],
    ['Statistiques', 'Statistics', 'الإحصائيات'],
    ['Statistiques & performance', 'Statistics & performance', 'الإحصائيات والأداء'],
    ['Administrateur', 'Administrator', 'المسؤول'],
    ['administrateur', 'administrator', 'المسؤول'],
    ['Espace client', 'Client area', 'مساحة العميل'],
    ['Espace livreur', 'Courier area', 'مساحة المندوب'],
    ['Espace', 'Workspace', 'المساحة'],
    ['Rechercher un colis…', 'Search parcels…', 'ابحث عن طرد…'],
    ['Rechercher un colis (raccourci ⌘/Ctrl K)', 'Search parcels (shortcut ⌘/Ctrl K)', 'ابحث عن طرد (اختصار ⌘/Ctrl K)'],
    ['Langue : français', 'Language: English', 'اللغة: العربية'],
    ['Interface en français', 'Interface language: English', 'لغة الواجهة: العربية'],
    ['Langue', 'Language', 'اللغة'],
    ['Choisir la langue', 'Select language', 'اختر اللغة'],
    ['Aide et horaires du service client', 'Customer service help and hours', 'المساعدة وساعات خدمة العملاء'],
    ['Besoin d’un coup de main ?', 'Need help?', 'هل تحتاج إلى مساعدة؟'],
    ['Notre équipe vous accompagne.', 'Our team is here to help.', 'فريقنا هنا لمساعدتك.'],
    ['Ouvrir les réclamations →', 'Open support requests →', 'فتح طلبات الدعم ←'],
    ['Aide & réclamations', 'Help & support', 'المساعدة والدعم'],
    ['Service clients', 'Customer service', 'خدمة العملاء'],
    ['Horaires de disponibilité', 'Opening hours', 'ساعات العمل'],
    ['Du lundi au vendredi', 'Monday to Friday', 'من الاثنين إلى الجمعة'],
    ['Samedi', 'Saturday', 'السبت'],
    ['Bonjour,', 'Hello,', 'مرحباً،'],
    ['Voici ce qui se passe chez ORIENTAL24 aujourd’hui.', 'Here is what is happening at ORIENTAL24 today.', 'إليك ما يحدث في ORIENTAL24 اليوم.'],
    ['Votre tournée, vos colis et vos encaissements en un coup d’œil.', 'Your route, parcels and collections at a glance.', 'جولتك وطرودك ومتحصلاتك في لمحة.'],
    ['Votre partenaire de proximité', 'Your local delivery partner', 'شريكك القريب'],
    ['L’Oriental, plus proche à chaque livraison.', 'The Oriental region, closer with every delivery.', 'الشرق أقرب مع كل عملية توصيل.'],
    ['Suivez vos expéditions et accompagnez votre activité, au même endroit.', 'Track your shipments and manage your business, all in one place.', 'تتبّع شحناتك وأدر نشاطك من مكان واحد.'],
    ['Total des colis', 'Total parcels', 'إجمالي الطرود'],
    ['Colis en cours', 'Active parcels', 'الطرود الجارية'],
    ['Colis livrés', 'Delivered parcels', 'الطرود المسلّمة'],
    ['Montant collecté', 'Amount collected', 'المبلغ المحصّل'],
    ['COD livré déclaré', 'Delivered COD reported', 'المبالغ المستحقة المصرّح بتسليمها'],
    ['Votre activité enregistrée, toutes périodes confondues.', 'Your recorded activity across all periods.', 'نشاطك المسجل عبر جميع الفترات.'],
    ['PASSER À L’ACTION', 'TAKE ACTION', 'اتخذ إجراءً'],
    ['Les files à consulter', 'Queues to review', 'قوائم المتابعة'],
    ['Votre tournée, par priorité de consultation', 'Your route, by review priority', 'جولتك حسب أولوية المتابعة'],
    ['Dernière actualisation · Toutes périodes', 'Last refresh · All periods', 'آخر تحديث · كل الفترات'],
    ['À affecter', 'To assign', 'بانتظار الإسناد'],
    ['Colis ouverts sans livreur', 'Open parcels without a courier', 'طرود مفتوحة دون مندوب'],
    ['Programmés', 'Scheduled', 'مجدولة'],
    ['À consulter avant la prochaine action', 'Review before the next action', 'راجعها قبل الإجراء التالي'],
    ['Retours & refus', 'Returns & refusals', 'المرتجعات والرفض'],
    ['Statuts à examiner, sans présumer un incident', 'Statuses to review; no incident is assumed', 'حالات للمراجعة دون افتراض وجود مشكلة'],
    ['À facturer', 'To invoice', 'بانتظار الفوترة'],
    ['Clôturés sans relevé client', 'Closed without a client statement', 'مغلقة دون كشف حساب للعميل'],
    ['À rapprocher', 'To reconcile', 'بانتظار المطابقة'],
    ['Clôturés sans relevé livreur', 'Closed without a courier statement', 'مغلقة دون كشف حساب للمندوب'],
    ['Sans relevé livreur', 'No courier statement', 'دون كشف حساب للمندوب'],
    ['Avec relevé livreur', 'With courier statement', 'مع كشف حساب للمندوب'],
    ['Non facturés au client', 'Not invoiced to client', 'غير مفوترة للعميل'],
    ['Facturés au client', 'Invoiced to client', 'مفوترة للعميل'],
    ['Voir les colis', 'View parcels', 'عرض الطرود'],
    ['Ces compteurs décrivent les statuts enregistrés : ils ne mesurent ni un retard contractuel, ni un paiement bancaire.', 'These counts reflect recorded statuses; they do not measure contractual lateness or bank payments.', 'تعكس هذه المؤشرات الحالات المسجلة؛ ولا تقيس التأخير التعاقدي أو المدفوعات البنكية.'],
    ['Classement des livreurs', 'Courier leaderboard', 'ترتيب المندوبين'],
    ['Livrés 7 j', 'Delivered · 7 days', 'تم التسليم · 7 أيام'],
    ['Taux 7 j', 'Rate · 7 days', 'المعدل · 7 أيام'],
    ['COD 7 j', 'COD · 7 days', 'المبالغ المستحقة · 7 أيام'],
    ['avec retards', 'overdue', 'متأخرة'],
    ['Le classement suit la date de mise à jour : un colis livré il y a plus de 7 jours ne compte plus. Les livreurs sans colis apparaissent en queue avec « — ».', 'The ranking uses the update date: parcels delivered more than 7 days ago no longer count. Couriers with no parcels appear at the bottom with “—”.', 'يعتمد الترتيب على تاريخ التحديث؛ الطرود المسلّمة منذ أكثر من 7 أيام لا تُحتسب. ويظهر المندوبون دون طرود في آخر القائمة بعلامة «—».'],
    ['Numéros à risque', 'At-risk phone numbers', 'أرقام هاتف عالية المخاطر'],
    ['Destinataires récurrents à échecs · « Livré » fait réduire le score', 'Repeat recipients with failed deliveries · “Delivered” lowers the score', 'مستلمون تتكرر معهم الإخفاقات · «تم التسليم» يخفض التقييم'],
    ['Colis vus', 'Parcels seen', 'الطرود المسجلة'],
    ['Échecs', 'Failures', 'الإخفاقات'],
    ['Score', 'Score', 'التقييم'],
    ['Risque élevé', 'High risk', 'مخاطر مرتفعة'],
    ['À surveiller', 'Monitor', 'تستدعي المتابعة'],
    ['Score = refus/retours ×2 · annulations/reports/non-réponses ×1 · moins les livraisons réussies. Affiché dès 2 points, « Risque élevé » dès 4 — calcul 100 % local, sur les colis visibles de votre espace.', 'Score = refusals/returns ×2 · cancellations/postponements/no answers ×1 · minus successful deliveries. Shown from 2 points; “High risk” from 4. Calculated locally from parcels visible in your workspace.', 'التقييم = الرفض/المرتجعات ×2 · الإلغاء/التأجيل/عدم الرد ×1 · ناقص عمليات التسليم الناجحة. يظهر ابتداءً من نقطتين، و«مخاطر مرتفعة» من 4. يُحسب محلياً من الطرود الظاهرة في مساحتك.'],

    ['Dans votre périmètre', 'In your workspace', 'ضمن نطاقك'],
    ['Colis non clôturés', 'Open parcels', 'الطرود غير المغلقة'],
    ['du total des colis', 'of all parcels', 'من إجمالي الطرود'],
    ['COD des colis livrés', 'COD from delivered parcels', 'المبالغ المستحقة للطرود المسلّمة'],
    ['Taux de livraison', 'Delivery rate', 'معدل التسليم'],
    ['Sur les colis au résultat définitif', 'For parcels with a final outcome', 'للطرود ذات النتيجة النهائية'],
    ['Délai moyen de livraison', 'Average delivery time', 'متوسط وقت التسليم'],
    ['De la création au « Livré »', 'From creation to “Delivered”', 'من الإنشاء إلى «تم التسليم»'],
    ['COD encaissé', 'COD collected', 'المبالغ المستحقة المحصّلة'],
    ['Somme des montants livrés', 'Total value delivered', 'إجمالي قيمة الطرود المسلّمة'],
    ['COD en attente', 'COD pending', 'المبالغ المستحقة قيد الانتظار'],
    ['Sur les colis encore ouverts', 'For parcels still open', 'للطرود التي ما زالت مفتوحة'],
    ['Activité des expéditions', 'Shipment activity', 'نشاط الشحنات'],
    ['Par date de création · 7 derniers jours', 'By creation date · last 7 days', 'حسب تاريخ الإنشاء · آخر 7 أيام'],
    ['Créés', 'Created', 'تم إنشاؤها'],
    ['Livrés', 'Delivered', 'تم التسليم'],
    ['Vos principales destinations', 'Your main destinations', 'أهم الوجهات'],
    ['Répartition des colis par ville', 'Parcel distribution by city', 'توزيع الطرود حسب المدينة'],
    ['Pas encore de destination', 'No destinations yet', 'لا توجد وجهات بعد'],
    ['Ajoutez votre premier colis.', 'Add your first parcel.', 'أضف طردك الأول.'],
    ['Mes derniers colis', 'My latest parcels', 'أحدث طرودي'],
    ['Derniers colis', 'Latest parcels', 'أحدث الطرود'],
    ['Les dernières expéditions de votre activité', 'Your latest shipments', 'أحدث شحنات نشاطك'],
    ['Mise à jour à l’ouverture de la page', 'Updated when the page opens', 'يتم التحديث عند فتح الصفحة'],
    ['Tous droits réservés.', 'All rights reserved.', 'جميع الحقوق محفوظة.'],
    ['programmé(s) aujourd’hui', 'scheduled today', 'مجدولة اليوم'],
    ['colis en retard (+48 h)', 'overdue parcels (+48 h)', 'طرود متأخرة (+48 ساعة)'],
    ['Voir tous les colis', 'View all parcels', 'عرض جميع الطرود'],
    ['Nouveau colis', 'New parcel', 'طرد جديد'],
    ['Ma tournée', 'My route', 'جولتي'],
    ['Chaque colis a son histoire. Retrouvez-la ici.', 'Every parcel has a story. Find it here.', 'لكل طرد سجلّ خاص. ستجده هنا.'],
    ['Exporter CSV', 'Export CSV', 'تصدير CSV'],
    ['Exporter cette vue', 'Export this view', 'تصدير هذا العرض'],
    ['Importer', 'Import', 'استيراد'],
    ['Actualiser les données', 'Refresh data', 'تحديث البيانات'],
    ['Réinitialiser les filtres', 'Reset filters', 'إعادة ضبط عوامل التصفية'],
    ['Aucun filtre · Tous les colis de votre périmètre', 'No filters · All parcels in your workspace', 'لا توجد عوامل تصفية · جميع الطرود ضمن نطاقك'],
    ['Retirer ce filtre', 'Remove this filter', 'إزالة عامل التصفية'],
    ['Recherche :', 'Search:', 'بحث:'],
    ['résultat', 'result', 'نتيجة'],
    ['résultats', 'results', 'نتائج'],
    ['Les dates filtrent la date de création enregistrée, pas la date de livraison. L’export reprend tous les résultats filtrés, même sur plusieurs pages. Les cases de sélection concernent la page affichée.', 'Dates filter by recorded creation date, not delivery date. The export includes all filtered results across pages. Selection boxes apply to the displayed page.', 'تصفّي التواريخ حسب تاريخ الإنشاء المسجل لا تاريخ التسليم. يشمل التصدير جميع النتائج المصفاة عبر الصفحات. وتخص خانات الاختيار الصفحة المعروضة فقط.'],
    ['Tous les colis', 'All parcels', 'جميع الطرود'],
    ['Mes colis assignés', 'Parcels assigned to me', 'الطرود المسندة إليّ'],
    ['En livraison', 'Out for delivery', 'قيد التوصيل'],
    ['Référence, nom, téléphone…', 'Reference, name, phone…', 'رقم التتبع، الاسم، الهاتف…'],
    ['Tous les statuts', 'All statuses', 'جميع الحالات'],
    ['Toutes les villes', 'All cities', 'جميع المدن'],
    ['Tous les motifs', 'All reasons', 'جميع الأسباب'],
    ['Sans motif', 'No reason', 'دون سبب'],
    ['Référence, nom, téléphone, boutique…', 'Reference, name, phone, store…', 'رقم التتبع، الاسم، الهاتف، المتجر…'],
    ['Filtrer par statut', 'Filter by status', 'تصفية حسب الحالة'],
    ['Filtrer par ville', 'Filter by city', 'تصفية حسب المدينة'],
    ['Filtrer par motif', 'Filter by reason', 'تصفية حسب السبب'],
    ['Créés du', 'Created from', 'تاريخ الإنشاء من'],
    ['Créés au (inclus)', 'Created through (inclusive)', 'تاريخ الإنشاء إلى (شامل)'],
    ['Livreur actuel', 'Current courier', 'المندوب الحالي'],
    ['Tous les livreurs', 'All couriers', 'جميع المندوبين'],
    ['Tous les clients', 'All clients', 'جميع العملاء'],
    ['Rapprochement livreur', 'Courier reconciliation', 'مطابقة حساب المندوب'],
    ['Facturation / rapprochement', 'Billing / reconciliation', 'الفوترة / المطابقة'],
    ['Tous les colis de votre périmètre', 'All parcels in your workspace', 'جميع الطرود ضمن نطاقك'],
    ['Statut de traitement', 'Processing status', 'حالة المعالجة'],

    ['Traité', 'Processed', 'تمت معالجته'],
    ['Non traité', 'Not processed', 'لم تتم معالجته'],
    ['Non Traité', 'Not processed', 'لم تتم معالجته'],
    ['Scanner', 'Scan', 'مسح'],
    ['Scanner un colis', 'Scan a parcel', 'امسح طرداً'],
    ['Étiquettes', 'Labels', 'الملصقات'],
    ['Affecter', 'Assign', 'إسناد'],
    ['Référence', 'Reference', 'رقم التتبع'],
    ['Destinataire', 'Recipient', 'المستلم'],
    ['Destination', 'Destination', 'الوجهة'],
    ['Montant COD', 'COD amount', 'المبلغ المستحق'],
    ['Statut', 'Status', 'الحالة'],
    ['Client / Boutique', 'Client / Store', 'العميل / المتجر'],
    ['Livreur / Agence', 'Courier / Agency', 'المندوب / الوكالة'],
    ['Livreur', 'Courier', 'المندوب'],
    ['Client', 'Client', 'العميل'],
    ['Aucun colis trouvé', 'No parcels found', 'لم يتم العثور على طرود'],
    ['Essayez d’autres filtres ou ajoutez un nouveau colis.', 'Try other filters or add a new parcel.', 'جرّب عوامل تصفية أخرى أو أضف طرداً جديداً.'],
    ['Retourné au hub', 'Returned to hub', 'أُعيد إلى المركز'],
    ['À l’agence', 'At the agency', 'في الوكالة'],
    ['Non affecté', 'Unassigned', 'غير مسند'],
    ['À collecter', 'To collect', 'الواجب تحصيله'],
    ['Frais de livraison', 'Delivery fee', 'رسوم التوصيل'],
    ['Produit', 'Product', 'المنتج'],
    ['Support responsable', 'Assigned support agent', 'موظف الدعم المسؤول'],
    ['Total colis', 'Total parcels', 'إجمالي الطرود'],
    ['Ouverts', 'Open', 'مفتوحة'],
    ['COD à collecter', 'COD to collect', 'المبلغ الواجب تحصيله'],
    ['Taux de réussite', 'Success rate', 'معدل النجاح'],
    ['Tous', 'All', 'الكل'],
    ['Aujourd’hui', 'Today', 'اليوم'],
    ['En tournée', 'On route', 'في الجولة'],
    ['Retards', 'Overdue', 'متأخرة'],
    ['Recherche par numéro de téléphone…', 'Search by phone number…', 'ابحث برقم الهاتف…'],
    ['Plage et dates', 'Date range', 'النطاق والتواريخ'],
    ['Effacer', 'Clear', 'مسح'],
    ['Effacer les filtres', 'Clear filters', 'مسح عوامل التصفية'],
    ['Aucun colis sur cette période.', 'No parcels in this period.', 'لا توجد طرود في هذه الفترة.'],
    ['Changez la plage de dates, le statut ou le filtre rapide pour voir plus.', 'Change the date range, status or quick filter to see more.', 'غيّر نطاق التاريخ أو الحالة أو عامل التصفية السريع لعرض المزيد.'],
    ['Mon équipe', 'My team', 'فريقي'],
    ['Fin de journée', 'End of day', 'نهاية اليوم'],
    ['Caisse & commissions', 'Cash desk & commissions', 'الصندوق والعمولات'],
    ['Mon véhicule connecté', 'My connected vehicle', 'مركبتي المتصلة'],
    ['Impression d’étiquettes', 'Print labels', 'طباعة الملصقات'],
    ['Manifest du jour (PDF)', 'Daily manifest (PDF)', 'بيان اليوم (PDF)'],
    ['Vue classique (ordinateur)', 'Classic desktop view', 'العرض التقليدي (الكمبيوتر)'],
    ['Se déconnecter', 'Sign out', 'تسجيل الخروج'],
    ['Voir le profil', 'View profile', 'عرض الملف الشخصي'],
    ['Actualiser', 'Refresh', 'تحديث'],
    ['Actualiser toutes les données', 'Refresh all data', 'تحديث جميع البيانات'],
    ['Une nouvelle version est prête — touchez pour mettre à jour', 'A new version is ready — tap to update', 'يتوفر إصدار جديد — اضغط للتحديث'],
    ['Transmettre ma position', 'Share my location', 'إرسال موقعي'],
    ['Toutes les dates', 'All dates', 'كل التواريخ'],
    ['Aucun colis à tracer pour ces filtres.', 'No parcels to route with these filters.', 'لا توجد طرود لرسم مسارها بهذه المرشحات.'],
    ['Aucun colis à rover pour ces filtres.', 'No parcels to manifest with these filters.', 'لا توجد طرود لإدراجها في البيان بهذه المرشحات.'],
    ['Itinéraire', 'Route', 'المسار'],
    ['Menu', 'Menu', 'القائمة'],
    ['Plage de dates', 'Date range', 'النطاق الزمني'],
    ['Du', 'From', 'من'],
    ['Au', 'To', 'إلى'],
    ['Tout voir', 'Show all', 'عرض الكل'],
    ['Appliquer', 'Apply', 'تطبيق'],
    ['Changer le statut', 'Change status', 'تغيير الحالة'],
    ['État actuel', 'Current status', 'الحالة الحالية'],
    ['Motif requis', 'Reason required', 'السبب مطلوب'],
    ['Preuve de livraison', 'Proof of delivery', 'إثبات التسليم'],
    ['Ajouter une photo', 'Add a photo', 'إضافة صورة'],
    ['Signature', 'Signature', 'التوقيع'],
    ['Fermer', 'Close', 'إغلاق'],
    ['Annuler', 'Cancel', 'إلغاء'],
    ['Confirmer', 'Confirm', 'تأكيد'],
    ['Enregistrer', 'Save', 'حفظ'],
    ['Imprimer', 'Print', 'طباعة'],
    ['Aucun résultat', 'No results', 'لا توجد نتائج'],
    ['Créé', 'Created', 'تم الإنشاء'],
    ['Transit', 'In transit', 'قيد النقل'],
    ['Reporté', 'Postponed', 'مؤجل'],
    ['Programmé', 'Scheduled', 'مجدول'],
    ['Réceptionné', 'Received at agency', 'تم الاستلام في الوكالة'],
    ['Reçu par le livreur', 'Received by courier', 'استلمه المندوب'],
    ['Refusé', 'Refused', 'مرفوض'],
    ['Refusée', 'Refused', 'مرفوضة'],
    ['Intéressé', 'Interested', 'مهتم'],
    ['Ramassé', 'Picked up', 'تم جمعه'],
    ['Au hub', 'At the hub', 'في المركز'],
    ['Retourné', 'Returned', 'مُعاد'],
    ['Annulé', 'Cancelled', 'ملغى'],
    ['Appel client', 'Customer call', 'اتصال بالعميل'],
    ['WhatsApp client', 'Customer WhatsApp', 'واتساب العميل'],
    ['Facturé', 'Invoiced', 'تمت فوترته'],
    ['Réglée', 'Paid', 'مدفوعة'],
    ['En attente', 'Pending', 'قيد الانتظار'],
    ['Demandé', 'Requested', 'مطلوب'],
    ['Reporté au', 'Postponed to', 'مؤجل إلى'],
    ['Traité aujourd’hui', 'Processed today', 'تمت معالجته اليوم'],
    ['Non traité aujourd’hui', 'Not processed today', 'لم تتم معالجته اليوم'],
    ['©', '©', '©'],
  ];

  // Load the wider screen catalog first; hand-reviewed common labels below override it.
  const translations = new Map();
  for (const row of (Array.isArray(window.O24_AUTO_TRANSLATIONS) ? window.O24_AUTO_TRANSLATIONS : [])) {
    if (!Array.isArray(row) || row.length < 3 || typeof row[0] !== 'string') continue;
    translations.set(row[0], {
      en: String(row[1] ?? row[0]),
      ar: String(row[2] ?? row[0]),
      fr: String(row[3] ?? row[0]),
    });
  }
  for (const row of ENTRIES) {
    const [source, en, ar, fr] = row;
    translations.set(source, { en, ar, fr: fr ?? source });
  }
  const ordered = [...translations.entries()]
    .map(([source, value]) => [source, value.en, value.ar, value.fr])
    .filter(([source]) => source.includes(' ') || /[…,:→·]/.test(source))
    .sort((a, b) => b[0].length - a[0].length);

  function localize(value, lang) {
    if (typeof value !== 'string' || !value || !value.trim()) return value;
    const lead = value.match(/^\s*/)?.[0] || '';
    const trail = value.match(/\s*$/)?.[0] || '';
    const source = value.slice(lead.length, value.length - trail.length);
    const exact = translations.get(source);
    const exactTranslation = exact && (lang === 'fr' ? exact.fr : exact[lang]);
    if (exactTranslation) return lead + exactTranslation + trail;

    // French is the source language for most screens, but a few legacy controls were authored in English.
    // Avoid phrase-substitution inside free-form notes or names; only mix translations around obvious live values.
    const hasLiveValue = /\d|\b(?:O24-|COD|MAD|ETA|OTP)\b/i.test(source);
    if (lang === 'fr') {
      if (!hasLiveValue) return value;
      let out = source;
      for (const [key, , , french] of ordered) {
        if (!key || !french || key === french) continue;
        if ((key.includes(' ') || /[…,:→·]/.test(key)) && out.includes(key)) out = out.split(key).join(french);
      }
      return lead + out + trail;
    }

    // Dynamic welcome line; the user's name is deliberately left unchanged.
    if (lang === 'en' && /^Bonjour,/.test(source)) return lead + source.replace(/^Bonjour,/, 'Hello,') + trail;
    if (lang === 'ar' && /^Bonjour,/.test(source)) return lead + source.replace(/^Bonjour,/, 'مرحباً،') + trail;
    const rangeCount = source.match(/^(\d+(?:[–-]\d+)?) sur (\d+) colis$/);
    const dashboardCount = source.match(/^(\d+) colis sur (\d+)$/);
    const count = rangeCount || dashboardCount;
    if (count) return lead + (lang === 'en' ? `${count[1]} of ${count[2]} parcels` : `${count[1]} من أصل ${count[2]} طرداً`) + trail;
    if (!hasLiveValue) return value;
    // Translate known UI phrases embedded alongside a count or live value, without touching user data.
    let out = source;
    for (const [key, en, ar] of ordered) {
      const replacement = lang === 'en' ? en : ar;
      if (!key || !replacement || key === replacement) continue;
      // For mixed text, only substitute full phrases (multiword labels) or explicit punctuation phrases.
      if ((key.includes(' ') || /[…,:→·]/.test(key)) && out.includes(key)) out = out.split(key).join(replacement);
    }
    return lead + out + trail;
  }

  function readLanguage() {
    try {
      const saved = localStorage.getItem(LANGUAGE_KEY);
      return LANGUAGES[saved] ? saved : 'fr';
    } catch (_) { return 'fr'; }
  }
  let currentLanguage = readLanguage();
  const root = document.documentElement;
  root.lang = LANGUAGES[currentLanguage].tag;
  root.dir = LANGUAGES[currentLanguage].dir;

  const sourceText = new WeakMap();
  const appliedText = new WeakMap();
  const sourceAttributes = new WeakMap();
  const appliedAttributes = new WeakMap();

  function translateAttributes(node) {
    if (!node || node.nodeType !== 1 || !node.attributes) return;
    let originals = sourceAttributes.get(node);
    let applied = appliedAttributes.get(node);
    if (!originals) { originals = new Map(); sourceAttributes.set(node, originals); }
    if (!applied) { applied = new Map(); appliedAttributes.set(node, applied); }
    for (const name of ['placeholder', 'title', 'aria-label', 'aria-description']) {
      if (!node.hasAttribute(name)) continue;
      const value = node.getAttribute(name);
      if (!originals.has(name) || (applied.has(name) && value !== applied.get(name))) originals.set(name, value);
      const next = localize(originals.get(name), currentLanguage);
      applied.set(name, next);
      if (next !== value) node.setAttribute(name, next);
    }
  }

  function translateTextNode(node) {
    if (!node || node.nodeType !== 3 || !node.parentElement) return;
    const parent = node.parentElement;
    if (parent.closest('script,style,textarea,[contenteditable="true"],[data-no-translate],[dir="auto"],.tracking,.mono,.recipient,.parcel-copy-recipient,.delivery-card h3,.da-card-main b,.parcel-event-actor,.message p,.timeline-item p,.finance-tx-note,.label-note,.notice-admin-body')) return;
    const value = node.nodeValue;
    if (!sourceText.has(node) || (appliedText.has(node) && value !== appliedText.get(node))) sourceText.set(node, value);
    const next = localize(sourceText.get(node), currentLanguage);
    appliedText.set(node, next);
    if (next !== value) node.nodeValue = next;
  }

  function translateTree(rootNode) {
    if (!rootNode) return;
    if (rootNode.nodeType === 1) translateAttributes(rootNode);
    if (rootNode.nodeType === 3) { translateTextNode(rootNode); return; }
    if (rootNode.nodeType !== 1 && rootNode.nodeType !== 9 && rootNode.nodeType !== 11) return;
    const walker = document.createTreeWalker(rootNode, NodeFilter.SHOW_TEXT);
    let textNode;
    while ((textNode = walker.nextNode())) translateTextNode(textNode);
    if (rootNode.querySelectorAll) rootNode.querySelectorAll('[placeholder],[title],[aria-label],[aria-description]').forEach(translateAttributes);
  }

  function updateLanguageButtons() {
    document.querySelectorAll('[data-o24-lang-code]').forEach((node) => {
      node.textContent = LANGUAGES[currentLanguage].short;
    });
  }

  function setLanguage(lang) {
    if (!LANGUAGES[lang]) return;
    currentLanguage = lang;
    root.lang = LANGUAGES[lang].tag;
    root.dir = LANGUAGES[lang].dir;
    try { localStorage.setItem(LANGUAGE_KEY, lang); } catch (_) { /* browser storage may be disabled */ }
    closeO24Popovers();
    translateTree(document.documentElement || document.body);
    updateLanguageButtons();
    window.dispatchEvent(new CustomEvent('o24:languagechange', { detail: { language: lang } }));
  }

  function iconMarkup(name) {
    if (typeof window.icon === 'function') return window.icon(name);
    const d = name === 'globe'
      ? 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M2 12h20 M12 2c6 6 6 14 0 20-6-6-6-14 0-20'
      : 'M6 9l6 6 6-6';
    return `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;
  }

  function languageButton(extraClass) {
    const extra = extraClass ? ` ${extraClass}` : '';
    return `<button type="button" class="o24-language-trigger${extra}" aria-label="Langue : français" title="Interface en français" aria-haspopup="menu" aria-expanded="false" onclick="toggleO24LanguageMenu(event,this)">${iconMarkup('globe')}<span data-o24-lang-code>${LANGUAGES[currentLanguage].short}</span>${iconMarkup('down')}</button>`;
  }

  function helpButton(extraClass) {
    const extra = extraClass ? ` ${extraClass}` : '';
    return `<button type="button" class="o24-help-trigger${extra}" aria-label="Aide et horaires du service client" title="Service clients" aria-haspopup="dialog" aria-expanded="false" onclick="toggleO24Help(event,this)">${iconMarkup('help')}</button>`;
  }

  function positionPopover(popover, anchor, width) {
    const rect = anchor.getBoundingClientRect();
    const x = Math.max(10, Math.min(window.innerWidth - width - 10, rect.right - width));
    const estimatedHeight = popover.classList.contains('o24-language-menu') ? 184 : 164;
    let y = rect.bottom + 8;
    if (y + estimatedHeight > window.innerHeight - 10) y = Math.max(10, rect.top - estimatedHeight - 8);
    popover.style.left = `${x}px`;
    popover.style.top = `${y}px`;
  }

  let activeAnchor = null;
  function closeO24Popovers() {
    document.querySelectorAll('.o24-language-menu,.o24-help-popover').forEach((node) => node.remove());
    document.querySelectorAll('.o24-language-trigger,.o24-help-trigger').forEach((node) => node.setAttribute('aria-expanded', 'false'));
    activeAnchor = null;
  }

  function toggleLanguageMenu(event, anchor) {
    if (event) event.stopPropagation();
    const existing = document.querySelector('.o24-language-menu');
    if (existing && activeAnchor === anchor) { closeO24Popovers(); return; }
    closeO24Popovers();
    activeAnchor = anchor;
    anchor.setAttribute('aria-expanded', 'true');
    const menu = document.createElement('div');
    menu.className = 'o24-language-menu';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', 'Choisir la langue');
    menu.dir = 'ltr';
    menu.innerHTML = Object.entries(LANGUAGES).map(([code, item]) =>
      `<button type="button" class="o24-language-option${code === currentLanguage ? ' is-selected' : ''}" role="menuitemradio" aria-checked="${code === currentLanguage}" data-lang="${code}"><span class="o24-language-flag" aria-hidden="true">${item.flag}</span><span>${item.native}</span>${code === currentLanguage ? '<span class="o24-language-check" aria-hidden="true">✓</span>' : ''}</button>`
    ).join('');
    menu.addEventListener('click', (e) => {
      e.stopPropagation();
      const choice = e.target.closest('[data-lang]');
      if (choice) setLanguage(choice.dataset.lang);
    });
    document.body.appendChild(menu);
    positionPopover(menu, anchor, 224);
  }

  function toggleHelp(event, anchor) {
    if (event) event.stopPropagation();
    const existing = document.querySelector('.o24-help-popover');
    if (existing && activeAnchor === anchor) { closeO24Popovers(); return; }
    closeO24Popovers();
    activeAnchor = anchor;
    anchor.setAttribute('aria-expanded', 'true');
    const popover = document.createElement('section');
    popover.className = 'o24-help-popover';
    popover.setAttribute('role', 'dialog');
    popover.setAttribute('aria-label', 'Service clients');
    popover.innerHTML = '<div class="o24-help-heading"><span class="o24-help-symbol">?</span><div><h3>Service clients</h3><p>Horaires de disponibilité</p></div></div><div class="o24-help-hours"><div><span>Du lundi au vendredi</span><b dir="ltr">9:00–18:00</b></div><div><span>Samedi</span><b dir="ltr">9:00–14:00</b></div></div>';
    document.body.appendChild(popover);
    translateTree(popover);
    positionPopover(popover, anchor, 270);
  }

  document.addEventListener('click', (event) => {
    if (!event.target.closest('.o24-language-menu,.o24-help-popover,.o24-language-trigger,.o24-help-trigger')) closeO24Popovers();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeO24Popovers();
  });
  window.addEventListener('resize', closeO24Popovers, { passive: true });
  window.addEventListener('scroll', () => {
    const menu = document.querySelector('.o24-language-menu,.o24-help-popover');
    if (menu) closeO24Popovers();
  }, { passive: true });

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === 'characterData') translateTextNode(mutation.target);
      else if (mutation.type === 'attributes') translateAttributes(mutation.target);
      else mutation.addedNodes.forEach((node) => translateTree(node));
    }
  });
  if (document.body) observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'title', 'aria-label', 'aria-description'] });

  window.o24LanguageButton = languageButton;
  window.o24HelpButton = helpButton;
  window.toggleO24LanguageMenu = toggleLanguageMenu;
  window.toggleO24Help = toggleHelp;
  window.setO24Language = setLanguage;
  window.o24CurrentLanguage = () => currentLanguage;
  window.o24Translate = (text) => localize(String(text ?? ''), currentLanguage);

  if (document.documentElement || document.body) translateTree(document.documentElement || document.body);
})();
