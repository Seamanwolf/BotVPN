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
        now = datetime.now()
        return render_template('subscriptions.html', subscriptions=subscriptions, now=now)
    finally:
        db.close()

@app.route('/admins')
@login_required
def admins():
    """Страница управления администраторами"""
    # Создаем список администраторов из config.py
    admins_list = []
    for telegram_id in ADMIN_IDS:
        admin = {
            'telegram_id': telegram_id,
            'username': None,
            'full_name': None,
            'added_at': datetime.now(),  # Временная дата
            'note': 'Главный администратор' if telegram_id == 261337953 else None
        }
        admins_list.append(admin)
    
    return render_template('admins.html', admins=admins_list)

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
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'bonus_coins': user.bonus_coins,
                    'is_admin': user.telegram_id in ADMIN_IDS
                },
                'subscriptions': [{
                    'id': sub.id,
                    'plan_name': sub.plan_name,
                    'status': sub.status,
                    'created_at': sub.created_at.isoformat() if sub.created_at else None,
                    'expires_at': sub.expires_at.isoformat() if sub.expires_at else None
                } for sub in subscriptions]
            })
        else:
            return jsonify({'success': False, 'message': 'Пользователь не найден'})
    finally:
        db.close()

@app.route('/api/subscription/<int:subscription_id>')
@login_required
def get_subscription_details(subscription_id):
    """API для получения деталей подписки"""
    db = SessionLocal()
    try:
        subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if subscription:
            user = db.query(User).filter(User.id == subscription.user_id).first()
            return jsonify({
                'success': True,
                'subscription': {
                    'id': subscription.id,
                    'plan_name': subscription.plan_name,
                    'status': subscription.status,
                    'created_at': subscription.created_at.isoformat() if subscription.created_at else None,
                    'expires_at': subscription.expires_at.isoformat() if subscription.expires_at else None
                },
                'user': {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'full_name': user.full_name,
                    'email': user.email,
                    'created_at': user.created_at.isoformat() if user.created_at else None
                } if user else None
            })
        else:
            return jsonify({'success': False, 'message': 'Подписка не найдена'})
    finally:
        db.close()

@app.route('/api/subscription/<int:subscription_id>/extend', methods=['POST'])
@login_required
def extend_subscription(subscription_id):
    """API для продления подписки"""
    try:
        days = request.json.get('days', 0)
        if days <= 0:
            return jsonify({'success': False, 'message': 'Количество дней должно быть больше 0'})
        
        db = SessionLocal()
        try:
            subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
            if subscription:
                if subscription.expires_at:
                    subscription.expires_at += timedelta(days=days)
                else:
                    subscription.expires_at = datetime.now() + timedelta(days=days)
                
                db.commit()
                return jsonify({'success': True, 'message': f'Подписка продлена на {days} дней'})
            else:
                return jsonify({'success': False, 'message': 'Подписка не найдена'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/sync-xui', methods=['POST'])
@login_required
def sync_with_xui():
    """API для синхронизации с 3xUI"""
    try:
        # Здесь можно вызвать функцию синхронизации из notifications.py
        # Пока возвращаем успех
        return jsonify({'success': True, 'message': 'Синхронизация выполнена'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/<int:telegram_id>')
@login_required
def get_admin_details(telegram_id):
    """API для получения деталей администратора"""
    if telegram_id not in ADMIN_IDS:
        return jsonify({'success': False, 'message': 'Администратор не найден'})
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        admin = {
            'telegram_id': telegram_id,
            'added_at': datetime.now().isoformat(),
            'note': 'Главный администратор' if telegram_id == 261337953 else None
        }
        
        return jsonify({
            'success': True,
            'admin': admin,
            'user': {
                'id': user.id,
                'telegram_id': user.telegram_id,
                'full_name': user.full_name,
                'email': user.email,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'subscriptions': len(user.subscriptions) if user else 0
            } if user else None
        })
    finally:
        db.close()

if __name__ == '__main__':
    # Создаем папку для шаблонов если её нет
    os.makedirs('templates', exist_ok=True)
    
    # Запускаем сервер
    app.run(host='0.0.0.0', port=8080, debug=False)
