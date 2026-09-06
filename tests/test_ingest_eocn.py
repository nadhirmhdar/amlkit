"""EOCN adapter tests.

The tests that earn their place here are the ones covering the decisions that
are expensive to get wrong: not screening people the Cabinet has delisted, not
turning a year into 1905, not silently accepting a PDF where a workbook was
expected, and not picking up the wrong file off a page that publishes a dozen
of them. Everything is offline -- the live source is watched by
`.github/workflows/source-canary.yml`, which is where upstream drift belongs.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amlkit.ingest.base import AdapterError  # noqa: E402
from amlkit.ingest.eocn import (  # noqa: E402
    EOCNLocalTerroristListAdapter,
    _candidate_file_ids,
    _countries,
    _looks_like_workbook,
)

# Column headings exactly as the EOCN workbook writes them, hard line break in
# the Latin family-name heading included -- the parser has to survive that.
INDIVIDUAL_HEADERS = [
    "#", "التصنيف", "الجنسية", "اسم العائلة (بالحروف العربية)",
    "اسم العائلة\n (بالحروف اللاتينية)", "الاسم الكامل (بالحروف العربية)",
    "الاسم الكامل (بالحروف اللاتينية)", "تاريخ الميلاد ", "مكان الميلاد",
    "الاسم", "الشارع   ", "المدينة", "الدولة", "النوع ", "رقم الوثيقة     ",
    "جهة الإصدار    ", "تاريخ الإصدار ", "تاريخ الانتهاء", "معلومات أخرى",
]

ENTITY_HEADERS = [
    "#", "التصنيف", "الاسم الكامل (باللغة العربية)",
    "الاسم الكامل (بالحروف اللاتينية)", "الاسم", "رقم الرخصة",
    "انتهاء الترخيص", "المقر", "ملاحظات", "معلومات أخرى",
]

# Same as INDIVIDUAL_HEADERS but ending in the two decision columns that mark
# a delisting sheet.
DELISTED_HEADERS = INDIVIDUAL_HEADERS[:-1] + ["قرار الإدراج", "قرار رفع الإدراج"]

BASIS = "مدرج بموجب قرار مجلس الوزراء رقم (18) لسنة 2017"


def _workbook(sheets: dict[str, list[list]]) -> bytes:
    """Build an .xlsx shaped like the real publication: two banner rows, then
    the headings, then data."""
    from openpyxl import Workbook

    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(title=name)
        sheet.append(["قائمة الإرهاب المحلية"])
        sheet.append(["أولاً- المعلومات الرئيسية"])
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _individual(index, latin, arabic, *, nationality="قطر", dob=None,
                family_ar="", family_la="", doc_type="", doc_number=""):
    return [
        index, "شخص إرهابي", nationality, family_ar, family_la, arabic, latin,
        dob if dob is not None else "-", "-", arabic, "-", "-", nationality,
        doc_type, doc_number, "-", "-", "-", BASIS,
    ]


LISTED = _individual(
    1, "KHALIFA MOHD T AL SUBAEY", "خليفة محمد تركي السبيعي",
    family_ar="السبيعي", family_la="AL SUBAEY",
    doc_type="جواز سفر", doc_number="685868",
)
DELISTED = _individual(1, "MOHAMMAD SAEED AL-SEQATRI", "محمد سعيد السقطري") + [
    BASIS, "رفع الإدراج بموجب قرار مجلس الوزراء رقم (24) لسنة 2024",
]


def _parse(payload: bytes):
    return list(EOCNLocalTerroristListAdapter().parse(payload))


class TestDelisting:
    """A delisted person must not be screenable. This is the whole reason the
    adapter looks at sheet structure at all."""

    def test_delisting_sheet_is_not_ingested(self):
        payload = _workbook({
            "الأفراد": [INDIVIDUAL_HEADERS, LISTED],
            "رفع الإدراج - أفراد": [DELISTED_HEADERS, DELISTED],
        })
        captions = [e.caption for e in _parse(payload)]
        assert captions == ["KHALIFA MOHD T AL SUBAEY"]

    def test_delisting_sheet_detected_by_structure_not_name(self):
        """A renamed tab must not turn delisted people back into targets."""
        payload = _workbook({
            "الأفراد": [INDIVIDUAL_HEADERS, LISTED],
            "Sheet2": [DELISTED_HEADERS, DELISTED],
        })
        captions = [e.caption for e in _parse(payload)]
        assert "MOHAMMAD SAEED AL-SEQATRI" not in captions


class TestNames:
    def test_both_scripts_are_indexed(self):
        """Arabic-aware matching is the differentiator; it works off the stored
        name rows, so the Arabic name can never be dropped for the Latin one."""
        entity = _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, LISTED]}))[0]
        names = entity.all_names()
        assert "KHALIFA MOHD T AL SUBAEY" in names
        assert "خليفة محمد تركي السبيعي" in names
        assert "السبيعي" in names and "AL SUBAEY" in names

    def test_latin_name_is_the_caption(self):
        entity = _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, LISTED]}))[0]
        assert entity.caption == "KHALIFA MOHD T AL SUBAEY"

    def test_arabic_only_entry_still_ingested(self):
        row = _individual(9, "", "أحمد عبد الجليل الحسناوي")
        entity = _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, row]}))[0]
        assert entity.caption == "أحمد عبد الجليل الحسناوي"


class TestBirthDates:
    def test_year_only_entry_stays_a_year(self):
        """The workbook stores year-only birth dates as a bare number. Running
        1975 through Excel's serial-date conversion yields 1905, which would
        then contradict the customer's real DOB and suppress the match."""
        row = _individual(2, "NAYIF SALIH SALIM AL-QAYSI", "نايف صالح سالم القيسي", dob=1975)
        assert _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, row]}))[0].birth_date == "1975"

    def test_real_date_is_iso(self):
        from datetime import date

        row = _individual(3, "TEST PERSON", "شخص", dob=date(1965, 1, 1))
        assert _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, row]}))[0].birth_date == "1965-01-01"

    def test_placeholder_dash_is_not_a_date(self):
        row = _individual(4, "TEST PERSON", "شخص", dob="-")
        assert _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, row]}))[0].birth_date is None


class TestIdentifiers:
    def test_bare_number_is_kept(self):
        entity = _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, LISTED]}))[0]
        assert ("passport", "685868") in entity.identifiers

    def test_number_is_extracted_from_an_arabic_label(self):
        """Real entries wrap the number in a label. Stored whole, it could
        never match a customer record."""
        row = _individual(
            5, "NIMA AHMAD JAMIL", "نعمة أحمد جميل",
            doc_type="الرقم الموحد", doc_number="رقم الهوية اللبنانية :000010757716",
        )
        entity = _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, row]}))[0]
        assert ("id", "000010757716") in entity.identifiers

    def test_licence_numbers_become_registration_identifiers(self):
        row = [
            1, "كيان إرهابي", "الخبراء للمحاسبة", "AL-Khobara For Accounting",
            "الخبراء", "رقم التسجيل (81396) رقم الرخصة (5083663376)", "-", "لبنان", "-", BASIS,
        ]
        entity = _parse(_workbook({"الكيانات": [ENTITY_HEADERS, row]}))[0]
        assert ("registration", "81396") in entity.identifiers
        assert ("registration", "5083663376") in entity.identifiers


class TestClassification:
    def test_person_and_organization_are_distinguished(self):
        entity_row = [
            2, "كيان إرهابي", "منظمة الكرامة", "AL-KARAMA ORGANISATION",
            "منظمة الكرامة", "-", "-", "-", "-", BASIS,
        ]
        entities = _parse(_workbook({
            "الأفراد": [INDIVIDUAL_HEADERS, LISTED],
            "الكيانات": [ENTITY_HEADERS, entity_row],
        }))
        by_caption = {e.caption: e for e in entities}
        assert by_caption["KHALIFA MOHD T AL SUBAEY"].schema_type == "Person"
        assert by_caption["AL-KARAMA ORGANISATION"].schema_type == "Organization"

    def test_programme_drives_terrorism_classification(self):
        """screening/pf.py keys terrorism-vs-proliferation off the programme.
        Emitting the wrong tag would file a terrorism hit as a PF offence."""
        from amlkit.screening.pf import classify_programs

        entity = _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, LISTED]}))[0]
        assert entity.programs == ["AE-UNSC1373"]
        assert classify_programs(entity.programs) == {"terrorism"}

    def test_sanction_topic_is_set(self):
        """`sanction` in topics is what makes a dismissal need four eyes."""
        entity = _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, LISTED]}))[0]
        assert "sanction" in entity.topics

    def test_designation_basis_is_preserved(self):
        entity = _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS, LISTED]}))[0]
        assert entity.raw["designation_basis"] == BASIS
        assert entity.listed_at == "2017"


class TestCountries:
    @pytest.mark.parametrize("arabic,expected", [
        ("قطر", "QA"),
        ("الأردن", "JO"),
        ("لبناني", "LB"),      # adjectival form
        ("السعوديه", "SA"),    # ta-marbuta spelling variant
        ("ايران", "IR"),
    ])
    def test_arabic_nationality_maps_to_iso(self, arabic, expected):
        assert expected in _countries(arabic)

    def test_dual_nationality_yields_both(self):
        result = _countries("السعودية / الكويت")
        assert "SA" in result and "KW" in result

    def test_narrative_nationality_yields_both(self):
        result = _countries("الحالية: السويد السابقة: ليبيريا")
        assert "SE" in result and "LR" in result

    def test_english_name_is_emitted_alongside_the_code(self):
        """scorer.py penalises a country the entity does not list, so the
        entity has to carry every form a customer record might use."""
        result = _countries("قطر")
        assert "QA" in result and "Qatar" in result and "قطر" in result

    def test_unmapped_country_is_kept_verbatim(self):
        assert _countries("بلد غير معروف") == ["بلد غير معروف"]


class TestLoudFailure:
    def test_a_pdf_is_rejected(self):
        with pytest.raises(AdapterError, match="not an Excel workbook"):
            _parse(b"%PDF-1.7\nnot a workbook")

    def test_empty_workbook_raises_rather_than_clearing_the_list(self):
        with pytest.raises(AdapterError, match="parsed 0 entities"):
            _parse(_workbook({"الأفراد": [INDIVIDUAL_HEADERS]}))

    def test_workbook_sniffing(self):
        assert _looks_like_workbook(b"PK\x03\x04rest")
        assert _looks_like_workbook(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest")
        assert not _looks_like_workbook(b"%PDF-1.7")


class TestFileDiscovery:
    """The page serves every publication through one endpoint, keyed only by an
    opaque GUID, so which file gets loaded depends entirely on this."""

    PAGE = """
    <div class="local-list">
      <ul><li><strong>Local Terrorist List</strong></li></ul>
      <div class="files-fromates">
        <div class="file"><em class="icon-pdf-file-format-symbol"></em>
          <a href="../API/Upload/DownloadFile?FileID=aaaaaaaa-1111-2222-3333-444444444444">PDF</a></div>
        <div class="file"><em class="icon-xlsx-file-extension-interface-symbol"></em>
          <a href="../API/Upload/DownloadFile?FileID=bbbbbbbb-1111-2222-3333-444444444444">Excel</a></div>
      </div>
    </div>
    <div class="local-list">
      <ul><li><strong>United Nations Security Council Consolidated List</strong></li></ul>
      <div class="file"><em class="icon-xlsx-file-extension-interface-symbol"></em>
        <a href="../API/Upload/DownloadFile?FileID=cccccccc-1111-2222-3333-444444444444">Excel</a></div>
    </div>
    """

    def test_excel_is_preferred_over_the_pdf(self):
        assert _candidate_file_ids(self.PAGE)[0].startswith("bbbbbbbb")

    def test_another_lists_downloads_are_not_candidates(self):
        assert not any(f.startswith("cccccccc") for f in _candidate_file_ids(self.PAGE))

    def test_no_local_list_on_the_page_yields_nothing(self):
        assert _candidate_file_ids("<html><body>nothing here</body></html>") == []


def test_dataset_identity_is_commercially_usable():
    """The entire point of this adapter: the mandatory UAE list without the
    non-commercial licence that came with sourcing it from an aggregator."""
    adapter = EOCNLocalTerroristListAdapter()
    assert adapter.is_mandatory is True
    assert adapter.key == "ae_local_terrorists"
    assert "NON-COMMERCIAL" not in adapter.licence.upper()
    assert "uaeiec.gov.ae" in adapter.source_url
