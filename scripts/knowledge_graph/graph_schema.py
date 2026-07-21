"""Graph labels, relationship types, and schema metadata."""

from __future__ import annotations

from dataclasses import dataclass


SUPPLY_CHAIN_NODE_LABELS = {
    "Country",
    "Port",
    "Terminal",
    "Refinery",
    "StorageTerminal",
    "Pipeline",
    "PowerIndustry",
    "Consumer",
    "Supplier",
    "Commodity",
    "ShippingRoute",
    "Organization",
    "Event",
    "EventCluster",
    "Record",
}

NODE_KEY_PROPERTY = {
    "Country": "entity_key",
    "Port": "entity_key",
    "Terminal": "entity_key",
    "Refinery": "entity_key",
    "StorageTerminal": "entity_key",
    "Pipeline": "entity_key",
    "PowerIndustry": "entity_key",
    "Consumer": "entity_key",
    "Supplier": "entity_key",
    "Commodity": "entity_key",
    "ShippingRoute": "entity_key",
    "Organization": "entity_key",
    "Event": "event_id",
    "EventCluster": "cluster_id",
    "Record": "record_id",
}

RELATIONSHIP_TYPES = {
    "HAS_PORT",
    "CONNECTS_TO",
    "SUPPLIES",
    "STORES_IN",
    "SERVES",
    "TRANSPORTED_VIA",
    "MENTIONS",
    "EVIDENCED_BY",
    "PART_OF_CLUSTER",
    "AFFECTS",
    "PRECEDES",
    "NEXT_EVENT",
    "TRIGGERS",
    "OBSERVED_IN",
    "DERIVED_FROM",
}

EVENT_CATEGORY_ORDER = {
    "sanctions": 10,
    "naval_activity": 20,
    "policy_change": 30,
    "oil_price_spike": 40,
    "shipping_disruption": 50,
    "strait_closure": 60,
}

DOMAIN_EVENT_CATEGORY = {
    "geopolitical": "geopolitical_signal",
    "maritime_logistics": "shipping_disruption",
    "market": "market_signal",
    "financial": "financial_signal",
    "weather_climate": "weather_disruption",
    "policy": "policy_change",
    "inventory": "inventory_signal",
    "refining_downstream": "refinery_signal",
    "procurement": "procurement_signal",
    "historical": "historical_disruption",
}

ASSET_TYPE_TO_LABEL = {
    "country": "Country",
    "port": "Port",
    "terminal": "Terminal",
    "storage": "StorageTerminal",
    "storage_terminal": "StorageTerminal",
    "refinery": "Refinery",
    "pipeline": "Pipeline",
    "power": "PowerIndustry",
    "power_industry": "PowerIndustry",
    "consumer": "Consumer",
    "supplier": "Supplier",
    "corporate": "Supplier",
    "organization": "Organization",
    "commodity": "Commodity",
    "route": "ShippingRoute",
    "shipping_route": "ShippingRoute",
    "chokepoint": "ShippingRoute",
}


@dataclass(frozen=True)
class SchemaStatement:
    """A named Cypher statement loaded from schema assets."""

    name: str
    cypher: str

