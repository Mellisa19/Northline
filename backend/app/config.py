"""Static domain configuration for the Northline demo portfolio.

Everything the generator and the analytics engines need to agree on lives here so
that a reseed produces byte-identical numbers.
"""

from __future__ import annotations

from datetime import date

# The portfolio is reported "as of" this date. Pinning it keeps the demo
# deterministic and every figure on screen reproducible from a reseed.
AS_OF = date(2026, 10, 5)
SEED = 20261005

CURRENCY = "NGN"
CURRENCY_SYMBOL = "\u20a6"

# --------------------------------------------------------------------------
# Lending products
# --------------------------------------------------------------------------
# weight          share of the book by account count
# tenor           months
# ticket          principal range in naira
# monthly_rate    flat monthly interest applied to principal
PRODUCTS: list[dict] = [
    {
        "code": "WC",
        "name": "Working Capital",
        "weight": 0.30,
        "tenor": (6, 18),
        "ticket": (2_000_000, 25_000_000),
        "monthly_rate": (0.025, 0.040),
    },
    {
        "code": "AF",
        "name": "Asset Finance",
        "weight": 0.22,
        "tenor": (12, 36),
        "ticket": (4_000_000, 45_000_000),
        "monthly_rate": (0.018, 0.028),
    },
    {
        "code": "ID",
        "name": "Invoice Discounting",
        "weight": 0.13,
        "tenor": (1, 3),
        "ticket": (6_000_000, 30_000_000),
        "monthly_rate": (0.020, 0.030),
    },
    {
        "code": "MCA",
        "name": "Merchant Cash Advance",
        "weight": 0.20,
        "tenor": (3, 9),
        "ticket": (600_000, 4_000_000),
        "monthly_rate": (0.045, 0.070),
    },
    {
        "code": "PAY",
        "name": "Payroll Advance",
        "weight": 0.15,
        "tenor": (6, 24),
        "ticket": (900_000, 7_000_000),
        "monthly_rate": (0.030, 0.045),
    },
]

PRODUCT_BY_CODE = {product["code"]: product for product in PRODUCTS}

# --------------------------------------------------------------------------
# Borrower universe
# --------------------------------------------------------------------------
SECTORS: list[tuple[str, float]] = [
    ("Food & Beverage Processing", 0.13),
    ("Logistics & Haulage", 0.11),
    ("Retail & FMCG Distribution", 0.11),
    ("Building Materials", 0.09),
    ("Pharmaceuticals & Health", 0.08),
    ("Agro-Processing", 0.08),
    ("Printing & Packaging", 0.06),
    ("Auto Parts & Repairs", 0.06),
    ("Hospitality & Catering", 0.06),
    ("ICT & Business Services", 0.05),
    ("Textiles & Garments", 0.05),
    ("Oil & Gas Services", 0.04),
    ("Education & Training", 0.04),
    ("Construction & Interiors", 0.04),
]

# Sector-level monthly shocks used to drive correlated stress episodes.
SECTOR_CYCLE_SENSITIVITY = {
    "Food & Beverage Processing": 0.55,
    "Logistics & Haulage": 0.95,
    "Retail & FMCG Distribution": 0.90,
    "Building Materials": 1.15,
    "Pharmaceuticals & Health": 0.45,
    "Agro-Processing": 1.05,
    "Printing & Packaging": 0.80,
    "Auto Parts & Repairs": 1.00,
    "Hospitality & Catering": 1.10,
    "ICT & Business Services": 0.60,
    "Textiles & Garments": 1.05,
    "Oil & Gas Services": 1.25,
    "Education & Training": 0.50,
    "Construction & Interiors": 1.20,
}

LOCATIONS: list[tuple[str, str, float]] = [
    ("Lagos", "Ikeja", 0.14),
    ("Lagos", "Lekki", 0.09),
    ("Lagos", "Apapa", 0.07),
    ("Lagos", "Yaba", 0.05),
    ("Lagos", "Surulere", 0.05),
    ("Lagos", "Mushin", 0.03),
    ("Ogun", "Abeokuta", 0.04),
    ("Ogun", "Sagamu", 0.03),
    ("Oyo", "Ibadan", 0.06),
    ("FCT", "Abuja", 0.09),
    ("FCT", "Gwagwalada", 0.02),
    ("Rivers", "Port Harcourt", 0.06),
    ("Kano", "Kano", 0.05),
    ("Kaduna", "Kaduna", 0.03),
    ("Enugu", "Enugu", 0.03),
    ("Anambra", "Onitsha", 0.03),
    ("Anambra", "Nnewi", 0.02),
    ("Abia", "Aba", 0.03),
    ("Edo", "Benin City", 0.03),
    ("Delta", "Warri", 0.02),
    ("Cross River", "Calabar", 0.01),
    ("Plateau", "Jos", 0.02),
    ("Kwara", "Ilorin", 0.02),
]

# Business naming: surname + trade word + legal suffix. Curated so that every
# generated name reads as a plausible Nigerian trading company.
SURNAMES = [
    "Adeola", "Okafor", "Balogun", "Eze", "Danjuma", "Ogundipe", "Nwachukwu",
    "Abubakar", "Afolabi", "Chukwu", "Oyelaran", "Ibrahim", "Obi", "Lawal",
    "Ekpo", "Bello", "Nnamdi", "Salami", "Uche", "Yakubu", "Ajayi", "Onwuka",
    "Suleiman", "Adebayo", "Emeka", "Gbadamosi", "Hassan", "Idowu", "Jideofor",
    "Kalu", "Lukman", "Mbah", "Nwosu", "Okonkwo", "Peters", "Raji", "Sanni",
    "Tijani", "Umeh", "Vincent", "Waziri", "Yusuf", "Zubairu", "Akintola",
    "Bamidele", "Chidozie", "Duru", "Eniola", "Fashola", "George", "Hamza",
    "Ikenna", "Jibrin", "Kingsley", "Madu", "Nurudeen", "Olatunji", "Precious",
    "Rotimi", "Sule", "Tunde", "Usman", "Victor", "Williams", "Yemi", "Zainab",
    "Aguiyi", "Bassey", "Chinwe", "Dike", "Ekwueme", "Folarin", "Garba",
    "Hillary", "Ijeoma", "Jimoh", "Keshi", "Lambo", "Musa", "Ndidi", "Ogunbiyi",
    "Pascal", "Quarshie", "Rufai", "Shaibu", "Teddy", "Ugo", "Vera", "Wale",
    "Yakubu", "Zaki", "Adenuga", "Buhari", "Chinedu", "Dangote", "Ejiro",
]

TRADE_WORDS = [
    "Foods", "Logistics", "Pharma", "Ventures", "Agro", "Trading", "Stores",
    "Packaging", "Haulage", "Motors", "Autoparts", "Fabrication", "Interiors",
    "Healthcare", "Feeds", "Plastics", "Steel", "Paints", "Textiles",
    "Electronics", "Chemicals", "Poultry", "Farms", "Bakeries", "Cold Chain",
    "Publishing", "Security", "Energy", "Marine", "Furniture", "Tyres",
    "Distribution", "Imports", "Oilfield", "Academy", "Diagnostics",
    "Confectionery", "Beverages", "Hardware", "Accessories",
]

SUFFIXES: list[tuple[str, float]] = [
    ("Ltd", 0.46),
    ("Nigeria Ltd", 0.16),
    ("Enterprises", 0.14),
    ("& Sons Ltd", 0.10),
    ("Ventures Ltd", 0.08),
    ("Interbiz Ltd", 0.06),
]

RELATIONSHIP_MANAGERS = [
    "C. Adeyemi", "F. Nwosu", "H. Bala", "I. Okonkwo", "J. Ademola",
    "K. Uzoma", "M. Danjuma", "N. Ogunleye", "O. Effiong", "P. Chikwendu",
    "R. Salami", "S. Ibrahim", "T. Obiora", "U. Lawal", "V. Ekhator",
    "W. Bankole", "Y. Musa", "Z. Oyelowo",
]

# --------------------------------------------------------------------------
# Collections operations
# --------------------------------------------------------------------------
COLLECTIONS_OFFICERS = [
    "A. Ogunlesi", "B. Eze", "D. Yakubu", "E. Bassey", "G. Nnamani",
    "L. Abiodun", "Q. Musa", "S. Akinwale", "T. Chukwuemeka", "X. Umar",
]

# Direct, out-of-pocket cost of one attempt, in naira.
CHANNEL_COST = {
    "call": 420,
    "sms": 12,
    "whatsapp": 18,
    "email": 5,
    "field_visit": 4_800,
    "payment_link": 30,
    "legal_notice": 26_000,
}

# Officer time an attempt consumes, in minutes. Direct cost and officer time
# together are what an attempt actually costs, so both are published rather than
# folded into one unexplained number.
OFFICER_MINUTES = {
    "call": 15,
    "sms": 2,
    "whatsapp": 6,
    "email": 3,
    "field_visit": 90,
    "payment_link": 2,
    "legal_notice": 30,
}

# Fully loaded collections officer cost per hour, in naira.
OFFICER_HOURLY_COST = 1_400


def attempt_cost(channel: str) -> int:
    """Total cost of one attempt: out-of-pocket plus officer time."""
    direct = CHANNEL_COST.get(channel, 0)
    minutes = OFFICER_MINUTES.get(channel, 0)
    return int(round(direct + minutes * OFFICER_HOURLY_COST / 60.0))


CHANNELS = list(CHANNEL_COST.keys())

DISPOSITIONS = [
    "promise_to_pay",
    "paid_in_full",
    "partial_payment",
    "no_answer",
    "wrong_number",
    "requested_extension",
    "disputed_amount",
    "refused_to_pay",
    "not_reachable",
    "business_closed",
    "restructure_requested",
]

DISPOSITION_LABELS = {
    "promise_to_pay": "Promise to pay",
    "paid_in_full": "Paid in full",
    "partial_payment": "Part payment received",
    "no_answer": "No answer",
    "wrong_number": "Wrong number",
    "requested_extension": "Requested extension",
    "disputed_amount": "Disputed amount",
    "refused_to_pay": "Refused to pay",
    "not_reachable": "Not reachable",
    "business_closed": "Business closed",
    "restructure_requested": "Requested restructure",
}

# --------------------------------------------------------------------------
# Playbooks — the answer to "so what do I do?"
# --------------------------------------------------------------------------
PLAYBOOKS: list[dict] = [
    {
        "code": "CARE_CALL",
        "name": "Pre-delinquency care call",
        "owner": "Relationship Manager",
        "timing": "5-10 days before due date",
        "objective": "Confirm the next instalment is funded before it is late.",
        "script": (
            "Good morning {contact}, this is {officer} from {lender}. I am calling ahead of "
            "your instalment of {instalment} due on {due_date} to confirm everything is on "
            "track. Is there anything on your side we should plan around?"
        ),
        "success_metric": "Instalment received on or before the due date",
        "phase": "early_intervention",
    },
    {
        "code": "REMIND_LINK",
        "name": "Payment reminder with settlement link",
        "owner": "Collections Officer",
        "timing": "3 days before and 1 day after due date",
        "objective": "Remove friction from a payment the borrower already intends to make.",
        "script": (
            "{contact}, your instalment of {instalment} on account {account_ref} is due "
            "{due_date}. Pay in one step here: {payment_link}. Reference {account_ref}."
        ),
        "success_metric": "Payment received within 3 days of the due date",
        "phase": "collections",
    },
    {
        "code": "PROMISE_CAPTURE",
        "name": "Promise-to-pay capture",
        "owner": "Collections Officer",
        "timing": "Any live contact on a delinquent account",
        "objective": "Convert a conversation into a dated, recorded commitment.",
        "script": (
            "I can hold the account at this stage if we agree a date. What specific date "
            "can you settle {outstanding}, and will it be a part payment or the full amount?"
        ),
        "success_metric": "Promise recorded and kept within 3 days of the promised date",
        "phase": "collections",
    },
    {
        "code": "PART_PAYMENT",
        "name": "Part-payment arrangement",
        "owner": "Collections Officer",
        "timing": "Capacity is reduced but activity continues",
        "objective": "Recover cash now rather than escalate an account that can still pay.",
        "script": (
            "{contact}, we can structure this so it stays workable. If {part_amount} comes in "
            "this week we will hold escalation and review the balance with you on {review_date}."
        ),
        "success_metric": "At least 30% of the overdue instalment received within 7 days",
        "phase": "collections",
    },
    {
        "code": "RESTRUCTURE",
        "name": "Soft restructure review",
        "owner": "Credit Manager",
        "timing": "Material cash-flow decline with a clean prior record",
        "objective": "Reschedule a viable business instead of writing it off.",
        "script": (
            "We have reviewed the account and would rather extend the tenor than escalate. "
            "Bring your last three months of statements and we will put a reschedule to committee."
        ),
        "success_metric": "Rescheduled and performing for 60 days",
        "phase": "early_intervention",
    },
    {
        "code": "MANDATE_SETUP",
        "name": "Direct-debit mandate setup",
        "owner": "Collections Officer",
        "timing": "Two or more late payments without a payment behaviour change",
        "objective": "Remove the recurring manual step that keeps failing.",
        "script": (
            "The pattern we see is timing, not willingness. Let us set up a standing order for "
            "{instalment} on the {due_day} of each month so this stops recurring."
        ),
        "success_metric": "Active mandate and two consecutive on-time instalments",
        "phase": "collections",
    },
    {
        "code": "DIVERSION_REVIEW",
        "name": "Fund-diversion investigation",
        "owner": "Risk Manager",
        "timing": "Proceeds not deployed as stated, or rapid outflow after disbursement",
        "objective": "Establish where the facility went before it becomes a loss.",
        "script": (
            "We need to reconcile the drawdown against the stated purpose. Please share the "
            "invoices and the receiving account details for the disbursement."
        ),
        "success_metric": "Usage evidenced, or the account escalated within 10 days",
        "phase": "early_intervention",
    },
    {
        "code": "FIELD_VISIT",
        "name": "Field visit",
        "owner": "Field Recovery",
        "timing": "60+ days past due, contactable, exposure above the visit threshold",
        "objective": "Establish whether the business is trading and secure a payment.",
        "script": (
            "Physical visit to the business address to verify trading status, confirm the "
            "responsible officer and secure a signed payment undertaking."
        ),
        "success_metric": "Payment received or a signed undertaking within 5 days",
        "phase": "recovery",
    },
    {
        "code": "LEGAL_REVIEW",
        "name": "Legal and write-off review",
        "owner": "Head of Credit",
        "timing": "90+ days past due with all recovery playbooks exhausted",
        "objective": "Take a documented decision rather than letting the balance drift.",
        "script": (
            "Committee pack: exposure, security, recovery to date, cost-to-collect and a "
            "recommendation to litigate, enforce security, or write off and keep recovering."
        ),
        "success_metric": "Decision recorded within 14 days",
        "phase": "recovery",
    },
]

PLAYBOOK_BY_CODE = {playbook["code"]: playbook for playbook in PLAYBOOKS}

# Recovery assumptions used by the expected-value engine.
LOSS_GIVEN_DEFAULT = {
    "WC": 0.58,
    "AF": 0.34,   # asset-backed, stronger recovery
    "ID": 0.46,
    "MCA": 0.72,
    "PAY": 0.55,
}

# Probability that a well-executed playbook converts a stressed account,
# by playbook code and delinquency band. Used for expected value, and
# documented as an assumption in the UI.
PLAYBOOK_EFFECTIVENESS = {
    "CARE_CALL": {0: 0.62, 1: 0.44, 2: 0.22, 3: 0.10, 4: 0.04},
    "REMIND_LINK": {0: 0.58, 1: 0.47, 2: 0.26, 3: 0.12, 4: 0.05},
    "PROMISE_CAPTURE": {0: 0.50, 1: 0.46, 2: 0.33, 3: 0.19, 4: 0.08},
    "PART_PAYMENT": {0: 0.44, 1: 0.42, 2: 0.34, 3: 0.24, 4: 0.11},
    "RESTRUCTURE": {0: 0.55, 1: 0.48, 2: 0.30, 3: 0.15, 4: 0.05},
    "MANDATE_SETUP": {0: 0.52, 1: 0.44, 2: 0.25, 3: 0.12, 4: 0.04},
    "DIVERSION_REVIEW": {0: 0.34, 1: 0.30, 2: 0.20, 3: 0.11, 4: 0.05},
    "FIELD_VISIT": {0: 0.05, 1: 0.30, 2: 0.36, 3: 0.31, 4: 0.18},
    "LEGAL_REVIEW": {0: 0.05, 1: 0.08, 2: 0.12, 3: 0.16, 4: 0.14},
}

# Delinquency bands: index 0..4
BANDS = [
    {"index": 0, "code": "current", "label": "Current", "min_dpd": -9999, "max_dpd": 0},
    {"index": 1, "code": "watch", "label": "1\u201330 days", "min_dpd": 1, "max_dpd": 30},
    {"index": 2, "code": "substandard", "label": "31\u201360 days", "min_dpd": 31, "max_dpd": 60},
    {"index": 3, "code": "doubtful", "label": "61\u201390 days", "min_dpd": 61, "max_dpd": 90},
    {"index": 4, "code": "lost", "label": "90+ days", "min_dpd": 91, "max_dpd": 99999},
]


def band_for_dpd(dpd: int) -> int:
    if dpd <= 0:
        return 0
    if dpd <= 30:
        return 1
    if dpd <= 60:
        return 2
    if dpd <= 90:
        return 3
    return 4


# Payments are recorded to the nearest 100 naira, so a residual smaller than that
# is not a delinquency. Without a stated tolerance the reconstructed history drifts
# away from the account position by a few naira and roll rates stop reconciling.
SETTLEMENT_TOLERANCE = 100
