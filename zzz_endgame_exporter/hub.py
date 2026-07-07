from __future__ import annotations

from pathlib import Path


def write_visualizer_hub(workspace_dir: Path, *, hsr_dir: str = "out", zzz_dir: str = "out_zzz") -> None:
    hub_dir = workspace_dir / "visualizer"
    hub_dir.mkdir(parents=True, exist_ok=True)
    (hub_dir / "index.html").write_text(_html(hsr_dir, zzz_dir), encoding="utf-8")
    (hub_dir / "styles.css").write_text(STYLES, encoding="utf-8")
    (hub_dir / "app.js").write_text(SCRIPT, encoding="utf-8")


def _html(hsr_dir: str, zzz_dir: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>米哈游终局可视化</title>
  <link rel="stylesheet" href="./styles.css" />
</head>
<body>
  <main class="hub">
    <header class="topbar">
      <div>
        <h1>米哈游终局可视化</h1>
        <p id="statusLine">同一个入口切换游戏；Box 数据按游戏分别本地保存。</p>
      </div>
      <nav class="tabs">
        <button data-game="hsr" data-src="../{hsr_dir}/visualizer/index.html">崩坏：星穹铁道</button>
        <button data-game="zzz" data-src="../{zzz_dir}/visualizer/index.html">绝区零</button>
      </nav>
    </header>
    <iframe id="gameFrame" title="终局可视化"></iframe>
  </main>
  <script src="./app.js"></script>
</body>
</html>
"""


STYLES = """*{box-sizing:border-box}body{margin:0;background:#eef3f5;color:#172126;font-family:Inter,Segoe UI,Arial,'Microsoft YaHei',sans-serif}.hub{height:100vh;display:grid;grid-template-rows:auto minmax(0,1fr)}.topbar{display:flex;justify-content:space-between;gap:16px;align-items:flex-start;padding:14px 18px;background:white;border-bottom:1px solid #d8e1e5}.topbar h1{margin:0 0 4px;font-size:21px}.topbar p{margin:0;color:#64757d;font-size:12px}.tabs{display:flex;gap:8px;flex-wrap:wrap}.tabs button{border:1px solid #c6d2d7;background:#f9fbfb;color:#1d3942;border-radius:6px;padding:8px 12px;cursor:pointer}.tabs button.active{background:#174c5a;color:white;border-color:#174c5a}iframe{width:100%;height:100%;border:0;background:white}@media(max-width:720px){.topbar{flex-direction:column;padding:12px}.tabs{width:100%}.tabs button{flex:1}}"""


SCRIPT = """const frame=document.getElementById('gameFrame');const statusLine=document.getElementById('statusLine');const buttons=[...document.querySelectorAll('.tabs button')];const params=new URLSearchParams(location.search);function setGame(game){const btn=buttons.find(b=>b.dataset.game===game)||buttons[0];buttons.forEach(b=>b.classList.toggle('active',b===btn));frame.src=btn.dataset.src;localStorage.setItem('mhy_endgame_visualizer_game',btn.dataset.game);statusLine.textContent=`当前：${btn.textContent} · 同一个入口切换游戏，Box 数据按游戏分别本地保存。`;}buttons.forEach(b=>b.onclick=()=>setGame(b.dataset.game));setGame(params.get('game')||localStorage.getItem('mhy_endgame_visualizer_game')||'hsr');"""
