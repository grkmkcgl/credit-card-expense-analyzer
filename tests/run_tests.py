"""index.html için uçtan uca testler (Playwright + Chromium, sentetik PDF'lerle).

Kurulum:   pip install playwright reportlab pypdf && python -m playwright install chromium
Çalıştır:  python tests/run_tests.py            (hepsi)
           python tests/run_tests.py taksit     (adında "taksit" geçen testler)

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
    t = a.text("#anom")
    assert "2 harcama" in t and "Çift çekim" in t and "ORNEK MARKET" in t and "4 katı" in t, t
    assert "TEK SEFERLIK" not in t, t
    a.pg.click("#anom button[data-dismiss^='D|']"); a.pg.wait_for_timeout(150)
    t = a.text("#anom"); assert "1 harcama" in t and "Çift çekim" not in t, t
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
