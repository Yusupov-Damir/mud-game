import os
import psycopg2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

# БЕЗОПАСНО: Код больше не хранит пароль. Он берет его из настроек хостинга!
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Критическая ошибка: Переменная окружения DATABASE_URL не задана!")

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            steps INTEGER DEFAULT 0
        );
    """)
    conn.commit()
    cursor.close()
    conn.close()

init_db()

active_players = []

async def send_to_all(message: str):
    for player in active_players:
        await player.send_text(message)

@app.get("/")
async def get():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_players.append(websocket)
    
    username = None
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        await websocket.send_text("Система: Привет! Введите ваше имя для входа в мир:")
        username = (await websocket.receive_text()).strip()
        
        cursor.execute("SELECT steps FROM users WHERE username = %s;", (username,))
        row = cursor.fetchone()
        
        if row:
            steps = row[0]
            await websocket.send_text(f"Система: С возвращением, {username}! База данных загрузила ваш прогресс. Вы уже сделали: {steps} шагов.")
        else:
            steps = 0
            cursor.execute("INSERT INTO users (username, steps) VALUES (%s, 0);", (username,))
            conn.commit()
            await websocket.send_text(f"Система: Создан новый персонаж {username}. Ваш баланс шагов обнулен.")
            
        await send_to_all(f"📢 Игрок [{username}] материализовался в комнате.")
        await websocket.send_text("Команды: 'шаг' — идти вперед, 'статус' — проверить счет. Любой другой текст — отправить в чат.")

        while True:
            data = await websocket.receive_text()
            cmd = data.strip().lower()
            
            if cmd == "шаг":
                steps += 1
                cursor.execute("UPDATE users SET steps = %s WHERE username = %s;", (steps, username))
                conn.commit()
                await websocket.send_text(f"🚶 Вы сделали шаг. Всего пройдено: {steps}. (Успешно сохранено в Supabase!)")
            elif cmd == "статус":
                await websocket.send_text(f"📊 Статистика {username}: совершено {steps} шагов.")
            else:
                await send_to_all(f"💬 [{username}]: {data}")
                
    except WebSocketDisconnect:
        active_players.remove(websocket)
        if username:
            await send_to_all(f"🏃 Игрок [{username}] растворился в воздухе.")
    finally:
        cursor.close()
        conn.close()
