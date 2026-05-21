# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a data processing workflow that generates daily bidding space analysis (竞价空间分析) Excel files from load forecast data. Each day's forecast `.xls` file is downloaded externally and processed using the template `.xlsx`.

## File inventory

- `assets/0521-竞价空间分析.xlsx` — Template with Sheet1 containing the 96-time-point structure and historical reference data in lower rows. This is the base copied for each new output.
- `assets/YYYY-MM-DD负荷信息预测.xls` — Source forecast files (e.g., `2026-05-21负荷信息预测.xls`).
- `output/MMDD-竞价空间分析.xlsx` — Generated output files.

## Data flow

**Source** (`YYYY-MM-DD负荷信息预测.xls`): 4 sheets each with row 1 = time headers (00:15–24:00, 96 points), row 2 = forecast values:

| Source sheet | Target row in Sheet1 |
|---|---|
| 直调负荷 | Row 3 |
| 联络线受电负荷 | Row 4 |
| 风电总加 | Row 5 |
| 光伏总加 | Row 6 |

**Template** (`0521-竞价空间分析.xlsx`): Sheet1 has 97 columns (col A = label, cols B–CS = 96 time points) and 28 rows. Only rows 3–6 are replaced with new data; rows 10+ contain historical reference data that stays as-is.

**Output**: Copy of template, then write the 4 data rows (3–6) with numeric values, and set formulas:
- Row 7 (竞价空间): `=<col>3-<col>4-<col>5-<col>6`
- Row 8 (火电+核电+抽蓄): `=MAX(B7:CS7)+4000+4000` (col B), others reference previous column
- Row 9 (竞价空间/火电+核电+抽蓄): `=<col>7/<col>8`

## Processing a new day

When the user provides a source file path and asks to generate the analysis:

1. Read the 4 source sheets via `pandas.read_excel()`, extracting `df.iloc[2, 1:]` (96 numeric values each)
2. Copy the template to `output/MMDD-竞价空间分析.xlsx`
3. Use `openpyxl` to write values to rows 3–6, columns B–CS (columns 2–97)
4. Write formulas to rows 7–9
5. Save

Keep numbers as floats. The `openpyxl` `data_type` should be `n` for data cells and `f` for formula cells — write formulas as strings starting with `=`.
