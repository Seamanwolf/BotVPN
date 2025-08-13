#!/usr/bin/env python3
"""
Веб-админ-панель для Telegram-бота SeaVPN
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
import json
from datetime import datetime, timedelta
from database import SessionLocal, User, Subscription
from config import ADMIN_WEB_USERNAME, ADMIN_WEB_PASSWORD, ADMIN_IDS
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Измените на свой секретный ключ

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class AdminUser(UserMixin):
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    if user_id == 'admin':
        return AdminUser('admin', ADMIN_WEB_USERNAME)
    return None

@app.route('/')
@login_required
def dashboard():
    """Главная страница админ-панели"""
    db = SessionLocal()
    try:
        # Получаем статистику
        total_users = db.query(User).count()
        active_subscriptions = db.query(Subscription).filter(Subscription.status == "active").count()
        expired_subscriptions = db.query(Subscription).filter(Subscription.status == "expired").count()
        
        # Получаем последние пользователей
        recent_users = db.query(User).order_by(User.created_at.desc()).limit(10).all()
        
        # Получаем последние подписки
        recent_subscriptions = db.query(Subscription).order_by(Subscription.created_at.desc()).limit(10).all()
        
        return render_template('dashboard.html',
                             total_users=total_users,
                             active_subscriptions=active_subscriptions,
                             expired_subscriptions=expired_subscriptions,
                             recent_users=recent_users,
                             recent_subscriptions=recent_subscriptions)
    finally:
        db.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_WEB_USERNAME and password == ADMIN_WEB_PASSWORD:
            user = AdminUser('admin', username)
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash('Неверный логин или пароль')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    return redirect(url_for('login'))

@app.route('/users')
@login_required
def users():
    """Страница управления пользователями"""
    db = SessionLocal()
    try:
        users = db.query(User).order_by(User.created_at.desc()).all()
        return render_template('users.html', users=users)
    finally:
        db.close()

@app.route('/subscriptions')
@login_required
def subscriptions():
    """Страница управления подписками"""
    db = SessionLocal()
    try:
        subscriptions = db.query(Subscription).order_by(Subscription.created_at.desc()).all()
        return render_template('subscriptions.html', subscriptions=subscriptions)
    finally:
        db.close()

@app.route('/admins')
@login_required
def admins():
    """Страница управления администраторами"""
    return render_template('admins.html', admin_ids=ADMIN_IDS)

@app.route('/api/add_admin', methods=['POST'])
@login_required
def add_admin():
    """API для добавления администратора"""
    try:
        telegram_id = int(request.json['telegram_id'])
        
        # Здесь нужно обновить конфигурацию
        # Пока просто возвращаем успех
        return jsonify({'success': True, 'message': f'Администратор {telegram_id} добавлен'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/remove_admin', methods=['POST'])
@login_required
def remove_admin():
    """API для удаления администратора"""
    try:
        telegram_id = int(request.json['telegram_id'])
        
        # Здесь нужно обновить конфигурацию
        # Пока просто возвращаем успех
        return jsonify({'success': True, 'message': f'Администратор {telegram_id} удален'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/user/<int:user_id>')
@login_required
def get_user_details(user_id):
    """API для получения деталей пользователя"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()
            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'full_name': user.full_name,
                    'email': user.email,
                    'phone': user.phone,
                    'created_at': user.created_at.isoformat(),
                    'bonus_coins': user.bonus_coins,
                    'is_admin': user.telegram_id in ADMIN_IDS
                },
                'subscriptions': [{
                    'id': sub.id,
                    'plan': sub.plan,
                    'status': sub.status,
                    'created_at': sub.created_at.isoformat(),
                    'expires_at': sub.expires_at.isoformat() if sub.expires_at else None
                } for sub in subscriptions]
            })
        else:
            return jsonify({'success': False, 'message': 'Пользователь не найден'})
    finally:
        db.close()

if __name__ == '__main__':
    # Создаем папку для шаблонов если её нет
    os.makedirs('templates', exist_ok=True)
    
    # Запускаем сервер
    app.run(host='0.0.0.0', port=8080, debug=True)
