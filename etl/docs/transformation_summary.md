# Data Cleaning, Wrangling and Validation Summary

NYC Yellow Taxi Data Warehouse (2025) — what the ETL does to the data, and why.
Details and full mappings: `etl_documentation.md`.

---

## 1. Approach in brief

- **Bronze is never cleaned.** It is an exact copy of the source, so every original value stays available.
- **All cleaning happens in Silver.** Each trip is either **accepted** (standardized) or **rejected** with exactly one recorded reason.
- **Gold only reshapes.** It converts accepted trips into a star schema (surrogate keys, date/time keys, dimension lookups). No further filtering.
- **Nothing is silently dropped.** Row counts must reconcile: `source = bronze = silver + rejected`, and `silver = gold fact`.
- **Real-world oddities are kept** when they are legitimate (negative fares, zero-distance trips), so totals stay faithful to the source.

```
Source ──copy──► Bronze ──validate + clean──► Silver ──reshape──► Gold
                 (raw)     │ accepted → silver.yellow_taxi_trips   (star schema)
                           └ rejected → silver.rejected_trips
```

---

## 2. Source data issues and how each is handled

From the source profiling in `etl_handoff.md`:

| Issue found in the source | Handling |
|---|---|
| Negative fares and totals (cancellations, disputes, voids) | **Kept.** Treated as valid adjustments so totals reconcile. |
| Zero-distance trips with a fare | **Kept.** Valid minimum-fare or immediate-dropoff trips. |
| Timestamps outside 2025 (meter clock errors) | **Rejected** (`pickup_outside_2025`, `dropoff_out_of_range`). Routed to `rejected_trips`, not dropped. |
| NULL optional surcharges and fees | **Defaulted to 0.** |
| NULL or unknown category codes (ratecode, payment, location, vendor) | **Mapped to Unknown** values, or rejected for vendor (see section 4). |
| Duplicate-looking trips (same timestamps and vendor) | **Not deduplicated.** `trip_id` is the key; identical timestamps are legitimate. |
| Outdated vendor name for vendor 2 ("VeriFone") | Replaced with the TLC's current name, **Curb Mobility, LLC**. |

---

## 3. Validation: accept / reject rules (Silver)

Evaluated in order; the **first** matching rule is the recorded reason.

| # | Reason code | Rejects a trip when… | Why |
|---|---|---|---|
| 1 | `missing_timestamp` | pickup or dropoff time is NULL | Cannot date or time the trip |
| 2 | `pickup_outside_2025` | pickup outside 2025 | Out of the warehouse's date range |
| 3 | `nonpositive_duration` | dropoff is at or before pickup | Impossible trip |
| 4 | `dropoff_out_of_range` | dropoff on/after 2026-01-02 | No matching date in `dim_date` |
| 5 | `excessive_duration` | trip longer than 24 hours | Implausible; likely meter left running |
| 6 | `negative_distance` | distance below 0 | Invalid measurement |
| 7 | `excessive_distance` | distance above 500 miles | Implausible |
| 8 | `excessive_speed` | average speed above 100 mph | Implausible distance/time combination |
| 9 | `invalid_passengers` | passengers below 0 or above 6 | Implausible |
| 10 | `missing_primary_amount` | fare or total is NULL | Core measures are required |
| 11 | `distance_out_of_range` | distance ≥ 99,999,999 | Cannot fit the column |
| 12 | `vendor_out_of_range` | vendor id outside SMALLINT | Cannot fit the column |
| 13 | `unmapped_vendor` | vendor NULL or not in the provider list | Silver requires a valid vendor |
| 14 | `amount_out_of_range` | any money value ≥ 99,999,999 in absolute value | Cannot fit the column |

Thresholds in rules 5, 7, 8 and 9 (24 hours, 500 miles, 100 mph, 6 passengers) are **project choices, not TLC limits**, and are configurable at the top of `etl_pipeline.py`.

**Deliberately accepted:** negative amounts, zero distance, passenger count of 0 or NULL, NULL optional fields.

---

## 4. Cleaning and standardization (accepted trips)

| Field(s) | Rule |
|---|---|
| Vendor | Cast to SMALLINT; must match the provider list |
| Ratecode | NULL or unknown code → **99** (Null/unknown) |
| Payment type | NULL or unknown code → **5** (Unknown) |
| Pickup / dropoff location | NULL or unmatched zone → NULL (becomes the Unknown member in Gold) |
| Store-and-forward flag | Trimmed, upper-cased; anything other than `Y` or `N` → NULL |
| Passenger count | Cast to SMALLINT; NULL kept |
| Trip distance | Rounded to 2 decimals; NULL kept |
| Fare and total | Rounded to 2 decimals |
| Extra, MTA tax, tip, tolls, improvement surcharge, congestion surcharge, airport fee, CBD congestion fee | NULL → 0; rounded to 2 decimals |
| Reference zone names | Blank borough, zone or service zone → `'Unknown'` |

Reference mappings (vendors, rate codes, payment types) follow the **TLC Yellow Taxi Data Dictionary, March 18, 2025**.

---

## 5. Wrangling and derived fields

**Bronze → Silver**

- `trip_id` renamed to `source_trip_id` in Bronze, then to `bronze_trip_id` in Silver (lineage key).
- Types changed from double precision / bigint to `NUMERIC(10,2)` / `SMALLINT`.
- Derived `trip_duration_minutes` = (dropoff − pickup) in minutes, 2 decimals.
- `source_file` and `imported_at` stay in Bronze only.

**Silver → Gold**

- `dim_date` generated for 2025-01-01 to 2026-01-01 (366 rows): ISO weekday, ISO week, quarter, weekend flag.
- `dim_time` generated at second precision (86,400 rows) with time-of-day periods.
- Vendor, location, payment and ratecode dimensions built from the Silver reference tables, each with surrogate keys.
- Fact table keys: date key `YYYYMMDD`, time key `HHMMSS`, and surrogate-key lookups for each dimension.
- Missing vendor or location → Unknown member (key −1). Payment and ratecode already carry TLC Unknown codes.
- Measures copied unchanged from Silver to Gold.

---

## 6. Validation layers (where bad data is caught)

| Layer | Check |
|---|---|
| **Pre-flight** | Source `import_manifest`: every file `COMPLETED`, imported rows = Parquet rows, manifest total = table count |
| **Silver rules** | The 14 accept/reject rules above |
| **Silver constraints** | Database checks: dropoff ≥ pickup, distance ≥ 0, passengers ≥ 0, flag is `Y`/`N`, duration ≥ 0; foreign keys to all reference tables |
| **Gold lookups** | Run stops if any Silver trip would get a NULL payment or ratecode key |
| **Reconciliation** | Counts, classification and measures, listed below |

**Reconciliation checks**

- source = Bronze row count
- Bronze = Silver + rejected
- Silver = Gold fact
- No trip is both accepted and rejected
- No Bronze trip is unclassified
- Every Silver trip has a Gold fact row
- No NULL payment or ratecode keys in the fact table
- Trip-level `total_amount`, `fare_amount`, `trip_distance` and `trip_duration_minutes` match between Silver and Gold
- Total amount and total distance match between Silver and Gold
- Rejected counts are logged per reason

---

## 7. Traceability

- Every rejected trip is stored in `silver.rejected_trips` (trip id, reason, source file, timestamp).
- Every accepted trip links back to its Bronze row (`bronze_trip_id`) and, through Bronze, to the original Parquet file.
- Progress is stored in `silver.etl_checkpoints`, so reruns skip finished batches and cannot create duplicates.

---

## 8. To confirm with the team

- Plausibility thresholds (24 h, 500 miles, 100 mph, 6 passengers).
- Whether trips with an unmapped vendor should be rejected (current) or mapped to an Unknown vendor.
- Whether negative-amount trips should be flagged with a reversal column in addition to being kept.
- Whether `passenger_count` of 0 or NULL should stay as-is (current) or become a default.

---

## 9. Impact on the data (fill in after the full run)

| Metric | Count | % of source |
|---|---|---|
| Source rows | | 100% |
| Accepted (Silver / Gold) | | |
| Rejected (total) | | |

| Reject reason | Count |
|---|---|
| `missing_timestamp` | |
| `pickup_outside_2025` | |
| `nonpositive_duration` | |
| `dropoff_out_of_range` | |
| `excessive_duration` | |
| `negative_distance` | |
| `excessive_distance` | |
| `excessive_speed` | |
| `invalid_passengers` | |
| `missing_primary_amount` | |
| `distance_out_of_range` | |
| `vendor_out_of_range` | |
| `unmapped_vendor` | |
| `amount_out_of_range` | |

| Defaulted value | Rows affected |
|---|---|
| Ratecode → 99 | |
| Payment type → 5 | |
| Location → NULL / Unknown | |
| Surcharge NULL → 0 | |
| Store-and-forward flag → NULL | |

Useful queries to fill these in:

```sql
SELECT reject_reason, COUNT(*) FROM silver.rejected_trips GROUP BY 1 ORDER BY 2 DESC;
SELECT COUNT(*) FROM bronze.yellow_taxi_trips WHERE ratecodeid IS NULL;
SELECT COUNT(*) FROM bronze.yellow_taxi_trips WHERE payment_type IS NULL;
SELECT COUNT(*) FROM silver.yellow_taxi_trips WHERE pickup_location_id IS NULL OR dropoff_location_id IS NULL;
```