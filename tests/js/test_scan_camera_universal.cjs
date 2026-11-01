/* Le scan caméra du téléphone doit être LE MÊME partout, et marcher sur iPhone.
   Demandé : « Réceptionner la sélection » doit utiliser le même scan avec téléphone
   que l'écran « Réception au scan · collecte » (image fournie).

   1. l'écran de réception groupée a la même barre de scan : caméra, son, vider, guide ;
   2. la caméra n'est plus limitée à BarcodeDetector (absent sur Safari/iOS) :
      le décodeur ZXing livré avec l'application prend le relais ;
   3. le fichier livré /static/vendor/zxing.min.js décode VRAIMENT un code-barres
      (test de décodage réel sur une image Code 128, sans navigateur). */
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');

const reception = fs.readFileSync('static/reception-collection.js', 'utf8');
const palette = fs.readFileSync('static/palette-scan.js', 'utf8');

// ---------- 1) l'écran « Réceptionner la sélection » a la même barre de scan ----------
const from = reception.indexOf('async function openBulkReceptionScan(');
const to = reception.indexOf('\n}', reception.indexOf('const camSlot='));
const bulk = reception.slice(from, to > from ? to : reception.length);
assert(from > 0, 'openBulkReceptionScan introuvable');
['pp-rx-cam-slot', 'bulk-rx-camera', 'bulk-rx-cam-state', 'bulk-rx-reset', 'data-o24-snd'].forEach((mark) => {
  assert(bulk.includes(mark), 'la barre de scan de la réception groupée n’a pas : ' + mark);
});
assert(/ppRxCam\(ctx\.node\.querySelector\('#bulk-rx-camera'\)/.test(bulk),
  'la réception groupée n’utilise pas le contrôleur caméra partagé');
assert(bulk.includes('ppRxCamWidget()'), 'le bouton caméra n’est pas le composant partagé');
assert(bulk.includes('ppReceptionGuide()'), 'le guide de scan (sons) n’est pas affiché');
assert(/modalCleanup=\(\)=>\{try\{cam&&cam\.stop\(\)/.test(bulk),
  'la caméra n’est pas arrêtée à la fermeture de la fenêtre');
assert(bulk.includes("scanned.clear();paint();message('','Lot vidé"),
  '« Vider les scans » ne vide pas la sélection');

// ---------- 2) la caméra n'exige plus BarcodeDetector ----------
assert(palette.includes('function ppCamLoadZXing('), 'aucun décodeur de secours');
assert(palette.includes("'/static/vendor/zxing.min.js'"), 'le décodeur embarqué n’est pas chargé depuis /static/vendor');
assert(/async function ppRxCamSupported\(\)\{return ppCamHasCamera\(\)\}/.test(palette),
  'la caméra est encore refusée quand BarcodeDetector est absent (Safari / iPhone)');
assert(palette.includes('zx.HTMLCanvasElementLuminanceSource'), 'ZXing n’est pas branché sur les images de la caméra');
assert(palette.includes('zxReader.decode(bitmap,zxHints)'), 'la boucle ZXing ne décode pas les images');
assert(!/if\(!window\.BarcodeDetector\|\|!navigator\.mediaDevices/.test(palette),
  'un chemin refuse encore la caméra sans BarcodeDetector');
assert(palette.includes("v.setAttribute('playsinline','')"), 'la vidéo n’est pas lisible en ligne sur iPhone');

// ---------- 3) le décodeur livré décode un vrai code-barres ----------
const vendor = path.join('static', 'vendor', 'zxing.min.js');
assert(fs.existsSync(vendor), 'static/vendor/zxing.min.js manquant');
const sandbox = { console, window: {}, self: {} };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext('var module=undefined, exports=undefined, define=undefined;' + fs.readFileSync(vendor, 'utf8'),
  sandbox, { filename: 'zxing.min.js' });
const ZXing = sandbox.ZXing;
assert(ZXing && typeof ZXing.MultiFormatReader === 'function', 'ZXing ne s’initialise pas hors navigateur');

// Code 128 réel (mêmes barres que celles imprimées sur les étiquettes ORIENTAL24).
// Positif = barre noire, négatif = espace blanc, en modules.
const RUNS = [2, -1, 1, -2, 3, -2, 2, -2, 2, -2, 2, -1, 1, -1, 5, -1, 3, -1, 2, -2, 1, -2, 3, -1, 1, -2, 2,
  -1, 3, -2, 1, -2, 3, -1, 2, -2, 1, -3, 2, -1, 1, -3, 3, -2, 1, -1, 2, -2, 1, -3, 1, -1, 2, -3, 1, -1, 2,
  -3, 1, -3, 1, -3, 2, -3, 1, -1, 2, -2, 1, -1, 4, -2, 2, -2, 1, -2, 3, -1, 1, -3, 1, -1, 2, -3, 3, -2, 1,
  -1, 2, -2, 3, -1, 2, -1, 3, -1, 2, -3, 3, -1, 1, -1, 2, -10];
const EXPECTED = '024-0E9BDF34B9';
const SCALE = 3;
const modules = RUNS.reduce((n, r) => n + Math.abs(r), 0);
const W = modules * SCALE, H = 90;
const matrix = new Uint8ClampedArray(W * H).fill(255);
let x = 0;
for (const run of RUNS) {
  const width = Math.abs(run) * SCALE;
  if (run > 0) {
    for (let row = 0; row < H; row++) for (let i = 0; i < width; i++) matrix[row * W + x + i] = 0;
  }
  x += width;
}
class LuminanceSource {
  getWidth() { return W; }
  getHeight() { return H; }
  getRow(y, row) { for (let i = 0; i < W; i++) row[i] = matrix[y * W + i]; return row; }
  getMatrix() { return matrix; }
}
const reader = new ZXing.MultiFormatReader();
const hints = new Map();
hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS,
  [ZXing.BarcodeFormat.CODE_128, ZXing.BarcodeFormat.CODE_39, ZXing.BarcodeFormat.QR_CODE]);
hints.set(ZXing.DecodeHintType.TRY_HARDER, true);
const decoded = reader.decode(new ZXing.BinaryBitmap(new ZXing.HybridBinarizer(new LuminanceSource())), hints);
assert.equal(decoded.getText(), EXPECTED, 'le décodeur embarqué ne relit pas le code-barres de l’étiquette');

console.log('Scan caméra universel (réception groupée + décodeur embarqué) PASS');
