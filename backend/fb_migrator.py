"""
Firebird Database Migration & Modernization Engine
Migrates Firebird 2.5 and 3.0 databases to Firebird 5.0 (ODS 13.1).
Supports automated GBAK transport backup/restore, ODS header inspection, and schema modernization.
"""

import os
import struct
import subprocess
import tempfile
import datetime
from typing import Dict, Any, List, Optional

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
ENGINES_DIR = os.path.join(BASE_DIR, 'engines')

ODS_VERSIONS_MAP = {
    10: {'version': '1.0 / 1.5', 'name': 'Firebird 1.x'},
    11: {
        0: {'version': '2.0', 'name': 'Firebird 2.0'},
        1: {'version': '2.1', 'name': 'Firebird 2.1'},
        2: {'version': '2.5', 'name': 'Firebird 2.5'}
    },
    12: {
        0: {'version': '3.0', 'name': 'Firebird 3.0'}
    },
    13: {
        0: {'version': '4.0', 'name': 'Firebird 4.0'},
        1: {'version': '5.0', 'name': 'Firebird 5.0'}
    }
}


class FirebirdMigrator:

    @classmethod
    def read_ods_header(cls, filepath: str) -> Dict[str, Any]:
        """
        Reads the Firebird database header and extracts ODS version, page size, and dialect.
        Uses gstat utility when available, with binary fallback.
        """
        if not os.path.exists(filepath):
            return {'valid': False, 'error': f'Arquivo não encontrado: {filepath}'}

        file_size = os.path.getsize(filepath)
        if file_size < 1024:
            return {'valid': False, 'error': 'Arquivo muito pequeno para ser um banco Firebird.'}

        # Check if it's a transportable backup (.FBK)
        with open(filepath, 'rb') as f:
            header_bytes = f.read(512)

        if filepath.upper().endswith('.FBK') or b'GBK' in header_bytes[:64] or b'FBK' in header_bytes[:64]:
            return {
                'valid': True,
                'is_backup': True,
                'file_type': 'FBK (Backup Transportável)',
                'ods_string': 'Transportável',
                'detected_version': 'Backup Transportável (.FBK)',
                'file_size': file_size,
                'file_size_formatted': f"{file_size / (1024 * 1024):.2f} MB"
            }

        # Try gstat inspection first
        for gstat_exe in cls.get_all_gstat_executables():
            try:
                gstat_cwd = os.path.dirname(gstat_exe)
                proc = subprocess.run(
                    [gstat_exe, '-h', os.path.abspath(filepath)],
                    capture_output=True, text=True, timeout=10, cwd=gstat_cwd
                )
                if proc.stdout and 'ODS version' in proc.stdout:
                    info = {
                        'valid': True,
                        'is_backup': False,
                        'file_size': file_size,
                        'file_size_formatted': f"{file_size / (1024 * 1024):.2f} MB"
                    }
                    for line in proc.stdout.splitlines():
                        line_s = line.strip()
                        if line_s.startswith('ODS version'):
                            ods_val = line_s.split('ODS version')[-1].strip()
                            info['ods_string'] = ods_val
                            try:
                                parts = ods_val.split('.')
                                info['ods_major'] = int(parts[0])
                                info['ods_minor'] = int(parts[1]) if len(parts) > 1 else 0
                            except Exception:
                                pass

                            if ods_val.startswith('11.'):
                                info['detected_version'] = f'Firebird 2.5 (ODS {ods_val})'
                            elif ods_val.startswith('12.'):
                                info['detected_version'] = f'Firebird 3.0 (ODS {ods_val})'
                            elif ods_val.startswith('13.0'):
                                info['detected_version'] = f'Firebird 4.0 (ODS {ods_val})'
                            elif ods_val.startswith('13.1'):
                                info['detected_version'] = f'Firebird 5.0 (ODS {ods_val})'
                            elif ods_val.startswith('10.'):
                                info['detected_version'] = f'Firebird 1.5 (ODS {ods_val})'
                            else:
                                info['detected_version'] = f'Firebird (ODS {ods_val})'
                        elif line_s.startswith('Page size'):
                            try:
                                info['page_size'] = int(line_s.split('Page size')[-1].strip())
                            except Exception:
                                pass
                        elif line_s.startswith('Database dialect'):
                            info['dialect'] = line_s.split('Database dialect')[-1].strip()

                    if 'detected_version' in info:
                        return info
            except Exception:
                pass

        # Binary fallback inspection
        try:
            page_type = header_bytes[0]
            if page_type != 0x01:
                return {'valid': False, 'error': 'Assinatura de cabeçalho Firebird não reconhecida.'}

            page_size = struct.unpack_from('<H', header_bytes, 0x10)[0] or 4096
            return {
                'valid': True,
                'is_backup': False,
                'page_size': page_size,
                'ods_string': 'Legado',
                'detected_version': 'Firebird Database',
                'file_size': file_size,
                'file_size_formatted': f"{file_size / (1024 * 1024):.2f} MB"
            }
        except Exception as e:
            return {'valid': False, 'error': f'Erro ao ler banco: {str(e)}'}

    @classmethod
    def get_all_gstat_executables(cls) -> List[str]:
        """Finds all available gstat.exe utilities in priority order."""
        candidates = [
            os.path.join(ENGINES_DIR, 'fb25', 'bin', 'gstat.exe'),
            os.path.join(ENGINES_DIR, 'fb30', 'gstat.exe'),
            r'C:\Program Files (x86)\Firebird\Firebird_5_0\gstat.exe',
            r'C:\Program Files\Firebird\Firebird_5_0\gstat.exe',
        ]
        return [os.path.abspath(c) for c in candidates if os.path.exists(c)]

    @classmethod
    def find_gbak_executable(cls, target_version: str = '5.0') -> Optional[str]:
        """Finds gbak.exe for the requested Firebird version."""
        candidates = []

        if target_version.startswith('2.'):
            candidates += [
                os.path.join(ENGINES_DIR, 'fb25', 'bin', 'gbak.exe'),
                os.path.join(ENGINES_DIR, 'fb25', 'gbak.exe'),
                r'C:\Program Files (x86)\Firebird\Firebird_2_5\bin\gbak.exe',
                r'C:\Program Files\Firebird\Firebird_2_5\bin\gbak.exe',
            ]
        elif target_version.startswith('3.'):
            candidates += [
                os.path.join(ENGINES_DIR, 'fb30', 'gbak.exe'),
                os.path.join(ENGINES_DIR, 'fb30', 'bin', 'gbak.exe'),
                r'C:\Program Files (x86)\Firebird\Firebird_3_0\gbak.exe',
                r'C:\Program Files\Firebird\Firebird_3_0\gbak.exe',
            ]
        elif target_version.startswith('5.'):
            candidates += [
                r'C:\Program Files (x86)\Firebird\Firebird_5_0\gbak.exe',
                r'C:\Program Files\Firebird\Firebird_5_0\gbak.exe',
                os.path.join(ENGINES_DIR, 'fb50', 'gbak.exe'),
            ]

        for c in candidates:
            if os.path.exists(c):
                return os.path.abspath(c)

        # Fallback to any gbak available in 5.0 or 3.0 or 2.5
        all_fallbacks = [
            r'C:\Program Files (x86)\Firebird\Firebird_5_0\gbak.exe',
            r'C:\Program Files\Firebird\Firebird_5_0\gbak.exe',
            os.path.join(ENGINES_DIR, 'fb30', 'gbak.exe'),
            os.path.join(ENGINES_DIR, 'fb25', 'bin', 'gbak.exe'),
        ]
        for f in all_fallbacks:
            if os.path.exists(f):
                return os.path.abspath(f)

        return None

    @classmethod
    def find_isql_executable(cls, target_version: str = '5.0') -> Optional[str]:
        """Finds isql.exe for the requested Firebird version."""
        candidates = []
        if target_version.startswith('5.'):
            candidates += [
                r'C:\Program Files (x86)\Firebird\Firebird_5_0\isql.exe',
                r'C:\Program Files\Firebird\Firebird_5_0\isql.exe',
            ]
        elif target_version.startswith('3.'):
            candidates += [
                os.path.join(ENGINES_DIR, 'fb30', 'isql.exe'),
                r'C:\Program Files (x86)\Firebird\Firebird_3_0\isql.exe',
            ]
        elif target_version.startswith('2.'):
            candidates += [
                os.path.join(ENGINES_DIR, 'fb25', 'bin', 'isql.exe'),
                r'C:\Program Files (x86)\Firebird\Firebird_2_5\bin\isql.exe',
            ]

        for c in candidates:
            if os.path.exists(c):
                return os.path.abspath(c)
        return None

    @classmethod
    def migrate_database_to_fb5(
        cls,
        source_filepath: str,
        target_filepath: str,
        user: str = 'SYSDBA',
        password: str = 'masterkey',
        page_size: int = 8192,
        charset: str = 'UTF8'
    ) -> Dict[str, Any]:
        """
        Migrates a legacy Firebird 2.5 or 3.0 database (.FDB, .GDB, .FBK) to Firebird 5.0 (ODS 13.1).
        Uses a two-step transport backup (source GBAK) and restore (Firebird 5.0 GBAK).
        """
        source_path = os.path.abspath(source_filepath)
        target_path = os.path.abspath(target_filepath)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception as e:
                return {'success': False, 'error': f'Não foi possível sobrescrever o arquivo de destino: {e}'}

        header_info = cls.read_ods_header(source_path)
        is_backup_file = header_info.get('is_backup', False) or source_path.upper().endswith('.FBK')

        fb5_gbak = cls.find_gbak_executable('5.0')
        if not fb5_gbak:
            return {'success': False, 'error': 'Utilitário gbak do Firebird 5.0 não encontrado.'}

        temp_fbk = None
        logs = []

        try:
            if is_backup_file:
                fbk_to_restore = source_path
                logs.append(f"[OK] Arquivo de entrada já é um backup transportável: {os.path.basename(source_path)}")
            else:
                # Need to generate a transportable .fbk from source database
                ods_major = header_info.get('ods_major')
                if ods_major is None and header_info.get('ods_string'):
                    try:
                        ods_major = int(header_info['ods_string'].split('.')[0])
                    except Exception:
                        ods_major = 11

                source_version = '2.5' if (ods_major is not None and ods_major <= 11) else '3.0'
                source_gbak = cls.find_gbak_executable(source_version) or fb5_gbak

                timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                temp_fbk = os.path.join(tempfile.gettempdir(), f"fb_trans_{timestamp}.fbk")

                logs.append(f"[1/2] Gerando backup transportável (.FBK) com engine {source_version}...")

                srv_proc = None
                connect_db_target = source_path
                gbak_cwd = os.path.dirname(source_gbak)
                gbak_env = os.environ.copy()
                gbak_env['FIREBIRD'] = gbak_cwd
                gbak_env['PATH'] = gbak_cwd + ';' + gbak_env.get('PATH', '')

                try:
                    if source_version == '2.5':
                        fb25_srv_exe = os.path.join(gbak_cwd, 'fbserver.exe')
                        if os.path.exists(fb25_srv_exe):
                            import time
                            srv_proc = subprocess.Popen([fb25_srv_exe, '-a', '-p', '3051'], cwd=gbak_cwd, env=gbak_env)
                            time.sleep(1.0)
                            connect_db_target = f"localhost/3051:{source_path}"
                    elif source_version == '3.0':
                        # FB 3.0 embedded backup directly using fbclient.dll in its folder
                        connect_db_target = source_path

                    backup_cmd = [
                        source_gbak,
                        '-b',
                        '-t',  # Transportable format
                        '-user', user,
                        '-password', password,
                        connect_db_target,
                        temp_fbk
                    ]

                    proc_b = subprocess.run(backup_cmd, capture_output=True, text=True, cwd=gbak_cwd, env=gbak_env, timeout=300)
                finally:
                    if srv_proc:
                        try:
                            srv_proc.terminate()
                            srv_proc.wait(timeout=3)
                        except Exception:
                            pass

                if not os.path.exists(temp_fbk) or os.path.getsize(temp_fbk) == 0:
                    err_msg = proc_b.stderr or proc_b.stdout or 'Falha desconhecida na geração do backup.'
                    return {'success': False, 'error': f'Erro ao extrair backup do banco original: {err_msg}'}

                fbk_size = os.path.getsize(temp_fbk) / (1024 * 1024)
                logs.append(f"[OK] Backup transportável gerado com sucesso ({fbk_size:.2f} MB).")
                fbk_to_restore = temp_fbk

            # Step 2: Restore into Firebird 5.0 (ODS 13.1)
            logs.append(f"[2/2] Restaurando e atualizando para Firebird 5.0 (ODS 13.1, PageSize {page_size})...")
            restore_cmd = [
                fb5_gbak,
                '-c',            # Create database
                '-v',            # Verbose
                '-page_size', str(page_size),
                '-user', user,
                '-password', password,
                fbk_to_restore,
                target_path
            ]

            fb5_cwd = os.path.dirname(fb5_gbak)
            proc_r = subprocess.run(restore_cmd, capture_output=True, text=True, cwd=fb5_cwd, timeout=300)

            if not os.path.exists(target_path):
                err_msg = proc_r.stderr or proc_r.stdout or 'Falha desconhecida na restauração do Firebird 5.0.'
                return {'success': False, 'error': f'Erro ao restaurar banco no Firebird 5.0: {err_msg}'}

            final_size = os.path.getsize(target_path)
            new_header = cls.read_ods_header(target_path)

            logs.append(f"[OK] Banco Firebird 5.0 gerado com sucesso!")
            logs.append(f"     ODS Atualizado: {new_header.get('ods_string')} ({new_header.get('detected_version')})")
            logs.append(f"     Tamanho Final: {final_size / (1024 * 1024):.2f} MB")

            return {
                'success': True,
                'target_fdb': target_path,
                'filename': os.path.basename(target_path),
                'file_size': final_size,
                'file_size_formatted': f"{final_size / (1024 * 1024):.2f} MB",
                'original_version': header_info.get('detected_version', 'Legado'),
                'original_ods': header_info.get('ods_string', 'N/A'),
                'target_ods': new_header.get('ods_string', '13.1'),
                'target_version': 'Firebird 5.0 (ODS 13.1)',
                'logs': logs,
                'message': f"Banco portado com sucesso para Firebird 5.0 ({final_size / (1024 * 1024):.2f} MB)!"
            }

        except Exception as e:
            return {'success': False, 'error': f'Erro durante a migração: {str(e)}'}
        finally:
            if temp_fbk and os.path.exists(temp_fbk):
                try:
                    os.remove(temp_fbk)
                except Exception:
                    pass
