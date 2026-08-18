"""Passport MRZ and OCR extraction using passporteye and pytesseract.

`extract_passport_data` also surfaces document-authenticity signal: the ICAO
9303 MRZ format has a checksum digit for each field (number, date of birth,
expiry, and a composite over the whole line), and passporteye already
computes whether each one matches. Prior to this, that signal was read from
the MRZ object and then thrown away. Surfacing it catches a materially
different failure mode than OCR-quality issues: a checksum mismatch means the
digits printed on the document are internally inconsistent -- either OCR
misread something, or the document itself has been altered -- and either way
it is something an operator should look at before trusting the extracted
identity, not something to silently accept because a name and number came
back.

This is authenticity SIGNAL, not authenticity PROOF: it cannot detect a
well-forged document with internally consistent (but fabricated) checksums,
and it says nothing about the customer's face matching the photo. Full
identity verification (liveness, face-match, forgery detection beyond
checksum consistency) is out of scope here -- see the project notes on the
Document AI / Vertex AI integration path for that.
"""

from __future__ import annotations

import re
from datetime import datetime
from PIL import Image
from passporteye import read_mrz


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
        "gender": None,
        "id_number": None,
        "id_type": "passport",
        "authenticity": None,
    }

    # 1. Try reading MRZ using passporteye
    mrz = None
    try:
        mrz = read_mrz(image_path_or_file)
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
            img = Image.open(image_path_or_file)
            # Run OCR on the image
            text = pytesseract.image_to_string(img)
            
            # Simple regex search for dates (YYYY-MM-DD or DD/MM/YYYY)
            if not res["birth_date"]:
                date_match = re.search(r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})", text)
                if date_match:
                    res["birth_date"] = f"{date_match.group(3)}-{date_match.group(2)}-{date_match.group(1)}"
                    
            # Simple search for passport number
            if not res["id_number"]:
                pass_match = re.search(r"[A-Z]\d{7,9}", text)
                if pass_match:
                    res["id_number"] = pass_match.group(0)
        except Exception:
            pass
            
    return res
