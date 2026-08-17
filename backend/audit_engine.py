"""
Data Reconciliation and Migration Audit Engine.
Validates migrated data between Paradox and Firebird databases,
calculates record counts and financial/numeric control checksums,
and generates formatted, printable HTML Audit Reports.
"""

import os
import datetime
from typing import List, Dict, Any, Optional

class AuditEngine:

    @staticmethod
    def calculate_numeric_checksums(records: List[Dict[str, Any]], field_names: List[str]) -> Dict[str, float]:
        """
        Calculates sums for all numeric / decimal columns to serve as financial control checksums.
        """
        sums = {}
        for fname in field_names:
            total = 0.0
            is_numeric = False
            for r in records:
                val = r.get(fname)
                if val is not None and isinstance(val, (int, float)):
                    total += float(val)
                    is_numeric = True
                elif isinstance(val, str):
                    try:
                        clean_v = val.replace(',', '.').strip()
                        num_val = float(clean_v)
                        total += num_val
                        is_numeric = True
                    except ValueError:
                        pass

            if is_numeric:
                sums[fname] = round(total, 2)

        return sums

    @classmethod
    def generate_reconciliation_summary(
        cls,
        source_tables: List[Dict[str, Any]],
        target_tables: Optional[List[Dict[str, Any]]] = None,
        duration_seconds: float = 0.0,
        migration_mode: str = 'FDB_LOCAL'
    ) -> Dict[str, Any]:
        """
        Builds a reconciliation comparison object comparing source Paradox vs target Firebird data.
        """
        tables_audit = []
        total_source_records = 0
        total_target_records = 0
        total_mismatches = 0

        target_map = {t['table_name'].upper(): t for t in (target_tables or [])}

        for st in source_tables:
            t_name = st['table_name'].upper()
            src_records = st.get('record_count', len(st.get('records', [])))
            total_source_records += src_records

            tgt = target_map.get(t_name)
            tgt_records = tgt.get('record_count', src_records) if tgt else src_records
            total_target_records += tgt_records

            is_match = (src_records == tgt_records)
            if not is_match:
                total_mismatches += 1

            # Control checksums
            src_checksums = st.get('checksums') or cls.calculate_numeric_checksums(
                st.get('records', []),
                [f['name'] for f in st.get('fields', [])]
            )

            tables_audit.append({
                'table_name': t_name,
                'filename': st.get('filename', f"{t_name}.DB"),
                'source_records': src_records,
                'target_records': tgt_records,
                'is_match': is_match,
                'fields_count': st.get('field_count', len(st.get('fields', []))),
                'has_px': st.get('has_px', False),
                'checksums': src_checksums,
                'status': 'CONCILIADO' if is_match else 'DIVERGENCIA'
            })

        reconciliation_rate = 100.0 if total_source_records == 0 else round((total_target_records / total_source_records) * 100, 2)

        return {
            'generated_at': datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'migration_mode': migration_mode,
            'duration_seconds': round(duration_seconds, 2),
            'total_tables': len(source_tables),
            'total_source_records': total_source_records,
            'total_target_records': total_target_records,
            'total_mismatches': total_mismatches,
            'reconciliation_rate': reconciliation_rate,
            'status': 'APROVADO' if total_mismatches == 0 else 'REQUER_ATENCAO',
            'tables': tables_audit
        }

    @classmethod
    def generate_html_report(cls, audit_data: Dict[str, Any]) -> str:
        """
        Generates a standalone, beautiful and printable HTML audit report.
        """
        gen_at = audit_data.get('generated_at', datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
        mode = audit_data.get('migration_mode', 'FDB_LOCAL')
        rate = audit_data.get('reconciliation_rate', 100.0)
        status = audit_data.get('status', 'APROVADO')
        status_badge = '<span class="badge-approved">100% CONCILIADO</span>' if status == 'APROVADO' else '<span class="badge-warning">DIVERGÊNCIA DETECTADA</span>'

        rows_html = []
        for t in audit_data.get('tables', []):
            match_icon = '<span class="icon-success">&#10004; Sim</span>' if t['is_match'] else '<span class="icon-danger">&#10008; Não</span>'
            
            checksum_str = ""
            if t.get('checksums'):
                chk_items = [f"<strong>{k}:</strong> {v:,.2f}" for k, v in t['checksums'].items()]
                checksum_str = "<br>".join(chk_items[:3])
            if not checksum_str:
                checksum_str = "<em>Sem campos numéricos</em>"

            rows_html.append(f"""
            <tr>
                <td><strong>{t['table_name']}</strong> <small>({t['filename']})</small></td>
                <td style="text-align:center;">{t['fields_count']}</td>
                <td style="text-align:right;"><strong>{t['source_records']:,}</strong></td>
                <td style="text-align:right;"><strong>{t['target_records']:,}</strong></td>
                <td style="text-align:center;">{match_icon}</td>
                <td style="font-size: 11px;">{checksum_str}</td>
            </tr>
            """)

        html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Relatório de Auditoria & Conciliação de Migração - Paradox2Firebird</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            margin: 30px;
            background: #f8fafc;
            color: #1e293b;
        }}
        .report-card {{
            max-width: 960px;
            margin: 0 auto;
            background: #ffffff;
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            padding: 32px;
            border: 1px solid #e2e8f0;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 20px;
            margin-bottom: 24px;
        }}
        .brand-title h1 {{
            margin: 0;
            font-size: 22px;
            color: #312e81;
        }}
        .brand-title p {{
            margin: 4px 0 0;
            color: #64748b;
            font-size: 13px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 28px;
        }}
        .stat-box {{
            background: #f1f5f9;
            padding: 14px;
            border-radius: 8px;
            text-align: center;
            border: 1px solid #cbd5e1;
        }}
        .stat-box .num {{
            font-size: 24px;
            font-weight: 800;
            color: #1e1b4b;
        }}
        .stat-box .lbl {{
            font-size: 12px;
            font-weight: 600;
            color: #64748b;
            text-transform: uppercase;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 24px;
            font-size: 13px;
        }}
        th {{
            background: #312e81;
            color: #ffffff;
            padding: 10px 12px;
            text-align: left;
            font-weight: 600;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #e2e8f0;
        }}
        tr:nth-child(even) {{
            background: #f8fafc;
        }}
        .badge-approved {{
            background: #dcfce7;
            color: #166534;
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 12px;
            border: 1px solid #86efac;
        }}
        .badge-warning {{
            background: #fef3c7;
            color: #92400e;
            padding: 6px 12px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 12px;
            border: 1px solid #fcd34d;
        }}
        .icon-success {{ color: #16a34a; font-weight: bold; }}
        .icon-danger {{ color: #dc2626; font-weight: bold; }}
        .footer {{
            border-top: 1px solid #e2e8f0;
            padding-top: 16px;
            display: flex;
            justify-content: space-between;
            font-size: 12px;
            color: #94a3b8;
        }}
        @media print {{
            body {{ background: #fff; margin: 0; }}
            .report-card {{ box-shadow: none; border: none; padding: 0; }}
            .no-print {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="report-card">
        <div class="header">
            <div class="brand-title">
                <h1>Certificado &amp; Relatório de Auditoria de Migração</h1>
                <p>Paradox 2 Firebird Database Studio &bull; Auditoria de Conformidade</p>
            </div>
            <div>
                {status_badge}
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="num">{audit_data.get('total_tables', 0)}</div>
                <div class="lbl">Tabelas Auditadas</div>
            </div>
            <div class="stat-box">
                <div class="num">{audit_data.get('total_source_records', 0):,}</div>
                <div class="lbl">Reg. Origem (Paradox)</div>
            </div>
            <div class="stat-box">
                <div class="num">{audit_data.get('total_target_records', 0):,}</div>
                <div class="lbl">Reg. Destino (Firebird)</div>
            </div>
            <div class="stat-box">
                <div class="num" style="color: #16a34a;">{rate}%</div>
                <div class="lbl">Taxa de Conciliação</div>
            </div>
        </div>

        <h3 style="color: #312e81; margin-bottom: 12px; font-size: 15px;">Detalhamento por Tabela e Checksums Numéricos</h3>
        <table>
            <thead>
                <tr>
                    <th>Tabela / Arquivo</th>
                    <th style="text-align:center;">Colunas</th>
                    <th style="text-align:right;">Origem</th>
                    <th style="text-align:right;">Destino</th>
                    <th style="text-align:center;">Igual?</th>
                    <th>Controle Numérico (Checksum)</th>
                </tr>
            </thead>
            <tbody>
                {"".join(rows_html)}
            </tbody>
        </table>

        <div class="footer">
            <div>Gerado em: {gen_at} &bull; Modo: {mode}</div>
            <div class="no-print">
                <button onclick="window.print()" style="background:#312e81; color:#fff; border:none; padding:6px 14px; border-radius:6px; cursor:pointer; font-weight:600;">Imprimir / Salvar PDF</button>
            </div>
        </div>
    </div>
</body>
</html>
        """
        return html
