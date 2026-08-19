# Framework and generated-project verification

This file is the mandatory regression contract for every framework or template
change. `AGENTS.md` points new development sessions here.

## Required lifecycle semantics

- A finite Spider finishes only after its `start()` producer has completed and
  every request owned by that Engine, including callbacks and WebSocket
  listeners, has reached its terminal boundary.
- A Redis, RabbitMQ, or Kafka Spider with `start_request_limit = None` is a
  continuous consumer. An empty broker read never means completion. It remains
  subscribed until crawler shutdown or another explicit stop event.
- A positive `start_request_limit` completes the standard queue ingress
  producer after that many accepted start requests. This is a real input event,
  not an empty-queue heuristic.
- `response.stop_listening()` and crawler shutdown are real WebSocket events.
  No queue sentinel, elapsed delay, or receive timeout may impersonate closure.
- Safety timeouts in tests may fail a hung run, but passing requires lifecycle
  evidence; reaching a timeout or sleeping for a chosen duration is never PASS
  evidence.
- In a mixed `run_all_spiders` run, finite Engines may finish while continuous
  sibling Engines keep the process alive. Each spider retains its own scheduler
  family unless the user explicitly configures a global `settings.SCHEDULER`.

## Required test layers

Run all of the following after every change:

1. Full framework pytest on Windows and WSL Ubuntu.
2. `scrapy-cffi test single` on Windows and WSL Ubuntu for Memory, Redis,
   RabbitMQ, and Kafka. This command builds disposable projects through the
   same `startproject` plus `demo` template path users receive, imports them,
   starts their real HTTP/WebSocket servers and brokers, and runs `runner.py`.
3. Finite verification: the generated project must finish `engine_task`
   naturally. The verifier may call `crawler.shutdown()` only in `finally` for
   cleanup; forced shutdown cannot turn a timeout into success.
4. Continuous verification: queue-backed generated Spiders run with
   `start_request_limit = None`. After their seeded work and WebSocket flow are
   complete, `runner.py` must still be alive. The verifier then sends an
   explicit console signal and requires graceful shutdown evidence.
5. Direct CLI generation smoke for `scrapy-cffi demo`, `demo -r`, `demo -m`,
   `demo -k`, and `demo -tls` whenever command routing or templates change.
   Also generate a plain `scrapy-cffi startproject` project and verify imports.
6. Run the engineering convention checker on new and materially changed Python
   files, then run `git diff --check`.

Use separate, serial Windows and WSL runs because both environments can share
the same Docker daemon and project names. Parallel matrices can interfere with
each other's containers and are invalid evidence.

## Release commands

Install the framework and its explicit verification dependencies before running
either platform gate. Do not rely on globally installed demo-server packages:

```bash
python -m pip install -e ".[kafka,rabbitmq,mysql,postgres,mongodb,verification]"
```

Windows PowerShell:

```powershell
pytest -q
scrapy-cffi test single --log-dir artifacts\release-verification\windows-final
```

WSL Ubuntu, using the project verification environment:

```bash
python -m pytest -q -p no:cacheprovider
scrapy-cffi test single \
  --log-dir artifacts/release-verification/wsl-ubuntu-final
```

Do not use `--no-interrupt` for the final gate: normal phases validate finite
natural exit, while Redis/RabbitMQ/Kafka interrupt phases validate real
continuous listening and explicit shutdown. Memory mode is finite and must not
be kept alive by a test-only hold-open flag. `--quick` is useful during
implementation but is not release evidence.

## Publish tag

Only tag a commit after its branch CI and both platform gates pass. The release
workflow requires the exact `v<project-version>` form:

```bash
git tag v0.4.2
git push origin v0.4.2
```

Tags such as `release-v.0.4.2` do not match the workflow and must not be used.
