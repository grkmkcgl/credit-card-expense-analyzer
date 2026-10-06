# Harcama Analizi

Kredi kartı ekstrelerini ve banka dökümlerini **tamamen kendi cihazınızda** analiz eden, tek dosyalık bir web aracı.
A single-file web tool that analyzes credit card statements and bank exports **entirely on your own device**.

## Gizlilik / Privacy

- Dosyalar hiçbir sunucuya gönderilmez; tüm okuma ve hesaplama tarayıcıda yapılır. Sayfa açıldıktan sonra internet kapatılsa da çalışır.
- Ağ kilidi: sayfadaki güvenlik kuralı (`Content-Security-Policy`, `connect-src 'none'`) hiçbir adrese bağlantı kurulmasına izin vermez; kod istese bile veri dışarı gidemez.
- Tarayıcıda (localStorage vb.) hiçbir veri saklanmaz. Kayıtlar yalnızca kullanıcının seçtiği `harcama-verisi.json` dosyasında tutulur. Telefonda internetsiz açılabilmesi için tarayıcı önbelleğinde yalnızca uygulamanın kendi dosyaları (sayfa, ikonlar) tutulur.
- PDF şifreleri sadece sayfa açıkken bellekte tutulur.
- `.gitignore`, ekstre ve kayıt dosyalarının yanlışlıkla depoya girmesini engeller. **Bu depoya asla gerçek ekstre veya `harcama-verisi.json` eklemeyin.**

Files are never uploaded anywhere; parsing and calculations run in the browser, and the page keeps working offline once loaded. Nothing is stored in browser storage — records live only in the user's own `harcama-verisi.json`. Never commit real statements or data files to this repo.

## Kullanım / Usage

- **Bilgisayar:** Chrome veya Edge ile açın, "Klasör seç" ile kayıt klasörünü seçin (ör. Masaüstü/harcamalar), ekstreleri yükleyin.
- **Telefon (iOS/Android):** Canlı sayfayı açın; kayıt dosyası "Kayıt dosyasını aç" ile açılır, değişiklikler "Kaydet" ile indirilir. iOS 16.4+ gerekir.
- **Telefona uygulama olarak kurma (internetsiz çalışır):** Canlı sayfayı bir kez açın ve ana ekrana ekleyin: iPhone'da Safari → *Paylaş → Ana Ekrana Ekle*, Android'de Chrome → *⋮ → Uygulamayı yükle / Ana ekrana ekle*. Bundan sonra ikondan açılır, uçak modunda da çalışır. İnternet varken açıldığında yeni sürüm kendiliğinden alınır; dosya paylaşmaya gerek yoktur.
- Dosyaya iPhone'daki Dosyalar uygulamasından dokunmak önizleme açar ve sayfa çalışmaz; canlı adresi kullanın.
- **Dönemler:** İşlemler takvim ayına değil, göründükleri **ekstrenin dönemine** yazılır (banka bir harcamayı geç işlerse sonraki ekstrede görünür). Ayın 1–5'inde kesilen bir ekstre önceki ayın dönemi sayılır; ay sonunda kesen kartlarda kesim 31 Ocak → 1 Mart → 31 Mart diye kaysa da her ay tek ekstre görünür.
- **Rapor:** Araç çubuğundaki "Yazdır" sade, beyaz zeminli bir baskı görünümü açar; tarayıcıdan "PDF olarak kaydet" ile rapor alınabilir.

## Özellikler / Features

**Okuma**
- PDF (şifreli dahil), Excel ve CSV; birden çok ekstreyi aynı anda yükleme (sayfanın herhangi bir yerine sürükle-bırak)
- Hesap kesim tarihini, dönem borcunu ve maskeli kart numarasını dosyadan bulma
- Ödeme, iade ve puan (Worldpuan vb.) bölümlerini ayırma
- Dövizli harcamalarda TL tutarını alma; ay sonu/yıl başı (Aralık→Ocak) ekstrelerinde tarihleri doğru yıla yazma; borç/alacak (B/A) sütunlu ekstreler
- Ekstre kontrolü: hesaplanan tutarı dönem borcuyla karşılaştırma, okunamayan satırları tek tıkla ekleme

**Analiz**
- Toplam ve özet kartları; çubuk ve pasta grafik; tüm zamanlar, tek ekstre ya da tarih aralığı
- Önceki ekstreye göre kategori değişimi (▲/▼) ve "en çok artan" kategori
- Kategori trendleri: her kategorinin son 12 dönemi küçük grafiklerle, ortalamaya göre son dönem
- Yıllık özet: yıl toplamı, dönem ortalaması, en yüksek/düşük dönem, ödenen faiz ve ücretler, geçen yılın aynı dönemleriyle karşılaştırma, kategori tablosu ve en çok harcanan yerler
- Taksit takibi: geçmiş ve gelecek taksitler seriden hesaplanır; gelecek aylar için taksit takvimi
- Düzenli ödemeler (abonelikler, faturalar): aylık/yıllık tutar, "tutar arttı", "son 2 dönemde yok"
- Olağandışı harcama uyarıları: çift çekim şüphesi, bir yerin ortalamasının çok üstündeki harcama
- Yer bazında harcama analizi; birden fazla kart varsa karta göre süzme

**Kategoriler**
- Otomatik kategori; kuralları kartlar ve anahtar kelime çipleriyle düzenleme, "Kural dene"
- Kategorisiz yerler için tek tıkla kural önerisi; kategoriyi toplamdan çıkarma
- Kuralları ve yer seçimlerini dosya ile başkasıyla paylaşma (işlem/tutar paylaşılmaz; eklenecekler önce listelenir, yalnızca onaylananlar kaydedilir)

**Düzenleme**
- Tüm işlemlerde arama, kategori süzgeci ve sıralama
- İşlemlere not ve `#etiket` ekleme, etiket toplamları
- Geri al (bildirimden ya da Ctrl/Cmd+Z)
- Uzun bölümler açılır/kapanır; yazdırma/PDF rapor görünümü

## Geliştirme / Development

Tüm uygulama `index.html` içindedir. Excel (SheetJS), PDF (PDF.js) ve arayüz (Preact + htm) kütüphaneleri dosyanın içine sıkıştırılmış olarak gömülüdür; harici bağımlılık veya derleme adımı yoktur. Telefona kurulum için yanında yalnızca `sw.js`, `manifest.webmanifest` ve `icons/` vardır.
The whole app is `index.html`. SheetJS, PDF.js and Preact + htm are embedded (gzip + base64), so there is no build step and no network dependency. `sw.js`, `manifest.webmanifest` and `icons/` only make it installable/offline on phones.

`index.html` içinde iki `<script>` bloğu vardır: ilki gömülü kütüphaneleri açar (ve service worker'ı kaydeder), ikincisi uygulama kodudur. Kod yapısı, kurallar ve dikkat edilecek noktalar `CLAUDE.md` içindedir.

**Testler / Tests:** `pip install -r tests/requirements.txt && python -m playwright install chromium && python tests/run_tests.py`
Sentetik ekstre PDF'leri üretip aracı Chromium'da uçtan uca test eder (53 senaryo, yaklaşık 1,5–3 dakika). `python tests/run_tests.py taksit` yalnızca adında "taksit" geçenleri çalıştırır; `BROWSER=webkit` Safari motorunda çalıştırır. Ayrıntılar `CLAUDE.md` içinde.

## Canlı sayfa / Live page

GitHub Pages, `.github/workflows/pages.yml` ile her push'ta yeniden kurulur:
- `main` → sitenin kökü
- diğer her branch → `/onizleme/<branch-adı>/` (`/` yerine `-`), liste: `/onizleme/`

Böylece bir branch'teki değişiklik, `index.html` indirmeden telefonda/bilgisayarda denenebilir. Yalnızca uygulama dosyaları yayınlanır: `index.html`, `sw.js`, `manifest.webmanifest`, `icons/`.
Ayar: *Settings → Pages → Source: Deploy from a branch → `gh-pages` / (root)*. `gh-pages` branch'i otomatik yazılır, elle değiştirmeyin.

The site is rebuilt by the workflow on every push: `main` at the root, every other branch under `/onizleme/<branch>/`. Only the app files are published (`index.html`, `sw.js`, `manifest.webmanifest`, `icons/`).

Canlı sayfa bağlantıyı bilen herkes tarafından açılabilir, ancak yalnızca boş aracı gösterir; kullanıcı verileri cihazdan çıkmaz.
Anyone with the link can open the page, but it is only the empty tool; user data never leaves the device.
