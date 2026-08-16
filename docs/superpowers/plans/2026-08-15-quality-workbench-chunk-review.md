# 187-P1 Quality Workbench Chunk Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing RAG quality workbench so a user can enter from a specific material, inspect its indexed chunks, edit a selected chunk with a visible before/after diff, and run a scoped retrieval test without losing the existing file → extraction job → Trace contract.

**Architecture:** Keep the existing global entry at `站点管理 → RAG 质量工作台` and the existing file-row shortcut at `资料大厅/资料库总览 → … → 质量工作台`. Extend the existing workbench page with three bounded client-side panels: chunk navigation backed by `GET /knowledge-base/files/{file_id}/chunks`, correction backed by the existing owner/admin chunk patch contract, and retrieval testing backed by `POST /knowledge-base/search` with the current file ACL scope. Do not add a new fact source, change the 187.1 aggregate API, or rewrite the original uploaded file.

**Tech Stack:** React/TypeScript, Ant Design, React Router search params, existing FileX knowledge-base APIs, Vitest.

## Global Constraints

- Keep `file_id → extraction job → Trace` selection deterministic; changing file or job clears dependent selections.
- Chunk preview and retrieval results must stay inside the current material ACL scope.
- Keep raw source content read-only; chunk edits use the existing owner/admin `PATCH /knowledge-base/files/{file_id}/chunks/{chunk_id}` contract and retain the original text for diff display.
- Retrieval test is diagnostic only: use the selected `file_id`, do not mutate production routing, and display bounded result text/citation metadata.
- Preserve `light/dark` semantic CSS variables, Chinese/English i18n, and all existing loading/empty/unknown/missing/partial/forbidden/error/truncated states.

---

### Task 1: Lock the workbench interaction contract

**Files:**
- Modify: `frontend/src/pages/admin/QualityWorkbench.test.tsx`
- Modify: `frontend/src/components/FileList.test.ts`
- Inspect only: `frontend/src/components/AdminOpsNavMenu.test.tsx`, `frontend/src/api/knowledgeBase.ts`

**Interfaces:**
- Consumes: existing `getQualityWorkbenchOptions`, `getQualityWorkbench`, `listKnowledgeBaseFileChunks`, `patchKnowledgeBaseChunk`, and `searchKnowledgeBase` APIs.
- Produces: failing UI assertions for chunk loading, selection, correction diff, and file-scoped retrieval testing.

- [ ] **Step 1: Add failing tests for the user flow**

  Add tests that render the workbench with a `file_id`, mock the existing API functions, and assert:
  - the page requests chunks only after a valid file scope is present;
  - selecting a chunk shows its source/range and original text;
  - editing text shows the original/edited comparison and calls `patchKnowledgeBaseChunk` with `{text, reembed: true}`;
  - the retrieval test calls `searchKnowledgeBase` with `file_ids: [358]`, `top_k`, `return_search_trace: true`, `citation_format: 'json'`, and displays returned results;
  - an empty chunk list and a search failure render localized messages.

- [ ] **Step 2: Run the focused test and verify the expected RED failure**

  Run:

  ```bash
  NODE_ENV=test npm test -- --run src/pages/admin/QualityWorkbench.test.tsx
  ```

  Expected: FAIL because the current page only renders projection JSON and does not load chunk data or expose correction/search controls.

- [ ] **Step 3: Add the file-entry assertion if needed**

  Keep the existing assertion that `qualityWorkbenchPath(358)` returns `/admin/knowledge-base/quality-workbench?file_id=358`; do not create a second menu route. If the existing test does not cover admin gating, add one assertion that the shortcut remains admin-only through the existing `isAdmin` branch.

### Task 2: Implement the three-panel workbench

**Files:**
- Modify: `frontend/src/pages/admin/QualityWorkbench.tsx`
- Modify: `frontend/src/pages/admin/QualityWorkbench.css`
- Modify: `frontend/src/api/knowledgeBase.ts` only if a type needed by the existing APIs is missing
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/en.ts`

**Interfaces:**
- Consumes: `QualityWorkbenchOptionsResponse`, `KbChunkListResponse`, `KbChunkDetail`, `KbSearchResponse`, and existing patch/search functions.
- Produces: a full-screen workbench with:
  - scope toolbar for material/job/Trace/strategy;
  - left chunk/outline navigation;
  - center read-only source preview and locator metadata;
  - right tabs for correction, retrieval test, and change status;
  - bounded loading, empty, error, and permission states.

- [x] **Step 1: Implement chunk loading state and selection**

  Add `chunks`, `chunksLoading`, `chunksError`, and `selectedChunkId` state. When `fileId` changes, clear the selected chunk and load page 1 with `listKnowledgeBaseFileChunks(fileId, {page: 1, page_size: 100})`. Select the first returned chunk only after a successful non-empty response.

- [x] **Step 2: Implement the left navigation and center preview**

  Render chunk index, `heading_path`, `loc_label`, `block_type`, `content_kind`, and a bounded text preview in the left panel. Render the selected chunk’s full bounded text, source, character range, and content metadata in the center panel. Keep the original text in state whenever editing begins so the diff remains available after the text area changes.

- [x] **Step 3: Implement correction with explicit diff and existing write contract**

  Add an edit textarea initialized from the selected chunk. Disable save when the trimmed content is empty or unchanged. On save, call:

  ```ts
  patchKnowledgeBaseChunk(fileId, selectedChunk.id, {
    text: editedText,
    reembed: true,
  })
  ```

  On success, keep the selected chunk visible and show the original/edited diff plus the change status. The UI states that the source file is unchanged and that the operation is owner/admin controlled by the existing API. Do not call the whole-file reindex endpoint after a successful chunk patch, because the patch endpoint already performs the partial re-embed and a full reindex would overwrite the manual chunk edit.

- [x] **Step 4: Implement retrieval test**

  Add a query input and test button. Call:

  ```ts
  searchKnowledgeBase({
    query,
    file_ids: [fileId],
    top_k: 5,
    debug: true,
    return_search_trace: true,
    citation_format: 'json',
  })
  ```

  Render result rank, score, chunk index, citation/location, bounded text, and the search funnel when present. Keep failures local to the test panel rather than replacing the loaded workbench projection.

- [x] **Step 5: Add the change-status tab and responsive layout**

  Show the selected material, job, Trace, chunk ID, parser/model/chunk/index versions, edit status, and last retrieval-test status. Use the existing semantic variables and responsive breakpoints so the three panels stack without hiding the primary action on narrow screens.

- [x] **Step 6: Run the focused test and verify GREEN**

  Run:

  ```bash
  NODE_ENV=test npm test -- --run src/pages/admin/QualityWorkbench.test.tsx src/components/FileList.test.ts src/components/AdminOpsNavMenu.test.tsx
  ```

  Expected: all focused workbench and menu tests pass.

### Task 3: Verify, document, and hand off

**Files:**
- Modify: `specs/187-p1-rag-quality-workbench/plan.md`
- Modify: `specs/187-p1-rag-quality-workbench/tasks.md`
- Modify: `specs/187-p1-rag-quality-workbench/spec.md` only to record the approved UI extension and its direct-chunk-patch boundary

- [x] **Step 1: Record the incremental UI task**

  Add a `T-5c` entry and plan section stating that the route/menu are unchanged, the file-row shortcut passes `file_id`, the workbench loads bounded chunks, correction uses the existing owner/admin patch API, and retrieval testing is file-scoped and diagnostic-only.

- [x] **Step 2: Run the system verification**

  Run:

  ```bash
  NODE_ENV=test npm test
  npm run build
  git diff --check
  ```

  Expected: the complete frontend suite passes, the production build succeeds, and `git diff --check` produces no output.

- [x] **Step 3: Inspect the rendered route**

  Open `/admin/knowledge-base/quality-workbench?file_id=358` in the local app and verify the menu path `站点管理 → RAG质量工作台` plus the material-row `… → 质量工作台` shortcut. Confirm selecting a job/Trace does not leak another material’s chunks or search results.

- [x] **Step 4: Review the final diff**

  Confirm only the workbench UI, its tests/styles/i18n, and the 187-P1 task/spec records changed. Do not stage `.superpowers/brainstorm/`; it is a discussion prototype, not product code.

## Closure evidence

- Chunk navigation uses the existing 100-item page bound and offers continued loading when more chunks exist.
- The correction panel states that saving requires the file owner or an admin, matching the existing API ACL contract.
- The route and final diff were reviewed after the follow-up closeout change; focused and full frontend tests, production build, and `git diff --check` are recorded in the feature review report.
