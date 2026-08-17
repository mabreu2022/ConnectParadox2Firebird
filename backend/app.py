"""
Flask Web Application for Paradox to Firebird Conversion Studio
Provides REST API for table inspection, conversion, sample generation, direct Firebird execution,
1-click .FDB binary database creation & download, CSV Import/Export, and Project Management.
"""

import os
import io
import json
import uuid
import shutil
import zipfile
from datetime import datetime
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename

from .paradox_engine import ParadoxReader, ParadoxWriter
from .firebird_engine import FirebirdEngine, FIREBIRD_RESERVED_WORDS
from .sample_generator import generate_all_samples
from .csv_engine import CSVEngine
from .fb_migrator import FirebirdMigrator
from .diagnostics_engine import DataDiagnosticsEngine
from .relations_engine import SmartRelationsEngine
from .audit_engine import AuditEngine

BASE_DIR = os.environ.get('P2F_BASE_DIR', os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

USER_DATA_DIR = os.environ.get('P2F_USER_DATA_DIR', BASE_DIR)
SAMPLES_DIR = os.path.join(USER_DATA_DIR, 'samples')
UPLOADS_DIR = os.path.join(USER_DATA_DIR, 'uploads')
OUTPUT_DIR = os.path.join(USER_DATA_DIR, 'output')
PROJECTS_FILE = os.path.join(USER_DATA_DIR, 'projects.json')

os.makedirs(SAMPLES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.exists(os.path.join(SAMPLES_DIR, 'CLIENTES.DB')):
    base_samples = os.path.join(BASE_DIR, 'samples')
    if os.path.exists(base_samples) and os.listdir(base_samples):
        for item in os.listdir(base_samples):
            s = os.path.join(base_samples, item)
            d = os.path.join(SAMPLES_DIR, item)
            if not os.path.exists(d):
                shutil.copy2(s, d)
    else:
        generate_all_samples(SAMPLES_DIR)

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path='')

# ─── Project Helpers ─────────────────────────────────────────────────────────

def load_projects():
    """Load projects from JSON persistence file."""
    if os.path.exists(PROJECTS_FILE):
        try:
            with open(PROJECTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_projects(projects):
    """Persist projects list to JSON file."""
    with open(PROJECTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)

def get_project_dir(project_id):
    """Returns the dedicated uploads directory for a given project."""
    return os.path.join(UPLOADS_DIR, project_id)

def scan_db_files(folder_path):
    """Scans a folder and returns list of Paradox table info dicts."""
    found_tables = []
    if not os.path.isdir(folder_path):
        return found_tables
    for f in os.listdir(folder_path):
        if f.upper().endswith('.DB'):
            fpath = os.path.join(folder_path, f)
            try:
                reader = ParadoxReader(fpath)
                found_tables.append({
                    'filename': f,
                    'table_name': reader.table_name or os.path.splitext(f)[0],
                    'file_size': os.path.getsize(fpath),
                    'records': reader.num_records,
                    'fields_count': reader.num_fields,
                    'has_px': reader.px_info.get('exists', False),
                    'primary_keys': reader.primary_keys,
                    'is_sample': False
                })
            except Exception as e:
                found_tables.append({'filename': f, 'error': str(e), 'is_sample': False})
    return found_tables

def count_project_tables(project_id):
    """Returns number of .DB files in the project directory."""
    pdir = get_project_dir(project_id)
    if not os.path.isdir(pdir):
        return 0
    return len([f for f in os.listdir(pdir) if f.upper().endswith('.DB')])

def _resolve_filepath(filename, is_sample=False, project_id=None):
    """Resolves the actual file path given optional project_id or is_sample flag."""
    if project_id:
        fpath = os.path.join(get_project_dir(project_id), filename)
        if os.path.exists(fpath):
            return fpath
    if is_sample:
        fpath = os.path.join(SAMPLES_DIR, filename)
        if os.path.exists(fpath):
            return fpath
    fpath = os.path.join(UPLOADS_DIR, filename)
    if os.path.exists(fpath):
        return fpath
    # Recursive fallback across project directories inside UPLOADS_DIR
    if os.path.isdir(UPLOADS_DIR):
        for root, _, files in os.walk(UPLOADS_DIR):
            for f in files:
                if f.upper() == filename.upper():
                    return os.path.join(root, f)
    for d in [SAMPLES_DIR, UPLOADS_DIR]:
        fpath = os.path.join(d, filename)
        if os.path.exists(fpath):
            return fpath
    return None

# ─── Static Routes ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    response = send_from_directory(FRONTEND_DIR, 'index.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def serve_static(path):
    if path.startswith('api/'):
        return jsonify({'success': False, 'error': f'Endpoint API "/{path}" não encontrado no servidor backend. Certifique-se de reiniciar o servidor (run_server.py).'}), 404
    if os.path.exists(os.path.join(FRONTEND_DIR, path)):
        response = send_from_directory(FRONTEND_DIR, path)
        if path.endswith(('.html', '.js', '.css')):
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response
    response = send_from_directory(FRONTEND_DIR, 'index.html')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response

# ─── Project API ─────────────────────────────────────────────────────────────

@app.route('/api/projects', methods=['GET'])
def list_projects():
    """List all saved projects with their table counts."""
    projects = load_projects()
    result = []
    for p in projects:
        p_copy = dict(p)
        p_copy['table_count'] = count_project_tables(p['id'])
        result.append(p_copy)
    return jsonify({'success': True, 'projects': result})


@app.route('/api/projects', methods=['POST'])
def create_project():
    """Create a new empty project."""
    data = request.json or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'Nome do projeto é obrigatório.'}), 400
    project_id = str(uuid.uuid4())[:8]
    project_dir = get_project_dir(project_id)
    os.makedirs(project_dir, exist_ok=True)
    project = {
        'id': project_id,
        'name': name,
        'folder_path': '',
        'created_at': datetime.now().isoformat(),
        'description': data.get('description', '')
    }
    projects = load_projects()
    projects.append(project)
    save_projects(projects)
    project['table_count'] = 0
    return jsonify({'success': True, 'project': project})


@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    """Delete a project. Optionally deletes associated files."""
    delete_files = request.args.get('delete_files', 'false').lower() == 'true'
    projects = load_projects()
    projects_filtered = [p for p in projects if p['id'] != project_id]
    if len(projects_filtered) == len(projects):
        return jsonify({'success': False, 'error': 'Projeto não encontrado.'}), 404
    save_projects(projects_filtered)
    if delete_files:
        project_dir = get_project_dir(project_id)
        if os.path.isdir(project_dir):
            shutil.rmtree(project_dir)
    return jsonify({'success': True, 'message': 'Projeto removido com sucesso.'})


@app.route('/api/projects/<project_id>/import_folder', methods=['POST'])
def project_import_folder(project_id):
    """Import all Paradox files from a local folder path into the project."""
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)
    if not project:
        return jsonify({'success': False, 'error': 'Projeto não encontrado.'}), 404
    data = request.json or {}
    folder_path = data.get('folder_path', '').strip()
    if not folder_path:
        return jsonify({'success': False, 'error': 'Caminho da pasta não informado.'}), 400
    if not os.path.exists(folder_path):
        return jsonify({'success': False, 'error': f'A pasta "{folder_path}" não existe.'}), 404
    if not os.path.isdir(folder_path):
        return jsonify({'success': False, 'error': f'"{folder_path}" não é uma pasta.'}), 400
    project_dir = get_project_dir(project_id)
    os.makedirs(project_dir, exist_ok=True)
    try:
        for f in os.listdir(folder_path):
            src = os.path.join(folder_path, f)
            if os.path.isfile(src) and f.upper().endswith(('.DB', '.PX', '.MB', '.VAL', '.TV', '.FAM')):
                shutil.copy2(src, os.path.join(project_dir, f))
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao copiar arquivos: {str(e)}'}), 500
    project['folder_path'] = folder_path
    save_projects(projects)
    found_tables = scan_db_files(project_dir)
    if not found_tables:
        return jsonify({'success': False, 'error': f'Nenhuma tabela Paradox (.DB) encontrada na pasta "{folder_path}".'}), 404
    return jsonify({
        'success': True, 'project_id': project_id, 'folder_path': folder_path,
        'tables': found_tables, 'count': len(found_tables),
        'message': f'{len(found_tables)} tabelas importadas com sucesso!'
    })


@app.route('/api/projects/<project_id>/upload_files', methods=['POST'])
def project_upload_files(project_id):
    """Upload individual Paradox files (.db, .px, .mb) into the project."""
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)
    if not project:
        return jsonify({'success': False, 'error': 'Projeto não encontrado.'}), 404
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'Nenhum arquivo enviado.'}), 400
    project_dir = get_project_dir(project_id)
    os.makedirs(project_dir, exist_ok=True)
    files = request.files.getlist('files')
    uploaded = []
    for file in files:
        if file and file.filename:
            # When using webkitdirectory the browser sends paths like "FolderName/FILE.DB"
            # Extract only the basename before applying secure_filename to avoid "FolderName_FILE.DB"
            raw_basename = os.path.basename(file.filename.replace('\\', '/'))
            filename = secure_filename(raw_basename)
            if not filename:
                continue
            save_path = os.path.join(project_dir, filename)
            file.save(save_path)
            if filename.upper().endswith('.DB'):
                try:
                    reader = ParadoxReader(save_path)
                    uploaded.append({
                        'filename': filename,
                        'table_name': reader.table_name or os.path.splitext(filename)[0],
                        'file_size': os.path.getsize(save_path),
                        'records': reader.num_records, 'fields_count': reader.num_fields,
                        'has_px': reader.px_info.get('exists', False),
                        'primary_keys': reader.primary_keys, 'is_sample': False
                    })
                except Exception as e:
                    uploaded.append({'filename': filename, 'error': str(e), 'is_sample': False})
    return jsonify({'success': True, 'uploaded': uploaded})


@app.route('/api/projects/<project_id>/tables', methods=['GET'])
def project_list_tables(project_id):
    """List all Paradox tables in a project."""
    projects = load_projects()
    project = next((p for p in projects if p['id'] == project_id), None)
    if not project:
        return jsonify({'success': False, 'error': 'Projeto não encontrado.'}), 404
    project_dir = get_project_dir(project_id)
    tables = scan_db_files(project_dir)
    return jsonify({'success': True, 'tables': tables, 'project': project})


# ─── Samples & Legacy Upload API ─────────────────────────────────────────────

@app.route('/api/samples', methods=['GET'])
def list_samples():
    """List all available Paradox tables from samples, uploads, or a project directory."""
    source = request.args.get('source', 'samples')
    project_id = request.args.get('project_id', None)
    if project_id:
        folder = get_project_dir(project_id)
    elif source == 'uploads':
        folder = UPLOADS_DIR
    else:
        folder = SAMPLES_DIR
    if not os.path.isdir(folder):
        return jsonify({'success': True, 'tables': [], 'source': source})
    sample_files = [f for f in os.listdir(folder) if f.upper().endswith('.DB') and os.path.isfile(os.path.join(folder, f))]
    result = []
    for f in sample_files:
        fpath = os.path.join(folder, f)
        try:
            reader = ParadoxReader(fpath)
            result.append({
                'filename': f,
                'table_name': reader.table_name or f.replace('.DB', ''),
                'file_size': os.path.getsize(fpath),
                'records': reader.num_records,
                'fields_count': reader.num_fields,
                'has_px': reader.px_info.get('exists', False),
                'primary_keys': reader.primary_keys,
                'is_sample': (source == 'samples' and not project_id)
            })
        except Exception as e:
            result.append({'filename': f, 'error': str(e), 'is_sample': (source == 'samples' and not project_id)})
    return jsonify({'success': True, 'tables': result, 'source': source})


@app.route('/api/generate_samples', methods=['POST'])
def create_samples():
    """Regenerates all sample Paradox tables."""
    try:
        samples = generate_all_samples(SAMPLES_DIR)
        return jsonify({'success': True, 'message': 'Bancos de teste Paradox gerados com sucesso!', 'tables': list(samples.keys())})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/upload', methods=['POST'])
def upload_files():
    """Uploads one or multiple Paradox files (.db, .mb, .px) or CSVs (legacy, no project)."""
    if 'files' not in request.files:
        return jsonify({'success': False, 'error': 'Nenhum arquivo enviado.'}), 400
    files = request.files.getlist('files')
    uploaded_tables = []
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            save_path = os.path.join(UPLOADS_DIR, filename)
            file.save(save_path)
            if filename.upper().endswith('.DB'):
                try:
                    reader = ParadoxReader(save_path)
                    uploaded_tables.append({
                        'filename': filename,
                        'table_name': reader.table_name or os.path.splitext(filename)[0],
                        'file_size': os.path.getsize(save_path),
                        'records': reader.num_records, 'fields_count': reader.num_fields,
                        'has_px': reader.px_info.get('exists', False),
                        'primary_keys': reader.primary_keys, 'is_sample': False
                    })
                except Exception as e:
                    uploaded_tables.append({'filename': filename, 'error': str(e), 'is_sample': False})
            elif filename.upper().endswith('.CSV'):
                try:
                    with open(save_path, 'r', encoding='utf-8', errors='replace') as f_csv:
                        content = f_csv.read()
                    tbl_name = os.path.splitext(filename)[0]
                    res = CSVEngine.import_csv_to_paradox(content, tbl_name, UPLOADS_DIR)
                    uploaded_tables.append({
                        'filename': res['filename'], 'table_name': res['table_name'],
                        'file_size': os.path.getsize(res['db_path']),
                        'records': res['records_count'], 'fields_count': res['fields_count'],
                        'has_px': res['has_px'], 'is_sample': False
                    })
                except Exception as e:
                    uploaded_tables.append({'filename': filename, 'error': f'Erro ao processar CSV: {str(e)}', 'is_sample': False})
    return jsonify({'success': True, 'uploaded': uploaded_tables})


@app.route('/api/scan_folder', methods=['POST'])
def scan_folder():
    """Scans a local directory for Paradox (.DB/.PX/.MB) and .CSV files (legacy)."""
    data = request.json or {}
    folder_path = data.get('folder_path', '').strip()
    if not folder_path:
        return jsonify({'success': False, 'error': 'Caminho da pasta não informado.'}), 400
    if not os.path.exists(folder_path):
        return jsonify({'success': False, 'error': f'A pasta "{folder_path}" não existe ou não pôde ser acessada.'}), 404
    if not os.path.isdir(folder_path):
        return jsonify({'success': False, 'error': f'"{folder_path}" não é uma pasta válida.'}), 400
    try:
        found_tables = []
        files = os.listdir(folder_path)
        for f in files:
            src = os.path.join(folder_path, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(UPLOADS_DIR, f))
        for f in files:
            if f.upper().endswith('.DB'):
                save_path = os.path.join(UPLOADS_DIR, f)
                try:
                    reader = ParadoxReader(save_path)
                    found_tables.append({
                        'filename': f, 'table_name': reader.table_name or os.path.splitext(f)[0],
                        'file_size': os.path.getsize(save_path), 'records': reader.num_records,
                        'fields_count': reader.num_fields, 'has_px': reader.px_info.get('exists', False),
                        'primary_keys': reader.primary_keys, 'is_sample': False
                    })
                except Exception as e:
                    found_tables.append({'filename': f, 'error': str(e), 'is_sample': False})
            elif f.upper().endswith('.CSV'):
                try:
                    with open(os.path.join(folder_path, f), 'r', encoding='utf-8', errors='replace') as fc:
                        content = fc.read()
                    res = CSVEngine.import_csv_to_paradox(content, os.path.splitext(f)[0], UPLOADS_DIR)
                    found_tables.append({
                        'filename': res['filename'], 'table_name': res['table_name'],
                        'file_size': os.path.getsize(res['db_path']), 'records': res['records_count'],
                        'fields_count': res['fields_count'], 'has_px': res['has_px'], 'is_sample': False
                    })
                except Exception:
                    pass
        if not found_tables:
            return jsonify({'success': False, 'error': f'Nenhuma tabela Paradox (.DB) ou planilha (.CSV) foi encontrada na pasta "{folder_path}".'}), 404
        return jsonify({'success': True, 'folder_path': folder_path, 'count': len(found_tables),
                        'tables': found_tables, 'message': f'{len(found_tables)} tabelas carregadas com sucesso da pasta!'})
    except Exception as e:
        return jsonify({'success': False, 'error': f'Erro ao ler pasta: {str(e)}'}), 500


# ─── Inspect, Convert, Generate (project-aware) ──────────────────────────────

@app.route('/api/inspect', methods=['POST'])
def inspect_table():
    """Inspects metadata and returns sample data preview of a table."""
    data = request.json or {}
    filename = data.get('filename')
    is_sample = data.get('is_sample', False)
    project_id = data.get('project_id', None)
    limit = int(data.get('limit', 50))
    encoding = data.get('encoding', 'latin1')
    if not filename:
        return jsonify({'success': False, 'error': 'Nome do arquivo não especificado.'}), 400
    filepath = _resolve_filepath(filename, is_sample, project_id)
    if not filepath:
        return jsonify({'success': False, 'error': f'Arquivo {filename} não encontrado.'}), 404
    try:
        reader = ParadoxReader(filepath, encoding=encoding)
        fields = [f.to_dict() for f in reader.fields]
        records = reader.read_all_records(limit=limit)
        json_records = []
        for r in records:
            row_dict = {}
            for k, v in r.items():
                row_dict[k] = v.isoformat() if hasattr(v, 'isoformat') else v
            json_records.append(row_dict)
        return jsonify({
            'success': True, 'filename': filename,
            'table_name': reader.table_name or os.path.splitext(filename)[0],
            'record_size': reader.record_size, 'num_records': reader.num_records,
            'num_fields': reader.num_fields, 'fields': fields, 'px_info': reader.px_info,
            'primary_keys': reader.primary_keys,
            'preview_records': json_records, 'total_preview': len(json_records)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/convert', methods=['POST'])
def convert_table():
    """Converts Paradox table to Firebird SQL script or executes directly."""
    data = request.json or {}
    filename = data.get('filename')
    is_sample = data.get('is_sample', False)
    project_id = data.get('project_id', None)
    custom_mappings = data.get('mappings', {})
    firebird_version = data.get('firebird_version', '3.0')
    direct_execute = data.get('direct_execute', False)
    conn_params = data.get('connection_params', {})
    if not filename:
        return jsonify({'success': False, 'error': 'Nome do arquivo não especificado.'}), 400
    filepath = _resolve_filepath(filename, is_sample, project_id)
    if not filepath:
        return jsonify({'success': False, 'error': f'Arquivo {filename} não encontrado.'}), 404
    try:
        conversion_result = FirebirdEngine.convert_paradox_file(filepath, custom_mappings=custom_mappings, firebird_version=firebird_version)
        direct_result = None
        if direct_execute and conn_params:
            direct_result = FirebirdEngine.execute_direct_firebird(conn_params, conversion_result['sql_script'])
        return jsonify({
            'success': True, 'table_name': conversion_result['table_name'],
            'record_count': conversion_result['record_count'], 'field_count': conversion_result['field_count'],
            'sql_script': conversion_result['sql_script'], 'direct_result': direct_result
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/convert_all', methods=['POST'])
def convert_all_tables():
    """Converts multiple or all available tables into a consolidated Firebird SQL script."""
    data = request.json or {}
    filenames = data.get('filenames', [])
    firebird_version = data.get('firebird_version', '3.0')
    project_id = data.get('project_id', None)
    if not filenames:
        search_dir = get_project_dir(project_id) if project_id else SAMPLES_DIR
        if os.path.isdir(search_dir):
            filenames = [f for f in os.listdir(search_dir) if f.upper().endswith('.DB')]
    combined_sql = [
        "/* " + "="*70 + " */",
        "/* SCRIPT COMPLETO DE MIGRAÇÃO PARADOX -> FIREBIRD                    */",
        f"/* Versão Alvo Firebird: {firebird_version}                                     */",
        "/* " + "="*70 + " */\n"
    ]
    summary = []
    for fn in filenames:
        filepath = _resolve_filepath(fn, False, project_id)
        if filepath and os.path.exists(filepath):
            try:
                res = FirebirdEngine.convert_paradox_file(filepath, firebird_version=firebird_version)
                combined_sql.append(res['sql_script'])
                combined_sql.append("\n/* " + "-"*70 + " */\n")
                summary.append({'filename': fn, 'records': res['record_count'], 'fields': res['field_count']})
            except Exception as e:
                combined_sql.append(f"/* Erro ao converter {fn}: {str(e)} */\n")
    return jsonify({'success': True, 'tables_converted': len(summary), 'summary': summary, 'sql_script': "\n".join(combined_sql)})


@app.route('/api/generate_fdb', methods=['POST'])
def generate_fdb_database():
    """Generates a complete binary .FDB Firebird database file on disk."""
    data = request.json or {}
    filenames = data.get('filenames', [])
    fdb_name = data.get('fdb_name', 'MIGRACAO_FIREBIRD.FDB')
    firebird_version = data.get('firebird_version', '3.0')
    charset = data.get('charset', 'UTF8')
    page_size = int(data.get('page_size', 8192))
    project_id = data.get('project_id', None)
    if not fdb_name.upper().endswith('.FDB'):
        fdb_name += '.FDB'
    if not filenames:
        if project_id:
            pdir = get_project_dir(project_id)
            if os.path.isdir(pdir):
                filenames = [f for f in os.listdir(pdir) if f.upper().endswith('.DB')]
        if not filenames:
            filenames = [f for f in os.listdir(SAMPLES_DIR) if f.upper().endswith('.DB')]
    combined_sql = []
    summary = []
    for fn in filenames:
        filepath = _resolve_filepath(fn, False, project_id)
        if filepath and os.path.exists(filepath):
            try:
                res = FirebirdEngine.convert_paradox_file(filepath, firebird_version=firebird_version)
                combined_sql.append(res['sql_script'])
                summary.append({'filename': fn, 'records': res['record_count']})
            except Exception:
                pass
    if not combined_sql:
        return jsonify({'success': False, 'error': 'Nenhuma tabela Paradox encontrada para converter.'}), 400
    full_sql = "\n".join(combined_sql)
    target_fdb = os.path.join(OUTPUT_DIR, fdb_name)
    result = FirebirdEngine.create_fdb_database(output_fdb_path=target_fdb, sql_script=full_sql, charset=charset, page_size=page_size)
    if result.get('success'):
        return jsonify({
            'success': True, 'fdb_name': fdb_name,
            'download_url': f'/api/download_fdb?filename={fdb_name}',
            'file_size': result.get('file_size'), 'file_size_formatted': result.get('file_size_formatted'),
            'tables_converted': len(summary), 'summary': summary,
            'message': f"Banco {fdb_name} gerado com sucesso ({result.get('file_size_formatted')}) contendo {len(summary)} tabelas!"
        })
    else:
        return jsonify({'success': False, 'error': result.get('error')}), 500


@app.route('/api/download_fdb', methods=['GET'])
def download_fdb():
    """Downloads the generated .FDB database file."""
    fdb_name = secure_filename(request.args.get('filename', 'MIGRACAO_FIREBIRD.FDB'))
    if not fdb_name.upper().endswith('.FDB'):
        fdb_name += '.FDB'
    fpath = os.path.join(OUTPUT_DIR, fdb_name)
    if os.path.exists(fpath):
        return send_file(fpath, as_attachment=True, download_name=fdb_name, mimetype='application/octet-stream')
    return jsonify({'error': 'Arquivo FDB não encontrado. Gere o banco primeiro.'}), 404


@app.route('/api/export_csv', methods=['GET'])
def export_single_csv():
    """Exports a single Paradox table to CSV format."""
    filename = request.args.get('filename')
    is_sample = request.args.get('is_sample', 'false').lower() == 'true'
    project_id = request.args.get('project_id', None)
    delimiter = request.args.get('delimiter', ';')
    if not filename:
        return jsonify({'error': 'Nome do arquivo não informado'}), 400
    filepath = _resolve_filepath(filename, is_sample, project_id)
    if not filepath:
        return jsonify({'error': 'Arquivo não encontrado'}), 404
    try:
        csv_bytes = CSVEngine.export_table_to_csv(filepath, delimiter=delimiter)
        csv_name = f"{os.path.splitext(filename)[0]}.csv"
        return send_file(io.BytesIO(csv_bytes), as_attachment=True, download_name=csv_name, mimetype='text/csv; charset=utf-8')
    except Exception as e:
        return jsonify({'error': f'Erro ao exportar CSV: {str(e)}'}), 500


@app.route('/api/export_all_csv_zip', methods=['GET'])
def export_all_csv_zip():
    """Exports all available tables as a ZIP containing CSV files."""
    delimiter = request.args.get('delimiter', ';')
    project_id = request.args.get('project_id', None)
    buffer = io.BytesIO()
    search_dirs = [get_project_dir(project_id)] if project_id else [SAMPLES_DIR, UPLOADS_DIR]
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.upper().endswith('.DB'):
                    try:
                        c_bytes = CSVEngine.export_table_to_csv(os.path.join(d, f), delimiter=delimiter)
                        zip_f.writestr(f"{os.path.splitext(f)[0]}.csv", c_bytes)
                    except Exception:
                        pass
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='tabelas_exportadas_csv.zip', mimetype='application/zip')


@app.route('/api/import_csv', methods=['POST'])
def import_csv():
    """Directly imports CSV data or uploaded CSV file into a Paradox table."""
    table_name = request.form.get('table_name', 'TABELA_CSV')
    delimiter = request.form.get('delimiter', None)
    project_id = request.form.get('project_id', None)
    target_dir = get_project_dir(project_id) if project_id else UPLOADS_DIR
    os.makedirs(target_dir, exist_ok=True)
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        table_name = table_name or os.path.splitext(file.filename)[0]
        content = file.read().decode('utf-8', errors='replace')
    else:
        data = request.json or {}
        content = data.get('csv_content', '')
        table_name = data.get('table_name', table_name)
        delimiter = data.get('delimiter', delimiter)
        if data.get('project_id'):
            target_dir = get_project_dir(data['project_id'])
            os.makedirs(target_dir, exist_ok=True)
    if not content:
        return jsonify({'success': False, 'error': 'Conteúdo CSV vazio.'}), 400
    try:
        res = CSVEngine.import_csv_to_paradox(csv_content=content, table_name=table_name, output_dir=target_dir, delimiter=delimiter)
        return jsonify({
            'success': True, 'filename': res['filename'], 'table_name': res['table_name'],
            'records_count': res['records_count'], 'fields_count': res['fields_count'],
            'message': f"CSV importado com sucesso! Criada tabela {res['filename']} com {res['records_count']} registros."
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download_sql', methods=['POST'])
def download_sql():
    """Download SQL content as a .sql file."""
    data = request.json or {}
    sql_text = data.get('sql_text', '')
    filename = data.get('filename', 'migracao_firebird.sql')
    if not filename.endswith('.sql'):
        filename += '.sql'
    buffer = io.BytesIO(sql_text.encode('utf-8'))
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/sql')


@app.route('/api/download_sample/<filename>', methods=['GET'])
def download_sample_file(filename):
    """Download single sample Paradox .DB file."""
    filename = secure_filename(filename)
    fpath = os.path.join(SAMPLES_DIR, filename)
    if os.path.exists(fpath):
        return send_file(fpath, as_attachment=True, download_name=filename)
    return jsonify({'error': 'Arquivo não encontrado'}), 404


@app.route('/api/download_samples_zip', methods=['GET'])
def download_samples_zip():
    """Download all sample Paradox tables bundled in a .zip archive."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_f:
        for root, _, files in os.walk(SAMPLES_DIR):
            for file in files:
                if file.upper().endswith(('.DB', '.PX')):
                    file_path = os.path.join(root, file)
                    zip_f.write(file_path, arcname=file)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name='bancos_paradox_exemplos.zip', mimetype='application/zip')
# ─── Firebird 2.5 / 3.0 -> 5.0 Migration API ─────────────────────────────────

FB_MIGRATE_DIR = os.path.join(USER_DATA_DIR, 'fb_migrations')
os.makedirs(FB_MIGRATE_DIR, exist_ok=True)


@app.route('/api/fb_migrate/inspect', methods=['POST'])
def inspect_fb_database():
    """Inspects an uploaded or local Firebird database/backup file."""
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        orig_name = os.path.basename(file.filename)
        safe_name = secure_filename(orig_name) or 'database.fdb'
        dest_path = os.path.join(FB_MIGRATE_DIR, f"{uuid.uuid4().hex[:8]}_{safe_name}")
        file.save(dest_path)
        target_path = dest_path
    else:
        data = request.json or {}
        local_path = data.get('local_path', '').strip()
        if not local_path or not os.path.exists(local_path):
            return jsonify({'success': False, 'error': 'Informe um arquivo Firebird válido ou selecione um arquivo.'}), 400
        target_path = local_path

    info = FirebirdMigrator.read_ods_header(target_path)
    if not info.get('valid'):
        return jsonify({'success': False, 'error': info.get('error', 'Arquivo inválido.')}), 400

    info['filepath'] = target_path
    info['filename'] = os.path.basename(target_path)
    return jsonify({'success': True, 'info': info})


@app.route('/api/fb_migrate/convert', methods=['POST'])
def convert_fb_to_50():
    """Migrates the inspected Firebird database to Firebird 5.0 (ODS 13.1)."""
    data = request.json or {}
    source_path = data.get('filepath', '').strip()
    page_size = int(data.get('page_size', 8192))
    charset = data.get('charset', 'UTF8')
    custom_name = data.get('target_name', '').strip()

    if not source_path or not os.path.exists(source_path):
        return jsonify({'success': False, 'error': 'Arquivo de origem não encontrado no servidor.'}), 400

    base_name = os.path.splitext(os.path.basename(source_path))[0]
    if custom_name:
        out_name = custom_name if custom_name.upper().endswith('.FDB') else f"{custom_name}.FDB"
    else:
        out_name = f"{base_name}_FB50.FDB"

    out_name = secure_filename(out_name)
    if not out_name.upper().endswith('.FDB'):
        out_name += '.FDB'

    target_path = os.path.join(OUTPUT_DIR, out_name)

    result = FirebirdMigrator.migrate_database_to_fb5(
        source_filepath=source_path,
        target_filepath=target_path,
        page_size=page_size,
        charset=charset
    )

    if result.get('success'):
        result['download_url'] = f"/api/fb_migrate/download?filename={out_name}"
        return jsonify(result)
    else:
        return jsonify(result), 500


@app.route('/api/fb_migrate/download', methods=['GET'])
def download_migrated_fb():
    """Downloads the migrated Firebird 5.0 .FDB file."""
    filename = secure_filename(request.args.get('filename', ''))
    if not filename.upper().endswith('.FDB'):
        filename += '.FDB'
    fpath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(fpath):
        return send_file(fpath, as_attachment=True, download_name=filename, mimetype='application/octet-stream')
    return jsonify({'error': 'Arquivo Firebird 5.0 não encontrado.'}), 404


# ─── Documentation Routes ─────────────────────────────────────────────────────

DOCS_DIR = os.path.join(BASE_DIR, 'documentacao')

@app.route('/docs')
@app.route('/manual')
def docs_index():
    """Serves the user manual index HTML page."""
    return send_from_directory(DOCS_DIR, 'index.html')

@app.route('/docs/<path:filename>')
def docs_static(filename):
    """Serves documentation static files."""
    return send_from_directory(DOCS_DIR, filename)


# ─── Data Diagnostics & Cleansing API ─────────────────────────────────────────

@app.route('/api/diagnostics/run', methods=['POST'])
def run_diagnostics():
    """Runs data diagnostics and health scoring on single table or entire folder/project."""
    data = request.json or {}
    filename = data.get('filename')
    is_sample = data.get('is_sample', False)
    project_id = data.get('project_id')
    source = data.get('source', 'samples')

    if filename:
        fpath = _resolve_filepath(filename, is_sample=(source == 'samples' or is_sample), project_id=project_id)
        if not fpath or not os.path.exists(fpath):
            return jsonify({'success': False, 'error': f'Arquivo {filename} não encontrado.'}), 404
        report = DataDiagnosticsEngine.inspect_table(fpath)
        return jsonify({'success': True, 'report': report})
    else:
        target_dir = SAMPLES_DIR if source == 'samples' else (get_project_dir(project_id) if project_id else UPLOADS_DIR)
        report = DataDiagnosticsEngine.inspect_directory(target_dir)
        return jsonify({'success': True, 'report': report})


@app.route('/api/diagnostics/fix', methods=['POST'])
def fix_diagnostics():
    """Applies automated sanitization and data cleansing."""
    data = request.json or {}
    filename = data.get('filename')
    is_sample = data.get('is_sample', False)
    project_id = data.get('project_id')
    options = data.get('options', {})

    if not filename:
        return jsonify({'success': False, 'error': 'Nome do arquivo obrigatório.'}), 400

    fpath = _resolve_filepath(filename, is_sample=is_sample, project_id=project_id)
    if not fpath or not os.path.exists(fpath):
        return jsonify({'success': False, 'error': f'Arquivo {filename} não encontrado.'}), 404

    try:
        reader = ParadoxReader(fpath)
        records = reader.read_all_records()
        clean_records, stats = DataDiagnosticsEngine.cleanse_records(
            records, reader.fields, reader.primary_keys, options
        )
        return jsonify({
            'success': True,
            'stats': stats,
            'cleaned_count': len(clean_records),
            'sample_cleaned': clean_records[:10],
            'message': f"Higienização concluída: {stats.get('invalid_dates_fixed',0)} datas corrigidas, {stats.get('null_pks_fixed',0)} PKs ajustadas, {stats.get('strings_trimmed',0)} textos formatados."
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── Smart Foreign Keys & Relational Engine API ────────────────────────────────

@app.route('/api/relations/detect', methods=['POST'])
def detect_relations():
    """Detects foreign key candidates across all loaded tables."""
    data = request.json or {}
    source = data.get('source', 'samples')
    project_id = data.get('project_id')

    target_dir = SAMPLES_DIR if source == 'samples' else (get_project_dir(project_id) if project_id else UPLOADS_DIR)
    tables_data = []

    if os.path.isdir(target_dir):
        for f in os.listdir(target_dir):
            if f.upper().endswith('.DB'):
                fpath = os.path.join(target_dir, f)
                try:
                    reader = ParadoxReader(fpath)
                    tables_data.append({
                        'filename': f,
                        'table_name': os.path.splitext(f)[0],
                        'fields': [fld.to_dict() for fld in reader.fields],
                        'primary_keys': reader.primary_keys,
                        'records_count': reader.num_records
                    })
                except Exception:
                    pass

    detected = SmartRelationsEngine.detect_relations(tables_data)
    return jsonify({
        'success': True,
        'tables_count': len(tables_data),
        'relations_count': len(detected),
        'relations': detected
    })


@app.route('/api/relations/validate', methods=['POST'])
def validate_relation_orphans():
    """Validates if a specific detected foreign key has orphaned records."""
    data = request.json or {}
    relation = data.get('relation')
    source = data.get('source', 'samples')
    project_id = data.get('project_id')

    if not relation:
        return jsonify({'success': False, 'error': 'Objeto de relação obrigatório.'}), 400

    c_file = f"{relation['child_table']}.DB"
    p_file = f"{relation['parent_table']}.DB"

    c_path = _resolve_filepath(c_file, is_sample=(source == 'samples'), project_id=project_id)
    p_path = _resolve_filepath(p_file, is_sample=(source == 'samples'), project_id=project_id)

    if not c_path or not p_path:
        return jsonify({'success': False, 'error': 'Arquivos das tabelas pai/filha não encontrados.'}), 404

    try:
        c_reader = ParadoxReader(c_path)
        p_reader = ParadoxReader(p_path)
        c_recs = c_reader.read_all_records()
        p_recs = p_reader.read_all_records()

        val_result = SmartRelationsEngine.validate_orphans(relation, c_recs, p_recs)
        return jsonify({'success': True, 'validation': val_result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/relations/generate-ddl', methods=['POST'])
def generate_relations_ddl():
    """Generates ALTER TABLE ADD CONSTRAINT FK_... DDL statements for selected relations."""
    data = request.json or {}
    relations = data.get('relations', [])
    on_delete = data.get('on_delete', 'NO ACTION')
    on_update = data.get('on_update', 'CASCADE')

    ddl = SmartRelationsEngine.generate_foreign_keys_ddl(relations, on_delete=on_delete, on_update=on_update)
    return jsonify({'success': True, 'ddl': ddl})


# ─── Live Remote Firebird & Query Runner API ───────────────────────────────────

@app.route('/api/firebird/test-connection', methods=['POST'])
def test_fb_connection():
    """Tests TCP/IP connection to a Firebird server."""
    data = request.json or {}
    res = FirebirdEngine.test_connection(data)
    status_code = 200 if res.get('success') else 400
    return jsonify(res), status_code


@app.route('/api/firebird/query-exec', methods=['POST'])
def exec_firebird_query():
    """Executes a SQL query on a local FDB file or remote Firebird database."""
    data = request.json or {}
    query = data.get('query', '').strip()
    database = data.get('database', '').strip()
    user = data.get('user', 'SYSDBA')
    password = data.get('password', 'masterkey')

    if not database:
        sample_fdb = os.path.join(OUTPUT_DIR, 'PARADOX_MIGRATED.FDB')
        if os.path.exists(sample_fdb):
            database = sample_fdb
        else:
            fdb_files = [f for f in os.listdir(OUTPUT_DIR) if f.upper().endswith('.FDB')]
            if fdb_files:
                database = os.path.join(OUTPUT_DIR, fdb_files[0])
            else:
                # Check root directory for test databases
                root_fdbs = [f for f in os.listdir(BASE_DIR) if f.upper().endswith('.FDB')]
                if root_fdbs:
                    database = os.path.join(BASE_DIR, root_fdbs[0])
                else:
                    return jsonify({'success': False, 'error': 'Nenhum banco .FDB encontrado. Gere o banco .FDB primeiro ou informe o caminho do arquivo.'}), 400

    res = FirebirdEngine.execute_query(database, query, user=user, password=password)
    return jsonify(res)


@app.route('/api/firebird/live-migrate', methods=['POST'])
def live_migrate_firebird():
    """Executes live migration directly to an existing Firebird database over TCP/IP."""
    data = request.json or {}
    conn_params = data.get('connection', {})
    sql_script = data.get('sql_script', '')

    if not sql_script:
        return jsonify({'success': False, 'error': 'Script SQL vazio.'}), 400

    res = FirebirdEngine.execute_direct_firebird(conn_params, sql_script)
    status_code = 200 if res.get('success') else 500
    return jsonify(res), status_code


# ─── Data Reconciliation & Audit Report API ───────────────────────────────────

@app.route('/api/audit/reconcile', methods=['POST'])
def reconcile_audit():
    """Performs reconciliation audit comparing source Paradox tables vs target."""
    data = request.json or {}
    source = data.get('source', 'samples')
    project_id = data.get('project_id')
    duration = float(data.get('duration_seconds', 0.0))
    mode = data.get('migration_mode', 'FDB_LOCAL')

    target_dir = SAMPLES_DIR if source == 'samples' else (get_project_dir(project_id) if project_id else UPLOADS_DIR)
    source_tables = []

    if os.path.isdir(target_dir):
        for f in os.listdir(target_dir):
            if f.upper().endswith('.DB'):
                fpath = os.path.join(target_dir, f)
                try:
                    reader = ParadoxReader(fpath)
                    recs = reader.read_all_records()
                    fnames = [fld.name for fld in reader.fields]
                    checksums = AuditEngine.calculate_numeric_checksums(recs, fnames)
                    source_tables.append({
                        'filename': f,
                        'table_name': os.path.splitext(f)[0],
                        'record_count': len(recs),
                        'field_count': len(reader.fields),
                        'has_px': reader.px_info.get('exists', False),
                        'checksums': checksums
                    })
                except Exception:
                    pass

    audit_summary = AuditEngine.generate_reconciliation_summary(
        source_tables, duration_seconds=duration, migration_mode=mode
    )
    return jsonify({'success': True, 'audit': audit_summary})


@app.route('/api/audit/report', methods=['POST'])
def export_audit_html_report():
    """Generates standalone HTML audit report for printing/download."""
    data = request.json or {}
    audit_data = data.get('audit')
    if not audit_data:
        return jsonify({'success': False, 'error': 'Dados de auditoria obrigatórios.'}), 400

    html = AuditEngine.generate_html_report(audit_data)
    return jsonify({'success': True, 'html': html})


# ─── Reserved Words & Schema API ──────────────────────────────────────────────

@app.route('/api/schema/reserved-words', methods=['GET'])
def get_reserved_words():
    """Returns list of Firebird reserved words."""
    return jsonify({'success': True, 'reserved_words': sorted(list(FIREBIRD_RESERVED_WORDS))})


if __name__ == '__main__':
    print("Iniciando Paradox2Firebird Studio em http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
