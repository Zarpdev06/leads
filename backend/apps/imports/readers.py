"""
Streaming readers for CSV / XLSX.

Design rule: memory usage is O(chunk), never O(file). 82-million-row files are
processed in 1,000-row batches by a Celery worker that never holds more than
one batch (+ the row buffers) in RAM.

* CSV  -> pandas.read_csv(chunksize=...)  (C engine, dtype=str)
* XLSX -> openpyxl read_only + iter_rows(values_only=True) in batches
* XLS  -> rejected (legacy binary format); convert to XLSX/CSV first.
"""
from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass
from typing import Any, Iterator

import pandas as pd
from openpyxl import load_workbook

from apps.imports.models import ImportFile

MAX_SAMPLE_ROWS = 50
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm"}
MAGIC_BYTES = {
    "zip": b"PK\x03\x04",      # xlsx / xlsm
    "ole": b"\xd0\xcf\x11\xe0",  # legacy .xls
}


class ImportFileError(Exception):
    """Raised for anything that makes a file unusable (validation, parse...)."""


@dataclass
class FileMeta:
    file_type: str
    sheets: list[str]
    headers: list[str]
    delimiter: str
    encoding: str
    sample_rows: list[dict]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_upload(uploaded) -> str:
    """Validate extension, MIME and magic bytes. Returns the file type."""
    name = (getattr(uploaded, "name", "") or "").lower()
    ext = os.path.splitext(name)[1]

    if ext in {".xls"}:
        raise ImportFileError(
            "Legacy .xls files are not supported. Re-save the file as .xlsx or export it "
            "as CSV and upload again."
        )
    if ext not in SUPPORTED_EXTENSIONS:
        raise ImportFileError(
            f"Unsupported file type '{ext or 'unknown'}'. Upload a CSV or XLSX file."
        )

    size = getattr(uploaded, "size", None)
    if size is not None:
        from django.conf import settings

        max_bytes = int(settings.IMPORT_MAX_FILE_MB) * 1024 * 1024
        if size > max_bytes:
            raise ImportFileError(
                f"File is {size / 1048576:.1f} MB; the limit is "
                f"{settings.IMPORT_MAX_FILE_MB} MB. Split the file and re-upload."
            )

    head = _read_head(uploaded)
    if ext in {".xlsx", ".xlsm"} and not head.startswith(MAGIC_BYTES["zip"]):
        raise ImportFileError("The file is not a valid XLSX workbook (bad magic bytes).")
    if ext in {".xls"} and head.startswith(MAGIC_BYTES["ole"]):
        raise ImportFileError("Legacy .xls files are not supported.")
    return "XLSX" if ext in {".xlsx", ".xlsm"} else "CSV"


def _read_head(uploaded, length: int = 8) -> bytes:
    try:
        position = uploaded.tell()
        uploaded.seek(0)
        head = uploaded.read(length)
        uploaded.seek(position)
        return head if isinstance(head, bytes) else str(head).encode()
    except Exception:  # pragma: no cover - storage backends without seek
        return b""


# ---------------------------------------------------------------------------
# Metadata + preview
# ---------------------------------------------------------------------------
def detect_delimiter(path: str, encoding: str = "utf-8") -> str:
    with open(path, "r", encoding=encoding, errors="replace", newline="") as handle:
        sample = handle.read(64 * 1024)
    if not sample:
        return ","
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
        return max(counts, key=counts.get) or ","


def detect_encoding(path: str) -> str:
    try:
        import chardet

        with open(path, "rb") as handle:
            raw = handle.read(256 * 1024)
        guess = chardet.detect(raw) or {}
        return guess.get("encoding") or "utf-8"
    except Exception:  # pragma: no cover
        return "utf-8"


def read_xlsx_sheets(path: str) -> list[str]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def _clean_header(value: Any, index: int) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.lower().startswith("unnamed:"):
        return f"column_{index + 1}"
    return text


def inspect_file(path: str, file_type: str, *, sheet_name: str = "",
                 sample: int = MAX_SAMPLE_ROWS) -> FileMeta:
    """Read headers + a small preview. Never reads the whole file."""
    if file_type == ImportFile.FileType.XLSX:
        return _inspect_xlsx(path, sheet_name=sheet_name, sample=sample)

    encoding = detect_encoding(path)
    delimiter = detect_delimiter(path, encoding)
    headers: list[str] = []
    rows: list[dict] = []
    with open(path, "r", encoding=encoding, errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row_index, raw_row in enumerate(reader):
            if row_index == 0:
                headers = [_clean_header(value, i) for i, value in enumerate(raw_row)]
                continue
            if len(rows) >= sample:
                break
            rows.append(_row_to_dict(headers, raw_row))
    return FileMeta(
        file_type=ImportFile.FileType.CSV,
        sheets=[],
        headers=headers,
        delimiter=delimiter,
        encoding=encoding,
        sample_rows=rows,
    )


def _inspect_xlsx(path: str, *, sheet_name: str = "", sample: int = MAX_SAMPLE_ROWS) -> FileMeta:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[sheet_name] if sheet_name and sheet_name in workbook.sheetnames \
            else workbook[workbook.sheetnames[0]]
        headers: list[str] = []
        rows: list[dict] = []
        for row_index, raw_row in enumerate(sheet.iter_rows(values_only=True)):
            values = list(raw_row)
            if all(v is None or str(v).strip() == "" for v in values):
                continue
            if row_index == 0:
                headers = [_clean_header(v, i) for i, v in enumerate(values)]
                continue
            if len(rows) >= sample:
                break
            rows.append(_row_to_dict(headers, ["" if v is None else v for v in values]))
        # Deduplicate headers (Excel exports often repeat a column name)
        headers = _dedupe_headers(headers)
        return FileMeta(
            file_type=ImportFile.FileType.XLSX,
            sheets=list(workbook.sheetnames),
            headers=headers,
            delimiter=",",
            encoding="utf-8",
            sample_rows=rows,
        )
    finally:
        workbook.close()


def _dedupe_headers(headers: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for header in headers:
        count = seen.get(header, 0)
        seen[header] = count + 1
        out.append(header if count == 0 else f"{header}_{count + 1}")
    return out


def _row_to_dict(headers: list[str], values) -> dict:
    row: dict[str, Any] = {}
    for index, header in enumerate(headers):
        value = values[index] if index < len(values) else ""
        row[header] = "" if value is None else (str(value).strip() if not isinstance(value, str) else value.strip())
    return row


# ---------------------------------------------------------------------------
# Chunked iteration
# ---------------------------------------------------------------------------
def iter_csv_chunks(path: str, *, chunk_size: int, delimiter: str = ",",
                    encoding: str = "utf-8", skip_header: bool = True,
                    usecols: list[str] | None = None,
                    ) -> Iterator[list[dict]]:
    """Yield batches of dict rows. Constant memory.

    The header row is read (and cleaned) by the csv module first, so that the
    column names pandas uses are the *normalised* ones - otherwise `usecols`
    would not match exports that pad headers with spaces
    ("  Contact Person " -> "Contact Person").
    """
    header_length = 0
    with open(path, "r", encoding=encoding, errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for raw_row in reader:
            if any(str(cell).strip() for cell in raw_row):
                header_length = len(raw_row)
                if skip_header:
                    names = _dedupe_headers(
                        [_clean_header(cell, index) for index, cell in enumerate(raw_row)]
                    )
                else:
                    names = _dedupe_headers(
                        [f"column_{index + 1}" for index in range(header_length)]
                    )
                break
        else:
            names = []  # empty file

    if usecols:
        usecols = [column for column in usecols if column in set(names)]
        if not usecols:
            usecols = None

    reader = pd.read_csv(
        path,
        chunksize=chunk_size,
        dtype=str,
        keep_default_na=False,
        na_values=[],
        sep=delimiter,
        encoding=encoding,
        encoding_errors="replace",
        on_bad_lines="skip",
        skip_blank_lines=True,
        low_memory=True,
        header=None,
        names=names or None,
        skiprows=1 if (skip_header and names) else 0,
        usecols=usecols,
    )
    for chunk in reader:
        chunk.columns = _dedupe_headers([str(column).strip() for column in chunk.columns])
        records = chunk.to_dict(orient="records")
        yield [
            {key: (_as_text(value)) for key, value in record.items()}
            for record in records
        ]


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:  # NaN
        return ""
    return str(value).strip()


def iter_xlsx_chunks(path: str, *, chunk_size: int, sheet_name: str = "",
                     skip_header: bool = True,
                     usecols: list[str] | None = None) -> Iterator[list[dict]]:
    """Yield batches from a worksheet using openpyxl's streaming reader."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[sheet_name] if sheet_name and sheet_name in workbook.sheetnames \
            else workbook[workbook.sheetnames[0]]
        headers: list[str] = []
        batch: list[dict] = []
        for row_index, raw_row in enumerate(sheet.iter_rows(values_only=True)):
            values = ["" if v is None else v for v in raw_row]
            if all(str(v).strip() == "" for v in values):
                continue
            if row_index == 0 and skip_header:
                headers = _dedupe_headers([_clean_header(v, i) for i, v in enumerate(values)])
                continue
            if not headers:  # pragma: no cover - defensive
                headers = _dedupe_headers([f"column_{i + 1}" for i in range(len(values))])
            row = _row_to_dict(headers, values)
            if usecols:
                row = {k: v for k, v in row.items() if k in usecols}
            batch.append(row)
            if len(batch) >= chunk_size:
                yield batch
                batch = []
        if batch:
            yield batch
    finally:
        workbook.close()


def iter_rows(import_file: ImportFile, *, chunk_size: int):
    """Dispatch to the right streaming reader for a saved ImportFile."""
    path = import_file.path
    mapping = import_file.effective_mapping
    usecols = [c for c in mapping.keys()] or None
    if import_file.file_type == ImportFile.FileType.XLSX:
        yield from iter_xlsx_chunks(
            path, chunk_size=chunk_size, sheet_name=import_file.sheet_name,
            skip_header=import_file.has_header_row, usecols=usecols,
        )
    else:
        yield from iter_csv_chunks(
            path, chunk_size=chunk_size, delimiter=import_file.detected_delimiter or ",",
            encoding=import_file.detected_encoding or "utf-8",
            skip_header=import_file.has_header_row, usecols=usecols,
        )


# ---------------------------------------------------------------------------
# Row counting (streaming estimate for progress bars)
# ---------------------------------------------------------------------------
def estimate_row_count(path: str, file_type: str, *, sheet_name: str = "") -> int:
    """Cheap, streaming row estimate (never loads the file)."""
    if file_type == ImportFile.FileType.XLSX:
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
            sheet = workbook[sheet_name] if sheet_name and sheet_name in workbook.sheetnames \
                else workbook[workbook.sheetnames[0]]
            total = int(sheet.max_row or 0)
            workbook.close()
            return max(total - 1, 0)
        except Exception:  # pragma: no cover
            return 0

    total = 0
    with open(path, "rb") as handle:
        while True:
            block = handle.read(8 * 1024 * 1024)
            if not block:
                break
            total += block.count(b"\n")
    return max(total - 1, 0)
