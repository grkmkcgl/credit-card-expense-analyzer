"""index.html için uçtan uca testler (Playwright + Chromium, sentetik PDF'lerle).

Kurulum:   pip install -r tests/requirements.txt && python -m playwright install chromium
Çalıştır:  python tests/run_tests.py            (hepsi)
           python tests/run_tests.py taksit     (adında "taksit" geçen testler)
           VERBOSE=1 python tests/run_tests.py  (hata ayrıntısıyla)
           BROWSER=webkit python tests/run_tests.py  (Safari motoru; önce: python -m playwright install webkit)

Her test aracı tertemiz bir sayfada açar; tarayıcıda hiçbir şey saklanmadığı için testler birbirini etkilemez.
Saat 28.09.2026'ya sabitlenir (gelecek/geçmiş taksit ayrımı buna bağlıdır).
"""
import json
import os
import sys
import traceback

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fixtures  # noqa: E402

PAGE = "file://" + os.path.abspath(os.path.join(HERE, "..", "index.html"))
OUT = fixtures.OUT
NOW = "2026-09-28T09:00:00"
TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def f(name):
    return os.path.join(OUT, name)


class App:
    """Sayfayı açar, klasör seçimini atlayıp yükleme alanlarını gösterir."""

    def __init__(self, browser, width=1000, mobile=False, password=None):
        ctx = browser.new_context(viewport={"width": width, "height": 1300}, accept_downloads=True)
        if mobile:
            ctx.add_init_script("delete window.showDirectoryPicker")
        self.pg = ctx.new_page()
        self.errors = []
        self.prompts = []
        self.pg.on("pageerror", lambda e: self.errors.append(str(e)))
        if password is not None:
            def dlg(d):
                self.prompts.append(d.message); d.accept(password)
            self.pg.on("dialog", dlg)
        self.pg.clock.set_fixed_time(NOW)
        self.pg.goto(PAGE)
        self.pg.wait_for_function("window.libsReady && typeof pdfToRows==='function'")
        self.pg.evaluate("window.libsReady")
        if not mobile:
            self.pg.evaluate("['drop','hist'].forEach(i=>document.getElementById(i).classList.remove('hide'))")

    def ev(self, js, arg=None):
        return self.pg.evaluate(js, arg) if arg is not None else self.pg.evaluate(js)

    def text(self, sel):
        return self.pg.inner_text(sel)

    def load(self, name):
        """Tek dosya: önizlemeye kadar."""
        self.pg.set_input_files("#file", f(name))
        self.pg.wait_for_function("!document.getElementById('setup').classList.contains('hide') || /okunamadı|bulunamadı/.test(document.getElementById('msg').textContent)", timeout=20000)

    def import_(self, name):
        self.load(name)
        self.pg.click("#run")
        self.pg.wait_for_timeout(150)

    def upload_many(self, names):
        self.pg.set_input_files("#file", [f(n) for n in names])
        self.pg.wait_for_function("/dosya işlendi/.test(document.getElementById('msg').textContent)", timeout=60000)

    def period(self, value):
        self.pg.select_option("#period", value)
        self.pg.wait_for_timeout(100)

    def total(self):
        return self.text("#total")

    def close(self):
        assert not self.errors, f"Sayfa hataları: {self.errors}"
        self.pg.context.close()


def eq(a, b, what=""):
    assert a == b, f"{what}: beklenen {b!r}, bulunan {a!r}"


# ---------------------------------------------------------------- PDF okuma
@test
def pdf_buyuk_143_islem(b, info):
    a = App(b); a.load("buyuk.pdf")
    rows = a.ev("raw.slice(1)")
    eq(len(rows), info["big"]["count"], "işlem sayısı")
    a.ev("$('sign').value='pos'"); a.pg.click("#run"); a.pg.wait_for_timeout(100)
    spend = a.ev("history.filter(t=>!t.kind&&!t.est).reduce((s,t)=>s+t.amt,0)")
    assert abs(spend - info["big"]["spend"]) < 0.01, (spend, info["big"]["spend"])
    a.close()


@test
def pdf_taksit_bicimleri_ve_dikey_yazi(b, info):
    a = App(b); a.load("taksit.pdf")
    rows = a.ev("raw.slice(1)")
    eq(len(rows), 10, "işlem sayısı")
    got = {r[1]: (r[2], r[6]) for r in rows}
    eq(got["TEKNOSA ANKARA TR"], ("1.654,98", "2/3"), "aynı satır taksit")
    eq(got["MEDIAMARKT ANKARA TR"], ("1.500,00", "3/6"), "alt satır taksit")
    eq(got["KOTON ANKARA TR"], ("800,00", "1/3"), "tutar üstte, bilgi altta")
    eq(got["IKEA ANKARA TR"], ("500,00", "4/12"), "tarihsiz taksit satırı")
    eq(got["BOYNER"], ("600,00", "2/2"), "sadece toplam")
    for d in got:
        assert not d.endswith((" B", " A", " L")), f"dikey yazıdan harf sızmış: {d!r}"
    eq(a.ev("pdfMissed.length"), 0, "okunamayan satır")
    a.close()


@test
def pdf_arti_odemeler_harcama_sayilmaz(b, info):
    a = App(b); a.import_("arti.pdf")
    msg = a.text("#msg")
    assert "4 yeni harcama" in msg and "2 ödemeniz" in msg and "1 iade" in msg, msg
    kinds = a.ev("history.filter(t=>!t.est).map(t=>[t.desc,t.kind||''])")
    assert ["HESAPTAN ÖDEME", "payment"] in kinds and ["ZARA İADE", "refund"] in kinds, kinds
    a.close()


# ---------------------------------------------------------------- Kesim tarihi
@test
def kesim_tarihi_alti_duzen(b, info):
    a = App(b)
    a.import_("kes_A_ayni_satir.pdf")  # F'nin önceki ekstreden kesim gününü öğrenmesi için
    for k in ["A_ayni_satir", "B_tablo", "C_alt_satir", "D_harf_aralikli", "E_donem", "F_etiket_yok"]:
        a.load(f"kes_{k}.pdf")
        eq(a.ev("$('stmtDate').value"), "2026-08-26", f"kesim tarihi ({k})")
    assert "bulunamadı" in a.text("#stmtSrc"), "F düzeninde tahmin uyarısı gösterilmeli"
    a.close()


# ---------------------------------------------------------------- Dönemler ve taksitler
@test
def ekstre_donemi_gec_islenen_harcama(b, info):
    a = App(b)
    a.import_("k_agustos.pdf"); a.import_("k_temmuz.pdf")
    a.period("2026-08"); eq(a.total(), "₺1.150", "Ağustos ekstresi")
    a.period("2026-07"); eq(a.total(), "₺1.600", "Temmuz ekstresi")
    a.close()


def _series(b, order, expect):
    a = App(b)
    for mo in order:
        a.import_(f"ekstre{mo}.pdf")
    for m, v in expect.items():
        a.period(m); eq(a.total(), v, f"{m} (sıra {order})")
    return a


@test
def taksit_serisi_sirali(b, info):
    exp = {"2026-04": "₺1.500", "2026-05": "₺1.500", "2026-06": "₺1.800", "2026-07": "₺1.800", "2026-08": "₺1.800", "2026-09": "₺1.500"}
    a = _series(b, [4, 5, 6, 7, 8, 9], exp)
    a.period(""); assert a.total() == "₺9.900", a.total()
    a.close()


@test
def taksit_serisi_karisik_sira(b, info):
    exp = {"2026-04": "₺1.500", "2026-05": "₺1.500", "2026-06": "₺1.800", "2026-07": "₺1.800", "2026-08": "₺1.800", "2026-09": "₺1.500"}
    _series(b, [9, 4, 7, 5, 8, 6], exp).close()


@test
def taksit_sadece_son_ekstre_gecmisi_hesaplar(b, info):
    a = _series(b, [9], {"2026-04": "₺1.000", "2026-08": "₺1.000", "2026-09": "₺1.500"})
    eq(a.ev("history.filter(t=>t.est==='past').length"), 5, "hesaplanan geçmiş taksit")
    a.close()


@test
def ayni_ekstre_iki_kez_yuklenince_tekrar_etmez(b, info):
    a = App(b); a.import_("ekstre6.pdf"); n = a.ev("history.length")
    a.import_("ekstre6.pdf")
    eq(a.ev("history.length"), n, "kayıt sayısı")
    assert "zaten kayıtlıydı" in a.text("#msg")
    a.close()


# ---------------------------------------------------------------- Ekstre kontrolü
def _recon(a, stmt_month="2026-08"):
    a.period(stmt_month)
    return a.text("#recon")


@test
def ekstre_kontrolu_tutuyor(b, info):
    for name in ["r_tutuyor.pdf", "r_oncekiyok.pdf"]:
        a = App(b); a.import_(name)
        assert "Tutuyor" in _recon(a), (name, _recon(a))
        a.close()


@test
def ekstre_kontrolu_fark_ve_ekle(b, info):
    a = App(b); a.import_("r_fark.pdf")
    r = _recon(a)
    assert "Fark: ₺150,00" in r, r
    a.pg.click("#recon button[data-mi]"); a.pg.wait_for_timeout(150)
    assert "Tutuyor" in a.text("#recon")
    a.close()


@test
def gercek_duzen_puan_ve_taksit_tutarlari(b, info):
    a = App(b); a.load("gercek_duzen.pdf")
    got = {r[1]: r[2] for r in a.ev("raw.slice(1)")}
    eq(got["PASTANE ORNEK ESKİŞEHİR TR"], "500,00", "puan sütunu tutar sanılmamalı")
    eq(got["SIGORTA ORNEK ISTANBUL TR"], "1.624,27", "çok tutarlı taksit satırı")
    eq(got["SEYAHAT ORNEK ISTANBUL TR"], "20.902,46", "çok tutarlı taksit satırı")
    a.pg.click("#run"); a.pg.wait_for_timeout(100)
    assert "Tutuyor" in _recon(a), _recon(a)
    a.close()


@test
def puan_detayi_bolumu_yok_sayilir(b, info):
    for name in ["wp_ayri.pdf", "wp_yapisik.pdf"]:
        a = App(b); a.import_(name)
        assert "Tutuyor" in _recon(a), (name, _recon(a))
        eq(a.ev("history.filter(t=>t.kind==='payment').length"), 0, f"ödeme sayısı ({name})")
        a.close()


@test
def eski_surum_kayitlari_tekrar_yuklemede_onarilir(b, info):
    old = [{"id": "2026-08-01|KAFE ORNEK ESKISEHIR TR|910#1", "date": "2026-08-01", "desc": "KAFE ORNEK ESKISEHIR TR", "amt": 910},
           {"id": "T|SIGORTA ORNEK ISTANBUL TR|10|16242.7|6", "date": "2026-03-04", "desc": "SIGORTA ORNEK ISTANBUL TR", "amt": 1624.27,
            "inst": {"n": 6, "m": 10, "total": 16242.7}, "note": "Taksit 6/10 (toplam 16.242,70 TL)"},
           {"id": "P|2026-08-26|X|37.75#1", "date": "2026-08-26", "stmt": "2026-08-26", "kind": "payment", "amt": 37.75,
            "desc": "WORLDPUAN DETAYI Bu Ay Kazanılan/Kullanılan DÖNEM İÇİ ALIŞVERİŞLERDEN KAZANILAN WORLDPUAN 3.775"}]
    a = App(b); a.ev("h=>{applyData({history:h});render()}", old)
    eq(a.ev("history.filter(t=>/WORLDPUAN DETAYI/.test(t.desc)).length"), 0, "yanlış puan kaydı silinmeli")
    a.import_("wp_ayri.pdf")
    eq(a.ev("history.filter(t=>!t.est&&!t.stmt).length"), 0, "ekstresiz kayıt kalmamalı")
    assert "Tutuyor" in _recon(a)
    a.close()


# ---------------------------------------------------------------- Çoklu yükleme
@test
def coklu_yukleme_sifreli_ve_bozuk(b, info):
    a = App(b, password="123456")
    a.upload_many(["ekstre4.pdf", "ekstre5.pdf", "ekstre6.pdf", "sifreli7.pdf", "sifreli8.pdf", "ekstre9.pdf", "wp_ayri.pdf", "bozuk.pdf"])
    msg = a.text("#msg")
    assert msg.startswith("7/8 dosya işlendi"), msg
    assert "bozuk.pdf" in msg and "okunamadı" in msg, msg
    eq(len(a.prompts), 1, "şifre bir kez sorulmalı")
    a.close()


# ---------------------------------------------------------------- Kategoriler
@test
def kategori_eslestirme(b, info):
    a = App(b); a.ev("parseRules()")
    cases = {"PATİ VETERİNER KLİNİĞİ ANKARA TR": "Veteriner ve evcil hayvan", "HAYVAN HASTANESI ANKARA": "Veteriner ve evcil hayvan",
             "PETSHOP DÜNYASI ANKARA": "Veteriner ve evcil hayvan", "ORNEK LOJISTIK PETROL KONYA TR": "Akaryakıt", "PETROL OFISI ANKARA": "Akaryakıt",
             "DİŞ HEKİMİ AHMET": "Sağlık", "ACIBADEM KLINIK": "Sağlık", "EGE PIDE SALONU ANKARA TR": "Kafe ve restoran",
             "BİM BIM-O001 ORNEK ANKARA TR": "Market", "OPET ANKARA": "Akaryakıt", "MEDIAMARKT ANKARA TR": "Elektronik",
             # kısa anahtarlar (PET, DIS) sadece ayrı kelime olarak eşleşmeli
             "PETEK APARTMAN YONETIMI": "Diğer", "YURT DISI SEYAHAT ACENTESI": "Diğer"}
    for d, c in cases.items():
        eq(a.ev("d=>categorize(d)", d), c, d)
    a.close()


@test
def kayitli_kurallara_yeni_anahtarlar_eklenir(b, info):
    a = App(b)
    a.ev("r=>{applyData({history:[],rules:r});parseRules()}", "Kafe ve restoran: STARBUCKS, CAFE\nSağlık: ECZANE, HASTANE, KLINIK\nAkaryakıt: SHELL")
    eq(a.ev("d=>categorize(d)", "EGE PIDE SALONU"), "Kafe ve restoran", "yeni anahtar")
    eq(a.ev("d=>categorize(d)", "HAYVAN HASTANESI"), "Veteriner ve evcil hayvan", "yeni kategori")
    eq(a.ev("$('rules').value.split('\\n')[0].split('CAFE').length-1"), 1, "anahtar tekrarlanmamalı")
    a.close()


def _write_json(name, obj):
    p = f(name)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False)
    return p


@test
def kategori_paylas_disa_aktar(b, info):
    a = App(b); a.import_("arti.pdf")
    a.ev("()=>{$('rules').value+='\\nHobi: ORNEKHOBI';overrides['ORNEK BUTIK']='Giyim';render()}")
    a.pg.click("#rulesFold > summary")
    with a.pg.expect_download() as dl:
        a.pg.click("#shareCats")
    d = dl.value
    eq(d.suggested_filename, "harcama-kategorileri.json", "dosya adı")
    data = json.loads(open(d.path(), encoding="utf-8").read())
    eq(data.get("type"), "kategoriler", "tür")
    assert "Hobi: ORNEKHOBI" in data["rules"], "kurallar paylaşılmalı"
    eq(data["overrides"].get("ORNEK BUTIK"), "Giyim", "yer seçimi paylaşılmalı")
    for k in ("history", "statements", "lastMap"):
        assert k not in data, f"paylaşım dosyasında {k} olmamalı"
    a.close()


SHARE_A = {
    "type": "kategoriler", "version": 1,
    "rules": "Market: MIGROS, KOSE BAKKALI ORNEK, migros, ORNEKMARKET\nHobi: ORNEKHOBI, MAKETCI",
    "overrides": {"ORNEK BUTIK": "Giyim", "ÖRNEK KAFE": "Market", "YENI DUKKAN": "Hobi"},
}


def _preview(a, path):
    a.pg.set_input_files("#importCats", path)
    a.pg.wait_for_function("!document.getElementById('sharePreview').classList.contains('hide') || /okunamadı|güncel/.test(document.getElementById('shareMsg').textContent)")


@test
def kategori_paylas_ice_aktar_onizleme_ve_secim(b, info):
    share = _write_json("paylas_a.json", SHARE_A)
    a = App(b); a.import_("arti.pdf")
    n = a.ev("history.length")
    a.ev("()=>{overrides['ORNEK KAFE']='Kafe ve restoran';render()}")
    rules0 = a.ev("$('rules').value")
    _preview(a, share)
    # onaydan önce hiçbir şey değişmez
    eq(a.ev("$('rules').value"), rules0, "önizlemede kurallar değişmemeli")
    eq(a.ev("overrides['ORNEK BUTIK']||null"), None, "önizlemede yer seçimi eklenmemeli")
    pv = a.text("#sharePreview")
    for s in ("KOSE BAKKALI ORNEK", "ORNEKMARKET", "Hobi", "MAKETCI", "ORNEK BUTIK", "YENI DUKKAN", "Kafe ve restoran", "Uygula", "Vazgeç"):
        assert s in pv, f"önizlemede '{s}' yok: {pv}"
    eq(a.ev("[...document.querySelectorAll('#sharePreview input[data-imp=keys]')].length"), 2, "tekrarlanan MIGROS listelenmemeli")
    eq(a.ev("document.querySelector('#sharePreview input[data-imp=conflicts]').checked"), False, "çakışma varsayılan olarak işaretsiz")
    eq(a.ev("[...document.querySelectorAll('#sharePreview input[data-imp]:not([data-imp=conflicts])')].every(c=>c.checked)"), True, "yeniler varsayılan işaretli")
    # ORNEKMARKET'i ve YENI DUKKAN'ı reddet, çakışmada karşı tarafı seç
    a.ev("()=>{const L=[...document.querySelectorAll('#sharePreview label')];"
         "L.find(l=>l.textContent.includes('ORNEKMARKET')).querySelector('input').checked=false;"
         "L.find(l=>l.textContent.includes('YENI DUKKAN')).querySelector('input').checked=false;"
         "document.querySelector('#sharePreview input[data-imp=conflicts]').checked=true}")
    a.pg.click("#impApply"); a.pg.wait_for_timeout(150)
    rules = a.ev("$('rules').value")
    market = [l for l in rules.split("\n") if l.startswith("Market:")][0]
    assert "KOSE BAKKALI ORNEK" in market, "onaylanan anahtar eklenmeli"
    assert "ORNEKMARKET" not in rules, "reddedilen anahtar eklenmemeli"
    eq(sum(l.startswith("Hobi:") for l in rules.split("\n")), 1, "yeni kategori bir kez eklenmeli")
    eq(a.ev("d=>categorize(d)", "MAKETCI DUNYASI"), "Hobi", "yeni kural uygulanmalı")
    eq(a.ev("overrides['ORNEK BUTIK']"), "Giyim", "onaylanan yer seçimi eklenmeli")
    eq(a.ev("overrides['YENI DUKKAN']||null"), None, "reddedilen yer seçimi eklenmemeli")
    eq(a.ev("overrides['ORNEK KAFE']"), "Market", "seçilen çakışmada karşı tarafınki alınmalı")
    eq(a.ev("history.length"), n, "işlemler değişmemeli")
    assert a.ev("document.getElementById('sharePreview').classList.contains('hide')"), "önizleme kapanmalı"
    msg = a.text("#shareMsg")
    for s in ("1 yeni anahtar kelime", "1 yeni kategori", "1 yer seçimi", "1 yer için karşı tarafın seçimi"):
        assert s in msg, f"mesajda '{s}' yok: {msg}"
    # tekrar: yalnızca reddedilenler listelenir
    _preview(a, share)
    eq(a.ev("[...document.querySelectorAll('#sharePreview input[data-imp]')].map(c=>c.dataset.imp).sort()"), ["keys", "picks"], "yalnızca reddedilenler kalmalı")
    a.close()


@test
def kategori_ice_aktar_vazgec_ve_guncel(b, info):
    share = _write_json("paylas_a.json", SHARE_A)
    a = App(b); a.import_("arti.pdf")
    rules0 = a.ev("$('rules').value"); ov0 = a.ev("JSON.stringify(overrides)")
    _preview(a, share)
    a.pg.click("#impCancel"); a.pg.wait_for_timeout(100)
    eq(a.ev("$('rules').value"), rules0, "vazgeçince kurallar aynı")
    eq(a.ev("JSON.stringify(overrides)"), ov0, "vazgeçince yer seçimleri aynı")
    assert "iptal" in a.text("#shareMsg"), a.text("#shareMsg")
    # hepsini onayla, sonra aynı dosya: önizleme açılmaz
    _preview(a, share); a.pg.click("#impApply"); a.pg.wait_for_timeout(100)
    _preview(a, share)
    assert a.ev("document.getElementById('sharePreview').classList.contains('hide')"), "değişiklik yoksa önizleme açılmamalı"
    assert "zaten güncel" in a.text("#shareMsg"), a.text("#shareMsg")
    a.close()


@test
def kategori_ice_aktar_tam_kayit_ve_bozuk_dosya(b, info):
    full = _write_json("paylas_tam.json", {
        "version": 1, "history": [{"id": "x1", "date": "2026-01-01", "desc": "BASKASININ ISLEMI", "amount": 999}],
        "statements": {}, "rules": "Hobi: ORNEKHOBI", "overrides": {"ORNEK BUTIK": "Giyim"},
    })
    bad = f("paylas_bozuk.json")
    with open(bad, "w") as fh:
        fh.write("{bozuk")
    a = App(b); a.import_("arti.pdf")
    n = a.ev("history.length")
    _preview(a, full); a.pg.click("#impApply"); a.pg.wait_for_timeout(150)
    eq(a.ev("history.length"), n, "başkasının işlemleri alınmamalı")
    eq(a.ev("d=>categorize(d)", "ORNEKHOBI MAGAZA"), "Hobi", "kurallar alınmalı")
    eq(a.ev("overrides['ORNEK BUTIK']"), "Giyim", "yer seçimi alınmalı")
    before = a.ev("$('rules').value")
    _preview(a, bad)
    assert "okunamadı" in a.text("#shareMsg"), a.text("#shareMsg")
    eq(a.ev("$('rules').value"), before, "bozuk dosya kuralları değiştirmemeli")
    a.close()


# ---------------------------------------------------------------- Görünümler
@test
def kategori_cikarma_ve_tarih_araligi(b, info):
    a = App(b); a.import_("wp_ayri.pdf"); a.period("2026-08")
    eq(a.total(), "₺28.339", "Ağustos toplam")
    a.pg.uncheck("input[data-inc='Taksitler']"); a.pg.wait_for_timeout(100)
    eq(a.total(), "₺5.813", "taksitler çıkınca")
    snap = a.ev("snapshot()"); a.ev("s=>{applyData(JSON.parse(s));render()}", snap)
    eq(a.ev("[...excluded]"), ["Taksitler"], "çıkarma kaydediliyor")
    a.pg.click("#inclAll"); a.pg.wait_for_timeout(100)
    a.period("range"); a.pg.fill("#rFrom", "2026-08-01"); a.pg.fill("#rTo", "2026-08-03"); a.pg.dispatch_event("#rTo", "change"); a.pg.wait_for_timeout(100)
    eq(a.total(), "₺2.680", "1-3 Ağustos")
    assert "10 işlem" in a.text("#range"), a.text("#range")
    a.close()


@test
def pasta_grafik(b, info):
    a = App(b); a.import_("wp_ayri.pdf"); a.period("2026-08")
    a.pg.click("#vPie"); a.pg.uncheck("input[data-inc='Taksitler']"); a.pg.wait_for_timeout(150)
    labels = a.ev("[...document.querySelectorAll('#donut path')].map(p=>p.getAttribute('aria-label').split(':')[0])")
    assert "Taksitler" not in labels and "Akaryakıt" in labels, labels
    bb = a.pg.locator("#donut svg").bounding_box(); s = bb["width"] / 240
    a.pg.mouse.click(bb["x"] + 150 * s, bb["y"] + 35 * s); a.pg.wait_for_timeout(150)  # ilk dilimin halkası
    eq(a.ev("[...document.querySelectorAll('#cats .row[aria-expanded=true]')].map(x=>x.dataset.cat)"), [labels[0]], "dilime tıklayınca açılan")
    a.close()


# ---------------------------------------------------------------- Harcama analizi
def _pide_history():
    H, i = [], 0
    data = {"2026-04": [("EGE PIDE SALONU ANKARA TR", 420, "2026-04-15")],
            "2026-05": [("EGE PIDE SALONU ANKARA TR", 380, "2026-05-03"), ("EGE PIDE CANKAYA ANKARA TR", 510, "2026-05-20")],
            "2026-06": [], "2026-07": [("EGE PIDE SALONU ANKARA TR", 450, "2026-07-12")],
            "2026-08": [("EGE PIDE SALONU ANKARA TR", 600, "2026-08-02"), ("EGE PIDE SALONU ANKARA TR", 720, "2026-08-09"), ("EGE PIDE CANKAYA ANKARA TR", 540, "2026-08-20")]}
    for m, rows in data.items():
        st = m + "-26"; H.append({"id": f"x{i}", "date": m + "-10", "stmt": st, "desc": "MİGROS ANKARA TR", "amt": 2000}); i += 1
        for d, amt, dt in rows:
            H.append({"id": f"x{i}", "date": dt, "stmt": st, "desc": d, "amt": amt}); i += 1
    return H


@test
def harcama_analizi_kapsamlar(b, info):
    a = App(b); a.ev("h=>{applyData({history:h});render()}", _pide_history())
    a.pg.fill("#q", "ege pide"); a.pg.wait_for_timeout(300)
    q = a.text("#qOut"); assert "₺3.620" in q and "%323 fazla" in q, q
    a.period("2026-08"); q = a.text("#qOut"); assert "₺1.860" in q and "3 kez" in q and "Diğer ayların ortalaması" in q, q
    a.period("range"); a.pg.fill("#rFrom", "2026-05-01"); a.pg.fill("#rTo", "2026-07-31"); a.pg.dispatch_event("#rTo", "change"); a.pg.wait_for_timeout(150)
    assert "₺1.340" in a.text("#qOut"), a.text("#qOut")
    a.pg.fill("#rFrom", "2026-06-01"); a.pg.fill("#rTo", "2026-06-30"); a.pg.dispatch_event("#rTo", "change"); a.pg.wait_for_timeout(150)
    assert "bulunamadı" in a.text("#qOut")
    a.close()


@test
def harcama_analizi_listelerden_acilir(b, info):
    a = App(b); a.ev("h=>{applyData({history:h});render()}", _pide_history()); a.period("2026-08")
    for view in ["#vBar", "#vPie"]:
        a.pg.click(view); a.pg.fill("#q", ""); a.pg.dispatch_event("#q", "input")
        row = a.pg.locator("#cats button.row").filter(has_text="Kafe").first
        if row.get_attribute("aria-expanded") != "true": row.click(); a.pg.wait_for_timeout(100)
        a.pg.locator("#cats .catlist button[data-an]").filter(has_text="CANKAYA").first.click(); a.pg.wait_for_timeout(150)
        eq(a.ev("$('q').value"), "ege pide", f"kategori listesinden ({view})")
    a.pg.click("#allFold > summary")
    for sel in ["#top", "#alltx"]:
        a.pg.fill("#q", ""); a.pg.dispatch_event("#q", "input")
        a.pg.locator(sel + " button[data-an]").first.click(); a.pg.wait_for_timeout(150)
        assert a.ev("$('q').value"), f"{sel} listesinden analiz açılmadı"
    a.close()


@test
def veri_yuklenince_sade_ust_kisim_ve_ozet_kartlari(b, info):
    a = App(b)
    assert a.pg.is_visible("#how") and not a.pg.is_visible("#toolbar"), "boşken adımlar görünmeli"
    assert not a.pg.is_visible("#tabs"), "veri kaynağı açılmadan sekmeler görünmemeli"
    a.import_("wp_ayri.pdf")
    for sel in ["#folderPanel", "#drop", "#how", ".intro"]:
        assert not a.pg.is_visible(sel), f"veri varken {sel} gizlenmeli"
    assert a.pg.is_visible("#toolbar") and a.pg.is_visible("#hist"), "araç çubuğu ve kayıt bölümü görünmeli"
    a.period("2026-08")
    k = a.text("#kpis"); assert "Tutuyor" in k and "En büyük kategori" in k, k
    a.pg.click("#kpiRecon"); a.pg.wait_for_timeout(100)
    assert a.ev("document.querySelector('#recon details').open"), "kart ekstre kontrolünü açmalı"
    a.period("")
    assert "Gelecek taksitler" in a.text("#kpis"), a.text("#kpis")
    # Sayfaya bırakılan dosya da yüklenir
    data = list(open(f("arti.pdf"), "rb").read())
    a.ev("""d=>{const dt=new DataTransfer();dt.items.add(new File([new Uint8Array(d)],"arti.pdf",{type:"application/pdf"}));
      document.body.dispatchEvent(new DragEvent("drop",{dataTransfer:dt,bubbles:true,cancelable:true}))}""", data)
    a.pg.wait_for_function("!document.getElementById('setup').classList.contains('hide')", timeout=20000)
    assert not a.ev("document.body.classList.contains('dragging')")
    a.close()


@test
def islem_silmeden_once_onay_sorulur(b, info):
    a = App(b); a.import_("arti.pdf")
    real = "history.filter(t=>!t.est).length"
    n = a.ev(real)
    answers, msgs = [False, True], []
    def dlg(d):
        msgs.append(d.message); d.accept() if answers.pop(0) else d.dismiss()
    a.pg.on("dialog", dlg)
    a.pg.click("#allFold > summary"); a.pg.wait_for_timeout(100)
    desc = a.pg.locator("#alltx tbody tr").first.locator("button[data-an]").inner_text()
    a.pg.locator("#alltx button.x").first.click(); a.pg.wait_for_timeout(100)
    eq(a.ev(real), n, "vazgeçince silinmemeli")
    assert "silinsin mi" in msgs[0] and desc in msgs[0], msgs
    a.pg.locator("#alltx button.x").first.click(); a.pg.wait_for_timeout(100)
    eq(a.ev(real), n - 1, "onaylayınca silinmeli")
    a.close()


@test
def katlanir_bolumler(b, info):
    a = App(b); a.import_("arti.pdf")
    for fid in ("allFold", "unkFold", "monthsFold", "rulesFold"):
        eq(a.ev(f"$('{fid}').open"), False, f"{fid} başta kapalı")
    assert not a.pg.is_visible("#alltx"), "kapalıyken tablo görünmemeli"
    n = a.ev("$('alltx').tBodies[0].rows.length")
    assert n > 0
    eq(a.text("#allCount"), f"({n} işlem)", "başlıktaki sayı")
    unk = a.ev("[...document.querySelectorAll('#unk select')].length")
    eq(a.text("#unkCount"), f"({unk})" if unk else "", "kategorisizler sayısı")
    months = a.ev("$('months').querySelectorAll('.mrow').length")
    assert months > 0
    eq(a.text("#monthsCount"), f"({months} dönem)", "dönem sayısı")
    cats = a.ev("new Set($('rules').value.split('\\n').filter(l=>l.indexOf(':')>0).map(l=>l.slice(0,l.indexOf(':')).trim())).size")
    eq(a.text("#rulesCount"), f"({cats} kategori)", "kategori sayısı")
    a.pg.click("#allFold > summary"); a.pg.wait_for_timeout(100)
    assert a.pg.is_visible("#alltx"), "açınca tablo görünmeli"
    a.pg.select_option("#alltx select >> nth=0", "Market"); a.pg.wait_for_timeout(150)
    eq(a.ev("$('allFold').open"), True, "yeniden çizimde açık kalmalı")
    a.pg.click("#allFold > summary"); a.pg.wait_for_timeout(100)
    eq(a.ev("$('allFold').open"), False, "tekrar tıklayınca kapanmalı")
    _preview(a, _write_json("paylas_a.json", SHARE_A))
    eq(a.ev("$('rulesFold').open"), True, "içe aktarma önizlemesi kural bölümünü açmalı")
    assert a.pg.is_visible("#impApply")
    a.close()


# ---------------------------------------------------------------- Telefon
@test
def telefon_ac_kaydet_tekrar_ac(b, info):
    a = App(b, width=390, mobile=True)
    assert a.pg.is_visible("#mobilePanel") and not a.pg.is_visible("#folderPanel")
    a.pg.click("#fresh"); a.import_("arti.pdf")
    assert a.pg.is_visible("#saveBar"), "kaydet çubuğu görünmeli"
    total = a.total()
    with a.pg.expect_download() as d:
        a.pg.click("#dl")
    path = os.path.join(OUT, "indirilen.json"); d.value.save_as(path)
    eq(d.value.suggested_filename, "harcama-verisi.json", "dosya adı")
    json.load(open(path, encoding="utf-8"))
    a.pg.reload(); a.pg.wait_for_function("window.libsReady"); a.pg.set_input_files("#openData", path); a.pg.wait_for_timeout(200)
    eq(a.total(), total, "tekrar açınca toplam")
    a.close()


@test
def tarayicida_veri_saklanmaz(b, info):
    a = App(b); a.import_("arti.pdf")
    eq(a.ev("localStorage.length+sessionStorage.length"), 0, "tarayıcı depolaması boş olmalı")
    a.close()


@test
def arayuz_kutuphanesi_gomulu_ve_ag_yok(b, info):
    ctx = b.new_context(viewport={"width": 1000, "height": 1300})
    pg = ctx.new_page()
    urls = []
    pg.on("request", lambda r: urls.append(r.url))
    pg.goto(PAGE); pg.wait_for_function("window.libsReady"); pg.evaluate("window.libsReady")
    bad = [u for u in urls if not u.startswith(("file:", "data:", "blob:", "about:"))]
    assert not bad, f"ağ isteği yapıldı: {bad}"
    eq(pg.evaluate("typeof preact.render+typeof hx"), "functionfunction", "Preact ve htm yüklenmeli")
    out = pg.evaluate("()=>{const d=document.createElement('div');preact.render(hx`<b class=x>${1+1} ok</b>`,d);return d.innerHTML}")
    eq(out, '<b class="x">2 ok</b>', "htm şablonu çizilmeli")
    ctx.close()


@test
def kategori_listesi_yerinde_guncellenir(b, info):
    a = App(b); a.import_("arti.pdf")
    a.ev("document.querySelector('#cats input[data-inc]').dataset.isaret='1'")
    rows = a.pg.locator("#cats button.row")
    rows.nth(1).click(); a.pg.wait_for_timeout(100)
    eq(rows.nth(1).get_attribute("aria-expanded"), "true", "satır açılmalı")
    assert a.pg.is_visible("#cats .catlist"), "işlem listesi görünmeli"
    eq(a.ev("document.querySelector('#cats input[data-inc]').dataset.isaret"), "1", "DOM yeniden yaratılmamalı, yerinde güncellenmeli")
    calls = a.ev("()=>{window._n=0;const o=openAnalysis;openAnalysis=d=>{window._n++;return o(d)};return 0}")
    a.pg.locator("#cats .catlist button[data-an]").first.click(); a.pg.wait_for_timeout(100)
    eq(a.ev("window._n"), 1, "analiz tek kez açılmalı (çift dinleyici yok)")
    rows.nth(1).click(); a.pg.wait_for_timeout(100)
    assert not a.pg.is_visible("#cats .catlist"), "tekrar tıklayınca kapanmalı"
    a.close()


@test
def ekstre_kontrolu_kapali_kalir(b, info):
    a = App(b); a.import_("wp_ayri.pdf"); a.period("2026-08")
    assert a.ev("!!$('recon').querySelector('details')"), "ekstre kontrolü görünmeli"
    a.ev("$('recon').querySelector('details').open=false"); a.ev("render()")
    eq(a.ev("$('recon').querySelector('details').open"), False, "kullanıcının kapattığı kutu yeniden çizimde açılmamalı")
    a.pg.click("#kpiRecon"); a.pg.wait_for_timeout(100)
    eq(a.ev("$('recon').querySelector('details').open"), True, "özet kartı kutuyu açmalı")
    a.close()


@test
def pasta_grafik_yerinde_guncellenir(b, info):
    a = App(b); a.import_("arti.pdf"); a.pg.click("#vPie"); a.pg.wait_for_timeout(700)
    n0 = a.ev("document.querySelectorAll('#donut path').length")
    a.ev("document.querySelector('#donut path').dataset.isaret='1'")
    total0 = a.text("#dVal")
    bb = a.pg.locator("#donut svg").bounding_box(); sc = bb["width"] / 240
    a.pg.mouse.move(bb["x"] + 150 * sc, bb["y"] + 35 * sc); a.pg.wait_for_timeout(100)  # ilk dilimin halkası
    assert a.text("#dName"), "üzerine gelince kategori adı görünmeli"
    assert a.text("#dVal") != total0, "üzerine gelince dilimin tutarı görünmeli"
    a.pg.mouse.move(2, 2); a.pg.wait_for_timeout(100)
    eq(a.text("#dName"), "", "ayrılınca ad silinmeli"); eq(a.text("#dVal"), total0, "ayrılınca toplam dönmeli")
    a.pg.uncheck("input[data-inc='Ulaşım']"); a.pg.wait_for_timeout(500)
    eq(a.ev("document.querySelectorAll('#donut path').length"), n0 - 1, "dışlanan kategorinin dilimi kalkmalı")
    eq(a.ev("document.querySelector('#donut path').dataset.isaret"), "1", "dilim DOM'u yeniden yaratılmamalı")
    a.pg.focus("#donut path >> nth=1"); a.pg.keyboard.press("Enter"); a.pg.wait_for_timeout(150)
    assert a.pg.is_visible("#cats .catlist"), "Enter ile kategori açılmalı"
    assert not a.errors, a.errors
    a.close()


@test
def pasta_grafik_hareket_azaltilinca_animasyonsuz(b, info):
    ctx = b.new_context(viewport={"width": 1000, "height": 1300}, reduced_motion="reduce")
    pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.clock.set_fixed_time(NOW); pg.goto(PAGE); pg.wait_for_function("window.libsReady && typeof pdfToRows==='function'")
    pg.evaluate("window.libsReady")
    pg.evaluate("['drop','hist'].forEach(i=>document.getElementById(i).classList.remove('hide'))")
    pg.set_input_files("#file", f("arti.pdf"))
    pg.wait_for_function("!document.getElementById('setup').classList.contains('hide')", timeout=20000)
    pg.click("#run"); pg.wait_for_timeout(150); pg.click("#vPie"); pg.wait_for_timeout(50)
    eq(pg.evaluate("getComputedStyle(document.querySelector('#donut path')).animationName"), "none", "animasyon kapalı olmalı")
    pg.uncheck("input[data-inc='Ulaşım']"); pg.wait_for_timeout(50)
    eq(pg.evaluate("document.querySelectorAll('#donut path').length"), 3, "hemen son durumda olmalı")
    assert not errs, errs
    ctx.close()


@test
def tum_islemler_arama_suzgec_siralama(b, info):
    a = App(b); a.import_("arti.pdf"); a.pg.click("#allFold > summary")
    rows = lambda: a.ev("[...document.querySelectorAll('#alltx tbody button[data-an]')].map(b=>b.textContent)")
    n = len(rows()); assert n >= 5, rows()
    a.pg.fill("#txq", "teknosa"); a.pg.wait_for_timeout(300)
    r = rows(); assert r and all("TEKNOSA" in x for x in r), r
    assert "/" in a.text("#allCount"), a.text("#allCount")
    a.pg.fill("#txq", "akaryakıt"); a.pg.wait_for_timeout(300)
    assert rows() == ["SHELL ORNEK ANKARA TR"], rows()
    a.pg.fill("#txq", ""); a.pg.wait_for_timeout(300); eq(len(rows()), n, "arama temizlenince hepsi")
    a.pg.select_option("#txcat", "Ulaşım"); a.pg.wait_for_timeout(100)
    eq(rows(), ["OTOPARK B ISTANBUL TR"], "kategori süzgeci")
    a.pg.select_option("#txcat", ""); a.pg.wait_for_timeout(100)
    a.pg.click("#alltx button[data-sort=amt]"); a.pg.wait_for_timeout(100)
    amts = a.ev("[...document.querySelectorAll('#alltx tbody tr')].map(r=>r.cells[3].textContent)")
    first_desc = rows()[0]
    a.pg.click("#alltx button[data-sort=amt]"); a.pg.wait_for_timeout(100)
    assert rows()[0] != first_desc and rows()[-1] == first_desc, "tekrar tıklayınca ters sıralanmalı"
    assert "ZARA" in rows()[0], rows()
    a.pg.fill("#txq", "yokboyleyer"); a.pg.wait_for_timeout(300)
    assert "uyan işlem yok" in a.text("#alltx")
    assert not a.errors, a.errors
    a.close()


@test
def donem_karsilastirma(b, info):
    a = App(b); a.ev("h=>{applyData({history:h});render()}", _pide_history())
    a.period("2026-08")
    badges = a.ev("Object.fromEntries([...document.querySelectorAll('#cats .cat')].map(c=>[c.dataset.k,(c.querySelector('.delta')||{}).textContent||'']))")
    eq(badges.get("Kafe ve restoran"), "▲ %313", "Kafe 450 → 1.860")
    eq(badges.get("Market"), "", "değişmeyen kategoride rozet yok")
    k = a.text("#kpis"); assert "En çok artan" in k and "Kafe ve restoran" in k and "₺1.410" in k, k
    a.period("2026-07")
    badges = a.ev("Object.fromEntries([...document.querySelectorAll('#cats .cat')].map(c=>[c.dataset.k,(c.querySelector('.delta')||{}).textContent||'']))")
    eq(badges.get("Kafe ve restoran"), "yeni", "önceki dönemde yoksa 'yeni'")
    a.period("")
    eq(a.ev("document.querySelectorAll('#cats .delta').length"), 0, "tüm zamanlarda rozet yok")
    assert "En çok artan" not in a.text("#kpis")
    assert not a.errors, a.errors
    a.close()


@test
def duzenli_odemeler(b, info):
    H, i = [], 0
    def add(d, desc, amt, **kw):
        nonlocal i; H.append({"id": f"r{i}", "date": d, "stmt": d[:7] + "-26", "desc": desc, "amt": amt, **kw}); i += 1
    for m, net, spo, gym, kafe in [("2026-04", 199.99, 59.99, 900, 120), ("2026-05", 199.99, 59.99, 900, 800),
                                    ("2026-06", 199.99, 59.99, 900, 60), ("2026-07", 229.99, 59.99, None, 300), ("2026-08", 229.99, 59.99, None, 45)]:
        add(m + "-05", "NETFLIX.COM ISTANBUL TR", net); add(m + "-07", "SPOTIFY AB STOCKHOLM SE", spo)
        if gym: add(m + "-02", "ORNEK SPOR SALONU ANKARA TR", gym)
        add(m + "-15", "KAHVE DURAGI ANKARA TR", kafe)
        add(m + "-20", "TAKSITLI MAGAZA TR", 500, inst={"n": 1, "m": 6, "total": 3000})
    a = App(b); a.ev("h=>{applyData({history:h});render()}", H)
    a.pg.click("#recurFold > summary")
    rows = a.ev("[...document.querySelectorAll('#recur tbody tr')].map(r=>r.textContent)")
    names = " | ".join(rows)
    assert "NETFLIX" in names and "SPOTIFY" in names and "ORNEK SPOR" in names, rows
    assert "KAHVE" not in names, "değişken tutarlı kahve düzenli sayılmamalı"
    assert "TAKSITLI" not in names, "taksitler dahil edilmemeli"
    net = next(r for r in rows if "NETFLIX" in r); assert "tutar arttı" in net and "yılda" in net, net
    gym = next(r for r in rows if "ORNEK SPOR" in r); assert "son 2 dönemde yok" in gym, gym
    spo = next(r for r in rows if "SPOTIFY" in r); assert "₺60" in spo and "arttı" not in spo, spo
    assert "(2 ·" in a.text("#recurCount"), a.text("#recurCount")
    a.pg.locator("#recur button[data-an]").filter(has_text="SPOTIFY").click(); a.pg.wait_for_timeout(150)
    eq(a.ev("$('q').value"), "spotify", "satır analizi açmalı")
    assert not a.errors, a.errors
    a.close()


@test
def olagandisi_harcamalar(b, info):
    H, i = [], 0
    def add(d, desc, amt, **kw):
        nonlocal i; H.append({"id": f"a{i}", "date": d, "stmt": d[:7] + "-26", "desc": desc, "amt": amt, **kw}); i += 1
    for m in ["2026-05", "2026-06", "2026-07"]:
        add(m + "-03", "ORNEK MARKET ANKARA TR", 400)
    add("2026-08-04", "ORNEK MARKET ANKARA TR", 1500)            # ortalamanın 3,75 katı
    add("2026-08-10", "ORNEK MARKET ANKARA TR", 450)             # normal
    add("2026-08-12", "KAFE ORNEK TR", 180); add("2026-08-12", "KAFE ORNEK TR", 180)  # çift çekim
    add("2026-08-20", "TEK SEFERLIK ALIS TR", 9000)              # geçmişi yok: uyarı yok
    a = App(b); a.ev("h=>{applyData({history:h});render()}", H); a.period("2026-08")
    eq(a.ev("document.querySelector('#anom .anom').open"), False, "uyarılar varsayılan kapalı")
    a.pg.click("#anom summary"); a.pg.wait_for_timeout(100)
    eq(a.ev("document.querySelector('#anom .anom').open"), True, "başlığa tıklayınca açılmalı")
    t = a.text("#anom")
    assert "2 harcama" in t and "Çift çekim" in t and "ORNEK MARKET" in t and "4 katı" in t, t
    assert "TEK SEFERLIK" not in t, t
    a.pg.click("#anom button[data-dismiss^='D|']"); a.pg.wait_for_timeout(150)
    t = a.text("#anom"); assert "1 harcama" in t and "Çift çekim" not in t, t
    eq(a.ev("document.querySelector('#anom .anom').open"), True, "yeniden çizimde açık kalmalı")
    data = json.loads(a.ev("snapshot()"))
    eq(len(data["dismissed"]), 1, "gizlenen uyarı dosyaya yazılmalı")
    a.ev("d=>{applyData(d);render()}", data); a.period("2026-08")
    assert "Çift çekim" not in a.text("#anom"), "yeniden açınca gizli kalmalı"
    a.period("2026-07"); eq(a.text("#anom"), "", "başka dönemde uyarı yok")
    a.ev("h=>{applyData({history:h,rules:'Market: MARKET'});render()}", H)   # eski dosya: yeni alanlar yok
    eq(a.ev("[Object.keys(notes).length,dismissed.size]"), [0, 0], "eski dosya varsayılanlarla açılmalı")
    assert not a.errors, a.errors
    a.close()


@test
def gelecek_taksit_takvimi(b, info):
    H = [{"id": "i1", "date": "2026-08-01", "pdate": "2026-08-01", "stmt": "2026-09-26", "desc": "ORNEK ELEKTRONIK TR", "amt": 500, "inst": {"n": 2, "m": 4, "total": 2000}},
         {"id": "i2", "date": "2026-09-10", "pdate": "2026-09-10", "stmt": "2026-09-26", "desc": "ORNEK GIYIM TR", "amt": 300, "inst": {"n": 1, "m": 2, "total": 600}}]
    a = App(b); a.ev("h=>{applyData({history:h});render()}", H); a.pg.click("#monthsFold > summary")
    rows = a.ev("[...document.querySelectorAll('#instCal .mrow')].map(r=>r.textContent)")
    eq(len(rows), 2, "iki gelecek dönem")
    assert rows[0].startswith("Eki") and "₺800" in rows[0] and "2 taksit" in rows[0] and "1 seri biter" in rows[0], rows
    assert rows[1].startswith("Kas") and "₺500" in rows[1] and "1 seri biter" in rows[1], rows
    assert "Toplam kalan: ₺1.300" in a.text("#instCal")
    a.ev("()=>{applyData({history:[{id:'n1',date:'2026-09-01',stmt:'2026-09-26',desc:'ORNEK MARKET TR',amt:100}]});render()}")
    eq(a.ev("$('instCal').textContent"), "", "taksit yoksa bölüm yok")
    assert not a.errors, a.errors
    a.close()


@test
def kategorisiz_icin_kural_onerisi(b, info):
    a = App(b); a.import_("arti.pdf"); a.pg.click("#unkFold > summary")
    eq(a.ev("document.querySelector('#unk input[data-kw]').value"), "FATURA", "önerilen anahtar kelime (düzenlenebilir)")
    eq(a.ev("getComputedStyle(document.querySelector('#unk .kwsug')).display"), "flex", "öneri satırının stili yüklü olmalı")
    a.pg.select_option("#unk select", "Faturalar"); a.pg.wait_for_timeout(150)
    assert "FATURA" in [l for l in a.ev("$('rules').value").split("\n") if l.startswith("Faturalar:")][0]
    eq(a.ev("Object.keys(overrides).length"), 0, "kural eklenince override gerekmez")
    eq(a.ev("categorize('FATURA ODEME NOKTASI IZMIR TR')"), "Faturalar", "aynı yerin yeni işlemleri de kategorilenir")
    assert "Hepsi kategorilendi" in a.text("#unk")
    # işaret kaldırılırsa yalnızca bu açıklama için seçim yapılır
    a.ev("h=>{history.push(...h);render()}", [{"id": "u1", "date": "2026-08-15", "stmt": "2026-08-26", "desc": "ORNEK YENI YER TR", "amt": 99}])
    a.pg.uncheck("#unk input[data-asrule]"); a.pg.select_option("#unk select", "Faturalar"); a.pg.wait_for_timeout(150)
    eq(a.ev("overrides['ORNEK YENI YER TR']"), "Faturalar", "override olarak kaydedilmeli")
    assert "ORNEK YENI" not in a.ev("$('rules').value")
    assert not a.errors, a.errors
    a.close()


@test
def geri_al(b, info):
    a = App(b); a.import_("arti.pdf"); a.pg.click("#allFold > summary")
    before = a.ev("JSON.stringify({h:history,o:overrides,e:[...excluded]})"); total = a.total()
    a.pg.select_option("#alltx tbody select >> nth=0", "Market"); a.pg.wait_for_timeout(150)
    assert "Market" in a.text("#toast") and a.pg.is_visible("#undoBtn"), a.text("#toast")
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(150)
    eq(a.ev("JSON.stringify({h:history,o:overrides,e:[...excluded]})"), before, "kategori değişikliği geri alınmalı")
    assert "Geri alındı" in a.text("#toast")
    a.pg.on("dialog", lambda d: d.accept())
    n = a.ev("history.length")
    a.pg.locator("#alltx tbody tr").filter(has_text="SHELL").locator("button.x").click(); a.pg.wait_for_timeout(150)
    eq(a.ev("history.length"), n - 1, "silindi")
    a.ev("document.activeElement&&document.activeElement.blur()"); a.pg.keyboard.press("Control+z"); a.pg.wait_for_timeout(150)
    eq(a.ev("history.length"), n, "Ctrl+Z silmeyi geri almalı"); eq(a.total(), total, "toplam aynı")
    a.pg.uncheck("input[data-inc='Akaryakıt']"); a.pg.wait_for_timeout(150)
    assert a.total() != total
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(150); eq(a.total(), total, "dışlama geri alınmalı")
    a.pg.uncheck("input[data-inc='Akaryakıt']"); a.pg.wait_for_timeout(6300)
    eq(a.ev("$('toast').textContent"), "", "bildirim 6 sn sonra kaybolmalı")
    assert not a.errors, a.errors
    a.close()


@test
def islem_notu_ve_etiket(b, info):
    a = App(b); a.import_("arti.pdf"); a.pg.click("#allFold > summary")
    tr = a.pg.locator("#alltx tbody tr").filter(has_text="SHELL")
    tr.locator(".notebtn").click(); a.pg.wait_for_timeout(100)
    a.pg.fill("#alltx input[data-note]", "Yaz tatili yolu #tatil #araba"); a.pg.keyboard.press("Enter"); a.pg.wait_for_timeout(200)
    assert "Yaz tatili yolu" in tr.inner_text(), tr.inner_text()
    n = json.loads(a.ev("snapshot()"))["notes"]; eq(list(n.values()), ["Yaz tatili yolu #tatil #araba"], "not dosyaya yazılmalı")
    chips = a.ev("[...document.querySelectorAll('#tagbar .tagchip')].map(c=>c.textContent)")
    assert len(chips) == 2 and chips[0].startswith("#tatil") and "₺2.000" in chips[0], chips
    a.pg.fill("#txq", "yaz tatili"); a.pg.wait_for_timeout(300)   # not içinde arama
    eq(a.ev("[...document.querySelectorAll('#alltx tbody button[data-an]')].map(b=>b.textContent)"), ["SHELL ORNEK ANKARA TR"], "not aranabilmeli")
    a.pg.fill("#txq", ""); a.pg.wait_for_timeout(300)
    a.pg.click("#tagbar .tagchip >> nth=0"); a.pg.wait_for_timeout(200)
    eq(a.ev("$('txq').value"), "#tatil", "çip aramayı doldurur")
    eq(a.ev("document.querySelectorAll('#alltx tbody button[data-an]').length"), 1, "yalnızca etiketli işlem")
    a.pg.click("#tagbar .tagchip.on"); a.pg.wait_for_timeout(200)
    assert a.ev("document.querySelectorAll('#alltx tbody button[data-an]').length") > 1
    # Esc vazgeçer, boş kaydetmek notu siler, geri al notu döndürür
    tr.locator(".notebtn").click(); a.pg.keyboard.press("Escape"); a.pg.wait_for_timeout(100)
    eq(len(json.loads(a.ev("snapshot()"))["notes"]), 1, "Esc notu değiştirmemeli")
    tr.locator(".notebtn").click(); a.pg.fill("#alltx input[data-note]", ""); a.pg.keyboard.press("Enter"); a.pg.wait_for_timeout(200)
    eq(json.loads(a.ev("snapshot()"))["notes"], {}, "boş not silinir")
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(150)
    eq(len(json.loads(a.ev("snapshot()"))["notes"]), 1, "geri al notu döndürür")
    # yeniden açınca not durur
    data = json.loads(a.ev("snapshot()")); a.ev("d=>{applyData(d);render()}", data)
    assert "Yaz tatili yolu" in a.text("#alltx")
    assert not a.errors, a.errors
    a.close()


@test
def kart_ayrimi(b, info):
    a = App(b)
    a.import_("kart_a.pdf"); assert not a.pg.is_visible("#cardSel"), "tek kartta seçici yok"
    a.import_("kart_b.pdf")
    eq(a.ev("[...new Set(history.map(t=>t.card))].sort()"), ["1234", "5678"], "kartlar okunmalı")
    eq(a.ev("statements['2026-08-26'].card+statements['2026-08-20'].card"), "12345678", "ekstre başına kart")
    assert a.pg.is_visible("#cardSel"), "iki kartta seçici görünmeli"
    a.period("2026-08"); eq(a.total(), "₺2.000", "tüm kartlar")
    a.pg.select_option("#cardSel", "1234"); a.pg.wait_for_timeout(150)
    eq(a.total(), "₺1.500", "yalnızca 1234"); assert "Tutuyor" in a.text("#recon") and a.ev("document.querySelectorAll('#recon details').length") == 1
    a.pg.select_option("#cardSel", "5678"); a.pg.wait_for_timeout(150)
    eq(a.total(), "₺500", "yalnızca 5678"); assert "SINEMA" in a.text("#top") and "MIGROS" not in a.text("#top")
    a.pg.select_option("#cardSel", ""); a.pg.wait_for_timeout(150)
    eq(a.total(), "₺2.000", "tekrar tüm kartlar")
    # eski dosya / kartsız ekstre: seçici çıkmaz
    a.ev("()=>{applyData({history:[{id:'k1',date:'2026-08-01',stmt:'2026-08-26',desc:'ORNEK TR',amt:10}]});render()}")
    assert not a.pg.is_visible("#cardSel")
    assert not a.errors, a.errors
    a.close()


@test
def yazdirma_gorunumu(b, info):
    a = App(b); a.import_("arti.pdf")
    called = a.ev("()=>{window._p=0;window.print=()=>{window._p++};return 0}")
    a.pg.click("#tbPrint"); eq(a.ev("window._p"), 1, "Yazdır düğmesi print çağırmalı")
    a.pg.emulate_media(media="print")
    css = lambda sel, prop: a.ev(f"getComputedStyle(document.querySelector('{sel}')).{prop}")
    eq(css("body", "backgroundColor"), "rgb(255, 255, 255)", "baskıda beyaz zemin")
    eq(css("#toolbar", "display"), "none", "araç çubuğu gizli")
    eq(css("#tabs", "display"), "none", "sekmeler baskıda yok")
    eq(css("#rulesFold", "display"), "none", "kurallar baskıda yok")
    assert css("body", "color") != "rgb(233, 237, 235)", "koyu tema rengi baskıda kalmamalı"
    a.ev("window.dispatchEvent(new Event('beforeprint'))")
    assert a.ev("document.getElementById('monthsFold').open && document.getElementById('allFold').open"), "yazdırırken bölümler açılmalı"
    eq(css(".scroll", "maxHeight"), "none", "liste tam uzunlukta")
    a.ev("window.dispatchEvent(new Event('afterprint'))")
    assert not a.ev("document.getElementById('allFold').open"), "sonra eski durum"
    a.pg.emulate_media(media="screen")
    eq(css("#toolbar", "display") != "none", True, "ekranda görünür")
    assert not a.errors, a.errors
    a.close()


def _rules_app(b):
    a = App(b); a.ev("h=>{applyData({history:h});render()}", _pide_history()); a.pg.click("#rulesFold > summary")
    return a


def _card(a, name):
    row = a.pg.locator(f"#rulesEd .rcard[data-k='{name}'] button.rhead")
    if row.get_attribute("aria-expanded") != "true": row.click(); a.pg.wait_for_timeout(100)


@test
def kural_duzenleyici_ekle_sil(b, info):
    a = _rules_app(b)
    assert a.pg.locator("#rulesEd .rcard").count() >= 10, "kategori kartları listelenmeli"
    eq(a.ev("categorize('ZZYX DUKKANI ANKARA TR')"), "Diğer")
    _card(a, "Market")
    a.pg.fill("input[data-addkey='Market']", "zzyx dukkani, ikinci yer"); a.pg.keyboard.press("Enter"); a.pg.wait_for_timeout(150)
    eq(a.ev("categorize('ZZYX DUKKANI ANKARA TR')"), "Market", "yeni kelime kategoriyi değiştirmeli")
    line = [l for l in a.ev("$('rules').value").split("\n") if l.startswith("Market:")][0]
    assert "ZZYX DUKKANI" in line and "IKINCI YER" in line, line
    assert "ZZYX DUKKANI" in json.loads(a.ev("snapshot()"))["rules"], "dosyaya yazılmalı"
    a.pg.locator("#rulesEd .rcard[data-k='Market'] .kchip").filter(has_text="ZZYX DUKKANI").locator("button.kx").click(); a.pg.wait_for_timeout(150)
    eq(a.ev("categorize('ZZYX DUKKANI ANKARA TR')"), "Diğer", "silince eski hâl")
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(150)
    eq(a.ev("categorize('ZZYX DUKKANI ANKARA TR')"), "Market", "geri al kelimeyi döndürmeli")
    # varsayılan bir kelimeyi silince yeniden açınca geri gelmemeli
    a.pg.locator("#rulesEd .rcard[data-k='Market'] .kchip").filter(has_text="MIGROS").first.locator("button.kx").click(); a.pg.wait_for_timeout(150)
    data = json.loads(a.ev("snapshot()")); assert "Market|MIGROS" in data["removedDefaults"], data["removedDefaults"]
    a.ev("d=>{applyData(d);render()}", data)
    assert "MIGROS" not in [l for l in a.ev("$('rules').value").split("\n") if l.startswith("Market:")][0], "silinen varsayılan geri gelmemeli"
    assert not a.errors, a.errors
    a.close()


@test
def kural_duzenleyici_cakisma_ve_tasi(b, info):
    a = _rules_app(b)
    src = [l for l in a.ev("$('rules').value").split("\n") if "MIGROS" in l][0].split(":")[0]
    _card(a, "Faturalar")
    a.pg.fill("input[data-addkey='Faturalar']", "migros"); a.pg.keyboard.press("Enter"); a.pg.wait_for_timeout(150)
    assert f'"{src}"' in a.text("#rulesEd .rcard[data-k='Faturalar'] .rmsg"), a.text("#rulesEd")
    eq(a.ev("categorize('MIGROS ANKARA TR')"), src, "çakışmada ekleme yapılmamalı")
    a.pg.click("#rulesEd [data-move]"); a.pg.wait_for_timeout(150)
    eq(a.ev("categorize('MIGROS ANKARA TR')"), "Faturalar", "taşınınca yeni kategori")
    assert "MIGROS" not in [l for l in a.ev("$('rules').value").split("\n") if l.startswith(src + ":")][0]
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(150)
    eq(a.ev("categorize('MIGROS ANKARA TR')"), src, "geri al taşımayı geri almalı")
    assert not a.errors, a.errors
    a.close()


@test
def kural_duzenleyici_kategori_yeniden_adlandir_sil(b, info):
    a = _rules_app(b)
    a.ev("()=>{overrides[norm('ORNEK BUTIK')]='Kafe ve restoran';excluded.add('Kafe ve restoran');render()}")
    _card(a, "Kafe ve restoran")
    a.pg.fill("#rulesEd input[data-rename='Kafe ve restoran']", "Yeme içme"); a.pg.keyboard.press("Enter"); a.pg.wait_for_timeout(200)
    eq(a.ev("overrides[norm('ORNEK BUTIK')]"), "Yeme içme", "override değeri güncellenmeli")
    eq(a.ev("[...excluded]"), ["Yeme içme"], "hariç tutulan ad güncellenmeli")
    assert a.ev("$('rules').value").count("Yeme içme:") == 1 and "Kafe ve restoran:" not in a.ev("$('rules').value")
    data = json.loads(a.ev("snapshot()")); assert "Kafe ve restoran|*" in data["removedDefaults"]
    a.ev("d=>{applyData(d);render()}", data)
    assert "Kafe ve restoran:" not in a.ev("$('rules').value"), "eski ad varsayılanlarla geri gelmemeli"
    a.pg.click("#addCat") if False else None
    _card(a, "Yeme içme")
    a.pg.on("dialog", lambda d: d.accept())
    a.pg.locator("#rulesEd .rcard[data-k='Yeme içme'] [data-delcat]").click(); a.pg.wait_for_timeout(200)
    assert "Yeme içme" not in a.ev("$('rules').value"), "kategori silinmeli"
    eq(a.ev("overrides[norm('ORNEK BUTIK')]"), None, "kategoriye bağlı override temizlenmeli")
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(200)
    assert "Yeme içme:" in a.ev("$('rules').value") and a.ev("overrides[norm('ORNEK BUTIK')]") == "Yeme içme", "geri al hepsini döndürmeli"
    # özel ad ve çift ad reddedilir, yeni kategori eklenir
    a.pg.fill("#newCat", "Diğer"); a.pg.click("#addCat"); a.pg.wait_for_timeout(100)
    assert "özel bir kategori" in a.text("#rulesEd"), a.text("#rulesEd")
    a.pg.fill("#newCat", "Hobi"); a.pg.fill("#newKey", "ornekhobi, oyuncak"); a.pg.click("#addCat"); a.pg.wait_for_timeout(200)
    eq(a.ev("categorize('ORNEKHOBI TR')"), "Hobi", "yeni kategori kuralı çalışmalı")
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(150)
    assert "Hobi:" not in a.ev("$('rules').value"), "tek geri al kategoriyi ve kelimeleri birlikte kaldırmalı"
    assert not a.errors, a.errors
    a.close()


@test
def kural_duzenleyici_arama_ve_dene(b, info):
    a = _rules_app(b)
    a.pg.fill("#rq", "migros"); a.pg.wait_for_timeout(150)
    assert 1 <= a.pg.locator("#rulesEd .rcard").count() <= 3, "yalnızca eşleşen kategoriler"
    assert a.pg.is_visible("#rulesEd .kchip.hit"), "eşleşen kelime vurgulanmalı"
    a.pg.fill("#rq", "yokyokyok"); a.pg.wait_for_timeout(150)
    assert "Eşleşen kategori ya da anahtar kelime yok" in a.text("#rulesEd")
    a.pg.fill("#rq", "")
    a.pg.fill("#rtest", "MIGROS ANKARA TR"); a.pg.wait_for_timeout(150)
    t = a.text("#rtestRes"); assert "MIGROS" in t and "eşleşti" in t, t
    a.pg.fill("#rtest", "TAMAMEN BILINMEYEN YER"); a.pg.wait_for_timeout(150)
    assert "Diğer" in a.text("#rtestRes") and "eşleşen anahtar kelime yok" in a.text("#rtestRes")
    a.ev("()=>{overrides[norm('ORNEK BUTIK')]='Giyim';render()}")
    a.pg.fill("#rtest", "ORNEK BUTIK"); a.pg.wait_for_timeout(150)
    assert "Kendi seçiminiz" in a.text("#rtestRes") and "Giyim" in a.text("#rtestRes"), a.text("#rtestRes")
    assert not a.errors, a.errors
    a.close()


@test
def kural_duzenleyici_metin_ve_varsayilan(b, info):
    a = _rules_app(b)
    a.pg.click("#rulesText > summary")
    a.ev("()=>{$('rules').value+='\\nHobi: ORNEKHOBI'}"); a.pg.click("#reapply"); a.pg.wait_for_timeout(200)
    assert a.pg.locator("#rulesEd .rcard[data-k='Hobi']").count() == 1, "metin değişikliği kartlara yansımalı"
    a.pg.locator("#rulesEd .rcard[data-k='Market'] button.rhead").click(); a.pg.wait_for_timeout(100)
    a.pg.locator("#rulesEd .rcard[data-k='Market'] .kchip").first.locator("button.kx").click(); a.pg.wait_for_timeout(150)
    n_before = len(a.ev("$('rules').value")); assert a.ev("removedDefaults.size") == 1
    a.pg.click("#completeDef"); a.pg.wait_for_timeout(200)
    eq(a.ev("removedDefaults.size"), 0, "tamamla, silinen varsayılanları geri getirir")
    assert len(a.ev("$('rules').value")) > n_before and "Hobi: ORNEKHOBI" in a.ev("$('rules').value"), "özel kurallar korunmalı"
    eq(a.ev("[Object.keys(overrides).length, typeof notes, dismissed.size]"), [0, "object", 0])
    # eski dosya (removedDefaults yok) açılır
    a.ev("()=>{applyData({history:[],rules:'Market: MIGROS'});render()}")
    assert "MIGROS" in a.ev("$('rules').value")
    assert not a.errors, a.errors
    a.close()



@test
def ag_kilidi_baglantiya_izin_vermez(b, info):
    a = App(b)
    blocked = a.ev("""async () => {
      const out = [];
      for (const u of ['https://example.com/', 'data:text/plain,x']) {
        try { await fetch(u); out.push('açık'); } catch (e) { out.push('kapalı'); }
      }
      try { const x = new XMLHttpRequest(); x.open('GET', 'https://example.com/', false); x.send(); out.push('açık'); }
      catch (e) { out.push('kapalı'); }
      return out;
    }""")
    eq(blocked, ["kapalı"] * 3, "fetch/XHR engellenmeli")
    a.import_("arti.pdf")  # kilit varken PDF okuma (eval + blob worker) çalışmalı
    assert "₺" in a.total(), a.total()
    a.close()


@test
def pwa_internetsiz_acilir_ve_guncellenir(b, info):
    import shutil
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    root = os.path.abspath(os.path.join(HERE, ".."))
    site = os.path.join(OUT, "site")
    shutil.rmtree(site, ignore_errors=True)
    os.makedirs(site)
    for name in ["index.html", "sw.js", "manifest.webmanifest", "icons"]:
        (shutil.copytree if os.path.isdir(os.path.join(root, name)) else shutil.copy)(os.path.join(root, name), os.path.join(site, name))

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a): pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    ctx = b.new_context()
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    try:
        pg.goto(url)
        pg.evaluate("navigator.serviceWorker.ready")
        pg.reload()
        assert pg.evaluate("!!navigator.serviceWorker.controller"), "sayfa service worker'a bağlanmalı"
        man = pg.evaluate("fetch('manifest.webmanifest').then(r=>r.json()).catch(()=>null)")
        eq(man, None, "sayfanın kendisi manifest'i bile fetch edememeli (ağ kilidi)")

        # İnternet varken yeni sürüm hemen gelir
        html = open(os.path.join(site, "index.html"), encoding="utf-8").read()
        open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(html.replace("<title>Harcama Analizi", "<title>YENİ Harcama Analizi", 1))
        st = os.stat(os.path.join(site, "index.html")); os.utime(os.path.join(site, "index.html"), (st.st_atime, st.st_mtime + 5))  # sunucu saniye çözünürlüklü
        pg.reload()
        assert pg.title().startswith("YENİ"), pg.title()

        # Sunucu kapanınca (internet yok) kayıtlı son sürüm açılır ve PDF okunur
        srv.shutdown(); srv.server_close()
        ctx.set_offline(True)
        pg.reload()
        assert pg.title().startswith("YENİ"), pg.title()
        pg.wait_for_function("window.libsReady && typeof pdfToRows==='function'")
        pg.evaluate("window.libsReady")
        pg.evaluate("document.getElementById('drop').classList.remove('hide')")
        pg.set_input_files("#file", f("arti.pdf"))
        pg.wait_for_function("!document.getElementById('setup').classList.contains('hide')", timeout=20000)

        # Önbellekte yalnızca uygulama dosyaları var
        cached = pg.evaluate("""async () => {
          const out = [];
          for (const k of await caches.keys()) for (const r of await (await caches.open(k)).keys()) out.push(new URL(r.url).pathname);
          return out.sort();
        }""")
        eq(cached, sorted(["/", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png", "/icons/apple-touch-icon.png"]), "önbellek içeriği")
        assert not errors, errors
    finally:
        ctx.close()
        try: srv.shutdown(); srv.server_close()
        except Exception: pass


@test
def ay_sonu_kesim_kaymasi(b, info):
    a = App(b)
    a.import_("kayma_ocak.pdf")
    eq(a.ev("history.filter(t=>t.inst&&t.inst.n===3).map(t=>[periodKey(t),t.est])"), [["2026-02", "future"]], "yalnız Ocak varken 3/6 Şubat'a tahmin edilmeli")
    a.import_("kayma_subat.pdf"); a.import_("kayma_mart.pdf")
    eq(a.ev("history.filter(t=>t.inst&&t.inst.n===3).map(t=>[periodKey(t),!!t.est])"), [["2026-02", False]], "tahmin gerçekle değişmeli, kopya yok")
    opts = a.ev("[...document.querySelectorAll('#period option')].map(o=>o.value).filter(v=>/^\\d{4}-\\d{2}$/.test(v))")
    for m in ["2026-01", "2026-02", "2026-03"]:
        eq(opts.count(m), 1, f"{m} dönemi bir kez")
    assert "Şubat 2026 ekstresi (kesim 01.03.2026)" in a.ev("document.querySelector('#period option[value=\"2026-02\"]').textContent"), a.ev("[...document.querySelectorAll('#period option')].map(o=>o.textContent)")
    for m, v in [("2026-01", "₺1.300"), ("2026-02", "₺1.200"), ("2026-03", "₺1.400")]:
        a.period(m); eq(a.total(), v, f"{m} toplamı")
        eq(a.ev("document.querySelectorAll('#recon details').length"), 1, f"{m} tek ekstre kontrolü")
        assert "Tutuyor" in a.text("#recon"), (m, a.text("#recon"))
    eq(a.ev("history.filter(t=>t.inst).map(t=>[t.inst.n,periodKey(t)]).sort((x,y)=>x[0]-y[0])"),
       [[1, "2025-12"], [2, "2026-01"], [3, "2026-02"], [4, "2026-03"], [5, "2026-04"], [6, "2026-05"]], "her dönemde tek taksit, doğru ay")
    a.period("2026-03")
    eq(a.ev("document.querySelector('#cats .cat[data-k=\"Taksitler\"] .delta')"), None, "Mart taksiti Şubat'la aynı: rozet yok")
    assert not a.errors, a.errors
    a.close()


# ---------------------------------------------------------------- PDF ayrıştırma sınır durumları
def _real_rows(a):
    return a.ev("history.filter(t=>!t.est).map(t=>({d:t.date,desc:t.desc,amt:t.amt,kind:t.kind||'',note:t.note||'',inst:t.inst?t.inst.n+'/'+t.inst.m:''}))")


@test
def pdf_dovizli_islemde_tl_tutar_alinir(b, info):
    a = App(b); a.import_("dovizli.pdf")
    rows = {r["desc"]: r for r in _real_rows(a)}
    eq(sorted(r["amt"] for r in rows.values()), [100, 405, 1012.5, 1620], "TL tutarlar (döviz tutarı değil)")
    eq(sorted(rows), ["AMAZON ORNEK LU", "BOOKING ORNEK NL", "ORNEK MARKET ANKARA TR", "ORNEK YAZILIM IE"], "açıklamada döviz kodu kalmamalı")
    assert "25,00 USD" in rows["AMAZON ORNEK LU"]["note"], rows["AMAZON ORNEK LU"]
    assert "Tutuyor" in _recon(a), _recon(a)
    assert not a.errors, a.errors
    a.close()


@test
def pdf_yilsiz_tarihlerde_yil_kesime_gore_cozulur(b, info):
    a = App(b); a.load("yilsiz_ocak.pdf")
    src = a.text("#stmtSrc"); assert "uyumsuz" not in src and "Dosyadan okundu" in src, src
    a.pg.click("#run"); a.pg.wait_for_timeout(150)
    eq(sorted(r["d"] for r in _real_rows(a)), ["2025-12-28", "2025-12-30", "2026-01-05", "2026-01-12"], "Aralık işlemleri önceki yılda")
    assert "Tutuyor" in _recon(a, "2026-01"), _recon(a, "2026-01")
    a.close()


@test
def pdf_vade_cumlesi_islem_sayilmaz(b, info):
    a = App(b); a.load("vade_cumlesi.pdf")
    src = a.text("#stmtSrc"); assert "uyumsuz" not in src and "Dosyadan okundu" in src, src
    a.pg.click("#run"); a.pg.wait_for_timeout(150)
    rows = _real_rows(a); eq(sorted(r["desc"] for r in rows), ["MIGROS ORNEK", "SHELL ORNEK"], "yalnızca gerçek işlemler")
    eq(sum(r["amt"] for r in rows), 300, "toplam")
    assert "Tutuyor" in _recon(a), _recon(a)
    a.close()


@test
def pdf_isaret_sutunu_silinmez(b, info):
    a = App(b); a.import_("isaret_ba.pdf")
    kinds = {r["desc"]: (r["kind"], r["amt"]) for r in _real_rows(a)}
    eq(kinds["ZARA ORNEK IADE"], ("refund", -50), "A = alacak: iade")
    eq(kinds["HESABINIZDAN ODEME"][0], "payment", "A = alacak: ödeme")
    eq(kinds["MIGROS ORNEK"], ("", 100), "B = borç: harcama")
    assert "Tutuyor" in _recon(a), _recon(a)
    a.close()
    a = App(b); a.import_("isaret_eksi.pdf")
    eq(a.ev("history.filter(t=>t.kind==='refund').length"), 4, "ayrı '-' sütunu iade olarak okunmalı")
    assert "Tutuyor" in _recon(a), _recon(a)
    a.close()


@test
def pdf_saat_kucuk_harfli_ay_ve_taksit_bicimleri(b, info):
    a = App(b); a.import_("kucuk_ayrintilar.pdf")
    rows = _real_rows(a)
    eq(len(rows), 5, "küçük harfli aylı satır da okunmalı")
    descs = [r["desc"] for r in rows if "MIGROS" in r["desc"]]
    eq(descs, ["MIGROS ORNEK ANKARA TR"] * 2, "saat açıklamada kalmamalı")
    eq(a.ev("[...new Set(history.filter(t=>/MIGROS/.test(t.desc)).map(t=>merchantKey(t.desc)))]"), ["migros"], "aynı yer tek yer sayılmalı")
    eq(sorted((r["desc"], r["inst"]) for r in rows if r["inst"]), [("GIYIM ORNEK TR", "2/3"), ("TEKNO ORNEK TR", "2/3")], "(2/3) ve alt satırdaki '2/3 Taksit'")
    assert "(2/3)" not in " ".join(r["desc"] for r in rows)
    eq(a.ev("history.find(t=>t.desc==='KAFE ORNEK ISTANBUL TR').date"), "2026-07-26", "küçük harfli ay")
    assert "Tutuyor" in _recon(a), _recon(a)
    a.close()


# ---------------------------------------------------------------- Grafik altındaki listeden düzenleme
def _liste_app(b):
    H = _pide_history() + [
        {"id": "t1", "date": "2026-08-05", "stmt": "2026-08-26", "desc": "ORNEK ELEKTRONIK TR", "amt": 500, "inst": {"n": 1, "m": 3, "total": 1500}},
        {"id": "r1", "date": "2026-08-06", "stmt": "2026-08-26", "desc": "ORNEK IADE TR", "amt": -100, "kind": "refund"},
        {"id": "u1", "date": "2026-08-07", "stmt": "2026-08-26", "desc": "ZZQ BILINMEYEN YER TR", "amt": 70},
        {"id": "u2", "date": "2026-08-21", "stmt": "2026-08-26", "desc": "ZZQ BILINMEYEN YER ANKARA TR", "amt": 30}]
    a = App(b); a.ev("h=>{applyData({history:h});render()}", H); a.period("2026-08")
    return a


def _ac(a, name):
    row = a.pg.locator(f"#cats .cat[data-k='{name}'] button.row")
    if row.get_attribute("aria-expanded") != "true": row.click(); a.pg.wait_for_timeout(120)


@test
def liste_icinden_kategori_duzenleme(b, info):
    a = _liste_app(b)
    sel = lambda c: a.pg.locator(f"#cats .cat[data-k='{c}'] .catlist .rowcat select")
    # kapalıyken hiçbir seçici yok
    eq(a.ev("document.querySelectorAll('#cats .rowcat').length"), 0, "kapalı listede seçici yok")
    # 1) Kafe: aynı açıklamalı iki satır birlikte taşınır
    _ac(a, "Kafe ve restoran"); eq(sel("Kafe ve restoran").count(), 3, "her satırın altında seçici")
    sel("Kafe ve restoran").nth(0).select_option("Market"); a.pg.wait_for_timeout(200)
    eq(a.ev("overrides[norm('EGE PIDE SALONU ANKARA TR')]"), "Market", "seçim override olarak yazılmalı")
    eq(sel("Kafe ve restoran").count(), 1, "taşınan satırlar Kafe listesinden kalkmalı")
    assert "₺540" in a.text("#cats .cat[data-k='Kafe ve restoran'] button.row") and "₺3.320" in a.text("#cats .cat[data-k='Market'] button.row"), a.text("#cats")
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(200)
    eq(sel("Kafe ve restoran").count(), 3, "Geri al satırları döndürmeli")
    # 2) Taksitler: seçici var, satır Taksitler'de kalır, alt kategori değişir
    _ac(a, "Taksitler"); eq(sel("Taksitler").count(), 1)
    sel("Taksitler").nth(0).select_option("Market"); a.pg.wait_for_timeout(200)
    eq(sel("Taksitler").count(), 1, "taksit satırı Taksitler'de kalmalı")
    eq(a.ev("categorize('ORNEK ELEKTRONIK TR')"), "Market", "alt kategori güncellenmeli")
    eq(sel("Taksitler").nth(0).input_value(), "Market", "seçici yeni alt kategoriyi göstermeli")
    # 3) İadeler: seçici yok
    _ac(a, "İadeler ve indirimler"); eq(sel("İadeler ve indirimler").count(), 0, "iadede seçici olmamalı")
    assert not a.errors, a.errors
    a.close()


@test
def liste_icinden_diger_icin_kural_onerisi(b, info):
    a = _liste_app(b)
    _ac(a, "Diğer")
    blk = a.pg.locator("#cats .cat[data-k='Diğer'] .catlist")
    eq(blk.locator(".kwsug").count(), 2, "iki farklı yer, ikisinde de kural önerisi")
    eq(blk.locator("input[data-kw]").first.input_value(), "ZZQ BİLİNMEYEN", "önerilen anahtar kelime")
    assert blk.locator("input[data-asrule]").first.is_checked(), "varsayılan işaretli"
    blk.locator("select").first.select_option("Market"); a.pg.wait_for_timeout(200)
    assert "ZZQ BİLİNMEYEN" in [l for l in a.ev("$('rules').value").split("\n") if l.startswith("Market:")][0], "kural eklenmeli"
    eq(a.ev("categorize('ZZQ BILINMEYEN YER ANKARA TR')"), "Market", "aynı yerin diğer işlemi de kategorilenir")
    eq(a.ev("Object.keys(overrides).filter(k=>/ZZQ/.test(k)).length"), 0, "kural varken override gerekmez")
    assert a.pg.locator("#cats .cat[data-k='Diğer']").count() == 0, "Diğer boşalınca satır kalkmalı"
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(200)
    eq(a.ev("categorize('ZZQ BILINMEYEN YER ANKARA TR')"), "Diğer", "Geri al kuralı kaldırmalı")
    # işaret kaldırılırsa yalnızca bu açıklama için seçim
    _ac(a, "Diğer"); blk = a.pg.locator("#cats .cat[data-k='Diğer'] .catlist")
    blk.locator("input[data-asrule]").first.uncheck(); blk.locator("select").first.select_option("Market"); a.pg.wait_for_timeout(200)
    eq(a.ev("categorize('ZZQ BILINMEYEN YER ANKARA TR')"), "Diğer", "öbür açıklama etkilenmemeli")
    assert a.ev("Object.keys(overrides).some(k=>/ZZQ BILINMEYEN YER TR/.test(k))"), "override yazılmalı"
    assert not a.errors, a.errors
    a.close()


# ---------------------------------------------------------------- yıllık özet ve kategori trendleri
def _yil_app(b):
    """2025-07…2025-12 ve 2026-01…2026-09 dönemleri; iki kart (Kafe 2026 satırları 5678'de)."""
    H, i = [], 0
    def add(m, desc, amt, card="1234", **kw):
        nonlocal i; H.append({"id": f"y{i}", "date": m + "-10", "stmt": m + "-26", "desc": desc, "amt": amt, "card": card, **kw}); i += 1
    for m in ["2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12"]:
        add(m, "MİGROS ANKARA TR", 1000)
    for m in ["2025-07", "2025-08", "2025-09"]:
        add(m, "ORNEK KAFE TR", 200)
    for k in range(1, 10):
        add(f"2026-{k:02d}", "MİGROS ANKARA TR", 1500)
    for m in ["2026-07", "2026-08", "2026-09"]:
        add(m, "ORNEK KAFE TR", 300, card="5678")
    add("2026-03", "FAIZ TUTARI", 120); add("2026-03", "BSMV", 18)
    add("2026-05", "ORNEK ELEKTRONIK TEKNOSA", 6000)
    add("2026-06", "ORNEK IADE TR", -250, kind="refund")
    add("2026-09", "ORNEK MOBILYA IKEA", 400, inst={"n": 1, "m": 2, "total": 800})   # 2/2 gelecekte: sayılmaz
    a = App(b); a.ev("h=>{applyData({history:h});render()}", H)
    return a


@test
def yillik_ozet(b, info):
    a = _yil_app(b)
    eq(a.ev("$('yearFold').open"), False, "varsayılan kapalı")
    eq(a.text("#yearCount"), "(2 yıl)", "başlıkta yıl sayısı")
    a.pg.click("#yearFold > summary"); a.pg.wait_for_timeout(100)
    eq(a.ev("document.querySelector('#yearSum select').value"), "2026", "varsayılan son yıl")
    t = a.text("#yearSum")
    for s in ["₺20.688", "9 dönem", "₺2.299", "₺7.500", "₺1.250", "ORNEK ELEKTRONIK TEKNOSA", "₺6.000", "₺138", "₺400", "₺250", "₺5.800", "▲ %61"]:
        assert s in t, f"{s!r} yıllık özette yok:\n{t}"
    eq(a.total(), "₺27.288", "tüm zamanlar = 2025 (6.600) + 2026 (20.688)")
    # kategori tablosu: Market dönem başına 1.500, geçen yıl 1.000 → ▲ %50; Kafe dönem başına aynı (100) → rozet yok
    rows = a.pg.locator("#yearSum tr[data-k='Market']")
    eq(rows.count(), 1, "Market satırı")
    rt = rows.inner_text(); assert "₺13.500" in rt and "▲ %50" in rt, rt
    assert "▲" not in a.pg.locator("#yearSum tr[data-k='Kafe ve restoran']").inner_text()
    eq(a.pg.locator("#yearSum tr[data-k='İadeler ve indirimler']").count(), 0, "iadeler kategori tablosunda değil")
    # en çok harcanan yerler: 5 yer, ilki MİGROS; tıklayınca analiz bir kez açılır
    eq(a.pg.locator("#yearSum .ytop [data-an]").count(), 5, "5 yer")
    a.ev("()=>{window.__an=0;const o=openAnalysis;window.openAnalysis=d=>{window.__an++;o(d)}}")
    a.pg.locator("#yearSum .ytop [data-an]").first.click(); a.pg.wait_for_timeout(150)
    eq(a.ev("window.__an"), 1, "analiz tek sefer açılmalı"); eq(a.ev("$('q').value"), "migros", "analiz MİGROS için")
    # yıl değişince
    a.pg.select_option("#yearSum select", "2025"); a.pg.wait_for_timeout(100)
    t = a.text("#yearSum"); assert "₺6.600" in t and "6 dönem" in t and "₺1.100" in t, t
    assert "aynı dönemleri" not in t, "önceki yıl yoksa karşılaştırma yok"
    eq(a.ev("$('yearFold').open"), True, "yeniden çizimde açık kalmalı")
    # kategori çıkarma ve kart süzgeci
    a.pg.select_option("#yearSum select", "2026"); a.ev("()=>{excluded.add('Elektronik');render()}")
    t = a.text("#yearSum"); assert "₺14.688" in t and "Elektronik" in t and "dahil değil" in t, t
    a.ev("()=>{excluded.clear();render()}")
    a.pg.select_option("#cardSel", "5678"); a.pg.wait_for_timeout(100)
    assert "₺900" in a.text("#yearSum"), a.text("#yearSum")
    a.close()


@test
def kategori_trendleri(b, info):
    a = _yil_app(b)
    eq(a.ev("$('trendFold').open"), False, "varsayılan kapalı")
    eq(a.text("#trendCount"), "(5 kategori)", "başlıkta kategori sayısı")
    a.pg.click("#trendFold > summary"); a.pg.wait_for_timeout(100)
    eq(a.ev("[...document.querySelectorAll('#trends .trend')].map(e=>e.dataset.k)"),
       ["Market", "Elektronik", "Kafe ve restoran", "Taksitler", "Faiz ve ücretler"], "pencere toplamına göre sıra, iadeler yok")
    m = "#trends .trend[data-k='Market']"
    eq(a.pg.locator(m + " .tbars span").count(), 12, "son 12 dönem")
    eq(a.pg.locator("#trends .trend[data-k='Kafe ve restoran'] .tbars span").count(), 12, "boş dönemler de çubuk")
    mt = a.text(m); assert "₺16.500" in mt and "₺1.375" in mt and "%9" in mt, mt
    assert "₺1.500" in a.ev(f"document.querySelector(\"{m} .tbars span:last-child\").title")
    a.period("2026-05")
    eq(a.pg.locator(m + " .tbars span").count(), 11, "pencere seçili dönemde biter")
    assert a.ev(f"document.querySelector(\"{m} .tbars span:last-child\").classList.contains('on')"), "seçili dönem vurgulu"
    a.ev("()=>{excluded.add('Elektronik');render()}")
    eq(a.pg.locator("#trends .trend[data-k='Elektronik']").count(), 0, "çıkarılan kategori yok")
    eq(a.ev("$('trendFold').open"), True, "yeniden çizimde açık kalmalı")
    a.close()


# ---------------------------------------------------------------- Birikim ve bütçe
def _butce_app(b, budget=True):
    """2026-06…09 MİGROS 1.500/dönem; Eylül'de kartla ödenen aidat 750 ve 2 taksitlik IKEA (2/2 Ekim'de planlı)."""
    H = [{"id": f"m{i}", "date": m + "-10", "stmt": m + "-26", "desc": "MİGROS ANKARA TR", "amt": 1500}
         for i, m in enumerate(["2026-06", "2026-07", "2026-08", "2026-09"])]
    H += [{"id": "a1", "date": "2026-09-05", "stmt": "2026-09-26", "desc": "ORNEK SITE AIDAT", "amt": 750},
          {"id": "t1", "date": "2026-09-26", "stmt": "2026-09-26", "pdate": "2026-09-03", "desc": "ORNEK MOBILYA IKEA", "amt": 400,
           "inst": {"n": 1, "m": 2, "total": 800}}]
    B = {"items": [
        {"id": "i1", "kind": "income", "name": "Maaş", "amts": [{"from": "2026-01", "v": 40000}, {"from": "2026-08", "v": 45000}]},
        {"id": "e1", "kind": "expense", "name": "Kira", "amts": [{"from": "2026-01", "v": 15000}]},
        {"id": "e2", "kind": "expense", "name": "Aidat", "amts": [{"from": "2026-01", "v": 750}], "card": True}]}
    a = App(b)
    a.ev("([h,bd])=>{applyData(bd?{history:h,budget:bd}:{history:h});render()}", [H, B if budget else None])
    return a


def _row(a, m):
    return a.pg.locator(f"#budget tr[data-m='{m}']").inner_text()


@test
def birikim_gelir_gider_kalan(b, info):
    a = _butce_app(b)
    assert a.pg.is_visible("#tabs") and a.pg.is_visible("#out") and not a.pg.is_visible("#budget")
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    assert not a.pg.is_visible("#out") and a.pg.is_visible("#budget"), "sekme değişmeli"
    eq(a.ev("$('bMonth').value"), "2026-09", "varsayılan: son ekstreli dönem")
    # Eylül: 45.000 − 15.000 (kira; aidat kartla ödendiği için düşülmez) − 2.650 (1.500 + 750 + 400)
    eq(a.text("#bLeft"), "₺27.350", "Eylül kalanı")
    for s in ["₺45.000", "₺15.000", "₺2.650", "₺750 kartla ödenen"]:
        assert s in a.text("#budget .hero"), s
    assert "₺23.500" in _row(a, "2026-07"), "Temmuz: eski maaş 40.000"
    assert "₺29.600" in _row(a, "2026-10") and "fut" in a.ev("document.querySelector(\"#budget tr[data-m='2026-10']\").className"), "Ekim tahmini"
    assert "–" in _row(a, "2026-03"), "ekstresiz ay"
    a.pg.click("#budget tr[data-m='2026-10']"); a.pg.wait_for_timeout(100)
    assert "henüz yok" in a.text("#bStatus") and "₺400" in a.text("#bStatus"), a.text("#bStatus")
    a.pg.select_option("#bMonth", "2026-09"); a.pg.wait_for_timeout(100)
    # Kira Eylül'den itibaren 17.500: Eylül değişir, Temmuz değişmez
    a.pg.click("[data-item='e1'] .bihead"); a.pg.wait_for_timeout(100)
    a.pg.fill("[data-item='e1'] [data-newamt]", "17.500"); a.pg.click("[data-item='e1'] [data-setamt]"); a.pg.wait_for_timeout(150)
    eq(a.text("#bLeft"), "₺24.850", "zam sonrası Eylül"); assert "₺23.500" in _row(a, "2026-07"), "Temmuz aynı kalmalı"
    eq(a.ev("budget.items.find(i=>i.id==='e1').amts.length"), 2, "tutar geçmişi")
    # Aidat kart dışı yapılınca ikinci kez düşülür ve ekstrede geçtiği hatırlatılır
    a.pg.click("[data-item='e2'] .bihead"); a.pg.wait_for_timeout(100)
    a.pg.uncheck("[data-item='e2'] [data-card]"); a.pg.wait_for_timeout(150)
    eq(a.text("#bLeft"), "₺24.100", "aidat kart dışı")
    assert "ORNEK SITE AIDAT" in a.text("[data-item='e2'] .bhint"), "çift sayım ipucu"
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(150)
    eq(a.text("#bLeft"), "₺24.850", "geri al"); eq(a.pg.locator("[data-item='e2'] .bhint").count(), 0)
    # Çıkarılan kategori kart harcamasından düşer
    a.ev("()=>{excluded.add('Market');render()}")
    eq(a.text("#bLeft"), "₺26.350", "Market çıkarılınca"); assert "Market" in a.text("#budget") and "dahil değil" in a.text("#budget")
    a.ev("()=>{excluded.clear();render()}")
    # Kart harcaması kartı Harcamalar sekmesinde o dönemi açar
    a.pg.select_option("#bMonth", "2026-08"); a.pg.click("#bCardKpi"); a.pg.wait_for_timeout(150)
    assert a.pg.is_visible("#out") and not a.pg.is_visible("#budget"); eq(a.ev("$('period').value"), "2026-08", "dönem")
    # Harcamalar'da "Gelirden kalan" kartı ve geri dönüş
    a.period("2026-09")
    k = a.text("#kpis"); assert "Gelirden kalan" in k and "₺24.850" in k, k
    a.pg.click("#kpiLeft"); a.pg.wait_for_timeout(150)
    assert a.pg.is_visible("#budget"); eq(a.ev("$('bMonth').value"), "2026-09", "Birikim sekmesi o ayla açılır")
    a.close()


@test
def birikim_varliklar_ve_kur(b, info):
    a = _butce_app(b, budget=False)   # bütçesiz eski dosya hatasız açılır
    eq(a.ev("JSON.stringify(budget)"), '{"items":[],"assets":[],"rates":{}}', "boş bütçe")
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    def add(name, typ, qty):
        a.pg.fill("#aName", name); a.pg.select_option("#aType", typ); a.pg.fill("#aQty", qty); a.pg.click("#aAdd"); a.pg.wait_for_timeout(120)
    add("Vadeli hesap", "TRY", "50.000"); add("Dolar", "USD", "1.000"); add("Bilezik", "GAU", "10")
    eq(a.text("#aTotal"), "₺50.000", "kursuz varlıklar toplama katılmaz")
    m = a.text("#aMissing"); assert "Dolar" in m and "Gram altın" in m, m
    a.pg.fill("#rate-USD", "41,50"); a.pg.press("#rate-USD", "Enter"); a.pg.wait_for_timeout(120)
    a.pg.fill("#rate-GAU", "4.200"); a.pg.press("#rate-GAU", "Enter"); a.pg.wait_for_timeout(120)
    eq(a.text("#aTotal"), "₺133.500", "50.000 + 41.500 + 42.000")
    eq(a.pg.locator("#aMissing").count(), 0)
    eq(a.ev("budget.rates.USD"), {"v": 41.5, "date": "2026-09-28"}, "kur ve tarihi")
    usd = a.ev("budget.assets.find(x=>x.type==='USD').id")
    a.pg.fill(f"[data-asset='{usd}'] [data-qty]", "1.500"); a.pg.press(f"[data-asset='{usd}'] [data-qty]", "Enter"); a.pg.wait_for_timeout(120)
    eq(a.text("#aTotal"), "₺154.250", "miktar düzenleme")
    answers = [False, True]
    a.pg.on("dialog", lambda d: d.accept() if answers.pop(0) else d.dismiss())
    gau = a.ev("budget.assets.find(x=>x.type==='GAU').id")
    a.pg.click(f"[data-asset='{gau}'] [data-del]"); a.pg.wait_for_timeout(100); eq(a.text("#aTotal"), "₺154.250", "vazgeçince kalır")
    a.pg.click(f"[data-asset='{gau}'] [data-del]"); a.pg.wait_for_timeout(120); eq(a.text("#aTotal"), "₺112.250", "silindi")
    assert "Birikim yeter" in a.text("#budget .hero"), "birikim / ortalama gider"
    snap = json.loads(a.ev("snapshot()"))
    eq(len(snap["budget"]["assets"]), 2, "dosyada birikimler"); eq(snap["budget"]["rates"]["USD"]["v"], 41.5)
    assert "budget" not in json.loads(a.ev("shareSnapshot()")), "kategori paylaşımına bütçe girmez"
    eq(a.ev("localStorage.length+sessionStorage.length"), 0, "tarayıcıda saklanmaz")
    a.close()


@test
def birikim_ekstresiz_telefonda(b, info):
    a = App(b, width=390, mobile=True)
    assert not a.pg.is_visible("#tabs"), "kayıt açılmadan sekme yok"
    a.pg.click("#fresh"); a.pg.wait_for_timeout(100)
    assert a.pg.is_visible("#tabs"), "kayıt açılınca ekstresiz de sekme var"
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    assert not a.pg.is_visible("#drop") and not a.pg.is_visible("#mobilePanel")
    a.pg.fill("#iName", "Maaş"); a.pg.fill("#iAmt", "45.000"); a.pg.click("#iAdd"); a.pg.wait_for_timeout(120)
    a.pg.fill("#eName", "Kira"); a.pg.fill("#eAmt", "15000"); a.pg.click("#eAdd"); a.pg.wait_for_timeout(120)
    eq(a.text("#bLeft"), "₺30.000", "gelir − kira")
    a.pg.fill("#eName", ""); a.pg.click("#eAdd"); a.pg.wait_for_timeout(100)
    assert "ad ve sıfırdan" in a.text("#budget").lower() or "Bir ad" in a.text("#budget"), "boş form uyarısı"
    assert a.pg.is_visible("#saveBar"), "kaydet çubuğu görünmeli"
    with a.pg.expect_download() as d:
        a.pg.click("#dl")
    path = os.path.join(OUT, "butce.json"); d.value.save_as(path)
    a.pg.reload(); a.pg.wait_for_function("window.libsReady"); a.pg.set_input_files("#openData", path); a.pg.wait_for_timeout(200)
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    eq(a.text("#bLeft"), "₺30.000", "tekrar açınca bütçe yerinde")
    a.close()


# ---------------------------------------------------------------- Vadesiz hesap özeti (Birikim sekmesi)
SUGS = "bView.bank.sugs.map(s=>[s.type,s.kind,s.name,s.amts.at(-1).v,s.amts[0].from,s.on])"
BEKLENEN = [["new", "income", "Maaş", 45000, "2026-07", True], ["new", "expense", "Kira", 15000, "2026-07", True],
            ["new", "expense", "BES", 1500, "2026-07", True], ["new", "expense", "Aidat", 750, "2026-07", True]]


def _bank(a, name):
    a.ev("bView.bank=null")
    a.pg.set_input_files("#bankFile", f(name))
    a.pg.wait_for_function("bView.bank&&!bView.bank.busy", timeout=20000)
    a.pg.wait_for_timeout(100)


@test
def hesap_ozeti_duzenli_kalemleri_onerir(b, info):
    a = _butce_app(b, budget=False)
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    hist = a.ev("JSON.stringify(history)")
    _bank(a, "hesap_isaretli.pdf")
    eq(a.ev(SUGS), BEKLENEN, "öneriler: maaş, kira, aidat; kart ödemesi ve tek seferlikler yok")
    t = a.text("#bankInfo"); assert "20 hareket" in t and "3 kredi kartı ödemesi (₺24.650) atlandı" in t and "kaydedilmedi" in t, t
    eq(a.ev("budget.items.length"), 0, "Ekle'den önce bütçe değişmez")
    a.pg.uncheck("[data-sug='expense|AIDAT SITE YONETIMI'] [data-on]")
    a.pg.uncheck("[data-sug='expense|BES'] [data-on]")
    a.pg.fill("[data-sug='expense|AYSE KIRA ORNEKOGLU'] [data-name]", "Ev kirası")
    a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    eq(a.ev("budget.items.map(i=>[i.kind,i.name,i.amts,i.src])"),
       [["income", "Maaş", [{"from": "2026-07", "v": 45000}], "MAAS ORNEK YAZILIM"],
        ["expense", "Ev kirası", [{"from": "2026-07", "v": 15000}], "AYSE KIRA ORNEKOGLU"]], "seçilenler eklendi")
    eq(a.text("#bLeft"), "₺27.350", "Eylül: 45.000 − 15.000 − 2.650")
    eq(a.ev("JSON.stringify(history)"), hist, "kart geçmişine hesap hareketi girmez")
    snap = a.ev("snapshot()")
    assert "KREDI KARTI ODEMESI" not in snap and "HAVALE GELEN" not in snap, "hesap hareketleri dosyaya yazılmaz"
    assert "Hesap özetinden 2 kalem" in a.text("#bankMsg") or "2 kalem" in a.text("#bankMsg")
    a.pg.click("#undoBtn"); a.pg.wait_for_timeout(150)
    eq(a.ev("budget.items.length"), 0, "geri al")
    # tekrar: hepsini ekle, sonra aynı özet yeni öneri getirmez
    _bank(a, "hesap_isaretli.pdf"); a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    eq(a.ev("budget.items.length"), 4)
    _bank(a, "hesap_isaretli.pdf")
    eq(a.ev("bView.bank.sugs.length"), 0, "kayıtlı kalemler tekrar önerilmez")
    assert "bulunamadı" in a.text("#bankPrev")
    a.pg.click("#bankCancel"); a.pg.wait_for_timeout(100)
    eq(a.pg.locator("#bankPrev").count(), 0)
    eq(a.ev("localStorage.length+sessionStorage.length"), 0)
    a.close()


@test
def hesap_ozeti_isaret_bakiyeden_ve_csv(b, info):
    a = _butce_app(b, budget=False)
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    for name in ["hesap_bakiye.pdf", "hesap_borc_alacak.csv"]:
        _bank(a, name)
        eq(a.ev(SUGS), BEKLENEN, f"{name}: öneriler")
        eq(a.ev("[bView.bank.n,bView.bank.unk,bView.bank.cardN]"), [20, 0, 3], f"{name}: tüm satırların yönü bulundu")
    a.pg.click("#bankCancel"); a.pg.wait_for_timeout(100)
    eq(a.ev("budget.items.length"), 0, "vazgeçince bir şey değişmez")
    assert "değişmedi" in a.text("#bankMsg")
    a.close()


@test
def hesap_ozeti_tutar_degisikligi(b, info):
    a = _butce_app(b)   # Maaş, Kira 15.000, Aidat 750 kayıtlı
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    _bank(a, "hesap_zam.pdf")
    eq(a.ev("bView.bank.sugs.map(s=>[s.type,s.name,s.itemName,s.from,s.amts.at(-1).v,s.cur])"),
       [["new", "BES", None, None, 1500, None], ["change", "Kira", "Kira", "2026-09", 17500, 15000]], "BES yeni; kira (açıklaması da değişen) tek öneri")
    assert "Kayıtlı ₺15.000" in a.text("#bankPrev")
    a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    eq(a.ev("budget.items.find(i=>i.id==='e1').amts"), [{"from": "2026-01", "v": 15000}, {"from": "2026-09", "v": 17500}], "Eylül'den yeni tutar")
    # Eylül: 45.000 − 17.500 (kira) − 1.500 (yeni BES) − 2.650 (kart); aidat kartla ödendiği için düşülmez
    eq(a.text("#bLeft"), "₺23.350", "Eylül kalanı"); assert "₺22.000" in _row(a, "2026-07"), "Temmuz: kira eski tutarda (40.000 − 15.000 − 1.500 − 1.500)"
    _bank(a, "hesap_zam.pdf"); eq(a.ev("bView.bank.sugs.length"), 0, "artık güncel")


@test
def hesap_ozeti_benzer_aciklamalar_birlesir(b, info):
    a = _butce_app(b, budget=False)
    rows = [{"date": f"2026-0{m}-08", "desc": d, "amt": v} for m in (7, 8, 9) for d, v in
            [("FATURA ODEMESI ENERJISA " + str(m), -900), ("FATURA ODEMESI IGDAS", -400), ("SGK PRIM ODEMESI", -2000)]]
    rows.append({"date": "2026-08-12", "desc": "DIGER SGK PRIM", "amt": -2000})   # aynı ay: toplanır
    got = a.ev("r=>detectFixedFromBank(r).sugs.map(s=>[s.key,s.name,s.amts.map(x=>[x.from,x.v])])", rows)
    eq(got, [["PRIM SGK", "SGK Prim", [["2026-07", 2000]]],   # Ağustos'taki ikinci ödeme aylık tutarı ikiye katlamaz
             ["ENERJISA", "Enerjisa", [["2026-07", 900]]], ["IGDAS", "Igdas", [["2026-07", 400]]]],
       "farklı kurumlar ayrı, aynı kurumun farklı yazılışı tek")
    # eski sürümün sıralı anahtarıyla kayıtlı kira tekrar önerilmez
    a.ev("()=>{budget.items=[{id:'k',kind:'expense',name:'Ev',amts:[{from:'2026-07',v:15000}],to:'',card:false,src:'AYSE ORNEKOGLU KIRA'}];render()}")
    got = a.ev("r=>detectFixedFromBank(r).sugs.map(s=>s.key)", [{"date": f"2026-0{m}-03", "desc": "EFT GIDEN AYSE ORNEKOGLU KIRA", "amt": -15000} for m in (7, 8)])
    eq(got, [], "eski src ile eşleşir")
    a.close()
    a.close()



@test
def hesap_ozeti_hareketleri_gosterir_ve_ayirir(b, info):
    a = _butce_app(b, budget=False)
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    _bank(a, "hesap_isaretli.pdf")
    bes = "[data-sug='expense|BES']"
    assert "Tem 26 ₺1.500 · Ağu 26 ₺1.500 · Eyl 26 ₺1.500" in a.text(bes), a.text(bes)
    a.pg.click(bes + " .bdet summary"); a.pg.wait_for_timeout(100)
    t = a.text(bes + " .bdet")
    assert "DIGER DIGER BES ODEMESI 1234" in t and "FATURA ODEMESI DIGER BES 5678" in t and "₺1.500,00" in t and "01.07.2026" not in t, t
    eq(a.pg.locator(bes + " .bdet .brow").count(), 3, "BES'in 3 hareketi")
    # bir hareketi çıkarınca aylar yeniden hesaplanır ve açık liste kapanmaz
    a.pg.uncheck(bes + " .brow[data-row='2'] [data-inc]"); a.pg.wait_for_timeout(100)
    eq(a.ev("bView.bank.sugs.find(s=>s.key==='BES').months"), ["2026-07", "2026-08"], "Eylül çıkarıldı")
    eq(a.ev("document.querySelector(\"[data-sug='expense|BES'] .bdet\").open"), True, "liste açık kalır")
    # kira iki yazılışlı: EYLUL KIRASI ayrı kalem yapılır
    kira = "[data-sug='expense|AYSE KIRA ORNEKOGLU']"
    a.pg.click(kira + " .bdet summary"); a.pg.wait_for_timeout(100)
    assert "2 farklı yazılış" in a.text(kira), a.text(kira)
    a.pg.click(kira + " [data-split='AYSE KIRASI ORNEKOGLU']"); a.pg.wait_for_timeout(100)
    eq(a.ev("bView.bank.sugs.filter(s=>s.kind==='expense').map(s=>[s.key,s.months.length,s.on])"),
       [["AYSE KIRA ORNEKOGLU", 2, True], ["AYSE KIRASI ORNEKOGLU", 1, False], ["BES", 2, True], ["AIDAT SITE YONETIMI", 3, True]], "ayrılan yazılış ayrı öneri")
    a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    eq(a.ev("budget.items.map(i=>[i.name,i.amts.length])"), [["Maaş", 1], ["Kira", 1], ["BES", 1], ["Aidat", 1]], "işaretsiz ayrılan eklenmez")
    a.close()


@test
def hesap_ozeti_onerilmeyenler_listelenir_ve_eklenir(b, info):
    a = _butce_app(b, budget=False)
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    assert a.ev("$('bankBox').compareDocumentPosition($('bMonth'))&Node.DOCUMENT_POSITION_FOLLOWING"), "kutu ay seçicinin üstünde"
    _bank(a, "hesap_isaretli.pdf")
    eq(a.ev("bView.bank.rest.reduce((n,g)=>n+g.rows.length,0)"), 8, "önerilmeyen 8 hareket")
    a.pg.click("#bankRest > summary"); a.pg.wait_for_timeout(100)
    t = a.text("#bankRest")
    for s in ["Önerilmeyen 8 hareket", "ORNEK MARKET ANKARA", "FAST GIDEN 77123 MEHMET ORNEK", "−₺5.000,00", "HAVALE GELEN ORNEK KISI", "+₺2.500,00",
              "ATM PARA CEKME", "ORNEK KAFE", "küçük tutar", "kredi kartı ödemesi", "tek seferlik"]:
        assert s in t, f"{s!r} listede yok:\n{t}"
    a.pg.fill("#restQ", "havale"); a.pg.wait_for_timeout(100)
    eq(a.pg.locator("#bankRest .brow").count(), 1, "arama süzer")
    a.pg.click("#bankRest [data-promote]"); a.pg.wait_for_timeout(100)
    eq(a.ev("bView.bank.sugs.filter(s=>s.kind==='income').map(s=>[s.name,s.on,s.amts.at(-1).v])"), [["Maaş", True, 45000], ["Ornek Kisi", True, 2500]], "öneriye taşındı")
    eq(a.ev("bView.bank.rest.reduce((n,g)=>n+g.rows.length,0)"), 7, "listeden kalktı")
    a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    assert ["income", "Ornek Kisi"] in a.ev("budget.items.map(i=>[i.kind,i.name])"), a.ev("budget.items.map(i=>i.name)")
    snap = a.ev("snapshot()"); assert "ATM PARA CEKME" not in snap and "ORNEK MARKET" not in snap, "hareketler kaydedilmez"
    a.close()


@test
def hesap_ozeti_yon_bakiyeden_ve_elle(b, info):
    a = _butce_app(b, budget=False)
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    for name in ["hesap_gelen_fast.pdf", "hesap_gelen_fast.csv"]:
        _bank(a, name)
        eq(a.ev(SUGS), [["new", "income", "Ornek Kisi", 3000, "2026-08", True]], f"{name}: gelen para gelir")
    a.pg.click("[data-sug='income|KISI ORNEK'] [data-flip]"); a.pg.wait_for_timeout(100)
    eq(a.ev("bView.bank.sugs.map(s=>s.kind)"), ["expense"], "elle gidere çevrildi")
    assert a.pg.locator("[data-sug='expense|KISI ORNEK']").count() == 1
    a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    eq(a.ev("budget.items.map(i=>[i.kind,i.name])"), [["expense", "Ornek Kisi"]], "seçilen yönde eklendi")
    a.close()


@test
def birikim_suzgec(b, info):
    a = _butce_app(b)
    a.ev("()=>{budget.items.push({id:'s1',kind:'expense',name:'Spor salonu',amts:[{from:'2026-01',v:600}],to:'',card:false});render()}")
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    left = a.text("#bLeft")
    _bank(a, "hesap_isaretli.pdf")
    a.pg.click("#bFilter > summary"); a.pg.click("#bankRest > summary"); a.pg.wait_for_timeout(100)
    rest = lambda: a.text("#bankRest")
    # yön = gider
    a.pg.click("#bFilter [data-dir='expense']"); a.pg.wait_for_timeout(100)
    eq(a.pg.locator("#iAdd").count(), 0, "sabit gelirler gizli"); assert a.pg.locator("#eAdd").count() == 1
    eq(a.ev("[...document.querySelectorAll('#bankBox [data-sug]')].map(e=>e.dataset.sug.split('|')[0])"), ["expense"], "önerilerde gelir yok")
    eq(a.pg.locator("#bankRest .bsign.in").count(), 0, "önerilmeyenlerde gelen yok")
    assert "Süzgeç (1)" in a.text("#bFilter > summary")
    a.pg.click("#bfClear"); a.pg.wait_for_timeout(100)
    # tutar en az 1.000
    a.pg.fill("#bfMin", "1.000"); a.pg.press("#bfMin", "Enter"); a.pg.wait_for_timeout(100)
    eq(a.ev("[...document.querySelectorAll('[data-item]')].map(e=>e.dataset.item)"), ["i1", "e1"], "Aidat ve Spor salonu gizli")
    assert "1 / 3 gösteriliyor" in a.text("#budget"), a.text("#budget")
    assert "ORNEK MARKET" not in rest() and "ORNEK KAFE" not in rest() and "ATM PARA" in rest()
    eq(a.text("#bLeft"), left, "kalan süzgeçten etkilenmez")
    a.pg.click("#bfClear"); a.pg.wait_for_timeout(100)
    # tür çipleri
    assert "KREDI KARTI ODEMESI" in rest()
    a.pg.click("#bFilter [data-type='cardpay']"); a.pg.wait_for_timeout(100)
    assert "KREDI KARTI ODEMESI" not in rest(), rest()
    a.pg.click("#bFilter [data-type='iCard']"); a.pg.wait_for_timeout(100)
    eq(a.pg.locator("[data-item='e2']").count(), 0, "kartla ödenen aidat gizli")
    a.pg.click("#bfClear"); a.pg.wait_for_timeout(100)
    # ay
    a.pg.select_option("#bfRange", "2026-08"); a.pg.wait_for_timeout(100)
    dates = a.ev("[...document.querySelectorAll('#bankRest .brow')].map(e=>e.innerText.match(/\\d\\d\\.(\\d\\d)\\.2026/)[1])")
    assert dates and set(dates) == {"08"}, dates
    eq(a.pg.locator("#budget tr[data-m]").count(), 1, "tabloda tek ay")
    a.pg.select_option("#bfRange", "3"); a.pg.wait_for_timeout(100)
    eq(a.ev("[...document.querySelectorAll('#budget tr[data-m]')].map(e=>e.dataset.m)"), ["2026-07", "2026-08", "2026-09"], "son 3 ay")
    a.pg.click("#bfClear"); a.pg.wait_for_timeout(100)
    assert a.pg.locator("#budget tr[data-m]").count() > 3 and a.pg.locator("[data-item]").count() == 4, "temizle hepsini geri getirir"
    # süzgeçle gizlenen işaretli öneri eklenmez
    a.pg.click("#bFilter [data-dir='income']"); a.pg.wait_for_timeout(100)
    assert "gizlenen 1 işaretli öneri" in a.text("#bankHidden"), a.text("#bankBox")
    a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    eq(a.ev("budget.items.length"), 4, "gizli BES eklenmedi")
    eq(sorted(json.loads(a.ev("snapshot()"))["budget"].keys()), ["assets", "items", "rates"], "süzgeç dosyaya yazılmaz")
    a.close()


@test
def hesap_ozeti_kesim_donemi_baslangic_ve_kalem_listesi(b, info):
    a = _butce_app(b, budget=False)   # ekstreler her ayın 26'sında kesiliyor
    rows = [{"date": d, "desc": "EFT GIDEN ORNEK EV SAHIBI KIRA", "amt": -15000} for d in ("2026-07-28", "2026-08-28", "2026-09-28")]
    rows += [{"date": d, "desc": "SITE AIDAT", "amt": -750} for d in ("2026-07-20", "2026-08-20", "2026-09-20")]
    got = a.ev("r=>detectFixedFromBank(r).sugs.map(s=>[s.name,s.months])", rows)
    eq(got, [["Kira", ["2026-08", "2026-09", "2026-10"]], ["Aidat", ["2026-07", "2026-08", "2026-09"]]],
       "kesimden (26) sonraki ödeme sonraki ekstre dönemine")
    a.close()
    # ekstre yoksa takvim ayı
    a = App(b)
    eq(a.ev("r=>detectFixedFromBank(r).sugs.map(s=>s.months[0])", rows), ["2026-07", "2026-07"], "ekstresiz: takvim ayı")
    a.close()
    # önizlemede başlangıç ayı, kalemde başlangıç ayı değiştirme
    a = _butce_app(b, budget=False)
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    _bank(a, "hesap_isaretli.pdf")
    a.pg.fill("[data-sug='expense|AYSE KIRA ORNEKOGLU'] [data-from]", "2026-05")
    a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    kira = a.ev("budget.items.find(i=>i.name==='Kira').id")
    eq(a.ev(f"budget.items.find(i=>i.id==='{kira}').amts"), [{"from": "2026-05", "v": 15000}], "seçilen başlangıç")
    a.pg.click(f"[data-item='{kira}'] .bihead"); a.pg.wait_for_timeout(100)
    a.pg.fill(f"[data-item='{kira}'] [data-start]", "2026-08"); a.pg.press(f"[data-item='{kira}'] [data-start]", "Tab"); a.pg.wait_for_timeout(150)
    eq(a.ev(f"budget.items.find(i=>i.id==='{kira}').amts"), [{"from": "2026-08", "v": 15000}], "kalemde başlangıç değişti")
    # Gelir / Sabit giderler kartı kalemleri listeler; etkin olmayanlar ayrıca yazar
    a.pg.select_option("#bMonth", "2026-07"); a.pg.wait_for_timeout(100)
    a.pg.click("#bFixed"); a.pg.wait_for_timeout(100)
    t = a.text("#bKpiList")
    assert "Temmuz 2026 · sabit giderler" in t and "Aidat" in t and "₺750" in t and "Bu ay etkin değil: Kira (Ağustos 2026 başından)" in t, t
    a.pg.click("#bIncome"); a.pg.wait_for_timeout(100)
    t = a.text("#bKpiList"); assert "gelirler" in t and "Maaş" in t and "₺45.000" in t, t
    a.pg.click("#bKpiList [data-kitem] button"); a.pg.wait_for_timeout(100)
    eq(a.pg.locator("#bKpiList").count(), 0, "kaleme gidince liste kapanır")
    assert a.ev("bView.open.has(budget.items.find(i=>i.name==='Maaş').id)"), "Maaş ayrıntısı açıldı"
    # süzgeçte tek ay seçmek özet ayını da değiştirir
    a.pg.click("#bFilter > summary"); a.pg.select_option("#bfRange", "2026-09"); a.pg.wait_for_timeout(100)
    eq(a.ev("$('bMonth').value"), "2026-09", "süzgeç ayı = özet ayı")
    a.close()


@test
def hesap_ozeti_ayni_doneme_iki_odeme_ve_tarihler(b, info):
    a = _butce_app(b, budget=False)   # kesim her ayın 26'sı
    R = lambda d, desc, v: {"date": d, "desc": desc, "amt": v}
    rows = [R("2026-07-25", "MAAS ODEMESI ORNEK AS", 45000), R("2026-08-27", "MAAS ODEMESI ORNEK AS", 45000), R("2026-09-25", "MAAS ODEMESI ORNEK AS", 45000)]
    rows += [R(f"2026-0{m}-05", "SITE AIDAT", -v) for m, v in ((7, 750), (8, 750), (9, 900))]
    rows += [R(f"2026-0{m}-10", "ORNEK SPOR KULUBU", -v) for m, v in ((7, 600), (8, 1800), (9, 600))]
    got = a.ev("r=>Object.fromEntries(detectFixedFromBank(r).sugs.map(s=>[s.name,[s.regular,s.amts.map(x=>[x.from,x.v]),s.per['2026-09']]]))", rows)
    # maaş kesimden sonra yattığı için Eylül döneminde iki maaş var: aylık tutar yine 45.000, Eylül toplamı 90.000 olarak gösterilir
    eq(got["Maaş"], [True, [["2026-07", 45000]], 90000], "aynı döneme düşen iki ödeme aylık tutarı ikiye katlamaz")
    eq(got["Aidat"], [True, [["2026-07", 750], ["2026-09", 900]], 900], "kalıcı değişiklik tutar geçmişine girer")
    eq(got["Ornek Spor Kulubu"], [True, [["2026-07", 600]], 600], "tek seferlik sıçrama tutar geçmişine girmez")
    # arayüz: dönemde iki ödeme yazar; eklenen kalemde ödeme tarihleri görünür ve dosyada kalır
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    a.ev("r=>{bView.bank={...detectFixedFromBank(r),n:r.length,unk:0,errs:[],files:['x'],ms:[]};renderBudget()}", rows)
    assert "Eyl 26 ₺90.000 (2 ödeme)" in a.text("[data-sug='income|MAAS ORNEK']"), a.text("[data-sug='income|MAAS ORNEK']")
    a.pg.click("#bankApply"); a.pg.wait_for_timeout(150)
    a.ev("()=>{applyData(JSON.parse(snapshot()));render()}")
    a.pg.select_option("#bMonth", "2026-09"); a.pg.wait_for_timeout(100)
    eq(a.text("#bIncome b"), "₺45.000", "Eylül geliri bir maaş")
    a.pg.click("#bIncome"); a.pg.wait_for_timeout(100)
    t = a.text("#bKpiList")
    assert "27.08.2026" in t and "25.09.2026" in t and "MAAS ODEMESI ORNEK AS" in t and "25.07.2026" not in t, t
    mid = a.ev("budget.items.find(i=>i.name==='Maaş').id")
    eq(len(a.ev(f"budget.items.find(i=>i.id==='{mid}').seen")), 3, "kalemin ödemeleri tarihleriyle dosyada")
    a.pg.click(f"#bKpiList [data-kitem='{mid}'] button"); a.pg.wait_for_timeout(200)
    a.pg.click(f"[data-item='{mid}'] .bdet > summary"); a.pg.wait_for_timeout(100)
    t = a.text(f"[data-item='{mid}']"); assert "Hesap özetindeki 3 ödeme" in t and "25.07.2026" in t, t
    a.close()


@test
def hesap_ozeti_bakiye_once_yazilmis(b, info):
    a = _butce_app(b, budget=False)
    a.pg.click("#tabBudget"); a.pg.wait_for_timeout(100)
    _bank(a, "hesap_bakiye_once.pdf")
    eq(a.ev(SUGS), BEKLENEN, "Bakiye sütunu Tutar'dan önce: tutar ve yön yine doğru")
    eq(a.ev("[bView.bank.n,bView.bank.unk]"), [20, 0])
    a.close()


@test
def hesap_ozeti_eski_kayit_onarimi_ve_kendi_hesap(b, info):
    a = _butce_app(b, budget=False)
    items = [{"id": "m", "kind": "income", "name": "Maaş", "src": "MAAS ORNEK", "amts": [{"from": "2026-07", "v": 45000}, {"from": "2026-09", "v": 90000}, {"from": "2026-10", "v": 45000}]},
             {"id": "k", "kind": "expense", "name": "Kira", "src": "KIRA", "amts": [{"from": "2026-07", "v": 15000}, {"from": "2026-09", "v": 30000}]},
             {"id": "z", "kind": "expense", "name": "Aidat", "src": "AIDAT", "amts": [{"from": "2026-07", "v": 750}, {"from": "2026-09", "v": 900}]},
             {"id": "e", "kind": "income", "name": "Elle", "amts": [{"from": "2026-07", "v": 1000}, {"from": "2026-09", "v": 2000}]}]
    got = a.ev("it=>{applyData({history:[],budget:{items:it}});return Object.fromEntries(budget.items.map(i=>[i.id,i.amts.map(x=>x.v)]))}", items)
    eq(got, {"m": [45000], "k": [15000], "z": [750, 900], "e": [1000, 2000]}, "eski sürümün iki katı tutarları atılır; gerçek değişiklik ve elle girilen kalır")
    rows = [{"date": f"2026-0{m}-15", "desc": "VIRMAN KENDI HESABIMA", "amt": 10000} for m in (7, 8, 9)]
    eq(a.ev("r=>detectFixedFromBank(r).sugs.map(s=>[s.own,s.on])", rows), [[True, False]], "kendi hesaplar arası aktarım işaretsiz")
    a.close()

# ----------------------------------------------------------------
def main():
    only = sys.argv[1:] and sys.argv[1]
    print("Sentetik PDF'ler üretiliyor…")
    info = fixtures.build_all()
    selected = [t for t in TESTS if not only or only in t.__name__]
    ok = 0
    with sync_playwright() as p:
        b = getattr(p, os.environ.get("BROWSER", "chromium")).launch()
        for t in selected:
            try:
                t(b, info); ok += 1; print(f"  GEÇTİ  {t.__name__}")
            except Exception as e:
                print(f"  HATA   {t.__name__}: {e}")
                if os.environ.get("VERBOSE"): traceback.print_exc()
        b.close()
    print(f"\n{ok}/{len(selected)} test geçti.")
    sys.exit(0 if ok == len(selected) else 1)


if __name__ == "__main__":
    main()
