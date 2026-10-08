import json

from sqlalchemy import select

from app.llm.router import LLMRouter
from app.models import LLMCall
from app.schemas.extraction import EmailCategory, POExtraction
from app.services.escalation import escalate, escalation_targets, has_size_table
from app.services.review import review_extraction
from tests.scripted import ScriptedClient, reply

SOURCE = """PURCHASE ORDER
PO Number: AB-1001
Buyer: Acme Apparel Ltd
Currency: USD
Total Quantity: 1,000 pcs

Colour  S    M    Total
Navy    400  600  1000
"""


def _extraction(**overrides) -> POExtraction:
    data = {
        "po_number": {"value": "AB-1001", "confidence": 0.9, "evidence": "PO Number: AB-1001"},
        "buyer": {"value": "Acme Apparel Ltd", "confidence": 0.9, "evidence": "Buyer: Acme Apparel Ltd"},
        "currency": {"value": "USD", "confidence": 0.9, "evidence": "Currency: USD"},
        "total_quantity": {"value": 1000, "confidence": 0.9, "evidence": "Total Quantity: 1,000 pcs"},
        "line_items": [{"colour": "Navy", "sizes": {"S": 400, "M": 600}, "quantity": 1000}],
    }
    data.update(overrides)
    return POExtraction.model_validate(data)


def _review(extraction: POExtraction):
    return review_extraction(extraction, SOURCE, EmailCategory.DELIVERY_CHANGE, threshold=0.7)


def test_size_table_detection():
    assert has_size_table(SOURCE)
    assert not has_size_table("Colours and quantities: Blanc 2,000 / Marine 2,500\nSize ratio 1:2:3:3:1")
    assert not has_size_table("sizes 0-3M / 3-6M split evenly")


def test_clean_extraction_has_no_targets():
    assert escalation_targets(_review(_extraction()), SOURCE) == []


def test_targets_for_each_trigger():
    missing_sizes = _extraction(line_items=[{"colour": "Navy", "sizes": {}, "quantity": 1000}])
    bad_sizes = _extraction(line_items=[{"colour": "Navy", "sizes": {"S": 750, "M": 750}, "quantity": None}])
    bad_quote = _extraction(currency={"value": "EUR", "confidence": 0.9, "evidence": "Buyer: Acme Apparel Ltd"})

    assert escalation_targets(_review(missing_sizes), SOURCE) == [("line_items", "size_table_not_extracted")]
    assert ("line_items", "size_total_mismatch") in escalation_targets(_review(bad_sizes), "no table here")
    assert escalation_targets(_review(bad_quote), SOURCE) == [("currency", "source_quote_missing")]


def _router(settings, session_factory, replies):
    return LLMRouter(settings, client=ScriptedClient(replies), session_factory=session_factory)


def test_super_fixes_the_field_and_the_escalation_is_logged(settings, session_factory):
    nano = _review(_extraction(line_items=[{"colour": "Navy", "sizes": {}, "quantity": 1000}]))
    fixed = {"line_items": [{"colour": "Navy", "sizes": {"S": 400, "M": 600}, "quantity": 1000, "unit_price": None}]}
    client = ScriptedClient([reply(json.dumps(fixed), prompt_tokens=800, completion_tokens=100)])
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    final = escalate(router, nano, SOURCE, EmailCategory.DELIVERY_CHANGE, 0.7)

    assert final.fields.line_items[0].sizes == {"S": 400, "M": 600}
    [escalation] = final.escalations
    assert (escalation.field, escalation.reason, escalation.outcome) == ("line_items", "size_table_not_extracted", "resolved")
    assert escalation.model == "test/super"
    # 800 * 0.30/1M + 100 * 0.90/1M
    assert float(escalation.cost_usd) == 0.00033
    # Only the failing field was asked for, from Super, without thinking.
    request = client.requests[0]
    assert request["model"] == "test/super"
    assert 'extract ONLY the field "line_items"' in request["messages"][0]["content"]
    assert request["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    with session_factory() as session:
        row = session.scalars(select(LLMCall)).one()
    assert (row.task_type, row.tier, row.detail) == (
        "extract_escalation", "super", "escalation: line_items (size_table_not_extracted)"
    )


def test_answer_that_still_fails_the_check_is_not_kept(settings, session_factory):
    nano = _review(_extraction(line_items=[{"colour": "Navy", "sizes": {}, "quantity": 1000}]))
    still_empty = {"line_items": [{"colour": "Navy", "sizes": {}, "quantity": 1000}]}
    router = _router(settings, session_factory, [reply(json.dumps(still_empty))])

    final = escalate(router, nano, SOURCE, EmailCategory.DELIVERY_CHANGE, 0.7)

    assert final.escalations[0].outcome == "unresolved"
    assert final.fields.line_items[0].sizes == {}


def test_unstated_value_becomes_null_after_escalation(settings, session_factory):
    nano = _review(_extraction(currency={"value": "EUR", "confidence": 0.9, "evidence": "Buyer: Acme Apparel Ltd"}))
    router = _router(settings, session_factory, [reply(json.dumps({"currency": {"value": None, "confidence": 0}}))])

    final = escalate(router, nano, SOURCE, EmailCategory.DELIVERY_CHANGE, 0.7)

    assert final.escalations[0].outcome == "resolved"
    assert final.fields.currency.value is None
    assert final.escalations[0].before == "EUR"


def test_unusable_answer_is_recorded_as_failed(settings, session_factory):
    nano = _review(_extraction(line_items=[{"colour": "Navy", "sizes": {}, "quantity": 1000}]))
    router = _router(settings, session_factory, [reply("not json"), reply("still not json")])

    final = escalate(router, nano, SOURCE, EmailCategory.DELIVERY_CHANGE, 0.7)

    assert final.escalations[0].outcome == "failed"
    assert final.escalations[0].calls == 2
    assert final.fields.line_items[0].sizes == {}


def test_no_escalation_when_nano_passes(settings, session_factory):
    client = ScriptedClient([])
    router = LLMRouter(settings, client=client, session_factory=session_factory)

    final = escalate(router, _review(_extraction()), SOURCE, EmailCategory.DELIVERY_CHANGE, 0.7)

    assert final.escalations == []
    assert client.requests == []
