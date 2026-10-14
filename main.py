import json
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

class ZapiraykaGame:
    def __init__(self):
        # Начальная расстановка: Белые (W) на 1-й строке, Чёрные (B) на 8-й
        # Координаты храним как [строка, столбец] от 0 до 7 и от 0 до 2
        # Столбцы: 0='a', 1='b', 2='c'. Строки: 0=1, 7=8
        self.board = {
            "white": [[0, 0], [0, 1], [0, 2]], # a1, b2(сместили на b1), c3(сместили на c1) для выравнивания по правилу "только вперед по прямой"
            "black": [[7, 0], [7, 1], [7, 2]]  # a8, b7(на b8), c6(на c8) для игры строго в вертикальных коридорах
        }
        self.turn = "white" # Первыми ходят белые
        self.winner = None
        self.chat_history = []
        self.active_connections = []

    def get_state(self):
        return {
            "board": self.board,
            "turn": self.turn,
            "winner": self.winner,
            "chat": self.chat_history
        }

    def check_game_over(self):
        # Проверяем, есть ли хоть один доступный ход для игрока, чей сейчас ход
        current_color = self.turn
        opponent_color = "black" if current_color == "white" else "white"
        
        has_any_move = False
        for i in range(3):
            curr_row, curr_col = self.board[current_color][i]
            opp_row, opp_col = self.board[opponent_color][i]
            
            if current_color == "white":
                # Белые ходят только ВНИЗ (увеличение индекса строки). Проверяем клетку прямо под ней.
                if curr_row + 1 < 8 and curr_row + 1 < opp_row:
                    has_any_move = True
                    break
            else:
                # Чёрные ходят только ВВЕРХ (уменьшение индекса строки). Проверяем клетку прямо над ней.
                if curr_row - 1 >= 0 and curr_row - 1 > opp_row:
                    has_any_move = True
                    break
                    
        if not has_any_move:
            # Если ходить некуда, побеждает тот, кто ходил ПРЕДЫДУЩИМ (оппонент)
            self.winner = opponent_color

    def make_move(self, color, fig_index, to_row, to_col):
        if self.winner or self.turn != color:
            return False, "Не ваш ход"

        from_row, from_col = self.board[color][fig_index]
        opp_row, opp_col = self.board["black" if color == "white" else "white"][fig_index]

        # Правило 1: Движение только в своём вертикальном столбце
        if from_col != to_col:
            return False, "Движение возможно только по вертикали вперёд"

        # Правило 2: Направление движения
        if color == "white":
            if to_row <= from_row:
                return False, "Белые могут ходить только вперёд (вниз)"
            if to_row >= opp_row:
                return False, "Нельзя перепрыгивать или вставать на фигуру соперника"
        else:
            if to_row >= from_row:
                return False, "Чёрные могут ходить только вперёд (вверх)"
            if to_row <= opp_row:
                return False, "Нельзя перепрыгивать или вставать на фигуру соперника"

        # Если проверки пройдены — делаем ход
        self.board[color][fig_index] = [to_row, to_col]
        
        # Меняем очередь хода и проверяем на финал игры
        self.turn = "black" if color == "white" else "white"
        self.check_game_over()
        return True, "Успешно"

    def reset(self):
        self.__init__()

game = ZapiraykaGame()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    game.active_connections.append(websocket)
    
    # Сразу отправляем текущее состояние игры новому клиенту
    await websocket.send_text(json.dumps({"type": "state", "data": game.get_state()}))
    
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("type") == "move":
                color = msg.get("color")
                fig_idx = int(msg.get("fig_index"))
                to_row = int(msg.get("to_row"))
                to_col = int(msg.get("to_col"))
                
                success, reason = game.make_move(color, fig_idx, to_row, to_col)
                if success:
                    # Оповещаем всех об обновлении поля
                    for conn in game.active_connections:
                        await conn.send_text(json.dumps({"type": "state", "data": game.get_state()}))
                        
            elif msg.get("type") == "message":
                chat_msg = {"sender": msg.get("sender"), "text": msg.get("text")}
                game.chat_history.append(chat_msg)
                for conn in game.active_connections:
                    await conn.send_text(json.dumps({"type": "chat", "data": chat_msg}))
                    
            elif msg.get("type") == "reset":
                game.reset()
                for conn in game.active_connections:
                    await conn.send_text(json.dumps({"type": "state", "data": game.get_state()}))

    except WebSocketDisconnect:
        game.active_connections.remove(websocket)

# Универсальный эндпоинт для отдачи одной страницы
def get_html_response(role):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    # Встраиваем роль прямо в JS код страницы перед отдачей
    html = html.replace("let userRole = 'spectator';", f"let userRole = '{role}';")
    return HTMLResponse(content=html)

@app.get("/")
async def get_spectator():
    return get_html_response("spectator")

@app.get("/player1")
async def get_player1():
    return get_html_response("white")

@app.get("/player2")
async def get_player2():
    return get_html_response("black")
