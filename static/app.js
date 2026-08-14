(() => {
  "use strict";

  const body = document.body;
  const jobId = body.dataset.jobId;
  const selectionLimit = Number(body.dataset.selectionLimit || 2000);
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const toastRegion = document.getElementById("toast-region");
  const rows = [...document.querySelectorAll(".track-table tbody tr")];
  const checkboxes = [...document.querySelectorAll(".row-checkbox")];
  const master = document.getElementById("master-checkbox");
  const selectAllButton = document.getElementById("select-all");
  const startButton = document.getElementById("download-selected");
  const retryButton = document.getElementById("retry-failed");
  const zipButton = document.getElementById("download-zip");
  const clearButton = document.getElementById("clear-job");

  const announce = (message, tone = "info") => {
    if (!toastRegion) return;
    const toast = document.createElement("div");
    toast.className = `toast toast-${tone}`;
    toast.setAttribute("role", tone === "error" ? "alert" : "status");
    toast.textContent = message;
    toastRegion.replaceChildren(toast);
    window.setTimeout(() => toast.remove(), 6000);
  };

  const csrfToken = () => csrfMeta?.content || "";

  const parseResponse = async (response) => {
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : { error: await response.text() };
    if (!response.ok) {
      const error = new Error(data.error || `Request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return data;
  };

  const mutate = async (url, options = {}) => {
    const response = await fetch(url, {
      method: "POST",
      credentials: "same-origin",
      ...options,
      headers: {
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
        ...(options.headers || {}),
      },
    });
    return parseResponse(response);
  };

  const withBusyButton = async (button, busyLabel, task) => {
    if (!button || button.disabled) return;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = busyLabel;
    try {
      await task();
    } catch (error) {
      announce(error.status === 429 ? "Too many requests. Wait a moment and try again." : error.message, "error");
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  };

  const selectedIndices = () => checkboxes.filter((box) => box.checked).map((box) => Number(box.value));

  const updateSelection = () => {
    const count = selectedIndices().length;
    const metric = document.getElementById("metric-selected");
    if (metric) metric.textContent = String(count);
    if (master) {
      const selectable = Math.min(checkboxes.length, selectionLimit);
      master.checked = Boolean(selectable) && count === selectable;
      master.indeterminate = count > 0 && !master.checked;
    }
  };

  const updateSummary = () => {
    const complete = rows.filter((row) => row.dataset.state === "success").length;
    const failed = rows.filter((row) => row.dataset.state === "failed").length;
    const settled = complete + failed;
    const percent = rows.length ? Math.round((settled / rows.length) * 100) : 0;
    const readyMetric = document.getElementById("metric-ready");
    const failedMetric = document.getElementById("metric-failed");
    const overall = document.getElementById("overall-progress");
    const label = document.getElementById("overall-label");
    if (readyMetric) readyMetric.textContent = String(complete);
    if (failedMetric) failedMetric.textContent = String(failed);
    if (overall) overall.value = percent;
    if (label) label.textContent = `${percent}%`;
    if (zipButton) zipButton.hidden = complete === 0;
  };

  const setTrackState = (data) => {
    if (data.job_id !== jobId) return;
    const row = document.querySelector(`tr[data-index="${CSS.escape(String(data.index))}"]`);
    if (!row) return;
    row.dataset.state = data.status;
    const status = row.querySelector(".status-text");
    const progress = row.querySelector(".track-progress");
    const link = row.querySelector(".download-link");
    if (status) status.textContent = data.message || data.status;
    if (progress) {
      const hasProgress = data.status === "downloading" && Number.isFinite(Number(data.progress));
      progress.hidden = !hasProgress;
      if (hasProgress) progress.value = Number(data.progress);
    }
    if (link) {
      if (data.status === "success" && data.download_url) {
        link.href = data.download_url;
        link.hidden = false;
      } else if (data.status !== "success") {
        link.hidden = true;
        link.removeAttribute("href");
      }
    }
    const choose = row.querySelector(".choose-source");
    if (choose) {
      const show = data.status === "failed" && data.can_choose_source === true;
      choose.hidden = !show;
    }
    updateSummary();
  };

  checkboxes.forEach((box) => box.addEventListener("change", updateSelection));
  master?.addEventListener("change", () => {
    checkboxes.forEach((box, index) => {
      box.checked = master.checked && index < selectionLimit;
    });
    updateSelection();
  });
  selectAllButton?.addEventListener("click", () => {
    const target = !checkboxes.slice(0, selectionLimit).every((box) => box.checked);
    checkboxes.forEach((box, index) => {
      box.checked = target && index < selectionLimit;
    });
    updateSelection();
  });

  startButton?.addEventListener("click", () => withBusyButton(startButton, "Starting…", async () => {
    const selected = selectedIndices();
    if (!selected.length) throw new Error("Select at least one track.");
    if (selected.length > selectionLimit) throw new Error(`Select no more than ${selectionLimit} tracks.`);
    selected.forEach((index) => setTrackState({ job_id: jobId, index, status: "queued", message: "Queued" }));
    const result = await mutate("/download", {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected }),
    });
    announce(`${result.started.length} track${result.started.length === 1 ? "" : "s"} queued.`, "success");
  }));

  retryButton?.addEventListener("click", () => withBusyButton(retryButton, "Retrying…", async () => {
    const result = await mutate("/retry-failed", { headers: { "Content-Type": "application/json" }, body: "{}" });
    announce(`${result.started.length} failed track${result.started.length === 1 ? "" : "s"} queued.`, "success");
  }));

  const sourceDialog = document.getElementById("source-dialog");
  const sourceMeta = document.getElementById("source-dialog-meta");
  const sourceCards = document.getElementById("source-dialog-cards");
  let sourceOpener = null;
  let sourceDialogGeneration = 0;
  let sourceDialogAbortController = null;

  const invalidateSourceDialogFetch = () => {
    sourceDialogGeneration += 1;
    sourceDialogAbortController?.abort();
    sourceDialogAbortController = null;
  };

  const formatDuration = (seconds) => {
    if (seconds == null || !Number.isFinite(Number(seconds))) return "";
    const total = Math.max(0, Math.floor(Number(seconds)));
    const minutes = Math.floor(total / 60);
    const remain = String(total % 60).padStart(2, "0");
    return `${minutes}:${remain}`;
  };

  const finalizeSourceDialogClose = () => {
    invalidateSourceDialogFetch();
    sourceOpener?.focus();
    sourceOpener = null;
  };

  const closeSourceDialog = () => {
    sourceDialog?.close();
  };

  const sourceCardButtons = () => [...(sourceCards?.querySelectorAll("button") || [])];

  const disableSourceCardButtons = (activeButton) => {
    sourceCardButtons().forEach((btn) => {
      btn.disabled = true;
    });
    if (activeButton) activeButton.textContent = "Starting…";
  };

  const enableSourceCardButtons = () => {
    sourceCardButtons().forEach((btn) => {
      btn.disabled = false;
      btn.textContent = "Use this source";
    });
  };

  const openSourceDialog = async (button) => {
    const row = button.closest("tr");
    const index = Number(button.dataset.index);
    if (!row || row.dataset.state !== "failed" || button.hidden) return;
    invalidateSourceDialogFetch();
    const generation = sourceDialogGeneration;
    const abortController = new AbortController();
    sourceDialogAbortController = abortController;
    sourceOpener = button;
    const title = row.querySelector('[data-label="Track"] strong')?.textContent || "this track";
    const artist = row.querySelector('[data-label="Artist"]')?.textContent || "";
    if (sourceMeta) sourceMeta.textContent = `${title} · ${artist}`;
    if (sourceCards) sourceCards.replaceChildren();
    sourceDialog?.showModal();
    document.getElementById("source-dialog-close")?.focus();
    try {
      const data = await parseResponse(await fetch(`/tracks/${index}/sources`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: abortController.signal,
      }));
      if (generation !== sourceDialogGeneration) return;
      (data.sources || []).forEach((source) => {
        const card = document.createElement("article");
        card.className = "source-card";
        const image = document.createElement("img");
        image.alt = "";
        image.src = `/tracks/${index}/source-thumbs/${encodeURIComponent(source.id)}`;
        image.addEventListener("error", () => image.remove());
        const heading = document.createElement("h3");
        heading.textContent = source.title || "Untitled";
        const channel = document.createElement("p");
        channel.textContent = [source.channel, formatDuration(source.duration)].filter(Boolean).join(" · ");
        const use = document.createElement("button");
        use.type = "button";
        use.className = "button button-primary";
        use.textContent = "Use this source";
        use.addEventListener("click", async () => {
          if (use.disabled) return;
          disableSourceCardButtons(use);
          try {
            const result = await mutate("/choose-source", {
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ index, video_id: source.id }),
            });
            setTrackState({ job_id: jobId, index, status: "queued", message: "Queued" });
            closeSourceDialog();
            announce(`${result.started.length} track${result.started.length === 1 ? "" : "s"} queued.`, "success");
          } catch (error) {
            enableSourceCardButtons();
            announce(error.status === 429 ? "Too many requests. Wait a moment and try again." : error.message, "error");
          }
        });
        card.append(image, heading, channel, use);
        sourceCards?.append(card);
      });
    } catch (error) {
      if (generation !== sourceDialogGeneration || error.name === "AbortError") return;
      closeSourceDialog();
      throw error;
    }
  };

  document.querySelectorAll(".choose-source").forEach((button) => {
    button.addEventListener("click", () => {
      openSourceDialog(button).catch((error) => announce(error.message, "error"));
    });
  });
  sourceDialog?.addEventListener("close", finalizeSourceDialogClose);
  sourceDialog?.addEventListener("click", (event) => {
    if (event.target === sourceDialog) closeSourceDialog();
  });

  zipButton?.addEventListener("click", () => withBusyButton(zipButton, "Building ZIP…", async () => {
    const response = await fetch("/download_zip", {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/zip, application/json", "X-CSRFToken": csrfToken() },
    });
    if (!response.ok) {
      await parseResponse(response);
      return;
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `audio-job-${jobId.slice(0, 8)}.zip`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
    announce("ZIP download started.", "success");
  }));

  clearButton?.addEventListener("click", () => withBusyButton(clearButton, "Clearing…", async () => {
    if (!window.confirm("Clear this inactive job and remove its completed files?")) return;
    await mutate("/cleanup", { headers: { "Content-Type": "application/json" }, body: "{}" });
    window.location.assign("/");
  }));

  const schemaToggle = document.getElementById("schema-toggle");
  const schemaHelp = document.getElementById("schema-help");
  schemaToggle?.addEventListener("click", () => {
    const expanded = schemaToggle.getAttribute("aria-expanded") === "true";
    schemaToggle.setAttribute("aria-expanded", String(!expanded));
    if (schemaHelp) schemaHelp.hidden = expanded;
  });

  const fileInput = document.getElementById("csv-file");
  const dropZone = document.getElementById("drop-zone");
  const fileChip = document.getElementById("file-chip");
  const showFile = () => {
    const file = fileInput?.files?.[0];
    if (!file || !fileChip) return;
    fileChip.textContent = `${file.name} · ${(file.size / 1000).toFixed(1)} KB`;
    fileChip.hidden = false;
  };
  fileInput?.addEventListener("change", showFile);
  ["dragenter", "dragover"].forEach((eventName) => dropZone?.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  }));
  ["dragleave", "drop"].forEach((eventName) => dropZone?.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  }));
  dropZone?.addEventListener("drop", (event) => {
    if (!fileInput || !event.dataTransfer?.files.length) return;
    const transfer = new DataTransfer();
    transfer.items.add(event.dataTransfer.files[0]);
    fileInput.files = transfer.files;
    showFile();
  });
  document.getElementById("upload-form")?.addEventListener("submit", (event) => {
    if (!fileInput?.files?.length) {
      event.preventDefault();
      announce("Choose a CSV file before importing.", "error");
      return;
    }
    const button = document.getElementById("upload-button");
    if (button) {
      button.disabled = true;
      button.textContent = "Importing…";
    }
  });

  if (window.io && jobId) {
    const socket = window.io({ transports: ["websocket", "polling"] });
    socket.on("connect", () => socket.emit("join_job", { job_id: jobId }));
    socket.on("download_progress", setTrackState);
    socket.on("join_error", (data) => announce(data?.error || "Could not join the job channel.", "error"));
    socket.on("connect_error", () => announce("Live progress disconnected; reconnecting…", "error"));
  }

  updateSelection();
  updateSummary();
})();
