"""
Firebird Engine (DDL / DML Generator, FDB Binary Database Creator, and Connection Manager)
Converts Paradox schema & records to optimized Firebird SQL scripts or generates direct .FDB databases.
Supports Firebird 2.5, 3.0, 4.0 and 5.0.
Includes Reserved Words validator, TCP/IP live migration, and SQL Query Execution.
"""

import os
import subprocess
import tempfile
import datetime
from typing import List, Dict, Any, Optional, Set
from .paradox_engine import ParadoxReader, ParadoxField

FIREBIRD_RESERVED_WORDS = {
    'ADD', 'ADMIN', 'ALL', 'ALTER', 'AND', 'ANY', 'AS', 'AT', 'AVG', 'BEGIN', 'BETWEEN',
    'BIGINT', 'BIT_LENGTH', 'BLOB', 'BOOLEAN', 'BOTH', 'BY', 'CASE', 'CAST', 'CHAR',
    'CHAR_LENGTH', 'CHARACTER', 'CHARACTER_LENGTH', 'CHECK', 'CLOSE', 'COLLATE', 'COLUMN',
    'COMMENT', 'COMMIT', 'CONNECT', 'CONSTRAINT', 'COUNT', 'CREATE', 'CROSS', 'CURRENT',
    'CURRENT_CONNECTION', 'CURRENT_DATE', 'CURRENT_ROLE', 'CURRENT_TIME', 'CURRENT_TIMESTAMP',
    'CURRENT_TRANSACTION', 'CURRENT_USER', 'CURSOR', 'DATE', 'DAY', 'DEC', 'DECIMAL', 'DECLARE',
    'DEFAULT', 'DELETE', 'DELETING', 'DETERMINISTIC', 'DISCONNECT', 'DISTINCT', 'DOUBLE', 'DROP',
    'ELSE', 'END', 'ESCAPE', 'EXECUTE', 'EXISTS', 'EXTERNAL', 'EXTRACT', 'FALSE', 'FETCH',
    'FILE', 'FILTER', 'FIRST', 'FLOAT', 'FOR', 'FOREIGN', 'FROM', 'FULL', 'FUNCTION', 'GDSCODE',
    'GLOBAL', 'GRANT', 'GROUP', 'HAVING', 'HOUR', 'IN', 'INDEX', 'INNER', 'INSENSITIVE', 'INSERT',
    'INSERTING', 'INT', 'INT128', 'INTEGER', 'INTO', 'IS', 'ISOLATION', 'JOIN', 'KEY', 'LEADING',
    'LEAVE', 'LEFT', 'LENGTH', 'LEVEL', 'LIKE', 'LIMIT', 'LOCAL', 'LOCK', 'LOWER', 'MATCH', 'MAX',
    'MAXVALUE', 'MERGE', 'MIN', 'MINUTE', 'MINVALUE', 'MONTH', 'NAMES', 'NATIONAL', 'NATURAL',
    'NCHAR', 'NO', 'NOT', 'NULL', 'NULLS', 'NUMERIC', 'OCTET_LENGTH', 'OF', 'OFFSET', 'ON', 'ONLY',
    'OPEN', 'OPTION', 'OR', 'ORDER', 'OUTER', 'OVER', 'OVERFLOW', 'PACKAGE', 'PAD', 'PAGE', 'PAGES',
    'PARAMETER', 'PASSWORD', 'PLAN', 'POSITION', 'POST_EVENT', 'PRECISION', 'PRIMARY', 'PROCEDURE',
    'PROTECTED', 'RDB$DB_KEY', 'RDB$RECORD_VERSION', 'READ', 'REAL', 'RECORD_VERSION', 'RECREATE',
    'RECURSIVE', 'REFERENCES', 'RELEASE', 'RESET', 'RESTART', 'RESTRICT', 'RETAIN', 'RETURN',
    'RETURNING', 'RETURNS', 'REVOKE', 'RIGHT', 'ROLE', 'ROLLBACK', 'ROW', 'ROW_COUNT', 'ROWS',
    'SAVEPOINT', 'SCALAR_ARRAY', 'SCHEMA', 'SCROLL', 'SECOND', 'SECTION', 'SEGMENT', 'SELECT',
    'SEQUENCE', 'SESSION_USER', 'SET', 'SIMILAR', 'SIZE', 'SKIP', 'SMALLINT', 'SOME', 'SQLCODE',
    'SQLSTATE', 'START', 'STATEMENT', 'SUBSTRING', 'SUM', 'SYSTEM_USER', 'TABLE', 'TEMPORARY',
    'THEN', 'TIME', 'TIMEZONE_HOUR', 'TIMEZONE_MINUTE', 'TO', 'TRAILING', 'TRANSACTION', 'TRIGGER',
    'TRIM', 'TRUE', 'TYPE', 'UNCOMMITTED', 'UNION', 'UNIQUE', 'UNKNOWN', 'UPDATE', 'UPDATING',
    'UPPER', 'USER', 'USING', 'VALUE', 'VALUES', 'VARBINARY', 'VARCHAR', 'VARIABLE', 'VARYING',
    'VIEW', 'WAIT', 'WHEN', 'WHERE', 'WHILE', 'WINDOW', 'WITH', 'WORK', 'WRITE', 'YEAR'
}

class FirebirdEngine:

    @staticmethod
    def is_reserved_word(identifier: str) -> bool:
        """Returns True if the identifier is a reserved word in Firebird."""
        return identifier.strip().upper() in FIREBIRD_RESERVED_WORDS

    @staticmethod
    def find_isql_executable() -> Optional[str]:
        """Auto-detects the Firebird isql.exe command line tool."""
        search_paths = [
            r'C:\Program Files (x86)\Firebird\Firebird_5_0\isql.exe',
            r'C:\Program Files\Firebird\Firebird_5_0\isql.exe',
            r'C:\Program Files (x86)\Firebird\Firebird_4_0\isql.exe',
            r'C:\Program Files\Firebird\Firebird_4_0\isql.exe',
            r'C:\Program Files (x86)\Firebird\Firebird_3_0\isql.exe',
            r'C:\Program Files\Firebird\Firebird_3_0\isql.exe',
            r'C:\Program Files (x86)\Firebird\Firebird_2_5\bin\isql.exe',
            r'C:\Program Files\Firebird\Firebird_2_5\bin\isql.exe',
        ]
        for path in search_paths:
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def sanitize_identifier(name: str, auto_prefix_reserved: bool = True) -> str:
        """Sanitize SQL identifiers (table and column names)."""
        name = name.strip().upper()
        clean = ""
        for ch in name:
            if ch.isalnum() or ch == '_':
                clean += ch
            else:
                clean += '_'
        if clean and clean[0].isdigit():
            clean = 'T_' + clean

        clean = clean or 'CAMPO'

        # Auto-prefix if it conflicts with Firebird reserved word
        if auto_prefix_reserved and clean in FIREBIRD_RESERVED_WORDS:
            clean = f"F_{clean}"

        return clean

    @staticmethod
    def format_sql_value(val: Any, field_type: int) -> str:
        """Format Python values into valid Firebird SQL literals."""
        if val is None or val == '':
            if field_type == 1 and val == '':
                return "''"
            return 'NULL'

        if isinstance(val, bool):
            return 'TRUE' if val else 'FALSE'

        if isinstance(val, (int, float)):
            return str(val)

        if isinstance(val, datetime.date):
            return f"'{val.strftime('%Y-%m-%d')}'"

        if isinstance(val, datetime.time):
            return f"'{val.strftime('%H:%M:%S')}'"

        if isinstance(val, datetime.datetime):
            return f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'"

        # String / text
        str_val = str(val).replace("'", "''")
        return f"'{str_val}'"

    @classmethod
    def generate_table_ddl(
        cls,
        table_name: str,
        fields: List[Dict[str, Any]],
        primary_keys: Optional[List[str]] = None,
        firebird_version: str = '3.0'
    ) -> str:
        """Generates CREATE TABLE DDL script for Firebird."""
        clean_table = cls.sanitize_identifier(table_name)
        lines = []
        lines.append(f"/* ========================================================= */")
        lines.append(f"/* TABELA: {clean_table}                                     */")
        lines.append(f"/* ========================================================= */")
        lines.append(f"RECREATE TABLE {clean_table} (")

        col_defs = []
        for f in fields:
            cname = cls.sanitize_identifier(f['name'])
            fb_type = f.get('firebird_type', 'VARCHAR(255)')

            # If Firebird 2.5, change BOOLEAN to SMALLINT CHECK (x IN (0, 1))
            if firebird_version.startswith('2.') and 'BOOLEAN' in fb_type.upper():
                fb_type = 'SMALLINT CHECK (' + cname + ' IN (0, 1))'

            col_defs.append(f"    {cname.ljust(25)} {fb_type}")

        # Primary Key constraint - only include columns that actually exist in the table definition
        valid_field_names_clean = {cls.sanitize_identifier(f['name']): f['name'] for f in fields}
        valid_pk_cols = []
        if primary_keys:
            for k in primary_keys:
                clean_k = cls.sanitize_identifier(k)
                if clean_k in valid_field_names_clean and clean_k not in valid_pk_cols:
                    valid_pk_cols.append(clean_k)

        if valid_pk_cols:
            pk_cols = ", ".join(valid_pk_cols)
            col_defs.append(f"    CONSTRAINT PK_{clean_table} PRIMARY KEY ({pk_cols})")
        elif fields and cls.sanitize_identifier(fields[0]['name']) in ('ID', 'CODIGO', f'ID_{clean_table}', f'COD_{clean_table}'):
            pk_col = cls.sanitize_identifier(fields[0]['name'])
            col_defs.append(f"    CONSTRAINT PK_{clean_table} PRIMARY KEY ({pk_col})")

        lines.append(",\n".join(col_defs))
        lines.append(");\n")
        lines.append(f"COMMIT WORK;\n")

        # Sequences / Generators for ID columns
        first_col = cls.sanitize_identifier(fields[0]['name']) if fields else ''
        if first_col and ('ID' in first_col or 'COD' in first_col):
            gen_name = f"GEN_{clean_table}_ID"
            lines.append(f"/* Generator & Trigger para AutoIncrement em {clean_table} */")
            lines.append(f"CREATE SEQUENCE {gen_name};")
            lines.append(f"ALTER SEQUENCE {gen_name} RESTART WITH 1000;")
            lines.append(f"SET TERM ^ ;")
            lines.append(f"CREATE OR ALTER TRIGGER TR_{clean_table}_BI FOR {clean_table}")
            lines.append(f"ACTIVE BEFORE INSERT POSITION 0 AS")
            lines.append(f"BEGIN")
            lines.append(f"    IF (NEW.{first_col} IS NULL OR NEW.{first_col} <= 0) THEN")
            lines.append(f"        NEW.{first_col} = NEXT VALUE FOR {gen_name};")
            lines.append(f"END^")
            lines.append(f"SET TERM ; ^\n")
            lines.append(f"COMMIT WORK;\n")

        return "\n".join(lines)

    @classmethod
    def generate_dml_inserts(
        cls,
        table_name: str,
        fields: List[ParadoxField],
        records: List[Dict[str, Any]],
        batch_size: int = 250
    ) -> str:
        """Generates batch INSERT INTO statements with periodic COMMIT WORK."""
        if not records:
            return f"/* Nenhum registro para a tabela {table_name} */\n"

        clean_table = cls.sanitize_identifier(table_name)
        col_names = [cls.sanitize_identifier(f.name) for f in fields]
        cols_str = ", ".join(col_names)

        lines = []
        lines.append(f"/* INSERÇÃO DE DADOS: {clean_table} ({len(records)} registros) */")

        for idx, row in enumerate(records, 1):
            val_strs = []
            for f in fields:
                raw_val = row.get(f.name)
                val_strs.append(cls.format_sql_value(raw_val, f.ftype))

            vals_line = ", ".join(val_strs)
            lines.append(f"INSERT INTO {clean_table} ({cols_str}) VALUES ({vals_line});")

            if idx % batch_size == 0:
                lines.append("COMMIT WORK;")

        if len(records) % batch_size != 0:
            lines.append("COMMIT WORK;")

        lines.append("")
        return "\n".join(lines)

    @classmethod
    def convert_paradox_file(
        cls,
        filepath: str,
        custom_mappings: Optional[Dict[str, str]] = None,
        firebird_version: str = '3.0'
    ) -> Dict[str, Any]:
        """
        Parses a Paradox table and generates complete Firebird DDL & DML script.
        """
        reader = ParadoxReader(filepath)
        table_name = os.path.splitext(os.path.basename(filepath))[0]

        fields_meta = []
        for f in reader.fields:
            f_dict = f.to_dict()
            if custom_mappings and f.name in custom_mappings:
                f_dict['firebird_type'] = custom_mappings[f.name]
            fields_meta.append(f_dict)

        records = reader.read_all_records()

        ddl = cls.generate_table_ddl(table_name, fields_meta, primary_keys=reader.primary_keys, firebird_version=firebird_version)
        dml = cls.generate_dml_inserts(table_name, reader.fields, records)

        full_sql = []
        full_sql.append("/* ========================================================================= */")
        full_sql.append(f"/* SCRIPT DE MIGRAÇÃO PARADOX -> FIREBIRD                                   */")
        full_sql.append(f"/* Tabela: {table_name}                                                     */")
        full_sql.append(f"/* Registros: {len(records)}                                                */")
        full_sql.append(f"/* Gerado em: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}       */")
        full_sql.append("/* ========================================================================= */\n")
        full_sql.append(ddl)
        full_sql.append("\n")
        full_sql.append(dml)

        return {
            'table_name': table_name,
            'record_count': len(records),
            'field_count': len(reader.fields),
            'fields': fields_meta,
            'sample_records': records[:15],
            'sql_script': "\n".join(full_sql)
        }

    @classmethod
    def create_fdb_database(
        cls,
        output_fdb_path: str,
        sql_script: str,
        user: str = 'SYSDBA',
        password: str = 'masterkey',
        page_size: int = 8192,
        charset: str = 'UTF8'
    ) -> Dict[str, Any]:
        """
        Creates a real .FDB Firebird database file on disk and runs the full SQL script on it.
        """
        abs_fdb_path = os.path.abspath(output_fdb_path)
        os.makedirs(os.path.dirname(abs_fdb_path), exist_ok=True)

        if os.path.exists(abs_fdb_path):
            try:
                os.remove(abs_fdb_path)
            except Exception as e:
                return {'success': False, 'error': f'Não foi possível sobrescrever o arquivo FDB existente: {e}'}

        isql_exe = cls.find_isql_executable()
        if not isql_exe:
            return {'success': False, 'error': 'isql.exe não encontrado no sistema. Certifique-se de que o Firebird está instalado.'}

        # Build execution script
        db_sql = []
        db_sql.append(f"CREATE DATABASE '{abs_fdb_path}' USER '{user}' PASSWORD '{password}' PAGE_SIZE {page_size} DEFAULT CHARACTER SET {charset};")
        db_sql.append(sql_script)
        db_sql.append("COMMIT WORK;")
        db_sql.append("EXIT;")

        script_text = "\n".join(db_sql)
        temp_sql_file = os.path.join(tempfile.gettempdir(), f"fb_build_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.sql")

        try:
            with open(temp_sql_file, 'w', encoding='utf-8') as f:
                f.write(script_text)

            proc = subprocess.run([isql_exe, '-q', '-i', temp_sql_file], capture_output=True, text=True, timeout=180)

            if not os.path.exists(abs_fdb_path):
                err_msg = proc.stderr or proc.stdout or "Falha na criação do arquivo .FDB"
                return {'success': False, 'error': f'Erro ao criar banco de dados: {err_msg}'}

            file_size = os.path.getsize(abs_fdb_path)
            return {
                'success': True,
                'fdb_path': abs_fdb_path,
                'file_size': file_size,
                'file_size_formatted': f"{file_size / (1024 * 1024):.2f} MB",
                'message': f"Banco de dados Firebird criado com sucesso ({file_size / (1024 * 1024):.2f} MB)!"
            }

        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            if os.path.exists(temp_sql_file):
                try:
                    os.remove(temp_sql_file)
                except Exception:
                    pass

    @classmethod
    def test_connection(cls, conn_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tests TCP/IP connection to a Firebird server instance.
        """
        host = conn_params.get('host', 'localhost')
        port = int(conn_params.get('port', 3050))
        database = conn_params.get('database', '')
        user = conn_params.get('user', 'SYSDBA')
        password = conn_params.get('password', 'masterkey')
        charset = conn_params.get('charset', 'UTF8')

        isql_exe = cls.find_isql_executable()
        dsn = f"{host}/{port}:{database}" if host and database else (database or host)

        try:
            # Try via firebird.driver if installed
            from firebird.driver import connect
            with connect(dsn, user=user, password=password, charset=charset) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT rdb$get_context('SYSTEM', 'ENGINE_VERSION') FROM rdb$database;")
                    row = cur.fetchone()
                    version = row[0] if row else 'Desconhecida'
            return {
                'success': True,
                'message': f'Conexão bem-sucedida ao Firebird! Versão do motor: {version}',
                'engine_version': version
            }
        except Exception as e_driver:
            # Fallback test via isql.exe
            if isql_exe and database:
                test_script = f"CONNECT '{dsn}' USER '{user}' PASSWORD '{password}';\nSHOW DATABASE;\nEXIT;\n"
                tf = os.path.join(tempfile.gettempdir(), f"fb_test_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.sql")
                try:
                    with open(tf, 'w', encoding='utf-8') as f:
                        f.write(test_script)
                    proc = subprocess.run([isql_exe, '-q', '-i', tf], capture_output=True, text=True, timeout=15)
                    if 'Database:' in proc.stdout or proc.returncode == 0:
                        return {
                            'success': True,
                            'message': f'Conexão via ISQL bem-sucedida ({dsn})!',
                            'engine_version': 'Firebird Server'
                        }
                    else:
                        err = proc.stderr or proc.stdout or str(e_driver)
                        return {'success': False, 'error': f'Falha na conexão Firebird: {err}'}
                except Exception as ex:
                    return {'success': False, 'error': f'Erro ao testar via ISQL: {ex}'}
                finally:
                    if os.path.exists(tf): os.remove(tf)

            return {'success': False, 'error': f'Não foi possível conectar: {str(e_driver)}'}

    @classmethod
    def execute_query(cls, database_path_or_dsn: str, query: str, user: str = 'SYSDBA', password: str = 'masterkey') -> Dict[str, Any]:
        """
        Executes a SELECT or DDL/DML query and returns results formatted as JSON.
        """
        query_clean = query.strip()
        if not query_clean:
            return {'success': False, 'error': 'Consulta SQL vazia.'}

        try:
            from firebird.driver import connect
            with connect(database_path_or_dsn, user=user, password=password, charset='UTF8') as conn:
                with conn.cursor() as cur:
                    cur.execute(query_clean)
                    if query_clean.upper().startswith(('SELECT', 'WITH', 'SHOW')):
                        columns = [desc[0] for desc in cur.description] if cur.description else []
                        rows = []
                        for row in cur.fetchmany(500):
                            row_dict = {}
                            for col, val in zip(columns, row):
                                if isinstance(val, (datetime.date, datetime.datetime, datetime.time)):
                                    row_dict[col] = str(val)
                                elif isinstance(val, bytes):
                                    row_dict[col] = f'<BLOB {len(val)} bytes>'
                                else:
                                    row_dict[col] = val
                            rows.append(row_dict)
                        return {
                            'success': True,
                            'is_select': True,
                            'columns': columns,
                            'rows': rows,
                            'row_count': len(rows),
                            'message': f'{len(rows)} linhas retornadas.'
                        }
                    else:
                        conn.commit()
                        return {
                            'success': True,
                            'is_select': False,
                            'message': 'Comando SQL executado e confirmado (COMMIT) com sucesso.'
                        }
        except Exception as e:
            # Fallback to ISQL if query runner fails
            isql_exe = cls.find_isql_executable()
            if isql_exe and os.path.exists(database_path_or_dsn):
                script = f"CONNECT '{database_path_or_dsn}' USER '{user}' PASSWORD '{password}';\n{query_clean};\nEXIT;\n"
                tf = os.path.join(tempfile.gettempdir(), f"fb_q_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.sql")
                try:
                    with open(tf, 'w', encoding='utf-8') as f:
                        f.write(script)
                    proc = subprocess.run([isql_exe, '-q', '-i', tf], capture_output=True, text=True, timeout=30)
                    output = proc.stdout or proc.stderr
                    return {
                        'success': True,
                        'is_select': True,
                        'raw_output': output,
                        'columns': ['RESULTADO_ISQL'],
                        'rows': [{'RESULTADO_ISQL': line} for line in output.splitlines()[:100]],
                        'message': 'Executado via Firebird ISQL Console.'
                    }
                except Exception as ex2:
                    return {'success': False, 'error': f'Erro ao executar consulta: {ex2}'}
                finally:
                    if os.path.exists(tf): os.remove(tf)

            return {'success': False, 'error': str(e)}

    @classmethod
    def execute_direct_firebird(cls, conn_params: Dict[str, Any], sql_script: str) -> Dict[str, Any]:
        """
        Executes generated SQL directly into an existing Firebird Database instance.
        """
        try:
            from firebird.driver import connect
            host = conn_params.get('host', 'localhost')
            port = int(conn_params.get('port', 3050))
            database = conn_params.get('database')
            user = conn_params.get('user', 'SYSDBA')
            password = conn_params.get('password', 'masterkey')
            charset = conn_params.get('charset', 'UTF8')

            dsn = f"{host}/{port}:{database}" if host else database

            statements = [s.strip() for s in sql_script.split(';') if s.strip()]
            executed = 0

            with connect(dsn, user=user, password=password, charset=charset) as conn:
                with conn.cursor() as cur:
                    for stmt in statements:
                        if stmt.upper().startswith('COMMIT') or stmt.upper().startswith('/*') or stmt.upper().startswith('SET TERM'):
                            continue
                        cur.execute(stmt)
                        executed += 1
                conn.commit()

            return {
                'success': True,
                'statements_executed': executed,
                'message': f'{executed} comandos SQL executados com sucesso no Firebird!'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
