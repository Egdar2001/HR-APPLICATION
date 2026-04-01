import os
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, send_from_directory, make_response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User, Task, FileBox, Message, Notification, Role

app = Flask(__name__)
# Configurations
app.config['SECRET_KEY'] = 'supersecretkey123'
base_dir = os.path.abspath(os.path.dirname(__name__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'database', 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(base_dir, 'static', 'uploads')
app.config['FILE_MANAGER_FOLDER'] = os.path.join(base_dir, 'static', 'user_files')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB max upload

# Initialize plugins
db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_FILE_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'csv', 'xlsx', 'png', 'jpg', 'jpeg'}

def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_FILE_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def is_admin():
    return current_user.is_authenticated and current_user.role == 'admin'

def is_manager():
    return current_user.is_authenticated and current_user.role in ['admin', 'manager']

def add_notification(user_id, message, n_type='info'):
    notif = Notification(user_id=user_id, message=message, type=n_type)
    db.session.add(notif)
    db.session.commit()

@app.context_processor
def inject_globals():
    if current_user.is_authenticated:
        unread_notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        if is_admin():
            unread_notifs += Notification.query.filter_by(user_id=None, is_read=False).count()
    else:
        unread_notifs = 0
    return dict(is_admin=is_admin(), is_manager=is_manager(), unread_notifs=unread_notifs)

# --- WEB AUTH ROUTES ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('signup'))

        user = User.query.filter_by(username=username).first()
        if user:
            flash('Username already exists.', 'danger')
            return redirect(url_for('signup'))

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        # Notify admins
        add_notification(None, f"New user registered: {username}", 'success')
        
        flash('Registration successful. You can now login.', 'success')
        return redirect(url_for('login'))
    return render_template('auth/signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username')
        answer = request.form.get('answer')
        new_password = request.form.get('new_password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_security_answer(answer):
            user.set_password(new_password)
            db.session.commit()
            flash('Password reset successful. You can now login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid username or security answer.', 'danger')
    return render_template('auth/forgot_password.html')

@app.route('/setup_security', methods=['POST'])
@login_required
def setup_security():
    question = request.form.get('security_question')
    answer = request.form.get('security_answer')
    if question and answer:
        current_user.security_question = question
        current_user.set_security_answer(answer)
        db.session.commit()
        flash('Security question configured.', 'success')
    return redirect(url_for('dashboard'))

# --- WEB DASHBOARD ROUTES ---
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard/index.html')

@app.route('/dashboard/upload_profile', methods=['POST'])
@login_required
def upload_profile():
    if 'profile_image' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('dashboard'))
    file = request.files['profile_image']
    if file and allowed_image(file.filename):
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        new_filename = f"user_{current_user.id}.{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        file.save(filepath)
        current_user.profile_image = new_filename
        db.session.commit()
        flash('Profile image updated.', 'success')
    return redirect(url_for('dashboard'))

# --- FILES & MESSAGES ---
@app.route('/files', methods=['GET', 'POST'])
@login_required
def file_manager():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file provided.', 'danger')
            return redirect(url_for('file_manager'))
        file = request.files['file']
        if file and allowed_file(file.filename):
            original_name = secure_filename(file.filename)
            uniq_filename = f"{current_user.id}_{datetime.utcnow().timestamp()}_{original_name}"
            filepath = os.path.join(app.config['FILE_MANAGER_FOLDER'], uniq_filename)
            file.save(filepath)
            new_file = FileBox(filename=uniq_filename, original_name=original_name, user_id=current_user.id)
            db.session.add(new_file)
            db.session.commit()
            flash('File uploaded successfully.', 'success')
    user_files = FileBox.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard/files.html', files=user_files)

@app.route('/files/download/<int:file_id>')
@login_required
def download_file(file_id):
    f = FileBox.query.get_or_404(file_id)
    if f.user_id != current_user.id and not is_manager():
        return "Unauthorized", 401
    return send_from_directory(app.config['FILE_MANAGER_FOLDER'], f.filename, as_attachment=True, download_name=f.original_name)

@app.route('/files/delete/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    f = FileBox.query.get_or_404(file_id)
    if f.user_id == current_user.id or is_manager():
        try:
            os.remove(os.path.join(app.config['FILE_MANAGER_FOLDER'], f.filename))
        except FileNotFoundError:
            pass
        db.session.delete(f)
        db.session.commit()
        flash("File deleted.", "info")
    return redirect(url_for('file_manager'))

@app.route('/messages', methods=['GET', 'POST'])
@login_required
def messages():
    if request.method == 'POST':
        content = request.form.get('content')
        receiver_id = request.form.get('receiver_id')
        if not receiver_id:
            receiver_id = None # Broadcast to admins
        else:
            receiver_id = int(receiver_id)
        
        msg = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
        db.session.add(msg)
        db.session.commit()
        flash('Message sent!', 'success')
        return redirect(url_for('messages'))

    if is_admin():
        inbox = Message.query.filter(db.or_(Message.receiver_id == current_user.id, Message.receiver_id == None)).order_by(Message.timestamp.desc()).all()
    else:
        inbox = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.timestamp.desc()).all()
    sent = Message.query.filter_by(sender_id=current_user.id).order_by(Message.timestamp.desc()).all()
    
    users = User.query.filter(User.id != current_user.id).all() if is_admin() else User.query.filter_by(role='admin').all()
    return render_template('dashboard/messages.html', inbox=inbox, sent=sent, users=users)

# --- ADMIN PANEL ---
@app.route('/admin/users')
@login_required
def admin_users():
    if not is_manager():
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('dashboard'))
    
    q = request.args.get('q', '')
    if q:
        users = User.query.filter(User.username.ilike(f'%{q}%')).all()
    else:
        users = User.query.all()
        
    available_roles = Role.query.all()
    return render_template('admin/users.html', users=users, search_query=q, available_roles=available_roles)

@app.route('/admin/set_role/<int:user_id>', methods=['POST'])
@login_required
def set_role(user_id):
    if not is_admin():
        return "Unauthorized", 401
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot change own role.", "warning")
        return redirect(url_for('admin_users'))
    
    new_role = request.form.get('new_role')
    role_check = Role.query.filter_by(name=new_role).first()
    if role_check:
        user.role = new_role
        db.session.commit()
        flash(f"Role for {user.username} updated to {new_role}.", "success")
        
    return redirect(url_for('admin_users'))

@app.route('/admin/rename_user/<int:user_id>', methods=['POST'])
@login_required
def rename_user(user_id):
    if not is_admin():
        return "Unauthorized", 401
    user = User.query.get_or_404(user_id)
    new_username = request.form.get('new_username')
    
    existing_user = User.query.filter_by(username=new_username.strip()).first() if new_username else None
    if existing_user and existing_user.id != user_id:
        flash(f'Username "{new_username}" is already taken.', 'danger')
        return redirect(url_for('admin_users'))
        
    if new_username and new_username.strip():
        old_name = user.username
        user.username = new_username.strip()
        db.session.commit()
        flash(f'User "{old_name}" has been renamed to "{user.username}".', 'success')
    else:
        flash('New username cannot be empty.', 'warning')
        
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not is_admin():
        return "Unauthorized", 401
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Cannot delete yourself.", "danger")
        return redirect(url_for('admin_users'))
        
    username = user.username
    
    Task.query.filter_by(user_id=user.id).delete()
    
    files = FileBox.query.filter_by(user_id=user.id).all()
    for f in files:
        file_path = os.path.join(app.config['FILE_MANAGER_FOLDER'], f.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        db.session.delete(f)
        
    Message.query.filter(db.or_(Message.sender_id==user.id, Message.receiver_id==user.id)).delete()
    Notification.query.filter_by(user_id=user.id).delete()
    
    db.session.delete(user)
    db.session.commit()
    flash(f"User '{username}' and all associated data have been permanently deleted.", "success")
    return redirect(url_for('admin_users'))

@app.route('/admin/broadcast_task', methods=['POST'])
@login_required
def broadcast_task():
    if not is_manager():
        return "Unauthorized", 401
    
    title = request.form.get('title')
    category = request.form.get('category', 'Work')
    priority = request.form.get('priority', 'Medium')
    due_date_str = request.form.get('due_date')
    due_date = datetime.fromisoformat(due_date_str) if due_date_str else None
    
    if title:
        users = User.query.all()
        for u in users:
            new_task = Task(title=title, user_id=u.id, category=category, priority=priority, due_date=due_date)
            db.session.add(new_task)
            add_notification(u.id, f"Admin assigned a new task: {title}", 'info')
        db.session.commit()
        flash(f"Task successfully broadcasted to all {len(users)} users.", "success")
    else:
        flash("Task title cannot be empty.", "warning")
    return redirect(url_for('admin_users'))

@app.route('/admin/assign_task/<int:user_id>', methods=['POST'])
@login_required
def assign_task(user_id):
    if not is_manager():
        return "Unauthorized", 401
    user = User.query.get_or_404(user_id)
    
    title = request.form.get('title')
    category = request.form.get('category', 'Work')
    priority = request.form.get('priority', 'Medium')
    due_date_str = request.form.get('due_date')
    due_date = datetime.fromisoformat(due_date_str) if due_date_str else None
    
    if title:
        new_task = Task(title=title, user_id=user.id, category=category, priority=priority, due_date=due_date)
        db.session.add(new_task)
        add_notification(user.id, f"Admin assigned you a new task: {title}", 'info')
        db.session.commit()
        flash(f"Task '{title}' assigned to {user.username}.", "success")
    else:
        flash("Task title cannot be empty.", "warning")
    return redirect(url_for('admin_users'))

@app.route('/admin/create_role', methods=['POST'])
@login_required
def create_role():
    if not is_admin():
        return "Unauthorized", 401
    new_role_name = request.form.get('role_name')
    if new_role_name and new_role_name.strip():
        r_name = new_role_name.strip().lower()
        if not Role.query.filter_by(name=r_name).first():
            db.session.add(Role(name=r_name))
            db.session.commit()
            flash(f"Role '{r_name}' successfully created.", 'success')
        else:
            flash(f"Role '{r_name}' already exists.", 'warning')
    else:
        flash("Role name cannot be empty.", 'danger')
    return redirect(url_for('admin_users'))

@app.route('/admin/export/users')
@login_required
def export_users():
    if not is_admin():
        return "Unauthorized", 401
    
    users = User.query.all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Username', 'Role', 'Tasks Count', 'Files Count'])
    for u in users:
        cw.writerow([u.id, u.username, u.role, len(u.tasks), len(u.files)])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=users_export.csv"
    output.headers["Content-type"] = "text/csv"
    return output

# --- REST API & AJAX ROUTES ---
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if user and user.check_password(data.get('password')):
        login_user(user)
        return jsonify({'status': 'success', 'message': 'Logged in', 'user': {'id': user.id, 'username': user.username, 'role': user.role}})
    return jsonify({'status': 'error', 'message': 'Invalid credentials'}), 401

@app.route('/api/tasks', methods=['GET', 'POST'])
@login_required
def api_tasks():
    if request.method == 'GET':
        tasks = Task.query.filter_by(user_id=current_user.id).all()
        return jsonify([{
            'id': t.id,
            'title': t.title,
            'is_completed': t.is_completed,
            'category': t.category,
            'priority': t.priority,
            'due_date': t.due_date.isoformat() if t.due_date else None,
            'created_at': t.created_at.isoformat()
        } for t in tasks])
    
    if request.method == 'POST':
        data = request.json
        category = data.get('category', 'Work')
        priority = data.get('priority', 'Medium')
        due_date_str = data.get('due_date')
        due_date = datetime.fromisoformat(due_date_str) if due_date_str else None
        
        new_task = Task(title=data['title'], user_id=current_user.id, category=category, priority=priority, due_date=due_date)
        db.session.add(new_task)
        db.session.commit()
        return jsonify({'status': 'success', 'task_id': new_task.id})

@app.route('/api/tasks/<int:task_id>', methods=['DELETE', 'PATCH'])
@login_required
def api_manipulate_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
    if request.method == 'DELETE':
        db.session.delete(task)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Task deleted'})
        
    if request.method == 'PATCH':
        data = request.json
        if 'is_completed' in data:
            task.is_completed = data['is_completed']
            if task.is_completed:
                add_notification(current_user.id, f"Task completed: {task.title}", 'success')
        db.session.commit()
        return jsonify({'status': 'success'})

@app.route('/api/notifications')
@login_required
def get_notifications():
    if is_admin():
        notifs = Notification.query.filter(db.or_(Notification.user_id == current_user.id, Notification.user_id == None)).order_by(Notification.created_at.desc()).limit(10).all()
    else:
        notifs = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(10).all()
        
    return jsonify([{
        'id': n.id,
        'message': n.message,
        'type': n.type,
        'is_read': n.is_read,
        'created_at': n.created_at.strftime("%b %d, %H:%M")
    } for n in notifs])

@app.route('/api/notifications/read', methods=['POST'])
@login_required
def read_notifications():
    if is_admin():
        notifs = Notification.query.filter(db.or_(Notification.user_id == current_user.id, Notification.user_id == None)).all()
    else:
        notifs = Notification.query.filter_by(user_id=current_user.id).all()
    for n in notifs:
        n.is_read = True
    db.session.commit()
    return jsonify({'status': 'success'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        for r_name in ['user', 'manager', 'admin']:
            if not Role.query.filter_by(name=r_name).first():
                db.session.add(Role(name=r_name))
        db.session.commit()
        
        if User.query.first() is None:
            admin_user = User(username='admin', role='admin')
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created: username='admin', password='admin123'")
    app.run(debug=True)
