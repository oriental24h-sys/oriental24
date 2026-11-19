/* Remise à zéro : l'écran admin doit être présent, verrouillé et branché.
   Vérifie le fichier statique réel (pas une copie) + la route serveur. */
const fs = require('node:fs');
const assert = require('node:assert/strict');

const app = fs.readFileSync('static/app.js', 'utf8');
const reset = fs.readFileSync('static/data-reset.js', 'utf8');
const index = fs.readFileSync('templates/index.html', 'utf8');
const routes = fs.readFileSync('data_reset_routes.py', 'utf8');
const module_ = fs.readFileSync('data_reset.py', 'utf8');
const manage = fs.readFileSync('manage.py', 'utf8');

// 1) entrée de menu réservée à l'administrateur
assert(/\["data-reset", "trash", "Remise à zéro", \["admin"\]\]/.test(app), 'entrée de menu admin absente');
assert(app.includes('case "data-reset":'), 'la vue n’est pas rendue');
assert(app.includes('trash: "M4 7h16'), 'icône « trash » absente');
assert(index.includes('/static/data-reset.js?v=remise-a-zero-bouton-2026-11-19'), 'script non inclus dans la page');

// 2) trois verrous côté interface
assert(reset.includes('REMETTRE A ZERO'), 'la phrase de confirmation est absente');
assert(/id="f-password" name="password" type="password"/.test(reset),
  'le mot de passe administrateur est demandé');
// Correctif capture : le remplissage automatique ne doit plus pouvoir toucher la phrase.
assert(reset.includes('contenteditable="true"'), 'la zone de confirmation reste un <input> remplissable');
assert(!/<input[^>]*name="phrase"/.test(reset), 'un input nommé phrase subsiste (autofill possible)');
assert(reset.includes('data-lpignore') && reset.includes('data-1p-ignore'), 'les gestionnaires de mots de passe ne sont pas bloqués');
assert(reset.includes("includes('@')"), 'aucun garde-fou contre l’e-mail injecté');
assert(/\^\[\+\\d\]/.test(reset) || reset.includes('numéro de téléphone'), 'aucun garde-fou contre le téléphone injecté');
assert(reset.includes('drPhraseKey'), 'aucune normalisation casse/accents/espaces');
assert(reset.includes("textContent"), 'la phrase n’est pas lue depuis la zone éditable');
assert(reset.includes("api('/admin/data-reset', 'POST'"), 'l’écran n’appelle pas la route');
assert(reset.includes('keep_accounts'), 'l’option comptes n’est pas transmise');
assert(reset.includes('Aucune sauvegarde') || reset.includes('sans sauvegarde'), 'l’absence de sauvegarde n’est pas annoncée');

// 3) la route est verrouillée côté serveur aussi
assert(routes.includes("@auth('admin')"), 'la route n’exige pas le rôle admin');
assert(routes.includes('check_password_hash'), 'le mot de passe n’est pas revérifié côté serveur');
assert(routes.includes('ORIENTAL24_ALLOW_DATA_RESET'), 'la double sécurité production est absente');
assert(routes.includes('verify_empty'), 'aucun recomptage final');

// 4) le module conserve la structure et purge le métier
assert(module_.includes('KEEP_TABLES'), 'aucune liste de conservation');
['users', 'ops_hubs', 'cities', 'settings', 'ops_reasons'].forEach((table) => {
  assert(module_.includes("'" + table + "'"), table + ' n’est pas conservée');
});
['parcels', 'invoices', 'ops_documents', 'ops_document_lines', 'driver_statements', 'events'].forEach((table) => {
  assert(module_.includes("('" + table + "'"), table + ' n’est pas comptée avant/après');
});
assert(module_.includes('BEGIN IMMEDIATE'), 'la purge n’est pas transactionnelle');
assert(module_.includes('fingerprint'), 'aucune empreinte SHA-256');
assert(module_.includes('verify_empty'), 'aucun contrôle final');
assert(!/DROP TABLE/i.test(module_), 'le module ne doit jamais détruire une table');

// 5) script terminal équivalent
assert(manage.includes("'reset-data'"), 'la commande reset-data manque');
assert(manage.includes('--dry-run'), 'le mode vérification manque');
assert(manage.includes('ORIENTAL24_RESET_PASSWORD'), 'le mode --yes n’est pas protégé');

console.log('Remise à zéro (écran admin + route + script) PASS');
