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
import re
from datetime import date, datetime
from PIL import Image, ImageChops
from passporteye import read_mrz


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


def _pdf_first_page_to_image_bytes(pdf_bytes: bytes, *, dpi: int = 300) -> bytes:
    """Rasterize a PDF's first page to PNG bytes.

    Documents scanned or saved as PDF (a phone scanner app, an all-in-one
    printer) land here just as often in practice as a direct photo upload
    -- validate_file_mime() already allow-lists application/pdf for exactly
    this reason -- but MRZ reading and PIL-based OCR fallback both only
    understand raster images. 300 DPI balances OCR/MRZ legibility against
    memory: an A4 page at 300 DPI is roughly 2480x3508px, comfortably above
    assess_image_quality()'s 600px-short-edge floor without being
    excessive. Only the first page is used -- passport/Emirates ID scans
    are single-document uploads, not multi-page packets.
    """
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        if doc.page_count == 0:
            raise ValueError("PDF has no pages")
        page = doc[0]
        zoom = dpi / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")
    finally:
        doc.close()


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

_TRADE_LICENCE_NUMBER_LABEL = re.compile(
    r"(?:Trade\s+)?Licen[cs]e\s+(?:No\.?|Number)|Registration\s+No\.?|Reg\.?\s*No\.?"
    r"|CN\s*No\.?",
    re.IGNORECASE,
)
_TRADE_LICENCE_NUMBER_VALUE = re.compile(r"[:\s]+([A-Z]{0,6}[\s\-]?\d{3,10})", re.IGNORECASE)

_TRADE_LICENCE_NAME_LABEL = re.compile(
    r"(?:Trade\s+Name|Company\s+Name|Licensee(?:\s+Name)?|Legal\s+Name)\s*[:\s]+"
    r"([A-Z][A-Za-z0-9&' \-\.]{2,90})",
    re.IGNORECASE,
)

_TRADE_LICENCE_TYPE_LABEL = re.compile(
    r"(?:Legal\s+(?:Type|Form)|Company\s+Type)\s*[:\s]+([A-Za-z][A-Za-z \-]{2,50})",
    re.IGNORECASE,
)


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

    num_label = _TRADE_LICENCE_NUMBER_LABEL.search(text)
    if num_label:
        value = _TRADE_LICENCE_NUMBER_VALUE.match(text[num_label.end():])
        if value:
            res["id_number"] = value.group(1).strip()
            res["field_confidence"]["id_number"] = mean_confidence

    name_match = _TRADE_LICENCE_NAME_LABEL.search(text)
    if name_match:
        res["full_name"] = name_match.group(1).strip().rstrip(".")
        res["field_confidence"]["full_name"] = mean_confidence

    type_match = _TRADE_LICENCE_TYPE_LABEL.search(text)
    if type_match:
        res["legal_type"] = type_match.group(1).strip()
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


def extract_trade_licence_data(image_path_or_file) -> dict[str, object]:
    """OCR a UAE trade licence image and extract company/licence fields.

    Runs pytesseract in word-level mode so a mean OCR confidence is available
    to attach to extracted fields, exactly like `extract_emirates_id_data` --
    see that function and `_parse_trade_licence_text` for why this is a
    page-level proxy rather than a true per-field score.

    An image that fails to decode or OCR (corrupt upload, unsupported format,
    a blurry phone photo pytesseract chokes on) degrades to an all-null
    result rather than raising -- the same "never let a missing field crash
    an otherwise-successful extraction" contract `extract_passport_data`
    documents for its own OCR fallback path, so the caller always gets a
    dict back and the person onboarding a company sees "nothing was read,
    fill it in" instead of a raw server error.
    """
    text = ""
    mean_confidence = None
    try:
        import pytesseract

        img = image_path_or_file if isinstance(image_path_or_file, Image.Image) else Image.open(image_path_or_file)
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
    except Exception:
        pass  # degrade to the all-null result below; see docstring

    return _parse_trade_licence_text(text, mean_confidence=mean_confidence)
