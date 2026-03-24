# Self-Hosted Geocoding Data: Research Report

**Date:** 2026-03-19
**Project:** CivPulse geo-api
**Scope:** Georgia addresses (expandable to national)
**Server:** Hundreds of GB RAM, TB-scale storage

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Current Architecture](#current-architecture)
- [Category 1: Government Sources](#category-1-government-sources)
- [Category 2: Open Source Self-Hosted Solutions](#category-2-open-source-self-hosted-solutions)
- [Category 3: Commercial Providers](#category-3-commercial-providers)
- [Cloud-Only Providers (No Self-Hosted Option)](#cloud-only-providers-no-self-hosted-option)
- [Supporting Tools](#supporting-tools)
- [Sources Not Viable](#sources-not-viable)
- [Overall Recommendations](#overall-recommendations)
- [Verification Strategy](#verification-strategy)
- [Glossary](#glossary)

---

## Executive Summary

This report evaluates **20+ geocoding data sources and solutions** across three categories
(government, open source, commercial) to identify the best options for self-hosting
geocoding data, eliminating per-request dependency on the US Census Bureau Geocoding API.

### Top Picks at a Glance

| Category | #1 Pick | Cost | Accuracy | Key Advantage |
|----------|---------|------|----------|---------------|
| **Government Data** | National Address Database (NAD) | Free | Address-point | Only free source with true point-level coordinates |
| **Open Source** | Pelias geocoder | Free | Address-point | Multi-source, Docker deploy, 10K+ queries/sec |
| **Commercial** | Smarty Local API | $25K-$100K/yr | Rooftop, CASS-certified | Drop-in REST API, easiest integration |
| **Overall Best** | Pelias + OpenAddresses | Free | Address-point | $0 cost, better than Census API, trivial resources for GA |

### Key Insight: Range Interpolation vs. Address Points

The Census Geocoder API uses TIGER/Line *address ranges* (e.g., "100-198 Main St") and
interpolates where a specific house number falls along the road segment. This introduces
**50-200 meters of positional error**. Sources like OpenAddresses and the National Address
Database provide actual *address point* coordinates (often derived from county parcel or
E911 data), delivering **rooftop-level accuracy** — a significant upgrade over the current
Census API approach.

---

## Current Architecture

CivPulse geo-api is a FastAPI-based geocoding service with the following relevant characteristics:

- **Geocoding provider:** US Census Bureau Geocoding API (range-interpolated, ~50-200m error)
- **Validation provider:** Scourgify (offline USPS Pub 28 address normalization)
- **Cache layer:** PostgreSQL with SHA-256 address hashing and upsert logic
- **Batch support:** Up to 100 addresses per batch, 10 concurrent requests
- **Provider pattern:** Pluggable `GeocodingProvider` base class — new providers can be added
  by extending the abstract class
- **Existing local data:** `data/Address_Points.geojson` (32 MB), `.kml` (68 MB), `.shp.zip`
  (2.3 MB) — likely sourced from Georgia state GIS portal

---

## Category 1: Government Sources

### Rank 1: National Address Database (NAD) — US DOT

The National Address Database is a collaborative effort between federal agencies and
state/local governments to create a comprehensive, publicly available address database
with point-level coordinates.

| Attribute | Details |
|-----------|---------|
| **What** | Individual address point records with lat/lon coordinates |
| **Coverage** | 80M+ records nationally; Georgia participation varies by county |
| **Format** | Geodatabase, Shapefile, CSV/text |
| **Accuracy** | Address-point level (not interpolated) — best accuracy among free sources |
| **License** | Public domain, no restrictions |
| **Updates** | Twice yearly |
| **GA data size** | Estimated 2-5 GB (subset of national ~15 GB download) |
| **URL** | https://www.transportation.gov/mission/open/gis/national-address-database/national-address-database-nad-disclaimer |

**Strengths:**
- Actual point coordinates (rooftop-level), not range interpolation
- Free with no usage restrictions
- The only government source providing true point-level geocoding data
- Federal backing ensures long-term availability

**Weaknesses:**
- Coverage gaps — state/county participation is voluntary
- Some Georgia counties may not contribute data
- Less frequently updated than some alternatives (twice yearly)

**Best for:** Primary address point data source, supplemented by TIGER/Line for gap coverage.

---

### Rank 2: OpenAddresses.io (Government-Sourced Aggregator)

OpenAddresses is an open data project that aggregates address point data exclusively from
government open data portals worldwide. While technically a community project, ~100% of
its data originates from government sources.

| Attribute | Details |
|-----------|---------|
| **What** | Aggregated address points from government open data portals |
| **Coverage** | ~300M+ US addresses (~80% of US population); strong Georgia coverage |
| **Format** | GeoJSON, CSV with lat/lon |
| **Accuracy** | Address-point level (sourced from authoritative government parcel/address data) |
| **License** | CC-0 / public domain for US data |
| **Updates** | Continuous (automated scraping of government portals) |
| **GA data size** | Estimated 500 MB - 2 GB |
| **URL** | https://openaddresses.io / https://batch.openaddresses.io |

**Strengths:**
- Nearly as accurate as NAD for point data
- Often has better coverage than NAD since it pulls directly from county-level GIS portals
  that may not participate in the NAD program
- Continuously updated via automated collection
- Well-structured, consistent data format across sources
- CC-0 license — maximum permissiveness

**Weaknesses:**
- Aggregator, not a primary source — quality depends on upstream government data
- Some counties may lack coverage
- No single authoritative entity behind the data

**Best for:** Primary data source for self-hosted geocoding engines like Pelias or Addok.
Excellent complement to NAD for filling coverage gaps.

---

### Rank 3: Census TIGER/Line Address Range Shapefiles (ADDRFEAT)

TIGER/Line files are the geographic backbone of the US Census Bureau, containing road
networks with associated address ranges. These are the same files that power the Census
Geocoding API.

| Attribute | Details |
|-----------|---------|
| **What** | Address ranges tied to road segments (e.g., "100-198 Main St, even side") |
| **Coverage** | 100% national — every county, every road |
| **Format** | Shapefile, ESRI Geodatabase |
| **Accuracy** | Range-interpolated only (~50-200m error) |
| **License** | Public domain |
| **Updates** | Annually (2025 data released September 2025) |
| **GA data size** | ~500 MB - 1 GB (159 county-level files) |
| **URL** | https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html |

**Strengths:**
- 100% geographic coverage — every road in every county
- Established, well-documented format
- Public domain with no restrictions
- Regular annual updates
- Same data the Census Geocoder API uses internally

**Weaknesses:**
- Does NOT provide individual address points — only ranges along road segments
- Self-hosting this gives the **same accuracy** as the Census API
- Benefit is eliminating API latency/dependency, not improving accuracy
- 159 separate county files for Georgia alone

**Best for:** Fallback/gap-filling layer behind point-level sources. Also useful if the
only goal is eliminating the external Census API dependency without improving accuracy.

---

### Rank 4: Georgia State GIS Portal

Georgia maintains its own GIS data clearinghouse with state-specific geographic datasets
including address points.

| Attribute | Details |
|-----------|---------|
| **What** | Georgia-specific address point data from the state GIS clearinghouse |
| **Format** | Varies (typically Shapefile, GeoJSON, or Geodatabase) |
| **Accuracy** | Address-point level (authoritative state data) |
| **License** | Typically public domain for government data |
| **URL** | https://gis.georgia.gov / Georgia GIS Clearinghouse |

**Strengths:**
- Most authoritative source for Georgia specifically
- May be the upstream source feeding both NAD and OpenAddresses for GA data
- Could have the most current data available
- The `data/Address_Points.geojson` already in the project likely came from here

**Weaknesses:**
- Requires manual investigation of available datasets
- Format and completeness varies by dataset
- No standardized update schedule
- State-specific only — not scalable to other states without additional research

**Best for:** Direct source when Georgia-specific data is needed and you want the most
authoritative, current version. Worth checking before using NAD or OpenAddresses.

---

## Category 2: Open Source Self-Hosted Solutions

### Rank 1: Pelias Geocoder

Pelias is a modular, open-source geocoding engine built on Elasticsearch that combines
multiple data sources for comprehensive coverage with address-point accuracy.

| Attribute | Details |
|-----------|---------|
| **What** | Modular geocoding engine combining multiple data sources |
| **Data sources** | OpenAddresses + OSM + Who's on First + GeoNames |
| **Accuracy** | Address-point level (via OpenAddresses) with interpolation fallback (via OSM/TIGER) |
| **GA-only resources** | ~4-8 GB RAM, ~20-50 GB disk |
| **National resources** | ~32-64 GB RAM, ~200 GB SSD |
| **Setup** | Docker Compose — hours, not days |
| **Query performance** | 10,000+ queries/sec on Elasticsearch backend |
| **License** | MIT |
| **Repository** | https://github.com/pelias/pelias |
| **Hosted option** | Geocode.earth ($9.99-$99.99/month) for testing/validation |

**Strengths:**
- Best combination of accuracy and coverage among open source options
- Multi-source fallback: if OpenAddresses lacks an address, falls back to OSM interpolation
- Docker Compose deployment — straightforward for Georgia-only
- Georgia deployment would use a trivial fraction of available server resources
- MIT license — maximum flexibility
- REST API maps directly to existing `GeocodingProvider` pattern
- Active development and community (backed by Geocode.earth team)
- Uses Libpostal internally for address parsing

**Weaknesses:**
- Elasticsearch dependency adds operational complexity
- Multiple data importers to configure and maintain
- Data refresh requires re-importing (not incremental)
- More complex than single-source solutions

**Integration approach:**
1. Deploy Pelias via Docker Compose with Georgia-only data
2. Create `PeliasProvider` class extending `GeocodingProvider`
3. Map Pelias JSON response to existing `GeocodingResult` model
4. Register alongside or in place of Census provider

---

### Rank 2: Addok + OpenAddresses

Addok is a lightweight Python geocoder backed by Redis, designed specifically for indexing
address datasets like OpenAddresses.

| Attribute | Details |
|-----------|---------|
| **What** | Lightweight Python + Redis geocoder for address datasets |
| **Data sources** | OpenAddresses (or any CSV with addresses + coordinates) |
| **Accuracy** | Address-point level (inherits from data source) |
| **GA-only resources** | ~2-4 GB RAM, ~5-10 GB disk |
| **Setup** | `pip install addok` + Redis — straightforward |
| **Query performance** | Thousands of queries/sec (Redis-backed) |
| **License** | MIT |
| **Repository** | https://github.com/addok/addok |

**Strengths:**
- Lightest resource footprint among all options
- Python-native — matches the FastAPI/Python stack perfectly
- Can be called in-process (no HTTP overhead) or via REST API
- Simple to understand and maintain
- Can index OpenAddresses CSV data directly
- MIT license

**Weaknesses:**
- Single data source — no multi-source fallback
- Smaller community than Pelias or Nominatim
- Originally built for French addresses; US usage is less documented
- Redis dependency (though lightweight)
- Less sophisticated address parsing than Pelias (no Libpostal)

**Best for:** Simplest possible self-hosted geocoding with address-point accuracy. Ideal
if you want minimal operational complexity and are okay with OpenAddresses as the sole data
source.

---

### Rank 3: Nominatim (Official OSM Geocoder)

Nominatim is the official geocoder for OpenStreetMap, widely used and well-documented.

| Attribute | Details |
|-----------|---------|
| **What** | Official OpenStreetMap geocoder with TIGER data integration |
| **Data sources** | OSM + TIGER/Line (for US address ranges) |
| **Accuracy** | Range-interpolated for most US addresses (~175m median error) |
| **GA-only resources** | ~8-16 GB RAM, ~30-50 GB disk |
| **National resources** | ~64-128 GB RAM, 900 GB+ disk |
| **Setup** | PostgreSQL + special indices; hours to import for GA-only |
| **License** | GPLv3 (copyleft) |
| **Repository** | https://github.com/osm-search/Nominatim |

**Strengths:**
- Most established open-source geocoder — large community, extensive documentation
- PostgreSQL-based — aligns with existing database infrastructure
- TIGER integration provides US address range coverage
- Reverse geocoding support
- Well-tested at scale (powers nominatim.openstreetmap.org)

**Weaknesses:**
- US address accuracy is lower than OpenAddresses-based solutions (interpolated, not point)
- OSM address coverage in the US is uneven (good urban, sparse rural)
- Median ~175m error vs Google's ~9m for US addresses
- GPLv3 license — copyleft implications if distributing
- More complex setup than Pelias or Addok
- Heavier resource requirements

**Best for:** Projects that need a well-established geocoder with strong community support
and don't require address-point accuracy. Better suited for European addresses where OSM
coverage is excellent.

---

### Rank 4: Photon

Photon is a lightweight geocoder by Komoot, built on OpenStreetMap data with
Elasticsearch.

| Attribute | Details |
|-----------|---------|
| **What** | Lightweight OSM-based geocoder with typo tolerance and autocomplete |
| **Data sources** | OpenStreetMap |
| **Accuracy** | Same as Nominatim (OSM data, interpolated for US addresses) |
| **GA-only resources** | ~4-8 GB RAM, ~15-30 GB disk |
| **National resources** | ~64 GB RAM, ~95 GB disk |
| **Setup** | Pre-built database dumps available — easier than Nominatim |
| **License** | Apache 2.0 |
| **Repository** | https://github.com/komoot/photon |

**Strengths:**
- Easiest setup among OSM-based geocoders (pre-built database dumps)
- Excellent typo-tolerant search-as-you-type capability
- Apache 2.0 license (permissive, no copyleft)
- Elasticsearch backend — fast fuzzy matching
- Lighter than Nominatim

**Weaknesses:**
- Same underlying OSM data quality limitations for US addresses
- No built-in TIGER integration (relies solely on OSM address data)
- Primarily designed for autocomplete/search, not batch geocoding
- Smaller community than Nominatim

**Best for:** Autocomplete/search-as-you-type use cases. Not the best choice for batch
geocoding where accuracy is the priority.

---

### Rank 5: PostGIS TIGER Geocoder

The PostGIS TIGER geocoder is a PostgreSQL extension that performs geocoding using
TIGER/Line data directly within an existing PostgreSQL database.

| Attribute | Details |
|-----------|---------|
| **What** | PostgreSQL/PostGIS extension for geocoding with TIGER/Line data |
| **Data sources** | Census TIGER/Line files |
| **Accuracy** | Range-interpolated (same as Census API) |
| **GA-only resources** | ~2-4 GB additional in existing PostgreSQL |
| **Setup** | SQL scripts to load TIGER data into PostGIS |
| **License** | PostgreSQL license (permissive) |

**Strengths:**
- Runs inside existing PostgreSQL — zero additional infrastructure
- SQL function calls — `SELECT geocode('123 Main St, Atlanta, GA')`
- Integrates directly with your existing database
- Lowest operational complexity
- Permissive license

**Weaknesses:**
- Same accuracy as Census API — no improvement, just eliminates the external call
- TIGER data loading scripts can be finicky
- Less actively maintained than standalone geocoders
- No address-point data — interpolation only

**Best for:** Quick win to eliminate the Census API dependency without any accuracy
improvement. Best if the primary motivation is removing the external API call rather than
improving geocoding quality.

---

## Category 3: Commercial Providers

### Rank 1: Smarty (formerly SmartyStreets) — Local API

Smarty is a US-focused address verification and geocoding company that offers a true
self-hosted local API option.

| Attribute | Details |
|-----------|---------|
| **What** | Self-hosted REST API for address verification + geocoding |
| **Accuracy** | Rooftop-level, CASS-certified (USPS gold standard) |
| **Coverage** | US and Canada |
| **Deployment** | Drop-in local REST API — identical interface to cloud API |
| **Pricing** | Estimated $25K-$100K+/year (volume/feature dependent) |
| **Updates** | Monthly data refreshes included in license |
| **URL** | https://www.smarty.com |

**Strengths:**
- Most seamless integration — same REST interface as their cloud API
- CASS-certified — USPS-validated address verification
- Rooftop-level accuracy
- Monthly data updates included
- Lowest integration effort among commercial options
- REST API maps directly to existing provider pattern

**Weaknesses:**
- Significant annual cost
- US/Canada only (not global)
- Proprietary data — vendor lock-in risk
- License terms may restrict certain use cases

**Best for:** Organizations that need CASS-certified address verification with rooftop
geocoding and have budget for commercial licensing. The easiest commercial path to
production-grade geocoding for your architecture.

---

### Rank 2: Melissa Data — Geocoder Object

Melissa provides address verification, geocoding, and data quality tools with installable
SDK options.

| Attribute | Details |
|-----------|---------|
| **What** | Installable SDK for address verification + geocoding |
| **Accuracy** | Rooftop-level for US addresses |
| **Coverage** | Global (240+ countries) |
| **Deployment** | Native SDK — Python, Java, .NET, C |
| **Pricing** | Estimated $15K-$75K+/year |
| **Updates** | Monthly |
| **URL** | https://www.melissa.com |

**Strengths:**
- Python SDK — can be called as a function, zero HTTP overhead
- Good price-to-accuracy ratio (potentially cheaper than Smarty)
- Global coverage if future expansion beyond Georgia/US is needed
- In-process integration eliminates network latency entirely

**Weaknesses:**
- Less well-known than Smarty in the geocoding space
- SDK integration is tighter coupling than REST API
- Proprietary data and SDK

**Best for:** Python-native projects that want to minimize latency by calling geocoding
as an in-process function rather than a REST API.

---

### Rank 3: Esri/ArcGIS StreetMap Premium

Esri provides offline geocoding capabilities through StreetMap Premium data with the
ArcGIS platform.

| Attribute | Details |
|-----------|---------|
| **What** | Offline geocoding data for ArcGIS platform |
| **Accuracy** | Rooftop-level, comprehensive |
| **Coverage** | Global |
| **Deployment** | Requires ArcGIS Enterprise infrastructure |
| **Pricing** | Estimated $10K-$50K+/year (plus ArcGIS Enterprise licensing) |
| **URL** | https://www.esri.com |

**Strengths:**
- Excellent data quality — industry-leading geographic data
- True offline/disconnected operation (including mobile devices)
- Comprehensive GIS ecosystem if broader spatial analysis is needed

**Weaknesses:**
- Requires ArcGIS Enterprise ecosystem — heavy infrastructure buy-in
- Doesn't align with Python/FastAPI/PostGIS stack
- Total cost includes ArcGIS licensing plus data licensing
- Overkill for geocoding-only use case

**Best for:** Organizations already invested in the ArcGIS ecosystem. Not recommended for
this project due to stack misalignment.

---

### Rank 4: HERE Technologies

HERE provides automotive and enterprise-grade geocoding with self-hosted SDK options.

| Attribute | Details |
|-----------|---------|
| **What** | Self-hosted geocoding SDK with global coverage |
| **Accuracy** | Automotive-grade, rooftop-level |
| **Coverage** | Global (400M+ addresses, 100+ countries) |
| **Deployment** | Self-hosted SDK |
| **Pricing** | Estimated $50K-$200K+/year |
| **URL** | https://www.here.com |

**Strengths:**
- Automotive-grade accuracy (highest tier)
- Global coverage with excellent data quality
- Well-documented APIs

**Weaknesses:**
- Enterprise-focused pricing — expensive for a single-state deployment
- Far more data than needed for Georgia-only scope
- Complex enterprise sales process

**Best for:** Large-scale enterprise deployments needing global coverage with automotive
precision. Overkill for Georgia-only.

---

### Rank 5: Precisely (formerly Pitney Bowes)

Precisely offers the Spectrum Technology Platform for enterprise geocoding with the
highest accuracy tier.

| Attribute | Details |
|-----------|---------|
| **What** | Enterprise geocoding platform (Spectrum Technology Platform) |
| **Accuracy** | Highest accuracy tier available commercially |
| **Coverage** | 200+ countries |
| **Deployment** | On-premise platform |
| **Pricing** | Estimated $50K-$300K+/year |
| **URL** | https://www.precisely.com |

**Strengths:**
- Highest accuracy of any commercial option
- Comprehensive enterprise data quality platform
- 200+ country coverage

**Weaknesses:**
- Most complex deployment among commercial options
- Most expensive option
- Enterprise sales process
- Massive overkill for Georgia-only geocoding

**Best for:** Large enterprises with complex, global geocoding needs and significant
budgets. Not recommended for this project.

---

## Cloud-Only Providers (No Self-Hosted Option)

These providers were evaluated but do not offer self-hosted/on-premise deployment.
Included for completeness and comparison.

| Provider | Pricing | Coverage | Notes |
|----------|---------|----------|-------|
| **Google Maps Platform** | $5/1K requests (10K free/month) | Global | ToS **prohibits caching** results. No self-hosted option. Highest accuracy (~9m median). |
| **Geocodio** | $0.50/1K lookups (2,500 free/day) | US, Canada, Mexico | Very affordable. Cloud-only. Good accuracy for US addresses. |
| **TomTom** | $0.75/1K requests (2,500 free/day) | Global | Moving away from on-premise. Historically had local options. |
| **Mapbox** | Custom enterprise pricing | Global | "Atlas" on-premise product exists, but unclear if geocoding is included (vs. map tiles only). |

**Note:** Google's ToS prohibition on caching means you cannot store geocoding results —
this conflicts with the cache-first architecture already in place in geo-api.

---

## Supporting Tools

These are not standalone geocoding solutions but can enhance or complement the options above.

| Tool | What It Does | License | Resources | URL |
|------|-------------|---------|-----------|-----|
| **Libpostal** | Address parsing and normalization across 60 languages, 100+ countries. 98.9% parsing accuracy. | MIT | ~2 GB RAM, ~2 GB disk | https://github.com/openvenues/libpostal |
| **GeoNames** | 11M+ place names worldwide. City/region level only — not useful for street-level geocoding. | CC-BY 4.0 | Minimal | https://www.geonames.org |
| **DeGAUSS** | Docker-based batch geocoder using TIGER/Line data. Good for one-off batch processing. | GPL | Docker container | https://degauss.org |
| **Scourgify** | USPS Pub 28 address normalization (already in use in geo-api). | MIT | Minimal | https://github.com/GreenBuildingRegistry/usaddress-scourgify |

---

## Sources Not Viable

| Source | Reason for Exclusion |
|--------|---------------------|
| **Census Master Address File (MAF)** | Protected by Title 13 of the US Code. Not publicly available. Access requires application to a Federal Statistical Research Data Center with special researcher approval. Dead end for self-hosted geocoding. |
| **USPS Address Database (ZIP+4 Product)** | Commercial product requiring purchase from USPS. Does NOT include lat/lon coordinates — only postal delivery information (carrier routes, delivery points). Not useful for geocoding. |
| **USPS AIS Viewer** | Free tool with encrypted data that cannot be exported. Not useful for bulk data extraction. |
| **Census Gazetteer Files** | Only centroid coordinates for places, ZCTAs, and counties. Not address-level data. Very small files but wrong granularity. |

---

## Overall Recommendations

### Primary Recommendation: Pelias + OpenAddresses (Georgia-Only)

Given the project constraints — Georgia-only scope, powerful server infrastructure,
FastAPI/PostGIS stack, and pluggable provider architecture — this is the strongest option.

| Factor | Assessment |
|--------|-----------|
| **Cost** | $0 (all open source and public domain data) |
| **Accuracy** | Address-point level via OpenAddresses (superior to current Census API) |
| **Server resources** | ~4-8 GB RAM, ~20-50 GB disk — trivial on your hardware |
| **Setup effort** | Docker Compose deployment, hours not days |
| **Integration** | New `PeliasProvider` extending existing `GeocodingProvider` base class |
| **Maintenance** | Periodic data refresh (OpenAddresses updates continuously) |
| **Scalability** | Can expand to national coverage by adding more states to the data import |
| **License** | MIT (Pelias) + CC-0/public domain (OpenAddresses) |

**Implementation path:**
1. Download Georgia address data from OpenAddresses.io
2. Deploy Pelias via Docker Compose with GA-only data importers
3. Create a `PeliasProvider` class extending `GeocodingProvider`
4. Register alongside Census provider (dual-source for comparison)
5. Optionally add TIGER/Line data via Pelias interpolation engine for gap-filling
6. Benchmark accuracy against known addresses in `data/Address_Points.geojson`

### Runner-Up: PostGIS TIGER Geocoder

If the primary goal is simply eliminating the external Census API dependency **without
improving accuracy**, the PostGIS TIGER geocoder runs inside your existing PostgreSQL
database with minimal setup. Zero additional infrastructure. Same interpolated accuracy
as the Census API but zero network calls — reduces geocoding latency from ~200-500ms to
<10ms.

### Commercial Option: Smarty Local API

If commercial licensing is viable and budget is available, Smarty offers the fastest path
to CASS-certified, rooftop-accuracy geocoding with the simplest integration. The REST API
pattern maps directly to the existing Census provider implementation.

---

## Verification Strategy

To validate any chosen geocoding approach:

1. **Sample selection:** Extract 100-500 known Georgia addresses from
   `data/Address_Points.geojson` (which has authoritative point coordinates)

2. **Baseline measurement:** Geocode the sample through the current Census API provider
   and record lat/lon results

3. **New provider measurement:** Geocode the same addresses through the new provider

4. **Accuracy comparison:** Calculate distance between each result and the known
   authoritative point. Compare distributions:
   - Mean/median distance error
   - 90th/95th percentile error
   - Match rate (percentage of addresses successfully geocoded)

5. **Performance measurement:** Compare query latency:
   - Census API: typically 200-500ms per request (network-bound)
   - Self-hosted: expected <10ms per request (local)

6. **Coverage analysis:** Identify addresses that the new provider cannot geocode and
   assess whether gap-filling (TIGER fallback) is needed

---

## Glossary

| Term | Definition |
|------|-----------|
| **Address point** | A specific lat/lon coordinate for an individual address, typically derived from parcel centroids or E911 data. Rooftop-level accuracy. |
| **Range interpolation** | Estimating an address location by its position within a known address range along a road segment. Lower accuracy (~50-200m error). |
| **CASS certification** | Coding Accuracy Support System — USPS certification that address data meets postal delivery standards. |
| **TIGER/Line** | Topologically Integrated Geographic Encoding and Referencing — the Census Bureau's geographic database of roads, boundaries, and address ranges. |
| **Rooftop accuracy** | Geocoding precision that places the coordinate on or very near the actual building. Typically <10m error. |
| **Who's on First** | An open gazetteer of administrative boundaries (countries, states, counties, neighborhoods) used by Pelias for context. |
| **OSM** | OpenStreetMap — a collaborative, open-source map of the world maintained by volunteers. |
| **NAD** | National Address Database — a US DOT initiative to create a comprehensive national address dataset. |
