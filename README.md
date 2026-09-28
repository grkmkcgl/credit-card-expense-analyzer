# Harcama Analizi

Kredi kartı ekstrelerini ve banka dökümlerini **tamamen kendi cihazınızda** analiz eden, tek dosyalık bir web aracı.
A single-file web tool that analyzes credit card statements and bank exports **entirely on your own device**.

## Gizlilik / Privacy

- Dosyalar hiçbir sunucuya gönderilmez; tüm okuma ve hesaplama tarayıcıda yapılır. Sayfa açıldıktan sonra internet kapatılsa da çalışır.
- Tarayıcıda (localStorage vb.) hiçbir şey saklanmaz. Kayıtlar yalnızca kullanıcının seçtiği `harcama-verisi.json` dosyasında tutulur.
- PDF şifreleri sadece sayfa açıkken bellekte tutulur.
- `.gitignore`, ekstre ve kayıt dosyalarının yanlışlıkla depoya girmesini engeller. **Bu depoya asla gerçek ekstre veya `harcama-verisi.json` eklemeyin.**

Files are never uploaded anywhere; parsing and calculations run in the browser, and the page keeps working offline once loaded. Nothing is stored in browser storage — records live only in the user's own `harcama-verisi.json`. Never commit real statements or data files to this repo.

## Kullanım / Usage

- **Bilgisayar:** Chrome veya Edge ile açın, "Klasör seç" ile kayıt klasörünü seçin (ör. Masaüstü/harcamalar), ekstreleri yükleyin.
- **Telefon (iOS/Android):** Canlı sayfayı açın; kayıt dosyası "Kayıt dosyasını aç" ile açılır, değişiklikler "Kaydet" ile indirilir. Safari/Chrome'da *Paylaş → Ana Ekrana Ekle* ile uygulama gibi kullanılabilir. iOS 16.4+ gerekir.
- Dosyaya iPhone'daki Dosyalar uygulamasından dokunmak önizleme açar ve sayfa çalışmaz; canlı adresi kullanın.

## Özellikler / Features

- PDF (şifreli dahil), Excel ve CSV okuma; birden çok ekstreyi aynı anda yükleme
- Hesap kesim tarihini dosyadan bulma; işlemleri ekstre dönemine göre gruplama
- Taksit takibi (geçmiş ve gelecek taksitlerin seriden hesaplanması)
- Ödeme, iade, puan (Worldpuan vb.) bölümlerini ayırma
- Ekstre kontrolü: hesaplanan tutarı dönem borcuyla karşılaştırma
- Otomatik kategori (düzenlenebilir kurallar), kategoriyi toplamdan çıkarma
- Çubuk ve pasta grafik, tarih aralığı analizi, yer bazında harcama analizi

## Geliştirme / Development

Tüm uygulama `index.html` içindedir. Excel (SheetJS) ve PDF (PDF.js) kütüphaneleri dosyanın içine sıkıştırılmış olarak gömülüdür; harici bağımlılık veya derleme adımı yoktur.
The whole app is `index.html`. SheetJS and PDF.js are embedded (gzip + base64), so there is no build step and no network dependency.

Uygulama kodu dosyanın sonundaki `<script>` bloğundadır.

**Testler / Tests:** `pip install -r tests/requirements.txt && python -m playwright install chromium && python tests/run_tests.py`
Sentetik ekstre PDF'leri üretip aracı Chromium'da uçtan uca test eder. Ayrıntılar `CLAUDE.md` içinde.

## Canlı sayfa / Live page

Depo gizli (private) tutulur. Canlı sayfa için depo Cloudflare Pages veya Netlify'a bağlanır; `main` dalına yapılan her değişiklik otomatik yayınlanır.
The repo stays private; the live page is served by Cloudflare Pages or Netlify connected to this repo, auto-deploying every push to `main`.

- Build command: *(boş / none)*
- Output / publish directory: `/` (root)

Canlı sayfa bağlantıyı bilen herkes tarafından açılabilir, ancak yalnızca boş aracı gösterir; kullanıcı verileri cihazdan çıkmaz.
Anyone with the link can open the page, but it is only the empty tool; user data never leaves the device.
