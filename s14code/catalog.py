"""The trusted component catalog.

A surface an agent produces may reference only the component *types* named
here, and each component may carry only the *properties* its schema allows.
The catalog is closed on purpose. There is no ``RawHtml`` type and no
free-form property, because a type or property that does not exist cannot be
named by a hostile agent.

Property kinds:
  - ``text``   a string shown to the user as literal text, never as markup
  - ``binding``a ``/json/pointer`` into the data model (see surface.py)
  - ``enum``   one of a fixed set of strings
  - ``ref``    a list of component ids (children)
  - ``action`` a named action + bound args; the only way a surface acts

The catalog also registers the closed set of action names a surface may emit.
Anything outside these sets is rejected by validator.py before render.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PropSpec:
    kind: str  # text | binding | enum | ref | action | number | bool
    values: tuple[str, ...] = ()  # for enum


@dataclass(frozen=True)
class ComponentSpec:
    type: str
    props: dict[str, PropSpec] = field(default_factory=dict)


# The eight component types the render client knows how to draw. Small on
# purpose: a student can read every one and the validator can prove coverage.
COMPONENTS: dict[str, ComponentSpec] = {
    "Column": ComponentSpec("Column", {"children": PropSpec("ref")}),
    "Row": ComponentSpec("Row", {"children": PropSpec("ref")}),
    "Heading": ComponentSpec("Heading", {"text": PropSpec("binding")}),
    "Text": ComponentSpec("Text", {"text": PropSpec("binding")}),
    "Badge": ComponentSpec(
        "Badge",
        {"text": PropSpec("binding"), "tone": PropSpec("enum", ("neutral", "good", "warn", "bad"))},
    ),
    "Table": ComponentSpec("Table", {"columns": PropSpec("text"), "rows": PropSpec("binding")}),
    "Notice": ComponentSpec(
        "Notice",
        {"text": PropSpec("binding"), "tone": PropSpec("enum", ("neutral", "good", "warn", "bad"))},
    ),
    "ApprovalCard": ComponentSpec(
        "ApprovalCard",
        {
            "summary": PropSpec("binding"),
            "params": PropSpec("binding"),
            "confirm": PropSpec("action"),
            "reject": PropSpec("action"),
        },
    ),
    "Button": ComponentSpec("Button", {"label": PropSpec("text"), "onPress": PropSpec("action")}),
    # --- richer components: the catalog an agent composes a real dashboard from ---
    "Card": ComponentSpec("Card", {"title": PropSpec("text"), "children": PropSpec("ref")}),
    "Grid": ComponentSpec("Grid", {"cols": PropSpec("number"), "children": PropSpec("ref")}),
    "Divider": ComponentSpec("Divider", {}),
    "StatTile": ComponentSpec(
        "StatTile",
        {
            "label": PropSpec("text"),
            "value": PropSpec("binding"),
            "unit": PropSpec("text"),
            "delta": PropSpec("binding"),
            "tone": PropSpec("enum", ("neutral", "good", "warn", "bad")),
        },
    ),
    "BarChart": ComponentSpec(
        "BarChart",
        {"title": PropSpec("text"), "data": PropSpec("binding"), "xKey": PropSpec("text"),
         "yKey": PropSpec("text"), "unit": PropSpec("text")},
    ),
    "LineChart": ComponentSpec(
        "LineChart",
        {"title": PropSpec("text"), "data": PropSpec("binding"), "xKey": PropSpec("text"), "yKey": PropSpec("text")},
    ),
    "Sparkline": ComponentSpec("Sparkline", {"data": PropSpec("binding"), "tone": PropSpec("enum", ("neutral", "good", "warn", "bad"))}),
    "ProgressBar": ComponentSpec("ProgressBar", {"value": PropSpec("binding"), "max": PropSpec("number"), "tone": PropSpec("enum", ("neutral", "good", "warn", "bad"))}),
    "Tabs": ComponentSpec("Tabs", {"labels": PropSpec("text"), "children": PropSpec("ref")}),
    "Tab": ComponentSpec("Tab", {"label": PropSpec("text"), "children": PropSpec("ref")}),
    "Timeline": ComponentSpec("Timeline", {"title": PropSpec("text"), "events": PropSpec("binding")}),
    "DataTable": ComponentSpec(
        "DataTable",
        {"columns": PropSpec("text"), "rows": PropSpec("binding"), "sortable": PropSpec("bool"), "filterKey": PropSpec("text")},
    ),
}

# The closed set of action names a surface may emit. An action the agent did
# not register cannot cross back into the graph.
REGISTERED_ACTIONS: frozenset[str] = frozenset({"approve", "reject", "rerun", "request_data"})


def catalog_manifest() -> dict:
    """A JSON view of the catalog, served at /v1/catalog for the client."""
    return {
        "components": {
            name: {
                "props": {
                    prop: {"kind": spec.kind, **({"values": list(spec.values)} if spec.values else {})}
                    for prop, spec in comp.props.items()
                }
            }
            for name, comp in COMPONENTS.items()
        },
        "actions": sorted(REGISTERED_ACTIONS),
    }
