"""
Diagnostics and Data Cleansing Engine for Paradox Tables.
Detects data corruption, header-block inconsistencies, memo file (.MB) issues,
null or duplicate primary keys, invalid dates, and encoding/charset anomalies.
Provides automated sanitization and health scoring.
"""

import os
import datetime
from typing import List, Dict, Any, Optional, Tuple
from .paradox_engine import ParadoxReader, ParadoxField

class DataDiagnosticsEngine:

    @staticmethod
    def inspect_table(filepath: str) -> Dict[str, Any]:
        """
        Performs a full deep inspection of a single Paradox (.DB) file.
        Returns health score (0-100), issue counts, anomalies, and statistics.
        """
        if not os.path.exists(filepath):
            return {
                'success': False,
                'filename': os.path.basename(filepath),
                'error': 'Arquivo não encontrado.'
            }

        filename = os.path.basename(filepath)
        table_name = os.path.splitext(filename)[0]
        file_size = os.path.getsize(filepath)

        issues: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        recommendations: List[str] = []

        try:
            reader = ParadoxReader(filepath)
        except Exception as e:
            return {
                'success': True,
                'filename': filename,
                'table_name': table_name,
                'file_size': file_size,
                'health_score': 10,
                'status': 'CORROMPIDO',
                'issues': [{
                    'severity': 'CRITICAL',
                    'type': 'HEADER_CORRUPTION',
                    'message': f'Falha ao ler cabeçalho Paradox: {str(e)}'
                }],
                'warnings': [],
                'recommendations': ['Tentar reconstruir cabeçalho ou restaurar backup.']
            }

        # 1. Header vs Structure checks
        expected_records = reader.num_records
        num_fields = reader.num_fields
        rec_size = reader.record_size
        block_size = reader.max_table_size * 1024 if hasattr(reader, 'max_table_size') else 2048

        if num_fields == 0:
            issues.append({
                'severity': 'CRITICAL',
                'type': 'NO_FIELDS',
                'message': 'A tabela não possui campos declarados na estrutura.'
            })

        # 2. Check Memo (.MB) files
        has_memo_fields = any(f.ftype in (0x0C, 0x0D, 0x19) for f in reader.fields)
        base_no_ext = os.path.splitext(filepath)[0]
        mb_path = None
        for ext in ('.MB', '.mb', '.Mb'):
            if os.path.exists(base_no_ext + ext):
                mb_path = base_no_ext + ext
                break

        if has_memo_fields and not mb_path:
            issues.append({
                'severity': 'HIGH',
                'type': 'MISSING_MB_FILE',
                'message': f'A tabela contém campos BLOB/Memo (tipo Paradox), mas o arquivo {filename[:-3]}.MB não foi encontrado na pasta.'
            })
            recommendations.append('Copie o arquivo .MB correspondente para evitar campos de texto truncados ou nulos.')

        # 3. Check Primary Key Index (.PX)
        px_info = reader.px_info
        if not px_info.get('exists', False):
            warnings.append({
                'severity': 'LOW',
                'type': 'NO_PX_INDEX',
                'message': f'Nenhum índice primário ({filename[:-3]}.PX) encontrado. A chave primária será inferida a partir de colunas como ID/CODIGO.'
            })
        elif px_info.get('error'):
            warnings.append({
                'severity': 'MEDIUM',
                'type': 'PX_READ_ERROR',
                'message': f'Aviso ao ler índice .PX: {px_info["error"]}'
            })

        # 4. Deep row inspection
        try:
            records = reader.read_all_records()
            actual_read_count = len(records)
        except Exception as e:
            records = []
            actual_read_count = 0
            issues.append({
                'severity': 'CRITICAL',
                'type': 'DATA_BLOCK_READ_ERROR',
                'message': f'Erro ao ler blocos de dados de registro: {str(e)}'
            })

        if expected_records > 0 and actual_read_count != expected_records:
            issues.append({
                'severity': 'MEDIUM',
                'type': 'RECORD_COUNT_MISMATCH',
                'message': f'Contagem do cabeçalho ({expected_records} reg) difere dos registros lidos ({actual_read_count} reg).'
            })

        # 5. Check row-level data issues (invalid dates, duplicate PKs, null PKs, encoding anomalies)
        pk_cols = reader.primary_keys
        pk_seen = set()
        duplicate_pks = 0
        null_pks = 0
        invalid_dates_count = 0
        mojibake_count = 0

        date_fields = [f.name for f in reader.fields if f.ftype in (0x02, 0x03, 0x09, 0x14, 0x15, 0x16)]
        text_fields = [f.name for f in reader.fields if f.ftype in (0x01, 0x0C, 0x0D)]

        for r_idx, row in enumerate(records):
            # PK check
            if pk_cols:
                pk_vals = tuple(row.get(col) for col in pk_cols)
                if any(v is None or v == '' for v in pk_vals):
                    null_pks += 1
                elif pk_vals in pk_seen:
                    duplicate_pks += 1
                else:
                    pk_seen.add(pk_vals)

            # Date checks
            for df in date_fields:
                val = row.get(df)
                if val is not None:
                    if isinstance(val, (datetime.date, datetime.datetime)):
                        if val.year < 1900 or val.year > 2100:
                            invalid_dates_count += 1
                    elif isinstance(val, str) and ('0000' in val or '00/00' in val):
                        invalid_dates_count += 1

            # Text / Charset check (detect common mojibake characters like Ã, , â)
            for tf in text_fields:
                val = row.get(tf)
                if isinstance(val, str):
                    if '\ufffd' in val or 'Ã£' in val or 'Ã©' in val or 'Ã³' in val:
                        mojibake_count += 1

        if null_pks > 0:
            issues.append({
                'severity': 'HIGH',
                'type': 'NULL_PRIMARY_KEY',
                'count': null_pks,
                'message': f'{null_pks} registro(s) contêm valor NULO na(s) chave(s) primária(s) ({", ".join(pk_cols)}).'
            })
            recommendations.append('Executar higienização para preencher PKs nulas com auto-incremento.')

        if duplicate_pks > 0:
            issues.append({
                'severity': 'HIGH',
                'type': 'DUPLICATE_PRIMARY_KEY',
                'count': duplicate_pks,
                'message': f'{duplicate_pks} registro(s) contêm chaves primárias duplicadas nos dados Paradox.'
            })
            recommendations.append('Revisar duplicatas ou aplicar higienização de chaves sequenciais.')

        if invalid_dates_count > 0:
            warnings.append({
                'severity': 'MEDIUM',
                'type': 'INVALID_DATE_VALUES',
                'count': invalid_dates_count,
                'message': f'{invalid_dates_count} data(s) fora da faixa padrão ou com formato nulo (ex: 00/00/0000).'
            })
            recommendations.append('Ativar a opção de converter datas inválidas para NULL ou data padrão durante a migração.')

        if mojibake_count > 0:
            warnings.append({
                'severity': 'LOW',
                'type': 'CHARSET_ANOMALY',
                'count': mojibake_count,
                'message': f'Detectados possíveis caracteres com encoding duplo ou corrompido em {mojibake_count} campo(s) de texto.'
            })
            recommendations.append('Selecione CP850 (DOS) ou WIN1252 na configuração de charset para conversão limpa para UTF8.')

        # 6. Calculate Health Score
        health = 100
        for iss in issues:
            sev = iss.get('severity', 'LOW')
            if sev == 'CRITICAL': health -= 40
            elif sev == 'HIGH': health -= 20
            elif sev == 'MEDIUM': health -= 10
            else: health -= 5

        for w in warnings:
            sev = w.get('severity', 'LOW')
            if sev == 'HIGH': health -= 10
            elif sev == 'MEDIUM': health -= 5
            else: health -= 2

        health = max(0, min(100, health))

        if health >= 85:
            status = 'EXCELENTE'
            status_color = 'success'
        elif health >= 65:
            status = 'BOM'
            status_color = 'info'
        elif health >= 40:
            status = 'ATENCAO'
            status_color = 'warning'
        else:
            status = 'CRITICO'
            status_color = 'danger'

        return {
            'success': True,
            'filename': filename,
            'table_name': table_name,
            'file_size': file_size,
            'health_score': health,
            'status': status,
            'status_color': status_color,
            'record_count': actual_read_count,
            'expected_record_count': expected_records,
            'field_count': num_fields,
            'has_px': px_info.get('exists', False),
            'has_mb': mb_path is not None,
            'primary_keys': pk_cols,
            'issues_count': len(issues),
            'warnings_count': len(warnings),
            'issues': issues,
            'warnings': warnings,
            'recommendations': recommendations
        }

    @classmethod
    def inspect_directory(cls, dir_path: str) -> Dict[str, Any]:
        """
        Inspects all Paradox .DB files in a directory and generates a consolidated diagnostics report.
        """
        if not os.path.isdir(dir_path):
            return {'success': False, 'error': 'Diretório não encontrado.'}

        results = []
        overall_health = 0
        total_records = 0
        total_issues = 0
        total_warnings = 0

        files = [f for f in os.listdir(dir_path) if f.upper().endswith('.DB')]
        if not files:
            return {
                'success': True,
                'total_tables': 0,
                'overall_health': 100,
                'tables': []
            }

        for f in files:
            fpath = os.path.join(dir_path, f)
            res = cls.inspect_table(fpath)
            results.append(res)
            overall_health += res.get('health_score', 0)
            total_records += res.get('record_count', 0)
            total_issues += res.get('issues_count', 0)
            total_warnings += res.get('warnings_count', 0)

        avg_health = int(overall_health / len(files)) if files else 100

        return {
            'success': True,
            'total_tables': len(files),
            'overall_health': avg_health,
            'total_records': total_records,
            'total_issues': total_issues,
            'total_warnings': total_warnings,
            'tables': results
        }

    @staticmethod
    def cleanse_records(
        records: List[Dict[str, Any]],
        fields: List[ParadoxField],
        primary_keys: List[str],
        options: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Sanitizes records based on provided options:
        - fix_null_pks: replaces null/empty PKs with generated sequential integers
        - fix_duplicate_pks: increments duplicated PKs
        - fix_invalid_dates: replaces year < 1900 or > 2100 with None or default date
        - trim_strings: trims leading/trailing whitespace
        - fix_charset: re-encodes text if mojibake is detected
        """
        if not options:
            options = {
                'fix_null_pks': True,
                'fix_duplicate_pks': True,
                'fix_invalid_dates': True,
                'trim_strings': True
            }

        clean_records = []
        stats = {
            'null_pks_fixed': 0,
            'duplicate_pks_fixed': 0,
            'invalid_dates_fixed': 0,
            'strings_trimmed': 0
        }

        pk_col = primary_keys[0] if primary_keys else None
        seen_pks = set()
        next_pk_id = 1000

        date_field_names = {f.name for f in fields if f.ftype in (0x02, 0x03, 0x09, 0x14, 0x15, 0x16)}
        string_field_names = {f.name for f in fields if f.ftype in (0x01, 0x0C, 0x0D)}

        # Determine highest existing PK if numeric
        for r in records:
            if pk_col and r.get(pk_col) is not None:
                try:
                    val_int = int(r[pk_col])
                    if val_int > next_pk_id:
                        next_pk_id = val_int + 1
                except (ValueError, TypeError):
                    pass

        for row in records:
            new_row = dict(row)

            # 1. Trim strings
            if options.get('trim_strings'):
                for sf in string_field_names:
                    val = new_row.get(sf)
                    if isinstance(val, str):
                        trimmed = val.strip()
                        if trimmed != val:
                            new_row[sf] = trimmed
                            stats['strings_trimmed'] += 1

            # 2. Fix dates
            if options.get('fix_invalid_dates'):
                for df in date_field_names:
                    dval = new_row.get(df)
                    if dval is not None:
                        if isinstance(dval, (datetime.date, datetime.datetime)):
                            if dval.year < 1900 or dval.year > 2100:
                                new_row[df] = None
                                stats['invalid_dates_fixed'] += 1
                        elif isinstance(dval, str) and ('0000' in dval or '00/00' in dval or dval.strip() == ''):
                            new_row[df] = None
                            stats['invalid_dates_fixed'] += 1

            # 3. Fix PKs
            if pk_col:
                pk_val = new_row.get(pk_col)
                if pk_val is None or pk_val == '' or str(pk_val).strip() == '':
                    if options.get('fix_null_pks'):
                        new_row[pk_col] = next_pk_id
                        next_pk_id += 1
                        stats['null_pks_fixed'] += 1
                elif pk_val in seen_pks:
                    if options.get('fix_duplicate_pks'):
                        new_row[pk_col] = next_pk_id
                        next_pk_id += 1
                        stats['duplicate_pks_fixed'] += 1

                if new_row.get(pk_col) is not None:
                    seen_pks.add(new_row.get(pk_col))

            clean_records.append(new_row)

        return clean_records, stats
