import { invoke } from "@tauri-apps/api/core";
import "./styles.css";

type Game = "hsr" | "zzz";
type BoxState = { version: number; updatedAt: string; owned: string[]; buildSlug: string; builds: Record<string, unknown> };

const app = document.querySelector<HTMLDivElement>("#app")!;
let game: Game = "zzz";
let state: BoxState = { version: 2, updatedAt: "", owned: [], buildSlug: "", builds: {} };

function render(message = "") {
  app.innerHTML = `<header><div><p class="eyebrow">MIHO ENDGAME</p><h1>终局数据中心</h1></div><nav><button data-game="hsr" class="${game === "hsr" ? "active" : ""}">崩坏：星穹铁道</button><button data-game="zzz" class="${game === "zzz" ? "active" : ""}">绝区零</button></nav></header>
  <main><section class="hero"><div><p>本地账户数据</p><h2>${game === "zzz" ? "绝区零" : "崩坏：星穹铁道"} Box</h2><span>${state.owned.length} 名已拥有角色</span></div><button id="refresh">刷新数据</button></section>
  <section class="panel"><div class="panel-title"><h3>已拥有角色</h3><span>${message}</span></div><textarea id="owned" placeholder="每行一个角色 slug">${state.owned.join("\n")}</textarea><button id="save">保存到本机</button></section></main>`;
  document.querySelectorAll<HTMLButtonElement>("[data-game]").forEach(button => button.onclick = async () => { game = button.dataset.game as Game; await load(); });
  document.querySelector<HTMLButtonElement>("#save")!.onclick = save;
  document.querySelector<HTMLButtonElement>("#refresh")!.onclick = () => load();
}

async function load() {
  render("读取中…");
  try { state = await invoke<BoxState>("load_box_state", { game }); render("已从 .miho 读取"); }
  catch (error) { render(`读取失败：${String(error)}`); }
}

async function save() {
  state.owned = document.querySelector<HTMLTextAreaElement>("#owned")!.value.split(/\r?\n/).map(v => v.trim()).filter(Boolean);
  state.updatedAt = new Date().toISOString();
  try { state = await invoke<BoxState>("save_box_state", { game, state }); render("已自动保存"); }
  catch (error) { render(`保存失败：${String(error)}`); }
}

void load();

