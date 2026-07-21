CREATE CONSTRAINT country_name_exists IF NOT EXISTS
FOR (n:Country) REQUIRE n.name IS NOT NULL;

CREATE CONSTRAINT port_name_exists IF NOT EXISTS
FOR (n:Port) REQUIRE n.name IS NOT NULL;

CREATE CONSTRAINT refinery_name_exists IF NOT EXISTS
FOR (n:Refinery) REQUIRE n.name IS NOT NULL;

CREATE CONSTRAINT supplier_name_exists IF NOT EXISTS
FOR (n:Supplier) REQUIRE n.name IS NOT NULL;

CREATE CONSTRAINT commodity_name_exists IF NOT EXISTS
FOR (n:Commodity) REQUIRE n.name IS NOT NULL;

CREATE CONSTRAINT shipping_route_name_exists IF NOT EXISTS
FOR (n:ShippingRoute) REQUIRE n.name IS NOT NULL;

CREATE CONSTRAINT event_timestamp_exists IF NOT EXISTS
FOR (n:Event) REQUIRE n.timestamp IS NOT NULL;

CREATE CONSTRAINT event_type_exists IF NOT EXISTS
FOR (n:Event) REQUIRE n.event_type IS NOT NULL;

CREATE CONSTRAINT record_timestamp_exists IF NOT EXISTS
FOR (n:Record) REQUIRE n.timestamp IS NOT NULL;

