CREATE INDEX event_timestamp_index IF NOT EXISTS
FOR (n:Event) ON (n.timestamp);

CREATE INDEX event_type_index IF NOT EXISTS
FOR (n:Event) ON (n.event_type);

CREATE INDEX event_severity_index IF NOT EXISTS
FOR (n:Event) ON (n.severity);

CREATE INDEX record_timestamp_index IF NOT EXISTS
FOR (n:Record) ON (n.timestamp);

CREATE INDEX record_domain_index IF NOT EXISTS
FOR (n:Record) ON (n.domain);

CREATE INDEX country_name_index IF NOT EXISTS
FOR (n:Country) ON (n.name);

CREATE INDEX port_name_index IF NOT EXISTS
FOR (n:Port) ON (n.name);

CREATE INDEX refinery_name_index IF NOT EXISTS
FOR (n:Refinery) ON (n.name);

CREATE INDEX supplier_name_index IF NOT EXISTS
FOR (n:Supplier) ON (n.name);

CREATE INDEX commodity_name_index IF NOT EXISTS
FOR (n:Commodity) ON (n.name);

CREATE INDEX shipping_route_name_index IF NOT EXISTS
FOR (n:ShippingRoute) ON (n.name);

