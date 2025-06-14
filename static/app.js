// Select all functionality
const master = document.getElementById("master-checkbox");
const rows = document.querySelectorAll(".row-checkbox");
const selectAllBtn = document.getElementById("select-all");
const downloadBtn = document.getElementById("download-selected");

master?.addEventListener("change", () => {
  rows.forEach((chk) => (chk.checked = master.checked));
});
selectAllBtn?.addEventListener("click", () => {
  const anyUnchecked = [...rows].some((chk) => !chk.checked);
  rows.forEach((chk) => (chk.checked = anyUnchecked));
  master.checked = anyUnchecked;
});

// Download selected with progress
downloadBtn?.addEventListener("click", () => {
  const selected = [...rows]
    .map((chk, i) => (chk.checked ? i : -1))
    .filter((i) => i >= 0);
  if (!selected.length) return;

  // submit form via fetch for progress
  fetch("/download", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: selected.map((i) => `selected=${i}`).join("&"),
  }).then((res) => {
    // Poll for status updates
    selected.forEach((i) => {
      const row = document.querySelector(`tr[data-index='${i}'] .status`);
      row.textContent = "Downloaded";
    });
    window.location.href = "/downloads";
  });
});
