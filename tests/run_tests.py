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
    desc = a.pg.locator("#alltx tr").first.locator("button[data-an]").inner_text()
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
    n = a.ev("$('alltx').rows.length")
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


# ----------------------------------------------------------------
def main():
    only = sys.argv[1:] and sys.argv[1]
    print("Sentetik PDF'ler üretiliyor…")
    info = fixtures.build_all()
    selected = [t for t in TESTS if not only or only in t.__name__]
    ok = 0
    with sync_playwright() as p:
        b = p.chromium.launch()
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
