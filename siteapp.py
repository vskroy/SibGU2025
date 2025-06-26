import os
import uuid
from datetime import datetime, timedelta
from flask import abort
from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FileField, TextAreaField
from wtforms.validators import DataRequired, Length
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import re
import unicodedata

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


def secure_filename_custom(filename):
    # Заменим пробелы на _
    filename = filename.replace(' ', '_')
    return re.sub(r'[^\w.\-а-яА-ЯёЁ]', '', filename)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(150), nullable=False)
    last_name = db.Column(db.String(150))
    role = db.Column(db.String(20), default='user')
    files = db.relationship('UserFile', backref='owner', lazy=True)

class ProfileForm(FlaskForm):
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(min=2, max=50)])
    submit = SubmitField('Сохранить')

class UserFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    download_count = db.Column(db.Integer, default=0)
    download_link = db.Column(db.String(150))
    link_expiration = db.Column(db.DateTime)


class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Войти')


class RegisterForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[DataRequired(), Length(min=3, max=150)])
    last_name = StringField('Фамилия', validators=[DataRequired(), Length(min=1, max=150)])
    password = PasswordField('Пароль', validators=[DataRequired()])
    submit = SubmitField('Зарегистрироваться')


class UploadForm(FlaskForm):
    file = FileField('Файл', validators=[DataRequired()])
    description = TextAreaField('Описание')
    submit = SubmitField('Загрузить')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def home():
    return render_template('home.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            flash('Успешный вход')
            return redirect(url_for('files'))
        flash('Неверное имя пользователя или пароль')
    return render_template('login.html', form=form)


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Пользователь уже существует')
        else:
            hashed_password = generate_password_hash(form.password.data)
            new_user = User(username=form.username.data, password_hash=hashed_password, last_name=form.last_name.data)
            db.session.add(new_user)
            db.session.commit()
            flash('Вы успешно зарегистрированы. Теперь войдите.')
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/admin')
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('Доступ запрещен')
        return redirect(url_for('home'))

    users = User.query.order_by(User.username).all()
    now = datetime.utcnow()
    stats = []

    for user in users:
        files = user.files  # Получаем все файлы пользователя
        total_files = len(files)
        links_created = sum(1 for f in files if f.download_link)
        active_links = sum(1 for f in files if f.download_link and f.link_expiration and f.link_expiration > now)
        total_downloads = sum(f.download_count or 0 for f in files)

        stats.append({
            'username': user.username,
            'total_files': total_files,
            'links_created': links_created,
            'active_links': active_links,
            'total_downloads': total_downloads
        })

    return render_template('admin_panel.html', stats=stats)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из аккаунта')
    return redirect(url_for('home'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)  # загрузить текущие данные пользователя в форму
    if form.validate_on_submit():
        current_user.last_name = form.last_name.data
        db.session.commit()
        flash('Фамилия успешно обновлена', 'success')
        return redirect(url_for('profile'))
    return render_template('profile.html', form=form)

def utc_to_krasnoyarsk(dt):
    if dt is None:
        return None
    return dt + timedelta(hours=7)

@app.template_filter('krasnoyarsk_time')
def krasnoyarsk_time_filter(dt):
    if dt is None:
        return '-'
    kras_time = utc_to_krasnoyarsk(dt)
    return kras_time.strftime('%Y-%m-%d %H:%M')

@app.route('/files', methods=['GET', 'POST'])
@login_required
def files():
    form = UploadForm()
    if form.validate_on_submit():
        f = form.file.data
        original_filename = secure_filename_custom(f.filename)

        # Сначала создаём запись в БД без пути
        new_file = UserFile(filename=original_filename, description=form.description.data, owner=current_user)
        db.session.add(new_file)
        db.session.commit()  # получим ID файла

        # Уникальная папка по user_id и file_id
        user_folder = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id), str(new_file.id))
        os.makedirs(user_folder, exist_ok=True)

        # Полный путь
        filepath = os.path.join(user_folder, original_filename)
        f.save(filepath)

        flash('Файл загружен')
        return redirect(url_for('files'))

    user_files = UserFile.query.filter_by(user_id=current_user.id).all()

    for f in user_files:
        f.upload_time_kras = utc_to_krasnoyarsk(f.upload_time)
        f.link_expiration_kras = utc_to_krasnoyarsk(f.link_expiration)

    return render_template('files.html', form=form, files=user_files, now=datetime.utcnow)



@app.route('/files/<int:file_id>/create_link')
@login_required
def create_link(file_id):
    file = UserFile.query.get_or_404(file_id)
    if file.user_id != current_user.id:
        flash('Нет доступа')
        return redirect(url_for('files'))

    token = str(uuid.uuid4())
    file.download_link = token
    file.link_expiration = datetime.utcnow() + timedelta(hours=12)
    db.session.commit()
    flash('Ссылка создана')
    return redirect(url_for('files'))

@app.route('/files/<int:file_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_file(file_id):
    file = UserFile.query.filter_by(id=file_id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        new_description = request.form.get('description', '').strip()
        if new_description:
            file.description = new_description
            db.session.commit()
            flash('Описание файла обновлено.', 'success')
            return redirect(url_for('files'))
        else:
            flash('Описание не может быть пустым.', 'danger')

    return render_template('edit_file.html', file=file)

@app.route('/files/<int:file_id>/delete', methods=['POST', 'GET'])
@login_required
def delete_file(file_id):
    file = UserFile.query.filter_by(id=file_id, user_id=current_user.id).first_or_404()

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id), str(file.id), file.filename)

    try:
        os.remove(file_path)
        # Также удалим папку, если она пустая
        folder_path = os.path.dirname(file_path)
        if os.path.exists(folder_path) and not os.listdir(folder_path):
            os.rmdir(folder_path)
    except Exception as e:
        print(f"Ошибка при удалении файла: {e}")

    db.session.delete(file)
    db.session.commit()
    flash('Файл удалён.', 'success')
    return redirect(url_for('files'))


@app.route('/download/<token>')
def download(token):
    file = UserFile.query.filter_by(download_link=token).first()
    if not file or file.link_expiration < datetime.utcnow():
        flash('Ссылка устарела')
        return redirect(url_for('home'))

    folder_path = os.path.join(app.config['UPLOAD_FOLDER'], str(file.user_id), str(file.id))
    file.download_count += 1
    db.session.commit()
    return send_from_directory(folder_path, file.filename, as_attachment=True)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # Проверяем, есть ли admin
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                password_hash=generate_password_hash('admin123'),  # обязательно хешируем пароль!
                role='admin',
                last_name='Администратор'
            )
            db.session.add(admin)
            db.session.commit()
            print('Admin user created')
        else:
            print('Admin user already exists')

    app.run(debug=True)
