import io
import os
import pandas as pd
import logging
import math
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from app.services.llm import LLMService

logger = logging.getLogger("block_credit")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 17(5) STATUTORY HSN/SAC MASTER TABLE
# Keys are 4-digit HSN/SAC prefixes.  Values: (status, reason)
# status ∈ {"BLOCKED", "ELIGIBLE", "NEEDS_REVIEW"}
# ─────────────────────────────────────────────────────────────────────────────
SECTION_17_5_HSN_MAP: Dict[str, Tuple[str, str]] = {

    # ── Motor Vehicles & Conveyances — Sec 17(5)(a) ───────────────────────
    "8702": ("BLOCKED",      "Motor vehicle (10+ persons) — Sec 17(5)(a)"),
    "8703": ("NEEDS_REVIEW", "Passenger motor vehicle — Blocked unless used for further supply / passenger transport / driver training — Sec 17(5)(a)"),
    "8704": ("ELIGIBLE",     "Motor vehicle for goods transport — Eligible — Sec 17(5)(a) exception"),
    "8705": ("ELIGIBLE",     "Special purpose vehicle (crane/fire engine etc.) — Eligible"),
    "8706": ("NEEDS_REVIEW", "Chassis for motor vehicle — Verify end-use vehicle type — Sec 17(5)(a)"),
    "8711": ("NEEDS_REVIEW", "Motorcycle/scooter — Verify if business or personal use — Sec 17(5)(a)"),
    "8714": ("NEEDS_REVIEW", "Parts/accessories for motor vehicle — Verify vehicle type — Sec 17(5)(a)"),
    "8716": ("ELIGIBLE",     "Trailer/semi-trailer for goods transport — Eligible"),
    "8708": ("NEEDS_REVIEW", "Motor vehicle parts — Verify if for goods carrier (Eligible) or passenger vehicle (Blocked) — Sec 17(5)(a)"),

    # ── Food, Beverages & Catering — Sec 17(5)(b)(i) ─────────────────────
    "0901": ("BLOCKED",      "Coffee — Food item — Sec 17(5)(b)(i)"),
    "0902": ("BLOCKED",      "Tea — Food item — Sec 17(5)(b)(i)"),
    "1006": ("BLOCKED",      "Rice/food grain — Food item — Sec 17(5)(b)(i)"),
    "1601": ("BLOCKED",      "Meat/sausages — Food item — Sec 17(5)(b)(i)"),
    "2101": ("BLOCKED",      "Coffee/tea extracts — Food item — Sec 17(5)(b)(i)"),
    "2201": ("BLOCKED",      "Water/mineral water — Food item — Sec 17(5)(b)(i)"),
    "2202": ("BLOCKED",      "Soft drinks/beverages — Food item — Sec 17(5)(b)(i)"),
    "2203": ("BLOCKED",      "Beer — Alcoholic beverage — Sec 17(5)(b)(i)"),
    "2204": ("BLOCKED",      "Wine — Alcoholic beverage — Sec 17(5)(b)(i)"),
    "2208": ("BLOCKED",      "Spirits/liquor — Alcoholic beverage — Sec 17(5)(b)(i)"),
    "9963": ("NEEDS_REVIEW", "Restaurant / outdoor catering services — Blocked unless same line of business — Sec 17(5)(b)(i)"),

    # ── Club, Fitness, Beauty, Health — Sec 17(5)(b)(ii) & (iii) ─────────
    "9995": ("BLOCKED",      "Club / fitness centre membership — Always blocked — Sec 17(5)(b)(ii)"),
    "9996": ("BLOCKED",      "Recreational / sports club activities — Always blocked — Sec 17(5)(b)(ii)"),
    "3304": ("BLOCKED",      "Beauty / cosmetic products — Sec 17(5)(b)(iii)"),
    "3305": ("BLOCKED",      "Hair care products — Sec 17(5)(b)(iii)"),
    "3401": ("BLOCKED",      "Soap / personal care products — Personal consumption — Sec 17(5)(g)"),
    "9993": ("NEEDS_REVIEW", "Health / medical services — Blocked if employee welfare; verify statutory obligation — Sec 17(5)(b)(iii)"),

    # ── Rent-a-Cab — Sec 17(5)(b)(ii) ────────────────────────────────────
    "9966": ("NEEDS_REVIEW", "Cab / taxi rental (rent-a-cab) — Blocked unless statutory obligation to provide to employees — Sec 17(5)(b)(ii)"),

    # ── Life / Health Insurance — Sec 17(5)(b)(iii) ───────────────────────
    "9971": ("NEEDS_REVIEW", "Insurance services — Health/life: Blocked unless statutory obligation; Marine/cargo/property: Eligible — Sec 17(5)(b)(iii)"),

    # ── Passenger Transport / Air Travel — Sec 17(5)(b)(ii) ──────────────
    "9964": ("NEEDS_REVIEW", "Passenger transport (air/rail/road) — Business travel: verify not vacation/LTC — Sec 17(5)(b)(ii)"),

    # ── GTA / Goods Transport — Eligible with RCM caveat ─────────────────
    "9965": ("NEEDS_REVIEW", "GTA / goods transport — Eligible on forward charge; RCM: verify compliance — Sec 17(5) exception"),

    # ── Works Contract / Construction — Sec 17(5)(c) & (d) ───────────────
    "9954": ("NEEDS_REVIEW", "Works contract / construction — Blocked for immovable property; Eligible for plant & machinery — Sec 17(5)(c)/(d)"),
    "9955": ("NEEDS_REVIEW", "Construction sub-contract — Same as 9954 — verify nature of property — Sec 17(5)(c)/(d)"),

    # ── Gifts / Samples / Freebies — Sec 17(5)(h) ────────────────────────
    "9999": ("BLOCKED",      "Gifts / samples / free supplies — Always blocked — Sec 17(5)(h)"),

    # ── Telecom & IT — Eligible ───────────────────────────────────────────
    "9984": ("ELIGIBLE",     "Telecom / internet services — Business operational input — Eligible"),
    "9983": ("ELIGIBLE",     "Professional / consulting / IT services — Business input — Eligible"),
    "9982": ("ELIGIBLE",     "Legal services — Professional input — Eligible"),
    "9985": ("ELIGIBLE",     "Support services (staffing / security / facility) — Business input — Eligible"),
    "9987": ("ELIGIBLE",     "Maintenance & repair services — Business input — Eligible (unless passenger vehicle)"),
    "9988": ("ELIGIBLE",     "Manufacturing services on job-work basis — Business input — Eligible"),
    "9989": ("ELIGIBLE",     "Publishing / printing services — Business input — Eligible"),
    "9991": ("ELIGIBLE",     "Government / public administration services — Eligible"),
    "9997": ("ELIGIBLE",     "Other miscellaneous services — Likely eligible; verify nature"),

    # ── Capital Goods / Office Equipment — Eligible ───────────────────────
    "8471": ("ELIGIBLE",     "Computers / laptops — Capital goods for business use — Eligible"),
    "8473": ("ELIGIBLE",     "Computer parts / peripherals — Business use — Eligible"),
    "8517": ("ELIGIBLE",     "Phones / communication equipment — Business use — Eligible"),
    "8528": ("NEEDS_REVIEW", "TV / monitors — Verify office use vs personal/home — Sec 17(5)(g)"),
    "8504": ("ELIGIBLE",     "Power supply / UPS — Capital goods — Eligible"),
    "8443": ("ELIGIBLE",     "Printers / photocopiers — Office equipment — Eligible"),
    "4820": ("ELIGIBLE",     "Stationery / office supplies — Operational input — Eligible"),

    # ── Furniture ─────────────────────────────────────────────────────────
    "9401": ("NEEDS_REVIEW", "Seating furniture — Verify office use (Eligible) vs personal/guest house (Blocked) — Sec 17(5)(g)"),
    "9403": ("NEEDS_REVIEW", "Office furniture — Generally eligible; verify not for residential premises — Sec 17(5)(g)"),

    # ── Real Estate / Renting ─────────────────────────────────────────────
    "9972": ("NEEDS_REVIEW", "Real estate / renting services — Office rent: Eligible; Residential: Blocked — Sec 17(5)(g)"),
}


# ─────────────────────────────────────────────────────────────────────────────
# SUPPLIER INTELLIGENCE TABLE
# Maps partial supplier name keywords → (inferred_service_type, status, reason)
# Used when HSN is absent — resolves well-known Indian companies directly
# without burning AI tokens on obvious cases.
# Keywords are lowercase; matched with 'in' against the lowercased supplier name.
# ─────────────────────────────────────────────────────────────────────────────
SUPPLIER_INTELLIGENCE: List[Tuple[str, str, str, str]] = [
    # ── IT / Software / Consulting ────────────────────────────────────────
    # (keyword, service_type_label, status, reason)
    ("infosys",          "IT/BPM services",            "ELIGIBLE", "IT / BPM services — professional business input — Eligible"),
    ("wipro",            "IT services",                "ELIGIBLE", "IT services / consulting — professional business input — Eligible"),
    ("tata consultancy", "IT services",                "ELIGIBLE", "IT services / consulting — professional business input — Eligible"),
    (" tcs ",            "IT services",                "ELIGIBLE", "IT services / consulting — professional business input — Eligible"),
    ("hcl tech",         "IT services",                "ELIGIBLE", "IT services — professional business input — Eligible"),
    ("hcl infosys",      "IT services",                "ELIGIBLE", "IT services — professional business input — Eligible"),
    ("l&t infotech",     "IT services",                "ELIGIBLE", "IT services / engineering — professional business input — Eligible"),
    ("ltimindtree",      "IT services",                "ELIGIBLE", "IT services — professional business input — Eligible"),
    ("mphasis",          "IT services",                "ELIGIBLE", "IT services — professional business input — Eligible"),
    ("tech mahindra",    "IT services",                "ELIGIBLE", "IT services — professional business input — Eligible"),
    ("cognizant",        "IT services",                "ELIGIBLE", "IT services / consulting — professional business input — Eligible"),
    ("accenture",        "IT/consulting services",     "ELIGIBLE", "IT / management consulting — professional business input — Eligible"),
    ("capgemini",        "IT/consulting services",     "ELIGIBLE", "IT / management consulting — professional business input — Eligible"),
    ("ibm india",        "IT services",                "ELIGIBLE", "IT services — professional business input — Eligible"),
    ("oracle india",     "Software/cloud services",    "ELIGIBLE", "Software license / cloud services — business use — Eligible"),
    ("microsoft india",  "Software/cloud services",    "ELIGIBLE", "Software license / cloud services — business use — Eligible"),
    ("sap india",        "Software/ERP services",      "ELIGIBLE", "ERP software services — professional business input — Eligible"),
    ("adobe",            "Software services",          "ELIGIBLE", "Software license / SaaS — business use — Eligible"),
    ("salesforce",       "CRM/cloud services",         "ELIGIBLE", "CRM / cloud software services — business use — Eligible"),
    ("zoho",             "Software/SaaS services",     "ELIGIBLE", "Software / SaaS services — business use — Eligible"),

    # ── E-Commerce / Marketplace ──────────────────────────────────────────
    ("amazon seller",    "E-commerce marketplace",     "ELIGIBLE", "E-commerce marketplace / cloud services — business input — Eligible"),
    ("amazon web",       "Cloud/AWS services",         "ELIGIBLE", "AWS / cloud services — business operational input — Eligible"),
    ("flipkart",         "E-commerce marketplace",     "ELIGIBLE", "E-commerce marketplace services — business input — Eligible"),
    ("myntra",           "E-commerce marketplace",     "NEEDS_REVIEW", "E-commerce platform — verify: office supplies (Eligible) vs personal goods — Sec 17(5)(g)"),
    ("nykaa",            "Beauty/personal care retail","NEEDS_REVIEW", "Beauty / personal care platform — likely personal consumption — verify Sec 17(5)(b)(iii)/(g)"),
    ("swiggy",           "Food delivery",              "BLOCKED",  "Food / outdoor catering delivery — Sec 17(5)(b)(i)"),
    ("zomato",           "Food delivery",              "BLOCKED",  "Food / outdoor catering delivery — Sec 17(5)(b)(i)"),

    # ── Telecom ───────────────────────────────────────────────────────────
    ("airtel",           "Telecom services",           "ELIGIBLE", "Telecom / internet services (SAC 9984) — business operational input — Eligible"),
    ("jio",              "Telecom services",           "ELIGIBLE", "Telecom / internet services (SAC 9984) — business operational input — Eligible"),
    ("vodafone",         "Telecom services",           "ELIGIBLE", "Telecom / internet services (SAC 9984) — business operational input — Eligible"),
    ("vi ",              "Telecom services",           "ELIGIBLE", "Telecom / internet services (SAC 9984) — business operational input — Eligible"),
    ("bsnl",             "Telecom services",           "ELIGIBLE", "Telecom / internet services (SAC 9984) — business operational input — Eligible"),
    ("tata communications", "Telecom services",        "ELIGIBLE", "Telecom / connectivity services (SAC 9984) — business operational input — Eligible"),

    # ── Banking & Financial Services ──────────────────────────────────────
    ("hdfc bank",        "Bank charges",               "ELIGIBLE", "Bank charges / financial services — business operational input — Eligible"),
    ("icici bank",       "Bank charges",               "ELIGIBLE", "Bank charges / financial services — business operational input — Eligible"),
    ("axis bank",        "Bank charges",               "ELIGIBLE", "Bank charges / financial services — business operational input — Eligible"),
    ("sbi ",             "Bank charges",               "ELIGIBLE", "Bank charges / financial services — business operational input — Eligible"),
    ("state bank",       "Bank charges",               "ELIGIBLE", "Bank charges / financial services — business operational input — Eligible"),
    ("kotak",            "Bank charges",               "ELIGIBLE", "Bank charges / financial services — business operational input — Eligible"),
    ("yes bank",         "Bank charges",               "ELIGIBLE", "Bank charges / financial services — business operational input — Eligible"),
    ("indusind",         "Bank charges",               "ELIGIBLE", "Bank charges / financial services — business operational input — Eligible"),

    # ── Insurance ─────────────────────────────────────────────────────────
    ("lic ",             "Life insurance",             "NEEDS_REVIEW", "Life insurance (LIC) — Blocked unless statutory obligation to employees — verify Sec 17(5)(b)(iii)"),
    ("life insurance",   "Life insurance",             "NEEDS_REVIEW", "Life insurance — Blocked unless statutory obligation to employees — verify Sec 17(5)(b)(iii)"),
    ("health insurance", "Health insurance",           "NEEDS_REVIEW", "Health insurance — Blocked unless statutory obligation to employees — verify Sec 17(5)(b)(iii)"),
    ("star health",      "Health insurance",           "NEEDS_REVIEW", "Health insurance — Blocked unless statutory obligation to employees — verify Sec 17(5)(b)(iii)"),
    ("new india assurance","General insurance",        "NEEDS_REVIEW", "General insurance — marine/cargo/property: Eligible; health/life: Blocked — verify type — Sec 17(5)(b)(iii)"),
    ("united india",     "General insurance",          "NEEDS_REVIEW", "General insurance — marine/cargo/property: Eligible; health/life: Blocked — verify type — Sec 17(5)(b)(iii)"),
    ("bajaj allianz",    "General insurance",          "NEEDS_REVIEW", "General insurance — marine/cargo/property: Eligible; health/life: Blocked — verify type — Sec 17(5)(b)(iii)"),
    ("hdfc ergo",        "General insurance",          "NEEDS_REVIEW", "General insurance — marine/cargo/property: Eligible; health/life: Blocked — verify type — Sec 17(5)(b)(iii)"),
    ("icici lombard",    "General insurance",          "NEEDS_REVIEW", "General insurance — marine/cargo/property: Eligible; health/life: Blocked — verify type — Sec 17(5)(b)(iii)"),
    ("tata aig",         "General insurance",          "NEEDS_REVIEW", "General insurance — marine/cargo/property: Eligible; health/life: Blocked — verify type — Sec 17(5)(b)(iii)"),

    # ── Automobiles (potential Sec 17(5)(a) risk) ─────────────────────────
    ("mahindra & mahindra", "Automobile manufacturer", "NEEDS_REVIEW", "Auto manufacturer — verify if vehicle purchase (BLOCKED for passenger/Sec 17(5)(a)) or spare parts for goods vehicle (Eligible)"),
    ("mahindra and mahindra","Automobile manufacturer","NEEDS_REVIEW", "Auto manufacturer — verify if vehicle purchase (BLOCKED for passenger/Sec 17(5)(a)) or spare parts for goods vehicle (Eligible)"),
    ("maruti",           "Automobile manufacturer",    "NEEDS_REVIEW", "Automobile — verify: passenger vehicle (BLOCKED — Sec 17(5)(a)) vs goods vehicle (Eligible)"),
    ("tata motors",      "Automobile manufacturer",    "NEEDS_REVIEW", "Automobile — verify: passenger vehicle (BLOCKED — Sec 17(5)(a)) vs goods vehicle or further supply (Eligible)"),
    ("hyundai",          "Automobile manufacturer",    "NEEDS_REVIEW", "Automobile — verify: passenger vehicle (BLOCKED — Sec 17(5)(a)) vs goods vehicle (Eligible)"),
    ("honda cars",       "Automobile manufacturer",    "NEEDS_REVIEW", "Automobile — verify: passenger vehicle (BLOCKED — Sec 17(5)(a)) vs goods vehicle (Eligible)"),
    ("toyota",           "Automobile manufacturer",    "NEEDS_REVIEW", "Automobile — verify: passenger vehicle (BLOCKED — Sec 17(5)(a)) vs goods vehicle (Eligible)"),
    ("ashok leyland",    "Commercial vehicles",        "ELIGIBLE",  "Commercial / goods transport vehicles — Eligible — Sec 17(5)(a) exception"),
    ("eicher",           "Commercial vehicles",        "ELIGIBLE",  "Commercial / goods transport vehicles (trucks/buses) — Eligible — Sec 17(5)(a) exception"),

    # ── Office Equipment & Electronics ────────────────────────────────────
    ("hp india",         "IT hardware",                "ELIGIBLE", "IT hardware / printers — office equipment — Eligible"),
    ("dell india",       "IT hardware",                "ELIGIBLE", "IT hardware / computers — capital goods for business — Eligible"),
    ("lenovo",           "IT hardware",                "ELIGIBLE", "IT hardware / computers — capital goods for business — Eligible"),
    ("apple india",      "IT hardware",                "NEEDS_REVIEW", "Apple hardware — verify: business use (Eligible) vs personal (Blocked — Sec 17(5)(g))"),
    ("samsung india",    "Electronics",                "NEEDS_REVIEW", "Electronics — verify: business equipment (Eligible) vs personal/home use (Blocked — Sec 17(5)(g))"),
    ("lg electronics",   "Electronics",                "NEEDS_REVIEW", "Electronics — verify: office equipment (Eligible) vs personal/home use (Blocked — Sec 17(5)(g))"),
    ("canon india",      "Office equipment",           "ELIGIBLE", "Printers / cameras — office equipment — Eligible"),
    ("epson",            "Office equipment",           "ELIGIBLE", "Printers / scanners — office equipment — Eligible"),

    # ── Construction / Interiors ──────────────────────────────────────────
    ("l&t construction", "Construction services",      "NEEDS_REVIEW", "Construction / works contract — BLOCKED for immovable property; Eligible for plant & machinery — verify Sec 17(5)(c)/(d)"),
    ("godrej & boyce",   "Industrial goods/appliances","NEEDS_REVIEW", "Industrial / electrical equipment — verify: capital goods for factory/office (Eligible) vs personal (Blocked — Sec 17(5)(g))"),
    ("godrej",           "Industrial goods",           "NEEDS_REVIEW", "Godrej products — verify: office/industrial equipment (Eligible) vs personal/consumer goods (Blocked — Sec 17(5)(g))"),
    ("asian paints",     "Paints",                     "NEEDS_REVIEW", "Paints — verify: factory/office painting (Eligible) vs residential/personal (Blocked — Sec 17(5)(g)/(c))"),
    ("berger paints",    "Paints",                     "NEEDS_REVIEW", "Paints — verify: factory/office painting (Eligible) vs residential/personal (Blocked — Sec 17(5)(g)/(c))"),
    ("nerolac",          "Paints",                     "NEEDS_REVIEW", "Paints — verify: factory/office painting (Eligible) vs residential/personal (Blocked — Sec 17(5)(g)/(c))"),
    ("pidilite",         "Adhesives/construction",     "NEEDS_REVIEW", "Construction chemicals/adhesives — verify: industrial use (Eligible) vs immovable property construction (Blocked — Sec 17(5)(c))"),

    # ── Electrical Goods ─────────────────────────────────────────────────
    ("bajaj electricals","Electrical goods",           "NEEDS_REVIEW", "Electrical goods / appliances — verify: industrial/office equipment (Eligible) vs personal/home appliances (Blocked — Sec 17(5)(g))"),
    ("havells",          "Electrical goods",           "NEEDS_REVIEW", "Electrical goods — verify: wiring/industrial use (Eligible) vs personal appliances (Blocked — Sec 17(5)(g))"),
    ("polycab",          "Electrical cables/goods",    "ELIGIBLE",  "Electrical cables / wiring material — industrial/office input — Eligible"),
    ("siemens india",    "Industrial electrical",      "ELIGIBLE",  "Industrial electrical equipment — capital goods — Eligible"),
    ("abb india",        "Industrial electrical",      "ELIGIBLE",  "Industrial automation / electrical equipment — capital goods — Eligible"),
    ("schneider",        "Industrial electrical",      "ELIGIBLE",  "Industrial electrical / automation equipment — capital goods — Eligible"),

    # ── Logistics / Transport ─────────────────────────────────────────────
    ("blue dart",        "Courier services",           "ELIGIBLE", "Courier / express logistics services — business operational input — Eligible"),
    ("dhl",              "Courier services",           "ELIGIBLE", "International / domestic courier services — business operational input — Eligible"),
    ("fedex",            "Courier services",           "ELIGIBLE", "Courier services — business operational input — Eligible"),
    ("dtdc",             "Courier services",           "ELIGIBLE", "Courier / delivery services — business operational input — Eligible"),
    ("gati",             "Logistics services",         "NEEDS_REVIEW", "GTA / logistics services — Eligible on forward charge; verify RCM compliance — Sec 17(5) exception"),
    ("transport corporation", "GTA services",          "NEEDS_REVIEW", "GTA services — Eligible on forward charge; verify RCM compliance — Sec 17(5) exception"),
    ("tci ",             "GTA services",               "NEEDS_REVIEW", "GTA services — Eligible on forward charge; verify RCM compliance — Sec 17(5) exception"),
    ("safexpress",       "Logistics services",         "NEEDS_REVIEW", "GTA / logistics services — Eligible on forward charge; verify RCM compliance — Sec 17(5) exception"),

    # ── Professional Services ─────────────────────────────────────────────
    ("deloitte",         "Professional/audit services","ELIGIBLE", "Audit / consulting services — professional business input — Eligible"),
    ("ernst & young",    "Professional/audit services","ELIGIBLE", "Audit / consulting services — professional business input — Eligible"),
    ("kpmg",             "Professional/audit services","ELIGIBLE", "Audit / consulting services — professional business input — Eligible"),
    ("pwc",              "Professional/audit services","ELIGIBLE", "Audit / consulting services — professional business input — Eligible"),
    ("price waterhouse", "Professional/audit services","ELIGIBLE", "Audit / consulting services — professional business input — Eligible"),
    ("grant thornton",   "Professional/audit services","ELIGIBLE", "Audit / consulting services — professional business input — Eligible"),
    ("bdo india",        "Professional/audit services","ELIGIBLE", "Audit / consulting services — professional business input — Eligible"),

    # ── Office Supplies / Stationery ──────────────────────────────────────
    ("staples",          "Office supplies",            "ELIGIBLE", "Office stationery / supplies — operational input — Eligible"),
    ("3m india",         "Office/industrial supplies", "ELIGIBLE", "Office / industrial supplies — operational input — Eligible"),
    ("camlin",           "Stationery",                 "ELIGIBLE", "Stationery / art supplies — office input — Eligible"),
    ("faber-castell",    "Stationery",                 "ELIGIBLE", "Stationery — office input — Eligible"),

    # ── Hotels / Travel (potential Sec 17(5) risk) ────────────────────────
    ("oyo",              "Hotel accommodation",        "NEEDS_REVIEW", "Hotel accommodation — verify: business travel (Eligible) vs vacation/LTC (Blocked — Sec 17(5)(b)(ii))"),
    ("taj hotels",       "Hotel accommodation",        "NEEDS_REVIEW", "Hotel accommodation — verify: business travel (Eligible) vs vacation/LTC (Blocked — Sec 17(5)(b)(ii))"),
    ("ihg",              "Hotel accommodation",        "NEEDS_REVIEW", "Hotel accommodation — verify: business travel (Eligible) vs vacation/LTC (Blocked — Sec 17(5)(b)(ii))"),
    ("marriott",         "Hotel accommodation",        "NEEDS_REVIEW", "Hotel accommodation — verify: business travel (Eligible) vs vacation/LTC (Blocked — Sec 17(5)(b)(ii))"),
    ("make my trip",     "Travel booking",             "NEEDS_REVIEW", "Travel booking — verify: business travel tickets (Eligible) vs vacation/LTC (Blocked — Sec 17(5)(b)(ii))"),
    ("cleartrip",        "Travel booking",             "NEEDS_REVIEW", "Travel booking — verify: business travel tickets (Eligible) vs vacation/LTC (Blocked — Sec 17(5)(b)(ii))"),
    ("irctc",            "Rail travel",                "NEEDS_REVIEW", "Rail travel booking — verify: business travel (Eligible) vs vacation/LTC (Blocked — Sec 17(5)(b)(ii))"),

    # ── Fuel / Petrol ─────────────────────────────────────────────────────
    ("indian oil",       "Petroleum products",         "NEEDS_REVIEW", "Petroleum products — GST not applicable on petrol/diesel; verify if LPG/CNG for industry (Eligible) or motor vehicle fuel"),
    ("bharat petroleum", "Petroleum products",         "NEEDS_REVIEW", "Petroleum products — GST not applicable on petrol/diesel; verify if LPG/CNG for industry (Eligible) or motor vehicle fuel"),
    ("hindustan petroleum","Petroleum products",       "NEEDS_REVIEW", "Petroleum products — GST not applicable on petrol/diesel; verify if LPG/CNG for industry (Eligible) or motor vehicle fuel"),
    ("reliance petroleum","Petroleum products",        "NEEDS_REVIEW", "Petroleum products — verify nature: industrial LPG/CNG (Eligible) vs motor fuel (GST not applicable)"),

    # ── Retail (ambiguous — depends on what was bought) ───────────────────
    ("reliance retail",  "Retail purchase",            "NEEDS_REVIEW", "Retail purchase — verify nature: office supplies / business goods (Eligible) vs personal goods (Blocked — Sec 17(5)(g))"),
    ("d-mart",           "Retail purchase",            "NEEDS_REVIEW", "Retail purchase — verify nature: office supplies (Eligible) vs food/personal goods (Blocked — Sec 17(5)(b)(i)/(g))"),
    ("big bazaar",       "Retail purchase",            "NEEDS_REVIEW", "Retail purchase — verify nature: office supplies (Eligible) vs food/personal goods (Blocked — Sec 17(5)(b)(i)/(g))"),
    ("spencer",          "Retail purchase",            "NEEDS_REVIEW", "Retail purchase — verify nature: office supplies (Eligible) vs food/personal goods (Blocked — Sec 17(5)(b)(i)/(g))"),
]


def lookup_supplier_itc(supplier_name: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Match supplier name against SUPPLIER_INTELLIGENCE table.
    Returns (status, reason, matched).
    Tries longest keyword match first to prefer specific entries over generic ones.
    """
    if not supplier_name or str(supplier_name).strip() in ("", "nan", "None"):
        return None, None, False

    name_lower = " " + str(supplier_name).strip().lower() + " "

    # Sort by keyword length descending — longer/more specific keywords win
    sorted_rules = sorted(SUPPLIER_INTELLIGENCE, key=lambda x: len(x[0]), reverse=True)

    for keyword, _service_type, status, reason in sorted_rules:
        if keyword.lower() in name_lower:
            return status, reason, True

    return None, None, False


def lookup_hsn_itc(hsn_code: Any) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Look up ITC status for an HSN/SAC code against Section 17(5) master table.
    Tries 8-digit → 6-digit → 4-digit prefix.

    Returns:
        (status, reason, matched)
        matched=False means no entry found — caller should fall back to AI.
    """
    if not hsn_code or str(hsn_code).strip() in ("", "nan", "None", "-"):
        return None, None, False

    clean = str(hsn_code).strip().replace(".", "").replace(" ", "").split(".")[0]

    for length in (8, 6, 4):
        prefix = clean[:length]
        if prefix in SECTION_17_5_HSN_MAP:
            status, reason = SECTION_17_5_HSN_MAP[prefix]
            return status, reason, True

    return None, None, False


# ─────────────────────────────────────────────────────────────────────────────
# AI ANALYSIS  (unchanged interface — only called for rows HSN couldn't resolve)
# ─────────────────────────────────────────────────────────────────────────────

async def analyze_items_with_ai(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Use LLM to classify ITC eligibility for items that couldn't be resolved
    by HSN lookup.  Returns items with 'itc_status' and 'blocking_reason' set.
    """
    if not items:
        return []

    system_prompt = """
You are an expert Indian GST Compliance Auditor with deep knowledge of Section 17(5) of the CGST Act.

IMPORTANT CONTEXT: The input you receive is a Purchase Register. Each item is a SUPPLIER NAME (company name)
and optionally an HSN/SAC code. You must reason from the supplier's known business activity to determine
what goods/services they likely supplied, and then classify ITC eligibility accordingly.

CLASSIFICATION — use exactly one of:
- "BLOCKED"      — ITC clearly blocked under Section 17(5). No ambiguity.
- "ELIGIBLE"     — ITC clearly eligible. Standard business input, no restrictions.
- "NEEDS_REVIEW" — Eligibility depends on conditions not determinable from the name alone. Human verification needed.

SECTION 17(5) — ITC IS BLOCKED ON:
1. Motor vehicles (< 13 persons) — BLOCKED unless: (a) further supply, (b) passenger transport business, (c) driver training.
2. Food, beverages, outdoor catering, beauty treatment, health services, cosmetic surgery — BLOCKED (unless output service).
3. Club / health & fitness centre memberships — Always BLOCKED.
4. Rent-a-cab, life insurance, health insurance — BLOCKED unless statutory obligation to provide to employees.
5. Employee vacation travel / LTC — Always BLOCKED. Business travel → NEEDS_REVIEW.
6. Works contract for immovable property — BLOCKED (plant & machinery is ELIGIBLE).
7. Personal consumption goods/services — BLOCKED.
8. Gifts, samples, free supplies — Always BLOCKED.

SUPPLIER-NAME REASONING RULES (apply these when HSN is absent):
- IT/Software companies (Infosys, Wipro, TCS, HCL, Cognizant, etc.) → SAC 9983 → ELIGIBLE: "IT/software services — professional business input — Eligible"
- Cloud/SaaS providers (Microsoft, Oracle, Salesforce, Adobe, Zoho) → SAC 9983 → ELIGIBLE: "Software/cloud services — business use — Eligible"
- Telecom operators (Airtel, Jio, Vodafone, BSNL) → SAC 9984 → ELIGIBLE: "Telecom/internet services — business operational input — Eligible"
- Banks (HDFC Bank, ICICI Bank, Axis Bank, Kotak) → SAC 9971 → ELIGIBLE: "Bank charges/financial services — business operational input — Eligible"
- Courier/logistics (Blue Dart, DHL, FedEx, DTDC) → SAC 9965 → ELIGIBLE: "Courier/logistics services — business operational input — Eligible"
- Audit/consulting firms (Deloitte, EY, KPMG, PwC, Grant Thornton) → SAC 9982/9983 → ELIGIBLE: "Professional audit/consulting services — Eligible"
- Food delivery apps (Swiggy, Zomato) → SAC 9963 → BLOCKED: "Food/catering delivery — Sec 17(5)(b)(i)"
- Automobile manufacturers (Mahindra, Maruti, Hyundai, Toyota, Honda Cars) → NEEDS_REVIEW: "Verify if passenger vehicle (Blocked — Sec 17(5)(a)) or goods vehicle / spare parts (Eligible)"
- Retail chains buying mixed goods (Reliance Retail, D-Mart, Big Bazaar) → NEEDS_REVIEW: "Verify: office/business supplies (Eligible) vs personal goods/food (Blocked — Sec 17(5)(g)/(b)(i))"
- Insurance companies → NEEDS_REVIEW: "Verify type — health/life: Blocked unless statutory; marine/cargo/property: Eligible — Sec 17(5)(b)(iii)"
- Hotels/travel booking → NEEDS_REVIEW: "Verify: business travel (Eligible) vs vacation/LTC (Blocked — Sec 17(5)(b)(ii))"
- Paint companies (Asian Paints, Berger, Nerolac) → NEEDS_REVIEW: "Verify: factory/office painting (Eligible) vs residential (Blocked — Sec 17(5)(c)/(g))"

REASONING RULES — MANDATORY:
- NEVER output generic reasons like "Verify nature of services" or "eligibility depends on specific business input use".
- ALWAYS name the specific service type the supplier is known for.
- ALWAYS end the reason with the relevant clause e.g. "— Sec 17(5)(a)" or "— Eligible".
- For NEEDS_REVIEW: state specifically WHAT needs to be verified and WHY it matters.

Return a JSON array of objects with keys: "status", "reason".
Do not include any other text outside the JSON array.
"""

    formatted_items = "\n".join(
        [f"- {i.get('description', '')} (HSN: {i.get('hsn', 'N/A')})" for i in items]
    )
    user_message = f"ITEMS TO ANALYZE:\n{formatted_items}"

    response = await LLMService.generate_response(system_prompt, user_message)

    try:
        clean_json = response.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:-3].strip()
        elif clean_json.startswith("```"):
            clean_json = clean_json[3:-3].strip()

        classifications = json.loads(clean_json)

        for i, cls in enumerate(classifications):
            if i < len(items):
                items[i]["itc_status"] = cls.get("status", "UNKNOWN")
                items[i]["blocking_reason"] = cls.get("reason", "Analysis failed")
                items[i]["itc_source"] = "AI"

        return items

    except Exception as e:
        logger.error(f"Failed to parse AI response: {e}\nResponse: {response}")
        for item in items:
            item["itc_status"] = "NEEDS_REVIEW"
            item["blocking_reason"] = "AI analysis failed — manual verification required"
            item["itc_source"] = "ERROR"
        return items


# ─────────────────────────────────────────────────────────────────────────────
# MAIN JOB ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def process_block_credit_job(
    input_bytes_list: List[bytes], filenames: List[str]
) -> bytes:
    """
    Main entry point for AI Block Credit job.

    Pipeline:
    1.  Identify Purchase Register from uploaded files.
    2.  Parse Excel/CSV and normalise headers.
    3.  For each unique item → try HSN statutory lookup first.
    4.  Items NOT resolved by HSN → batch-send to AI.
    5.  Merge results back and generate colour-coded Excel report.
    """

    # ── 1. Load Purchase Register ─────────────────────────────────────────
    pr_df = None
    for i, file_bytes in enumerate(input_bytes_list):
        fname = filenames[i].lower()
        if "purchase" in fname or "pr" in fname or len(input_bytes_list) == 1:
            try:
                pr_df = (
                    pd.read_csv(io.BytesIO(file_bytes))
                    if fname.endswith(".csv")
                    else pd.read_excel(io.BytesIO(file_bytes))
                )
                break
            except Exception as e:
                logger.error(f"Error reading file {filenames[i]}: {e}")

    if pr_df is None:
        raise ValueError("Could not identify or read a valid Purchase Register file.")

    # ── 2. Handle merged/title header rows ───────────────────────────────
    # Detect if row 0 is a title (most values are NaN) and real headers are in row 1
    raw_cols = [str(c).strip() for c in pr_df.columns]
    if sum(1 for c in raw_cols if c.startswith("Unnamed")) > len(raw_cols) // 2:
        logger.info("Detected merged title row — promoting row 0 as header")
        pr_df.columns = [str(v).strip() for v in pr_df.iloc[0]]
        pr_df = pr_df.iloc[1:].reset_index(drop=True)

    # Normalise column names to lowercase
    pr_df.columns = [str(c).strip().lower() for c in pr_df.columns]
    logger.info(f"Purchase Register columns: {list(pr_df.columns)}")

    # Drop pure-total / empty rows
    pr_df = pr_df[
        pr_df.iloc[:, 0].apply(lambda x: str(x).strip().lower() not in ["total", "nan", ""])
    ].copy()
    pr_df = pr_df[pd.to_numeric(pr_df.iloc[:, 0], errors="coerce").notna()].copy()

    # ── 3. Smart column detection ─────────────────────────────────────────
    def find_col(keywords: List[str]) -> Optional[str]:
        for kw in keywords:
            for c in pr_df.columns:
                if kw.lower() in c.lower():
                    return c
        return None

    # Supplier name is the primary "description" column for registers without item lines
    desc_col = find_col([
        "supplier name", "supplier", "party name", "party", "vendor name", "vendor",
        "desc", "item", "particular", "narration", "product", "goods", "service",
        "supply", "ledger", "expense", "head"
    ])
    hsn_col    = find_col(["hsn", "sac", "hsn/sac"])
    amount_col = find_col(["taxable value", "taxable amt", "taxable", "amount", "amt", "value"])
    igst_col   = find_col(["igst"])
    cgst_col   = find_col(["cgst"])
    sgst_col   = find_col(["sgst"])
    remarks_col = find_col(["remarks", "narration", "note"])
    itc_col    = find_col(["itc eligible", "itc"])

    # Fallback: first object column with average string length > 5
    if not desc_col:
        for c in pr_df.columns:
            if pr_df[c].dtype == "object":
                avg_len = pr_df[c].dropna().astype(str).str.len().mean()
                if avg_len and avg_len > 5:
                    desc_col = c
                    logger.info(f"Fallback desc_col: '{c}'")
                    break

    if not desc_col:
        raise ValueError(
            f"Could not find a description/supplier column. "
            f"Columns found: {list(pr_df.columns)}"
        )

    logger.info(
        f"Column mapping — desc: '{desc_col}' | hsn: '{hsn_col}' | "
        f"amount: '{amount_col}' | itc: '{itc_col}'"
    )

    # ── 4. Build unique item list & apply HSN lookup first ────────────────
    key_cols = [desc_col] + ([hsn_col] if hsn_col else [])
    unique_items_df = pr_df[key_cols].drop_duplicates().head(200)

    items_for_ai:  List[Dict[str, Any]] = []
    hsn_resolved:  Dict[Tuple, Dict]   = {}   # (desc, hsn) → {itc_status, blocking_reason, itc_source}

    for _, row in unique_items_df.iterrows():
        description = str(row.get(desc_col, "") or "").strip()
        hsn_raw     = row.get(hsn_col) if hsn_col else None
        key         = (description, str(hsn_raw) if hsn_raw else None)

        # Also check if register already flags this as blocked
        orig_itc = ""
        itc_match = pr_df[pr_df[desc_col] == description]
        if itc_col and len(itc_match):
            orig_itc = str(itc_match.iloc[0].get(itc_col, "") or "").strip().lower()
        remarks_val = ""
        if remarks_col and len(itc_match):
            remarks_val = str(itc_match.iloc[0].get(remarks_col, "") or "").strip().lower()

        # Priority 1: Explicit register flag
        if orig_itc == "no" or "blocked" in remarks_val or "17(5)" in remarks_val:
            hsn_resolved[key] = {
                "itc_status":    "BLOCKED",
                "blocking_reason": f"Marked ineligible in source register — {remarks_val or 'ITC Ineligible'}",
                "itc_source":    "Register",
            }
            continue

        # Priority 2: HSN statutory lookup
        hsn_status, hsn_reason, matched = lookup_hsn_itc(hsn_raw)
        if matched:
            hsn_resolved[key] = {
                "itc_status":    hsn_status,
                "blocking_reason": hsn_reason,
                "itc_source":    "HSN Lookup (Sec 17(5))",
            }
            continue

        # Priority 3: Supplier name intelligence lookup
        sup_status, sup_reason, sup_matched = lookup_supplier_itc(description)
        if sup_matched:
            hsn_resolved[key] = {
                "itc_status":    sup_status,
                "blocking_reason": sup_reason,
                "itc_source":    "Supplier Intelligence",
            }
            continue

        # Priority 4: Queue for AI (only truly unknown suppliers reach here)
        items_for_ai.append({
            "description": description,
            "hsn":         str(hsn_raw) if hsn_raw and str(hsn_raw) not in ("nan", "") else "N/A",
            "_key":        key,
        })

    logger.info(
        f"HSN resolved: {len(hsn_resolved)} | Sending to AI: {len(items_for_ai)}"
    )

    # ── 5. AI analysis for unresolved items ──────────────────────────────
    ai_resolved: Dict[Tuple, Dict] = {}
    if items_for_ai:
        chunk_size = 20
        all_classified: List[Dict] = []
        for i in range(0, len(items_for_ai), chunk_size):
            chunk = items_for_ai[i : i + chunk_size]
            classified = await analyze_items_with_ai(chunk)
            all_classified.extend(classified)

        for item in all_classified:
            key = item.pop("_key", (item.get("description"), item.get("hsn")))
            ai_resolved[key] = {
                "itc_status":    item.get("itc_status", "NEEDS_REVIEW"),
                "blocking_reason": item.get("blocking_reason", "AI analysis result"),
                "itc_source":    item.get("itc_source", "AI"),
            }

    # Merge both resolution maps
    classification_map = {**hsn_resolved, **ai_resolved}

    # ── 6. Apply results to full dataframe ────────────────────────────────
    def get_result(row, field: str) -> str:
        d   = str(row.get(desc_col, "") or "").strip()
        h   = str(row.get(hsn_col) if hsn_col else None or "")
        key = (d, h if h not in ("", "nan", "None") else None)
        fallback = {
            "itc_status":    "ELIGIBLE",
            "blocking_reason": "General business input — no block credit indicator found",
            "itc_source":    "Default",
        }
        return classification_map.get(key, fallback).get(field, "")

    pr_df["itc_status"]    = pr_df.apply(lambda r: get_result(r, "itc_status"), axis=1)
    pr_df["blocking_reason"] = pr_df.apply(lambda r: get_result(r, "blocking_reason"), axis=1)
    pr_df["itc_source"]    = pr_df.apply(lambda r: get_result(r, "itc_source"), axis=1)

    # ── 7. Build Excel output ─────────────────────────────────────────────
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pr_df.to_excel(writer, index=False, sheet_name="Blocked Credit Report")

        workbook  = writer.book
        worksheet = writer.sheets["Blocked Credit Report"]

        # ── Formats ──
        header_fmt  = workbook.add_format({"bold": True, "bg_color": "#1E3A8A", "font_color": "white",  "border": 1, "font_size": 10, "align": "center", "valign": "vcenter"})
        blocked_fmt = workbook.add_format({"bg_color": "#FEE2E2", "font_color": "#991B1B", "border": 1, "font_size": 9})
        eligible_fmt= workbook.add_format({"bg_color": "#DCFCE7", "font_color": "#166534", "border": 1, "font_size": 9})
        review_fmt  = workbook.add_format({"bg_color": "#FEF3C7", "font_color": "#92400E", "border": 1, "font_size": 9})
        bold_blocked= workbook.add_format({"bg_color": "#FEE2E2", "font_color": "#991B1B", "border": 1, "bold": True, "font_size": 9})
        bold_eligible=workbook.add_format({"bg_color": "#DCFCE7", "font_color": "#166534", "border": 1, "bold": True, "font_size": 9})
        bold_review = workbook.add_format({"bg_color": "#FEF3C7", "font_color": "#92400E", "border": 1, "bold": True, "font_size": 9})

        # ── Column widths ──
        col_widths = {
            desc_col:          30,
            "itc_status":      16,
            "blocking_reason": 50,
            "itc_source":      22,
        }
        for col_num, col_name in enumerate(pr_df.columns):
            width = col_widths.get(col_name, 18)
            worksheet.set_column(col_num, col_num, width)
            worksheet.write(0, col_num, col_name, header_fmt)

        worksheet.set_row(0, 20)

        # ── Row colouring ──
        status_idx  = list(pr_df.columns).index("itc_status")
        source_idx  = list(pr_df.columns).index("itc_source")

        for row_num, row_data in pr_df.iterrows():
            status = str(row_data["itc_status"]).upper()
            source = str(row_data["itc_source"])

            if status == "BLOCKED":
                row_fmt, bold_fmt = blocked_fmt, bold_blocked
            elif status == "NEEDS_REVIEW":
                row_fmt, bold_fmt = review_fmt, bold_review
            else:
                row_fmt, bold_fmt = eligible_fmt, bold_eligible

            for col_num, val in enumerate(row_data):
                fmt = bold_fmt if col_num in (status_idx, source_idx) else row_fmt

                if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                    val = ""
                worksheet.write(row_num + 1, col_num, val, fmt)

        # Freeze header + enable autofilter
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(pr_df), len(pr_df.columns) - 1)

        # ── Summary Sheet ─────────────────────────────────────────────────
        total          = len(pr_df)
        blocked_count  = (pr_df["itc_status"].str.upper() == "BLOCKED").sum()
        review_count   = (pr_df["itc_status"].str.upper() == "NEEDS_REVIEW").sum()
        eligible_count = total - blocked_count - review_count

        # GST at risk
        def sum_gst(mask):
            total_gst = 0
            for col in [igst_col, cgst_col, sgst_col]:
                if col:
                    total_gst += pd.to_numeric(pr_df.loc[mask, col], errors="coerce").fillna(0).sum()
            return total_gst

        blocked_mask  = pr_df["itc_status"].str.upper() == "BLOCKED"
        review_mask   = pr_df["itc_status"].str.upper() == "NEEDS_REVIEW"
        eligible_mask = ~blocked_mask & ~review_mask

        blocked_gst  = sum_gst(blocked_mask)
        review_gst   = sum_gst(review_mask)
        eligible_gst = sum_gst(eligible_mask)

        # HSN vs Supplier vs AI split
        hsn_count = (pr_df["itc_source"].str.contains("HSN", na=False)).sum()
        sup_count = (pr_df["itc_source"] == "Supplier Intelligence").sum()
        ai_count  = (pr_df["itc_source"] == "AI").sum()
        reg_count = (pr_df["itc_source"] == "Register").sum()

        summary_ws = workbook.add_worksheet("Summary")

        title_fmt  = workbook.add_format({"bold": True, "font_size": 14, "font_color": "#1E3A8A"})
        section_fmt= workbook.add_format({"bold": True, "font_size": 11, "font_color": "#1E3A8A", "bottom": 2})
        label_fmt  = workbook.add_format({"bold": True, "font_size": 10, "border": 1, "bg_color": "#F1F5F9"})
        val_fmt    = workbook.add_format({"font_size": 10, "border": 1, "align": "center"})
        money_fmt  = workbook.add_format({"font_size": 10, "border": 1, "align": "right", "num_format": "₹#,##0"})

        summary_ws.set_column(0, 0, 35)
        summary_ws.set_column(1, 1, 18)
        summary_ws.set_column(2, 2, 20)

        # Title
        summary_ws.write(0, 0, "ITC Block Credit Report — Section 17(5) CGST Act", title_fmt)
        summary_ws.set_row(0, 22)

        # ITC Status Summary
        summary_ws.write(2, 0, "ITC Status Summary", section_fmt)
        summary_ws.write(3, 0, "Status",              header_fmt)
        summary_ws.write(3, 1, "Invoices",            header_fmt)
        summary_ws.write(3, 2, "GST at Risk (₹)",     header_fmt)

        rows = [
            ("✅  ELIGIBLE",      eligible_count, eligible_gst, eligible_fmt),
            ("🔴  BLOCKED",       blocked_count,  blocked_gst,  blocked_fmt),
            ("⚠️  NEEDS REVIEW",  review_count,   review_gst,   review_fmt),
            ("TOTAL",             total,          blocked_gst + review_gst + eligible_gst, label_fmt),
        ]
        for ri, (label, count, gst, fmt) in enumerate(rows, start=4):
            summary_ws.write(ri, 0, label, label_fmt)
            summary_ws.write(ri, 1, count, val_fmt)
            summary_ws.write(ri, 2, gst,   money_fmt)

        # Resolution source breakdown
        summary_ws.write(9,  0, "Analysis Source Breakdown", section_fmt)
        summary_ws.write(10, 0, "Source",                    header_fmt)
        summary_ws.write(10, 1, "Items Processed",           header_fmt)
        source_rows = [
            ("🔎  HSN Statutory Lookup",      hsn_count),
            ("🏢  Supplier Intelligence",      sup_count),
            ("🤖  AI Analysis",               ai_count),
            ("📋  Source Register Flag",       reg_count),
        ]
        for ri, (src, cnt) in enumerate(source_rows, start=11):
            summary_ws.write(ri, 0, src, label_fmt)
            summary_ws.write(ri, 1, cnt, val_fmt)

        # Section 17(5) reference table
        summary_ws.write(15, 0, "Section 17(5) — Blocked Categories Quick Reference", section_fmt)
        ref_header_fmt = workbook.add_format({"bold": True, "bg_color": "#1E3A8A", "font_color": "white", "border": 1, "font_size": 9, "text_wrap": True})
        ref_label_fmt  = workbook.add_format({"bold": True, "font_size": 9, "border": 1, "bg_color": "#FEE2E2", "font_color": "#991B1B"})
        ref_val_fmt    = workbook.add_format({"font_size": 9, "border": 1, "bg_color": "#FEE2E2", "text_wrap": True})

        summary_ws.set_column(3, 3, 45)
        summary_ws.write(16, 0, "Clause",      ref_header_fmt)
        summary_ws.write(16, 1, "Category",    ref_header_fmt)
        summary_ws.write(16, 2, "Status",      ref_header_fmt)
        summary_ws.write(16, 3, "Key Exception / Note", ref_header_fmt)

        sec_ref_data = [
            ("17(5)(a)",       "Motor vehicles (<13 persons)",      "BLOCKED", "Further supply / passenger transport / driver training"),
            ("17(5)(b)(i)",    "Food, beverages, outdoor catering", "BLOCKED", "If it is an output service of the taxpayer"),
            ("17(5)(b)(ii)",   "Club / fitness membership",         "BLOCKED", "No exception — always blocked"),
            ("17(5)(b)(ii)",   "Rent-a-cab, life/health insurance", "BLOCKED", "Statutory obligation under law to provide to employees"),
            ("17(5)(b)(iii)",  "Travel benefits (vacation / LTC)",  "BLOCKED", "No exception — always blocked for vacation"),
            ("17(5)(c)",       "Works contract — immovable property", "BLOCKED", "Plant & machinery construction is eligible"),
            ("17(5)(d)",       "Goods/services for construction",   "BLOCKED", "Plant & machinery — eligible"),
            ("17(5)(g)",       "Personal consumption",              "BLOCKED", "No exception"),
            ("17(5)(h)",       "Gifts, samples, free supplies",     "BLOCKED", "No exception"),
        ]
        for ri, (clause, cat, status, exc) in enumerate(sec_ref_data, start=17):
            summary_ws.write(ri, 0, clause, ref_label_fmt)
            summary_ws.write(ri, 1, cat,    ref_val_fmt)
            summary_ws.write(ri, 2, status, ref_label_fmt)
            summary_ws.write(ri, 3, exc,    ref_val_fmt)
            summary_ws.set_row(ri, 20)

        # Items needing review
        if review_count > 0:
            review_start = 17 + len(sec_ref_data) + 2
            summary_ws.write(review_start, 0, "⚠️  Items Requiring Verification", title_fmt)
            summary_ws.write(review_start + 1, 0, "Supplier / Item", header_fmt)
            summary_ws.write(review_start + 1, 1, "Source",          header_fmt)
            summary_ws.write(review_start + 1, 2, "What to Verify",  ref_header_fmt)
            summary_ws.set_column(2, 2, 55)
            review_rows_df = pr_df[pr_df["itc_status"].str.upper() == "NEEDS_REVIEW"]
            for idx, (_, r) in enumerate(review_rows_df.iterrows()):
                summary_ws.write(review_start + 2 + idx, 0, str(r.get(desc_col, "")),          review_fmt)
                summary_ws.write(review_start + 2 + idx, 1, str(r.get("itc_source", "")),       review_fmt)
                summary_ws.write(review_start + 2 + idx, 2, str(r.get("blocking_reason", "")),  review_fmt)

    summary_data = {
        "total": int(total),
        "eligible": int(eligible_count),
        "blocked": int(blocked_count),
        "needs_review": int(review_count),
        "eligible_gst": round(float(eligible_gst), 2),
        "blocked_gst": round(float(blocked_gst), 2),
        "review_gst": round(float(review_gst), 2),
        "hsn_resolved": int(hsn_count),
        "supplier_resolved": int(sup_count),
        "ai_resolved": int(ai_count),
        "register_resolved": int(reg_count),
    }

    return output.getvalue(), summary_data