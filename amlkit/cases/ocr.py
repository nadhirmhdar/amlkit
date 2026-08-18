"""Passport MRZ and OCR extraction using passporteye and pytesseract."""

from __future__ import annotations

import re
from datetime import datetime
from PIL import Image
from passporteye import read_mrz


def extract_passport_data(image_path_or_file) -> dict[str, str | None]:
    """Extract passport information from image file.
    
    Returns a dictionary of extracted fields (standardized).
    """
    res = {
        "full_name": None,
        "name_arabic": None,
        "nationality": None,
        "birth_date": None,
        "gender": None,
        "id_number": None,
        "id_type": "passport",
    }
    
    # 1. Try reading MRZ using passporteye
    mrz = None
    try:
        mrz = read_mrz(image_path_or_file)
    except Exception:
        pass
        
    if mrz is not None:
        mrz_data = mrz.to_dict()
        
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
