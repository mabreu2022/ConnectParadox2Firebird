"""
Paradox Database Engine (Pure Python Parser & Generator)
Supports Paradox 3.x, 4.x, 5.x, 7.x (.DB, .PX, .MB)
Handles full binary decoding, data block traversing, companion .PX primary index reading, and encoding conversions.
"""

import os
import struct
import datetime
from typing import List, Dict, Any, Tuple, Optional

# Paradox Field Types Definition
PARADOX_TYPES = {
    1: {'name': 'Alpha', 'firebird': 'VARCHAR', 'default_len': 50},
    2: {'name': 'Date', 'firebird': 'DATE', 'default_len': 4},
    3: {'name': 'Short', 'firebird': 'SMALLINT', 'default_len': 2},
    4: {'name': 'Long', 'firebird': 'INTEGER', 'default_len': 4},
    5: {'name': 'Currency', 'firebird': 'NUMERIC(15,2)', 'default_len': 8},
    6: {'name': 'Number', 'firebird': 'DOUBLE PRECISION', 'default_len': 8},
    9: {'name': 'Logical', 'firebird': 'BOOLEAN', 'default_len': 1},
    12: {'name': 'MemoBLOb', 'firebird': 'BLOB SUB_TYPE TEXT', 'default_len': 10},
    13: {'name': 'BLOb', 'firebird': 'BLOB SUB_TYPE BINARY', 'default_len': 10},
    14: {'name': 'FmtMemoBLOb', 'firebird': 'BLOB SUB_TYPE TEXT', 'default_len': 10},
    15: {'name': 'OLE', 'firebird': 'BLOB SUB_TYPE BINARY', 'default_len': 10},
    16: {'name': 'Graphic', 'firebird': 'BLOB SUB_TYPE BINARY', 'default_len': 10},
    20: {'name': 'Time', 'firebird': 'TIME', 'default_len': 4},
    21: {'name': 'Timestamp', 'firebird': 'TIMESTAMP', 'default_len': 8},
    22: {'name': 'AutoInc', 'firebird': 'BIGINT', 'default_len': 4},
    23: {'name': 'BCD', 'firebird': 'NUMERIC(18,4)', 'default_len': 17},
    24: {'name': 'Bytes', 'firebird': 'VARCHAR', 'default_len': 255},
}


def days_to_date(days: int) -> Optional[datetime.date]:
    """Convert Paradox date (days since 01/01/0001 Gregorian) to datetime.date."""
    if days is None or days <= 0:
        return None
    try:
        base = datetime.date(1, 1, 1)
        return base + datetime.timedelta(days=days - 1)
    except Exception:
        return None


def date_to_days(d: datetime.date) -> int:
    """Convert datetime.date to Paradox days count."""
    base = datetime.date(1, 1, 1)
    return (d - base).days + 1


def ms_to_time(ms: int) -> Optional[datetime.time]:
    """Convert Paradox time (milliseconds since midnight) to datetime.time."""
    if ms is None or ms < 0:
        return None
    try:
        seconds, milliseconds = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return datetime.time(hours % 24, minutes % 60, seconds % 60, milliseconds * 1000)
    except Exception:
        return None


class ParadoxField:
    def __init__(self, name: str, ftype: int, flen: int, fdc: int = 0, is_primary_key: bool = False):
        self.name = name
        self.ftype = ftype
        self.flen = flen
        self.fdc = fdc
        self.is_primary_key = is_primary_key
        type_info = PARADOX_TYPES.get(ftype, {'name': f'Unknown({ftype})', 'firebird': 'VARCHAR(255)'})
        self.type_name = type_info['name']
        self.default_firebird = type_info['firebird']

    def to_dict(self) -> Dict[str, Any]:
        fb_type = self.default_firebird
        if self.ftype == 1:  # Alpha
            fb_type = f"VARCHAR({self.flen})"
        elif self.ftype == 23:  # BCD
            fb_type = f"NUMERIC(18,{self.fdc})"
        return {
            'name': self.name,
            'type_id': self.ftype,
            'type_name': self.type_name,
            'length': self.flen,
            'decimal': self.fdc,
            'is_primary_key': self.is_primary_key,
            'firebird_type': fb_type
        }


class PXIndexReader:
    """Reads companion Paradox Primary Index (.PX) files."""

    @staticmethod
    def parse_px_file(px_filepath: str, encoding: str = 'latin1') -> Dict[str, Any]:
        if not os.path.exists(px_filepath):
            return {'exists': False}

        try:
            with open(px_filepath, 'rb') as f:
                data = f.read(2048)

            if len(data) < 128:
                return {'exists': True, 'valid': False, 'error': 'Tamanho de cabeçalho .PX inválido'}

            rec_size = struct.unpack_from('<H', data, 0x00)[0]
            header_size = struct.unpack_from('<H', data, 0x02)[0] or 2048
            file_type = data[0x04]  # 0x01 for primary index
            num_records = struct.unpack_from('<I', data, 0x06)[0]
            num_fields = struct.unpack_from('<H', data, 0x21)[0]
            pk_fields_count = struct.unpack_from('<H', data, 0x23)[0] or num_fields
            file_version = data[0x39]

            # Field descriptors start at 0x78
            offset = 0x78
            raw_fields = []
            for _ in range(num_fields):
                ftype = data[offset]
                flen = data[offset + 1]
                raw_fields.append((ftype, flen))
                offset += 2

            # Skip TableNamePtr (4 bytes)
            offset += 4

            # Table name length
            tname_len = 261 if file_version >= 12 else 79
            raw_tname = data[offset:offset + tname_len]
            table_name = raw_tname.split(b'\x00')[0].decode(encoding, errors='ignore')
            offset += tname_len

            # Field names
            field_names = []
            for idx in range(num_fields):
                end_idx = data.find(b'\x00', offset)
                if end_idx != -1 and end_idx < len(data):
                    fname = data[offset:end_idx].decode(encoding, errors='ignore').strip()
                    offset = end_idx + 1
                else:
                    fname = f"PK_COL_{idx + 1}"
                field_names.append(fname or f"PK_COL_{idx + 1}")

            return {
                'exists': True,
                'valid': True,
                'file_type': file_type,
                'table_name': table_name,
                'key_fields_count': num_fields,
                'key_field_names': field_names,
                'record_size': rec_size,
                'num_index_entries': num_records
            }
        except Exception as e:
            return {'exists': True, 'valid': False, 'error': str(e)}


class ParadoxReader:
    """Reads Paradox .DB tables directly and automatically detects companion .PX index files."""

    def __init__(self, filepath: str, encoding: str = 'latin1'):
        self.filepath = filepath
        self.encoding = encoding
        self.record_size = 0
        self.header_size = 0
        self.file_type = 0
        self.max_table_size = 0
        self.num_records = 0
        self.num_fields = 0
        self.file_blocks = 0
        self.first_block = 1
        self.last_block = 1
        self.file_version = 0
        self.primary_key_fields = 0
        self.table_name = ""
        self.fields: List[ParadoxField] = []
        self.px_info: Dict[str, Any] = {'exists': False}
        self.primary_keys: List[str] = []

        self._load_header()
        self._detect_and_load_px_index()

    def _load_header(self):
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"Arquivo Paradox não encontrado: {self.filepath}")

        with open(self.filepath, 'rb') as f:
            data = f.read(2048)

        if len(data) < 128:
            raise ValueError("Arquivo corrompido ou menor que o cabeçalho mínimo do Paradox.")

        self.record_size = struct.unpack_from('<H', data, 0x00)[0]
        self.header_size = struct.unpack_from('<H', data, 0x02)[0]
        if self.header_size == 0:
            self.header_size = 2048

        self.file_type = data[0x04]
        self.max_table_size = data[0x05] if data[0x05] > 0 else 2
        self.num_records = struct.unpack_from('<I', data, 0x06)[0]
        self.file_blocks = struct.unpack_from('<H', data, 0x0C)[0]
        self.first_block = struct.unpack_from('<H', data, 0x0E)[0]
        self.last_block = struct.unpack_from('<H', data, 0x10)[0]
        self.num_fields = struct.unpack_from('<H', data, 0x21)[0]
        self.primary_key_fields = struct.unpack_from('<H', data, 0x23)[0]
        self.file_version = data[0x39]

        # Field definitions start at offset 0x78 (120)
        offset = 0x78
        raw_fields = []
        for _ in range(self.num_fields):
            ftype = data[offset]
            flen = data[offset + 1]
            fdc = 0
            if ftype == 23:  # BCD
                flen = 17
                fdc = data[offset + 1]
            raw_fields.append((ftype, flen, fdc))
            offset += 2

        # Skip TableNamePtr (4 bytes)
        offset += 4

        # If non-indexed or indexed DB, skip field name pointers (4 bytes each)
        if self.file_type in (0, 2, 3, 5, 6, 8):
            offset += self.num_fields * 4

        # Table name length depends on version
        tname_len = 261 if self.file_version >= 12 else 79
        raw_tname = data[offset:offset + tname_len]
        header_tname = raw_tname.split(b'\x00')[0].decode(self.encoding, errors='ignore').strip()
        offset += tname_len

        # Base filename without extension
        file_basename = os.path.splitext(os.path.basename(self.filepath))[0]
        # Prefer actual file name if header name is empty, generic 'RESTTEMP', or contains .DB
        if not header_tname or header_tname.upper().startswith('RESTTEMP') or '.' in header_tname:
            self.table_name = file_basename
        else:
            self.table_name = header_tname

        # Read null-terminated field names
        self.fields = []
        for idx, (ftype, flen, fdc) in enumerate(raw_fields):
            end_idx = data.find(b'\x00', offset)
            if end_idx != -1 and end_idx < len(data):
                fname = data[offset:end_idx].decode(self.encoding, errors='ignore').strip()
                offset = end_idx + 1
            else:
                fname = f"CAMPO_{idx + 1}"
            if not fname:
                fname = f"CAMPO_{idx + 1}"
            
            # In Paradox, if primary_key_fields is N, the first N fields form the primary key
            is_pk = (idx < self.primary_key_fields)
            self.fields.append(ParadoxField(fname, ftype, flen, fdc, is_primary_key=is_pk))

    def _detect_and_load_px_index(self):
        """Checks for companion .PX file and extracts primary key columns."""
        base_no_ext = os.path.splitext(self.filepath)[0]
        possible_px = [
            base_no_ext + '.PX',
            base_no_ext + '.px',
            base_no_ext + '.Px',
            base_no_ext + '.pX',
        ]

        px_path = None
        for p in possible_px:
            if os.path.exists(p):
                px_path = p
                break

        if px_path:
            self.px_info = PXIndexReader.parse_px_file(px_path, self.encoding)
            self.px_info['filepath'] = px_path
            
            actual_field_names = [f.name for f in self.fields]
            extracted_keys = self.px_info.get('key_field_names', [])
            valid_keys = [k for k in extracted_keys if k in actual_field_names]
            
            if valid_keys:
                self.primary_keys = valid_keys
            else:
                # In Paradox primary index (.PX), key is always the first K fields of the table
                k_count = self.px_info.get('key_fields_count', 0)
                if k_count <= 0 and self.primary_key_fields > 0:
                    k_count = self.primary_key_fields
                elif k_count <= 0 and self.px_info.get('valid'):
                    k_count = 1
                
                if k_count > 0 and self.fields:
                    self.primary_keys = [self.fields[i].name for i in range(min(k_count, len(self.fields)))]
            
            # Mark corresponding fields as primary keys
            for f in self.fields:
                if f.name in self.primary_keys:
                    f.is_primary_key = True

        # Fallback if no .PX file exists on disk but primary_key_fields was declared in .DB header
        if not self.primary_keys and self.primary_key_fields > 0:
            k_count = min(self.primary_key_fields, len(self.fields))
            self.primary_keys = [self.fields[i].name for i in range(k_count)]
            for f in self.fields:
                if f.name in self.primary_keys:
                    f.is_primary_key = True

        # Secondary heuristic if neither was set
        if not self.primary_keys and self.fields:
            first_name = self.fields[0].name.upper()
            if first_name in ('ID', 'CODIGO', f'ID_{self.table_name.upper()}', f'COD_{self.table_name.upper()}'):
                self.primary_keys = [self.fields[0].name]
                self.fields[0].is_primary_key = True

    def get_block_size(self) -> int:
        return self.max_table_size * 1024

    def decode_field(self, raw_bytes: bytes, field: ParadoxField) -> Any:
        """Decode a single field from Paradox binary representation."""
        if not raw_bytes or len(raw_bytes) < field.flen:
            return None

        if field.ftype == 1:  # Alpha / String
            val = raw_bytes.split(b'\x00')[0].decode(self.encoding, errors='replace').rstrip()
            return val if val else ""

        elif field.ftype == 2:  # Date
            b0 = raw_bytes[0]
            if b0 == 0:
                return None
            val_int = struct.unpack('>I', raw_bytes)[0] ^ 0x80000000
            return days_to_date(val_int)

        elif field.ftype == 3:  # Short integer
            if raw_bytes == b'\x00\x00':
                return None
            val = struct.unpack('>H', raw_bytes)[0] ^ 0x8000
            if val >= 0x8000:
                val -= 0x10000
            return val

        elif field.ftype in (4, 22):  # Long integer or AutoInc
            if raw_bytes == b'\x00\x00\x00\x00':
                return None
            val = struct.unpack('>I', raw_bytes)[0] ^ 0x80000000
            if val >= 0x80000000:
                val -= 0x100000000
            return val

        elif field.ftype in (5, 6):  # Currency / Double
            if raw_bytes == b'\x00' * 8:
                return None
            mod_bytes = bytearray(raw_bytes)
            if mod_bytes[0] & 0x80:
                mod_bytes[0] ^= 0x80
            else:
                mod_bytes = bytearray([b ^ 0xFF for b in mod_bytes])
            try:
                val = struct.unpack('>d', bytes(mod_bytes))[0]
                return round(val, 4) if field.ftype == 5 else val
            except Exception:
                return None

        elif field.ftype == 9:  # Logical / Boolean
            b = raw_bytes[0]
            if b == 0x81 or b == 0x01:
                return True
            elif b == 0x80 or b == 0x00:
                return False
            return None

        elif field.ftype == 20:  # Time
            if raw_bytes == b'\x00\x00\x00\x00':
                return None
            ms = struct.unpack('>I', raw_bytes)[0] ^ 0x80000000
            return ms_to_time(ms)

        elif field.ftype == 21:  # Timestamp
            if raw_bytes == b'\x00' * 8:
                return None
            mod_bytes = bytearray(raw_bytes)
            if mod_bytes[0] & 0x80:
                mod_bytes[0] ^= 0x80
            else:
                mod_bytes = bytearray([b ^ 0xFF for b in mod_bytes])
            try:
                ms_val = struct.unpack('>d', bytes(mod_bytes))[0]
                days = int(ms_val // 86400000.0)
                rem_ms = int(ms_val % 86400000.0)
                d = days_to_date(days)
                t = ms_to_time(rem_ms)
                if d and t:
                    return datetime.datetime.combine(d, t)
                return None
            except Exception:
                return None

        else:
            return raw_bytes.hex()

    def read_all_records(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Reads all records across all data blocks in the Paradox table."""
        records: List[Dict[str, Any]] = []
        block_size = self.get_block_size()

        with open(self.filepath, 'rb') as f:
            f.seek(self.header_size)

            block_nr = self.first_block
            blocks_read = 0

            while block_nr > 0 and (self.file_blocks == 0 or blocks_read < self.file_blocks + 10):
                block_offset = self.header_size + (block_nr - 1) * block_size
                f.seek(block_offset)
                block_data = f.read(block_size)

                if len(block_data) < 6:
                    break

                next_block = struct.unpack_from('<H', block_data, 0x00)[0]
                cur_block = struct.unpack_from('<H', block_data, 0x02)[0]
                add_data_size = struct.unpack_from('<H', block_data, 0x04)[0]

                if self.record_size > 0:
                    num_recs_in_block = (add_data_size // self.record_size) + 1 if add_data_size > 0 else 0
                else:
                    num_recs_in_block = 0

                rec_offset = 0x06
                for _ in range(num_recs_in_block):
                    if rec_offset + self.record_size > len(block_data):
                        break

                    row_bytes = block_data[rec_offset:rec_offset + self.record_size]
                    row_dict: Dict[str, Any] = {}
                    field_pos = 0

                    for field in self.fields:
                        fld_raw = row_bytes[field_pos:field_pos + field.flen]
                        row_dict[field.name] = self.decode_field(fld_raw, field)
                        field_pos += field.flen

                    records.append(row_dict)
                    rec_offset += self.record_size

                    if limit and len(records) >= limit:
                        return records

                blocks_read += 1
                if next_block == 0 or next_block == block_nr:
                    break
                block_nr = next_block

        return records


class ParadoxWriter:
    """Generates standard Paradox 5.0/7.0 .DB files and companion .PX primary index files."""

    @staticmethod
    def create_table(
        filepath: str,
        table_name: str,
        fields: List[Tuple[str, int, int]],
        rows: List[Tuple],
        primary_key_count: int = 1,
        encoding: str = 'latin1',
        create_px_index: bool = True
    ):
        """
        Creates a valid Paradox binary table file (.DB) and companion (.PX) primary index file.
        """
        rec_size = sum(f[2] for f in fields)
        num_fields = len(fields)
        header_size = 2048
        block_size = 2048
        max_table_size = 2

        header = bytearray(header_size)

        # 0x00: Record Size (uint16)
        struct.pack_into('<H', header, 0x00, rec_size)
        # 0x02: Header Size (uint16)
        struct.pack_into('<H', header, 0x02, header_size)
        # 0x04: File Type (0 = Indexed DB if primary key exists, 2 = Non-indexed DB)
        header[0x04] = 0x00 if primary_key_count > 0 else 0x02
        # 0x05: Max Table Size
        header[0x05] = max_table_size
        # 0x0A: Next Block
        struct.pack_into('<H', header, 0x0A, 2)
        # 0x0C: File Blocks
        struct.pack_into('<H', header, 0x0C, 1)
        # 0x0E: First Block
        struct.pack_into('<H', header, 0x0E, 1)
        # 0x10: Last Block
        struct.pack_into('<H', header, 0x10, 1)
        # 0x21: Num Fields
        struct.pack_into('<H', header, 0x21, num_fields)
        # 0x23: Num Key Fields
        struct.pack_into('<H', header, 0x23, primary_key_count)
        # 0x39: File Version (0x0A = Paradox 5.0)
        header[0x39] = 0x0A

        # Field definitions at 0x78
        offset = 0x78
        for fname, ftype, flen in fields:
            header[offset] = ftype
            header[offset + 1] = flen
            offset += 2

        # TableNamePtr (4 bytes)
        offset += 4
        # Field pointers (4 bytes each)
        offset += num_fields * 4

        # Table Name (79 bytes)
        t_name_enc = table_name.upper().encode(encoding) + b'\x00'
        header[offset:offset + min(len(t_name_enc), 79)] = t_name_enc[:79]
        offset += 79

        # Field Names (null-terminated)
        for fname, ftype, flen in fields:
            enc = fname.encode(encoding) + b'\x00'
            header[offset:offset + len(enc)] = enc
            offset += len(enc)

        # 0x06: Num Records
        struct.pack_into('<I', header, 0x06, len(rows))

        # Build data blocks
        blocks = []
        max_recs_per_block = (block_size - 6) // rec_size
        if max_recs_per_block < 1:
            max_recs_per_block = 1

        row_chunks = [rows[i:i + max_recs_per_block] for i in range(0, len(rows), max_recs_per_block)]
        if not row_chunks:
            row_chunks = [[]]

        struct.pack_into('<H', header, 0x0C, len(row_chunks))
        struct.pack_into('<H', header, 0x10, len(row_chunks))

        for b_idx, chunk in enumerate(row_chunks):
            block = bytearray(block_size)
            next_b = b_idx + 2 if b_idx + 1 < len(row_chunks) else 0
            cur_b = b_idx + 1

            struct.pack_into('<H', block, 0x00, next_b)
            struct.pack_into('<H', block, 0x02, cur_b)

            add_data_size = (len(chunk) - 1) * rec_size if len(chunk) > 0 else 0
            struct.pack_into('<H', block, 0x04, add_data_size)

            d_pos = 0x06
            for row in chunk:
                rec_buf = bytearray(rec_size)
                p = 0
                for col_idx, (fname, ftype, flen) in enumerate(fields):
                    val = row[col_idx] if col_idx < len(row) else None
                    if val is None:
                        p += flen
                        continue

                    if ftype == 1:  # Alpha
                        s_bytes = str(val).encode(encoding, errors='replace')[:flen]
                        rec_buf[p:p + len(s_bytes)] = s_bytes
                    elif ftype in (4, 22):  # Long / AutoInc
                        v_int = int(val)
                        encoded = (v_int ^ 0x80000000) & 0xFFFFFFFF
                        struct.pack_into('>I', rec_buf, p, encoded)
                    elif ftype == 3:  # Short
                        v_int = int(val)
                        encoded = (v_int ^ 0x8000) & 0xFFFF
                        struct.pack_into('>H', rec_buf, p, encoded)
                    elif ftype in (5, 6):  # Currency / Double
                        v_float = float(val)
                        dbl_bytes = bytearray(struct.pack('>d', v_float))
                        if v_float >= 0:
                            dbl_bytes[0] ^= 0x80
                        else:
                            dbl_bytes = bytearray([b ^ 0xFF for b in dbl_bytes])
                        rec_buf[p:p + 8] = dbl_bytes
                    elif ftype == 9:  # Logical
                        rec_buf[p] = 0x81 if bool(val) else 0x80
                    elif ftype == 2:  # Date
                        if isinstance(val, str):
                            try:
                                val = datetime.datetime.strptime(val, '%Y-%m-%d').date()
                            except Exception:
                                val = datetime.date(2024, 1, 1)
                        if isinstance(val, (datetime.date, datetime.datetime)):
                            days = date_to_days(val)
                        else:
                            days = int(val)
                        encoded = (days ^ 0x80000000) & 0xFFFFFFFF
                        struct.pack_into('>I', rec_buf, p, encoded)
                    elif ftype == 20:  # Time
                        if isinstance(val, str):
                            try:
                                parts = [int(x) for x in val.split(':')]
                                ms = (parts[0] * 3600 + parts[1] * 60 + (parts[2] if len(parts) > 2 else 0)) * 1000
                            except Exception:
                                ms = 0
                        elif isinstance(val, datetime.time):
                            ms = (val.hour * 3600 + val.minute * 60 + val.second) * 1000 + val.microsecond // 1000
                        else:
                            ms = int(val)
                        encoded = (ms ^ 0x80000000) & 0xFFFFFFFF
                        struct.pack_into('>I', rec_buf, p, encoded)

                    p += flen

                block[d_pos:d_pos + rec_size] = rec_buf
                d_pos += rec_size

            blocks.append(block)

        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(header)
            for b in blocks:
                f.write(b)

        # Create companion .PX primary index file if requested
        if create_px_index and primary_key_count > 0:
            px_path = os.path.splitext(filepath)[0] + '.PX'
            pk_fields = fields[:primary_key_count]
            px_rec_size = sum(f[2] for f in pk_fields) + 4
            px_header = bytearray(header_size)

            struct.pack_into('<H', px_header, 0x00, px_rec_size)
            struct.pack_into('<H', px_header, 0x02, header_size)
            px_header[0x04] = 0x01  # 0x01 = Primary Index (.PX)
            px_header[0x05] = max_table_size
            struct.pack_into('<I', px_header, 0x06, len(rows))
            struct.pack_into('<H', px_header, 0x21, len(pk_fields))
            struct.pack_into('<H', px_header, 0x23, len(pk_fields))
            px_header[0x39] = 0x0A

            px_off = 0x78
            for fname, ftype, flen in pk_fields:
                px_header[px_off] = ftype
                px_header[px_off + 1] = flen
                px_off += 2

            px_off += 4  # TableNamePtr
            px_header[px_off:px_off + min(len(t_name_enc), 79)] = t_name_enc[:79]
            px_off += 79

            for fname, ftype, flen in pk_fields:
                enc = fname.encode(encoding) + b'\x00'
                px_header[px_off:px_off + len(enc)] = enc
                px_off += len(enc)

            with open(px_path, 'wb') as f_px:
                f_px.write(px_header)
