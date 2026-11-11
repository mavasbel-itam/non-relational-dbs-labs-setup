# Labs Setup Maintenance Contract

These rules apply to maintainers and automation working inside this independent submodule.

## Project Boundary

- Treat `labs-setup` as its own `uv` project with its own `pyproject.toml`, `uv.lock`, and `.venv`.
- Run `uv sync` separately here. Do not merge this environment with the parent repository.
- Keep every present-state `README.md`, `LOAD_ME.md`, and `AGENTS.md` current, mutually consistent, and written in English.
- Historical plans and research live in the parent repository. Preserve them as historical records; do not rewrite or delete them when updating current submodule documentation.

## Network Contract

- `NETWORK_MODE` accepts exactly lowercase `local` or `vpn`; its default is `local`. Reject every other value.
- Docker and Compose provide infrastructure in both modes. Docker-internal service names remain unchanged for container-to-container communication.
- Local host-side client endpoints use only ports published on `127.0.0.1`.
- VPN host-side client identities use `<container>.<VPN_CLIENT_ALIAS>.<VPN_DOMAIN>` and published ports bind to `VPN_HOST_IP`.
- Defaults are `VPN_CLIENT_ALIAS=mavasbel`, `VPN_DOMAIN=vpn.itam.mx`, `VPN_HOST_IP=10.15.20.100`, and `VPN_DNS_IP=10.15.20.1`. The alias and domain are editable notebook parameters and must remain injectable through papermill.
- CoreDNS must provide each student's base identity `<student_alias>.<VPN_DOMAIN>` and wildcard service resolution for `<container>.<student_alias>.<VPN_DOMAIN>` to the same WireGuard client IP. A notebook's `VPN_CLIENT_ALIAS` selects the applicable student alias.

## Notebook Contract

- Treat each `py:percent` `.py` source as canonical.
- Force source-to-notebook updates with `uv run jupytext --to ipynb --update <source.py>`. Do not use bidirectional `--sync` for this refresh.
- Keep exactly one papermill `parameters` cell in every notebook.
- Preserve intended papermill types, especially unquoted Boolean values such as `True` and `False`.
- Run every `*_infra.ipynb` to completion and health before its matching `*_lab.ipynb`.
- Hive and Spark require healthy Hadoop infrastructure first.
- Acceptance requires complete execution of every supported infrastructure/lab pair in both Local and VPN modes, including MongoDB config-server infrastructure.

## Spark Contract

- Spark is self-contained and must not resolve Maven packages or download JARs at runtime.
- Keep these Spark 4.1.2 / Scala 2.13 connector JARs tracked and validate their pinned SHA-256 checksums before creating a Spark session:
  - `iceberg-spark-runtime-4.1_2.13-1.12.0.jar`
  - Delta 4.3.1: `delta-spark_2.13`, `delta-storage`, `delta-kernel-api`, `delta-kernel-defaults`, and `delta-kernel-unitycatalog`
- Keep the two GraphFrames 0.12.3 JARs tracked and checksum-validated too (`graphframes-spark4_2.13-0.12.3.jar`, `graphframes-graphx-spark4_2.13-0.12.3.jar`). `spark_infra` verifies all eight checksums before starting the cluster and mounts the GraphFrames JARs on Spark's default classpath (`/opt/spark/jars`) of `spark-jupyter` and every Worker; `spark-jupyter` installs `graphframes-py==0.12.3`. Do not add GraphFrames' `datasketches` dependency: Spark 4.1.2 already ships its exact 6.2.0/3.0.2 runtime pair.
- The Driver is the notebook kernel inside `spark-jupyter`; it uses Docker-network names (`spark-master-internal`, `namenode`, `spark-jupyter`) so executors never connect to the host. Executors run with the shipped Python environment and bundled JAR classpath.

## Notebook Documentation

- Every code cell is preceded by a markdown cell with a numbered `## ` heading and **What / Why / How** bullets, written in English; references are `📄` links to official documentation, each answering HTTP 200 and stating the cited fact. The structural audit enforces the structure and `https://` links and runs from the course repository: `cd .. && uv run python -m scripts.labs_audit`; `LABS_LINKS=1 uv run pytest tests/live/test_labs_notebook_links.py` there also checks every link answers 200.

## AWS Contract

- The AWS lab must never use a real AWS account or create billable resources. It runs only against the local emulator started by `aws/aws_infra`: Moto for S3, DynamoDB, IAM, STS and Lambda, and the Athena gateway (`athena_gateway/`) with its HiveServer2 engine.
- Students work in the `aws-terminal` container (dummy credentials, `AWS_ENDPOINT_URL` / `AWS_ENDPOINT_URL_ATHENA`, no access to the host's `~/.aws`); host-side clients use the generated `aws/mount/client` files. Checks must confirm Moto's account `123456789012`.
- Keep images pinned (`motoserver/moto:5.2.4`, `apache/hive:4.0.1`, the Lambda runtime by digest, the AWS CLI installer by SHA-256 per architecture). The gateway and terminal images install `aws/*.requirements.txt` with `--no-deps`; those pins must equal `uv.lock` (enforced by a unit test).

## Operating System Contract

- Notebooks and labs must behave the same on Windows, macOS and Linux. Notebooks never use IPython `!` lines or `shell=True`: they call `labs_runtime.run_command([...])`. Text I/O states `encoding=` and, on writes, `newline=` (enforced by `labs_audit`); `.gitattributes` keeps text files LF.
- Anything that needs a shell runs inside a Linux container. Commands a student types on their own computer are single-line `docker`, `uv` or `python` commands without shell-specific characters.
- Images without an `arm64` build declare `platform: linux/amd64` (currently `apache/hadoop:3.4.3`).

## Safety

- Never commit generated Compose files, generated state, executed notebooks, credentials, secrets, WireGuard private keys or client configurations, certificates, or student-identifiable data.
- Keep generated outputs and secrets covered by `.gitignore`.
- Do not hand-edit generated Compose files; change the canonical source and regenerate them.
