"""
CSV Engine for Paradox2Firebird Studio
Handles high-fidelity CSV Export and Smart CSV Import with automatic type inference.
"""

import os
import csv
import io
import re
import datetime
from typing import List, Dict, Any, Tuple, Optional
from .paradox_engine import ParadoxReader, ParadoxWriter

class CSVEngine:

    @staticmethod
    def export_table_to_csv(
        filepath: str,
        delimiter: str = ';',
        encoding: str = 'utf-8-sig'
    ) -> bytes:
        """
        Exports a Paradox table to CSV format.
        Uses utf-8-sig by default for immediate Excel compatibility without encoding corruption.
        """
        reader = ParadoxReader(filepath)
        records = reader.read_all_records()
        field_names = [f.name for f in reader.fields]

        output = io.StringIO()
        writer = csv.writer(output, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)

        # Header row
        writer.writerow(field_names)

        # Data rows
        for row in records:
            row_vals = []
            for f in reader.fields:
                val = row.get(f.name)
                if val is None:
                    row_vals.append("")
                elif isinstance(val, bool):
                    row_vals.append("SIM" if val else "NAO")
                elif isinstance(val, datetime.date):
                    row_vals.append(val.strftime('%Y-%m-%d'))
                elif isinstance(val, datetime.time):
                    row_vals.append(val.strftime('%H:%M:%S'))
                elif isinstance(val, datetime.datetime):
                    row_vals.append(val.strftime('%Y-%m-%d %H:%M:%S'))
                elif isinstance(val, float):
                    row_vals.append(f"{val:.2f}" if f.ftype == 5 else str(val))
                else:
                    row_vals.append(str(val))
            writer.writerow(row_vals)

        return output.getvalue().encode(encoding)

    @classmethod
    def detect_delimiter(cls, sample_text: str) -> str:
        """Detects CSV delimiter (, ; \t |)."""
        lines = [line for line in sample_text.splitlines() if line.strip()][:5]
        if not lines:
            return ';'

        candidates = [';', ',', '\t', '|']
        best_delim = ';'
        max_score = -1

        for d in candidates:
            counts = [line.count(d) for line in lines]
            if len(counts) > 0 and counts[0] > 0 and all(c == counts[0] for c in counts):
                # Perfectly uniform count across lines
                score = counts[0] * 10
                if score > max_score:
                    max_score = score
                    best_delim = d
            elif sum(counts) > max_score:
                max_score = sum(counts)
                best_delim = d

        return best_delim

    @classmethod
    def infer_type_and_convert(cls, values: List[str]) -> Tuple[int, int, List[Any]]:
        """
        Infers Paradox type and returns (type_id, length, converted_values).
        """
        non_empty = [v.strip() for v in values if v is not None and v.strip() != ""]
        if not non_empty:
            return (1, 50, ["" for _ in values])

        # 1. Test Boolean
        bool_map = {
            'sim': True, 'nao': False, 'não': False, 'true': True, 'false': False,
            '1': True, '0': False, 's': True, 'n': False, 't': True, 'f': False
        }
        if all(v.lower() in bool_map for v in non_empty):
            converted = [bool_map.get(v.strip().lower(), False) if v and v.strip() else None for v in values]
            return (9, 1, converted)

        # 2. Test Integer (Long)
        is_int = True
        int_converted = []
        for v in values:
            v_str = v.strip() if v else ""
            if not v_str:
                int_converted.append(None)
                continue
            try:
                int_val = int(v_str)
                int_converted.append(int_val)
            except ValueError:
                is_int = False
                break
        if is_int:
            return (4, 4, int_converted)

        # 3. Test Float / Currency (e.g. 1234.56 or 1.234,56 or R$ 150,00)
        is_float = True
        float_converted = []
        for v in values:
            v_str = v.strip() if v else ""
            if not v_str:
                float_converted.append(None)
                continue
            # Remove currency symbols and clean brazilian number format
            clean_v = v_str.replace('R$', '').replace('$', '').strip()
            if ',' in clean_v and '.' in clean_v:
                clean_v = clean_v.replace('.', '').replace(',', '.')
            elif ',' in clean_v:
                clean_v = clean_v.replace(',', '.')
            try:
                flt_val = float(clean_v)
                float_converted.append(flt_val)
            except ValueError:
                is_float = False
                break
        if is_float:
            return (5, 8, float_converted)

        # 4. Test Date (YYYY-MM-DD or DD/MM/YYYY)
        is_date = True
        date_converted = []
        for v in values:
            v_str = v.strip() if v else ""
            if not v_str:
                date_converted.append(None)
                continue
            d_parsed = None
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
                try:
                    d_parsed = datetime.datetime.strptime(v_str, fmt).date()
                    break
                except ValueError:
                    pass
            if d_parsed:
                date_converted.append(d_parsed)
            else:
                is_date = False
                break
        if is_date:
            return (2, 4, date_converted)

        # 5. Fallback to Alpha / String
        max_len = max(len(v) for v in non_empty)
        allocated_len = max(50, ((max_len + 15) // 10) * 10)
        if allocated_len > 255:
            allocated_len = 255
        str_converted = [v.strip() if v is not None else "" for v in values]
        return (1, allocated_len, str_converted)

    @classmethod
    def import_csv_to_paradox(
        cls,
        csv_content: str,
        table_name: str,
        output_dir: str,
        delimiter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parses CSV text, infers column types, generates .DB + .PX Paradox table files,
        and saves them into output_dir.
        """
        if not delimiter:
            delimiter = cls.detect_delimiter(csv_content)

        reader = csv.reader(io.StringIO(csv_content), delimiter=delimiter)
        raw_rows = [row for row in reader if any(cell.strip() for cell in row)]

        if not raw_rows:
            raise ValueError("O arquivo CSV está vazio.")

        raw_headers = raw_rows[0]
        data_rows = raw_rows[1:]

        if not data_rows:
            raise ValueError("O arquivo CSV contém apenas o cabeçalho e nenhuma linha de dados.")

        # Clean headers
        headers = []
        for idx, h in enumerate(raw_headers):
            clean_h = re.sub(r'[^a-zA-Z0-9_]', '_', h.strip().upper())
            if not clean_h or clean_h[0].isdigit():
                clean_h = f"COL_{idx + 1}"
            headers.append(clean_h)

        num_cols = len(headers)
        columns_data: List[List[str]] = [[] for _ in range(num_cols)]

        for row in data_rows:
            for col_idx in range(num_cols):
                val = row[col_idx] if col_idx < len(row) else ""
                columns_data[col_idx].append(val)

        # Infer types for each column
        fields_def: List[Tuple[str, int, int]] = []
        converted_columns: List[List[Any]] = []

        for col_idx, h_name in enumerate(headers):
            ftype, flen, col_vals = cls.infer_type_and_convert(columns_data[col_idx])
            fields_def.append((h_name, ftype, flen))
            converted_columns.append(col_vals)

        # Transpose back into row tuples
        converted_rows: List[Tuple] = []
        num_records = len(data_rows)
        for r_idx in range(num_records):
            row_tuple = tuple(converted_columns[c_idx][r_idx] for c_idx in range(num_cols))
            converted_rows.append(row_tuple)

        # Check for Primary Key candidate (first column if ID/CODIGO or Long)
        pk_count = 1 if headers and ('ID' in headers[0] or 'COD' in headers[0] or fields_def[0][1] in (4, 22)) else 0

        clean_table_name = re.sub(r'[^a-zA-Z0-9_]', '_', table_name.upper()).replace('.CSV', '').replace('.DB', '')
        if not clean_table_name:
            clean_table_name = "TABELA_IMPORTADA"

        db_filename = f"{clean_table_name}.DB"
        db_path = os.path.join(output_dir, db_filename)

        ParadoxWriter.create_table(
            filepath=db_path,
            table_name=clean_table_name,
            fields=fields_def,
            rows=converted_rows,
            primary_key_count=pk_count,
            create_px_index=True
        )

        return {
            'filename': db_filename,
            'table_name': clean_table_name,
            'db_path': db_path,
            'records_count': num_records,
            'fields_count': len(fields_def),
            'has_px': pk_count > 0,
            'fields': [{'name': f[0], 'type_id': f[1], 'length': f[2]} for f in fields_def]
        }
