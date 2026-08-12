"""Proliferation financing classification.

Federal Decree-Law No. 10 of 2025 elevated proliferation financing from a
subset of AML/CFT to a **standalone criminal offence with its own chapter**.
Folding PF hits into generic sanctions alerts understates that: PF carries its
own obligations, its own reporting route, and its own supervisory expectations.

There is no separate PF sanctions list to load. PF designations live inside the
UN and OFAC lists and are distinguished by the **sanctions programme** under
which a target was designated. So classification, not ingestion, is the work:
UNSCR 1718 (DPRK) and 1737/2231 (Iran) are non-proliferation regimes, while
1267/1989/2253 (ISIL & Al-Qaida), 1988 (Taliban) and 1373 (the UAE Local
Terrorist List basis) are counter-terrorism regimes.

Getting this distinction right matters practically: a DPRK procurement network
hit and an ISIL financing hit are both freezable, but they are different
offences with different reports.
"""

from __future__ import annotations

# UN Security Council non-proliferation regimes.
#   1718 - DPRK: nuclear, ballistic missile and WMD programmes
#   1737 - Iran: nuclear programme (superseded by 2231 but still carried)
#   2231 - Iran: JCPOA implementation, successor to 1737
PF_PROGRAM_PREFIXES: tuple[str, ...] = (
    "UN-SC1718",
    "UN-SC1737",
    "UN-SC2231",
)

# OFAC programme codes covering WMD proliferation and related procurement.
#   NPWMD - Non-Proliferation of Weapons of Mass Destruction
#   DPRK* - North Korea regimes
#   IFSR / IRAN* - Iran, where proliferation-linked
PF_OFAC_CODES: tuple[str, ...] = (
    "NPWMD", "DPRK", "DPRK2", "DPRK3", "DPRK4",
    "NPWMD-EO13382", "IFSR", "IRAN-TRA", "MBS",
)

# Counter-terrorism regimes. Listed explicitly so the two are never conflated
# by accident, and so an unrecognised programme is treated as neither rather
# than silently defaulting into one.
CT_PROGRAM_PREFIXES: tuple[str, ...] = (
    "UN-SCISIL",   # ISIL (Da'esh) & Al-Qaida, res. 1267/1989/2253
    "UN-SC1988",   # Taliban
    "AE-UNSC1373", # UAE Local Terrorist List, res. 1373 basis
)


def classify_programs(programs: list[str] | None) -> set[str]:
    """Map sanction programme identifiers to risk categories.

    Returns any of {"proliferation", "terrorism"}. An empty set means the
    designation is under a country or conflict regime that is neither -- for
    example Libya (1970) or DRC (1533) -- which is still a sanctions match, it
    is simply not a PF or CT one.
    """
    found: set[str] = set()
    for p in programs or []:
        code = (p or "").strip().upper()
        if not code:
            continue
        if any(code.startswith(x) for x in PF_PROGRAM_PREFIXES):
            found.add("proliferation")
        elif any(code == x or code.startswith(x + "-") for x in PF_OFAC_CODES):
            found.add("proliferation")
        elif any(code.startswith(x) for x in CT_PROGRAM_PREFIXES):
            found.add("terrorism")
    return found


def is_proliferation(programs: list[str] | None) -> bool:
    return "proliferation" in classify_programs(programs)


def is_terrorism(programs: list[str] | None) -> bool:
    return "terrorism" in classify_programs(programs)


def obligation_note(categories: set[str]) -> str:
    """Plain-language statement of what the match obliges, for the alert record.

    Written out rather than left implicit because the operator acting on the
    alert may not be the person who knows the difference between these regimes.
    """
    if "proliferation" in categories:
        return (
            "PROLIFERATION FINANCING match. Standalone offence under Federal "
            "Decree-Law No. 10 of 2025. Freeze without delay and without prior "
            "notice; report to the supervisory authority and file via goAML. "
            "Do not tip off."
        )
    if "terrorism" in categories:
        return (
            "TERRORISM FINANCING match. Freeze without delay and without prior "
            "notice; report to the supervisory authority and file via goAML. "
            "Do not tip off."
        )
    return (
        "SANCTIONS match. Freeze without delay and without prior notice; report "
        "to the supervisory authority. Do not tip off."
    )
