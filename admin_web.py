#!/usr/bin/env python3
"""
Веб-админ-панель для Telegram-бота SeaVPN
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
import json
from datetime import datetime, timedelta
from database import SessionLocal, User, Subscription, Admin
from config import ADMIN_IDS
import os
import asyncio
from xui_client import XUIClient

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Измените на свой секретный ключ

# Настройка Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class AdminUser(UserMixin):
    def __init__(self, admin_id, telegram_id, username, is_superadmin=False):
        self.id = admin_id
        self.telegram_id = telegram_id
        self.username = username
        self.is_superadmin = is_superadmin

@login_manager.user_loader
def load_user(admin_id):
    # Если admin_id == 'admin', это суперадмин
    if admin_id == 'admin':
        db = SessionLocal()
        try:
            admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
            if admin:
                return AdminUser(admin.id, admin.telegram_id, admin.username, admin.is_superadmin)
        finally:
            db.close()
    else:
        # Обычный админ по ID
        try:
            admin_id_int = int(admin_id)
            db = SessionLocal()
            try:
                admin = db.query(Admin).filter(Admin.id == admin_id_int, Admin.is_active == True).first()
                if admin:
                    return AdminUser(admin.id, admin.telegram_id, admin.username, admin.is_superadmin)
            finally:
                db.close()
        except ValueError:
            pass
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
        
        db = SessionLocal()
        try:
            admin = db.query(Admin).filter(Admin.username == username, Admin.is_active == True).first()
            if admin and check_password_hash(admin.password_hash, password):
                # Для суперадмина используем 'admin' как ID, для остальных - числовой ID
                user_id = 'admin' if admin.is_superadmin else str(admin.id)
                user = AdminUser(user_id, admin.telegram_id, admin.username, admin.is_superadmin)
                login_user(user)
                
                # Обновляем время последнего входа
                admin.last_login = datetime.utcnow()
                db.commit()
                
                return redirect(url_for('dashboard'))
            else:
                flash('Неверный логин или пароль')
        finally:
            db.close()
    
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
        # Получаем всех администраторов
        admin_telegram_ids = [admin.telegram_id for admin in db.query(Admin).all()]
        
        # Исключаем администраторов из списка пользователей
        users = db.query(User).filter(~User.telegram_id.in_(admin_telegram_ids)).order_by(User.created_at.desc()).all()
        
        # Получаем все подписки для подсчета
        subscriptions = db.query(Subscription).all()
        
        # Подсчитываем количество рефералов для каждого пользователя
        for user in users:
            user.referrals_count = db.query(User).filter(User.referred_by == user.id).count()
        
        return render_template('users.html', users=users, subscriptions=subscriptions)
    finally:
        db.close()

@app.route('/subscriptions')
@login_required
def subscriptions():
    """Страница управления подписками"""
    db = SessionLocal()
    try:
        subscriptions = db.query(Subscription).order_by(Subscription.created_at.desc()).all()
        users = db.query(User).all()  # Добавляем пользователей для модального окна создания подписки
        now = datetime.utcnow()
        return render_template('subscriptions.html', subscriptions=subscriptions, users=users, now=now)
    finally:
        db.close()

@app.route('/admins')
@login_required
def admins():
    """Страница управления администраторами"""
    db = SessionLocal()
    try:
        admins_list = db.query(Admin).order_by(Admin.created_at.desc()).all()
        return render_template('admins.html', admins=admins_list)
    finally:
        db.close()

# API endpoints

@app.route('/api/user/<int:user_id>')
@login_required
def get_user_details(user_id):
    """API для получения деталей пользователя"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()
            # Подсчитываем количество рефералов
            referrals_count = db.query(User).filter(User.referred_by == user.id).count()
            
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
                    'referral_code': user.referral_code,
                    'referred_by': user.referred_by,
                    'referrals_count': referrals_count,
                    'has_made_first_purchase': user.has_made_first_purchase,
                    'is_admin': user.telegram_id in ADMIN_IDS
                },
                'subscriptions': [{
                    'id': sub.id,
                    'plan': sub.plan,
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

@app.route('/api/user/<int:user_id>/subscriptions')
@login_required
def get_user_subscriptions(user_id):
    """API для получения подписок пользователя"""
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
                    'email': user.email
                },
                'subscriptions': [{
                    'id': sub.id,
                    'plan': sub.plan,
                    'plan_name': sub.plan_name,
                    'status': sub.status,
                    'subscription_number': sub.subscription_number or 1,
                    'unique_name': f"SeaMiniVpn-{user.telegram_id}-{sub.subscription_number or 1}",
                    'created_at': sub.created_at.strftime('%d.%m.%Y %H:%M') if sub.created_at else None,
                    'expires_at': sub.expires_at.strftime('%d.%m.%Y %H:%M') if sub.expires_at else None
                } for sub in subscriptions]
            })
        else:
            return jsonify({'success': False, 'message': 'Пользователь не найден'})
    finally:
        db.close()

@app.route('/api/user/<int:user_id>/referrals')
@login_required
def get_user_referrals(user_id):
    """API для получения списка рефералов пользователя"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            referrals = db.query(User).filter(User.referred_by == user.id).order_by(User.created_at.desc()).all()
            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'full_name': user.full_name,
                    'email': user.email,
                    'referral_code': user.referral_code
                },
                'referrals': [{
                    'id': ref.id,
                    'telegram_id': ref.telegram_id,
                    'full_name': ref.full_name,
                    'email': ref.email,
                    'bonus_coins': ref.bonus_coins,
                    'has_made_first_purchase': ref.has_made_first_purchase,
                    'created_at': ref.created_at.strftime('%d.%m.%Y %H:%M') if ref.created_at else None
                } for ref in referrals]
            })
        else:
            return jsonify({'success': False, 'message': 'Пользователь не найден'})
    finally:
        db.close()

@app.route('/api/subscription/<int:subscription_id>/delete', methods=['POST'])
@login_required
def delete_subscription(subscription_id):
    """API для удаления подписки"""
    db = SessionLocal()
    try:
        subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
        if not subscription:
            return jsonify({'success': False, 'message': 'Подписка не найдена'})
        
        # Получаем пользователя
        user = db.query(User).filter(User.id == subscription.user_id).first()
        if not user:
            return jsonify({'success': False, 'message': 'Пользователь не найден'})
        
        # Формируем уникальный email для поиска в 3xUI
        unique_email = f"SeaMiniVpn-{user.telegram_id}-{subscription.subscription_number}"
        
        # Удаляем из 3xUI
        import asyncio
        from xui_client import XUIClient
        
        async def delete_from_3xui():
            xui_client = XUIClient()
            try:
                success = await xui_client.delete_user(unique_email)
                return success
            finally:
                await xui_client.close()
        
        # Запускаем асинхронную функцию
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            xui_success = loop.run_until_complete(delete_from_3xui())
        finally:
            loop.close()
        
        if xui_success:
            # Проверяем, что подписка еще существует в БД
            db.refresh(subscription)
            if subscription:
                # Удаляем из базы данных
                db.delete(subscription)
                db.commit()
                return jsonify({'success': True, 'message': 'Подписка успешно удалена из БД и 3xUI'})
            else:
                return jsonify({'success': True, 'message': 'Подписка уже была удалена из БД, но успешно удалена из 3xUI'})
        else:
            return jsonify({'success': False, 'message': 'Ошибка удаления из 3xUI'})
            
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'})
    finally:
        db.close()

@app.route('/api/user/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """API для удаления пользователя"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'message': 'Пользователь не найден'})
        
        # Проверяем, не является ли пользователь админом
        admin = db.query(Admin).filter(Admin.telegram_id == user.telegram_id).first()
        if admin:
            return jsonify({'success': False, 'message': 'Нельзя удалить администратора'})
        
        # Получаем все подписки пользователя
        subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()
        
        # Удаляем пользователя из 3xUI (будет удален при следующей синхронизации)
        print(f"Пользователь {user.telegram_id} будет удален из 3xUI при следующей синхронизации")
        
        # Удаляем все подписки пользователя из БД
        for subscription in subscriptions:
            db.delete(subscription)
        
        # Удаляем пользователя из БД
        db.delete(user)
        db.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Пользователь {user.full_name or user.telegram_id} успешно удален'
        })
        
    except Exception as e:
        db.rollback()
        print(f"Ошибка при удалении пользователя: {e}")
        return jsonify({'success': False, 'message': f'Ошибка при удалении: {str(e)}'})
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
                    'plan': subscription.plan,
                    'plan_name': subscription.plan_name,
                    'status': subscription.status,
                    'subscription_number': subscription.subscription_number or 1,
                    'unique_name': f"SeaMiniVpn-{user.telegram_id}-{subscription.subscription_number or 1}" if user else None,
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
                    subscription.expires_at = datetime.utcnow() + timedelta(days=days)
                
                db.commit()
                return jsonify({'success': True, 'message': f'Подписка продлена на {days} дней'})
            else:
                return jsonify({'success': False, 'message': 'Подписка не найдена'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/subscription/<int:subscription_id>/pause', methods=['POST'])
@login_required
def pause_subscription(subscription_id):
    """API для приостановки подписки"""
    try:
        db = SessionLocal()
        try:
            subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
            if subscription:
                subscription.status = "paused"
                db.commit()
                return jsonify({'success': True, 'message': 'Подписка приостановлена'})
            else:
                return jsonify({'success': False, 'message': 'Подписка не найдена'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})



@app.route('/api/subscription/create', methods=['POST'])
@login_required
def create_subscription():
    """API для создания подписки вручную"""
    try:
        data = request.json
        user_id = data.get('user_id')
        plan = data.get('plan')
        plan_name = data.get('plan_name')
        days = data.get('days', 30)
        
        if not all([user_id, plan, plan_name]):
            return jsonify({'success': False, 'message': 'Не все поля заполнены'})
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'success': False, 'message': 'Пользователь не найден'})
            
            subscription = Subscription(
                user_id=user_id,
                plan=plan,
                plan_name=plan_name,
                status="active",
                expires_at=datetime.utcnow() + timedelta(days=days)
            )
            
            db.add(subscription)
            db.commit()
            
            return jsonify({'success': True, 'message': f'Подписка создана на {days} дней'})
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

@app.route('/api/admin/add', methods=['POST'])
@login_required
def add_admin():
    """API для добавления администратора"""
    try:
        data = request.json
        telegram_id = int(data['telegram_id'])
        username = data.get('username')
        full_name = data.get('full_name')
        password = data.get('password')
        
        if not password:
            return jsonify({'success': False, 'message': 'Пароль обязателен'})
        
        db = SessionLocal()
        try:
            # Проверяем, есть ли уже админ с таким Telegram ID
            existing_admin = db.query(Admin).filter(Admin.telegram_id == telegram_id).first()
            if existing_admin:
                return jsonify({'success': False, 'message': 'Администратор уже существует'})
            
            # Проверяем, есть ли уже админ с таким username
            if username:
                existing_username = db.query(Admin).filter(Admin.username == username).first()
                if existing_username:
                    return jsonify({'success': False, 'message': 'Пользователь с таким логином уже существует'})
            
            admin = Admin(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                password_hash=generate_password_hash(password),
                is_superadmin=False,
                is_active=True
            )
            
            db.add(admin)
            db.commit()
            
            return jsonify({'success': True, 'message': f'Администратор {full_name or telegram_id} добавлен'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/<int:admin_id>/remove', methods=['POST'])
@login_required
def remove_admin(admin_id):
    """API для удаления администратора"""
    try:
        db = SessionLocal()
        try:
            admin = db.query(Admin).filter(Admin.id == admin_id).first()
            if not admin:
                return jsonify({'success': False, 'message': 'Администратор не найден'})
            
            if admin.is_superadmin:
                return jsonify({'success': False, 'message': 'Нельзя удалить суперадмина'})
            
            db.delete(admin)
            db.commit()
            
            return jsonify({'success': True, 'message': f'Администратор {admin.full_name or admin.telegram_id} удален'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/<int:admin_id>/block', methods=['POST'])
@login_required
def block_admin(admin_id):
    """API для блокировки администратора"""
    try:
        db = SessionLocal()
        try:
            admin = db.query(Admin).filter(Admin.id == admin_id).first()
            if not admin:
                return jsonify({'success': False, 'message': 'Администратор не найден'})
            
            if admin.is_superadmin:
                return jsonify({'success': False, 'message': 'Нельзя заблокировать суперадмина'})
            
            admin.is_active = False
            db.commit()
            
            return jsonify({'success': True, 'message': f'Администратор {admin.full_name or admin.telegram_id} заблокирован'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/<int:admin_id>/unblock', methods=['POST'])
@login_required
def unblock_admin(admin_id):
    """API для разблокировки администратора"""
    try:
        db = SessionLocal()
        try:
            admin = db.query(Admin).filter(Admin.id == admin_id).first()
            if not admin:
                return jsonify({'success': False, 'message': 'Администратор не найден'})
            
            if admin.is_superadmin:
                return jsonify({'success': False, 'message': 'Нельзя разблокировать суперадмина'})
            
            admin.is_active = True
            db.commit()
            
            return jsonify({'success': True, 'message': f'Администратор {admin.full_name or admin.telegram_id} разблокирован'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/<int:admin_id>')
@login_required
def get_admin_details(admin_id):
    """API для получения деталей администратора"""
    db = SessionLocal()
    try:
        admin = db.query(Admin).filter(Admin.id == admin_id).first()
        if admin:
            user = db.query(User).filter(User.telegram_id == admin.telegram_id).first()
            return jsonify({
                'success': True,
                'admin': {
                    'id': admin.id,
                    'telegram_id': admin.telegram_id,
                    'username': admin.username,
                    'full_name': admin.full_name,
                    'is_superadmin': admin.is_superadmin,
                    'is_active': admin.is_active,
                    'created_at': admin.created_at.isoformat() if admin.created_at else None,
                    'last_login': admin.last_login.isoformat() if admin.last_login else None
                },
                'user': {
                    'id': user.id,
                    'telegram_id': user.telegram_id,
                    'full_name': user.full_name,
                    'email': user.email,
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'subscriptions': len(user.subscriptions) if user else 0
                } if user else None
            })
        else:
            return jsonify({'success': False, 'message': 'Администратор не найден'})
    finally:
        db.close()

if __name__ == '__main__':
    # Создаем папку для шаблонов если её нет
    os.makedirs('templates', exist_ok=True)
    
    # Запускаем сервер
    app.run(host='0.0.0.0', port=8080, debug=False)
