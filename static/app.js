// Initialize SocketIO
const socket = io();

// Select DOM elements
const master = document.getElementById("master-checkbox");
const rows = document.querySelectorAll(".row-checkbox");
const selectAllBtn = document.getElementById("select-all");
const downloadBtn = document.getElementById("download-selected");
const retryBtn = document.getElementById("retry-failed");
const downloadZipBtn = document.getElementById("download-zip");
let hasSuccessfulDownloads = false;

// Get CSRF token from hidden input
const getCsrfToken = () => {
  const tokenElement = document.querySelector('input[name="csrf_token"]');
  if (!tokenElement || !tokenElement.value) {
    console.error("CSRF token not found. Ensure the form is rendered correctly.");
    alert("CSRF token missing. Please refresh the page and try again.");
    return null;
  }
  return tokenElement.value;
};

// Select all functionality
master?.addEventListener("change", () => {
  rows.forEach((chk) => (chk.checked = master.checked));
});

selectAllBtn?.addEventListener("click", () => {
  const anyUnchecked = [...rows].some((chk) => !chk.checked);
  rows.forEach((chk) => (chk.checked = anyUnchecked));
  master.checked = anyUnchecked;
});

// Handle real-time progress updates
socket.on("download_progress", (data) => {
  const row = document.querySelector(`tr[data-index='${data.index}'] .status`);
  if (!row) return;

  const statusText = row.querySelector(".status-text");
  const downloadBtn = row.querySelector(".download-btn");
  if (!statusText || !downloadBtn) return;

  statusText.textContent = data.message;
  if (data.status === "downloading") {
    row.className = "status downloading";
    downloadBtn.style.display = "none";
  } else if (data.status === "success") {
    row.className = "status success";
    downloadBtn.style.display = "inline-block";
    // Set href based on sanitized song title
    const song = rows[data.index].closest("tr").querySelector("td:nth-child(2)").textContent;
    const sanitized = song.replace(/[\\/*?:"<>|]/g, "");
    downloadBtn.href = `/downloads/${encodeURIComponent(sanitized)}.mp3`;
    hasSuccessfulDownloads = true;
    downloadZipBtn.style.display = hasSuccessfulDownloads ? "inline-block" : "none";
  } else if (data.status === "failed") {
    row.className = "status error";
    downloadBtn.style.display = "none";
  } else if (data.status === "finished") {
    row.className = "status downloading";
    downloadBtn.style.display = "none";
  }
});

// Download selected songs
downloadBtn?.addEventListener("click", () => {
  const selected = [...rows]
    .map((chk, i) => (chk.checked ? i : -1))
    .filter((i) => i >= 0);
  if (!selected.length) {
    alert("Please select at least one song.");
    return;
  }

  const csrfToken = getCsrfToken();
  if (!csrfToken) return;

  // Set initial status to "Pending"
  selected.forEach((i) => {
    const row = document.querySelector(`tr[data-index='${i}'] .status`);
    const statusText = row.querySelector(".status-text");
    const downloadBtn = row.querySelector(".download-btn");
    if (statusText && downloadBtn) {
      statusText.textContent = "Pending";
      row.className = "status pending";
      downloadBtn.style.display = "none";
    }
  });

  // Submit form via fetch
  fetch("/download", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": csrfToken,
    },
    body: selected.map((i) => `selected=${i}`).join("&"),
  })
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP error! Status: ${res.status}`);
      return res.json();
    })
    .then((data) => {
      // SocketIO handles real-time updates
    })
    .catch((err) => {
      console.error("Download error:", err);
      selected.forEach((i) => {
        const row = document.querySelector(`tr[data-index='${i}'] .status`);
        const statusText = row.querySelector(".status-text");
        if (statusText) {
          statusText.textContent = "Failed";
          row.className = "status error";
        }
      });
      alert("Download failed. Please try again.");
    });
});

// Retry failed downloads
retryBtn?.addEventListener("click", () => {
  const csrfToken = getCsrfToken();
  if (!csrfToken) return;

  fetch("/retry-failed", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
  })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
      return response.json();
    })
    .then((results) => {
      // SocketIO handles real-time updates
    })
    .catch((err) => {
      console.error("Retry failed error:", err);
      alert("Failed to retry downloads. Please try again.");
    });
});

// Download all as ZIP
downloadZipBtn?.addEventListener("click", () => {
  const csrfToken = getCsrfToken();
  if (!csrfToken) return;

  fetch("/download_zip", {
    method: "POST",
    headers: {
      "X-CSRFToken": csrfToken,
    },
  })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
      return response.blob();
    })
    .then((blob) => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "downloaded_songs.zip";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    })
    .catch((err) => {
      console.error("Download ZIP error:", err);
      alert("Failed to download ZIP file. Please try again.");
    });
});