"""Reference geodata for Part C/G geospatial evidence enrichment.

Country centroid coordinates used to backfill ``lat``/``lon`` onto
``Country``/``Port`` graph nodes when NLP-resolved region/location text
does not match a specific ``config/energy_entities.yaml`` gazetteer entry
(chokepoints, refineries, named terminals already carry their own precise
coordinates from that file).

Coordinates are approximate geographic centers (not capitals) — adequate
for regional risk visualization and distance-based reasoning, not survey
precision. ``resolve_country_centroid`` never fabricates a location: it
returns ``None`` when nothing matches rather than guessing.
"""

from __future__ import annotations

COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "AFGHANISTAN": (33.9391, 67.7100),
    "ALBANIA": (41.1533, 20.1683),
    "ALGERIA": (28.0339, 1.6596),
    "ANGOLA": (-11.2027, 17.8739),
    "ARGENTINA": (-38.4161, -63.6167),
    "ARMENIA": (40.0691, 45.0382),
    "AUSTRALIA": (-25.2744, 133.7751),
    "AUSTRIA": (47.5162, 14.5501),
    "AZERBAIJAN": (40.1431, 47.5769),
    "BAHRAIN": (25.9304, 50.6378),
    "BANGLADESH": (23.6850, 90.3563),
    "BELARUS": (53.7098, 27.9534),
    "BELGIUM": (50.5039, 4.4699),
    "BOTSWANA": (-22.3285, 24.6849),
    "BRAZIL": (-14.2350, -51.9253),
    "BULGARIA": (42.7339, 25.4858),
    "CAMEROON": (7.3697, 12.3547),
    "CANADA": (56.1304, -106.3468),
    "CHAD": (15.4542, 18.7322),
    "CHILE": (-35.6751, -71.5430),
    "CHINA": (35.8617, 104.1954),
    "COLOMBIA": (4.5709, -74.2973),
    "CUBA": (21.5218, -77.7812),
    "CYPRUS": (35.1264, 33.4299),
    "DENMARK": (56.2639, 9.5018),
    "DJIBOUTI": (11.8251, 42.5903),
    "ECUADOR": (-1.8312, -78.1834),
    "EGYPT": (26.8206, 30.8025),
    "ERITREA": (15.1794, 39.7823),
    "ESTONIA": (58.5953, 25.0136),
    "ETHIOPIA": (9.1450, 40.4897),
    "FINLAND": (61.9241, 25.7482),
    "FRANCE": (46.2276, 2.2137),
    "GABON": (-0.8037, 11.6094),
    "GEORGIA": (42.3154, 43.3569),
    "GERMANY": (51.1657, 10.4515),
    "GHANA": (7.9465, -1.0232),
    "GREECE": (39.0742, 21.8243),
    "GUINEA": (9.9456, -9.6966),
    "HONG KONG": (22.3193, 114.1694),
    "HUNGARY": (47.1625, 19.5033),
    "INDIA": (20.5937, 78.9629),
    "INDONESIA": (-0.7893, 113.9213),
    "IRAN": (32.4279, 53.6880),
    "IRAQ": (33.2232, 43.6793),
    "IRELAND": (53.1424, -7.6921),
    "ISRAEL": (31.0461, 34.8516),
    "ITALY": (41.8719, 12.5674),
    "JAPAN": (36.2048, 138.2529),
    "JORDAN": (30.5852, 36.2384),
    "KAZAKHSTAN": (48.0196, 66.9237),
    "KENYA": (-0.0236, 37.9062),
    "KUWAIT": (29.3117, 47.4818),
    "LATVIA": (56.8796, 24.6032),
    "LEBANON": (33.8547, 35.8623),
    "LIBYA": (26.3351, 17.2283),
    "LITHUANIA": (55.1694, 23.8813),
    "MALAYSIA": (4.2105, 101.9758),
    "MEXICO": (23.6345, -102.5528),
    "MOROCCO": (31.7917, -7.0926),
    "MOZAMBIQUE": (-18.6657, 35.5296),
    "MALI": (17.5707, -3.9962),
    "MOLDOVA": (47.4116, 28.3699),
    "MYANMAR": (21.9162, 95.9560),
    "NEPAL": (28.3949, 84.1240),
    "NETHERLANDS": (52.1326, 5.2913),
    "NEW ZEALAND": (-40.9006, 174.8860),
    "NIGERIA": (9.0820, 8.6753),
    "NORTH KOREA": (40.3399, 127.5101),
    "NORWAY": (60.4720, 8.4689),
    "OMAN": (21.4735, 55.9754),
    "PAKISTAN": (30.3753, 69.3451),
    "PANAMA": (8.5380, -80.7821),
    "PERU": (-9.1900, -75.0152),
    "PHILIPPINES": (12.8797, 121.7740),
    "POLAND": (51.9194, 19.1451),
    "PORTUGAL": (39.3999, -8.2245),
    "QATAR": (25.3548, 51.1839),
    "ROMANIA": (45.9432, 24.9668),
    "RUSSIA": (61.5240, 105.3188),
    "SAUDI ARABIA": (23.8859, 45.0792),
    "SINGAPORE": (1.3521, 103.8198),
    "SOMALIA": (5.1521, 46.1996),
    "SOUTH AFRICA": (-30.5595, 22.9375),
    "SOUTH KOREA": (35.9078, 127.7669),
    "SOUTH SUDAN": (6.8770, 31.3070),
    "SPAIN": (40.4637, -3.7492),
    "SRI LANKA": (7.8731, 80.7718),
    "SUDAN": (12.8628, 30.2176),
    "SWEDEN": (60.1282, 18.6435),
    "SWITZERLAND": (46.8182, 8.2275),
    "SYRIA": (34.8021, 38.9968),
    "TAIWAN": (23.6978, 120.9605),
    "TANZANIA": (-6.3690, 34.8888),
    "THAILAND": (15.8700, 100.9925),
    "TUNISIA": (33.8869, 9.5375),
    "TURKEY": (38.9637, 35.2433),
    "TURKMENISTAN": (38.9697, 59.5563),
    "UKRAINE": (48.3794, 31.1656),
    "UNITED ARAB EMIRATES": (23.4241, 53.8478),
    "UNITED KINGDOM": (55.3781, -3.4360),
    "UNITED STATES": (37.0902, -95.7129),
    "URUGUAY": (-32.5228, -55.7658),
    "UZBEKISTAN": (41.3775, 64.5853),
    "VENEZUELA": (6.4238, -66.5897),
    "VIETNAM": (14.0583, 108.2772),
    "WEST BANK": (31.9522, 35.2332),
    "GAZA": (31.5017, 34.4668),
    "YEMEN": (15.5527, 48.5164),
}

# US state names occasionally surface as standalone spaCy GPE extractions
# (e.g. a market report mentioning "Texas" refining capacity) without the
# country name alongside them; map them to the US centroid rather than
# leaving clearly-American locations unresolved.
US_STATE_NAMES: frozenset[str] = frozenset(
    {
        "ALABAMA", "ALASKA", "ARIZONA", "ARKANSAS", "CALIFORNIA", "COLORADO",
        "CONNECTICUT", "DELAWARE", "FLORIDA", "HAWAII", "IDAHO",
        "ILLINOIS", "INDIANA", "IOWA", "KANSAS", "KENTUCKY", "LOUISIANA",
        "MAINE", "MARYLAND", "MASSACHUSETTS", "MICHIGAN", "MINNESOTA",
        "MISSISSIPPI", "MISSOURI", "MONTANA", "NEBRASKA", "NEVADA",
        "NEW HAMPSHIRE", "NEW JERSEY", "NEW MEXICO", "NEW YORK",
        "NORTH CAROLINA", "NORTH DAKOTA", "OHIO", "OKLAHOMA", "OREGON",
        "PENNSYLVANIA", "RHODE ISLAND", "SOUTH CAROLINA", "SOUTH DAKOTA",
        "TENNESSEE", "TEXAS", "UTAH", "VERMONT", "VIRGINIA", "WASHINGTON STATE",
        "WEST VIRGINIA", "WISCONSIN", "WYOMING",
    }
)

# Major capital / hub cities that frequently appear as standalone NLP
# location extractions in geopolitical/market news (e.g. "London",
# "Manama") without the country name alongside them.
CAPITAL_CITY_TO_COUNTRY: dict[str, str] = {
    "LONDON": "UNITED KINGDOM",
    "MANAMA": "BAHRAIN",
    "BEIJING": "CHINA",
    "MOSCOW": "RUSSIA",
    "WASHINGTON": "UNITED STATES",
    "TEHRAN": "IRAN",
    "RIYADH": "SAUDI ARABIA",
    "DOHA": "QATAR",
    "ABU DHABI": "UNITED ARAB EMIRATES",
    "DUBAI": "UNITED ARAB EMIRATES",
    "DAMASCUS": "SYRIA",
    "BAGHDAD": "IRAQ",
    "TEL AVIV": "ISRAEL",
    "JERUSALEM": "ISRAEL",
    "ANKARA": "TURKEY",
    "CAIRO": "EGYPT",
    "TRIPOLI": "LIBYA",
    "SANAA": "YEMEN",
    "MUSCAT": "OMAN",
    "KUWAIT CITY": "KUWAIT",
    "TOKYO": "JAPAN",
}

# Common alternate names / abbreviations observed in GDELT, OFAC, and NLP
# entity-resolution output, mapped to the canonical key above.
COUNTRY_ALIASES: dict[str, str] = {
    "USA": "UNITED STATES",
    "US": "UNITED STATES",
    "U.S.": "UNITED STATES",
    "U.S.A.": "UNITED STATES",
    "AMERICA": "UNITED STATES",
    "THE UNITED STATES": "UNITED STATES",
    "UK": "UNITED KINGDOM",
    "BRITAIN": "UNITED KINGDOM",
    "GREAT BRITAIN": "UNITED KINGDOM",
    "UAE": "UNITED ARAB EMIRATES",
    "EMIRATES": "UNITED ARAB EMIRATES",
    "KOREA": "SOUTH KOREA",
    "REPUBLIC OF KOREA": "SOUTH KOREA",
    "DPRK": "NORTH KOREA",
    "RUSSIAN FEDERATION": "RUSSIA",
    "ISLAMIC REPUBLIC OF IRAN": "IRAN",
    "PEOPLE'S REPUBLIC OF CHINA": "CHINA",
    "PRC": "CHINA",
    "KSA": "SAUDI ARABIA",
    "KINGDOM OF SAUDI ARABIA": "SAUDI ARABIA",
    "MYANMAR (BURMA)": "MYANMAR",
    "BURMA": "MYANMAR",
}

_ALL_KEYS_BY_LENGTH_DESC: list[str] = sorted(
    list(COUNTRY_CENTROIDS.keys())
    + list(COUNTRY_ALIASES.keys())
    + list(CAPITAL_CITY_TO_COUNTRY.keys())
    + list(US_STATE_NAMES),
    key=len,
    reverse=True,
)


def resolve_country_centroid(name: str) -> tuple[float, float] | None:
    """Best-effort country centroid lookup for noisy NLP-resolved region text.

    Tries, in order: exact match, alias match, capital-city match, then
    substring match — this last step handles inputs like "Kyiv, Kyyiv,
    Misto, Ukraine" or "THE United States" that embed a known country name
    inside a longer, noisy NLP-extracted string. Longest candidate names are
    checked first so "SOUTH KOREA" is not shadowed by a shorter unrelated
    fragment. Returns ``None`` rather than guessing when nothing matches.
    """
    if not name:
        return None
    normalized = name.strip().upper()
    if normalized in COUNTRY_CENTROIDS:
        return COUNTRY_CENTROIDS[normalized]
    if normalized in COUNTRY_ALIASES:
        return COUNTRY_CENTROIDS.get(COUNTRY_ALIASES[normalized])
    if normalized in CAPITAL_CITY_TO_COUNTRY:
        return COUNTRY_CENTROIDS.get(CAPITAL_CITY_TO_COUNTRY[normalized])
    if normalized in US_STATE_NAMES:
        return COUNTRY_CENTROIDS.get("UNITED STATES")
    for candidate in _ALL_KEYS_BY_LENGTH_DESC:
        if candidate in normalized:
            if candidate in US_STATE_NAMES:
                return COUNTRY_CENTROIDS.get("UNITED STATES")
            resolved_name = (
                COUNTRY_ALIASES.get(candidate)
                or CAPITAL_CITY_TO_COUNTRY.get(candidate)
                or candidate
            )
            return COUNTRY_CENTROIDS.get(resolved_name)
    return None
