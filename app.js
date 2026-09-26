let mediaRecorder = null;
let audioChunks = [];
let recordedBlob = null;
let deferredInstallPrompt = null;

const $ = id => document.getElementById(id);

window.addEventListener("beforeinstallprompt", e => {
  e.preventDefault();
  deferredInstallPrompt = e;
  $("installBtn").classList.remove("hidden");
});

$("installBtn").addEventListener("click", async () => {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  $("installBtn").classList.add("hidden");
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(console.error);
}

$("locationBtn").addEventListener("click", () => {
  if (!navigator.geolocation) {
    showError("Location is not supported by this browser.");
    return;
  }

  navigator.geolocation.getCurrentPosition(
    pos => {
      $("lat").value = pos.coords.latitude.toFixed(6);
      $("lon").value = pos.coords.longitude.toFixed(6);
      $("locationBtn").textContent = "✅ Location captured";
    },
    err => showError("Could not get location: " + err.message),
    {enableHighAccuracy:true, timeout:10000}
  );
});

$("recordBtn").addEventListener("click", async () => {
  if (mediaRecorder && mediaRecorder.state === "recording") {
    mediaRecorder.stop();
    $("recordBtn").textContent = "🎤 Start voice";
    $("recordStatus").textContent = "Voice recorded.";
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio:true});
    audioChunks = [];
    recordedBlob = null;

    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = e => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = () => {
      recordedBlob = new Blob(audioChunks, {type:"audio/webm"});
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start();
    $("recordBtn").textContent = "⏹ Stop recording";
    $("recordStatus").textContent = "Recording...";
  } catch (e) {
    showError("Microphone permission is required for voice input.");
  }
});

$("sendBtn").addEventListener("click", async () => {
  hideError();

  const message = $("message").value.trim();
  const lat = $("lat").value || "0";
  const lon = $("lon").value || "0";

  if (!message && !recordedBlob) {
    showError("Type an emergency message or record your voice.");
    return;
  }

  $("sendBtn").disabled = true;
  $("sendBtn").textContent = "Processing emergency...";

  const form = new FormData();
  form.append("message", message);
  form.append("latitude", lat);
  form.append("longitude", lon);

  if (recordedBlob) {
    form.append("audio", recordedBlob, "emergency.webm");
  }

  try {
    const res = await fetch("/api/emergency", {method:"POST", body:form});
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || "Emergency submission failed.");

    showResult(data);
    loadHistory();
    recordedBlob = null;
    $("message").value = "";
  } catch (e) {
    showError(e.message);
  } finally {
    $("sendBtn").disabled = false;
    $("sendBtn").textContent = "🚨 SEND EMERGENCY ALERT";
  }
});

$("refreshBtn").addEventListener("click", loadHistory);

async function loadHistory() {
  try {
    const res = await fetch("/api/history");
    const rows = await res.json();
    $("history").innerHTML = rows.map(r => `
      <tr>
        <td>${escapeHtml(r.timestamp)}</td>
        <td><strong>${escapeHtml(r.priority)}</strong></td>
        <td>${escapeHtml(r.emergency_type)}</td>
        <td>${escapeHtml(r.status)}</td>
        <td>${escapeHtml(r.message)}</td>
      </tr>
    `).join("");
  } catch(e) {
    console.error(e);
  }
}

async function loadHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    $("connectionBadge").textContent = data.internet ? "ONLINE" : "OFFLINE";
    $("connectionText").textContent =
      data.internet
        ? "Server is reachable. Internet alert processing is available."
        : "Internet is unavailable. The server is still reachable, but external SMS/API delivery may not work.";
  } catch(e) {
    $("connectionBadge").textContent = "SERVER OFFLINE";
    $("connectionText").textContent = "Cannot reach the ResQAI backend.";
  }
}

function showResult(a) {
  $("resultCard").classList.remove("hidden");
  $("result").innerHTML = `
    <div class="alert-box">
      <div><b>Alert ID</b><br>${escapeHtml(a.alert_id)}</div>
      <div><b>Incident ID</b><br>${escapeHtml(a.incident_id)}</div>
      <div><b>Priority</b><br><span class="priority">${escapeHtml(a.priority)}</span></div>
      <div><b>Emergency Type</b><br>${escapeHtml(a.emergency_type)}</div>
      <div><b>AI Reason</b><br>${escapeHtml(a.reason)}</div>
      <div><b>Recommended Action</b><br>${escapeHtml(a.recommended_action)}</div>
      <div><b>Confidence</b><br>${escapeHtml(a.confidence)}</div>
      <div><b>Communication</b><br>${escapeHtml(a.communication)}</div>
    </div>
  `;

  if (a.voice_url) {
    $("voiceOutput").src = a.voice_url;
    $("voiceOutput").classList.remove("hidden");
  }
  $("resultCard").scrollIntoView({behavior:"smooth"});
}

function showError(msg) {
  $("error").textContent = msg;
  $("error").classList.remove("hidden");
}
function hideError() {
  $("error").classList.add("hidden");
}
function escapeHtml(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

loadHealth();
loadHistory();
setInterval(loadHealth, 15000);
