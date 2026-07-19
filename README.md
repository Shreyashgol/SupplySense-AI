
## Known Limitations
- **SWIFT/LC Proxy Data**: Due to the lack of free public APIs for SWIFT banking channels and Letter of Credit (LC) data, this pipeline utilizes proxy financial indicators (like FX rates) as a substitute for direct trade finance intelligence.
- **Low-Volume Domains**: Certain domains like `policy` (e.g., DGFT, MoPNG notifications) and `procurement` (e.g., GeM Tenders) update infrequently. Zero-row runs for these domains are expected during short intervals and accurately reflect the lack of new published data on their respective official portals.
