# NAIP display copies: query guidance

One file per quarter quad per state-year, from flights of 2021 to 2025. Each file name holds the date it was flown; a 2023 name then holds a second date, the day the file was made. The quad index gives the flight date of every file.

Use the following dataset-specific constraints when choosing records, interpreting values, or making comparisons:

- Display copy only. The files hold red, green and blue as lossy JPEG at quality 65, with overviews at quality 75 and colour at half resolution. The near-infrared band and the lossless pixels stay in s3://naip-analytic.
- Four Pennsylvania 2024 files carry a 2010 flight date in their names, as they do in the source.
- Pennsylvania 2024 (1,118 quads) and West Virginia 2024 (101 quads) cover only part of each state. Their files are hosted, under pa/2024/ and wv/2024/ and as overviews/pa-2024-utm18.tif and overviews/wv-2024-utm17.tif, but the two indexes do not list them and the national file is made without them. Both states are listed whole from 2022, so a map that draws the newest file over a place shows one flight per state. The rule is a count. A year holding under 90% of the quads of an older year of the same state is not listed.
- The 2024 folders of the source lack every quad numbered xx12023 (California and Oregon at 120 W), and Florida 2025 lacks a strip of south Florida. Those places are filled with only the missing quads from California 2022, Oregon 2022 and Florida 2023. They differ from their neighbours in year, season and tone.
- The overview files are for drawing a map, not for measurement. A state file holds one flight year of one state in one UTM zone at 9.6 m; the national file holds the latest flight of each state, so neighbouring states can differ in year and in tone.
- Adjacent quarter quads overlap, as they do in the source.

[Field dictionaries, runnable queries and source citations](README.md).
[Shared catalog conventions](../AGENTS.md).
