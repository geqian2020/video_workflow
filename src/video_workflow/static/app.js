"use strict";
const $ = id => document.getElementById(id);
const busyStates = new Set(["importing", "generating", "rendering", "previewing"]);
let project = null, selectedId = null, settings = {}, timer = null, dirty = false;

function message(text = "") { $("message").textContent = text; $("message").hidden = !text; }
async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = Array.isArray(data.detail) ? data.detail.map(x => x.msg).join("；") : data.detail;
    throw new Error(detail || "操作未完成，请重试");
  }
  return response.json();
}
function json(method, body) { return {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)}; }
function media(relative) { return `/api/projects/${project.id}/files/${relative}`; }
function selected() { return project?.slides.find(s => s.id === selectedId); }
function guarded(action) { return async event => { event?.preventDefault(); message(); try { await action(event); } catch (error) { message(error.message); } }; }

async function refreshList() {
  const projects = await request("/api/projects");
  $("projects").replaceChildren();
  for (const item of projects) {
    const button = document.createElement("button");
    button.textContent = item.title; button.className = item.id === project?.id ? "active" : "";
    button.onclick = guarded(async () => { await saveScript(); selectedId = null; show(await request(`/api/projects/${item.id}`)); });
    $("projects").append(button);
  }
}
function show(value) {
  if (project?.id !== value.id) { $("audio-player").pause(); $("video-player").pause(); dirty = false; }
  project = value;
  const busy = busyStates.has(project.status);
  $("start").hidden = true; $("workspace").hidden = false;
  $("heading").textContent = project.title; $("status").textContent = project.progress;
  $("warnings").textContent = project.warnings.join("\n");
  message(project.error || "");
  if (!project.slides.some(s => s.id === selectedId)) selectedId = project.slides[0]?.id || null;
  $("slide-nav").replaceChildren();
  for (const [index, slide] of project.slides.entries()) {
    const button = document.createElement("button"); button.textContent = `${index + 1}`;
    button.className = slide.id === selectedId ? "active" : "";
    button.onclick = guarded(async () => { await saveScript(); selectedId = slide.id; show(project); });
    $("slide-nav").append(button);
  }
  const slide = selected();
  $("slide-image").hidden = !slide;
  if (slide) {
    $("slide-image").src = media(slide.image);
    $("slide-number").textContent = `第 ${slide.source_page} 页，共 ${project.slides.length} 页`;
    if (!dirty) { $("slide-title").value = slide.title; $("narration").value = slide.narration; }
  } else { $("slide-title").value = ""; $("narration").value = ""; $("slide-number").textContent = "等待页面导入"; }
  for (const id of ["slide-title", "narration", "save-script", "preview-audio", "render-page"]) $(id).disabled = busy || !slide;
  $("draft-script").disabled = busy || !slide || !settings.narration_model;
  $("draft-script").title = settings.narration_model ? "" : "尚未配置讲稿模型，可以直接编辑讲稿";
  for (const id of ["avatar-file", "save-avatar", "mouth-x", "mouth-y", "mouth-w", "mouth-h", "render-all"]) $(id).disabled = busy;
  $("render-all").disabled = busy || !project.slides.length || !project.avatar;
  $("render-page").disabled = busy || !slide || !project.avatar;
  $("retry-import").hidden = project.status !== "failed" || !!project.slides.length || project.source_kind === "generated";
  $("avatar-stage").hidden = !project.avatar;
  if (project.avatar) {
    $("avatar-image").src = media(project.avatar.image);
    ["mouth-x", "mouth-y", "mouth-w", "mouth-h"].forEach((id, i) => { $(id).value = project.avatar.mouth[i]; });
    marker();
  }
  const audio = project.outputs.preview_audio && project.preview_audio_slide === selectedId ? media(project.outputs.preview_audio) : null;
  $("audio-player").hidden = !audio;
  if (audio) { if ($("audio-player").getAttribute("src") !== audio) $("audio-player").src = audio; }
  else { $("audio-player").pause(); $("audio-player").removeAttribute("src"); }
  $("downloads").replaceChildren();
  const labels = {deck: "下载可编辑 PPTX", pdf: "下载 PDF", video: "下载完整视频", subtitles: "下载完整字幕", timeline: "下载时间线", preview_video: "下载页面预览", preview_subtitles: "下载预览字幕"};
  for (const [key, label] of Object.entries(labels)) if (project.outputs[key]) {
    const link = document.createElement("a"); link.textContent = label; link.href = media(project.outputs[key]); link.download = ""; $("downloads").append(link);
  }
  const output = project.outputs.preview_video || project.outputs.video;
  $("result").hidden = !output;
  if (output) {
    const url = media(output); if ($("video-player").getAttribute("src") !== url) $("video-player").src = url;
    $("result-label").textContent = project.outputs.preview_video ? `页面预览${project.preview_stale ? "：讲稿或角色已修改，请重新生成" : ""}` : `完整视频${project.output_stale ? "：讲稿或角色已修改，请重新生成" : ""}`;
  }
  clearTimeout(timer);
  if (busy) timer = setTimeout(guarded(async () => { show(await request(`/api/projects/${project.id}`)); await refreshList(); }), 1800);
}
async function saveScript() {
  const slide = selected(); if (!slide || !dirty) return;
  project = await request(`/api/projects/${project.id}/slides/${slide.id}`, json("PATCH", {title: $("slide-title").value, narration: $("narration").value}));
  dirty = false;
}
function renderOptions(slideIds = null) { return {width: 1280, height: 720, fps: 24, engine: $("voice-engine").value, slide_ids: slideIds}; }
function marker() {
  const [x,y,w,h] = ["mouth-x", "mouth-y", "mouth-w", "mouth-h"].map(id => Number($(id).value));
  Object.assign($("mouth-marker").style, {left: `${x*100}%`, top: `${y*100}%`, width: `${w*100}%`, height: `${h*100}%`});
}
async function saveAvatar() {
  if (!project.avatar) throw new Error("请先上传角色");
  const mouth = ["mouth-x", "mouth-y", "mouth-w", "mouth-h"].map(id => Number($(id).value));
  project = await request(`/api/projects/${project.id}/avatar`, json("PATCH", {...project.avatar, mouth}));
}

$("upload-form").onsubmit = guarded(async () => { const data = new FormData(); data.append("file", $("deck-file").files[0]); show(await request("/api/projects", {method:"POST",body:data})); await refreshList(); });
$("generate-form").onsubmit = guarded(async () => { show(await request("/api/generate", json("POST", {content:$("topic").value, slides:Number($("page-count").value), title:$("topic-title").value}))); await refreshList(); });
$("upload-tab").onclick = () => { $("upload-form").hidden=false; $("generate-form").hidden=true; $("upload-tab").setAttribute("aria-selected","true"); $("generate-tab").setAttribute("aria-selected","false"); };
$("generate-tab").onclick = () => { $("upload-form").hidden=true; $("generate-form").hidden=false; $("upload-tab").setAttribute("aria-selected","false"); $("generate-tab").setAttribute("aria-selected","true"); };
$("new-project").onclick = guarded(async () => { await saveScript(); $("audio-player").pause(); $("video-player").pause(); clearTimeout(timer); project=null; selectedId=null; $("workspace").hidden=true; $("start").hidden=false; $("heading").textContent="让卡通讲师讲解你的课件"; $("status").textContent="准备开始"; await refreshList(); });
$("slide-title").oninput = $("narration").oninput = () => { dirty=true; };
$("save-script").onclick = guarded(async () => { await saveScript(); show(project); $("status").textContent="讲稿已保存"; });
$("preview-audio").onclick = guarded(async () => { await saveScript(); show(await request(`/api/projects/${project.id}/preview/${selectedId}`, json("POST", renderOptions()))); });
$("draft-script").onclick = guarded(async () => { await saveScript(); show(await request(`/api/projects/${project.id}/slides/${selectedId}/narration`, {method:"POST"})); });
$("avatar-file").onchange = guarded(async () => { const data=new FormData(); data.append("file",$("avatar-file").files[0]); show(await request(`/api/projects/${project.id}/avatar`,{method:"POST",body:data})); });
$("avatar-image").onclick = event => { const r=event.currentTarget.getBoundingClientRect(); $("mouth-x").value=((event.clientX-r.left)/r.width).toFixed(3); $("mouth-y").value=((event.clientY-r.top)/r.height).toFixed(3); marker(); };
for (const id of ["mouth-x","mouth-y","mouth-w","mouth-h"]) $(id).oninput=marker;
$("save-avatar").onclick = guarded(async () => { await saveScript(); await saveAvatar(); show(project); });
$("render-page").onclick = guarded(async () => { await saveScript(); await saveAvatar(); show(await request(`/api/projects/${project.id}/render`,json("POST",renderOptions([selectedId])))); });
$("render-all").onclick = guarded(async () => { await saveScript(); await saveAvatar(); show(await request(`/api/projects/${project.id}/render`,json("POST",renderOptions()))); });
$("retry-import").onclick = guarded(async () => { show(await request(`/api/projects/${project.id}/retry-import`,{method:"POST"})); });
window.addEventListener("beforeunload", event => { if(dirty){event.preventDefault();event.returnValue="";} });
(async () => { settings=await request("/api/config"); $("voice-engine").value=settings.default_engine; if(!settings.offline_voice) $("voice-engine").querySelector('[value="sapi"]').disabled=true; $("generate-button").disabled=!settings.presenton; $("generation-note").textContent=settings.presenton?"生成服务已连接。生成的 PPTX 与 PDF 会一并保留。":"自动生成入口已预留。需先在本机配置 Presenton 服务及模型，才能生成 PPT。"; await refreshList(); })().catch(error=>message(error.message));
