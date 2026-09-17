# Scout review preview

From the repository root:

```sh
npm --prefix web run preview:scout
```

Open http://127.0.0.1:3106. Optionally pass a different port with `-- 3107`.
Use the checkpoint and snapshot controls to inspect pending, partially reviewed,
and completed decisions. Selecting an item, choosing an estimate, bulk acceptance,
and correcting a decision use the real review components and helpers.

`scout-review-fixture.ts` owns fictional source-linked data shared with tests.
`scout-review-preview.tsx.template` supplies only the local preview controls.
The script copies the current components and styles into a fresh temporary app;
it exports private checkpoint components only in that copy. No production route,
credentials, API adapters, or Assistant is included. A browser policy blocks
requests to external services. Advancing displays a notice instead of running AI.
Reloading resets decisions. Ctrl+C stops the server and removes its temporary app.

These fixtures test presentation and decision handling, not model accuracy.
The preview uses the application's fonts; Next may download fonts on first use.

Run the containment test with `npm --prefix web run test:preview` and fixture
tests with `npm --prefix web test`.
