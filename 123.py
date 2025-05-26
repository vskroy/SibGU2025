import os
import uuid
import hashlib
import json
from datetime import datetime
from flask import Flask, render_template, request, flash, redirect, url_for

app = Flask(__name__)
app.secret_key = 'secret_key'

UPLOAD_FOLDER = 'uploads'
DATA_FILE = 'uploaded_files.json'
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.pdf', '.txt'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Загружаем информацию о загруженных файлах
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        uploaded_files = json.load(f)
else:
    uploaded_files = []

def allowed_file(filename):
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS

def file_md5(file):
    hash_md5 = hashlib.md5()
    for chunk in iter(lambda: file.read(4096), b""):
        hash_md5.update(chunk)
    file.seek(0)
    return hash_md5.hexdigest()

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    global uploaded_files

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('Нет файла в запросе')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            md5 = file_md5(file)
            if any(entry['md5'] == md5 for entry in uploaded_files):
                flash('Такой файл уже был загружен ранее')
                return redirect(request.url)

            ext = os.path.splitext(file.filename)[1].lower()
            file_uuid = uuid.uuid4().hex + ext
            subdir = os.path.join(file_uuid[:2], file_uuid[2:4])
            full_path = os.path.join(app.config['UPLOAD_FOLDER'], subdir)
            os.makedirs(full_path, exist_ok=True)
            save_path = os.path.join(full_path, file_uuid)

            file.save(save_path)

            record = {
                'uuid': file_uuid,
                'original_name': file.filename,
                'upload_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'path': save_path,
                'extension': ext,
                'md5': md5
            }

            uploaded_files.append(record)
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(uploaded_files, f, ensure_ascii=False, indent=2)

            flash('Файл успешно загружен')
            return redirect(url_for('upload_file'))
        else:
            flash('Недопустимое расширение файла')
            return redirect(request.url)

    return render_template('table.html', files=uploaded_files)

if __name__ == '__main__':
    app.run(debug=True)
