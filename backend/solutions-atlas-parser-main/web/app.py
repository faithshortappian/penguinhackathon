"""Simple Flask web interface for Appian Parser."""

import os
import json
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from appian_parser.cli import dump_package
from appian_parser.domain.models import DumpOptions

app = Flask(__name__, static_folder='static')

# Configuration
UPLOAD_FOLDER = Path(__file__).parent / 'uploads'
UPLOAD_FOLDER.mkdir(exist_ok=True)


def get_next_job_id() -> int:
    """Get the next sequential job ID."""
    existing = [int(d.name) for d in UPLOAD_FOLDER.iterdir() if d.is_dir() and d.name.isdigit()]
    return max(existing, default=0) + 1


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/upload', methods=['POST'])
def upload_and_process():
    """Upload a ZIP file and process it."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if not file.filename or not file.filename.endswith('.zip'):
        return jsonify({'error': 'Please upload a ZIP file'}), 400
    
    # Create job folder
    job_id = get_next_job_id()
    job_folder = UPLOAD_FOLDER / str(job_id)
    job_folder.mkdir(exist_ok=True)
    
    # Save uploaded file
    zip_path = job_folder / file.filename
    file.save(zip_path)
    
    # Process the package
    output_dir = job_folder / 'output'
    
    try:
        options = DumpOptions(
            pretty=True,
            locale=request.form.get('locale', 'en-US'),
            include_dependencies=True,
        )
        
        result = dump_package(str(zip_path), str(output_dir), options)
        
        return jsonify({
            'job_id': job_id,
            'filename': file.filename,
            'objects_parsed': result.objects_parsed,
            'errors_count': result.errors_count,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'job_id': job_id}), 500


@app.route('/api/jobs')
def list_jobs():
    """List all processed jobs."""
    jobs = []
    for d in sorted(UPLOAD_FOLDER.iterdir(), key=lambda x: int(x.name) if x.name.isdigit() else 0, reverse=True):
        if d.is_dir() and d.name.isdigit():
            manifest_path = d / 'output' / 'app_overview.json'
            if manifest_path.exists():
                with open(manifest_path) as f:
                    overview = json.load(f)
                jobs.append({
                    'job_id': int(d.name),
                    'filename': overview.get('package_info', {}).get('filename', 'Unknown'),
                    'objects_parsed': overview.get('package_info', {}).get('total_parsed_objects', 0),
                    'parsed_at': overview.get('_metadata', {}).get('generated_at', ''),
                })
    return jsonify(jobs)


@app.route('/api/jobs/<int:job_id>/files')
def list_job_files(job_id: int):
    """List all output files for a job."""
    output_dir = UPLOAD_FOLDER / str(job_id) / 'output'
    if not output_dir.exists():
        return jsonify({'error': 'Job not found'}), 404
    
    files = []
    for f in output_dir.rglob('*.json'):
        rel_path = f.relative_to(output_dir)
        files.append({
            'path': str(rel_path),
            'name': f.name,
            'size': f.stat().st_size,
        })
    
    return jsonify(sorted(files, key=lambda x: x['path']))


@app.route('/api/jobs/<int:job_id>/file')
def get_file_content(job_id: int):
    """Get content of a specific file."""
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'No file path provided'}), 400
    
    full_path = UPLOAD_FOLDER / str(job_id) / 'output' / file_path
    if not full_path.exists() or not full_path.is_file():
        return jsonify({'error': 'File not found'}), 404
    
    # Security check - ensure path is within job folder
    try:
        full_path.resolve().relative_to((UPLOAD_FOLDER / str(job_id)).resolve())
    except ValueError:
        return jsonify({'error': 'Invalid path'}), 400
    
    with open(full_path) as f:
        content = json.load(f)
    
    return jsonify(content)


@app.route('/api/jobs/<int:job_id>/download')
def download_file(job_id: int):
    """Download a specific file."""
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'No file path provided'}), 400
    
    full_path = UPLOAD_FOLDER / str(job_id) / 'output' / file_path
    if not full_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(full_path, as_attachment=True)


@app.route('/api/jobs/<int:job_id>/download-all')
def download_all(job_id: int):
    """Download all output as a ZIP file."""
    output_dir = UPLOAD_FOLDER / str(job_id) / 'output'
    if not output_dir.exists():
        return jsonify({'error': 'Job not found'}), 404
    
    zip_path = UPLOAD_FOLDER / str(job_id) / f'output_{job_id}.zip'
    shutil.make_archive(str(zip_path.with_suffix('')), 'zip', output_dir)
    
    return send_file(zip_path, as_attachment=True, download_name=f'appian_parsed_{job_id}.zip')


if __name__ == '__main__':
    app.run(debug=True, port=5002)
