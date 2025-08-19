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
        if not message:
            return jsonify({'success': False, 'error': 'Сообщение не может быть пустым'})
        
        db = SessionLocal()
        try:
            # Получаем тикет
            ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
            if not ticket:
                return jsonify({'success': False, 'error': 'Тикет не найден'})
            
            if ticket.status != 'open':
                return jsonify({'success': False, 'error': 'Тикет закрыт и не может быть обновлен'})
            
            # Создаем сообщение от администратора
            ticket_message = TicketMessage(
                ticket_id=ticket.id,
                sender_id=None,  # Администратор (через веб-панель)
                sender_type="admin",
                message=message
            )
            db.add(ticket_message)
            
            # Обновляем время последнего обновления тикета
            ticket.updated_at = datetime.utcnow()
            db.commit()
            
            # Отправляем уведомление пользователю через бота
            try:
                # Получаем пользователя
                user = db.query(User).filter(User.id == ticket.user_id).first()
                if user:
                    # Импортируем бота поддержки
                    sys.path.append(os.path.join(os.path.dirname(__file__), 'support_bot'))
                    from support_bot.bot import bot as support_bot
                    
                    # Отправляем сообщение
                    asyncio.run(support_bot.send_message(
                        user.telegram_id,
                        f"📢 **Новый ответ на ваш тикет #{ticket.ticket_number}**\n\n"
                        f"От: Поддержка\n"
                        f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"Сообщение:\n{message}",
                        reply_markup=None
                    ))
            except Exception as e:
                print(f"Ошибка отправки уведомления пользователю: {e}")
            
            return jsonify({'success': True, 'message': 'Ответ успешно отправлен'})
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=False)