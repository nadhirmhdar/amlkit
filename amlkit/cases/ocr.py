"""Passport MRZ, Emirates ID, and general OCR extraction (Tier 1 IDV).

`extract_passport_data` surfaces document-authenticity signal: the ICAO 9303
MRZ format has a checksum digit for each field (number, date of birth,
expiry, and a composite over the whole line), and passporteye already
computes whether each one matches. Surfacing it catches a materially
different failure mode than OCR-quality issues: a checksum mismatch means the
digits printed on the document are internally inconsistent -- either OCR
misread something, or the document itself has been altered -- and either way
it is something an operator should look at before trusting the extracted
identity, not something to silently accept because a name and number came
back.

`extract_emirates_id_data` extracts the same normalized field taxonomy from
a UAE Emirates ID card front, following the field-normalization pattern
AWS Textract's AnalyzeID (a common ~21-key taxonomy across document types)
and Azure Document Intelligence's prebuilt-idDocument model (per-field
confidence scores) both use. It is weaker than the passport path: Emirates
ID cards carry no MRZ, so there is no checksum-based authenticity signal at
all -- see its docstring and `validate_emirates_id_number` for why.

`check_expiry` and `assess_image_quality` are shared across both document
types.

Everything here is SIGNAL, not PROOF -- consistent with the passport MRZ
authenticity check below, and with Anthropic's own documented caveat that
vision models "cannot determine whether an image is AI-generated" and
shouldn't be relied on to detect fake or synthetic images. None of this
detects a well-forged document, and none of it confirms the customer's face
matches the photo. Full identity verification (liveness, face-match,
forgery detection beyond the signal here) remains out of scope -- see
`research/compliance-traceability.md` for the tracked gap.
"""

from __future__ import annotations

import io
import logging
import re
import time
from datetime import date, datetime
from PIL import Image, ImageChops, ImageOps
from passporteye import read_mrz

logger = logging.getLogger(__name__)


# 784-YYYY-NNNNNNN-N. OCR may drop or vary the separators, so the pattern
# tolerates a dash, a space, or nothing between groups.
EMIRATES_ID_PATTERN = re.compile(r"784[\s\-]?(\d{4})[\s\-]?(\d{7})[\s\-]?(\d)\b")

# DD/MM/YYYY, shared by the passport OCR fallback and the Emirates ID parser
# so a future change to separator/format handling only has to be made once.
_DATE_DDMMYYYY_PATTERN = re.compile(r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})")

# Front-of-card labels the Emirates ID name regex's word class can run into.
# The name capture stops at the first one of these it hits (see
# `_parse_emirates_id_text`), not just at trailing occurrences: "Date of
# Birth" as the next field means the un-labelled connector word "of" would
# otherwise survive a trailing-only strip.
_EMIRATES_ID_LABEL_WORDS = {
    "ID", "Number", "Date", "Nationality", "Sex", "Card", "Birth", "Expiry",
    "Occupation", "Employer", "Signature", "Issuing", "Emirates", "Gender",
}


def _load_bytes(image_path_or_file) -> bytes:
    """Read a path or a file-like object into memory once.

    Existing code re-reads image_path_or_file twice in both public
    functions below (once for MRZ, again for the OCR fallback) by passing
    the SAME object to two different readers -- fragile even before this
    change (a stream exhausted by the first reader silently starves the
    second), and actively wrong once PDF rasterization is added, since the
    rasterized bytes must be computed once and handed to both readers as
    fresh streams, not the raw PDF bytes reused. Centralizing the read here
    fixes both problems: everything downstream gets its own fresh
    io.BytesIO(these_bytes).

    Already-loaded `bytes` are returned as-is (checked before the path
    branch below): `bytes` also satisfies a naive path-like check, which
    would otherwise send raw content into `open(...)` as a filename.
    """
    import os
    if isinstance(image_path_or_file, bytes):
        return image_path_or_file
    if isinstance(image_path_or_file, (str, os.PathLike)):
        with open(image_path_or_file, "rb") as f:
            return f.read()
    if hasattr(image_path_or_file, "read"):
        pos = image_path_or_file.tell() if hasattr(image_path_or_file, "tell") else None
        data = image_path_or_file.read()
        if pos is not None:
            try:
                image_path_or_file.seek(pos)
            except Exception:
                pass
        return data
    raise TypeError(f"Unsupported input type for OCR: {type(image_path_or_file)!r}")


# Longest rendered edge, in pixels. An A4 page at 300 DPI is 2480x3508, so
# ordinary scans render at full 300 DPI; only oversized pages are scaled
# down. Without this, a few-hundred-byte PDF declaring one huge page renders
# at 300 DPI into gigabytes of pixels (a 3000pt page took 92s and 5.4 GB).
_PDF_MAX_RENDER_PX = 3600
# PDF's own page-size limit without UserUnit is 14,400pt (200in); anything
# larger (or non-positive) is not a scanned document.
_PDF_MAX_PAGE_PT = 14_400.0


def _pdf_first_page_to_image_bytes(pdf_bytes: bytes, *, dpi: int = 300) -> bytes:
    """Rasterize a PDF's first page to PNG bytes with pypdfium2.

    Documents scanned or saved as PDF (a phone scanner app, an all-in-one
    printer) are as common as photo uploads -- validate_file_mime() already
    allow-lists application/pdf -- but MRZ reading and PIL-based OCR only
    understand raster images. Only the first page is used: passport and
    Emirates ID scans are single-document uploads.
    """
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        if len(pdf) == 0:
            raise ValueError("PDF has no pages")
        page = pdf[0]
        try:
            width_pt, height_pt = page.get_size()
            if not (0 < width_pt <= _PDF_MAX_PAGE_PT and 0 < height_pt <= _PDF_MAX_PAGE_PT):
                raise ValueError(f"implausible PDF page size {width_pt}x{height_pt}pt")
            scale = min(dpi / 72, _PDF_MAX_RENDER_PX / max(width_pt, height_pt))
            bitmap = page.render(scale=scale)
            try:
                out = io.BytesIO()
                bitmap.to_pil().save(out, format="PNG")
                return out.getvalue()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        pdf.close()


def _prepare_image_bytes(image_path_or_file, *, dpi: int = 300) -> bytes:
    """Load input bytes, transparently rasterizing a PDF's first page.

    PDF is detected by the %PDF- magic header on the actual bytes, not by
    filename or a caller-supplied content-type -- callers here only ever
    have a file-like object or a path, no reliable extension. If PDF
    rasterization itself fails (corrupt/encrypted PDF, no pages), this
    falls back to returning the raw bytes unchanged rather than raising:
    the raw bytes will then fail MRZ/OCR the same way any other unreadable
    input already does (caught internally, all-null result) -- consistent
    with this module's existing "swallow failures, surface nothing rather
    than crash" behavior, not a new failure mode.
    """
    raw = _load_bytes(image_path_or_file)
    if raw[:5] == b"%PDF-":
        try:
            return _pdf_first_page_to_image_bytes(raw, dpi=dpi)
        except Exception:
            pass
    return raw


def _resolve_two_digit_year(two_digit_year: str, month: str, day: str) -> str | None:
    """Disambiguate an MRZ two-digit year by picking whichever century
    lands closer to today.

    ICAO 9303 MRZ dates are two digits with no century marker. A fixed
    pivot (as used for date_of_birth below) is wrong for an expiry date:
    an already-expired document -- the exact case expiry checking exists to
    catch -- can carry a last-century year, and a fixed "assume 20XX"
    prefix would silently reinterpret it as decades in the future instead.
    Picking the century whose result is numerically closest to today holds
    up for both birth dates and expiry dates without a hardcoded cutoff.
    Returns `None` if neither century produces a valid calendar date.
    """
    candidates = []
    for prefix in ("19", "20"):
        candidate = f"{prefix}{two_digit_year}-{month}-{day}"
        try:
            parsed = datetime.strptime(candidate, "%Y-%m-%d").date()
        except ValueError:
            continue
        candidates.append((abs(parsed.year - date.today().year), candidate))

    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def _authenticity_from_mrz(mrz) -> dict[str, object]:
    """Pull passporteye's per-field checksum validity off the MRZ object.

    Reads defensively (`getattr(..., None)`) rather than assuming every
    attribute exists: passporteye's exact field set has drifted across
    versions, and a missing attribute should degrade to "unknown", not crash
    a scan that otherwise succeeded.
    """
    fields = {
        "number": getattr(mrz, "valid_number", None),
        "date_of_birth": getattr(mrz, "valid_date_of_birth", None),
        "expiration_date": getattr(mrz, "valid_expiration_date", None),
        "composite": getattr(mrz, "valid_composite", None),
        "personal_number": getattr(mrz, "valid_personal_number", None),
    }
    known = {k: v for k, v in fields.items() if v is not None}
    failed = [k for k, v in known.items() if not v]

    score = getattr(mrz, "valid_score", None)
    if score is None and known:
        # passporteye reports valid_score on a 0-100 scale; derive an
        # equivalent from the individual field checks when the library
        # version in use doesn't expose it directly.
        score = round(100 * sum(1 for v in known.values() if v) / len(known))

    return {
        "mrz_valid_score": score,
        "checksum_failures": failed,
        "flags": (
            [f"MRZ checksum failed: {f.replace('_', ' ')}" for f in failed]
            if failed else []
        ),
    }


def extract_passport_data(image_path_or_file) -> dict[str, str | None]:
    """Extract passport information from image file.

    Returns a dictionary of extracted fields (standardized), plus an
    `authenticity` block (see `_authenticity_from_mrz`). `authenticity` is
    `None` when MRZ reading failed entirely -- there is nothing to check
    checksums against, which is itself informative (OCR fallback fields
    below have no authenticity signal at all).
    """
    res = {
        "full_name": None,
        "name_arabic": None,
        "nationality": None,
        "birth_date": None,
        "expiry_date": None,
        "gender": None,
        "id_number": None,
        "id_type": "passport",
        "authenticity": None,
    }

    image_bytes = _prepare_image_bytes(image_path_or_file)

    # 1. Try reading MRZ using passporteye
    mrz = None
    try:
        mrz = read_mrz(io.BytesIO(image_bytes))
    except Exception:
        pass
        
    if mrz is not None:
        mrz_data = mrz.to_dict()
        res["authenticity"] = _authenticity_from_mrz(mrz)

        # Extract name (surname + given names)
        names = []
        if mrz_data.get("surname"):
            names.append(mrz_data["surname"].strip())
        if mrz_data.get("names"):
            names.append(mrz_data["names"].strip())
        if names:
            res["full_name"] = " ".join(names).replace("<", " ").strip().title()
            
        # Nationality (usually 3-letter code, e.g. ARE, IND, USA)
        if mrz_data.get("nationality"):
            res["nationality"] = mrz_data["nationality"].strip().upper()
            
        # DOB (YYMMDD in MRZ)
        dob = mrz_data.get("date_of_birth")
        if dob and len(dob) == 6:
            try:
                # Guess century
                year_prefix = "19" if int(dob[:2]) > 30 else "20"
                formatted_dob = f"{year_prefix}{dob[:2]}-{dob[2:4]}-{dob[4:6]}"
                # Validate format
                datetime.strptime(formatted_dob, "%Y-%m-%d")
                res["birth_date"] = formatted_dob
            except ValueError:
                pass

        # Expiry (YYMMDD in MRZ). A fixed "assume 20XX" prefix would silently
        # turn an already-expired document -- the exact thing expiry
        # checking exists to catch -- into one that looks valid for another
        # 70-odd years whenever its MRZ year is from last century (e.g. "99"
        # meaning 1999, not 2099). `_resolve_two_digit_year` picks whichever
        # century lands closer to today instead of assuming one.
        expiry = mrz_data.get("expiration_date")
        if expiry and len(expiry) == 6:
            resolved = _resolve_two_digit_year(expiry[:2], expiry[2:4], expiry[4:6])
            if resolved:
                res["expiry_date"] = resolved

        # Gender (M/F)
        if mrz_data.get("sex"):
            sex = mrz_data["sex"].strip().upper()
            if sex in ("M", "MALE"):
                res["gender"] = "male"
            elif sex in ("F", "FEMALE"):
                res["gender"] = "female"
                
        # Passport Number
        if mrz_data.get("number"):
            res["id_number"] = mrz_data["number"].replace("<", "").strip().upper()
            
    # 2. Fallback to pytesseract OCR if MRZ failed or fields are missing
    if not res["full_name"] or not res["id_number"]:
        try:
            import pytesseract
            img = Image.open(io.BytesIO(image_bytes))
            # Run OCR on the image
            text = pytesseract.image_to_string(img)
            
            # Simple regex search for dates (DD/MM/YYYY)
            if not res["birth_date"]:
                date_match = _DATE_DDMMYYYY_PATTERN.search(text)
                if date_match:
                    res["birth_date"] = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"
                    
            # Simple search for passport number
            if not res["id_number"]:
                pass_match = re.search(r"[A-Z]\d{7,9}", text)
                if pass_match:
                    res["id_number"] = pass_match.group(0)
        except Exception:
            pass

    res["expiry_check"] = check_expiry(res["expiry_date"])
    return res


def check_expiry(expiry_date: str | None, warn_days: int = 30) -> dict[str, object]:
    """Evaluate an ISO (`YYYY-MM-DD`) expiry date against today.

    Shared by both the passport and Emirates ID paths -- an expired document
    fails CDD regardless of which document type it came from. `expiry_date`
    of `None` (nothing was extracted) degrades to an "unknown" result rather
    than raising, matching this module's pattern elsewhere of never letting
    a missing field crash an otherwise-successful extraction.
    """
    if not expiry_date:
        return {
            "expired": None,
            "expiring_soon": None,
            "days_until_expiry": None,
            "flags": [],
        }

    try:
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d").date()
    except ValueError:
        return {
            "expired": None,
            "expiring_soon": None,
            "days_until_expiry": None,
            "flags": [f"expiry date unparseable: {expiry_date!r}"],
        }

    days = (expiry - date.today()).days
    expired = days < 0
    expiring_soon = 0 <= days <= warn_days

    flags = []
    if expired:
        flags.append(f"document expired {abs(days)} day(s) ago")
    elif expiring_soon:
        flags.append(f"document expires in {days} day(s)")

    return {
        "expired": expired,
        "expiring_soon": expiring_soon,
        "days_until_expiry": days,
        "flags": flags,
    }


def _parse_emirates_id_text(text: str, mean_confidence: float | None = None) -> dict[str, object]:
    """Pull identity fields out of raw OCR text from an Emirates ID front.

    Split out from `extract_emirates_id_data` so the field-parsing logic is
    testable without a tesseract binary -- the same reasoning
    `_authenticity_from_mrz` was split out for.

    Emirates ID cards carry no MRZ, so this is regex-against-free-text, not
    a structured-format parser: materially weaker than the passport path.
    Name extraction in particular is a best-effort label search, not a
    template-anchored field read, because there is no fixed bounding box to
    read it from without building a card template this function doesn't
    have. Every extracted field shares one `mean_confidence` (the page's
    average OCR word confidence) rather than a true per-field score, because
    mapping OCR words to specific fields would need that same template.
    This is a coarser signal than AWS AnalyzeID's or Azure's true per-field
    confidence, and callers should treat it accordingly.
    """
    res: dict[str, object] = {
        "full_name": None,
        "id_number": None,
        "birth_date": None,
        "expiry_date": None,
        "id_type": "emirates_id",
        "field_confidence": {},
        "authenticity": None,  # no MRZ on this document type -- nothing to checksum
    }

    id_match = EMIRATES_ID_PATTERN.search(text)
    if id_match:
        res["id_number"] = f"784-{id_match.group(1)}-{id_match.group(2)}-{id_match.group(3)}"
        res["field_confidence"]["id_number"] = mean_confidence

    # Dates print as DD/MM/YYYY. A front-side card shows Date of Birth and
    # Expiry Date (some layouts add Issuing Date between them); sorted
    # ascending, birth date is the oldest and expiry the newest -- a
    # heuristic, not a labelled field read, and it assumes at least two
    # dates were legible.
    date_matches = _DATE_DDMMYYYY_PATTERN.findall(text)
    parsed_dates = []
    for d, m, y in date_matches:
        try:
            parsed_dates.append(datetime.strptime(f"{y}-{m}-{d}", "%Y-%m-%d").date())
        except ValueError:
            continue
    if parsed_dates:
        parsed_dates.sort()
        res["birth_date"] = parsed_dates[0].isoformat()
        res["field_confidence"]["birth_date"] = mean_confidence
        if len(parsed_dates) > 1:
            res["expiry_date"] = parsed_dates[-1].isoformat()
            res["field_confidence"]["expiry_date"] = mean_confidence

    # Name: best-effort label search immediately after "Name" (English side
    # of the bilingual card). Arabic name is not extracted here. The class
    # below is greedy about what counts as "still the name" -- it doesn't
    # know where the name ends -- so the words are walked from the front and
    # cut at the first word that is itself a card label (e.g. the next field
    # over, "Nationality"). Cutting from the front rather than stripping
    # known labels off the tail matters for multi-word labels like "Date of
    # Birth": stripping the tail only removes an exact label word, so the
    # unlabelled connector "of" would survive; stopping at the first label
    # word removes "Date" and everything after it in one pass.
    name_match = re.search(r"Name[:\s]+([A-Z][A-Za-z' \-]{2,60})", text)
    if name_match:
        name_words = []
        for word in name_match.group(1).strip().split():
            if word in _EMIRATES_ID_LABEL_WORDS:
                break
            name_words.append(word)
        if name_words:
            res["full_name"] = " ".join(name_words)
            res["field_confidence"]["full_name"] = mean_confidence

    res["expiry_check"] = check_expiry(res["expiry_date"])
    res["id_validation"] = validate_emirates_id_number(res["id_number"])
    return res


def extract_emirates_id_data(image_path_or_file) -> dict[str, object]:
    """OCR a UAE Emirates ID card front and extract identity fields.

    Runs pytesseract in word-level mode (`image_to_data`) rather than plain
    `image_to_string` so a mean OCR confidence is available to attach to
    extracted fields -- see `_parse_emirates_id_text` for why that is a
    page-level proxy rather than a true per-field score, and for the field
    extraction logic itself, which this function only feeds.
    """
    import pytesseract

    if isinstance(image_path_or_file, Image.Image):
        img = image_path_or_file
    else:
        image_bytes = _prepare_image_bytes(image_path_or_file)
        img = Image.open(io.BytesIO(image_bytes))
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    words_with_conf = [
        (word, float(conf))
        for word, conf in zip(data["text"], data["conf"])
        if word.strip() and float(conf) >= 0
    ]
    text = " ".join(word for word, _ in words_with_conf)
    mean_confidence = (
        round(sum(conf for _, conf in words_with_conf) / len(words_with_conf), 1)
        if words_with_conf
        else None
    )

    return _parse_emirates_id_text(text, mean_confidence=mean_confidence)


def validate_emirates_id_number(id_number: str | None) -> dict[str, object]:
    """Format-check a UAE Emirates ID number (`784-YYYY-NNNNNNN-N`).

    Checks structure and birth-year plausibility only. The final digit is a
    check digit, but the UAE authorities have not published its algorithm --
    every third-party "validator" claiming to verify it is guessing at an
    undocumented scheme. Shipping a fabricated checksum would give false
    confidence in a compliance tool, so this validates format only and says
    so explicitly in every result.
    """
    flags = ["check digit not verified -- algorithm is not publicly documented"]

    if not id_number:
        return {"valid_format": False, "flags": ["no ID number extracted"]}

    match = re.fullmatch(r"784-(\d{4})-(\d{7})-(\d)", id_number)
    if not match:
        flags.insert(0, f"does not match 784-YYYY-NNNNNNN-N format: {id_number!r}")
        return {"valid_format": False, "flags": flags}

    birth_year = int(match.group(1))
    if not (1900 <= birth_year <= date.today().year):
        flags.insert(0, f"implausible birth year in ID number: {birth_year}")
        return {"valid_format": False, "flags": flags}

    return {"valid_format": True, "flags": flags}


def assess_image_quality(image_path_or_file) -> dict[str, object]:
    """Cheap, dependency-free signal on scan quality and possible re-editing.

    This is quality/anomaly SIGNAL, not forgery PROOF -- same caveat as
    `_authenticity_from_mrz`, and consistent with Anthropic's own documented
    limitation that vision models "cannot determine whether an image is
    AI-generated" and shouldn't be relied on to detect fake or synthetic
    images. This heuristic makes no stronger claim: it catches only the
    cruder failure modes below, and a well-forged or well-generated document
    passes through it undetected.

    Two checks, both using only PIL (no new dependency):

    - Resolution: a scan too small to trust for either OCR or a human
      reviewer's visual check.
    - Coarse Error Level Analysis: re-save the image at a fixed JPEG quality
      and diff it against the original. A genuine single-generation JPEG
      re-compresses to a near-uniform, low error level across the frame;
      a large diff can indicate the image was edited and re-saved after its
      last real capture, though a heavily-compressed but otherwise genuine
      scan can also trigger it. The 60/255 threshold below is a starting
      point, not a validated cutoff -- it needs calibration against real
      UAE-document samples before being trusted for anything but a
      human-review prompt.
    """
    if isinstance(image_path_or_file, Image.Image):
        img = image_path_or_file
    else:
        image_bytes = _prepare_image_bytes(image_path_or_file)
        img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    width, height = img.size

    flags = []
    if min(width, height) < 600:
        flags.append(
            f"low resolution ({width}x{height}) -- extraction and manual "
            "review reliability both degrade below 600px on the short edge"
        )

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    buf.seek(0)
    resaved = Image.open(buf)
    diff = ImageChops.difference(img, resaved)
    max_error = max(band_extrema[1] for band_extrema in diff.getextrema())
    if max_error > 60:
        flags.append(
            f"elevated re-compression error (max channel diff {max_error}/255) "
            "-- possible prior edit; review manually"
        )

    return {
        "width": width,
        "height": height,
        "max_ela_error": max_error,
        "flags": flags,
    }


# Issuing-authority display names, matched against a keyword found anywhere
# in the OCR text. Order matters: more specific free-zone names are checked
# before the generic "Department of Economy" (mainland) fallback so a free
# zone licence that also happens to mention "Dubai" doesn't get mis-tagged.
_TRADE_LICENCE_AUTHORITIES: tuple[tuple[str, str], ...] = (
    ("dmcc", "Dubai Multi Commodities Centre (DMCC)"),
    ("jafza", "Jebel Ali Free Zone (JAFZA)"),
    ("dafza", "Dubai Airport Free Zone (DAFZA)"),
    ("difc", "Dubai International Financial Centre (DIFC)"),
    ("ifza", "International Free Zone Authority (IFZA)"),
    ("rakez", "Ras Al Khaimah Economic Zone (RAKEZ)"),
    ("shams", "Sharjah Media City (SHAMS)"),
    ("adgm", "Abu Dhabi Global Market (ADGM)"),
    ("meydan", "Meydan Free Zone"),
    ("department of economy and tourism", "Dubai Department of Economy and Tourism"),
    ("department of economic development", "Department of Economic Development"),
)

# Legal-structure suffixes/phrases a trade name or "Legal Type" field commonly
# carries. Checked longest-first so "Free Zone Establishment" matches before
# the bare "LLC" a shorter, unrelated substring could otherwise catch.
_TRADE_LICENCE_LEGAL_TYPES: tuple[str, ...] = (
    "Free Zone Establishment", "Free Zone Company", "Sole Establishment",
    "Sole Proprietorship", "Civil Company", "Limited Liability Company",
    "Branch of a Foreign Company", "Public Joint Stock Company",
    "Private Joint Stock Company", "General Partnership", "FZCO", "FZE", "LLC",
)

# Genuine licence-number labels, tried first (see _parse_trade_licence_text).
# Registration/CR/CN numbers are a DIFFERENT identifier some layouts print
# ABOVE the licence number -- searching the whole alternation with one
# .search() let whichever label happened to appear FIRST in the text win,
# so a "Register No." printed before "License No." silently took the
# licence-number field. This pattern is searched on its own, first.
_TRADE_LICENCE_NUMBER_LABEL = re.compile(
    r"(?:Trade\s+)?Licen[cs]e\s+(?:No\.?|Number)",
    re.IGNORECASE,
)
# Only consulted when no genuine licence-number label was found anywhere in
# the text -- a registration/CR/CN number is better than nothing, but must
# never outrank the real licence number.
_TRADE_LICENCE_NUMBER_LABEL_FALLBACK = re.compile(
    r"Registration\s+No\.?|Reg\.?\s*No\.?|CR\s*No\.?|CN\s*No\.?",
    re.IGNORECASE,
)
_TRADE_LICENCE_NUMBER_VALUE = re.compile(r"[:\s]+([A-Z]{0,6}[\s\-]?\d{3,10})", re.IGNORECASE)

# Name-field labels across the 40+ issuing-authority layouts this module has
# to cope with (see _parse_trade_licence_text's docstring) -- the original
# list only covered "Trade Name"/"Company Name"/"Licensee"/"Legal Name", so
# a "Business Name" (and similar) layout returned nothing at all. Ordered
# longest-alternative-first within each near-duplicate pair ("Licensee Name"
# before bare "Licensee") so re's leftmost-alternative-wins behavior prefers
# the more specific label when both would match at the same position.
_TRADE_LICENCE_NAME_LABEL = re.compile(
    r"(?:Trade\s+Name|Company\s+Name|Business\s+Name|Firm\s+Name|"
    r"Establishment\s+Name|Entity\s+Name|Name\s+of\s+Company|"
    r"Licensee\s+Name|Licensee|Legal\s+Name)\s*[:\s]+"
    r"([A-Z][^\n]{2,90})",
    re.IGNORECASE,
)

_TRADE_LICENCE_TYPE_LABEL = re.compile(
    r"(?:Legal\s+(?:Type|Form)|Company\s+Type)\s*[:\s]+([A-Za-z][^\n]{2,50})",
    re.IGNORECASE,
)

# Labels a captured name/legal-type value must stop AT rather than run into.
# With line-preserving OCR text (_ocr_data_to_text) the capture above
# already stops at the newline most of the time, but a line break tesseract
# missed (or a layout that prints two fields on one visual line) used to let
# the name capture run on into the next field, e.g. name ending up as
# "FALCON RIDGE TRADING LLC Legal Type" with legal_type then reading
# "Limited Liability Company Issue Date". Ordered longest-first so a
# multi-word label is matched (and cut) whole rather than at its first word.
_TRADE_LICENCE_NAME_STOP = re.compile(
    r"\b(?:"
    r"Legal\s+Type|Legal\s+Form|Company\s+Type|"
    r"Trade\s+Name|Company\s+Name|Business\s+Name|Firm\s+Name|"
    r"Establishment\s+Name|Entity\s+Name|Name\s+of\s+Company|"
    r"Licensee\s+Name|Licensee|Legal\s+Name|"
    r"(?:Trade\s+)?Licen[cs]e\s+(?:No\.?|Number)|"
    r"Registration\s+No\.?|Reg\.?\s*No\.?|CR\s*No\.?|CN\s*No\.?|"
    r"Issue\s+Date|Expiry\s+Date|Date\s+of\s+Issue|Date\s+of\s+Expiry|"
    r"Nationality|Address|Activity|Activities|Owner|Partners|Manager"
    r")\b",
    re.IGNORECASE,
)


def _cut_at_stop_label(value: str) -> str:
    """Truncate a captured name/legal-type value at the first label word it
    ran into, per _TRADE_LICENCE_NAME_STOP above. Trims trailing punctuation
    left over from a label's leading colon/dash."""
    stop = _TRADE_LICENCE_NAME_STOP.search(value)
    if stop:
        value = value[: stop.start()]
    return value.strip().strip(":-.,").strip()


def _parse_trade_licence_text(text: str, mean_confidence: float | None = None) -> dict[str, object]:
    """Pull identity fields out of raw OCR text from a UAE trade licence.

    Unlike passport MRZ (one fixed ICAO format) or even Emirates ID (one
    national format), a UAE trade licence has no fixed template at all: over
    40 issuing authorities (mainland DED per emirate, dozens of free zones)
    each print their own layout. So this is regex-against-free-text, and
    weaker still than the Emirates ID path in one specific way -- the licence
    number has no universal, safe pattern to fall back on (Emirates ID's
    `784-...` prefix is unique enough to search for even unlabelled; a bare
    5-10 digit trade licence number is not, and guessing wrong would misfile
    the one field everything else on the customer record keys off). So
    `id_number` is extracted ONLY next to an explicit label, never as a
    bare-number guess.

    `issuing_authority` is a best-effort keyword match, used to tag which
    licence layout was likely being read -- not itself an extracted field
    printed on the document.
    """
    res: dict[str, object] = {
        "full_name": None,
        "id_number": None,
        "legal_type": None,
        "issue_date": None,
        "expiry_date": None,
        "issuing_authority": None,
        "id_type": "trade_licence",
        "field_confidence": {},
    }

    # Genuine licence-number label first; registration/CR/CN number only as
    # a fallback when no licence-number label was found anywhere in the
    # text -- see _TRADE_LICENCE_NUMBER_LABEL_FALLBACK above.
    num_label = _TRADE_LICENCE_NUMBER_LABEL.search(text)
    if not num_label:
        num_label = _TRADE_LICENCE_NUMBER_LABEL_FALLBACK.search(text)
    if num_label:
        value = _TRADE_LICENCE_NUMBER_VALUE.match(text[num_label.end():])
        if value:
            res["id_number"] = value.group(1).strip()
            res["field_confidence"]["id_number"] = mean_confidence

    name_match = _TRADE_LICENCE_NAME_LABEL.search(text)
    if name_match:
        name_value = _cut_at_stop_label(name_match.group(1))
        if name_value:
            res["full_name"] = name_value
            res["field_confidence"]["full_name"] = mean_confidence

    type_match = _TRADE_LICENCE_TYPE_LABEL.search(text)
    if type_match:
        type_value = _cut_at_stop_label(type_match.group(1))
        if type_value:
            res["legal_type"] = type_value
            res["field_confidence"]["legal_type"] = mean_confidence
    else:
        # No labelled "Legal Type" field on this layout -- the trade name
        # itself often carries the suffix (e.g. "... TRADING LLC").
        haystack = (res["full_name"] or "") + " " + text
        for legal_type in _TRADE_LICENCE_LEGAL_TYPES:
            if re.search(r"\b" + re.escape(legal_type) + r"\b", haystack, re.IGNORECASE):
                res["legal_type"] = legal_type
                break

    # Dates: same DD/MM/YYYY-or-DD-MM-YYYY pattern as the Emirates ID path.
    # A licence prints Issue and Expiry (never a third date), sorted
    # ascending: issue is the older date, expiry the newer one.
    date_matches = _DATE_DDMMYYYY_PATTERN.findall(text)
    parsed_dates = []
    for d, m, y in date_matches:
        try:
            parsed_dates.append(datetime.strptime(f"{y}-{m}-{d}", "%Y-%m-%d").date())
        except ValueError:
            continue
    if parsed_dates:
        parsed_dates.sort()
        res["issue_date"] = parsed_dates[0].isoformat()
        res["field_confidence"]["issue_date"] = mean_confidence
        if len(parsed_dates) > 1:
            res["expiry_date"] = parsed_dates[-1].isoformat()
            res["field_confidence"]["expiry_date"] = mean_confidence

    lowered = text.lower()
    for keyword, display_name in _TRADE_LICENCE_AUTHORITIES:
        if keyword in lowered:
            res["issuing_authority"] = display_name
            break

    res["expiry_check"] = check_expiry(res["expiry_date"])
    return res


def _prepare_for_ocr(img: Image.Image, *, min_long_side: int = 1600, max_long_side: int = 3000) -> Image.Image:
    """Normalize a phone photo for tesseract: real orientation, contrast, size.

    Two failure modes this exists to fix (see extract_trade_licence_data's
    docstring for the reported symptom):

    1. Phone photos are routinely stored sideways -- the camera saved
       landscape pixels with the intended "portrait" orientation recorded
       only in the EXIF `Orientation` tag. tesseract does not read EXIF at
       all, so it OCR'd the raw (sideways) pixels as noise and returned
       nothing. `ImageOps.exif_transpose` physically rotates the pixels to
       match the recorded orientation before any OCR pass runs.
    2. A phone photo is often low-contrast (indoor lighting, glare) and
       either far larger or far smaller than tesseract's sweet spot.
       Greyscale + autocontrast plus clamping the long edge into
       [min_long_side, max_long_side] keeps quality consistent across wildly
       different camera resolutions without ever upscaling a huge image into
       a slow multi-pass run.

    A genuinely sideways image with NO EXIF orientation tag (a screenshot, a
    re-saved copy that stripped metadata) is not fixed here -- that is what
    the rotation passes in `extract_trade_licence_data` are for.
    """
    img = ImageOps.exif_transpose(img)
    if img.mode != "L":
        img = img.convert("L")
    img = ImageOps.autocontrast(img)

    long_side = max(img.size)
    if long_side < min_long_side:
        scale = min_long_side / long_side
    elif long_side > max_long_side:
        scale = max_long_side / long_side
    else:
        scale = 1.0
    if scale != 1.0:
        new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        img = img.resize(new_size, Image.LANCZOS)
    return img


def _ocr_data_to_text(data: dict) -> str:
    """Rebuild line-preserving text from pytesseract's `image_to_data` output.

    The old code joined every OCR word with a single space
    (`" ".join(...)`), which flattens a labelled-field layout -- "License
    No: 123456   Issue Date: 01/01/2023" printed as two columns, or any
    multi-field licence -- onto one line. The name/legal-type regexes then
    ran straight past the end of the intended value into the next label
    (e.g. `full_name` coming back as "FALCON RIDGE TRADING LLC Legal
    Type"). `image_to_data`'s `block_num`/`par_num`/`line_num` identify
    which physical source line each word belongs to, in reading order, so
    this walks the parallel arrays once and starts a new output line
    whenever that triple changes -- giving the field parser real line
    boundaries to anchor "stop at end of line" on.

    Falls back to the old space-joined behavior when those keys are absent:
    the fake `image_to_data` mocks in test_trade_licence_scan.py (and the
    original test fixtures) only return `text`/`conf`, and must keep
    working unchanged.
    """
    texts = data.get("text", [])
    confs = data.get("conf", [])
    has_line_info = "block_num" in data and "par_num" in data and "line_num" in data

    if not has_line_info:
        words = [w for w, c in zip(texts, confs) if w.strip() and float(c) >= 0]
        return " ".join(words)

    out_lines: list[str] = []
    current_key = None
    current_words: list[str] = []
    for word, conf, b, p, ln in zip(texts, confs, data["block_num"], data["par_num"], data["line_num"]):
        if not word.strip() or float(conf) < 0:
            continue
        key = (b, p, ln)
        if key != current_key:
            if current_words:
                out_lines.append(" ".join(current_words))
            current_words = []
            current_key = key
        current_words.append(word)
    if current_words:
        out_lines.append(" ".join(current_words))
    return "\n".join(out_lines)


def _mean_ocr_confidence(data: dict) -> float | None:
    """Mean word-level OCR confidence, same filter as `_ocr_data_to_text`."""
    confs = [
        float(conf) for word, conf in zip(data.get("text", []), data.get("conf", []))
        if word.strip() and float(conf) >= 0
    ]
    return round(sum(confs) / len(confs), 1) if confs else None


def _score_trade_licence_result(result: dict[str, object]) -> int:
    """Rank a parsed OCR pass so the best of several attempts can be kept.

    The two fields everything else on the customer record keys off --
    company name and licence number -- weigh far more than the supporting
    fields, so a pass that recovers both always outranks a pass that only
    picked up a legal type and a date.
    """
    score = 0
    if result.get("full_name"):
        score += 3
    if result.get("id_number"):
        score += 3
    if result.get("legal_type"):
        score += 1
    if result.get("issue_date"):
        score += 1
    if result.get("expiry_date"):
        score += 1
    return score


# (config, rotation-degrees) for each attempt, in order. `None` config runs
# pytesseract.image_to_data with no `config=` kwarg at all -- required so the
# FIRST pass keeps calling it with the exact signature existing test mocks
# (e.g. test_trade_licence_scan.py's fake_image_to_data(img, output_type=))
# expect. --psm 6 ("assume a single uniform block of text") and --psm 11
# ("sparse text, no particular layout") cover licences tesseract's default
# page-segmentation guess misreads; the three rotations cover a sideways
# photo that carries no usable EXIF orientation (see _prepare_for_ocr).
_TRADE_LICENCE_OCR_PASSES: tuple[tuple[str | None, int], ...] = (
    (None, 0),
    ("--psm 6", 0),
    ("--psm 11", 0),
    (None, 90),
    (None, 270),
    (None, 180),
)

# Wall-clock ceiling across all passes. Best-effort only -- checked between
# passes, not inside one -- but bounds the worst case (a large, hard image
# run through six full tesseract passes) to something a web request can
# still return within.
_TRADE_LICENCE_OCR_TIME_BUDGET_S = 45.0


def extract_trade_licence_data(image_path_or_file) -> dict[str, object]:
    """OCR a UAE trade licence image and extract company/licence fields.

    Multi-pass: tries `_TRADE_LICENCE_OCR_PASSES` in order (default page
    segmentation, then --psm 6, then --psm 11, then the image rotated 90/
    270/180 degrees), keeping the highest-`_score_trade_licence_result`
    parse seen so far, and stopping as soon as a pass recovers both
    `full_name` and `id_number` -- the two fields nothing else can be
    guessed for. This exists because a real phone photo of a licence is
    often sideways with no usable EXIF (a screenshot, a re-saved copy) and
    tesseract's default page-segmentation mode alone frequently returns
    nothing readable from it; see this module's module-level docstring
    reference and the regression tests in test_ocr.py.

    Each pass runs on the SAME `_prepare_for_ocr`-normalized image (rotated
    per-pass where listed) -- see that function for the EXIF-orientation and
    contrast/scaling fix that handles the common case.

    An image that fails to decode or every OCR pass raises (corrupt upload,
    unsupported format, the tesseract binary missing) degrades to an
    all-null result with `ocr_error` set to a short message, rather than
    raising -- the same "never let a missing field crash an otherwise-
    successful extraction" contract `extract_passport_data` documents for
    its own OCR fallback path. Previously EVERY OCR exception was silently
    swallowed (`except Exception: pass`), so "the scanner itself failed"
    and "the scanner ran fine but found nothing" were indistinguishable to
    both the caller and the person onboarding a company; `ocr_error` is
    `None` on any pass that ran, whatever it did or didn't find.
    """
    try:
        import pytesseract

        if isinstance(image_path_or_file, Image.Image):
            raw_img = image_path_or_file
        else:
            # Same path as passport/Emirates ID: a scanned-to-PDF licence is
            # rasterized (size-capped) before OCR.
            raw_img = Image.open(io.BytesIO(_prepare_image_bytes(image_path_or_file)))
        prepared = _prepare_for_ocr(raw_img)
    except Exception as exc:
        logger.warning("trade licence OCR: could not prepare image: %s", exc)
        result = _parse_trade_licence_text("")
        result["ocr_error"] = f"could not read this image: {exc}"
        return result

    best_result: dict[str, object] | None = None
    best_score = -1
    last_error: Exception | None = None
    any_pass_ran = False
    start = time.monotonic()

    for config, rotation in _TRADE_LICENCE_OCR_PASSES:
        if time.monotonic() - start > _TRADE_LICENCE_OCR_TIME_BUDGET_S:
            break
        pass_img = prepared.rotate(rotation, expand=True) if rotation else prepared
        try:
            kwargs: dict[str, object] = {"output_type": pytesseract.Output.DICT}
            if config:
                kwargs["config"] = config
            data = pytesseract.image_to_data(pass_img, **kwargs)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "trade licence OCR pass failed (config=%r, rotation=%s): %s", config, rotation, exc
            )
            continue

        any_pass_ran = True
        text = _ocr_data_to_text(data)
        mean_confidence = _mean_ocr_confidence(data)
        result = _parse_trade_licence_text(text, mean_confidence=mean_confidence)
        score = _score_trade_licence_result(result)
        if score > best_score:
            best_result, best_score = result, score
        if result.get("full_name") and result.get("id_number"):
            break

    if not any_pass_ran:
        logger.warning("trade licence OCR: every pass failed: %s", last_error)
        result = _parse_trade_licence_text("")
        result["ocr_error"] = f"OCR engine failed: {last_error}" if last_error else "OCR engine failed"
        return result

    assert best_result is not None  # any_pass_ran guarantees at least one result was scored
    best_result["ocr_error"] = None
    return best_result
