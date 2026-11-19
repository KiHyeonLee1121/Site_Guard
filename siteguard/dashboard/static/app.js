"use strict";

const $ = id => document.getElementById(id);
const canvas = $("overlay"), ctx = canvas.getContext("2d"), image = $("frame");
const colors = {1: "#7ce0af", 2: "#f5c26d", 3: "#fb8784"};
let status = {}, roi = {revision: 0, zones: []}, draft = null, selected = null, dragging = -1;
let lastImage = 0, imageUrl = null, imageSeq = null;

async function get(path, options) {
  const response = await fetch(path, {cache: "no-store", ...options});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}
function text(id, value) { $(id).textContent = value; }
function rows(id, labels) {
  const target = $(id);
  target.replaceChildren(...labels.map(([label, value]) => {
    const div = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = label; dd.textContent = value;
    div.append(dt, dd);
    return div;
  }));
}
function table(id, records, blank, cols) {
  const tableRows = records.length ? records : [[blank]];
  $(id).replaceChildren(...tableRows.map(record => {
    const row = document.createElement("tr");
    record.forEach(value => {
      const cell = document.createElement("td");
      if (!records.length) cell.colSpan = cols;
      if (value instanceof HTMLElement) cell.append(value);
      else cell.textContent = value;
      row.append(cell);
    });
    return row;
  }));
}
function draw() {
  const {width: w, height: h} = canvas;
  ctx.clearRect(0, 0, w, h);
  const weight = Math.max(2, w / 280);
  for (const zone of (draft || roi.zones)) {
    if (!zone.points.length) continue;
    ctx.beginPath();
    zone.points.forEach(([x, y], i) => i ? ctx.lineTo(x * w, y * h) : ctx.moveTo(x * w, y * h));
    if (zone.points.length > 2) ctx.closePath();
    ctx.strokeStyle = colors[zone.level];
    ctx.fillStyle = colors[zone.level] + "24";
    ctx.lineWidth = weight;
    ctx.fill();
    ctx.stroke();
    if (draft && selected === zone) {
      zone.points.forEach(([x, y], i) => {
        ctx.beginPath();
        ctx.arc(x * w, y * h, weight * 3.5, 0, 2 * Math.PI);
        ctx.fillStyle = colors[zone.level];
        ctx.fill();
        ctx.fillStyle = "#0a121b";
        ctx.font = `bold ${Math.max(9, w / 85)}px system-ui`;
        ctx.fillText(i + 1, x * w - weight * 1.4, y * h + weight * 1.6);
      });
    }
  }
  if (draft) return;
  for (const item of status.objects || []) {
    if (!item.visible) continue;
    const [x1, y1, x2, y2] = item.bbox;
    ctx.strokeStyle = colors[item.roi] || "#e1edf8";
    ctx.fillStyle = ctx.strokeStyle;
    ctx.lineWidth = weight;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    ctx.font = `600 ${Math.max(13, w / 50)}px system-ui`;
    ctx.fillText(`#${item.id} ${item.class_name}`, x1, Math.max(16, y1 - 4));
    ctx.beginPath();
    ctx.arc((x1 + x2) / 2, y2, weight * 2, 0, 2 * Math.PI);
    ctx.fill();
  }
}
function desaturateState(s) {
  const source = {mock: "MOCK · 가상 데이터", video: "VIDEO TEST · 저장 영상", camera: "CAMERA · 실시간"};
  text("mode", source[s.source] || "연결 중");
  text("health", s.running ? (s.input_status || "실행 중") : "처리 종료");
  if (s.width && s.height && (canvas.width !== s.width || canvas.height !== s.height)) {
    canvas.width = s.width;
    canvas.height = s.height;
    $("viewport").style.aspectRatio = `${s.width} / ${s.height}`;
  }
  text("resolution", s.width ? `${s.width} × ${s.height} · ${s.backend}` : "");
  $("empty-frame").hidden = Boolean(s.has_image);
  text("empty-frame", s.source === "mock" ? "가상 프레임에 검출 정보를 표시합니다" : "영상 입력 대기");
  const hardware = s.hardware || {};
  rows("devices", [["Arduino", hardware.connection || "대기"], ["경고", ["감시", "주의", "핵심"][s.output?.level] || "감시"],
    ["LED", hardware.brightness == null ? "확인 대기" : `${hardware.brightness}%`],
    ["스피커 명령", hardware.sound || "확인 대기"], ["PIR", hardware.pir == null ? "미연결" : hardware.pir ? "감지" : "대기"],
    ["클라우드", s.cloud || "대기"], ["미전송 이벤트", s.queued ?? 0], ["이벤트 저장 오류", s.storage_errors ?? 0]]);
  table("tracks", (s.objects || []).map(o => [
    o.id, o.class_name, o.visible ? `${(o.confidence * 100).toFixed(0)}%` : "누락 중",
    o.roi || "외부", `${o.dwell.toFixed(1)}s`, o.state
  ]), "감지된 객체 없음", 6);
}
async function updateImage() {
  if (status.has_image && imageSeq !== status.image_sequence && Date.now() - lastImage > 170) {
    lastImage = Date.now();
    const response = await fetch("/api/frame.jpg", {cache: "no-store"});
    if (response.ok) {
      const next = URL.createObjectURL(await response.blob());
      image.src = next;
      image.hidden = false;
      imageSeq = status.image_sequence;
      if (imageUrl) URL.revokeObjectURL(imageUrl);
      imageUrl = next;
    }
  } else if (!status.has_image) {
    image.hidden = true;
  }
}
function refreshROIInfo() {
  text("roi-info", roi.zones.map(z => `ROI ${z.level} ${z.name}`).join(" · ") || "저장된 구역 없음");
}
async function loadROI() {
  roi = await get("/api/roi");
  refreshROIInfo();
}
function pick() {
  const level = Number($("zone-level").value);
  selected = draft.find(z => z.level === level);
  if (!selected) {
    selected = {level, name: `ROI ${level}`, points: []};
    draft.push(selected);
  }
  $("zone-name").value = selected.name;
  draw();
}
function startEditor() {
  draft = JSON.parse(JSON.stringify(roi.zones));
  $("editor").hidden = false;
  $("viewport").classList.add("editing");
  text("edit", "닫기");
  pick();
}
function closeEditor() {
  draft = selected = null;
  $("editor").hidden = true;
  $("viewport").classList.remove("editing");
  text("edit", "편집");
  draw();
}
function point(event) {
  const box = canvas.getBoundingClientRect();
  return [Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)),
          Math.min(1, Math.max(0, (event.clientY - box.top) / box.height))];
}
$("edit").onclick = () => draft ? closeEditor() : startEditor();
$("zone-level").onchange = pick;
$("zone-name").oninput = () => { selected.name = $("zone-name").value; };
$("undo").onclick = () => { selected.points.pop(); draw(); };
$("delete").onclick = () => { selected.points = []; text("roi-message", "저장하면 선택한 구역이 삭제됩니다."); draw(); };
$("reload").onclick = async () => {
  try { await loadROI(); startEditor(); text("roi-message", "저장된 구역을 불러왔습니다."); }
  catch (error) { text("roi-message", error.message); }
};
$("save").onclick = async () => {
  try {
    const zones = draft.filter(z => z.points.length);
    // Use the revision captured at the start of editing.
    await get("/api/roi", {method: "PUT", headers: {"Content-Type": "application/json", "X-SiteGuard-ROI": "1"},
      body: JSON.stringify({zones, revision: roi.revision})});
    await loadROI();
    closeEditor();
    text("roi-message", "ROI를 저장했습니다.");
  } catch (error) { text("roi-message", error.message); }
};
canvas.onpointerdown = event => {
  if (!selected || event.button !== 0) return;
  const [x, y] = point(event), box = canvas.getBoundingClientRect();
  dragging = selected.points.findIndex(([px, py]) => Math.hypot((px - x) * box.width, (py - y) * box.height) < 12);
  if (dragging < 0 && selected.points.length < 64) {
    selected.points.push([x, y]);
    dragging = selected.points.length - 1;
  }
  if (dragging >= 0) canvas.setPointerCapture(event.pointerId);
  draw();
};
canvas.onpointermove = event => {
  if (!selected || dragging < 0) return;
  selected.points[dragging] = point(event);
  draw();
};
canvas.onpointerup = canvas.onpointercancel = () => { dragging = -1; };

async function monitor() {
  try {
    status = await get("/api/status");
    desaturateState(status);
    if (!draft && status.roi_revision != null && status.roi_revision !== roi.revision) await loadROI();
    draw();
    await updateImage();
  } catch (error) { text("health", error.message); }
  window.setTimeout(monitor, 250);
}
const eventNames = {warning: "1차 경고", critical: "높은 단계 경고", cleared: "경고 해제",
  lost: "객체 추적 종료", reannouncement: "재안내", review_required: "관리자 확인",
  pir_motion: "PIR 감지", pir_clear: "PIR 해제", output: "장치 명령"};
async function eventList() {
  try {
    const result = await get("/api/events");
    table("events", result.events.map(event => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "event-link";
      button.textContent = eventNames[event.kind] || event.kind;
      button.onclick = async () => {
        const pane = $("event-detail");
        try { pane.textContent = JSON.stringify(await get(`/api/events/${event.id}`), null, 2); }
        catch (error) { pane.textContent = error.message; }
        pane.hidden = false;
      };
      return [event.utc.replace("T", " ").slice(0, 19), button,
        event.track ? `#${event.track.track_id} ${event.track.class_name}` : "—",
        event.arduino_response ? event.arduino_response.ok ? "ACK" : "오류" : "—", event.cloud_status];
    }), "기록된 이벤트 없음", 5);
  } catch (error) { table("events", [], error.message, 5); }
  window.setTimeout(eventList, 1500);
}
Promise.all([loadROI(), get("/api/policy").then(p => rows("policy", [
  ["사람 체류", `${p.dwell.person}초`], ["개 체류", `${p.dwell.dog}초`], ["핵심 구역 확인", `${p.critical_frames}프레임`],
  ["해제 확인", `${p.clear_sec}초`], ["재안내 간격", `${p.repeat_sec}초`],
  ["최대 재안내", `${p.max_repeats}회`], ["동일 단계 우선", p.person_first ? "사람" : "개"]
]))]).catch(error => text("roi-message", error.message)).finally(() => { monitor(); eventList(); });
