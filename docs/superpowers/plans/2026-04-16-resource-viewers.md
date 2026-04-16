# Resource File Viewers — Proposal

**Goal:** Make the OUTPUTS panel's file rows clickable. Clicking opens a modal viewer chosen by mimetype: markdown/text (rendered), PDF, CSV (table), image, and a plain-text fallback that covers JSON and anything else.

**Status:** proposal, not yet implemented.

---

## What exists today

- **Blob storage.** Content-addressed on disk at `${ERGON_BLOB_ROOT}/<sha256[:2]>/<sha256>` (default `/var/ergon/blob`). Two writers — `_write_blob` in `ergon_builtins/ergon_builtins/workers/baselines/researcher_stub_worker.py:313` and `ergon_core/ergon_core/core/providers/sandbox/resource_publisher.py:176` — share this scheme.
- **DB row.** `RunResource` carries `id`, `name`, `mime_type`, `size_bytes`, `file_path` (absolute path to the blob), plus `content_hash`. Already serialized into `RunSnapshotDto.resourcesByTask` via `_task_keyed_resources` in `ergon_core/core/api/runs.py`.
- **No content endpoint.** `runs.py` exposes snapshot / generations / mutations / training metrics only. Nothing streams blob bytes.
- **Frontend.** `ergon-dashboard/src/components/panels/ResourcePanel.tsx` renders `ResourceItem` rows — icon, name, size, mime badge, timestamp. **No click handler, no modal.** Data shape is `ResourceState` (`lib/types.ts:224`).
- **Modal primitive.** None. No Radix, no shadcn, no headless UI in `package.json`. Tailwind only.
- **Mimetypes in flight.** `text/markdown`, `text/plain`, `application/json`, `application/pdf`, `image/*`, `text/csv` — inferred by Python's `mimetypes.guess_type()` plus the stub worker's explicit `text/markdown`.

---

## Design

### 1. Backend: content endpoint

**New route** in `ergon_core/core/api/runs.py`:

```
GET /runs/{run_id}/resources/{resource_id}/content
  → 200 streaming bytes, `Content-Type` = resource.mime_type,
    `Content-Length` = resource.size_bytes,
    `Content-Disposition` = inline; filename="{resource.name}"
```

- Look up `RunResource` by `(run_id, resource_id)`. 404 if missing.
- Resolve `file_path`, validate it sits under `settings.blob_root` (path traversal guard — cheap but important).
- Stream via `FileResponse` (starlette). No transformation.
- Add a soft cap — reject with 413 if `size_bytes > 10 MiB` for v1. The viewer modal isn't a download manager.

No new tables, no new events, no migration. This is a pure read path.

### 2. Frontend: modal primitive

Build a minimal `<Dialog>` around the native `<dialog>` element (supported in all targeted browsers; Tailwind-styleable; handles Escape and backdrop click for free). Single file, ~50 lines, at `ergon-dashboard/src/components/ui/Dialog.tsx`.

Not worth pulling Radix/shadcn just for this. If the dashboard grows more overlay surfaces later, migrate then.

### 3. Viewer components

One folder: `ergon-dashboard/src/components/viewers/`. Each file is a leaf component that takes a resource descriptor plus the fetched `Blob`/`string` and renders it.

| Mimetype pattern | Viewer | Library |
|---|---|---|
| `text/markdown` | `MarkdownViewer.tsx` — rendered GFM | `react-markdown` + `remark-gfm` (already common, small) |
| `text/*`, `application/json`, default | `TextViewer.tsx` — monospace `<pre>` with line numbers | none |
| `application/pdf` | `PdfViewer.tsx` — `<iframe>` pointing at the content URL | none |
| `text/csv` | `CsvViewer.tsx` — parsed table, truncated at 500 rows | `papaparse` |
| `image/*` | `ImageViewer.tsx` — `<img>` with contain fit | none |

A dispatcher `resolveViewer(mimeType)` in `viewers/index.ts` returns the right component; otherwise `TextViewer` is the lean fallback (covers JSON per the request).

### 4. Wiring it up

- `ResourceItem` becomes a `<button>` with an `onClick` that sets modal state in `ResourcePanel`.
- `ResourcePanel` owns a single `selectedResourceId` state and renders one `<Dialog>` at a time.
- Inside the dialog, a `useResourceContent(runId, resourceId, mimeType)` hook:
  - For binary/embed viewers (PDF, image): returns the content URL directly, no fetch.
  - For text viewers (markdown, text, csv): `fetch()` + `response.text()`, cache the result in a `Map<resourceId, string>` so reopening is free.
- `runId` is already available on the `ResourcePanel` parent route; thread it through as a prop.

---

## Effort

Rough breakdown assuming the scope above, one person, no scope creep:

| Phase | Work | Effort |
|---|---|---|
| 1. Backend endpoint + 413 cap + path-traversal guard + test | `runs.py` route, `tests/state/test_resource_content_api.py` | **~2–3 hrs** |
| 2. Dialog primitive | `components/ui/Dialog.tsx` | **~1 hr** |
| 3. Text + Markdown viewers | Two components; add `react-markdown`/`remark-gfm` | **~2 hrs** |
| 4. PDF + Image viewers | Both are trivial (`<iframe>` and `<img>`) | **~1 hr** |
| 5. CSV viewer | `papaparse`, virtualized not required at 500-row cap | **~2 hrs** |
| 6. Wire up `ResourcePanel` — click, state, hook, cache | ~80 lines changed in existing file | **~2 hrs** |
| 7. Manual smoke + `pnpm run check:fe` + visual polish | — | **~1–2 hrs** |

**Total: ~1–1.5 days** of focused work.

---

## Non-goals (deliberately out of scope)

- **No editor.** Read-only. Download button optional later.
- **No streaming / chunked rendering.** The 10 MiB cap handles it. If we hit that for real workloads, revisit.
- **No syntax highlighting for JSON.** Request said "lean just as text file" — honored. A `JsonViewer` with collapsible tree can come later.
- **No thumbnails in the OUTPUTS list.** Keeps the panel fast; modal is opt-in.
- **No unification of the two `_write_blob` copies.** Pre-existing duplication; fix in a separate tidy commit if desired.

---

## Open questions

1. **Auth.** The dashboard currently trusts the API. If that changes, the content endpoint needs the same middleware — cheap to add later, noting here so it doesn't get missed.
2. **Blob root inside Docker.** `/var/ergon/blob` is shared between the `api` container and the worker. Confirmed writeable mount exists today (stub worker writes there). The content endpoint reads from the same mount — no new volume config.
3. **CSP for PDF `<iframe>`.** Next.js's default headers allow same-origin iframes. If we add a strict CSP later, `frame-src 'self'` must be retained.
4. **react-markdown vs `marked` + DOMPurify.** `react-markdown` is safer (no `dangerouslySetInnerHTML`), so prefer it. Flagging only because the bundle grows ~30KB gz.

---

## Suggested PR shape

Single PR, small, reviewable. No migration. No runtime behavior change on the data path — purely additive read surface. Safe to revert.
