"""Sentetik ekstre PDF'leri üretir. Gerçek kişisel veri İÇERMEZ; tüm isimler ve tutarlar uydurmadır.

Her fonksiyon tests/out/ altına bir PDF yazar. Beklenen sonuçlar run_tests.py içindedir.
Çalıştırma:  python tests/fixtures.py   (run_tests.py bunu kendisi de çağırır)
"""
import glob
import os
import random

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

# Türkçe harfleri (ş, ğ, İ, ı) içeren bir yazı tipi gerekir.
FONT_CANDIDATES = [
    os.environ.get("TEST_FONT", ""),
    *glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True),
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
_font = next((f for f in FONT_CANDIDATES if f and os.path.exists(f)), None)
if not _font:
    raise SystemExit("Türkçe karakter destekli bir TTF bulunamadı. TEST_FONT=/yol/font.ttf ile belirtin.")
pdfmetrics.registerFont(TTFont("D", _font))

AY = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def p(name):
    return os.path.join(OUT, name)


def tr(v):
    s = f"{v:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def rows_pdf(name, rows, header=None, size=(700, 842), font=8):
    """rows: (tarih, açıklama, tutar) — tutar sağa hizalı."""
    c = canvas.Canvas(p(name), pagesize=size)
    c.setFont("D", font)
    y = size[1] - 30
    if header:
        c.drawString(40, y, header)
        y -= 30
    for d, desc, a in rows:
        c.drawString(40, y, d)
        c.drawString(130, y, desc)
        if a:
            c.drawRightString(size[0] - 60, y, a)
        y -= 14
    c.save()


# 1) 3 sayfa, 143 işlem: harf harf satırlar, sağa hizalı tutar, taksit sütunu, iki satıra taşan açıklama
def big():
    random.seed(1)
    M = ["MARKET A ANKARA TR", "OTOPARK B ISTANBUL TR", "SHELL ORNEK ANKARA TR", "FATURA ODEME MERKEZI TR", "OTEL ORNEK BOLU TR",
         "YEMEKSEPETİ İSTANBUL TR", "TRENDYOL.COM İSTANBUL TR", "NETFLIX.COM AMSTERDAM NL", "A101 YENİ MAĞAZACILIK ANKARA TR", "ECZANE ŞİFA ANKARA TR"]
    c = canvas.Canvas(p("buyuk.pdf"))
    exp, n = [], 0
    for page in range(3):
        c.setFont("D", 8)
        y = 810
        c.drawString(30, y, "HESAP ÖZETİ  Hesap Kesim Tarihi 30 Temmuz 2026  Son Ödeme Tarihi 10 Ağustos 2026"); y -= 12
        c.drawString(30, y, "Dönem Borcu 45.678,90 TL   Asgari Ödeme 18.271,56 TL   Sayfa %d/3" % (page + 1)); y -= 20
        c.drawString(30, y, "İşlem Tarihi"); c.drawString(120, y, "Açıklama"); c.drawString(420, y, "Taksit"); c.drawRightString(560, y, "Tutar (TL)"); y -= 14
        while y > 60:
            d = random.randint(1, 30); mo = random.choice([6, 7]); desc = random.choice(M); v = round(random.uniform(20, 9000), 2)
            if n % 17 == 0:
                v = -round(random.uniform(1000, 5000), 2); desc = "ÖDEME - TEŞEKKÜRLER"
            style = n % 5
            date = f"{d} {AY[mo]} 2026" if style != 3 else f"{d:02d}.{mo:02d}.2026"
            if style == 1:
                x = 30
                for ch in date:
                    c.drawString(x, y, ch); x += pdfmetrics.stringWidth(ch, "D", 8)
                x = 120
                for ch in desc:
                    c.drawString(x, y, ch); x += pdfmetrics.stringWidth(ch, "D", 8)
            else:
                c.drawString(30, y, date); c.drawString(120, y, desc)
            if style == 2:
                c.drawString(420, y, "2/6")
            c.drawRightString(560, y, tr(v))
            if style == 4:
                y -= 10; c.drawString(120, y, "MAĞAZA NO 1234 ŞUBE KODU")
            exp.append(v); n += 1; y -= 13
        c.showPage()
    c.save()
    return {"count": len(exp), "spend": round(sum(v for v in exp if v > 0), 2)}


# 2) Taksit biçimleri + kenarda döndürülmüş ve harf harf dikey yazı
def installments_and_vertical():
    c = canvas.Canvas(p("taksit.pdf"), pagesize=(700, 842)); c.setFont("D", 8)
    c.drawString(40, 810, "Hesap Kesim Tarihi 30 Temmuz 2026 Son Ödeme Tarihi 10 Ağustos 2026 Dönem Borcu 12.345,67 TL")
    y = [780]

    def row(d, desc, amt, extra=None):
        c.drawString(40, y[0], d); c.drawString(130, y[0], desc)
        if amt: c.drawRightString(640, y[0], amt)
        y[0] -= 14
        if extra:
            c.drawString(130, y[0], extra[0])
            if extra[1]: c.drawRightString(640, y[0], extra[1])
            y[0] -= 14
    row("26 Temmuz 2026", "OTOPARK B ISTANBUL TR", "360,00")
    row("26 Temmuz 2026", "OTEL ORNEK BOLU TR", "160,00")
    row("27 Temmuz 2026", "TEKNOSA ANKARA TR 4.964,93 TL'lik işlemin 2 / 3 taksidi", "1.654,98")
    row("28 Temmuz 2026", "MEDIAMARKT ANKARA TR", None, ("9.000,00 TL'lik işlemin 3 / 6 taksidi", "1.500,00"))
    row("28 Temmuz 2026", "KOTON ANKARA TR", "800,00", ("2.400,00 TL'lik işlemin 1 / 3 taksidi", None))
    row("29 Temmuz 2026", "SHELL ORNEK ANKARA TR", "2.000,00")
    row("29 Temmuz 2026", "YEMEKSEPETİ İSTANBUL TR", "389,50")
    c.drawString(130, y[0], "IKEA ANKARA TR 6.000,00 TL'lik işlemin 4 / 12 taksidi"); c.drawRightString(640, y[0], "500,00"); y[0] -= 14
    row("30 Temmuz 2026", "BOYNER 1.200,00 TL'lik işlemin 2 / 2 taksidi", None)
    row("30 Temmuz 2026", "MİGROS KADIKÖY İSTANBUL TR", "1.245,90")
    c.saveState(); c.translate(20, y[0] + 14 * 6); c.rotate(90); c.setFont("D", 6)
    c.drawString(0, 0, "Bu belge elektronik imzalıdır. Mersis No 0123456789 Tutar 99,99"); c.restoreState()
    c.setFont("D", 6); yy = y[0] + 14 * 9
    for ch in "BANKA A.Ş. SİCİL 123456,78":
        if ch != " ": c.drawString(675, yy, ch)
        yy -= 6.5
    c.save()


# 3) Aynı 6 taksitli alışveriş (Mart) ve 3 taksitli ikinci alışveriş, Nisan–Eylül ekstreleri
def installment_series():
    for mo in range(4, 10):
        rows = [("15 Mart 2026", f"MEDIAMARKT ANKARA TR 6.000,00 TL'lik işlemin {mo - 3} / 6 taksidi", "1.000,00")]
        if 6 <= mo <= 8:
            rows.append(("02 Mayıs 2026", f"KOTON ANKARA TR {mo - 5}/3", "300,00"))
        rows.append((f"10 {AY[mo]} 2026", "MİGROS ANKARA TR", "500,00"))
        rows_pdf(f"ekstre{mo}.pdf", rows, header=f"Hesap Kesim Tarihi 28 {AY[mo]} 2026   Son Ödeme Tarihi 8 Ekim 2026   Dönem Borcu 9.999,99 TL")


# 4) Kesim günü 26: geç işlenen harcamalar sonraki ekstreye aittir
def statement_periods():
    rows_pdf("k_temmuz.pdf", [("28 Haziran 2026", "MİGROS ANKARA TR", "100,00"), ("15 Temmuz 2026", "OPET ANKARA TR", "200,00"), ("26 Temmuz 2026", "A101 ANKARA TR", "300,00"),
             ("15 Mart 2026", "MEDIAMARKT ANKARA TR 6.000,00 TL'lik işlemin 4 / 6 taksidi", "1.000,00"), ("20 Temmuz 2026", "HESAPTAN ÖDEME", "+5.000,00")],
             header="Hesap Kesim Tarihi 26 Temmuz 2026   Son Ödeme Tarihi 5 Ağustos 2026   Dönem Borcu 9.999,99 TL")
    rows_pdf("k_agustos.pdf", [("27 Temmuz 2026", "YEMEKSEPETİ İSTANBUL TR", "40,00"), ("30 Temmuz 2026", "SHELL ANKARA TR", "50,00"), ("20 Ağustos 2026", "MİGROS ANKARA TR", "60,00"),
             ("15 Mart 2026", "MEDIAMARKT ANKARA TR 6.000,00 TL'lik işlemin 5 / 6 taksidi", "1.000,00"), ("10 Ağustos 2026", "HESAPTAN ÖDEME", "+3.000,00")],
             header="Hesap Kesim Tarihi 26 Ağustos 2026   Son Ödeme Tarihi 5 Eylül 2026   Dönem Borcu 9.999,99 TL")


# 5) Kesim tarihi 6 farklı düzende (hepsi 26.08.2026; son ödeme 05.09.2026 ile karışmamalı)
def cut_date_layouts():
    TX = [("27 Temmuz 2026", "YEMEKSEPETİ İSTANBUL TR", "40,00"), ("20 Ağustos 2026", "MİGROS ANKARA TR", "60,00"),
          ("15 Mart 2026", "MEDIAMARKT ANKARA TR 6.000,00 TL'lik işlemin 5 / 6 taksidi", "1.000,00")]

    def body(c, y=700):
        c.setFont("D", 8)
        for d, desc, a in TX:
            c.drawString(40, y, d); c.drawString(130, y, desc); c.drawRightString(640, y, a); y -= 14

    def charwise(c, x, y, text):
        for ch in text:
            c.drawString(x, y, ch); x += pdfmetrics.stringWidth(ch, "D", 8) + 1.5

    def A(c):
        c.setFont("D", 8); c.drawString(40, 800, "Hesap Kesim Tarihi 26 Ağustos 2026   Son Ödeme Tarihi 5 Eylül 2026")

    def B(c):
        c.setFont("D", 8)
        for x, t in [(40, "Son Ödeme Tarihi"), (200, "Hesap Kesim Tarihi"), (380, "Dönem Borcu"), (520, "Asgari Ödeme")]: c.drawString(x, 800, t)
        for x, t in [(40, "05.09.2026"), (200, "26.08.2026"), (380, "12.345,67"), (520, "4.938,27")]: c.drawString(x, 786, t)

    def C(c):
        c.setFont("D", 8); c.drawString(40, 800, "Ekstre Kesim Tarihi:"); c.drawString(40, 786, "26/08/2026")
        c.drawString(300, 800, "Son Ödeme Tarihi:"); c.drawString(300, 786, "05/09/2026")

    def D(c):
        c.setFont("D", 8); charwise(c, 40, 800, "HESAP KESİM TARİHİ"); c.drawString(200, 800, ":"); c.drawString(210, 800, "26.08.2026")
        charwise(c, 330, 800, "SON ÖDEME TARİHİ"); c.drawString(470, 800, "05.09.2026")

    def E(c):
        c.setFont("D", 8); c.drawString(40, 800, "Ekstre Dönemi: 27.07.2026 - 26.08.2026     Son Ödeme: 05.09.2026")

    def F(c):
        c.setFont("D", 8); c.drawString(40, 800, "Kredi Kartı Hesap Özeti     Son Ödeme 05.09.2026")

    for k, f in {"A_ayni_satir": A, "B_tablo": B, "C_alt_satir": C, "D_harf_aralikli": D, "E_donem": E, "F_etiket_yok": F}.items():
        c = canvas.Canvas(p(f"kes_{k}.pdf"), pagesize=(700, 842)); f(c); body(c); c.save()


# 6) Ekstre kontrolü: önceki borç, ödeme, iade, faiz/BSMV, geç işlenen harcama
def reconciliation():
    TX = [("25 Temmuz 2026", "MİGROS ANKARA TR", "100,00"), ("30 Temmuz 2026", "SHELL ANKARA TR", "50,00"), ("05 Ağustos 2026", "HESAPTAN ÖDEME", "+4.200,00"),
          ("12 Ağustos 2026", "ZARA İADE", "+300,00"), ("20 Ağustos 2026", "YEMEKSEPETİ İSTANBUL TR", "40,00"),
          ("15 Mart 2026", "MEDIAMARKT ANKARA TR 6.000,00 TL'lik işlemin 5 / 6 taksidi", "1.000,00"), ("26 Ağustos 2026", "FAİZ", "45,10"), ("26 Ağustos 2026", "BSMV", "6,77")]

    def mk(name, due, table=True, extra=None, prev=True):
        c = canvas.Canvas(p(name), pagesize=(700, 842)); c.setFont("D", 8)
        if table:
            c.drawString(40, 810, "Hesap Kesim Tarihi"); c.drawString(170, 810, "Son Ödeme Tarihi")
            if prev: c.drawString(300, 810, "Önceki Dönem Borcu")
            c.drawString(430, 810, "Dönem Borcu"); c.drawString(540, 810, "Asgari Ödeme Tutarı")
            c.drawString(40, 796, "26.08.2026"); c.drawString(170, 796, "05.09.2026")
            if prev: c.drawString(300, 796, "4.200,00 TL")
            c.drawString(430, 796, due + " TL"); c.drawString(540, 796, "376,75 TL")
        else:
            c.drawString(40, 810, f"Hesap Kesim Tarihi 26 Ağustos 2026  Son Ödeme Tarihi 5 Eylül 2026  Dönem Borcu {due} TL  Asgari Ödeme 376,75 TL")
        y = 760
        for d, desc, a in TX:
            c.drawString(40, y, d); c.drawString(130, y, desc); c.drawRightString(640, y, a); y -= 14
        if extra:
            c.drawString(130, y, extra[0]); c.drawRightString(640, y, extra[1])
        c.save()
    mk("r_tutuyor.pdf", "941,87")
    mk("r_fark.pdf", "1.091,87", extra=("KART ÜCRETİ", "150,00"))
    mk("r_oncekiyok.pdf", "941,87", table=False, prev=False)


# 7) Gerçek bir ekstrenin DÜZENİ (isimler/tutarlar uydurma): puan sütunu, çok tutarlı taksit satırı,
#    "+" iadeler, puan kullanımı, ekstre sonunda puan detayı bölümü (ayrık ve yapışık iki yazılış)
def real_layout():
    R = [("01 Ağustos 2026", "YURT İÇI VE YURT DIŞI RESTORANLARDA %5 İ", "+25,00", ""), ("01 Ağustos 2026", "TOPLU TASIMA UCRETI ESKISEHIR TR", "42,00", ""),
         ("01 Ağustos 2026", "KAFE ORNEK ESKISEHIR TR", "910,00", ""), ("01 Ağustos 2026", "TAKSI ORNEK İSTANBUL TR", "177,60", ""),
         ("01 Ağustos 2026", "PASTANE ORNEK ESKİŞEHİR TR", "500,00", "10"), ("02 Ağustos 2026", "KARACA ANKARA TR", "800,99", ""),
         ("02 Ağustos 2026", "SÜPERMARKET ORNEK ANKARA TR", "20,93", ""), ("03 Ağustos 2026", "YURT İÇI VE YURT DIŞI RESTORANLARDA %5 İ", "+3,78", ""),
         ("03 Ağustos 2026", "YEMEKHANE ORNEK ANKARA TR", "75,60", ""), ("03 Ağustos 2026", "MİGROS ORNEK ANKARAANKARA TR", "181,50", ""),
         ("07 Ağustos 2026", "MİGROS ORNEK ANKARAANKARA TR", "760,90", "2"), ("15 Ağustos 2026", "ORNEK LOJISTIK PETROL KONYA TR", "2.100,00", "84"),
         ("16 Ağustos 2026", "BİM BIM-O001 ORNEK ANKARA TR", "291,00", "1"), ("17 Ağustos 2026", "BAŞKENT DOĞALGAZ", "31,00", ""),
         ("18 Ağustos 2026", "WORLDPUAN KULLANIMI", "+50,00", ""),
         ("04 Mart 2026", "SIGORTA ORNEK ISTANBUL TR", "1.624,27", "6.497,08 / 4", "16.242,70 TL'lik işlemin 6 / 10 taksidi"),
         ("10 Haziran 2026", "SEYAHAT ORNEK ISTANBUL TR", "20.902,46", "62.707,38 / 3", "125.414,73 TL'lik işlemin 3 / 6 taksidi")]
    pos = [42, 910, 177.60, 500, 800.99, 20.93, 75.60, 181.50, 760.90, 2100, 291, 31, 1624.27, 20902.46]
    due = round(sum(pos) - 25 - 3.78 - 50, 2)

    def mk(name, section):
        c = canvas.Canvas(p(name), pagesize=(700, 842)); c.setFont("D", 7.5)
        c.drawString(40, 810, "Hesap Kesim Tarihi"); c.drawString(170, 810, "Son Ödeme Tarihi"); c.drawString(430, 810, "Dönem Borcu")
        c.drawString(40, 797, "26.08.2026"); c.drawString(170, 797, "05.09.2026"); c.drawString(430, 797, tr(due) + " TL")
        c.drawString(40, 770, "İşlem Tarihi"); c.drawString(120, 770, "Açıklama"); c.drawRightString(520, 770, "Tutar"); c.drawRightString(640, 770, "Bonus/Taksit")
        y = 755
        for r in R:
            c.drawString(40, y, r[0]); c.drawString(120, y, r[1]); c.drawRightString(520, y, r[2])
            if r[3]: c.drawRightString(640, y, r[3])
            y -= 12
            if len(r) > 4:
                c.drawString(120, y, r[4]); y -= 12
        y -= 20
        if section == "glued":
            c.drawString(40, y, "WORLDPUAN DETAYI Bu Ay Kazanılan/Kullanılan Worldpuan Detaylarınız İşlem Tarihi İşlem Türü Worldpuan Karşılığı Son Kullanım Tarihi"); y -= 12
            c.drawString(40, y, "26 Ağustos 2026 DÖNEM İÇİ ALIŞVERİŞLERDEN KAZANILAN WORLDPUAN 3.775 37,75 31.12.2028"); y -= 12
            c.drawString(40, y, "18 Ağustos 2026 KULLANILAN WORLDPUAN -5.000 50,00")
        elif section == "split":
            c.setFont("D", 9); c.drawString(40, y, "WORLDPUAN DETAYI"); y -= 13; c.setFont("D", 7.5)
            c.drawString(40, y, "Bu Ay Kazanılan/Kullanılan Worldpuan Detaylarınız"); y -= 12
            for x, t in [(40, "İşlem Tarihi"), (120, "İşlem Türü"), (380, "Worldpuan"), (460, "Karşılığı"), (560, "Son Kullanım Tarihi")]: c.drawString(x, y, t)
            y -= 12
            for d, t, w, k, e in [("26.08.2026", "DÖNEM İÇİ ALIŞVERİŞLERDEN KAZANILAN WORLDPUAN", "3.775", "37,75", "31.12.2028"), ("18.08.2026", "KULLANILAN WORLDPUAN", "-5.000", "50,00", "")]:
                c.drawString(40, y, d); c.drawString(120, y, t); c.drawString(380, y, w); c.drawString(460, y, k); c.drawString(560, y, e); y -= 12
        c.save()
    mk("gercek_duzen.pdf", None)
    mk("wp_ayri.pdf", "split")
    mk("wp_yapisik.pdf", "glued")
    return {"due": due}


# 8) "+" ödemeler ve iade
def plus_payments():
    rows_pdf("arti.pdf", [("26 Temmuz 2026", "OTOPARK B ISTANBUL TR", "360,00"), ("27 Temmuz 2026", "HESAPTAN ÖDEME", "+5.000,00"),
             ("27 Temmuz 2026", "TEKNOSA ANKARA TR 4.964,93 TL'lik işlemin 2 / 3 taksidi", "1.654,98"), ("28 Temmuz 2026", "ÖDEME - TEŞEKKÜRLER", "+2.500,00"),
             ("29 Temmuz 2026", "SHELL ORNEK ANKARA TR", "2.000,00"), ("29 Temmuz 2026", "FATURA ODEME MERKEZI TR", "792,00"), ("30 Temmuz 2026", "ZARA İADE", "+300,00")])


# 8b) İki ayrı kart (maskeli numara farklı yazılışlarda), aynı ayda farklı kesim tarihleri
def two_cards():
    rows_pdf("kart_a.pdf", [("02 Ağustos 2026", "MİGROS ANKARA TR", "1.000,00"), ("09 Ağustos 2026", "SHELL ORNEK ANKARA TR", "500,00")],
             header="Kart No: 4543 12** **** 1234   Hesap Kesim Tarihi 26 Ağustos 2026   Dönem Borcu 1.500,00 TL")
    rows_pdf("kart_b.pdf", [("03 Ağustos 2026", "SINEMA ORNEK ISTANBUL TR", "300,00"), ("12 Ağustos 2026", "KAFE ORNEK ISTANBUL TR", "200,00")],
             header="**** **** **** 5678   Hesap Kesim Tarihi 20 Ağustos 2026   Dönem Borcu 500,00 TL")


# 8c) Ay sonunda kesen kart: Şubat kısa olduğu için kesim 31 Ocak → 1 Mart → 31 Mart kayıyor.
#     Aynı 6 taksitli serinin 2/6, 3/6, 4/6'sı; önceki dönem borcu yok (ekstre kontrolü net harcamayla karşılaştırır).
def month_end_drift():
    inst = lambda n: ("20 Kasım 2025", f"ORNEK TEKNO ANKARA TR 6.000,00 TL'lik işlemin {n} / 6 taksidi", "1.000,00")
    rows_pdf("kayma_ocak.pdf", [("05 Ocak 2026", "ORNEK MARKET ANKARA TR", "300,00"), inst(2)],
             header="Hesap Kesim Tarihi 31 Ocak 2026   Son Ödeme Tarihi 10 Şubat 2026   Dönem Borcu 1.300,00 TL")
    rows_pdf("kayma_subat.pdf", [("10 Şubat 2026", "ORNEK KAFE ANKARA TR", "200,00"), inst(3)],
             header="Hesap Kesim Tarihi 1 Mart 2026   Son Ödeme Tarihi 11 Mart 2026   Dönem Borcu 1.200,00 TL")
    rows_pdf("kayma_mart.pdf", [("12 Mart 2026", "ORNEK AKARYAKIT ANKARA TR", "400,00"), inst(4)],
             header="Hesap Kesim Tarihi 31 Mart 2026   Son Ödeme Tarihi 10 Nisan 2026   Dönem Borcu 1.400,00 TL")


# 9) Şifreli PDF'ler (aynı şifre) ve bozuk dosya
def encrypted_and_broken():
    from pypdf import PdfReader, PdfWriter
    for src, dst in [("ekstre7.pdf", "sifreli7.pdf"), ("ekstre8.pdf", "sifreli8.pdf")]:
        w = PdfWriter()
        for pg in PdfReader(p(src)).pages: w.add_page(pg)
        w.encrypt("123456"); w.write(p(dst))
    with open(p("bozuk.pdf"), "w") as f:
        f.write("bu bir pdf değil")


def build_all():
    info = {"big": big()}
    installments_and_vertical()
    installment_series()
    statement_periods()
    cut_date_layouts()
    reconciliation()
    info["real"] = real_layout()
    plus_payments()
    two_cards()
    month_end_drift()
    encrypted_and_broken()
    return info


if __name__ == "__main__":
    print(build_all())
    print("PDF'ler:", OUT)
