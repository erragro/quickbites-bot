"""Handlebars-style variable substitution — pure unit tests, no DB."""

import pytest

from app.conversation_studio.render import render


def test_simple_substitution():
    out = render("Hi {{customer.first_name}}", {"customer": {"first_name": "Rahul"}})
    assert out == "Hi Rahul"


def test_multiple_variables_in_one_sentence():
    ctx = {
        "customer": {"first_name": "Rahul"},
        "order": {"id": 452},
        "restaurant": {"name": "Pizza Spice"},
    }
    out = render(
        "Sorry {{customer.first_name}} — pulling up order #{{order.id}} from {{restaurant.name}}.",
        ctx,
    )
    assert out == "Sorry Rahul — pulling up order #452 from Pizza Spice."


def test_missing_var_drops_that_sentence_not_the_whole_template():
    ctx = {"customer": {"first_name": "Rahul"}}
    out = render(
        "Hi {{customer.first_name}}! Looking at order #{{order.id}} for you.",
        ctx,
    )
    assert out == "Hi Rahul!"


def test_all_variables_missing_returns_neutral_fallback():
    # Every sentence loses a variable → fallback prose so we don't leak.
    out = render("Hi {{customer.first_name}}, order #{{order.id}}.", {})
    assert "{{" not in out
    assert out  # non-empty


def test_no_placeholders_returns_template_verbatim():
    out = render("Sorry about that — one moment.", {})
    assert out == "Sorry about that — one moment."


def test_empty_string_variable_is_treated_as_missing():
    out = render(
        "Hello {{customer.first_name}}. Looking now.",
        {"customer": {"first_name": "   "}},
    )
    # Whitespace-only value ⇒ sentence dropped.
    assert out == "Looking now."


def test_number_values_are_stringified():
    out = render("Order #{{order.id}}, ₹{{order.total_inr}}.",
                 {"order": {"id": 452, "total_inr": 1642}})
    assert out == "Order #452, ₹1642."


def test_nested_dotted_path_walks_dict():
    ctx = {"customer": {"abuse": {"complaint_rate": 0.3}}}
    out = render("Rate is {{customer.abuse.complaint_rate}}.", ctx)
    assert out == "Rate is 0.3."


def test_never_leaks_literal_placeholder_syntax():
    # No matter what happens, output must not contain {{...}}.
    for tpl in [
        "{{customer.first_name}}",
        "Hi {{a}} and {{b}}",
        "{{a.b.c.d}}",
        "{{missing}} sentence one. And {{also_missing}} sentence two.",
    ]:
        out = render(tpl, {})
        assert "{{" not in out and "}}" not in out


def test_object_attribute_access_works():
    """Templates may render Pydantic models directly."""

    class Obj:
        pass

    o = Obj()
    o.first_name = "Priya"  # type: ignore[attr-defined]
    out = render("Hi {{u.first_name}}", {"u": o})
    assert out == "Hi Priya"


@pytest.mark.parametrize(
    "sep",
    [". ", "! ", "? "],
    ids=["period", "bang", "question"],
)
def test_sentence_boundary_handling(sep: str):
    tpl = f"Hi {{{{u.name}}}}{sep}Looking now."
    out = render(tpl, {"u": {"name": "X"}})
    assert out == f"Hi X{sep.strip()} Looking now."
