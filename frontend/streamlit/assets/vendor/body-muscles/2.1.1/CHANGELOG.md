# Changelog

## 2.1.1 (2026-10-09)

No runtime or type changes: the published JavaScript and declarations are byte-identical to 2.1.0.

### Development

- Build with TypeScript 7 (previously 5.9). Both configs now use `moduleResolution: "bundler"`,
  because TypeScript 7 removed the legacy `node` (node10) resolution. The examples moved to
  TypeScript 7 too.
- CI now also compiles the consumer type fixture with TypeScript 5.0.4, so the documented consumer
  minimum is checked on every change rather than by hand.

### Documentation

- Credited the original project and author, Ivan Vulović, in the README, the documentation site
  footer, and package metadata, and recorded this fork's modifications in `NOTICE`.
- Corrected stale README claims: 89 regions rather than "70+", actual bundle sizes, and removed
  "automatic viewport switching", which the chart does not do.
- Restructured the README: a preview image that follows the reader's light or dark theme, a compact
  feature list, one install block covering npm, pnpm, yarn, and Bun, task-oriented guides,
  collapsible framework examples and reference tables, and a Contributing section. Removed duplicate
  utility rows. The documentation site's install tabs also gained Bun.

## 2.1.0 (2026-10-09)

### Added

- `setGroupSelection(state, group, action)` and `setBilateralSelection(state, id, action)`, with
  explicit `"select"`, `"deselect"`, and `"toggle"` actions. Toggle selects a mixed target set and
  deselects a fully selected one. Helpers preserve intensity and unrelated state without mutating
  inputs; central/unpaired regions act alone. No-op results and unchanged entries are shared.
- Canonical readonly `MUSCLE_PAIRS` tuples, available from both the root and `./data` entry points.
  Relationships are explicit and stay within the same region/view; no identifier substitution is used.
- Vanilla TypeScript group/bilateral controls and demo group selection composed through the helpers.
  Six deterministic selection regressions and consumer type checks run in CI.

### Changed

- Region refreshes reuse keyed definitions and a shared rendering-only default state, compare
  rendered values before DOM writes, and configure cursor/outline/transitions outside the state
  refresh. Reused state mappings, ambient resolver/label changes, focus, tooltips, and live CSS
  variables retain their behavior. Added an ambient-closure browser regression.
  The implementation plan records before/after Chromium profiles for repeated intensity updates;
  measurements describe a local synthetic workload, not a universal frame-rate guarantee.

### Documentation

- Redesigned the documentation site. A live playground leads the page, showing both views with an
  inspector, group and both-sides selection, and the exact `bodyState` passed to `update()`. The
  guide is reorganized into Start, Guides, Anatomy, and Reference parts with a contents rail.
  Framework and install examples use accessible tabs, catalog rows copy region identifiers, and
  duplicate or outdated reference entries were corrected.
- The site uses design tokens in a cascade-layered stylesheet and ES modules, self-hosts its fonts
  through `npm run docs:build`, and themes the chart only through public `--bm-*` properties.
  Browser tests now run an axe audit of both themes and check layout at four widths.

## 2.0.0 (2026-10-09)

### Added

- Public CSS custom properties (`--bm-*`) for layout limits and padding, region strokes, selection
  and focus styling, tooltip appearance, and view labels. Every variable falls back to the existing
  built-in value, so current output is unchanged until one is overridden. See the README section
  "Styling and Theming".
- The `intensityColor` option, plus the `resolveIntensityColor` and `createIntensityColorScale`
  exports, so applications can supply their own intensity colour scale. `getMuscleColor()` accepts
  an optional resolver as its third argument.
- `MUSCLE_DEFS` (definitions keyed by identifier), `getMuscleDef(id)` (string lookup returning
  `undefined` when unknown), and `isMuscleId(value)` (type guard), plus the `FrontMuscleId`,
  `BackMuscleId`, `MuscleSpec`, and `MuscleEntry` types.
- The `labels` option (`ChartLabels`) and its `regionName`, `region`, `intensity`, `tooltip`,
  `viewLabel`, and `chart` members, so every rendered string — chart name, region names, accessible
  names, tooltips, intensity wording, and view labels — can be localized. Defaults remain English,
  `ariaLabel` still beats `labels.chart`, and `tooltipFormatter` still beats `labels.tooltip`.
- `MUSCLE_METADATA` and `getMuscleMetadata(id)`, plus the `MuscleMetadata` and `MuscleGroup` types:
  canonical side (the subject's own left/right), display group, view, and name for every region, so
  consumers no longer have to parse identifiers. `MUSCLE_GROUPS` is now declared as a readonly
  literal table whose identifiers are checked against the dataset at compile time, and the release
  gate verifies that every region belongs to exactly one group.
- Data-only entry points for consumers that never render the chart:
  `@emmorts/body-muscles/data` (the canonical anatomy exports, ESM and CommonJS with types) and
  `@emmorts/body-muscles/data.json` (the same geometry and intensity scale as one JSON document,
  now carrying a `schemaVersion` field). Both work in Node and in bundlers without browser globals.
- A searchable anatomy catalog on the documentation site, generated from canonical data, with
  group/side/view filters and anterior/posterior previews.
- Runnable vanilla TypeScript and React integration examples in the repository, including React
  server rendering/hydration, callback updates, cleanup, and remounts. Examples are not shipped in
  the npm package.
- Development-only browser regressions, consumer declaration checks, isolated packaged-entry-point
  checks, and CI builds for both examples. The library still has zero runtime dependencies.

### Fixed

- Explicit `labels` updates refresh the chart name, view labels, region names, and visible tooltip
  even when the consumer mutates and reuses the same object, preserving focus.
- `labels.region` receives `undefined` for regions omitted from `bodyState`, consistently with
  tooltip callbacks; rendering defaults no longer fabricate tracked state for accessible names.
- `BodyChart.update()` now applies every option it accepts. It previously refreshed only the
  region colours (and rebuilt on `view`), so changes to `ariaLabel`, `className`,
  `showViewLabel`, `showTooltip`, `tooltipFormatter`, or `enableTransitions` were silently
  ignored until the view changed.
- `update()` ignores `undefined` values, so passing a spread object no longer clobbers options
  that were not meant to change.
- Constructor defaults now apply when optional fields are explicitly `undefined`, including
  `interactive`; explicit `false` options remain respected.
- A visible tooltip now reflects explicit `bodyState` updates, including mutations to a reused
  state mapping, or a new `tooltipFormatter`, without waiting for pointer movement.
- Tooltip content updates recompute positioning from the current anchor, keeping content
  that fits within the chart inside its boundaries.
- Enabling tooltips while a region is focused immediately shows its tooltip and restores
  `aria-describedby`, without requiring the user to leave and re-enter the region.
- The chart no longer marks its interactive SVG `aria-hidden`, and the container no longer uses
  `role="img"`, so muscle regions are reachable by assistive technology instead of being hidden
  focusable content nested inside an image. Regions are exposed as toggle buttons whose
  `aria-pressed` state tracks `selected`, and keyboard focus shows a high-contrast indicator.
- Documentation demo controls remain mounted during state changes, retain keyboard focus when rows
  disappear, and keep large selections scrollable. Theme contrast, landmarks, and prose links were corrected.
- Catalog search no longer reloads the page on Enter; filtering removes stale preview highlights
  and retains the current-row annotation.
- Vanilla examples no longer destroy charts before back/forward-cache restoration. The site's
  standalone HTML example loads a browser-resolvable UMD script, and the runnable example replaces
  genuinely distinct callback functions, retaining the active handler across rebuilds.

### Changed

- **BREAKING:** published declarations require TypeScript 5.0+ because the anatomy declaration
  helper uses const type parameters. Upgrade older consumer compilers; `skipLibCheck` cannot
  suppress syntax errors. JavaScript runtime requirements are unchanged.
- **BREAKING:** intensities are validated as finite integers from 0 to 10. The `BodyChart`
  constructor and `update()` now throw descriptive errors identifying the region and invalid value;
  `createBodyPartState()` identifies the invalid value. Validation runs before submitted options or
  rendering changes are applied; it cannot roll back prior consumer mutations to already-accepted
  objects. Rejected construction mounts nothing. Default and custom-palette colour resolvers still
  round and clamp defensively; application-provided resolvers remain application code.
- **BREAKING:** `MuscleId` is now a union of the region identifiers derived from the dataset, not
  `string`. State keys, callbacks, and helpers are type-checked, so a misspelled literal is a
  compile error instead of a silently ignored region. Identifiers that only exist at runtime must
  be narrowed with `isMuscleId(value)` (or resolved with `getMuscleDef(id)`) before being used as
  state keys; the README's "Typed identifiers" section shows the migration.
- **BREAKING:** `MUSCLE_GROUPS` has literal keys and readonly member arrays in its declarations.
  Consumers needing mutable lists should copy the selected group with `[...MUSCLE_GROUPS[group]]`.
- Keyboard navigation now uses a roving tab index: the chart is a single tab stop and regions are
  reached with the arrow keys (`Home`/`End` jump to the ends), instead of placing every region in
  the tab order.
- Added the `interactive` option (default `true`). When `false` the chart is a static, single
  labelled graphic with no focusable regions, tooltip, or callbacks.
- In-place `update()` calls preserve focus; changing `view` or `interactive` rebuilds the chart
  and therefore drops focus.
- The default tooltip now appends the numeric intensity (`Name - intensity N`) when the region has
  state. Pass `tooltipFormatter` to customize the wording.
- `prefers-reduced-motion: reduce` disables chart and tooltip transitions regardless of
  `enableTransitions`; the preference is re-evaluated when it changes.

### Documentation and verification limits

- `bodyState` and `labels` are replaced as whole objects by `update()`; spreading preserves members
  you are not changing. No patch API or internal selection-state model was added.
- CSS-variable expressions are supported by intensity resolvers; the browser resolves them on each
  SVG region, while the `fill` attribute retains the expression.
- Automated browser and accessibility-tree checks are not a claim of full WCAG conformance.
  Real screen-reader announcements and browse/focus-mode behavior remain unverified.

## 1.1.1 (2026-10-09)

No functional change. This release exists to exercise the release pipeline end to end: the tag
`v1.1.1` is picked up by GitHub Actions, which type-checks, builds and verifies the artifacts,
publishes the package over npm trusted publishing, then opens this GitHub release from this
changelog section.

## 1.1.0 (2026-10-09)

### Features

- Added `ViewSide.BOTH` to render anterior and posterior views side-by-side in a single chart,
  with view labels centred over each half
- Added an instant floating tooltip (`showTooltip`, on by default) with a customisable
  `tooltipFormatter`, positioned near the cursor and clamped to the container
- Muscle hover/focus now uses pointer events with `focus`/`blur` support and
  `aria-describedby` for keyboard and assistive-technology users
- Redrew every muscle region as smoothed bezier paths (`scripts/smooth-raw-paths.ts`)

## 1.0.0 (2026-04-14)

### Features

- Interactive SVG body chart with 70+ individually targetable muscles
- Front and back body views
- Muscle intensity visualization with customizable color mapping
- Muscle group definitions and filtering utilities
- CJS, ESM, and UMD builds
- Zero dependencies
- Framework-agnostic (works with React, Vue, Svelte, or vanilla JS)
