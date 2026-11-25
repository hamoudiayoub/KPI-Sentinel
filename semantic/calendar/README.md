# semantic/calendar

Shared Moroccan calendar (`morocco.yaml`): public holidays, Ramadan, Eid, seasonality; used by the generator, dbt and the agent.

`morocco.yaml` holds:

- `utc_offset_hours`: local time is UTC+1, and UTC+0 during Ramadan.
- `fixed_holidays`: holidays on the same date every year, with an optional first year (`since`).
- `years`: for each year, the Ramadan period and the religious holidays (`eid_al_fitr`, `eid_al_adha`, `islamic_new_year`, `mawlid`), each as the list of its days off.

Religious dates follow the lunar calendar and are announced after moon sighting, so each one carries its source in a comment, and tentative dates are marked. Covered years: 2025 to 2027; extend the file before generating or analyzing data outside them (the generator refuses an uncovered period).
