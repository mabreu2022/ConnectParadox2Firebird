"""
Smart Foreign Keys and Relational Graph Engine.
Detects potential foreign key relationships between legacy Paradox tables using naming heuristics,
checks for orphaned records, and generates Firebird FOREIGN KEY DDL statements.
"""

import os
from typing import List, Dict, Any, Optional, Set, Tuple
from .paradox_engine import ParadoxReader

class SmartRelationsEngine:

    COMMON_ID_SUFFIXES = [
        '_ID', 'ID', '_COD', 'COD', '_CODIGO', 'CODIGO', '_NUM', 'NUM',
        '_FK', '_REF', '_CLI', '_PROD', '_FORN', '_VEND', '_PED'
    ]

    COMMON_ID_PREFIXES = [
        'ID_', 'COD_', 'NUM_', 'FK_', 'CD_'
    ]

    @classmethod
    def clean_name(cls, name: str) -> str:
        return name.strip().upper().replace(' ', '_')

    @classmethod
    def find_pk_candidates(cls, table_info: Dict[str, Any]) -> List[str]:
        """Finds primary key or identifier columns in a table."""
        # 1. First choice: explicit primary keys from index or header
        if table_info.get('primary_keys'):
            return [cls.clean_name(k) for k in table_info['primary_keys']]

        # 2. Heuristics based on field name
        t_name = cls.clean_name(table_info.get('table_name', ''))
        candidates = []
        for f in table_info.get('fields', []):
            fname = cls.clean_name(f.get('name', ''))
            if fname in ('ID', 'CODIGO', 'COD', f'ID_{t_name}', f'COD_{t_name}', f'{t_name}_ID', f'{t_name}_COD'):
                candidates.append(fname)

        if not candidates and table_info.get('fields'):
            candidates.append(cls.clean_name(table_info['fields'][0].get('name', '')))

        return candidates

    @classmethod
    def detect_relations(cls, tables_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Inspects all loaded tables and detects potential Foreign Keys.
        tables_data is a list of dicts:
        {
           'table_name': 'VENDAS',
           'filename': 'VENDAS.DB',
           'fields': [{'name': 'COD_CLIENTE', 'type': 'INTEGER', ...}],
           'primary_keys': ['ID_VENDA'],
           'records': [...] (optional)
        }
        """
        detected_relations: List[Dict[str, Any]] = []
        table_map = {cls.clean_name(t['table_name']): t for t in tables_data}

        # Build table primary key map
        pk_map = {}
        for t_name, t_info in table_map.items():
            pk_map[t_name] = cls.find_pk_candidates(t_info)

        # Look for references across tables
        for child_name, child_table in table_map.items():
            child_fields = child_table.get('fields', [])
            child_pks = set(pk_map.get(child_name, []))

            for field in child_fields:
                f_name = cls.clean_name(field.get('name', ''))

                # Don't consider the child table's own primary key as a foreign key if single-column PK
                p_sing = child_name.rstrip('S')
                if f_name in child_pks and len(child_pks) == 1 and (f_name in ('ID', 'CODIGO', 'COD') or f_name in (f"ID_{child_name}", f"ID_{p_sing}", f"COD_{child_name}", f"COD_{p_sing}")):
                    continue

                # Skip non-key descriptive columns
                if any(skip in f_name for skip in ['TOTAL', 'VALOR', 'PRECO', 'STATUS', 'NOME', 'DATA', 'OBS', 'CATEGORIA', 'DESCRICAO', 'QUANTIDADE', 'QTD']):
                    continue

                # Must look like an ID or code or reference
                is_id_like = any(f_name.startswith(p) or f_name.endswith(s) for p in ['ID_', 'COD_', 'CD_', 'FK_'] for s in ['_ID', 'ID', '_COD', 'COD', '_CODIGO', 'CODIGO'])

                # Test matches against other parent tables
                for parent_name, parent_table in table_map.items():
                    if parent_name == child_name:
                        continue

                    parent_pks = pk_map.get(parent_name, [])
                    if not parent_pks:
                        continue

                    parent_main_pk = parent_pks[0]
                    p_singular = parent_name.rstrip('S')

                    confidence = 0
                    match_reason = ""

                    # Rule 1: Exact column name match where column is like ID (e.g., ID_CLIENTE in VENDAS matching ID_CLIENTE in CLIENTES)
                    if f_name == parent_main_pk and is_id_like:
                        confidence = 95
                        match_reason = f"Nome exato da chave primária '{parent_main_pk}' da tabela '{parent_name}'"

                    # Rule 2: Child column contains parent table name or singular (e.g. COD_CLIENTE / ID_CLIENTE -> CLIENTES)
                    elif (parent_name in f_name or p_singular in f_name) and is_id_like:
                        confidence = 90
                        match_reason = f"Coluna referencia diretamente a tabela '{parent_name}'"

                    # Rule 3: Abbreviation match (e.g., COD_CLI -> CLIENTES, COD_PROD -> PRODUTOS)
                    elif is_id_like and any(abbr in f_name and abbr in parent_name for abbr in ['CLI', 'PROD', 'FORN', 'VEND', 'FUNC', 'USU', 'ITEM']):
                        confidence = 80
                        match_reason = f"Abreviação relacional compatível com '{parent_name}.{parent_main_pk}'"

                    if confidence >= 75:
                        existing = any(
                            r['child_table'] == child_name and
                            r['child_column'] == f_name and
                            r['parent_table'] == parent_name
                            for r in detected_relations
                        )
                        if not existing:
                            fk_constraint_name = f"FK_{child_name}_{parent_name[:6]}_{f_name[:6]}"
                            detected_relations.append({
                                'id': f"{child_name}_{f_name}_{parent_name}",
                                'child_table': child_name,
                                'child_column': f_name,
                                'parent_table': parent_name,
                                'parent_column': parent_main_pk,
                                'constraint_name': fk_constraint_name,
                                'confidence': confidence,
                                'reason': match_reason,
                                'enabled': True,
                                'orphans_count': 0,
                                'status': 'DETECTADO'
                            })

        return detected_relations

    @classmethod
    def validate_orphans(
        cls,
        relation: Dict[str, Any],
        child_records: List[Dict[str, Any]],
        parent_records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validates if there are orphaned records in child table that don't exist in parent table.
        """
        child_col = relation['child_column']
        parent_col = relation['parent_column']

        parent_keys = set()
        for pr in parent_records:
            pval = pr.get(parent_col) or pr.get(parent_col.lower()) or pr.get(parent_col.upper())
            if pval is not None and str(pval).strip() != '':
                parent_keys.add(str(pval).strip())

        orphans = []
        null_count = 0
        valid_count = 0

        for r_idx, cr in enumerate(child_records):
            cval = cr.get(child_col) or cr.get(child_col.lower()) or cr.get(child_col.upper())
            if cval is None or str(cval).strip() == '':
                null_count += 1
            elif str(cval).strip() in parent_keys:
                valid_count += 1
            else:
                orphans.append({
                    'row_index': r_idx + 1,
                    'key_value': cval,
                    'record_preview': {k: cr[k] for k in list(cr.keys())[:4]}
                })

        total_child = len(child_records)
        orphan_count = len(orphans)
        integrity_pct = round((valid_count / total_child * 100) if total_child > 0 else 100, 1)

        return {
            'relation_id': relation.get('id'),
            'total_child_records': total_child,
            'valid_count': valid_count,
            'null_count': null_count,
            'orphan_count': orphan_count,
            'integrity_percentage': integrity_pct,
            'has_orphans': orphan_count > 0,
            'orphan_sample': orphans[:10]
        }

    @classmethod
    def generate_foreign_keys_ddl(
        cls,
        relations: List[Dict[str, Any]],
        on_delete: str = 'NO ACTION',
        on_update: str = 'CASCADE'
    ) -> str:
        """
        Generates Firebird ALTER TABLE ... ADD CONSTRAINT FK_... statements for approved relations.
        """
        lines = []
        lines.append("/* ========================================================= */")
        lines.append("/* DEFINIÇÃO DE CHAVES ESTRANGEIRAS (FOREIGN KEYS)           */")
        lines.append("/* ========================================================= */\n")

        active_relations = [r for r in relations if r.get('enabled', True)]
        if not active_relations:
            return "/* Nenhuma chave estrangeira selecionada para inclusão. */\n"

        for rel in active_relations:
            c_tbl = rel['child_table']
            c_col = rel['child_column']
            p_tbl = rel['parent_table']
            p_col = rel['parent_column']
            c_name = rel.get('constraint_name', f"FK_{c_tbl}_{p_tbl[:6]}")

            lines.append(f"ALTER TABLE {c_tbl} ADD CONSTRAINT {c_name}")
            lines.append(f"    FOREIGN KEY ({c_col}) REFERENCES {p_tbl} ({p_col})")
            lines.append(f"    ON DELETE {on_delete} ON UPDATE {on_update};")
            lines.append("COMMIT WORK;\n")

        return "\n".join(lines)
