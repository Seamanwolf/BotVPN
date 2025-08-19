import asyncio
import logging
import uuid
import json
from fastapi import FastAPI, HTTPException, Request
from bot.payment import check_payment_status, process_payment
from bot.validate import validate_init_data
from bot.database import (
    create_pending_payment_ref, get_payment_by_id, get_payment_by_ref,
    get_payment_user, get_pending_payment_by_tg_id, get_user_id,
    get_user_open_payment_pending, get_user_tg_id, mark_payment_processed,
    register_user, save_payment, save_subscription, get_user_subscriptions,
    get_subscriptions_from_db, update_payment_pending_type,
    update_payment_renewal_data, update_payment_status,
    update_payment_status_by_id, update_payment_status_by_ref,
    update_subscription_in_db, get_user_receipt_email, update_receipt_email,
    delete_subscription_from_db, get_subscription_by_sub_id, init_db
)
from bot.panel import (
    add_client_to_panel, extend_client_subscription, login_to_panel, 
    get_client_traffic, get_client_traffic_all_servers, generate_mix_link,
    extend_client_subscription_all_servers, delete_client_multi_servers,
    SERVERS, add_client_to_server, delete_client
)
from bot.subscriptions import SUB
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, RedirectResponse
from datetime import datetime, timedelta
import os
from bot.admin import admin_router, is_admin
from bot.adm_db import is_admin_user, get_admin_subscription_by_tg_id
from typing import Optional

# Настройка базового логирования
logging.basicConfig(
    level=logging.INFO,  # Установите уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

app = FastAPI()

# Добавляем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lunetra.online",  # Домен вашего проекта
        "https://web.telegram.org",  # Telegram веб-домен
        "https://webk.telegram.org",  # Telegram WebK
        "https://t.me",  # Telegram короткий домен
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Путь к директории со статическими файлами фронтенда
frontend_dir = os.path.abspath("../frontend/public")

# Подключаем директорию как статические файлы
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
else:
    logging.warning(f"Directory '{frontend_dir}' does not exist")

# Маршрут для возврата index.html из фронтенда
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.post("/api/validate/")
async def validate(request: Request):
    data = await request.json()
    init_data = data.get("initData")

    if validate_init_data(init_data):
        return {"status": "success", "message": "Data is valid"}
    else:
        raise HTTPException(status_code=400, detail="Invalid initData")


@app.post("/api/subscribe/")
async def subscribe(request: Request):
    data = await request.json()
    tg_id = data.get("tg_id")
    plan = data.get("plan")
    username = data.get("username")
    return_url = data.get("return_url")
    user_email = await get_user_receipt_email(tg_id) # Получаем email пользователя
    renewal_data = data.get("renewalData")  # Передаётся с фронтенда при продлении

    plan_durations = {
        "sub_1": 30,
        "sub_3": 90,
        "sub_6": 180,
    }
    days = plan_durations.get(plan)
    if not days:
        raise HTTPException(status_code=400, detail="Неверный план подписки.")

    # Проверка пользователя
    user_id = await get_user_id(tg_id)
    if not user_id:
        registered = await register_user(tg_id, username)
        if not registered:
            raise HTTPException(status_code=500, detail="Ошибка при регистрации пользователя.")
        user_id = await get_user_id(tg_id)

    # Ищем pending платёж по этому плану
    pending_payment = await get_user_open_payment_pending(tg_id, plan)
    if pending_payment:
        # Проверяем expires_at
        expires_at = pending_payment.get("expires_at")
        if expires_at:
            now_ts = datetime.now()
            if (now_ts < expires_at):
                # Ссылка ещё действует, возвращаем старую payment_url
                old_url = pending_payment.get("payment_url")
                if old_url:
                    return JSONResponse({
                        "status": "pending_already",
                        "detail": "У вас уже есть незавершённый платеж по этому тарифу, он ещё не истек.",
                        "payment_url": old_url
                    })
                else:
                    # Теоретически если нет ссылки, но pending
                    # Можем попросить "Отменить и создать заново"
                    return JSONResponse({
                        "status": "pending_already",
                        "detail": "У вас уже есть незавершённый платеж, но нет ссылки. Попробуйте отменить или подождать."
                    })
            else:
                # Срок вышел => ставим canceled
                await update_payment_status_by_id(pending_payment["payment_id"], "canceled")
                logging.info(f"Платеж {pending_payment['payment_id']} просрочен, ставим canceled.")

    # (Если дошли сюда — либо нет pending, либо он истек и мы отменили.)

    # Определяем тип платежа: 'renewal' если renewal_data передано, иначе 'new'
    pending_type = "renewal" if renewal_data else "new"

    plan_info = SUB.get(plan)
    price = plan_info["price"]
    description = plan_info["text"]

    # Если renewal_data, добавим приписку "Продление"
    if renewal_data:
        description = f"[Продление] {description}"

    # Генерируем payment_ref
    payment_ref = str(uuid.uuid4())

    # expires_at = +11 минут
    expires_at = datetime.now() + timedelta(minutes=11)

    # Создаём "черновой" платёж
    saved = await create_pending_payment_ref(
        user_id=user_id,
        payment_ref=payment_ref,
        amount=price,
        status="pending",
        description=description,
        plan=plan,
        expires_at=expires_at,
        pending_type=pending_type
    )
    if not saved:
        raise HTTPException(status_code=500, detail="Не удалось создать запись о платеже.")
    
    # Сохраняем renewal_data, если передано
    if renewal_data:
        updated_renewal = await update_payment_renewal_data(payment_ref, renewal_data)
        if not updated_renewal:
            logging.warning(f"Не удалось сохранить renewal_data для платежа {payment_ref}")

    FRONTEND_DOMAIN = "https://lunetra.online"
    return_url = f"{FRONTEND_DOMAIN}/payment-result?ref={payment_ref}"

    try:
        # Создаём платёж в ЮKassa
        payment_url, yk_pid = await process_payment(
            amount=price,
            description=description,
            return_url=return_url,
            user_email=user_email,
            payment_ref=payment_ref
        )
        return {"status": "pending", "payment_url": payment_url}
    except Exception as e:
        logging.error(f"Ошибка при создании платежа: {e}")
        raise HTTPException(status_code=500, detail="Ошибка создания платежа.")


@app.get("/api/payment/result")
async def payment_result(ref: str):
    """
    Когда пользователь возвращается на /payment-result?ref=<payment_ref>
    фронтенд дергает этот метод, чтобы узнать, оплачен ли уже платёж и получить подписку.
    """
    payment_entry = await get_payment_by_ref(ref)
    if not payment_entry:
        logging.error(f"[payment_result] Payment ref={ref} not found")
        raise HTTPException(status_code=404, detail="Платёж не найден.")

    yookassa_pid = payment_entry["payment_id"]  # это поле payment_id (YooKassa)
    if not yookassa_pid:
        # значит ещё не был прописан; крайне редкий случай
        logging.error(f"[payment_result] No YooKassa payment_id for ref={ref}")
        return {"status": "failed"}

    # Если платеж уже обработан, получаем подписку и возвращаем
    if payment_entry.get("processed"):
        logging.info(f"[payment_result] Payment {yookassa_pid} already processed")
        return await get_subscription_data(payment_entry)

    # Если платеж находится в процессе обработки (например, через webhook)
    # ждем секунду и возвращаем соответствующий статус
    if payment_entry.get("status") == "processing":
        logging.info(f"[payment_result] Payment {yookassa_pid} is currently processing, waiting...")
        # Даем немного времени на завершение обработки
        await asyncio.sleep(1)
        
        # Перечитываем статус
        payment_entry = await get_payment_by_ref(ref)
        if payment_entry.get("processed"):
            logging.info(f"[payment_result] Payment {yookassa_pid} was processed while waiting")
            return await get_subscription_data(payment_entry)
        else:
            return {"status": "processing", "message": "Платеж в процессе обработки, попробуйте обновить страницу"}

    # Проверяем статус (если используете webhook, он мог уже быть succeeded; но проверим ещё раз)
    is_succeeded = await check_payment_status(yookassa_pid)
    if not is_succeeded:
        logging.warning(f"[payment_result] Payment {yookassa_pid} is not succeeded")
        return {"status": "failed"}

    # Обновляем статус (если ещё не обновлён)
    if payment_entry["status"] != "succeeded":
        logging.info(f"[payment_result] Updating payment {yookassa_pid} status to succeeded")
        await update_payment_status_by_ref(ref, "succeeded")
        
    # Проверяем, обработан ли уже платеж (создана ли подписка)
    if not payment_entry.get("processed"):
        # Если платеж еще не processed, значит подписка не создана
        # В этом случае надо запустить обработку платежа
        logging.info(f"[payment_result] Starting processing payment {yookassa_pid}")
        try:
            await payment_success(yookassa_pid)
            logging.info(f"[payment_result] Successfully processed payment {yookassa_pid}")
        except Exception as e:
            logging.error(f"[payment_result] Failed to process payment {yookassa_pid}: {str(e)}")
            return {"status": "failed"}
        
        # Обновляем информацию о платеже после обработки
        payment_entry = await get_payment_by_ref(ref)
        if not payment_entry.get("processed"):
            logging.error(f"[payment_result] Payment {yookassa_pid} not marked as processed after payment_success")
            return {"status": "failed"}

    # Возвращаем информацию о подписке
    return await get_subscription_data(payment_entry)


# Вспомогательная функция для получения данных подписки
async def get_subscription_data(payment_entry):
    """Получает информацию о подписке из платежа"""
    yookassa_pid = payment_entry["payment_id"]

    # Извлекаем данные пользователя
    user_id = await get_payment_user(yookassa_pid)
    if not user_id:
        logging.error(f"[get_subscription_data] User not found for payment {yookassa_pid}")
        return {"status": "failed"}
        
    tg_id = await get_user_tg_id(user_id)
    if not tg_id:
        logging.error(f"[get_subscription_data] Telegram ID not found for user {user_id}")
        return {"status": "failed"}

    # Проверяем, есть ли renewal_data
    renewal_data_raw = payment_entry.get("renewal_data")  # строка JSON или None
    is_renewal = bool(renewal_data_raw)

    if is_renewal:
        # 1) Преобразуем строку в dict
        try:
            renewal_data_dict = json.loads(renewal_data_raw) if renewal_data_raw else {}
        except json.JSONDecodeError:
            logging.exception("[get_subscription_data] Не удалось декодировать renewal_data.")
            return {"status": "failed"}

        # 2) Извлекаем sub_id, end_date (если надо), etc.
        subscription_data = renewal_data_dict.get("subscription", {})
        sub_id = subscription_data.get("sub_id")

        # 3) days можно взять так же, как вы делаете в subscribe() или payment_success()
        plan = payment_entry["plan"]  # тот же plan, что и при /api/subscribe
        plan_durations = {
            "sub_1": 30,
            "sub_3": 90,
            "sub_6": 180,
        }
        days = plan_durations.get(plan, 0)

        if not sub_id or not days:
            # Если чего-то нет, отдаём ошибку
            logging.error(f"[get_subscription_data] No sub_id or days for renewal payment {yookassa_pid}")
            return {"status": "failed"}

        # Если это продление, не нужно link, а лишь "isRenewal"
        return {
            "status": "success", 
            "isRenewal": True, 
            "subscriptionName": sub_id, 
            "days": days,
            "renewalData": {  # Оставляем для обратной совместимости
                "subscriptionName": sub_id,
                "days": days
            }
        }
    else:
        # Для новой подписки находим самую последнюю подписку пользователя
        # Она должна быть создана в payment_success
        subscriptions = await get_subscriptions_from_db(tg_id)
        if not subscriptions:
            logging.error(f"[get_subscription_data] No subscriptions found for user {tg_id} after payment")
            return {"status": "failed"}
            
        latest_subscription = subscriptions[-1]  # Берём последнюю подписку
        
        # Формируем объект subscription для фронтенда
        subscription = {
            "sub_id": latest_subscription.get("sub_id"),
            "mix_link": latest_subscription.get("mix_link"),
            "end_date": str(latest_subscription.get("end_date")),
            "servers_data": latest_subscription.get("servers_data", {})
        }
        
        # Возвращаем ссылку и объект подписки для фронтенда
        return {
            "status": "success",
            "isRenewal": False,
            "link": latest_subscription.get("mix_link") or latest_subscription.get("link_key"),  # Предпочитаем mix_link, если доступно
            "subscription": subscription  # Данные для компонента SubscriptionLinkPage
        }


@app.post("/api/payment/success/")
async def payment_success(payment_id: str):
    """
    Маршрут, который можно вызывать вручную или из webhook,
    когда статус платежа точно succeeded.
    Здесь создаётся подписка и возвращается готовый link.
    """

    # 1) Берём запись о платеже из БД
    payment_entry = await get_payment_by_id(payment_id)  # или как у вас функция называется
    if not payment_entry:
        logging.error("[payment_success] Payment %s not found", payment_id)
        raise HTTPException(status_code=404, detail="Платеж не найден.")

    # 2) Проверяем, не был ли уже обработан - ВАЖНО: возвращаем успех если уже обработан
    if payment_entry.get("processed"):
        # Если уже processed = true, значит подписка создана, выходим.
        logging.info("[payment_success] Payment %s already processed, returning.", payment_id)
        # Можно вернуть 200 OK, чтобы провайдер не слал заново:
        return {"status": "already_processed"}

    # Проверка статуса платежа
    if not await check_payment_status(payment_id):
        logging.error("[payment_success] Payment %s status is not succeeded", payment_id)
        raise HTTPException(status_code=400, detail="Платеж не завершен.")

    # 3) Сначала помечаем платеж как обрабатываемый, чтобы избежать гонки
    # Это временная метка, которая будет заменена на processed=True по завершении
    await update_payment_status(payment_id, "processing")
    logging.info("[payment_success] Payment %s status set to processing.", payment_id)

    try:
        # Достаём plan, user_id и т.д.
        plan = payment_entry["plan"]
        if not plan:
            raise HTTPException(status_code=400, detail="План подписки не найден.")

        # Логика определения дней и создания подписки
        plan_durations = {
            "sub_1": 30,
            "sub_3": 90,
            "sub_6": 180,
        }
        days = plan_durations.get(plan)
        if not days:
            logging.error("[payment_success] Unknown plan=%s for payment_id=%s", plan, payment_id)
            raise HTTPException(status_code=400, detail="Неверный план подписки.")

        user_id = payment_entry["user_id"]
        if not user_id:
            logging.error("[payment_success] user_id not found in payment_entry for %s", payment_id)
            raise HTTPException(status_code=404, detail="Пользователь не найден в платеже.")

        tg_id = await get_user_tg_id(user_id)
        if not tg_id:
            logging.error("[payment_success] tg_id for user_id=%s not found.", user_id)
            raise HTTPException(status_code=404, detail="Пользователь не найден.")
        logging.info("[payment_success] tg_id=%s, user_id=%s, plan=%s, days=%d", tg_id, user_id, plan, days)

        # Если есть renewal_data – это продление
        raw_renewal_data = payment_entry.get("renewal_data")  # Может быть строка в JSON
        logging.info("[payment_success] raw_renewal_data (possibly string) = %s", raw_renewal_data)

        if raw_renewal_data:
            # 1. Если это строка, декодируем её в dict
            if isinstance(raw_renewal_data, str):
                try:
                    raw_renewal_data = json.loads(raw_renewal_data)
                    logging.info("[payment_success] renewal_data successfully loaded from JSON.")
                except json.JSONDecodeError:
                    logging.exception("[payment_success] Can't decode renewal_data as JSON.")
                    raise HTTPException(status_code=500, detail="Невозможно декодировать renewal_data как JSON.")

            # 2. Извлекаем subscription-данные (sub_id, end_date)
            subscription_data = raw_renewal_data.get("subscription")
            if not subscription_data:
                logging.error("[payment_success] No 'subscription' field in renewal_data.")
                raise HTTPException(status_code=400, detail="В renewal_data отсутствует поле subscription.")

            sub_id = subscription_data.get("sub_id")
            end_date_str = subscription_data.get("end_date")
            if not sub_id or not end_date_str:
                logging.error("[payment_success] sub_id or end_date missing in subscription_data: %s", subscription_data)
                raise HTTPException(status_code=400, detail="В subscription не найден sub_id или end_date.")

            logging.info("[payment_success] renewalData => sub_id=%s, end_date=%s, days=%d", sub_id, end_date_str, days)

            # 3. Находим подписку пользователя в локальной БД
            user_subs = await get_subscriptions_from_db(tg_id)
            logging.info("[payment_success] user_subs for tg_id=%s => %s", tg_id, user_subs)
            if not user_subs:
                logging.warning("[payment_success] No subscriptions found in DB for tg_id=%s", tg_id)
                raise HTTPException(status_code=404, detail="У пользователя нет подписок для продления.")

            # 4. Находим нужную подписку по sub_id (локальный ключ)
            matching_sub = next((row for row in user_subs if row["sub_id"] == sub_id), None)
            if not matching_sub:
                logging.error("[payment_success] sub_id=%s not found among user_subs for tg_id=%s", sub_id, tg_id)
                raise HTTPException(status_code=404, detail=f"Подписка sub_id={sub_id} не найдена у пользователя {tg_id}.")

            # 5. Извлекаем данные серверов
            servers_data = matching_sub.get("servers_data", {})
            
            logging.info("[payment_success] matching_sub => %s", matching_sub)
            logging.info("[payment_success] servers_data => %s", servers_data)

            if not servers_data:
                logging.error("[payment_success] No servers_data found in subscription for sub_id=%s, user=%s", sub_id, tg_id)
                raise HTTPException(
                    status_code=400,
                    detail=f"У найденной подписки sub_id={sub_id} отсутствуют данные серверов в БД."
                )

            # 6. Продление на панели (extend_client_subscription)
            logging.info("[payment_success] Calling extend_client_subscription with days=%d, servers_data=%s", days, servers_data)
            panel_result = await extend_client_subscription_all_servers(days, servers_data)
            logging.info("[payment_success] extend_client_subscription => %s", panel_result)

            # Получение успешного результата продления
            if panel_result["success"]:
                # Обновление end_date в БД
                old_end_date = datetime.fromisoformat(str(matching_sub["end_date"]))
                logging.info(f"[payment_success] old_end_date parsed => {old_end_date}")
                
                new_end_date = old_end_date + timedelta(days=days)
                logging.info(f"[payment_success] new_end_date => {new_end_date}")
                
                # Обновляем servers_data, если есть результаты от серверов
                if servers_data and panel_result.get("server_results"):
                    for server_id, result in panel_result["server_results"].items():
                        if result.get("success") and server_id in servers_data:
                            # Обновляем информацию о новой дате истечения, если она есть
                            if "new_expiry_time" in result:
                                servers_data[server_id]["expiryTime"] = result["new_expiry_time"]
                
                # Обновляем подписку в БД с новыми данными серверов
                db_updated = await update_subscription_in_db(sub_id, new_end_date, servers_data)
                
                if db_updated:
                    await mark_payment_processed(payment_id)
                    logging.info(f"[payment_success] Marking payment {payment_id} as processed. "
                                f"Подписка {sub_id} продлена до {new_end_date.strftime('%Y-%m-%d %H:%M:%S')}.")
                    return {
                        "status": "success", 
                        "message": "Подписка успешно продлена",
                        "renewalData": {
                            "subscriptionName": sub_id,
                            "days": days
                        }
                    }
                else:
                    logging.error(f"[payment_success] Failed to update subscription {sub_id} in DB")
                    await update_payment_status(payment_id, "succeeded")
                    raise HTTPException(status_code=500, 
                                      detail="Ошибка при обновлении подписки в базе данных")
            else:
                logging.error(f"[payment_success] Panel extension failed: {panel_result['msg']}")
                await update_payment_status(payment_id, "succeeded")
                raise HTTPException(status_code=500, 
                                  detail=f"Ошибка при продлении подписки на панели: {panel_result['msg']}")

        else:
            # Проверяем лимит подписок и т.д., как у вас
            subscriptions = await get_user_subscriptions(tg_id)
            current_count = len(subscriptions)
            if current_count >= 10:
                raise HTTPException(status_code=400, detail="Превышен лимит подписок.")
            
            # Генерация email
            email = f"{tg_id}_{current_count + 1}"
            
            try:
                # Словарь для хранения данных успешно созданных серверов
                servers_data = {}
                sub_id = None  # будет установлен при создании первого сервера
            
                # Авторизуемся и добавляем клиента на каждый сервер в SERVERS
                for server_id in SERVERS:
                    # Первая итерация - создаем новый клиент
                    if not sub_id:
                        logging.info(f"[payment_success] Начинаем авторизацию на сервере {server_id} для платежа {payment_id}")
                        auth_result = await login_to_panel(server_id)
                        if not auth_result:
                            logging.error(f"[payment_success] Не удалось авторизоваться на сервере {server_id} для платежа {payment_id}")
                            # Пропускаем этот сервер и пробуем следующий
                            continue
                            
                        logging.info(f"[payment_success] Авторизация на сервере {server_id} успешна, создаем клиента для платежа {payment_id}")
                        success, message, link_key, vless_id, new_sub_id = await add_client_to_server(days, tg_id, current_count + 1, email, server_id)
                        
                        if success:
                            logging.info(f"[payment_success] Клиент успешно создан на сервере {server_id}, link_key={link_key}, vless_id={vless_id}, sub_id={new_sub_id}")
                            # Сохраняем данные сервера
                            servers_data[server_id] = {
                                "vless_id": str(vless_id),
                                "link_key": link_key
                            }
                            # Запоминаем sub_id для следующих серверов
                            sub_id = new_sub_id
                        else:
                            logging.error(f"[payment_success] Ошибка при добавлении клиента на сервер {server_id}: {message}")
                            # Пропускаем этот сервер и пробуем следующий
                            continue
                    
                    # Последующие итерации - добавляем клиента с тем же sub_id
                    else:
                        logging.info(f"[payment_success] Начинаем авторизацию на сервере {server_id} для платежа {payment_id}")
                        auth_result = await login_to_panel(server_id)
                        if not auth_result:
                            logging.error(f"[payment_success] Не удалось авторизоваться на сервере {server_id} для платежа {payment_id}")
                            logging.warning(f"[payment_success] Клиент будет доступен не на всех серверах")
                            continue
                            
                        logging.info(f"[payment_success] Авторизация на сервере {server_id} успешна, создаем клиента с существующим sub_id={sub_id}")
                        success, message, link_key, vless_id, _ = await add_client_to_server(days, tg_id, current_count + 1, email, server_id, sub_id)
                        
                        if success:
                            logging.info(f"[payment_success] Клиент успешно создан на сервере {server_id}, link_key={link_key}, vless_id={vless_id}")
                            # Сохраняем данные сервера
                            servers_data[server_id] = {
                                "vless_id": str(vless_id),
                                "link_key": link_key
                            }
                        else:
                            logging.error(f"[payment_success] Ошибка при добавлении клиента на сервер {server_id}: {message}")
                            logging.warning(f"[payment_success] Клиент будет доступен не на всех серверах")
                
                # Проверяем, был ли создан хотя бы один клиент
                if not servers_data:
                    logging.error(f"[payment_success] Не удалось создать клиента ни на одном сервере для платежа {payment_id}")
                    # Устанавливаем статус платежа обратно в succeeded для повторной попытки
                    await update_payment_status(payment_id, "succeeded")
                    raise HTTPException(status_code=500, detail="Не удалось создать подписку ни на одном сервере")
                
                # Генерируем mix-ссылку для всех серверов
                mix_link = generate_mix_link(sub_id)
                logging.info(f"[payment_success] Сгенерирована общая ссылка mix_link={mix_link}")
            
                # Если всё хорошо, сохраняем подписку:
                start_date = datetime.now()
                end_date = start_date + timedelta(days=days)
                
                logging.info(f"[payment_success] Сохраняем подписку в БД, start_date={start_date}, end_date={end_date}")
                logging.info(f"[payment_success] servers_data={servers_data}")
                
                saved = await save_subscription(
                    tg_id=tg_id,
                    sub_id=sub_id,
                    start_date=start_date,
                    end_date=end_date,
                    duration=days,
                    email=email,
                    mix_link=mix_link,
                    servers_data=servers_data  # Новый параметр для масштабируемости
                )
                if not saved:
                    logging.error(f"[payment_success] Ошибка при сохранении подписки в БД для платежа {payment_id}")
                    raise HTTPException(status_code=500, detail="Ошибка при сохранении подписки в БД.")

                # Обновляем флаг processed (важно!)
                logging.info(f"[payment_success] Помечаем платеж {payment_id} как обработанный")
                await mark_payment_processed(payment_id)

                logging.info(f"[payment_success] Подписка для пользователя {tg_id} успешно создана по платежу {payment_id}")
                # Возвращаем данные для фронтенда
                return {
                    "status": "success", 
                    "link": mix_link,
                    "subscription": {
                        "sub_id": sub_id,
                        "mix_link": mix_link,
                        "end_date": end_date.isoformat(),
                        "servers_data": servers_data
                    }
                }
            except Exception as e:
                logging.error(f"[payment_success] Ошибка добавления клиента для платежа {payment_id}: {str(e)}")
                # Устанавливаем статус платежа обратно в succeeded для повторной попытки
                await update_payment_status(payment_id, "succeeded")
                raise
    except Exception as e:
        # В случае ошибки снимаем статус "processing"
        logging.error(f"[payment_success] Error processing payment {payment_id}: {str(e)}")
        await update_payment_status(payment_id, "succeeded")  # Возвращаем статус в "succeeded" для повторной попытки
        raise


@app.post("/api/payment/cancel")
async def cancel_payment(request: Request):
    """
    Отменяет активный платеж по payment_ref.
    """
    data = await request.json()
    payment_ref = data.get("payment_ref")
    if not payment_ref:
        raise HTTPException(status_code=400, detail="Не указан payment_ref.")

    try:
        # Обновляем статус платежа на "canceled"
        success = await update_payment_status_by_ref(payment_ref, "canceled")
        if not success:
            raise HTTPException(status_code=500, detail="Не удалось отменить платёж.")
        logging.info(f"[API] Платёж {payment_ref} успешно отменён.")
        return {"status": "canceled"}
    except Exception as e:
        logging.error(f"[API] Ошибка при отмене платежа {payment_ref}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сервера.")


@app.post("/api/payment/webhook/")
async def payment_webhook(request: Request):
    data = await request.json()

    # Это поле "event" в JSON:
    event = data.get("event")  # например, "payment.succeeded" или "payment.canceled"
    yk_object = data.get("object", {})
    
    payment_id = yk_object.get("id")
    status = yk_object.get("status")

    if not payment_id or not status:
        logging.warning(f"[webhook] Incomplete webhook data received: {data}")
        raise HTTPException(status_code=400, detail="Некорректные данные.")

    # Проверяем, есть ли платеж в БД и был ли он обработан
    payment_entry = await get_payment_by_id(payment_id)
    if not payment_entry:
        logging.warning(f"[webhook] Payment {payment_id} not found in database")
        return {"status": "ok"}  # Не найден - возможно это тестовый вебхук

    # Если платеж уже обработан, просто возвращаем OK
    if payment_entry.get("processed"):
        logging.info(f"[webhook] Payment {payment_id} already processed, ignoring")
        return {"status": "ok"}

    # Обновим статус в нашей БД
    await update_payment_status(payment_id, status)
    logging.info(f"[webhook] Event={event}, payment_id={payment_id}, status={status}")

    if status in ["canceled", "failed"]:
        logging.warning(f"[webhook] Платёж {payment_id} неуспешный: {status}")
        # Опционально: записать причину отмены
        # cancellation_reason = yk_object.get("cancellation_details", {}).get("reason")
        # logging.warning(f"Причина отмены: {cancellation_reason}")
        
        return {"status": "ok"}  # Возвращаем 200 OK, чтобы ЮKassa не слала повторно

    if status == "succeeded":
        # Дополнительная проверка статуса в YooKassa
        yookassa_status = await check_payment_status(payment_id)
        logging.info(f"[webhook] Дополнительная проверка в YooKassa для {payment_id}: {yookassa_status}")
        
        if yookassa_status:
            # Платёж успешен — создаём подписку:
            try:
                payment_result = await payment_success(payment_id)
                logging.info(f"[webhook] Successfully processed payment {payment_id}: {payment_result}")
                
                # Принудительно обновляем статус платежа до succeeded в БД
                await update_payment_status(payment_id, "succeeded")
                logging.info(f"[webhook] Принудительно обновлен статус платежа {payment_id} до succeeded")
            except Exception as e:
                logging.error(f"[webhook] Error processing payment {payment_id}: {str(e)}")
                # Не возвращаем ошибку, чтобы YooKassa не слала повторно
        
        return {"status": "ok"}

    # Если пришёл event, который нас не интересует напрямую, просто ответим OK
    return {"status": "ok"}


@app.get("/api/subscriptions/{tg_id}")
async def get_subscriptions(tg_id: str):
    """Получение подписок пользователя."""
    try:
        logging.info(f"Запрос подписок для пользователя: {tg_id}")
        
        # Сначала проверяем, есть ли у пользователя админские подписки
        admin_subscription = await get_admin_subscription_by_tg_id(int(tg_id))
        
        if admin_subscription:
            logging.info(f"Найдена админ-подписка для пользователя {tg_id}")
            # Проверяем наличие mix_link
            servers_data = admin_subscription["servers_data"]
            if "mix_link" not in servers_data:
                from .bot.panel import generate_mix_link
                mix_link = generate_mix_link(admin_subscription["sub_id"])
                servers_data["mix_link"] = mix_link
                await update_admin_subscription(admin_subscription["sub_id"], servers_data)
                admin_subscription["servers_data"] = servers_data
            
            # Преобразуем admin_subscription в формат, ожидаемый фронтендом
            result = [{
                "sub_id": admin_subscription["sub_id"],
                "tg_id": int(tg_id),
                "email": admin_subscription.get("email", ""),
                "mix_link": servers_data.get("mix_link"),
                "end_date": admin_subscription["end_date"],
                "servers_data": servers_data,
                "is_admin_user": True  # Флаг, указывающий что это "свой" пользователь
            }]
            return result
        
        # Если нет админской подписки, получаем обычные подписки
        subscriptions = await get_subscriptions_from_db(tg_id)
        return subscriptions
    except Exception as e:
        logging.error(f"Ошибка при получении подписок: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении подписок: {str(e)}")


@app.get("/api/subscriptions/get-traffic/{tg_id}")
async def get_traffic(tg_id: int):
    """Получение подписок и трафика по tg_id."""
    try:
        # Проверяем, является ли пользователь "своим" 
        admin_subscription = await get_admin_subscription_by_tg_id(tg_id)
        
        if admin_subscription:
            # Для "своих" пользователей возвращаем безлимитный трафик
            logging.info(f"Обрабатываем запрос трафика для 'своего' пользователя: {tg_id}")
            
            # Получаем данные подписки
            servers_data = admin_subscription.get('servers_data', {})
            
            # Попробуем получить реальный трафик, если есть email
            email = admin_subscription.get('email', '')
            used_gb = 0
            
            if email and servers_data:
                servers_to_check = list(servers_data.keys()) if servers_data else None
                try:
                    # Получаем трафик с серверов, если возможно
                    traffic_result = await get_client_traffic_all_servers(email, servers_to_check)
                    if traffic_result.get("success"):
                        used_gb = traffic_result.get("used_gb", 0)
                except Exception as traffic_err:
                    logging.warning(f"Не удалось получить реальный трафик для 'своего' пользователя {tg_id}: {traffic_err}")
            
            # Для "своих" пользователей устанавливаем безлимитный трафик
            result = [{
                "sub_id": admin_subscription["sub_id"],
                "link": servers_data.get("mix_link", ""),
                "email": email,
                "used_gb": used_gb,  # Реальный трафик, если удалось получить
                "max_gb": "Безлимит",  # Безлимитный трафик
                "is_admin_user": True   # Флаг, что это "свой" пользователь
            }]
            
            return JSONResponse(content={"success": True, "subscriptions": result})
        
        # Получаем обычные подписки из базы данных
        subscriptions = await get_subscriptions_from_db(tg_id)
        
        if not subscriptions:
            return JSONResponse(content={"success": False, "msg": "Подписки не найдены."}, status_code=404)
        
        # Обработка подписок и получение трафика
        result = []
        for sub in subscriptions:
            # Получаем список серверов из servers_data, если есть
            servers_to_check = None
            if sub.get('servers_data'):
                servers_to_check = list(sub['servers_data'].keys())
                
            # Получаем трафик с серверов и суммируем
            traffic_data = await get_client_traffic_all_servers(sub['email'], servers_to_check)
            if traffic_data["success"]:
                result.append({
                    "sub_id": sub["sub_id"],
                    "link": sub.get("mix_link", ""),  # используем mix_link или пустую строку
                    "email": sub["email"],
                    "used_gb": traffic_data["used_gb"],
                    "max_gb": traffic_data["max_gb"],
                    "errors": traffic_data.get("errors"),  # Добавляем информацию об ошибках
                    "is_admin_user": False  # Флаг, указывающий что это обычный пользователь
                })
            else:
                result.append({
                    "sub_id": sub["sub_id"],
                    "link": sub.get("mix_link", ""),  # используем mix_link или пустую строку
                    "email": sub["email"],
                    "used_gb": 0,
                    "max_gb": 100,
                    "error": traffic_data["msg"],
                    "is_admin_user": False  # Флаг, указывающий что это обычный пользователь
                })
        
        return JSONResponse(content={"success": True, "subscriptions": result})
    
    except Exception as e:
        logging.error(f"Ошибка при обработке трафика: {str(e)}")
        return JSONResponse(content={"success": False, "msg": f"Ошибка: {str(e)}"}, status_code=500)



@app.get("/api/payment/pending")
async def get_pending_payment(tg_id: str):
    """
    Проверяет, есть ли активный платеж (pending) у пользователя по tg_id.
    """
    try:
        # Приводим tg_id к целому числу
        tg_id = int(tg_id)
        
        pending_payment = await get_pending_payment_by_tg_id(tg_id)
        if not pending_payment:
            logging.info("[API] Активный платеж не найден.")
            return {"status": "no_pending"}
        
        logging.info(f"[API] Найден активный платёж: {pending_payment}")
        return {
            "status": "pending",
            "payment_ref": pending_payment["payment_ref"],
            "pending_type": pending_payment["pending_type"],
            "payment_url": pending_payment["payment_url"],
            "description": pending_payment["description"]
        }
    except Exception as e:
        logging.error(f"[API] Ошибка проверки платежа: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сервера.")


@app.post("/api/user/receipt-email")
async def save_receipt_email(request: Request):
    data = await request.json()
    tg_id = data.get("tg_id")
    email = data.get("email")

    if not tg_id or not email:
        raise HTTPException(status_code=400, detail="Не указан tg_id или email.")

    try:
        # Преобразуем tg_id в число
        tg_id = int(tg_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат tg_id")

    # Сохраняем email в БД
    success = await update_receipt_email(tg_id, email)
    if not success:
        raise HTTPException(status_code=500, detail="Не удалось сохранить email.")

    return {"status": "success", "message": "Email успешно сохранен."}


@app.get("/api/user/receipt-email/{tg_id}")
async def get_user_email(tg_id: str):
    """Получает email пользователя для чеков."""
    try:
        logging.info(f"Запрос email для tg_id: {tg_id}")
        
        # Преобразование tg_id в int не требуется здесь, 
        # т.к. мы добавили эту логику в get_user_receipt_email
        email = await get_user_receipt_email(tg_id)
        
        if email:
            logging.info(f"Найден email для tg_id {tg_id}: {email}")
            return {"status": "found", "email": email}
        
        logging.info(f"Email для tg_id {tg_id} не найден")
        return {"status": "not_found"}  # Возвращаем 200 OK с status: "not_found"
        
    except Exception as e:
        logging.error(f"Ошибка при запросе email для tg_id {tg_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")


@app.post("/api/user/username")
async def save_username(request: Request):
    """Сохраняет или обновляет username пользователя Telegram."""
    data = await request.json()
    tg_id = data.get("tg_id")
    username = data.get("username")
    
    if not tg_id:
        raise HTTPException(status_code=400, detail="Не указан tg_id")
    
    try:
        # Если username не передан, получаем его из объекта initData
        if not username and "initData" in data:
            from bot.validate import parse_init_data
            init_data = parse_init_data(data.get("initData"))
            if init_data and "user" in init_data:
                username = init_data["user"].get("username")
                logging.info(f"Извлечен username '{username}' из initData для tg_id {tg_id}")
        
        # Проверяем, есть ли что сохранять
        if not username:
            raise HTTPException(status_code=400, detail="Не указан username и не найден в initData")
        
        # Сохраняем username
        from bot.database import update_user_username
        success = await update_user_username(tg_id, username)
        
        if success:
            return {"status": "success", "message": "Username успешно сохранен"}
        else:
            raise HTTPException(status_code=500, detail="Не удалось сохранить username")
    
    except Exception as e:
        logging.error(f"Ошибка при сохранении username для tg_id {tg_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/admin/subscription/{sub_id}")
async def admin_delete_subscription(sub_id: str, request: Request):
    """Удаление подписки администратором."""
    try:
        auth_header = request.headers.get('Authorization')
        token = auth_header.split(' ')[1] if auth_header and ' ' in auth_header else None
        
        if not token or not await is_admin_token(token):
            raise HTTPException(status_code=401, detail="Требуется токен администратора")
        
        # Используем новую функцию для удаления подписки
        result = await delete_subscription(sub_id)
        
        if result["status"] == "success":
            return result
        else:
            raise HTTPException(status_code=500, detail=result["message"])
    
    except Exception as e:
        logging.error(f"Ошибка при удалении подписки {sub_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка при удалении подписки: {str(e)}")

async def delete_subscription(sub_id: str) -> dict:
    # Получаем данные подписки
    subscription = await get_subscription_by_sub_id(sub_id)
    if not subscription:
        logging.error(f"[delete_subscription] Подписка с sub_id={sub_id} не найдена")
        return {"status": "error", "message": "Подписка не найдена"}
    
    # Извлекаем данные серверов
    servers_data = subscription.get("servers_data", {})
    
    # Сначала удаляем из панелей
    all_success = True
    delete_statuses = {}
    
    # Проходим по всем серверам
    for server_id, server_info in servers_data.items():
        vless_id = server_info.get("vless_id")
        if vless_id and server_id in SERVERS:
            success, message = await delete_client(vless_id, server_id)
            delete_statuses[server_id] = {"success": success, "message": message}
            if not success:
                all_success = False
                logging.error(f"[delete_subscription] Ошибка при удалении клиента на {server_id}: {message}")
    
    # Затем удаляем из БД
    logging.info(f"[delete_subscription] Starting to delete subscription {sub_id} from DB")
    
    # Используем функцию delete_subscription_from_db вместо прямого обращения к БД
    deleted = await delete_subscription_from_db(sub_id)
    
    if deleted:
        logging.info(f"[delete_subscription] Subscription {sub_id} successfully deleted")
        return {
            "status": "success", 
            "message": "Подписка успешно удалена",
            "delete_statuses": delete_statuses,
            "all_success": all_success
        }
    else:
        logging.error(f"[delete_subscription] Failed to delete subscription {sub_id} from DB")
        return {
            "status": "error", 
            "message": "Ошибка при удалении подписки из БД",
            "delete_statuses": delete_statuses
        }

# API endpoint для проверки админа (совместимость с фронтендом)
@app.get("/api/check-admin")
async def api_check_admin(tg_id: str):
    """Проверка админских прав для API."""
    try:
        return {"is_admin": is_admin(tg_id)}
    except Exception as e:
        logging.error(f"Ошибка при проверке админа: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

# Подключаем админские роутеры
app.include_router(admin_router)

# Проверяем статус "своего" пользователя
@app.get("/api/user/is-admin-user")
async def check_admin_user(tg_id: Optional[str] = None):
    """Проверка, является ли пользователь 'своим' и получение его подписки."""
    if not tg_id:
        raise HTTPException(status_code=400, detail="Отсутствует telegram_id")
    
    try:
        tg_id_int = int(tg_id)
        logging.info(f"Проверка, является ли пользователь {tg_id_int} 'своим'")
        
        # Проверяем, является ли пользователь "своим"
        is_admin = await is_admin_user(tg_id_int)
        
        if not is_admin:
            logging.info(f"Пользователь {tg_id_int} не является 'своим'")
            return {"success": True, "is_admin_user": False}
        
        # Получаем подписку "своего" пользователя
        admin_subscription = await get_admin_subscription_by_tg_id(tg_id_int)
        
        if not admin_subscription:
            logging.warning(f"Пользователь {tg_id_int} помечен как 'свой', но подписка не найдена")
            return {"success": True, "is_admin_user": True, "subscription": None}
        
        logging.info(f"Пользователь {tg_id_int} является 'своим', подписка найдена")
        return {
            "success": True, 
            "is_admin_user": True, 
            "subscription": admin_subscription
        }
    except Exception as e:
        logging.error(f"Ошибка при проверке статуса 'своего' пользователя {tg_id}: {e}")
        return {"success": False, "message": str(e)}

# Инициализация базы данных - добавляем создание таблицы admin_subscriptions
@app.on_event("startup")
async def startup_event():
    """
    Выполняется при запуске приложения для инициализации базы данных.
    """
    try:
        conn = await init_db()
        
        # Применяем скрипт для создания таблицы admin_subscriptions, если её еще нет
        with open("migrations/admin_subscriptions.sql", "r") as f:
            migration_sql = f.read()
            await conn.execute(migration_sql)
        
        # Применяем скрипт для добавления столбца updated_at в таблицу users
        try:
            with open("migrations/add_updated_at_to_users.sql", "r") as f:
                migration_sql = f.read()
                await conn.execute(migration_sql)
                logging.info("Миграция add_updated_at_to_users.sql успешно применена")
        except Exception as migration_error:
            logging.error(f"Ошибка при применении миграции add_updated_at_to_users.sql: {migration_error}")
            
        await conn.close()
        logging.info("База данных успешно инициализирована")
    except Exception as e:
        logging.error(f"Ошибка при инициализации базы данных: {e}")

# Добавим функцию для проверки активности подписки
def check_is_active(end_date_str):
    """Проверяет, активна ли подписка по дате окончания."""
    try:
        # Если передано как строка, преобразуем в дату
        if isinstance(end_date_str, str):
            end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
        else:
            end_date = end_date_str
            
        # Проверяем, не истекла ли подписка
        return datetime.now() < end_date
    except Exception as e:
        logging.error(f"Ошибка при проверке активности подписки: {e}")
        return False

@app.get("/api/user/subscription")
async def get_user_subscription(tg_id: Optional[str] = None):
    """Получение данных о подписке пользователя."""
    if not tg_id:
        raise HTTPException(status_code=400, detail="Отсутствует telegram_id")
    
    try:
        # Конвертируем tg_id в число
        tg_id_int = int(tg_id)
        logging.info(f"Получение данных о подписке для пользователя с TG ID: {tg_id_int}")
        
        # Сначала проверяем, является ли пользователь "своим" администратором
        admin_subscription = await get_admin_subscription_by_tg_id(tg_id_int)
        
        if admin_subscription:
            logging.info(f"Найдена админ-подписка для пользователя {tg_id_int}: {admin_subscription['sub_id']}")
            
            # Это "свой" пользователь
            is_active = True  # "Свои" пользователи всегда активны
            subscription = {
                "id": admin_subscription["sub_id"],
                "user_id": admin_subscription["user_id"],
                "start_date": admin_subscription["start_date"],
                "end_date": admin_subscription["end_date"],
                "duration": admin_subscription["duration"],
                "is_active": is_active,
                "servers_data": admin_subscription["servers_data"],
                "is_admin_user": True  # Флаг, указывающий что это "свой" пользователь
            }
            
            # Проверяем наличие mix_link, если отсутствует - создаем
            if "mix_link" not in admin_subscription["servers_data"]:
                logging.info(f"Создаем mix_link для админ-подписки {admin_subscription['sub_id']}")
                servers_data = admin_subscription["servers_data"]
                mix_link = f"mix_{admin_subscription['sub_id']}"
                servers_data["mix_link"] = mix_link
                await update_admin_subscription(admin_subscription["sub_id"], servers_data)
                subscription["servers_data"] = servers_data
            
            return {"success": True, "subscription": subscription}
        
        # Если не "свой", проверяем обычную подписку
        subscriptions = await get_subscriptions_from_db(tg_id_int)
        if not subscriptions or len(subscriptions) == 0:
            logging.info(f"Подписка не найдена для пользователя {tg_id_int}")
            return {"success": False, "message": "Подписка не найдена"}
        
        # Берем последнюю подписку (обычно самую новую)
        subscription = subscriptions[0]
        subscription["is_active"] = check_is_active(subscription["end_date"])
        subscription["is_admin_user"] = False  # Флаг, указывающий что это обычный пользователь
        
        logging.info(f"Найдена обычная подписка для пользователя {tg_id_int}: {subscription['sub_id']}")
        return {"success": True, "subscription": subscription}
    except Exception as e:
        logging.error(f"Ошибка при получении данных о подписке для пользователя {tg_id}: {e}")
        return {"success": False, "message": str(e)}