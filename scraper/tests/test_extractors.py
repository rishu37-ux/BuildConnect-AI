from buildconnect_scraper.extractors import (
    classify_profession, extract_leads, find_emails, find_mobiles,
)
from buildconnect_scraper.geo import locate
from buildconnect_scraper.models import Profession, State

DIRECTORY = """
<html><head><title>Architects in Ludhiana, Punjab | Member Directory</title></head>
<body>
  <h1>Registered Architects – Punjab</h1>
  <div class="member">
    <h3>Ar. Harpreet Kaur</h3>
    <p>Kaur Design Studio, Model Town, Ludhiana</p>
    <p>Mobile: +91 98140-12345</p>
    <p>Email: harpreet [at] kaurdesign [dot] in</p>
  </div>
  <div class="member">
    <h3>Ar. Gurpreet Singh Sandhu</h3>
    <p>Sector 70, Mohali</p>
    <p><a href="tel:09876501234">Call</a></p>
  </div>
  <div class="member"><h3>Contact Us</h3><p>0161-2401234</p></div>
  <a href="/members?page=2">Next »</a>
</body></html>
"""

JSONLD = """
<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"GeneralContractor","name":"Thakur Builders",
 "telephone":"+91-94180-55555","email":"info@thakurbuilders.in",
 "address":{"@type":"PostalAddress","addressLocality":"Mandi","addressRegion":"Himachal Pradesh"}}
</script></head><body><h1>Thakur Builders</h1></body></html>
"""


def test_find_mobiles_normalises_and_rejects_landlines():
    text = "Call 98140 12345 or +91-94180-55555, office 0172-2701234, fax 0161 2401234"
    assert find_mobiles(text) == ["+919814012345", "+919418055555"]


def test_find_emails_deobfuscates_and_filters_junk():
    assert find_emails("ravi (at) firm (dot) com, logo@2x.png, noreply@x.com") == ["ravi@firm.com"]


def test_classify_profession():
    assert classify_profession("Ar. Neha Sharma, COA registered")[0] is Profession.ARCHITECT
    assert classify_profession("Structural consultant, M.Tech")[0] is Profession.STRUCTURAL_ENGINEER
    assert classify_profession("Civil contractor and builder")[0] is Profession.CONTRACTOR
    assert classify_profession("Bakery and cafe")[0] is Profession.OTHER


def test_locate():
    assert locate("Office in Zirakpur") == ("Zirakpur", "Sahibzada Ajit Singh Nagar", State.PUNJAB)
    assert locate("Manali, HP")[2] is State.HIMACHAL_PRADESH
    assert locate("Bengaluru") == ("Bengaluru", None, State.OTHER)
    assert locate("no place here") == (None, None, State.OTHER)


def test_directory_cards():
    leads, ctx = extract_leads(DIRECTORY, "https://dir.example.in/members")
    by_name = {lead.full_name: lead for lead in leads}
    assert set(by_name) == {"Ar. Harpreet Kaur", "Ar. Gurpreet Singh Sandhu"}

    h = by_name["Ar. Harpreet Kaur"]
    assert h.phone == "+919814012345"
    assert h.email == "harpreet@kaurdesign.in"
    assert h.profession is Profession.ARCHITECT
    assert (h.city, h.state) == ("Ludhiana", State.PUNJAB)
    assert h.confidence >= 0.7

    g = by_name["Ar. Gurpreet Singh Sandhu"]
    assert g.phone == "+919876501234"
    assert g.district == "Sahibzada Ajit Singh Nagar"
    assert ("https://dir.example.in/members?page=2", "Next »") in ctx.links


def test_jsonld_business():
    leads, _ = extract_leads(JSONLD, "https://thakurbuilders.in/")
    assert len(leads) == 1
    lead = leads[0]
    assert lead.firm_name == "Thakur Builders"
    assert lead.profession is Profession.CONTRACTOR
    assert lead.state is State.HIMACHAL_PRADESH and lead.city == "Mandi"
    assert lead.phone == "+919418055555" and lead.email == "info@thakurbuilders.in"
