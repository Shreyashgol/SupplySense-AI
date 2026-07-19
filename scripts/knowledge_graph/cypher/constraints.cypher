CREATE CONSTRAINT country_entity_key_unique IF NOT EXISTS
FOR (n:Country) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT port_entity_key_unique IF NOT EXISTS
FOR (n:Port) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT terminal_entity_key_unique IF NOT EXISTS
FOR (n:Terminal) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT refinery_entity_key_unique IF NOT EXISTS
FOR (n:Refinery) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT storage_terminal_entity_key_unique IF NOT EXISTS
FOR (n:StorageTerminal) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT pipeline_entity_key_unique IF NOT EXISTS
FOR (n:Pipeline) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT power_industry_entity_key_unique IF NOT EXISTS
FOR (n:PowerIndustry) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT consumer_entity_key_unique IF NOT EXISTS
FOR (n:Consumer) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT supplier_entity_key_unique IF NOT EXISTS
FOR (n:Supplier) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT commodity_entity_key_unique IF NOT EXISTS
FOR (n:Commodity) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT shipping_route_entity_key_unique IF NOT EXISTS
FOR (n:ShippingRoute) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT organization_entity_key_unique IF NOT EXISTS
FOR (n:Organization) REQUIRE n.entity_key IS UNIQUE;

CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (n:Event) REQUIRE n.event_id IS UNIQUE;

CREATE CONSTRAINT event_cluster_id_unique IF NOT EXISTS
FOR (n:EventCluster) REQUIRE n.cluster_id IS UNIQUE;

CREATE CONSTRAINT record_id_unique IF NOT EXISTS
FOR (n:Record) REQUIRE n.record_id IS UNIQUE;

