#!/usr/bin/env python3
"""
Веб-админ-панель для Telegram-бота SeaVPN
"""

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from flask_socketio import join_room, emit
import json
from datetime import datetime, timedelta
import os
import sys
import asyncio
import logging
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загружаем переменные окружения из .env файла
load_dotenv()

from database import SessionLocal, User, Subscription, Admin, Ticket, TicketMessage, AdminReadMessages, AdminNotificationsViewed, AdminViewedUsers, AdminSettings, MassNotification, Payment
from config import ADMIN_IDS
from xui_client import XUIClient
from socketio_app import socketio

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')
app.secret_key = 'your-secret-key-change-this'  # Измените на свой секретный ключ

# Инициализация Socket.IO
socketio.init_app(app)

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
        
        from datetime import timedelta
        now = datetime.utcnow()
        
        # Получаем ID администратора из текущего пользователя
        current_user_id = current_user.id
        if current_user_id == 'admin':
            # Для суперадмина получаем его реальный ID из базы
            admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
            if not admin:
                admin_id = None
            else:
                admin_id = admin.id
        else:
            admin_id = int(current_user_id)
        
        # Получаем просмотренных пользователей для текущего админа
        viewed_users = set()
        if admin_id:
            viewed_records = db.query(AdminViewedUsers).filter(AdminViewedUsers.admin_id == admin_id).all()
            viewed_users = {record.user_id for record in viewed_records}
        
        # Определяем новых пользователей (за последние 2 часа и не просмотренных)
        two_hours_ago = now - timedelta(hours=2)
        new_users_count = 0
        
        for user in users:
            is_new = (user.created_at > two_hours_ago and user.id not in viewed_users)
            user.is_new = is_new
            if is_new:
                new_users_count += 1
        
        return render_template('users.html', users=users, subscriptions=subscriptions, now=now, timedelta=timedelta, new_users_count=new_users_count)
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

@app.route('/notifications')
@login_required
def notifications():
    """Страница массовых уведомлений"""
    db = SessionLocal()
    try:
        # Получаем статистику
        total_users = db.query(User).count()
        active_subscriptions = db.query(Subscription).filter(Subscription.status == "active").count()
        
        # Статистика уведомлений
        sent_today = db.query(MassNotification).filter(
            MassNotification.created_at >= datetime.utcnow().date()
        ).count()
        total_sent = db.query(MassNotification).count()
        
        # История уведомлений
        notifications_history = db.query(MassNotification).order_by(MassNotification.created_at.desc()).limit(20).all()
        
        return render_template('notifications.html',
                             total_users=total_users,
                             active_subscriptions=active_subscriptions,
                             sent_today=sent_today,
                             total_sent=total_sent,
                             notifications_history=notifications_history)
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

@app.route('/tickets')
@login_required
def tickets():
    """Страница тикетов"""
    db = SessionLocal()
    try:
        # Получаем все тикеты с информацией о пользователях и сообщениях
        tickets_query = db.query(Ticket).order_by(
            Ticket.status,  # Сначала открытые (open < closed)
            Ticket.updated_at.desc()  # Затем по времени обновления (новые вверху)
        ).all()
        
        # Для каждого тикета получаем имя пользователя
        for ticket in tickets_query:
            user = db.query(User).filter(User.id == ticket.user_id).first()
            if user:
                ticket.user_name = user.full_name
                ticket.user = user
            else:
                ticket.user_name = "Неизвестный пользователь"
                ticket.user = None
            
            # Получаем сообщения тикета
            ticket.messages = db.query(TicketMessage).filter(
                TicketMessage.ticket_id == ticket.id
            ).order_by(TicketMessage.created_at).all()
        
        return render_template('tickets.html', tickets=tickets_query)
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

@app.route('/api/user/<int:user_id>/tickets')
@login_required
def get_user_tickets(user_id):
    """API для получения тикетов пользователя"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({'success': False, 'message': 'Пользователь не найден'})
        
        # Получаем все тикеты пользователя
        tickets = db.query(Ticket).filter(Ticket.user_id == user_id).order_by(
            Ticket.status,  # Сначала открытые (open < closed)
            Ticket.updated_at.desc()  # Затем по времени обновления (новые вверху)
        ).all()
        
        # Преобразуем в список словарей
        tickets_data = []
        for ticket in tickets:
            # Получаем количество сообщений
            messages_count = db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).count()
            
            tickets_data.append({
                'id': ticket.id,
                'ticket_number': ticket.ticket_number,
                'status': ticket.status,
                'subject': ticket.subject,
                'created_at': ticket.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': ticket.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                'closed_at': ticket.closed_at.strftime('%Y-%m-%d %H:%M:%S') if ticket.closed_at else None,
                'messages_count': messages_count
            })
        
        return jsonify({
            'success': True, 
            'user': {
                'id': user.id,
                'telegram_id': user.telegram_id,
                'full_name': user.full_name
            },
            'tickets': tickets_data
        })
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
    print(f"=== НАЧАЛО УДАЛЕНИЯ ПОЛЬЗОВАТЕЛЯ ID: {user_id} ===")
    print(f"Метод: {request.method}")
    print(f"URL: {request.url}")
    print(f"Заголовки: {dict(request.headers)}")
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            print(f"Пользователь ID {user_id} не найден")
            return jsonify({'success': False, 'message': 'Пользователь не найден'})
        
        print(f"Найден пользователь: {user.full_name} (Telegram ID: {user.telegram_id})")
        
        # Проверяем, не является ли пользователь админом
        admin = db.query(Admin).filter(Admin.telegram_id == user.telegram_id).first()
        if admin:
            print(f"Пользователь {user.telegram_id} является администратором, удаление запрещено")
            return jsonify({'success': False, 'message': 'Нельзя удалить администратора'})
        
        # Получаем все подписки пользователя
        subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()
        print(f"Найдено подписок у пользователя: {len(subscriptions)}")

        # Удаляем связанные платежи
        payments_deleted = db.query(Payment).filter(Payment.user_id == user_id).delete(synchronize_session=False)
        print(f"Удалено платежей: {payments_deleted}")

        # Удаляем записи о просмотренных пользователях у админов
        viewed_deleted = db.query(AdminViewedUsers).filter(AdminViewedUsers.user_id == user_id).delete(synchronize_session=False)
        print(f"Удалено отметок о просмотре пользователя у админов: {viewed_deleted}")

        # Удаляем тикеты пользователя вместе с сообщениями и связями чтения
        tickets = db.query(Ticket).filter(Ticket.user_id == user_id).all()
        print(f"Найдено тикетов у пользователя: {len(tickets)}")
        for ticket in tickets:
            # Сначала удаляем записи о прочтении сообщений для этого тикета
            reads_deleted = db.query(AdminReadMessages).filter(AdminReadMessages.ticket_id == ticket.id).delete(synchronize_session=False)
            print(f"Удалено отметок о чтении для тикета {ticket.id}: {reads_deleted}")
            # Удаляем сам тикет (сообщения удалятся каскадно через relationship)
            db.delete(ticket)

        # Удаляем все подписки пользователя из БД
        for subscription in subscriptions:
            print(f"Удаляем подписку ID: {subscription.id}")
            db.delete(subscription)

        # Удаляем пользователя из 3xUI (будет удален при следующей синхронизации)
        print(f"Пользователь {user.telegram_id} будет удален из 3xUI при следующей синхронизации")

        # Удаляем пользователя из БД
        print(f"Удаляем пользователя ID: {user.id}")
        db.delete(user)
        db.commit()
        print(f"Пользователь {user.full_name or user.telegram_id} успешно удален из БД")
        
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
                    'extensions_count': subscription.extensions_count or 0,
                    'last_extension_date': subscription.last_extension_date.isoformat() if subscription.last_extension_date else None,
                    'total_days_added': subscription.total_days_added or 0,
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

@app.route('/api/user/<int:user_id>/add_coins', methods=['POST'])
@login_required
def add_coins(user_id):
    """API для начисления бонусных монет пользователю"""
    try:
        coins = request.json.get('coins', 0)
        if coins <= 0:
            return jsonify({'success': False, 'message': 'Количество монет должно быть больше 0'})
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                # Начисляем монеты
                user.bonus_coins += coins
                db.commit()
                
                # Отправляем уведомление пользователю
                try:
                    from notifications import NotificationManager
                    import asyncio
                    
                    notification_manager = NotificationManager()
                    asyncio.run(notification_manager.notify_coins_added(user, coins))
                except Exception as e:
                    print(f"Ошибка при отправке уведомления о начислении монет: {e}")
                
                return jsonify({
                    'success': True, 
                    'message': f'Пользователю {user.full_name or user.telegram_id} начислено {coins} монет',
                    'new_balance': user.bonus_coins
                })
            else:
                return jsonify({'success': False, 'message': 'Пользователь не найден'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/user/<int:user_id>/add_subscription', methods=['POST'])
@login_required
def add_user_subscription(user_id):
    """API для добавления подписки пользователю"""
    try:
        # Получаем данные из запроса
        plan = request.json.get('plan')
        plan_name = request.json.get('plan_name')
        days = request.json.get('days', 30)
        create_in_xui = request.json.get('create_in_xui', True)
        
        if not all([plan, plan_name, days]):
            return jsonify({'success': False, 'error': 'Не все поля заполнены'})
        
        db = SessionLocal()
        try:
            # Проверяем существование пользователя
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
            # Определяем следующий номер подписки
            existing_subscriptions = db.query(Subscription).filter(
                Subscription.user_id == user.id
            ).all()
            next_subscription_number = max([s.subscription_number for s in existing_subscriptions], default=0) + 1
            
            # Создаем пользователя в 3xUI, если требуется
            xui_result = None
            if create_in_xui:
                try:
                    # Используем email пользователя или создаем временный
                    user_email = user.email if user.email else f"user_{user.telegram_id}@vpn.local"
                    
                    # Создаем пользователя в 3xUI
                    xui_client = XUIClient()
                    xui_result = asyncio.run(xui_client.create_user(
                        user_email, 
                        days, 
                        f"{user.full_name or 'User'} (ADMIN)", 
                        str(user.telegram_id), 
                        next_subscription_number
                    ))
                    
                    if not xui_result:
                        return jsonify({'success': False, 'error': 'Ошибка создания пользователя в 3xUI'})
                except Exception as e:
                    return jsonify({'success': False, 'error': f'Ошибка при работе с 3xUI: {str(e)}'})
            
            # Создаем подписку в БД
            expires_at = datetime.utcnow() + timedelta(days=days)
            subscription = Subscription(
                user_id=user.id,
                plan=plan,
                plan_name=plan_name,
                status="active",
                subscription_number=next_subscription_number,
                expires_at=expires_at
            )
            db.add(subscription)
            db.commit()
            
            return jsonify({
                'success': True, 
                'message': f'Подписка успешно добавлена пользователю {user.full_name or user.telegram_id}',
                'subscription_id': subscription.id,
                'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



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

@app.route('/api/ticket/<int:ticket_id>')
@login_required
def get_ticket_details(ticket_id):
    """API для получения деталей тикета"""
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if ticket:
            # Получаем пользователя
            user = db.query(User).filter(User.id == ticket.user_id).first()
            user_name = user.full_name if user else "Неизвестный пользователь"
            
            # Получаем сообщения
            messages = db.query(TicketMessage).filter(
                TicketMessage.ticket_id == ticket.id
            ).order_by(TicketMessage.created_at).all()
            
            messages_list = []
            for msg in messages:
                sender = db.query(User).filter(User.id == msg.sender_id).first() if msg.sender_id else None
                sender_name = sender.full_name if sender else "Система"
                
                messages_list.append({
                    'id': msg.id,
                    'sender_id': msg.sender_id,
                    'sender_name': sender_name,
                    'sender_type': msg.sender_type,
                    'message': msg.message,
                    'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
                })
            
            return jsonify({
                'success': True, 
                'ticket': {
                    'id': ticket.id,
                    'ticket_number': ticket.ticket_number,
                    'user_id': ticket.user_id,
                    'user_name': user_name,
                    'status': ticket.status,
                    'subject': ticket.subject,
                    'created_at': ticket.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'updated_at': ticket.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'closed_at': ticket.closed_at.strftime('%Y-%m-%d %H:%M:%S') if ticket.closed_at else None
                },
                'messages': messages_list
            })
        else:
            return jsonify({'success': False, 'message': 'Тикет не найден'})
    finally:
        db.close()

@app.route('/api/ticket/<int:ticket_id>/reply', methods=['POST'])
@login_required
def reply_to_ticket(ticket_id):
    """API для ответа на тикет"""
    try:
        message = request.json.get('message', '')
        attachment_type = request.json.get('attachment_type')
        attachment_file_id = request.json.get('attachment_file_id')
        attachment_url = request.json.get('attachment_url')
        
        if not message and not attachment_type:
            return jsonify({'success': False, 'error': 'Сообщение или вложение обязательно'})
        
        db = SessionLocal()
        try:
            # Получаем тикет
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                return jsonify({'success': False, 'error': 'Тикет не найден'})
            
            if ticket.status != 'open':
                return jsonify({'success': False, 'error': 'Тикет закрыт и не может быть обновлен'})
            
            try:
                # Создаем сообщение от администратора
                ticket_message = TicketMessage(
                    ticket_id=ticket.id,
                    sender_id=None,  # Администратор (через веб-панель)
                    sender_type="admin",
                    message=message,
                    attachment_type=attachment_type,
                    attachment_file_id=attachment_file_id,
                    attachment_url=attachment_url
                )
                db.add(ticket_message)
                
                # Обновляем время последнего обновления тикета
                ticket.updated_at = datetime.utcnow()
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"Ошибка при добавлении сообщения в базу данных: {e}")
                return jsonify({'success': False, 'error': 'Ошибка при сохранении сообщения в базе данных'})
            
            # Отправляем уведомление пользователю через бота
            notification_sent = False
            try:
                # Получаем пользователя
                user = db.query(User).filter(User.id == ticket.user_id).first()
                if user:
                    # Импортируем бота поддержки
                    sys.path.append(os.path.join(os.path.dirname(__file__), 'support_bot'))
                    try:
                        from support_bot.bot import bot as support_bot
                        
                        # Формируем сообщение
                        notification = f"📢 **Новый ответ на ваш тикет #{ticket.ticket_number}**\n\n"
                        notification += f"От: Поддержка\n"
                        notification += f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        if message:
                            notification += f"Сообщение:\n{message}\n\n"
                        if attachment_type:
                            attachment_names = {
                                'photo': '📷 Фото',
                                'video': '🎥 Видео',
                                'document': '📄 Документ'
                            }
                            notification += f"{attachment_names.get(attachment_type, '📎 Вложение')} прикреплено\n\n"
                        notification += "Ответьте на это сообщение, чтобы продолжить диалог."
                        
                        # Отправляем сообщение
                        asyncio.run(support_bot.send_message(
                            user.telegram_id,
                            notification,
                            reply_markup=None
                        ))
                        notification_sent = True
                    except ImportError as e:
                        print(f"Ошибка импорта бота поддержки: {e}")
                    except Exception as e:
                        print(f"Ошибка отправки сообщения через бота: {e}")
            except Exception as e:
                print(f"Ошибка отправки уведомления пользователю: {e}")
            
            if notification_sent:
                return jsonify({'success': True, 'message': 'Ответ успешно отправлен и уведомление отправлено пользователю'})
            else:
                return jsonify({'success': True, 'message': 'Ответ сохранен, но уведомление пользователю не отправлено'})
        finally:
            db.close()
    except Exception as e:
        print(f"Неожиданная ошибка при обработке ответа на тикет: {e}")
        return jsonify({'success': False, 'error': f'Произошла ошибка при обработке запроса: {str(e)}'})

@app.route('/api/ticket/create', methods=['POST'])
@login_required
def create_ticket():
    """API для создания тикета из админ-панели"""
    try:
        user_id = request.json.get('user_id')
        subject = request.json.get('subject')
        message = request.json.get('message')
        ticket_type = request.json.get('ticket_type', 'support')
        
        if not user_id or not subject or not message:
            return jsonify({'success': False, 'error': 'Необходимые поля не заполнены'})
        
        db = SessionLocal()
        try:
            # Проверяем существование пользователя
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
            # Генерируем номер тикета
            # Получаем количество тикетов + 1
            count = db.query(Ticket).count() + 1
            ticket_number = f"{count:04d}"
            
            # Создаем тикет
            ticket = Ticket(
                ticket_number=ticket_number,
                user_id=user_id,
                status="open",
                ticket_type=ticket_type,
                subject=subject
            )
            db.add(ticket)
            db.flush()  # Получаем ID тикета
            
            # Добавляем первое сообщение
            ticket_message = TicketMessage(
                ticket_id=ticket.id,
                sender_id=None,  # От имени администрации
                sender_type="admin",
                message=message
            )
            db.add(ticket_message)
            db.commit()
            
            # Отправляем уведомление пользователю через бота
            try:
                # Импортируем бота поддержки
                sys.path.append(os.path.join(os.path.dirname(__file__), 'support_bot'))
                from support_bot.bot import bot as support_bot
                
                # Формируем сообщение
                notification = f"📢 **Новый тикет #{ticket_number}**\n\n"
                notification += f"Тема: {subject}\n\n"
                notification += f"Сообщение от поддержки:\n{message}\n\n"
                notification += "Вы можете ответить на это сообщение через бота поддержки."
                
                # Отправляем сообщение
                asyncio.run(support_bot.send_message(
                    user.telegram_id,
                    notification,
                    reply_markup=None
                ))
            except Exception as e:
                print(f"Ошибка отправки уведомления пользователю: {e}")
            
            return jsonify({
                'success': True, 
                'ticket_id': ticket.id,
                'ticket_number': ticket_number,
                'message': 'Тикет успешно создан'
            })
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ticket/<int:ticket_id>/close', methods=['POST'])
@login_required
def close_ticket(ticket_id):
    """API для закрытия тикета"""
    try:
        message = request.json.get('message')
        
        db = SessionLocal()
        try:
            # Получаем тикет
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                return jsonify({'success': False, 'error': 'Тикет не найден'})
            
            if ticket.status == 'closed':
                return jsonify({'success': False, 'error': 'Тикет уже закрыт'})
            
            # Закрываем тикет
            ticket.status = 'closed'
            ticket.closed_at = datetime.utcnow()
            
            # Добавляем системное сообщение о закрытии тикета
            ticket_message = TicketMessage(
                ticket_id=ticket.id,
                sender_id=None,
                sender_type="system",
                message="Тикет был закрыт администратором"
            )
            db.add(ticket_message)
            
            # Если есть сообщение, добавляем его
            if message:
                admin_message = TicketMessage(
                    ticket_id=ticket.id,
                    sender_id=None,
                    sender_type="admin",
                    message=message
                )
                db.add(admin_message)
            
            db.commit()
            
            # Отправляем уведомление пользователю через бота
            try:
                # Получаем пользователя
                user = db.query(User).filter(User.id == ticket.user_id).first()
                if user:
                    # Импортируем бота поддержки
                    sys.path.append(os.path.join(os.path.dirname(__file__), 'support_bot'))
                    from support_bot.bot import bot as support_bot
                    
                    # Формируем сообщение
                    notification = f"🔴 Ваш тикет #{ticket.ticket_number} был закрыт.\n\n"
                    if message:
                        notification += f"Сообщение от поддержки:\n{message}\n\n"
                    notification += "Если у вас возникнут новые вопросы, создайте новый тикет."
                    
                    # Отправляем сообщение
                    asyncio.run(support_bot.send_message(
                        user.telegram_id,
                        notification,
                        reply_markup=None
                    ))
            except Exception as e:
                print(f"Ошибка отправки уведомления пользователю: {e}")
            
            return jsonify({'success': True, 'message': 'Тикет успешно закрыт'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ticket/<int:ticket_id>/delete', methods=['DELETE'])
@login_required
def delete_ticket(ticket_id):
    """API для удаления тикета"""
    try:
        db = SessionLocal()
        try:
            # Получаем тикет
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                return jsonify({'success': False, 'error': 'Тикет не найден'})
            
            # Получаем пользователя для уведомления
            user = db.query(User).filter(User.id == ticket.user_id).first()
            
            # Сначала удаляем записи о прочтении сообщений этого тикета
            db.query(AdminReadMessages).filter(AdminReadMessages.ticket_id == ticket_id).delete()
            
            # Удаляем тикет (каскадное удаление сообщений)
            db.delete(ticket)
            db.commit()
            

            
            return jsonify({'success': True, 'message': 'Тикет успешно удален'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications/count')
@login_required
def get_notifications_count():
    """API для получения количества новых уведомлений"""
    try:
        db = SessionLocal()
        try:
            # Получаем ID администратора из текущего пользователя
            current_user_id = current_user.id
            if current_user_id == 'admin':
                # Для суперадмина получаем его реальный ID из базы
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            # Получаем время последнего просмотра для каждого типа уведомлений
            tickets_viewed = db.query(AdminNotificationsViewed).filter(
                AdminNotificationsViewed.admin_id == admin_id,
                AdminNotificationsViewed.notification_type == 'tickets'
            ).first()
            
            users_viewed = db.query(AdminNotificationsViewed).filter(
                AdminNotificationsViewed.admin_id == admin_id,
                AdminNotificationsViewed.notification_type == 'users'
            ).first()
            
            subscriptions_viewed = db.query(AdminNotificationsViewed).filter(
                AdminNotificationsViewed.admin_id == admin_id,
                AdminNotificationsViewed.notification_type == 'subscriptions'
            ).first()
            
            # Получаем количество новых тикетов с момента последнего просмотра
            tickets_since = tickets_viewed.last_viewed if tickets_viewed else datetime.utcnow() - timedelta(days=30)
            new_tickets = db.query(Ticket).filter(Ticket.created_at >= tickets_since).count()
            
            # Получаем количество новых пользователей (за последние 2 часа и не просмотренных)
            two_hours_ago = datetime.utcnow() - timedelta(hours=2)
            
            # Получаем просмотренных пользователей для текущего админа
            viewed_users = set()
            if admin_id:
                viewed_records = db.query(AdminViewedUsers).filter(AdminViewedUsers.admin_id == admin_id).all()
                viewed_users = {record.user_id for record in viewed_records}
            
            # Подсчитываем новых пользователей
            new_users = db.query(User).filter(
                User.created_at >= two_hours_ago,
                ~User.id.in_(viewed_users) if viewed_users else True
            ).count()
            
            # Получаем количество новых подписок с момента последнего просмотра
            subscriptions_since = subscriptions_viewed.last_viewed if subscriptions_viewed else datetime.utcnow() - timedelta(days=30)
            new_subscriptions = db.query(Subscription).filter(Subscription.created_at >= subscriptions_since).count()
            

            

            
            return jsonify({
                'success': True,
                'tickets': new_tickets,
                'users': new_users,
                'subscriptions': new_subscriptions
            })
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications/new-tickets')
@login_required
def get_new_tickets():
    """API для получения списка новых тикетов"""
    try:
        db = SessionLocal()
        try:
            # Получаем ID администратора из текущего пользователя
            current_user_id = current_user.id
            if current_user_id == 'admin':
                # Для суперадмина получаем его реальный ID из базы
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            # Получаем время последнего просмотра тикетов
            tickets_viewed = db.query(AdminNotificationsViewed).filter(
                AdminNotificationsViewed.admin_id == admin_id,
                AdminNotificationsViewed.notification_type == 'tickets'
            ).first()
            
            tickets_since = tickets_viewed.last_viewed if tickets_viewed else datetime.utcnow() - timedelta(days=30)
            
            # Получаем новые тикеты с информацией о пользователях
            new_tickets = db.query(Ticket).join(User, Ticket.user_id == User.id).filter(
                Ticket.created_at >= tickets_since
            ).all()
            
            tickets_data = []
            for ticket in new_tickets:
                tickets_data.append({
                    'id': ticket.id,
                    'subject': ticket.subject,
                    'user_name': ticket.user.full_name or f'Пользователь {ticket.user.telegram_id}',
                    'created_at': ticket.created_at.strftime('%d.%m.%Y %H:%M')
                })
            
            return jsonify({
                'success': True,
                'tickets': tickets_data
            })
        finally:
            db.close()
    except Exception as e:
                    return jsonify({'success': False, 'error': str(e)})

@app.route('/api/tickets')
@login_required
def get_tickets_list():
    """API для получения списка тикетов"""
    try:
        db = SessionLocal()
        try:
            # Получаем ID администратора из текущего пользователя
            current_user_id = current_user.id
            if current_user_id == 'admin':
                # Для суперадмина получаем его реальный ID из базы
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            # Получаем все тикеты с информацией о пользователях и сообщениях
            tickets = db.query(Ticket).join(User, Ticket.user_id == User.id).all()
            
            tickets_data = []
            for ticket in tickets:
                # Подсчитываем общее количество сообщений
                messages_count = db.query(TicketMessage).filter(TicketMessage.ticket_id == ticket.id).count()
                
                # Получаем последнее прочитанное сообщение для этого тикета
                last_read = db.query(AdminReadMessages).filter(
                    AdminReadMessages.admin_id == admin_id,
                    AdminReadMessages.ticket_id == ticket.id
                ).first()
                
                last_read_id = last_read.last_read_message_id if last_read else 0
                
                # Подсчитываем непрочитанные сообщения
                new_messages_count = db.query(TicketMessage).filter(
                    TicketMessage.ticket_id == ticket.id,
                    TicketMessage.id > last_read_id
                ).count()
                
                tickets_data.append({
                    'id': ticket.id,
                    'ticket_number': ticket.ticket_number,
                    'subject': ticket.subject,
                    'status': ticket.status,
                    'user_id': ticket.user_id,
                    'user_name': ticket.user.full_name or f'Пользователь {ticket.user.telegram_id}',
                    'messages_count': messages_count,
                    'new_messages_count': new_messages_count,
                    'created_at': ticket.created_at.isoformat()
                })
            
            return jsonify({
                'success': True,
                'tickets': tickets_data
            })
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications/settings', methods=['GET', 'POST'])
@login_required
def notification_settings():
    """API для работы с настройками уведомлений"""
    try:
        db = SessionLocal()
        try:
            # Получаем ID администратора из текущего пользователя
            current_user_id = current_user.id
            if current_user_id == 'admin':
                # Для суперадмина получаем его реальный ID из базы
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            if request.method == 'GET':
                # Получаем настройки
                settings = db.query(AdminSettings).filter(AdminSettings.admin_id == admin_id).first()
                if not settings:
                    # Создаем настройки по умолчанию
                    settings = AdminSettings(
                        admin_id=admin_id,
                        notifications_enabled=True,
                        sounds_enabled=True,
                        new_ticket_notifications=True,
                        new_user_notifications=True,
                        new_subscription_notifications=True,
                        new_message_notifications=True,
                        ticket_sound_enabled=True,
                        user_sound_enabled=True,
                        subscription_sound_enabled=True,
                        message_sound_enabled=True
                    )
                    db.add(settings)
                    db.commit()
                
                return jsonify({
                    'success': True,
                    'settings': {
                        'notificationsEnabled': settings.notifications_enabled,
                        'soundsEnabled': settings.sounds_enabled,
                        'newTicketNotifications': settings.new_ticket_notifications,
                        'newUserNotifications': settings.new_user_notifications,
                        'newSubscriptionNotifications': settings.new_subscription_notifications,
                        'newMessageNotifications': settings.new_message_notifications,
                        'ticketSoundEnabled': settings.ticket_sound_enabled,
                        'userSoundEnabled': settings.user_sound_enabled,
                        'subscriptionSoundEnabled': settings.subscription_sound_enabled,
                        'messageSoundEnabled': settings.message_sound_enabled
                    }
                })
            
            elif request.method == 'POST':
                # Сохраняем настройки
                data = request.json
                settings = db.query(AdminSettings).filter(AdminSettings.admin_id == admin_id).first()
                
                if not settings:
                    settings = AdminSettings(admin_id=admin_id)
                    db.add(settings)
                
                settings.notifications_enabled = data.get('notificationsEnabled', True)
                settings.sounds_enabled = data.get('soundsEnabled', True)
                settings.new_ticket_notifications = data.get('newTicketNotifications', True)
                settings.new_user_notifications = data.get('newUserNotifications', True)
                settings.new_subscription_notifications = data.get('newSubscriptionNotifications', True)
                settings.new_message_notifications = data.get('newMessageNotifications', True)
                settings.ticket_sound_enabled = data.get('ticketSoundEnabled', True)
                settings.user_sound_enabled = data.get('userSoundEnabled', True)
                settings.subscription_sound_enabled = data.get('subscriptionSoundEnabled', True)
                settings.message_sound_enabled = data.get('messageSoundEnabled', True)
                
                db.commit()
                
                return jsonify({'success': True})
                
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications/mark-viewed', methods=['POST'])
@login_required
def mark_notifications_viewed():
    """API для отметки уведомлений как просмотренных"""
    try:
        data = request.json
        notification_type = data.get('type')  # 'tickets', 'users', 'subscriptions'
        
        if not notification_type:
            return jsonify({'success': False, 'error': 'Тип уведомления не указан'})
        
        db = SessionLocal()
        try:
            # Получаем ID администратора из текущего пользователя
            current_user_id = current_user.id
            if current_user_id == 'admin':
                # Для суперадмина получаем его реальный ID из базы
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            # Обновляем или создаем запись о просмотре
            viewed_record = db.query(AdminNotificationsViewed).filter(
                AdminNotificationsViewed.admin_id == admin_id,
                AdminNotificationsViewed.notification_type == notification_type
            ).first()
            
            if viewed_record:
                viewed_record.last_viewed = datetime.utcnow()
            else:
                viewed_record = AdminNotificationsViewed(
                    admin_id=admin_id,
                    notification_type=notification_type
                )
                db.add(viewed_record)
            
            db.commit()
            return jsonify({'success': True, 'message': 'Уведомления отмечены как просмотренные'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/user/<int:user_id>/mark-viewed', methods=['POST'])
@login_required
def mark_user_viewed(user_id):
    """API для отметки пользователя как просмотренного"""
    try:
        db = SessionLocal()
        try:
            # Получаем ID администратора из текущего пользователя
            current_user_id = current_user.id
            if current_user_id == 'admin':
                # Для суперадмина получаем его реальный ID из базы
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            # Проверяем, что пользователь существует
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
            # Проверяем, не отмечен ли уже пользователь как просмотренный
            existing_record = db.query(AdminViewedUsers).filter(
                AdminViewedUsers.admin_id == admin_id,
                AdminViewedUsers.user_id == user_id
            ).first()
            
            if not existing_record:
                # Создаем запись о просмотре
                viewed_record = AdminViewedUsers(
                    admin_id=admin_id,
                    user_id=user_id
                )
                db.add(viewed_record)
                db.commit()
            
            return jsonify({'success': True, 'message': 'Пользователь отмечен как просмотренный'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/user/<int:user_id>/remove_coins', methods=['POST'])
@login_required
def remove_coins_from_user(user_id):
    """API для списания монет у пользователя"""
    try:
        data = request.json
        coins_to_remove = data.get('coins', 0)
        
        if coins_to_remove <= 0:
            return jsonify({'success': False, 'error': 'Количество монет должно быть положительным'})
        
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return jsonify({'success': False, 'error': 'Пользователь не найден'})
            
            if user.bonus_coins < coins_to_remove:
                return jsonify({'success': False, 'error': 'Недостаточно монет для списания'})
            
            user.bonus_coins -= coins_to_remove
            db.commit()
            
            return jsonify({
                'success': True,
                'message': f'Списано {coins_to_remove} монет',
                'new_balance': user.bonus_coins
            })
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications/new-messages')
@login_required
def get_new_messages_count():
    """API для получения количества новых сообщений в тикетах"""
    try:
        db = SessionLocal()
        try:
            # Получаем ID администратора из текущего пользователя по единому правилу
            current_user_id = current_user.id
            if current_user_id == 'admin':
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            # Получаем все тикеты с новыми сообщениями
            tickets_with_new_messages = []
            
            # Получаем все тикеты
            tickets = db.query(Ticket).filter(Ticket.status == 'open').all()
            
            for ticket in tickets:
                # Получаем последнее сообщение в тикете
                last_message = db.query(TicketMessage).filter(
                    TicketMessage.ticket_id == ticket.id
                ).order_by(TicketMessage.id.desc()).first()
                
                if not last_message:
                    continue
                
                # Проверяем, читал ли администратор это сообщение
                read_record = db.query(AdminReadMessages).filter(
                    AdminReadMessages.admin_id == admin_id,
                    AdminReadMessages.ticket_id == ticket.id
                ).first()
                
                if not read_record or read_record.last_read_message_id < last_message.id:
                    # Есть новые сообщения
                    new_messages_count = db.query(TicketMessage).filter(
                        TicketMessage.ticket_id == ticket.id,
                        TicketMessage.id > (read_record.last_read_message_id if read_record else 0)
                    ).count()
                    
                    # Создаем превью сообщения
                    message_preview = last_message.message[:100] + '...' if len(last_message.message) > 100 else last_message.message
                    
                    tickets_with_new_messages.append({
                        'ticket_id': ticket.id,
                        'ticket_number': ticket.ticket_number,
                        'subject': ticket.subject,
                        'user_name': ticket.user.full_name if ticket.user else 'Неизвестный',
                        'new_messages_count': new_messages_count,
                        'last_message_preview': message_preview,
                        'last_message_time': last_message.created_at.isoformat()
                    })
            
            return jsonify({
                'success': True,
                'tickets_with_new_messages': tickets_with_new_messages,
                'total_new_messages': sum(t['new_messages_count'] for t in tickets_with_new_messages)
            })
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/notifications/messages-count')
@login_required
def get_messages_count():
    """API для получения количества непрочитанных сообщений"""
    try:
        db = SessionLocal()
        try:
            # Получаем ID администратора из текущего пользователя по единому правилу
            current_user_id = current_user.id
            if current_user_id == 'admin':
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            # Получаем общее количество непрочитанных сообщений
            total_new_messages = 0
            
            # Получаем все тикеты
            tickets = db.query(Ticket).filter(Ticket.status == 'open').all()
            
            for ticket in tickets:
                # Получаем последнее сообщение в тикете
                last_message = db.query(TicketMessage).filter(
                    TicketMessage.ticket_id == ticket.id
                ).order_by(TicketMessage.id.desc()).first()
                
                if not last_message:
                    continue
                
                # Проверяем, читал ли администратор это сообщение
                read_record = db.query(AdminReadMessages).filter(
                    AdminReadMessages.admin_id == admin_id,
                    AdminReadMessages.ticket_id == ticket.id
                ).first()
                
                if not read_record or read_record.last_read_message_id < last_message.id:
                    # Есть новые сообщения
                    new_messages_count = db.query(TicketMessage).filter(
                        TicketMessage.ticket_id == ticket.id,
                        TicketMessage.id > (read_record.last_read_message_id if read_record else 0)
                    ).count()
                    
                    total_new_messages += new_messages_count
            
            return jsonify({
                'success': True,
                'count': total_new_messages
            })
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/ticket/<int:ticket_id>/mark-read', methods=['POST'])
@login_required
def mark_ticket_as_read(ticket_id):
    """API для отметки тикета как прочитанного"""
    try:
        db = SessionLocal()
        try:
            # Унифицированное определение admin_id как в других эндпоинтах
            current_user_id = current_user.id
            if current_user_id == 'admin':
                admin = db.query(Admin).filter(Admin.is_superadmin == True, Admin.is_active == True).first()
                if not admin:
                    return jsonify({'success': False, 'error': 'Администратор не найден'})
                admin_id = admin.id
            else:
                admin_id = int(current_user_id)
            
            # Получаем последнее сообщение в тикете
            last_message = db.query(TicketMessage).filter(
                TicketMessage.ticket_id == ticket_id
            ).order_by(TicketMessage.id.desc()).first()
            
            if not last_message:
                return jsonify({'success': False, 'error': 'Тикет не найден'})
            
            # Обновляем или создаем запись о прочтении
            read_record = db.query(AdminReadMessages).filter(
                AdminReadMessages.admin_id == admin_id,
                AdminReadMessages.ticket_id == ticket_id
            ).first()
            
            if read_record:
                read_record.last_read_message_id = last_message.id
                read_record.read_at = datetime.utcnow()
            else:
                read_record = AdminReadMessages(
                    admin_id=admin_id,
                    ticket_id=ticket_id,
                    last_read_message_id=last_message.id
                )
                db.add(read_record)
            
            db.commit()
            return jsonify({'success': True, 'message': 'Тикет отмечен как прочитанный'})
        finally:
            db.close()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ===== Socket.IO Events =====

@socketio.on('tickets:join')
def ws_join_ticket(data):
    ticket_id = str(data.get('ticket_id'))
    join_room(f"ticket:{ticket_id}")
    emit('tickets:joined', {'ticket_id': ticket_id})

# ===== API для массовых уведомлений =====

@app.route('/api/notifications/stats')
@login_required
def notifications_stats():
    """API для получения статистики уведомлений"""
    db = SessionLocal()
    try:
        total_users = db.query(User).count()
        active_subscriptions = db.query(Subscription).filter(Subscription.status == "active").count()
        
        # Статистика уведомлений
        sent_today = db.query(MassNotification).filter(
            MassNotification.created_at >= datetime.utcnow().date()
        ).count()
        total_sent = db.query(MassNotification).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'active_subscriptions': active_subscriptions,
                'sent_today': sent_today,
                'total_sent': total_sent
            }
        })
    finally:
        db.close()

@app.route('/api/notifications/recipients-count')
@login_required
def notifications_recipients_count():
    """API для получения количества получателей по типу"""
    recipient_type = request.args.get('type', 'all')
    db = SessionLocal()
    try:
        if recipient_type == 'all':
            count = db.query(User).count()
        elif recipient_type == 'active':
            count = db.query(User).join(Subscription).filter(
                Subscription.status == "active",
                Subscription.expires_at > datetime.utcnow()
            ).distinct().count()
        elif recipient_type == 'expired':
            count = db.query(User).join(Subscription).filter(
                Subscription.status == "expired"
            ).distinct().count()
        elif recipient_type == 'new':
            week_ago = datetime.utcnow() - timedelta(days=7)
            count = db.query(User).filter(User.created_at >= week_ago).count()
        elif recipient_type == 'admins':
            count = db.query(User).filter(User.telegram_id.in_(ADMIN_IDS)).count()
        else:
            count = 0
        
        return jsonify({
            'success': True,
            'count': count
        })
    finally:
        db.close()

@app.route('/api/notifications/send', methods=['POST'])
@login_required
def send_notification():
    """API для отправки массового уведомления"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Нет данных'})
    
    title = data.get('title', '').strip()
    message = data.get('message', '').strip()
    recipient_type = data.get('recipient_type', 'all')
    
    if not title or not message:
        return jsonify({'success': False, 'message': 'Заголовок и сообщение обязательны'})
    
    db = SessionLocal()
    try:
        # Получаем список пользователей по типу
        if recipient_type == 'all':
            users = db.query(User).all()
        elif recipient_type == 'active':
            users = db.query(User).join(Subscription).filter(
                Subscription.status == "active",
                Subscription.expires_at > datetime.utcnow()
            ).distinct().all()
        elif recipient_type == 'expired':
            users = db.query(User).join(Subscription).filter(
                Subscription.status == "expired"
            ).distinct().all()
        elif recipient_type == 'new':
            week_ago = datetime.utcnow() - timedelta(days=7)
            users = db.query(User).filter(User.created_at >= week_ago).all()
        elif recipient_type == 'admins':
            # Получаем администраторов из ADMIN_IDS
            users = db.query(User).filter(User.telegram_id.in_(ADMIN_IDS)).all()
        else:
            return jsonify({'success': False, 'message': 'Неверный тип получателей'})
        
        # Создаем запись об уведомлении
        notification = MassNotification(
            title=title,
            message=message,
            recipient_type=recipient_type,
            total_count=len(users),
            sent_count=0,
            status="in_progress",
            created_by=current_user.id if hasattr(current_user, 'id') else None
        )
        db.add(notification)
        db.commit()
        
        # Отправляем уведомления асинхронно
        import threading
        thread = threading.Thread(
            target=send_notifications_async,
            args=(notification.id, title, message, [user.telegram_id for user in users])
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Уведомление поставлено в очередь',
            'sent_count': 0,
            'total_count': len(users)
        })
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'})
    finally:
        db.close()

def send_notifications_async(notification_id, title, message, telegram_ids):
    """Асинхронная отправка уведомлений"""
    import asyncio
    import nest_asyncio
    
    # Применяем патч для вложенных event loops
    nest_asyncio.apply()
    
    async def send_notifications():
        from aiogram import Bot
        from dotenv import load_dotenv
        load_dotenv()
        
        # Пытаемся получить токен из переменных окружения
        bot_token = os.getenv('BOT_TOKEN')
        if not bot_token:
            # Если не найден в переменных окружения, берем из config.py
            try:
                from config import BOT_TOKEN
                bot_token = BOT_TOKEN
                logger.info(f"Используем BOT_TOKEN из config.py: {bot_token[:20]}...")
            except ImportError:
                logger.error("BOT_TOKEN не найден ни в переменных окружения, ни в config.py")
                return
        
        bot = Bot(token=bot_token)
        db = SessionLocal()
        
        try:
            notification = db.query(MassNotification).filter(MassNotification.id == notification_id).first()
            if not notification:
                logger.error(f"Уведомление {notification_id} не найдено")
                return
            
            sent_count = 0
            total_count = len(telegram_ids)
            
            # Формируем полное сообщение (без тега <br>, который не поддерживается Telegram HTML)
            full_message = f"<b>{title}</b>\n\n{message}\n\n<i>С уважением,\nкоманда разработки SeaVPN</i>"
            
            for telegram_id in telegram_ids:
                try:
                    await bot.send_message(
                        chat_id=telegram_id,
                        text=full_message,
                        parse_mode="HTML"
                    )
                    sent_count += 1
                    
                    # Обновляем счетчик каждые 10 отправок
                    if sent_count % 10 == 0:
                        notification.sent_count = sent_count
                        db.commit()
                        
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления пользователю {telegram_id}: {e}")
            
            # Обновляем статус
            notification.sent_count = sent_count
            notification.status = "completed"
            notification.completed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Уведомление {notification_id} отправлено: {sent_count}/{total_count}")
            
        except Exception as e:
            logger.error(f"Ошибка в send_notifications_async: {e}")
            if notification:
                notification.status = "error"
                db.commit()
        finally:
            db.close()
            await bot.session.close()
    
    # Запускаем асинхронную функцию
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(send_notifications())
    except Exception as e:
        logger.error(f"Ошибка запуска асинхронной функции: {e}")
    finally:
        loop.close()

@app.route('/api/notifications/<int:notification_id>')
@login_required
def get_notification_details(notification_id):
    """API для получения деталей уведомления"""
    db = SessionLocal()
    try:
        notification = db.query(MassNotification).filter(MassNotification.id == notification_id).first()
        if not notification:
            return jsonify({'success': False, 'message': 'Уведомление не найдено'})
        
        return jsonify({
            'success': True,
            'notification': {
                'id': notification.id,
                'title': notification.title,
                'message': notification.message,
                'recipient_type': notification.recipient_type,
                'total_count': notification.total_count,
                'sent_count': notification.sent_count,
                'status': notification.status,
                'created_at': notification.created_at.strftime('%d.%m.%Y %H:%M') if notification.created_at else None,
                'completed_at': notification.completed_at.strftime('%d.%m.%Y %H:%M') if notification.completed_at else None
            }
        })
    finally:
        db.close()

@app.route('/api/notifications/<int:notification_id>/delete', methods=['DELETE'])
@login_required
def delete_notification(notification_id):
    """API для удаления уведомления"""
    db = SessionLocal()
    try:
        notification = db.query(MassNotification).filter(MassNotification.id == notification_id).first()
        if not notification:
            return jsonify({'success': False, 'message': 'Уведомление не найдено'})
        
        # Удаляем уведомление
        db.delete(notification)
        db.commit()
        
        return jsonify({'success': True, 'message': 'Уведомление удалено'})
    except Exception as e:
        logger.error(f"Ошибка удаления уведомления: {e}")
        return jsonify({'success': False, 'message': f'Ошибка: {str(e)}'})
    finally:
        db.close()

# ===== Внутренний хук для уведомлений из других процессов (бот и т.п.) =====

@app.post('/internal/notify')
def internal_notify():
    """
    JSON:
    {
      "ticket_id": "123",
      "message_id": "456",
      "preview": "Короткий текст",
      "author": "user|operator"
    }
    или
    {
      "type": "new_user",
      "user_id": "123",
      "full_name": "Имя",
      "phone": "Телефон",
      "email": "Email"
    }
    """
    data = request.get_json(force=True) or {}
    logger.info(f"[INTERNAL_NOTIFY] Получены данные: {data}")
    
    # Проверяем тип уведомления
    notify_type = data.get('type')
    if notify_type == 'new_user':
        # Уведомление о новом пользователе
        payload = {
            "user_id": data.get('user_id'),
            "full_name": data.get('full_name'),
            "phone": data.get('phone'),
            "email": data.get('email'),
        }
        logger.info(f"[INTERNAL_NOTIFY] Отправляем users:badge_inc: {payload}")
        socketio.emit('users:badge_inc', payload)
        return ('', 204)
    elif notify_type == 'new_ticket':
        # Уведомление о новом тикете
        ticket_id = str(data.get('ticket_id', ''))
        payload = {"ticket_id": ticket_id}
        logger.info(f"[INTERNAL_NOTIFY] Отправляем tickets:badge_inc: {payload}")
        socketio.emit('tickets:badge_inc', payload)
        return ('', 204)
    else:
        # Уведомление о новом сообщении в тикете
        ticket_id = str(data.get('ticket_id', ''))
        message_id = data.get('message_id')
        payload = {
            "ticket_id": ticket_id,
            "message_id": message_id,
            "preview": data.get('preview'),
            "author": data.get('author'),
        }

        # Защита: если это первое сообщение тикета (создание тикета), не отправляем как new_message
        try:
            db = SessionLocal()
            try:
                # Найдём самое раннее сообщение этого тикета
                first_msg = db.query(TicketMessage).filter(TicketMessage.ticket_id == int(ticket_id)).order_by(TicketMessage.id.asc()).first()
                if first_msg and message_id and str(first_msg.id) == str(message_id):
                    logger.info(f"[INTERNAL_NOTIFY] Пропускаем ticket:new_message для первого сообщения тикета {ticket_id}")
                    return ('', 204)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"[INTERNAL_NOTIFY] Ошибка проверки первого сообщения: {e}")

        logger.info(f"[INTERNAL_NOTIFY] Отправляем ticket:new_message: {payload}")
        # Отправляем глобально всем подключенным клиентам
        socketio.emit('ticket:new_message', payload)
        # Глобально бейдж тикетов НЕ увеличиваем, это именно новое сообщение
        return ('', 204)

if __name__ == '__main__':
    # Создаем папку для шаблонов если её нет
    os.makedirs('templates', exist_ok=True)
    
    # Для Socket.IO нужен eventlet/gevent
    import eventlet
    import eventlet.wsgi  # noqa
    
    # Настройки Socket.IO
    socketio.run(
        app, 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", 8080)),
        debug=False,
        use_reloader=False,
        log_output=True
    )
