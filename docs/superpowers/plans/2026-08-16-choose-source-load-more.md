# Choose Source Load More Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After automatic YouTube download fails, store up to nine leftover hits from that same search and let the Choose source dialog append them three at a time with Load more.

**Architecture:** Raise `PICKER_SOURCE_LIMIT` to 9 so `collect_picker_sources` keeps more leftovers on `Job.source_choices`. GET `/tracks/<index>/sources` already returns that stored list; do not add a route. The dialog still paints three cards first. **Load more** (`type="button"`) appends the next three or the remainder. Reopening starts at three again. POST `/choose-source` and thumbnails still allow any stored 11-character id.

**Tech Stack:** Flask, vanilla JS, Jinja, pytest. No new dependencies.

## Global Constraints

- Picker is failure-only; **Start selected** and **Retry failed** keep their current meaning.
- Leftover filters stay unchanged: drop tried ids, duration `< 90` or `>= 600` when present, movie/scene, clean/non-explicit, and processed-variant titles. Keep label, lyric, soundtrack, music video, and visualizer hits that pass those filters.
- Store at most **nine** leftover records (`id`, `title`, `channel`, `duration`). Search stays `ytsearch15`.
- Dialog page size is **3**. Do not put page size in `app.py`.
- No second YouTube search, no pasted URLs, no YouTube embed.
- Do not widen CSP `img-src` beyond `'self' data:`.
- Accept only an 11-character YouTube id (`[A-Za-z0-9_-]{11}`) already in that track’s stored list.
- Do not 409 **Choose source** when the library folder is unusable.
- Do not hit live YouTube or iTunes in tests; mock yt-dlp and HTTP.
- `source_choices` stays process-local memory on `Job`; never write it under `DATA_ROOT`.

## File map

- `app.py` — `PICKER_SOURCE_LIMIT = 9` (already used by `collect_picker_sources`).
- `tests/test_app.py` — nine-cap, GET full list, updated existing leftover assertion, dialog contract.
- `templates/index.html` — **Load more** in the source dialog footer.
- `static/app.js` — `PICKER_PAGE_SIZE = 3`, first page, append on click, hide when exhausted.
- `static/style.css` — footer row so **Load more** sits beside **Close**.

Do not split `app.py`. Do not add a new route.

---

### Task 1: Store up to nine leftovers

**Files:**
- Modify: `app.py` (`PICKER_SOURCE_LIMIT = 3` near `youtube_video_id`)
- Test: `tests/test_app.py` (`test_collect_picker_sources_keeps_label_hits_and_drops_tried_or_junk` and new tests after it)

**Interfaces:**
- Consumes: existing `collect_picker_sources(entries, tried_ids)` filters and ranking
- Produces: `PICKER_SOURCE_LIMIT = 9`; GET `/tracks/<index>/sources` continues to return the full stored list (0–9)

- [ ] **Step 1: Write the failing tests**

The current leftover test expects three ids. After the cap is 9, `noduration1` also passes the filters (no duration, not junk) and must be included. Replace the id assertion in `test_collect_picker_sources_keeps_label_hits_and_drops_tried_or_junk`:

```python
    ids = [item["id"] for item in picked]
    assert ids == ["labellabel1", "soundtracks", "lyriclyric1", "noduration1"]
```

Keep the `picked[0]` dict assertion and the `youtube_video_id` assertions.

Add immediately after that test:

```python
def test_collect_picker_sources_caps_at_nine():
    entries = [
        {
            "id": f"pick{i:07d}",
            "title": "Halo",
            "uploader": "Starling",
            "duration": 200,
            "view_count": 1000 - i,
        }
        for i in range(10)
    ]
    picked = application.collect_picker_sources(entries, set())
    assert application.PICKER_SOURCE_LIMIT == 9
    assert [item["id"] for item in picked] == [f"pick{i:07d}" for i in range(9)]


def test_sources_route_returns_all_stored_leftovers(app, client):
    upload_csv(app, client)
    job = current_job(client)
    job.failed.add(0)
    job.statuses[0] = {
        "job_id": job.job_id,
        "index": 0,
        "status": "failed",
        "message": "failed",
        "can_choose_source": True,
    }
    job.source_choices[0] = [
        {"id": f"pick{i:07d}", "title": "Halo", "channel": "Starling", "duration": 200}
        for i in range(9)
    ]
    listed = client.get("/tracks/0/sources")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json["sources"]] == [f"pick{i:07d}" for i in range(9)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_collect_picker_sources_keeps_label_hits_and_drops_tried_or_junk tests/test_app.py::test_collect_picker_sources_caps_at_nine tests/test_app.py::test_sources_route_returns_all_stored_leftovers`

Expected: `test_collect_picker_sources_caps_at_nine` FAIL (`PICKER_SOURCE_LIMIT == 3` or nine ids not returned). The updated leftover test FAIL (`noduration1` missing). The GET test may PASS already (route does not truncate); that is acceptable.

- [ ] **Step 3: Raise the cap**

In `app.py`, change only:

```python
PICKER_SOURCE_LIMIT = 9
```

Do not change `collect_picker_sources` body. It already slices with `PICKER_SOURCE_LIMIT`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_collect_picker_sources_keeps_label_hits_and_drops_tried_or_junk tests/test_app.py::test_collect_picker_sources_caps_at_nine tests/test_app.py::test_sources_route_returns_all_stored_leftovers tests/test_app.py::test_choose_source_routes_require_failed_stored_id tests/test_app.py::test_source_thumbnail_allows_only_stored_id tests/test_app.py::test_process_song_stores_picker_sources_and_can_choose_flag`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Store up to nine leftover Choose source hits."
```

---

### Task 2: Load more in the source dialog

**Files:**
- Modify: `templates/index.html` (the `#source-dialog` block)
- Modify: `static/app.js` (source dialog helpers and `openSourceDialog`)
- Modify: `static/style.css` (after `.choose-source`)
- Test: `tests/test_app.py` (`test_render_includes_accessibility_and_local_ui_contract` plus a dialog contract test)

**Interfaces:**
- Consumes: GET `/tracks/<index>/sources` `{ sources: [...] }` from Task 1 (full stored list)
- Produces: `#source-dialog-more`, `PICKER_PAGE_SIZE = 3` in `static/app.js`, append-next-page behavior

- [ ] **Step 1: Write the failing contract tests**

In `test_render_includes_accessibility_and_local_ui_contract`, after the existing `id="source-dialog"` assertion, add:

```python
    assert b'id="source-dialog-more"' in response.data
    assert b"Load more" in response.data
```

Add after `test_failed_row_renders_choose_source_when_flag_set`:

```python
def test_source_dialog_load_more_is_a_non_submit_button():
    html = Path("templates/index.html").read_text(encoding="utf-8")
    assert 'id="source-dialog-more" type="button" hidden' in html
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "const PICKER_PAGE_SIZE = 3;" in js
    assert "source-dialog-more" in js
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert ".source-dialog-actions" in css
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract tests/test_app.py::test_source_dialog_load_more_is_a_non_submit_button`

Expected: FAIL (missing `source-dialog-more` / `PICKER_PAGE_SIZE`)

- [ ] **Step 3: Add the footer button**

Replace the Close-only footer in `templates/index.html` with:

```html
    <dialog id="source-dialog" aria-labelledby="source-dialog-title">
      <form method="dialog" class="source-dialog-chrome">
        <h2 id="source-dialog-title">Choose a source</h2>
        <p id="source-dialog-meta"></p>
        <div id="source-dialog-cards" class="source-cards"></div>
        <div class="source-dialog-actions">
          <button class="button button-quiet" id="source-dialog-more" type="button" hidden>Load more</button>
          <button class="button button-quiet" id="source-dialog-close" value="cancel">Close</button>
        </div>
      </form>
    </dialog>
```

`type="button"` is required so **Load more** does not close the `method="dialog"` form.

- [ ] **Step 4: Page the cards in `static/app.js`**

Next to the existing source dialog locals, add:

```javascript
  const sourceMore = document.getElementById("source-dialog-more");
  const PICKER_PAGE_SIZE = 3;
  let sourceDialogIndex = null;
  let storedSources = [];
  let shownCount = 0;
```

Replace the card-building `forEach` inside `openSourceDialog` with helpers. Keep thumbnail URLs, duration formatting, **Use this source** mutate behavior, and abort/generation guards as they are. The intended shape:

```javascript
  const updateLoadMoreVisibility = () => {
    if (sourceMore) sourceMore.hidden = storedSources.length <= shownCount;
  };

  const appendSourceCards = (index, sources) => {
    sources.forEach((source) => {
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
        if (sourceMore) sourceMore.disabled = true;
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
          if (sourceMore) sourceMore.disabled = false;
          announce(error.status === 429 ? "Too many requests. Wait a moment and try again." : error.message, "error");
        }
      });
      card.append(image, heading, channel, use);
      sourceCards?.append(card);
    });
  };

  const renderNextSourcePage = (index) => {
    const next = storedSources.slice(shownCount, shownCount + PICKER_PAGE_SIZE);
    appendSourceCards(index, next);
    shownCount += next.length;
    updateLoadMoreVisibility();
  };
```

In `openSourceDialog`, after a successful fetch (and the generation check), replace painting every `data.sources` card with:

```javascript
      storedSources = data.sources || [];
      shownCount = 0;
      sourceDialogIndex = index;
      if (sourceCards) sourceCards.replaceChildren();
      if (sourceMore) sourceMore.disabled = false;
      renderNextSourcePage(index);
```

Keep the existing `sourceCards.replaceChildren()` that runs before `showModal()` so a reopen does not flash the previous cards.

Wire the button once, next to the other source-dialog listeners:

```javascript
  sourceMore?.addEventListener("click", (event) => {
    event.preventDefault();
    if (sourceDialogIndex == null || sourceMore.hidden) return;
    renderNextSourcePage(sourceDialogIndex);
  });
```

On close, `finalizeSourceDialogClose` does not need to clear `storedSources`; the next open resets `shownCount` to 0 and paints three cards from a fresh GET.

- [ ] **Step 5: Footer CSS**

In `static/style.css`, after `.choose-source { margin-left: 8px; }`:

```css
.source-dialog-actions { display: flex; gap: 8px; flex-wrap: wrap; }
```

- [ ] **Step 6: Run tests and syntax check**

Run: `python -m pytest -q tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract tests/test_app.py::test_source_dialog_load_more_is_a_non_submit_button tests/test_app.py::test_failed_row_renders_choose_source_when_flag_set tests/test_app.py::test_sources_route_returns_all_stored_leftovers`

Then: `python -m pytest -q`

Then: `node --check static/app.js`

Expected: all PASS; `node --check` exits 0.

- [ ] **Step 7: Commit**

```bash
git add templates/index.html static/app.js static/style.css tests/test_app.py
git commit -m "Page leftover Choose source hits with Load more."
```

---

## Spec coverage

| Spec requirement | Task |
|---|---|
| Leftover filters unchanged | 1 (existing test kept, now includes `noduration1`) |
| Store at most nine; tenth dropped | 1 `test_collect_picker_sources_caps_at_nine` |
| GET returns full stored list | 1 `test_sources_route_returns_all_stored_leftovers` |
| No new route; allow-list is stored ids | 1 (existing CSRF/forged-id tests) |
| Dialog opens with three; Load more appends three or remainder | 2 |
| Load more hidden when fewer than four or when exhausted | 2 (`hidden` when `sources.length <= shownCount`) |
| Reopen starts at three | 2 (`shownCount = 0` on each open) |
| `type="button"` so the dialog does not close | 2 |
| Page size 3 in JS, not `app.py` | 2 `PICKER_PAGE_SIZE` |
| No library-folder 409 on choose-source | neither task |
| Automatic ranking / CSP / Start / Retry unchanged | neither task |
