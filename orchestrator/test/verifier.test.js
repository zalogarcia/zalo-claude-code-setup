"use strict";

/**
 * Tests for the Symphony verifier.
 *
 * Strategy: build temp workdirs and stateDirs on disk and exercise the public
 * `run()` entry point. We set SYMPHONY_VERIFIER_SKIP_QA=1 in every test so the
 * qa layer never spawns a real `claude` process — the qa layer's own logic is
 * exercised at code-review level (tests would need a working claude binary
 * otherwise, which would be slow + non-deterministic).
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const VERIFIER_PATH = require.resolve("../src/symphony/verifier.js");

function freshDirs(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "symphony-verifier-"));
  const workdir = path.join(root, "wd");
  const stateDir = path.join(root, "sd");
  fs.mkdirSync(workdir, { recursive: true });
  fs.mkdirSync(stateDir, { recursive: true });
  t.after(() => {
    try {
      fs.rmSync(root, { recursive: true, force: true });
    } catch (_) {}
  });
  return { workdir, stateDir, root };
}

function withSkipQa(t) {
  const prev = process.env.SYMPHONY_VERIFIER_SKIP_QA;
  process.env.SYMPHONY_VERIFIER_SKIP_QA = "1";
  t.after(() => {
    if (prev === undefined) {
      delete process.env.SYMPHONY_VERIFIER_SKIP_QA;
    } else {
      process.env.SYMPHONY_VERIFIER_SKIP_QA = prev;
    }
  });
}

function freshVerifier() {
  delete require.cache[VERIFIER_PATH];
  return require(VERIFIER_PATH);
}

test("empty workdir → all core layers ran:false, passed:true", async (t) => {
  withSkipQa(t);
  const { workdir, stateDir } = freshDirs(t);
  const verifier = freshVerifier();

  const result = await verifier.run({ stateDir, workdir, filesChanged: [] });

  assert.equal(result.passed, true, "should pass when nothing to verify");
  assert.equal(result.layers.tsc.ran, false, "tsc skipped");
  assert.equal(result.layers.tests.ran, false, "tests skipped");
  assert.equal(result.layers.lint.ran, false, "lint skipped");
  // qa skipped via SYMPHONY_VERIFIER_SKIP_QA — counts as ran:false → passes.
  assert.equal(result.layers.qa.ran, false, "qa skipped via env hook");
  assert.equal(result.layers.backend.ran, false, "backend skipped");
  assert.equal(result.layers.visual.ran, false, "visual skipped");
});

test("workdir with bad TypeScript → tsc fails, overall passed:false", async (t) => {
  withSkipQa(t);
  const { workdir, stateDir } = freshDirs(t);

  // Minimal tsconfig that compiles whatever .ts files are present.
  fs.writeFileSync(
    path.join(workdir, "tsconfig.json"),
    JSON.stringify(
      {
        compilerOptions: {
          strict: true,
          noEmit: true,
          target: "es2020",
          module: "commonjs",
        },
        include: ["*.ts"],
      },
      null,
      2,
    ),
  );
  // Type error: assigning a string to a number.
  fs.writeFileSync(
    path.join(workdir, "broken.ts"),
    'const n: number = "definitely a string";\n',
  );

  const verifier = freshVerifier();

  const result = await verifier.run({ stateDir, workdir, filesChanged: [] });

  // The tsc layer should have run. Whether it actually compiles depends on
  // whether `npx --no-install tsc` finds a tsc binary. If tsc is absent the
  // exit code will be non-zero (npx prints "could not determine executable")
  // — which still satisfies "ran && !passed".
  assert.equal(result.layers.tsc.ran, true, "tsc layer ran");
  assert.equal(result.layers.tsc.passed, false, "tsc layer failed");
  assert.equal(result.passed, false, "overall failed because tsc failed");

  // qa/backend/visual must skip with the 'previous layers failed' reason.
  assert.equal(result.layers.qa.ran, false);
  assert.equal(result.layers.backend.ran, false);
  assert.equal(result.layers.backend.reason, "previous layers failed");
  assert.equal(result.layers.visual.ran, false);
  assert.equal(result.layers.visual.reason, "previous layers failed");
});

test("migration in filesChanged but no supabase/config.toml → backend ran:false", async (t) => {
  withSkipQa(t);
  const { workdir, stateDir } = freshDirs(t);
  const verifier = freshVerifier();

  const result = await verifier.run({
    stateDir,
    workdir,
    filesChanged: ["supabase/migrations/0001_init.sql"],
  });

  assert.equal(result.passed, true);
  assert.equal(
    result.layers.backend.ran,
    false,
    "backend skipped without supabase/config.toml",
  );
});

test("frontend file changed but no baselines → visual ran:false", async (t) => {
  withSkipQa(t);
  const { workdir, stateDir } = freshDirs(t);
  const verifier = freshVerifier();

  const result = await verifier.run({
    stateDir,
    workdir,
    filesChanged: ["src/components/Button.tsx", "src/styles/main.css"],
  });

  assert.equal(result.passed, true);
  assert.equal(
    result.layers.visual.ran,
    false,
    "visual skipped — no baselines on disk",
  );
});

test("baselines exist but pixelmatch resolution failure → visual ran:false with reason", async (t) => {
  withSkipQa(t);
  const { workdir, stateDir } = freshDirs(t);

  // Create a baseline so the path-existence check passes; whether pixelmatch
  // is installed is environment-dependent. The verifier's contract is:
  //   - if pixelmatch + pngjs both resolve and there is a screenshot pair → run + pass/fail
  //   - if either is missing → ran:false with reason 'pixelmatch or pngjs not installed'
  //   - if no screenshot pair → ran:false with reason 'no baseline or screenshot pairs'
  // We assert the verifier never throws and the visual layer reports a
  // consistent shape regardless.
  fs.mkdirSync(path.join(workdir, ".symphony", "baselines"), {
    recursive: true,
  });
  fs.writeFileSync(
    path.join(workdir, ".symphony", "baselines", "home.png"),
    Buffer.from([0x89, 0x50, 0x4e, 0x47]), // PNG magic — not a real PNG, but the verifier never reads it without a screenshot pair
  );

  const verifier = freshVerifier();

  const result = await verifier.run({
    stateDir,
    workdir,
    filesChanged: ["app/page.tsx"],
  });

  // Visual must be either ran:false (pixelmatch missing OR no screenshot pair)
  // or ran:true with a passed flag if pixelmatch IS installed. Either is fine
  // for this test — we're proving the verifier handles both gracefully.
  assert.ok(result.layers.visual, "visual layer reported");
  if (result.layers.visual.ran === false) {
    assert.ok(
      typeof result.layers.visual.reason === "string" &&
        result.layers.visual.reason.length > 0,
      "ran:false visual layer must include a reason",
    );
  } else {
    // If pixelmatch IS resolvable, we have no real screenshot pair on disk,
    // so the layer should have skipped via 'no baseline or screenshot pairs'.
    // (This branch shouldn't be reachable in the typical test env.)
    assert.equal(result.layers.visual.passed, true);
  }
  assert.equal(result.passed, true);
});

test("verification.json written atomically", async (t) => {
  withSkipQa(t);
  const { workdir, stateDir } = freshDirs(t);
  const verifier = freshVerifier();

  const result = await verifier.run({
    stateDir,
    workdir,
    filesChanged: [],
  });

  const verPath = path.join(stateDir, "verification.json");
  assert.equal(fs.existsSync(verPath), true, "verification.json present");
  const tmpPath = verPath + ".tmp";
  assert.equal(fs.existsSync(tmpPath), false, "tmp file cleaned up by rename");

  const persisted = JSON.parse(fs.readFileSync(verPath, "utf8"));
  assert.deepEqual(persisted, result, "persisted JSON matches return value");
  assert.equal(persisted.passed, true);
  assert.ok(persisted.layers && typeof persisted.layers === "object");
  for (const name of ["tsc", "tests", "lint", "qa", "backend", "visual"]) {
    assert.ok(
      Object.prototype.hasOwnProperty.call(persisted.layers, name),
      "layer present: " + name,
    );
  }
});

test("npm test placeholder script is treated as no-test", async (t) => {
  withSkipQa(t);
  const { workdir, stateDir } = freshDirs(t);
  // npm-init-style placeholder: writing this should NOT cause the tests layer
  // to actually run npm test (which would fail with exit 1).
  fs.writeFileSync(
    path.join(workdir, "package.json"),
    JSON.stringify(
      {
        name: "noop",
        version: "0.0.0",
        scripts: {
          test: 'echo "Error: no test specified" && exit 1',
        },
      },
      null,
      2,
    ),
  );
  const verifier = freshVerifier();

  const result = await verifier.run({ stateDir, workdir, filesChanged: [] });

  assert.equal(
    result.layers.tests.ran,
    false,
    "placeholder test script skipped",
  );
  assert.equal(result.passed, true);
});

test("filesChanged validation: non-array becomes empty array (no throw)", async (t) => {
  withSkipQa(t);
  const { workdir, stateDir } = freshDirs(t);
  const verifier = freshVerifier();

  // filesChanged = undefined should not throw.
  const result = await verifier.run({ stateDir, workdir });
  assert.equal(result.passed, true);
});

test("missing stateDir or workdir → throws TypeError", async (t) => {
  withSkipQa(t);
  const verifier = freshVerifier();
  await assert.rejects(
    () => verifier.run({ stateDir: "", workdir: "/tmp" }),
    /stateDir/,
  );
  await assert.rejects(
    () => verifier.run({ stateDir: "/tmp", workdir: "" }),
    /workdir/,
  );
});
