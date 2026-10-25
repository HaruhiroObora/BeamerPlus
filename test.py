import sys
import json
import asyncio
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtCore import Qt, QPointF, Signal, QObject
import websockets

# --- iPad向けに配信するHTML/JS ---
HTML_CONTENT = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Apple Pencil Canvas</title>
  <style>
    * {
      margin: 0;
      padding: 0;
      -webkit-touch-callout: none !important;
      -webkit-user-select: none !important;
      user-select: none !important;
    }
    body, html {
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #f0f0f0;
      position: fixed;
    }
    canvas {
      display: block;
      background: #ffffff;
      /* スクリブルの対象外であることを徹底 */
      cursor: crosshair;
    }
    #ui-bar {
      position: fixed;
      top: 12px;
      left: 12px;
      display: flex;
      align-items: center;
      gap: 12px;
      background: rgba(255, 255, 255, 0.9);
      backdrop-filter: blur(8px);
      padding: 8px 14px;
      border-radius: 20px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      font-family: -apple-system, sans-serif;
      font-size: 13px;
      z-index: 10;
    }
    #status { color: #666; }
    .switch-label {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
      font-weight: 500;
    }
  </style>
</head>
<body>
  <div id="ui-bar">
    <span id="status">Connecting...</span>
    <label class="switch-label">
      <input type="checkbox" id="penOnlyToggle" checked>
      <span>Pencilのみ描画</span>
    </label>
  </div>

  <!-- inputmode="none" でOSの入力システムを完全シャットアウト -->
  <canvas id="paintCanvas" inputmode="none"></canvas>

  <script>
    const canvas = document.getElementById('paintCanvas');
    const ctx = canvas.getContext('2d');
    const statusDiv = document.getElementById('status');
    const penOnlyToggle = document.getElementById('penOnlyToggle');

    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const ws = new WebSocket(`ws://${location.hostname}:8765`);
    ws.onopen = () => { statusDiv.innerText = "Connected"; };
    ws.onclose = () => { statusDiv.innerText = "Disconnected"; };

    let isDrawing = false;
    let lastX = 0, lastY = 0;

    // スクリブルをバイパスするため Touch Events を直接処理
    function getTouchInfo(e) {
      const touch = e.touches[0] || e.changedTouches[0];
      const isStylus = touch.touchType === 'stylus';
      
      let lineWidth = 3; // 指や通常タッチ時の固定幅 (px)

      if (isStylus) {
        // Apple Pencil の場合のみ筆圧 (force) を適用
        // force が取得できない場合はデフォルト 0.5
        const force = (typeof touch.force === 'number' && touch.force > 0) ? touch.force : 0.5;
        // 筆圧に応じて 1.5px 〜 12px の範囲に収める (Math.min で安全マージン)
        lineWidth = Math.min(15, Math.max(1.5, force * 10));
      } else {
        // 指の場合は太さを 3px〜4px 程度で固定
        lineWidth = 3.5;
      }
      
      return {
        x: touch.clientX,
        y: touch.clientY,
        isStylus: isStylus,
        lineWidth: lineWidth
      };
    }

    function isValid(info) {
      if (penOnlyToggle.checked) {
        return info.isStylus;
      }
      return true;
    }

    // touchstart の先頭で preventDefault() するとスクリブル判定が即死します
    canvas.addEventListener('touchstart', (e) => {
      const info = getTouchInfo(e);
      if (!isValid(info)) return;

      e.preventDefault();

      isDrawing = true;
      lastX = info.x;
      lastY = info.y;

      // info.lineWidth を使用
      drawDot(lastX, lastY, info.lineWidth);
      sendStroke('start', lastX, lastY, info.lineWidth);
    }, { passive: false });

    canvas.addEventListener('touchmove', (e) => {
      if (!isDrawing) return;
      const info = getTouchInfo(e);
      if (!isValid(info)) return;

      e.preventDefault();

      // info.lineWidth を使用
      ctx.beginPath();
      ctx.moveTo(lastX, lastY);
      ctx.lineTo(info.x, info.y);
      ctx.strokeStyle = '#0055ff';
      ctx.lineWidth = info.lineWidth;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.stroke();

      lastX = info.x;
      lastY = info.y;

      sendStroke('move', lastX, lastY, info.lineWidth);
    }, { passive: false });

    const endTouch = (e) => {
      if (!isDrawing) return;
      isDrawing = false;
      const touch = e.changedTouches[0];
      sendStroke('end', touch ? touch.clientX : lastX, touch ? touch.clientY : lastY, 2);
    };

    canvas.addEventListener('touchend', endTouch, { passive: false });
    canvas.addEventListener('touchcancel', endTouch, { passive: false });

    function drawDot(x, y, width) {
      ctx.beginPath();
      ctx.arc(x, y, width / 2, 0, Math.PI * 2);
      ctx.fillStyle = '#0055ff';
      ctx.fill();
    }

    function sendStroke(type, x, y, width) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: type,
          normX: x / canvas.width,
          normY: y / canvas.height,
          width: width
        }));
      }
    }
  </script>
</body>
</html>
"""

# --- シグナル中継ブリッジ ---
class Bridge(QObject):
    stroke_received = Signal(dict)
    clear_received = Signal()

bridge = Bridge()

# --- HTTP サーバー（iPadへHTMLを配信） ---
class WebRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML_CONTENT.encode('utf-8'))
    def log_message(self, format, *args):
        pass  # ログ非表示

def start_http_server():
    server = HTTPServer(('0.0.0.0', 8080), WebRequestHandler)
    server.serve_forever()

# --- WebSocket サーバー（iPadからの描画データ受信） ---
async def ws_handler(websocket):
    async for message in websocket:
        try:
            data = json.loads(message)
            bridge.stroke_received.emit(data)
        except Exception:
            pass

async def ws_main():
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        await asyncio.Future()

def start_ws_server():
    asyncio.run(ws_main())

# --- PySide6 描画ウィジェット ---
class CanvasWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.strokes = []  # [[(QPointF, width), ...], ...]
        self.current_stroke = []

    def add_point(self, data):
        w = self.width()
        h = self.height()
        pt = QPointF(data['normX'] * w, data['normY'] * h)
        width = data.get('width', 2.0)

        if data['type'] == 'start':
            self.current_stroke = [(pt, width)]
            self.strokes.append(self.current_stroke)
        elif data['type'] == 'move':
            if not self.current_stroke:
                self.current_stroke = [(pt, width)]
                self.strokes.append(self.current_stroke)
            else:
                self.current_stroke.append((pt, width))
        elif data['type'] == 'end':
            self.current_stroke = []

        self.update()

    def clear_canvas(self):
        self.strokes.clear()
        self.current_stroke.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        for stroke in self.strokes:
            for i in range(len(stroke) - 1):
                p1, w1 = stroke[i]
                p2, _ = stroke[i+1]
                pen = QPen(QColor("#0055ff"), w1, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                painter.drawLine(p1, p2)

# --- メインウィンドウ ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 - Realtime iPad Pencil Receiver")
        self.resize(1000, 700)

        self.canvas = CanvasWidget()
        clear_btn = QPushButton("Clear Canvas")
        clear_btn.clicked.connect(self.canvas.clear_canvas)

        layout = QVBoxLayout()
        layout.addWidget(clear_btn)
        layout.addWidget(self.canvas)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # WebSocket受信シグナルをキャンバスへバインド
        bridge.stroke_received.connect(self.canvas.add_point)

if __name__ == "__main__":
    # バックグラウンドで HTTP(8080) & WebSocket(8765) を常駐
    threading.Thread(target=start_http_server, daemon=True).start()
    threading.Thread(target=start_ws_server, daemon=True).start()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())