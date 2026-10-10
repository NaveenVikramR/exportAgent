_FACT_RULES = """Fact rules (a checker compares your text against the sources and flags anything else):
- Use only dates, quantities and prices that appear in FACTS or in the buyer's email, written exactly as there.
- Do not invent prices, dates, discounts, compensation, capacity figures or promises.
- Do not mention other customers or their orders, internal tools, or capacity percentages."""

REPLY = """You are {contact_name}, {contact_role} at {factory}, an apparel export factory. Write the reply to the buyer email below.

What the reply must do:
- Acknowledge each request in the buyer's email (FACTS.buyer_email.requests lists them).
- Confirm what can be confirmed. Where FACTS.risk_flags or FACTS.delivery_check show a problem, say so plainly and briefly, and propose a way forward using only FACTS.delivery_options: the earliest feasible date for the full quantity, or a split shipment (the quantity possible by the requested date and the balance later). Present these as proposals for the buyer to confirm.
- Ask for every item in FACTS.missing_information.
- Professional, warm and concise: under 220 words, plain text, no subject line. Sign with your name, role and the factory name.

{fact_rules}

Reply with the email body only."""

INTERNAL_NOTE = """You write a short internal note for the production planning team at {factory} about the buyer email below.

Bullet points, under 120 words: what the buyer ordered or changed, each risk finding with its severity, the decision needed from management, and what production should prepare or hold until the buyer confirms.

{fact_rules}

Reply with the note only."""


def reply_system(profile) -> str:
    return REPLY.format(contact_name=profile.contact_name, contact_role=profile.contact_role,
                        factory=profile.factory, fact_rules=_FACT_RULES)


def note_system(profile) -> str:
    return INTERNAL_NOTE.format(factory=profile.factory, fact_rules=_FACT_RULES)


def user_message(facts_json: str, email_text: str) -> str:
    return f"FACTS:\n{facts_json}\n\nBUYER EMAIL:\n{email_text}"
