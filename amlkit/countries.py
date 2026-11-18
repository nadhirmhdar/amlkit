"""Country names and codes -> ISO 3166-1 alpha-2, for comparing like with like.

Customers carry ISO alpha-2 codes (``IN``) while most reference lists publish
plain English names (``India``, ``Korea, North``, ``Russian Federation``): the
CIA World Leaders and Wikidata PEP lists, and the UN / OFAC / UK / EU sanctions
lists all do. Compared as raw strings those never agree, which used to read as
a country *mismatch* and silently knocked 0.20 off even an exact name match
(a perfect hit on India's Home Minister for an Indian customer fell under the
0.85 alert threshold). ``to_alpha2`` resolves either spelling to a code so the
scorer can tell "same country" from "different country" from "can't tell".

Pure data and string handling; no I/O.
"""
from __future__ import annotations

import re
import unicodedata

# alpha-2 -> "Official-ish name|alias|alias". Aliases cover the spellings the
# lists above actually use (CIA "Burma", UN "Korea, Democratic People's
# Republic of", OFAC "Russia", ...).
_TABLE: dict[str, str] = {
    "AD": "Andorra", "AE": "United Arab Emirates|UAE|Emirates", "AF": "Afghanistan",
    "AG": "Antigua and Barbuda|Antigua & Barbuda", "AI": "Anguilla", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica", "AR": "Argentina",
    "AS": "American Samoa", "AT": "Austria", "AU": "Australia", "AW": "Aruba",
    "AX": "Aland Islands", "AZ": "Azerbaijan", "BA": "Bosnia and Herzegovina|Bosnia & Herzegovina|Bosnia-Herzegovina|Bosnia",
    "BB": "Barbados", "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina Faso",
    "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi", "BJ": "Benin",
    "BL": "Saint Barthelemy", "BM": "Bermuda", "BN": "Brunei|Brunei Darussalam",
    "BO": "Bolivia|Bolivia, Plurinational State of|Plurinational State of Bolivia",
    "BQ": "Bonaire, Sint Eustatius and Saba", "BR": "Brazil", "BS": "Bahamas|The Bahamas|Bahamas, The",
    "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana", "BY": "Belarus|Byelarus",
    "BZ": "Belize", "CA": "Canada", "CC": "Cocos (Keeling) Islands|Cocos Islands",
    "CD": "Congo, Democratic Republic of the|Democratic Republic of the Congo|Congo (Kinshasa)|Congo, Dem. Rep.|DR Congo|DRC|Zaire|Congo, The Democratic Republic of the",
    "CF": "Central African Republic", "CG": "Congo|Republic of the Congo|Congo, Republic of the|Congo (Brazzaville)|Congo, Rep.",
    "CH": "Switzerland", "CI": "Cote d'Ivoire|Ivory Coast|Cote dIvoire", "CK": "Cook Islands",
    "CL": "Chile", "CM": "Cameroon", "CN": "China|People's Republic of China|PRC|China, People's Republic of",
    "CO": "Colombia", "CR": "Costa Rica", "CU": "Cuba", "CV": "Cabo Verde|Cape Verde",
    "CW": "Curacao", "CX": "Christmas Island", "CY": "Cyprus", "CZ": "Czechia|Czech Republic",
    "DE": "Germany", "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica",
    "DO": "Dominican Republic", "DZ": "Algeria", "EC": "Ecuador", "EE": "Estonia",
    "EG": "Egypt", "EH": "Western Sahara", "ER": "Eritrea", "ES": "Spain",
    "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji", "FK": "Falkland Islands|Falkland Islands (Malvinas)|Falkland Islands (Islas Malvinas)",
    "FM": "Micronesia|Micronesia, Federated States of|Federated States of Micronesia",
    "FO": "Faroe Islands", "FR": "France", "GA": "Gabon", "GB": "United Kingdom|UK|Great Britain|Britain|England|Scotland|Wales|Northern Ireland|United Kingdom of Great Britain and Northern Ireland",
    "GD": "Grenada", "GE": "Georgia", "GF": "French Guiana", "GG": "Guernsey",
    "GH": "Ghana", "GI": "Gibraltar", "GL": "Greenland", "GM": "Gambia|The Gambia|Gambia, The",
    "GN": "Guinea", "GP": "Guadeloupe", "GQ": "Equatorial Guinea", "GR": "Greece",
    "GS": "South Georgia and the South Sandwich Islands", "GT": "Guatemala", "GU": "Guam",
    "GW": "Guinea-Bissau|Guinea Bissau", "GY": "Guyana", "HK": "Hong Kong|Hong Kong SAR|Hong Kong, China",
    "HM": "Heard Island and McDonald Islands", "HN": "Honduras", "HR": "Croatia", "HT": "Haiti",
    "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland", "IL": "Israel", "IM": "Isle of Man",
    "IN": "India", "IO": "British Indian Ocean Territory", "IQ": "Iraq",
    "IR": "Iran|Iran, Islamic Republic of|Islamic Republic of Iran", "IS": "Iceland", "IT": "Italy",
    "JE": "Jersey", "JM": "Jamaica", "JO": "Jordan", "JP": "Japan", "KE": "Kenya",
    "KG": "Kyrgyzstan|Kyrgyz Republic", "KH": "Cambodia", "KI": "Kiribati", "KM": "Comoros",
    "KN": "Saint Kitts and Nevis|St. Kitts and Nevis|St Kitts and Nevis",
    "KP": "North Korea|Korea, North|Korea, Democratic People's Republic of|Democratic People's Republic of Korea|DPRK|Korea (North)",
    "KR": "South Korea|Korea, South|Korea, Republic of|Republic of Korea|Korea (South)|Korea",
    "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan",
    "LA": "Laos|Lao People's Democratic Republic|Lao PDR", "LB": "Lebanon",
    "LC": "Saint Lucia|St. Lucia|St Lucia", "LI": "Liechtenstein", "LK": "Sri Lanka",
    "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia",
    "LY": "Libya|Libyan Arab Jamahiriya", "MA": "Morocco", "MC": "Monaco",
    "MD": "Moldova|Moldova, Republic of|Republic of Moldova", "ME": "Montenegro",
    "MF": "Saint Martin|Saint Martin (French part)", "MG": "Madagascar", "MH": "Marshall Islands",
    "MK": "North Macedonia|Macedonia|Macedonia, the Former Yugoslav Republic of|The former Yugoslav Republic of Macedonia|FYROM",
    "ML": "Mali", "MM": "Myanmar|Burma", "MN": "Mongolia", "MO": "Macao|Macau|Macao SAR",
    "MP": "Northern Mariana Islands", "MQ": "Martinique", "MR": "Mauritania", "MS": "Montserrat",
    "MT": "Malta", "MU": "Mauritius", "MV": "Maldives", "MW": "Malawi", "MX": "Mexico",
    "MY": "Malaysia", "MZ": "Mozambique", "NA": "Namibia", "NC": "New Caledonia", "NE": "Niger",
    "NF": "Norfolk Island", "NG": "Nigeria", "NI": "Nicaragua", "NL": "Netherlands|The Netherlands|Holland",
    "NO": "Norway", "NP": "Nepal", "NR": "Nauru", "NU": "Niue", "NZ": "New Zealand", "OM": "Oman",
    "PA": "Panama", "PE": "Peru", "PF": "French Polynesia", "PG": "Papua New Guinea",
    "PH": "Philippines|The Philippines", "PK": "Pakistan", "PL": "Poland", "PM": "Saint Pierre and Miquelon",
    "PN": "Pitcairn|Pitcairn Islands", "PR": "Puerto Rico", "PS": "Palestine|State of Palestine|Palestinian Territory|Palestinian Territory, Occupied|West Bank|Gaza Strip|Gaza|West Bank and Gaza",
    "PT": "Portugal", "PW": "Palau", "PY": "Paraguay", "QA": "Qatar", "RE": "Reunion",
    "RO": "Romania", "RS": "Serbia", "RU": "Russia|Russian Federation", "RW": "Rwanda",
    "SA": "Saudi Arabia|Saudi", "SB": "Solomon Islands", "SC": "Seychelles", "SD": "Sudan",
    "SE": "Sweden", "SG": "Singapore", "SH": "Saint Helena|Saint Helena, Ascension and Tristan da Cunha",
    "SI": "Slovenia", "SJ": "Svalbard and Jan Mayen", "SK": "Slovakia|Slovak Republic",
    "SL": "Sierra Leone", "SM": "San Marino", "SN": "Senegal", "SO": "Somalia", "SR": "Suriname",
    "SS": "South Sudan", "ST": "Sao Tome and Principe|Sao Tome & Principe", "SV": "El Salvador",
    "SX": "Sint Maarten|Sint Maarten (Dutch part)", "SY": "Syria|Syrian Arab Republic",
    "SZ": "Eswatini|Swaziland", "TC": "Turks and Caicos Islands", "TD": "Chad",
    "TF": "French Southern Territories", "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan",
    "TK": "Tokelau", "TL": "Timor-Leste|East Timor|Timor Leste", "TM": "Turkmenistan",
    "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey|Turkiye", "TT": "Trinidad and Tobago|Trinidad & Tobago",
    "TV": "Tuvalu", "TW": "Taiwan|Taiwan, Province of China|Chinese Taipei", "TZ": "Tanzania|Tanzania, United Republic of|United Republic of Tanzania",
    "UA": "Ukraine", "UG": "Uganda", "UM": "United States Minor Outlying Islands",
    "US": "United States|United States of America|USA|U.S.|U.S.A.|America", "UY": "Uruguay",
    "UZ": "Uzbekistan", "VA": "Holy See|Vatican City|Vatican|Vatican City State|Holy See (Vatican City State)",
    "VC": "Saint Vincent and the Grenadines|St. Vincent and the Grenadines|St Vincent and the Grenadines",
    "VE": "Venezuela|Venezuela, Bolivarian Republic of|Bolivarian Republic of Venezuela",
    "VG": "British Virgin Islands|Virgin Islands, British", "VI": "U.S. Virgin Islands|Virgin Islands, U.S.|US Virgin Islands|Virgin Islands",
    "VN": "Vietnam|Viet Nam", "VU": "Vanuatu", "WF": "Wallis and Futuna", "WS": "Samoa",
    "XK": "Kosovo", "YE": "Yemen", "YT": "Mayotte", "ZA": "South Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}


def _norm(value: str) -> str:
    """Lower-case, accent-free, punctuation-light key for a country name."""
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("&", " and ").replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9()' ,.-]", " ", text)
    text = text.replace("'", "")
    return re.sub(r"\s+", " ", text).strip(" .,")


_NAME_TO_CODE: dict[str, str] = {}
for _code, _names in _TABLE.items():
    for _name in _names.split("|"):
        _NAME_TO_CODE.setdefault(_norm(_name), _code)


def to_alpha2(value: str | None) -> str | None:
    """ISO 3166-1 alpha-2 for a code or an English country name, else None.

    None means "cannot tell", never "no country": callers must not treat an
    unresolved value as a mismatch.
    """
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) == 2 and text.isalpha() and text.upper() in _TABLE:
        return text.upper()
    return _NAME_TO_CODE.get(_norm(text))
