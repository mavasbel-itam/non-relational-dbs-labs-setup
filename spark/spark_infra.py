# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: .venv
#     language: python
#     name: non-relational-dbs-labs
# ---

# %% [markdown]
# # Spark — infrastructure (Standalone cluster + JupyterLab on the Hadoop network)
#
# ## 1. Parameters
#
# - **What:** default values for `NETWORK_MODE`, the VPN identity and `START_FROM_SCRATCH`.
# - **Why:** the same notebook serves Local mode (ports on `127.0.0.1`) and VPN mode (`<container>.<alias>.<domain>`).
# - **How:** the cell is tagged `parameters`; papermill inserts an `injected-parameters` cell right after it with the `-p` values.
# - 📄 [papermill — Parameterize](https://papermill.readthedocs.io/en/latest/usage-parameterize.html)

# %% tags=["parameters"]
# Local mode is the portable default; VPN mode publishes services on this host.
NETWORK_MODE = "local"
VPN_HOST_IP = "10.15.20.100"
VPN_DNS_IP = "10.15.20.1"
VPN_DOMAIN = "vpn.itam.mx"
VPN_CLIENT_ALIAS = "mavasbel"
START_FROM_SCRATCH = False

# %% [markdown]
# ## 2. Validate the parameters
#
# - **What:** lower-cases `NETWORK_MODE` and `VPN_CLIENT_ALIAS` and builds `VPN_CLIENT_DOMAIN = <alias>.<domain>`.
# - **Why:** a wrong value must stop the notebook here, before any container changes.
# - **How:** rejects any mode other than `local`/`vpn` and, in VPN mode, a host IP outside `10.15.20.*`, and an alias that is not lower-case letters, digits and inner hyphens.

# %%
NETWORK_MODE = NETWORK_MODE.strip().lower()
VPN_CLIENT_ALIAS = VPN_CLIENT_ALIAS.strip().lower()
if NETWORK_MODE not in {"local", "vpn"}:
    raise ValueError("NETWORK_MODE must be 'local' or 'vpn'")
if NETWORK_MODE == "vpn" and not VPN_HOST_IP.startswith("10.15.20."):
    raise ValueError("VPN_HOST_IP must be in the 10.15.20.* subnet")
if (
    not VPN_CLIENT_ALIAS
    or VPN_CLIENT_ALIAS.startswith("-")
    or VPN_CLIENT_ALIAS.endswith("-")
    or not VPN_CLIENT_ALIAS.isascii()
    or not VPN_CLIENT_ALIAS.replace("-", "").isalnum()
):
    raise ValueError(
        "VPN_CLIENT_ALIAS must contain only lowercase letters, digits, and internal hyphens"
    )
VPN_CLIENT_DOMAIN = f"{VPN_CLIENT_ALIAS}.{VPN_DOMAIN}"

# %% [markdown]
# ## 3. Find the module folder
#
# - **What:** locates the labs-setup root, changes into `spark/` and imports `run_command`.
# - **Why:** relative paths (Compose file, `mount/`) then resolve the same way whether papermill or JupyterLab started the kernel; `run_command` passes an argument list to the program without a shell, so it behaves the same on Windows, macOS and Linux.
# - **How:** walks up from the current folder to the first one holding `pyproject.toml`, `cassandra/` and `mongodb/`.

# %%
# Resolve module assets from the labs-setup root.
import os
from pathlib import Path

_start = Path.cwd().resolve()
LABS_ROOT = next(
    (
        candidate
        for candidate in (_start, *_start.parents)
        if (candidate / "pyproject.toml").is_file()
        and (candidate / "cassandra").is_dir()
        and (candidate / "mongodb").is_dir()
    ),
    None,
)
if LABS_ROOT is None:
    raise RuntimeError(
        "Could not find the labs-setup root from the current directory"
    )
MODULE_DIR = LABS_ROOT / "spark"
import sys

if str(LABS_ROOT) not in sys.path:
    sys.path.insert(0, str(LABS_ROOT))
from labs_runtime import run_command

os.chdir(MODULE_DIR)
print(f"Working directory: {MODULE_DIR}")

# %% [markdown]
# ## 4. Cluster names and ports
#
# - **What:** the master (`spark-master-internal`, port `6077`, UI `6080`), three workers (UIs `6081-6083`) and `spark-jupyter` (JupyterLab `6888`, Spark UI `4040`); images based on `apache/spark:4.1.2-scala2.13-java17-python3-ubuntu`.
# - **Why:** the notebooks run inside `spark-jupyter`, which is the Spark Driver; the names are the same in Local and VPN mode inside the Docker network, while browsers reach the UIs at `127.0.0.1` or `<container>.<alias>.<domain>`.
# - **How:** the token of JupyterLab is empty, which is acceptable only because it listens on `127.0.0.1` (Local) or the VPN address.
# - 📄 [Spark 4.1.2 — Standalone mode](https://spark.apache.org/docs/4.1.2/spark-standalone.html) · [Spark — Web UI (port 4040)](https://spark.apache.org/docs/4.1.2/monitoring.html)

# %%
SPARK_START_FROM_SCRATCH = START_FROM_SCRATCH
DOCKER_INTERNAL_HOST = "host.docker.internal"
SPARK_LOCAL_HDFS_HOST = "namenode.lvh.me"
DOCKER_DNS = [VPN_DNS_IP] if NETWORK_MODE == "vpn" else []
HOST_BIND_IP = VPN_HOST_IP if NETWORK_MODE == "vpn" else "127.0.0.1"

SPARK_DOCKER_BASE = "spark:4.1.2-scala2.13-java17-python3-ubuntu"
SPARK_JUPYTER_LAB_DOCKER_TAG = "spark-jupyter:4.1.2-scala2.13-java17-python3-ubuntu"
SPARK_JOB_VENV_DOCKER_TAG = "spark-job-venv:4.1.2-scala2.13-java17-python3-ubuntu"
SPARK_JOB_VENV_BUILD_DIR = "/opt/spark/venv-build"
SPARK_EXECUTOR_ENV_DIR = "/opt/spark/executor-env"

SPARK_MASTER_NAME = "spark-master"
SPARK_MASTER_HOSTNAME = "spark-master-internal"
SPARK_MASTER_COMPOSE_HOST = (
    SPARK_MASTER_HOSTNAME
    if NETWORK_MODE == "local"
    else f"{SPARK_MASTER_NAME}.{VPN_CLIENT_DOMAIN}"
)
SPARK_MASTER_CLIENT_HOST = (
    "127.0.0.1"
    if NETWORK_MODE == "local"
    else f"{SPARK_MASTER_NAME}.{VPN_CLIENT_DOMAIN}"
)
SPARK_MASTER_WUBUI_PORT = 6080
SPARK_MASTER_PORT = 6077

SPARK_TOTAL_WORKERS = 3
SPARK_WORKER_NAMES = [f"spark-worker-{i+1}" for i in range(SPARK_TOTAL_WORKERS)]
SPARK_WORKER_HOSTNAMES = SPARK_WORKER_NAMES
SPARK_WORKER_COMPOSE_HOSTS = [
    name if NETWORK_MODE == "local" else f"{name}.{VPN_CLIENT_DOMAIN}"
    for name in SPARK_WORKER_NAMES
]
SPARK_WORKER_IPS = [
    f"{name}.{VPN_CLIENT_DOMAIN}" if NETWORK_MODE == "vpn" else "127.0.0.1"
    for name in SPARK_WORKER_NAMES
]
SPARK_WORKER_WEBUI_PORTS = [6080 + (i + 1) for i in range(SPARK_TOTAL_WORKERS)]

SPARK_WORKDIR = "/opt/spark/work-dir"
# Shown in JupyterLab's file browser as labs-setup/ (read-only).
SPARK_LABS_SETUP_DIR = f"{SPARK_WORKDIR}/labs-setup"

JUPYTER_LAB_NAME = "spark-jupyter"
JUPYTER_LAB_HOSTNAME = JUPYTER_LAB_NAME
JUPYTER_LAB_COMPOSE_HOST = (
    JUPYTER_LAB_HOSTNAME
    if NETWORK_MODE == "local"
    else f"{JUPYTER_LAB_NAME}.{VPN_CLIENT_DOMAIN}"
)
JUPYTER_LAB_CLIENT_HOST = (
    "127.0.0.1"
    if NETWORK_MODE == "local"
    else f"{JUPYTER_LAB_NAME}.{VPN_CLIENT_DOMAIN}"
)
JUPYTER_LAB_PORT = 6888
JUPYTER_LAB_MONITOR_PORT = 4040
JUPYTER_LAB_TOKEN = ""

SPARK_SHARED_WORKSPACE = "shared-workspace"
SPARK_SHARED_WORKSPACE_DIR = f"/opt/spark/{SPARK_SHARED_WORKSPACE}"

# %% [markdown]
# ## 5. Host folder
#
# - **What:** creates the module folder; `mount/` will hold the master's, workers' and JupyterLab's files.
# - **Why:** work files and the packed Python environment live on the host.
# - **How:** path built from `MODULE_DIR`.
# - 📄 [Docker — Bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)

# %%
import os
from pathlib import Path

LOCALHOST_WORKDIR = str(MODULE_DIR.resolve())
DOCKER_MOUNTDIR = os.path.join(LOCALHOST_WORKDIR, "mount")

path = Path(LOCALHOST_WORKDIR)
path.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## 6. Check the bundled JARs
#
# - **What:** compares the SHA-256 of the eight JARs in `jars/` with pinned values: Iceberg 1.12.0, five Delta 4.3.1 JARs and two GraphFrames 0.12.3 JARs.
# - **Why:** Spark never downloads packages at run time; a missing or altered JAR stops the build here instead of failing later in an Executor.
# - **How:** `hashlib.sha256` over each file. Spark 4.1.2 already ships Hadoop, Parquet, Jackson, ANTLR and Scala; only connectors it lacks are bundled. GraphFrames' `datasketches-java` dependency is also already in Spark, so it is not added twice.

# %%
import hashlib

SPARK_COURSE_JARS = {
    "iceberg-spark-runtime-4.1_2.13-1.12.0.jar": "3123c3798af642dd537230923548e013ef41cc28b6626e5225808cf5670a0f82",
    "delta-spark_2.13-4.3.1.jar": "ebf35a4383f0a653c3ee3c7882c0edcac2f846be31ac61af4b96ccfaaf36c171",
    "delta-storage-4.3.1.jar": "577c12c7e371be4c041714fb48e88ad86e3c3512beea2bdaffbe7a4debf79718",
    "delta-kernel-api-4.3.1.jar": "b081b818d6f5686c7d6406588af72c9f8baf6765a41ada8197364aef90a260e8",
    "delta-kernel-defaults-4.3.1.jar": "27471cca7dd7a36289af2c8d52d2babb37e9e5a13cdaaea76730120f4c72e62f",
    "delta-kernel-unitycatalog-4.3.1.jar": "a288342b7e53da34a608a1a227c8109aa4681fcb582da499ed19347f2193362b",
}
# GraphFrames 0.12.3 is built for this exact Spark 4.1.2 / Scala 2.13 line. Its
# datasketches-java 6.2.0 dependency is already shipped by Spark 4.1.2, so adding
# a second copy would only risk classpath shadowing.
SPARK_GRAPHFRAMES_JARS = {
    "graphframes-spark4_2.13-0.12.3.jar": "a78958f7ea3ac89ed1ea9dbbd1546f403d94151e969bb0de96e33697a5f49f50",
    "graphframes-graphx-spark4_2.13-0.12.3.jar": "385ea9934bdeedff9cd4591df66ada45ce739148f15fe947a032886997626675",
}
for jar_name, expected_sha256 in {**SPARK_COURSE_JARS, **SPARK_GRAPHFRAMES_JARS}.items():
    jar_path = Path(LOCALHOST_WORKDIR) / "jars" / jar_name
    if not jar_path.is_file():
        raise FileNotFoundError(f"Missing tracked JAR: {jar_path}")
    actual_sha256 = hashlib.sha256(jar_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(f"Checksum mismatch for {jar_name}: {actual_sha256} != {expected_sha256}")
    print(f"OK {jar_name}")

# %% [markdown]
# ## 7. Stop the previous cluster
#
# - **What:** with `START_FROM_SCRATCH=True`, removes the containers, network attachments and volumes.
# - **Why:** a fresh build must not reuse old state; with `False` the running cluster is kept.
# - **How:** `docker compose -f spark-cluster.docker-compose.yml down -v` (`check=False`).
# - 📄 [docker compose down](https://docs.docker.com/reference/cli/docker/compose/down/)

# %%
import subprocess

if SPARK_START_FROM_SCRATCH:
    subprocess.run(
        ["docker", "compose", "-f", "spark-cluster.docker-compose.yml", "down", "-v"],
        check=False,
    )
else:
    print("Preserving existing containers and volumes")


# %% [markdown]
# ## 8. Delete the old state
#
# - **What:** with `START_FROM_SCRATCH=True`, empties the master's, workers' and shared folders under `mount/`.
# - **Why:** files written by the containers belong to root and the host user cannot always delete them.
# - **How:** `rm -rf` runs as root inside a throwaway `busybox:1.36` container that sees each folder as `/target`.
# - 📄 [docker container run](https://docs.docker.com/reference/cli/docker/container/run/)

# %%
def clear_bind_directory(path):
    target = Path(path).resolve()
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "docker", "run", "--rm", "--mount",
            f"type=bind,source={target},target=/target",
            "busybox:1.36", "sh", "-c",
            "find /target -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +",
        ],
        check=True,
    )

if SPARK_START_FROM_SCRATCH :
    # shutil.rmtree(os.path.join(DOCKER_MOUNTDIR, SPARK_SHARED_WORKSPACE, "spark-warehouse"), ignore_errors=True)
    # shutil.rmtree(
    #     os.path.join(DOCKER_MOUNTDIR, SPARK_SHARED_WORKSPACE, "iceberg-warehouse"), ignore_errors=True
    # )
    clear_bind_directory(os.path.join(DOCKER_MOUNTDIR, SPARK_MASTER_NAME))
    for spark_worker_name in SPARK_WORKER_NAMES:
        clear_bind_directory(os.path.join(DOCKER_MOUNTDIR, spark_worker_name))
    clear_bind_directory(os.path.join(DOCKER_MOUNTDIR, SPARK_SHARED_WORKSPACE))
    
    Path(os.path.join(DOCKER_MOUNTDIR, JUPYTER_LAB_NAME)).mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## 9. spark-jupyter Dockerfile
#
# - **What:** writes `dockerfile.spark-jupyter`: the Spark image plus JupyterLab, papermill, `graphframes-py` and the lab's libraries at exact versions.
# - **Why:** the Driver and the Executors must use the same library versions, so the shared ones (`pandas`, `pyarrow`, `numpy`, `faker`) are pinned once and reused for the workers' environment.
# - **How:** `pip install pyspark==4.1.2 jupyterlab==4.6.4 papermill==2.7.0 graphframes-py==0.12.3 ...`.
# - 📄 [graphframes-py 0.12.3](https://pypi.org/project/graphframes-py/0.12.3/)

# %%
import os
from IPython.display import Markdown, display

# Exact versions: the lab notebooks run inside this image (it is the Spark
# Driver), and papermill executes spark_lab.ipynb here for acceptance runs.
# The libraries the lab's code uses on both sides (Driver and Executors) are pinned
# once here, so spark-jupyter and spark-job-venv install the same versions; the
# parity check after both builds stops the run if any shared package still differs.
SPARK_SHARED_PYTHON_PACKAGES = "pandas==2.3.3 pyarrow==25.0.1 numpy==2.2.6 faker==40.36.0"
dockerfile_spark_jupyter_python_packages = (
    "pyspark==4.1.2 jupyterlab==4.6.4 papermill==2.7.0 graphframes-py==0.12.3 "
    + SPARK_SHARED_PYTHON_PACKAGES
)
# Only the Workers need these (packing the env, and the generators' extra providers).
spark_job_venv_python_packages = (
    "venv-pack==0.2.0 faker-commerce==1.0.4 mimesis==22.2.0 " + SPARK_SHARED_PYTHON_PACKAGES
)

dockerfile_spark_jupyter_name = "dockerfile.spark-jupyter"

# language=dockerfile
dockerfile_spark_jupyter_contents = f""" 

# Use the official Spark image as the base
FROM apache/{SPARK_DOCKER_BASE}

# Switch to root to install software
USER root

# Set the working directory
WORKDIR {SPARK_WORKDIR}

# Expose the Jupyter port
EXPOSE 8888

# Install Python dependencies
RUN apt-get update && apt-get install -y python3-venv
RUN python3 -m pip install --no-cache-dir {dockerfile_spark_jupyter_python_packages}

# Set the default command to launch Jupyter Lab
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=$$JUPYTER_LAB_TOKEN"]
"""

with open(
    os.path.join(LOCALHOST_WORKDIR, dockerfile_spark_jupyter_name), "w",
    encoding="utf-8", newline="\n",
) as spark_compose_yaml_file:
    spark_compose_yaml_file.write(dockerfile_spark_jupyter_contents.strip())

print(
    f"Successfully created: '{os.path.relpath(os.path.join(LOCALHOST_WORKDIR,dockerfile_spark_jupyter_name))}'"
)
display(Markdown(f"```dockerfile\n{dockerfile_spark_jupyter_contents}\n```"))

# %% [markdown]
# ## 10. Build spark-jupyter
#
# - **What:** builds the image tagged `spark-jupyter:4.1.2-scala2.13-java17-python3-ubuntu`.
# - **Why:** it is the base of the next image and the container where students run the notebooks.
# - **How:** `docker build -t ... -f dockerfile.spark-jupyter .`.
# - 📄 [docker buildx build](https://docs.docker.com/reference/cli/docker/buildx/build/)

# %%
run_command(["docker", "build", "-t", f"{SPARK_JUPYTER_LAB_DOCKER_TAG}", "-f", "dockerfile.spark-jupyter", "."], check=False)

# %% [markdown]
# ## 11. spark-job-venv Dockerfile
#
# - **What:** writes `dockerfile.spark-job-venv`: a virtual environment with the Executors' libraries, packed with `venv-pack`.
# - **Why:** the workers run the plain Spark image, which lacks the lab's Python libraries; they get them from this archive instead of installing anything at run time.
# - **How:** `python3 -m venv --copies` (copies the interpreter so the environment works once unpacked elsewhere), `pip install`, then `venv-pack -o spark_job_env.tar.gz`.
# - 📄 [PySpark — Python package management (venv-pack)](https://spark.apache.org/docs/4.1.2/api/python/tutorial/python_packaging.html) · [venv-pack](https://jcristharif.com/venv-pack/)

# %%
import os
from IPython.display import Markdown, display

dockerfile_spark_job_venv_name = "dockerfile.spark-job-venv"
dockerfile_spark_job_venv_contents = f"""
# Use the previously generated spark-jupyter image as the base
FROM {SPARK_JUPYTER_LAB_DOCKER_TAG}

# Create virtual env for spark jobs
RUN mkdir -p {SPARK_JOB_VENV_BUILD_DIR} && \\
        cd {SPARK_JOB_VENV_BUILD_DIR} && \\
        python3 -m venv --copies spark_job_env && \\
        {SPARK_JOB_VENV_BUILD_DIR}/spark_job_env/bin/pip install --no-cache-dir {spark_job_venv_python_packages} && \\
        {SPARK_JOB_VENV_BUILD_DIR}/spark_job_env/bin/venv-pack -p spark_job_env -o spark_job_env.tar.gz
"""

with open(os.path.join(LOCALHOST_WORKDIR, dockerfile_spark_job_venv_name), "w", encoding="utf-8", newline="\n") as spark_compose_yaml_file:
    spark_compose_yaml_file.write(dockerfile_spark_job_venv_contents.strip())

print(f"Successfully created: '{os.path.relpath(os.path.join(LOCALHOST_WORKDIR,dockerfile_spark_jupyter_name))}'")
display(Markdown(f"```dockerfile\n{dockerfile_spark_job_venv_contents}\n```"))

# %% [markdown]
# ## 12. Build and extract the environment
#
# - **What:** builds `spark-job-venv`, copies `spark_job_env.tar.gz` into `mount/shared-workspace/` and removes the temporary container.
# - **Why:** every worker unpacks that archive when it starts.
# - **How:** `docker build`, `docker create`, `docker cp`, `docker rm`.
# - 📄 [docker buildx build](https://docs.docker.com/reference/cli/docker/buildx/build/) · [docker container create](https://docs.docker.com/reference/cli/docker/container/create/) · [docker container cp](https://docs.docker.com/reference/cli/docker/container/cp/)

# %%
from pathlib import Path
path = Path(DOCKER_MOUNTDIR)
path.mkdir(parents=True, exist_ok=True)

run_command(["docker", "build", "-t", f"{SPARK_JOB_VENV_DOCKER_TAG}", "-f", "dockerfile.spark-job-venv", "."], check=False)
run_command(["docker", "create", "--name", "spark-job-venv", f"{SPARK_JOB_VENV_DOCKER_TAG}"], check=False)
run_command(["docker", "cp", f"spark-job-venv:{SPARK_JOB_VENV_BUILD_DIR}/spark_job_env.tar.gz", f"{DOCKER_MOUNTDIR}/{SPARK_SHARED_WORKSPACE}/spark_job_env.tar.gz"], check=False)
run_command(["docker", "rm", "spark-job-venv"], check=False)

# %% [markdown]
# ## 13. Write the Compose file
#
# - **What:** generates `spark-cluster.docker-compose.yml` with the master, `spark-jupyter` and three workers on the existing `hadoop-network`.
# - **Why:** Spark reads and writes HDFS, so it joins Hadoop's network and reaches `namenode` by name.
# - **How:** each worker unpacks the environment into `/opt/spark/executor-env` before starting, with `SPARK_WORKER_CORES=2` and `SPARK_WORKER_MEMORY=2048M`; the JARs are mounted read-only at `/opt/spark/course-jars`, and the GraphFrames JARs also in `/opt/spark/jars` (Spark's default classpath) of the Driver and the workers; `labs-setup` is mounted read-only in JupyterLab; JupyterLab runs with an empty token and XSRF checks off so the validation tools can drive it.
# - 📄 [Spark 4.1.2 — Standalone mode](https://spark.apache.org/docs/4.1.2/spark-standalone.html) · [Jupyter Server — config options](https://jupyter-server.readthedocs.io/en/latest/other/full-config.html) · [Compose file — services](https://docs.docker.com/reference/compose-file/services/)

# %%
import os
import yaml
from IPython.display import Markdown, display

SPARK_VSCODE_SERVER_DIR = os.path.join(LOCALHOST_WORKDIR, "vscode_server")
SPARK_MOUNT_JARS = [
    f"{os.path.join(LOCALHOST_WORKDIR, 'jars')}:/opt/spark/course-jars:ro"
]
# GraphFrames joins Spark's default classpath (/opt/spark/jars) in the Driver and
# the Executors, so every session can use it without listing it or downloading it.
SPARK_MOUNT_GRAPHFRAMES_JARS = [
    f"{os.path.join(LOCALHOST_WORKDIR, 'jars', jar_name)}:/opt/spark/jars/{jar_name}:ro"
    for jar_name in SPARK_GRAPHFRAMES_JARS
]

spark_compose_dict = {
    "name": "spark-cluster",
    "networks": {
        "spark-cluster": {"external": True, "name": "hadoop-network"},
    },
    "services": {
        SPARK_MASTER_NAME: {
            "image": f"apache/{SPARK_DOCKER_BASE}",
            "container_name": SPARK_MASTER_NAME,
            "user": "root",
            "command": f'bash -c "/opt/spark/bin/spark-class org.apache.spark.deploy.$$SPARK_MODE.$${{SPARK_MODE^}} --host {SPARK_MASTER_HOSTNAME} --port $$SPARK_MASTER_PORT --webui-port $$SPARK_MASTER_WEBUI_PORT"',
            "environment": [
                "PYSPARK_PYTHON=python3",
                "SPARK_MODE=master",
                f"SPARK_MASTER_PORT={SPARK_MASTER_PORT}",
                f"SPARK_MASTER_WEBUI_PORT={SPARK_MASTER_WUBUI_PORT}",
                "SPARK_DAEMON_MEMORY=1G",
            ],
            "volumes": [
                f"{os.path.join(DOCKER_MOUNTDIR,SPARK_SHARED_WORKSPACE)}:{SPARK_SHARED_WORKSPACE_DIR}",
                f"{os.path.join(DOCKER_MOUNTDIR,SPARK_MASTER_NAME)}:{SPARK_WORKDIR}"
            ]
            + SPARK_MOUNT_JARS,
            "networks": {
                "spark-cluster": {"aliases": [SPARK_MASTER_HOSTNAME]},
            },
            "hostname": SPARK_MASTER_COMPOSE_HOST,
            "ports": [
                f"{HOST_BIND_IP}:{SPARK_MASTER_WUBUI_PORT}:{SPARK_MASTER_WUBUI_PORT}",
                f"{HOST_BIND_IP}:{SPARK_MASTER_PORT}:{SPARK_MASTER_PORT}",
            ],
            "extra_hosts": [
                f"{DOCKER_INTERNAL_HOST}:host-gateway",
            ],
            "dns": DOCKER_DNS,
            "deploy": {"resources": {"limits": {"cpus": "2.0", "memory": "1G"}}},
            "healthcheck": {
                "test": [
                    "CMD",
                    "curl",
                    "-f",
                    f"http://{SPARK_MASTER_HOSTNAME}:{SPARK_MASTER_WUBUI_PORT}",
                ],
                "interval": "10s",
                "timeout": "10s",
                "retries": 10,
                "start_period": "10s",
            },
        },
        "spark-jupyter": {
            "image": SPARK_JUPYTER_LAB_DOCKER_TAG,
            "container_name": "spark-jupyter",
            "user": "root",
            "command": [
                "bash",
                "-c",
                " ".join(
                    [
                        "jupyter lab",
                        "--ip=0.0.0.0",
                        f"--port={JUPYTER_LAB_PORT}",
                        "--no-browser",
                        "--allow-root",
                        f"--NotebookApp.token='{JUPYTER_LAB_TOKEN}'",
                        "--NotebookApp.password=''",
                        "--NotebookApp.allow_origin='*'",
                        "--ServerApp.disable_check_xsrf=True",
                        f"--ServerApp.root_dir={SPARK_WORKDIR}",
                    ]
                ),
            ],
            "environment": [
                "PYSPARK_PYTHON=python3",
                # f"JUPYTER_LAB_PORT={JUPYTER_LAB_PORT}",
                # f"JUPYTER_LAB_TOKEN={JUPYTER_LAB_TOKEN}",
                "SPARK_EXECUTOR_MEMORY=1536M",
            ],
            "volumes": [
                f"{os.path.join(DOCKER_MOUNTDIR,SPARK_SHARED_WORKSPACE)}:{SPARK_SHARED_WORKSPACE_DIR}",
                f"{os.path.join(DOCKER_MOUNTDIR,JUPYTER_LAB_NAME)}:{SPARK_WORKDIR}",
                f"{SPARK_VSCODE_SERVER_DIR}:/root/.vscode-server",
                # labs-setup itself, read-only, so spark_lab.ipynb runs here.
                f"{LABS_ROOT}:{SPARK_LABS_SETUP_DIR}:ro",
            ]
            + SPARK_MOUNT_JARS
            + SPARK_MOUNT_GRAPHFRAMES_JARS,
            "networks": ["spark-cluster"],
            "hostname": JUPYTER_LAB_COMPOSE_HOST,
            "ports": [
                f"{HOST_BIND_IP}:{JUPYTER_LAB_PORT}:{JUPYTER_LAB_PORT}",
                f"{HOST_BIND_IP}:{JUPYTER_LAB_MONITOR_PORT}:{JUPYTER_LAB_MONITOR_PORT}",
            ],
            "extra_hosts": [
                f"{DOCKER_INTERNAL_HOST}:host-gateway",
            ],
            "dns": DOCKER_DNS,
            "deploy": {"resources": {"limits": {"cpus": "2.0", "memory": "1G"}}},
            "healthcheck": {
                "test": [
                    "CMD",
                    "curl",
                    "-f",
                    f"http://{JUPYTER_LAB_HOSTNAME}:{JUPYTER_LAB_PORT}",
                ],
                "interval": "10s",
                "timeout": "10s",
                "retries": 10,
                "start_period": "10s",
            },
        },
    },
}

for i in range(SPARK_TOTAL_WORKERS):

    spark_compose_dict["services"][SPARK_WORKER_NAMES[i]] = {
        "image": f"apache/{SPARK_DOCKER_BASE}",
        "container_name": SPARK_WORKER_NAMES[i],
        "user": "root",
        "command": f'bash -c "rm -rf {SPARK_EXECUTOR_ENV_DIR} && mkdir -p {SPARK_EXECUTOR_ENV_DIR} && tar -xzf {SPARK_SHARED_WORKSPACE_DIR}/spark_job_env.tar.gz -C {SPARK_EXECUTOR_ENV_DIR} && /opt/spark/bin/spark-class org.apache.spark.deploy.$$SPARK_MODE.$${{SPARK_MODE^}} $$SPARK_MASTER_URL --host {SPARK_WORKER_HOSTNAMES[i]} --webui-port $$SPARK_WORKER_WEBUI_PORT"',
        "environment": [
            "PYSPARK_PYTHON=python3",
            "SPARK_MODE=worker",
            "SPARK_WORKER_CORES=2",
            "SPARK_DAEMON_MEMORY=512M",
            "SPARK_WORKER_MEMORY=2048M",
            f"SPARK_WORKER_WEBUI_PORT={SPARK_WORKER_WEBUI_PORTS[i]}",
            f"SPARK_MASTER_URL=spark://{SPARK_MASTER_HOSTNAME}:{SPARK_MASTER_PORT}",
        ],
        "volumes": [
            f"{os.path.join(DOCKER_MOUNTDIR,SPARK_SHARED_WORKSPACE)}:{SPARK_SHARED_WORKSPACE_DIR}",
            f"{os.path.join(DOCKER_MOUNTDIR,SPARK_WORKER_NAMES[i])}:{SPARK_WORKDIR}"
        ]
        + SPARK_MOUNT_JARS
        + SPARK_MOUNT_GRAPHFRAMES_JARS,
        "networks": ["spark-cluster"],
        "hostname": SPARK_WORKER_COMPOSE_HOSTS[i],
        "ports": [
            f"{HOST_BIND_IP}:{SPARK_WORKER_WEBUI_PORTS[i]}:{SPARK_WORKER_WEBUI_PORTS[i]}"
        ],
        "extra_hosts": [
            f"{DOCKER_INTERNAL_HOST}:host-gateway",
        ],
        "dns": DOCKER_DNS,
        "deploy": {"resources": {"limits": {"cpus": "4.0", "memory": "1.5G"}}},
        "depends_on": {
            "spark-master": {"condition": "service_healthy"},
            "spark-jupyter": {"condition": "service_healthy"},
        }
        | {
            SPARK_WORKER_NAMES[j]: {"condition": "service_started"} for j in range(0, i)
        },
        "healthcheck": {
            "test": [
                "CMD",
                "curl",
                "-f",
                f"http://{SPARK_WORKER_HOSTNAMES[i]}:{SPARK_WORKER_WEBUI_PORTS[i]}",
            ],
            "interval": "10s",
            "timeout": "10s",
            "retries": 10,
            "start_period": "10s",
        },
    }

# 3. Dump the dictionary to a YAML file
spark_compose_yaml_path = os.path.join(
    LOCALHOST_WORKDIR, "spark-cluster.docker-compose.yml"
)
spark_compose_yaml_contents = yaml.dump(
    spark_compose_dict, default_flow_style=False, sort_keys=False, indent=4
)
with open(spark_compose_yaml_path, "w", encoding="utf-8", newline="\n") as spark_compose_yaml_file:
    spark_compose_yaml_file.write(spark_compose_yaml_contents)

print(f"Successfully created: '{os.path.relpath(spark_compose_yaml_path)}'")
display(Markdown(f"```yaml\n{spark_compose_yaml_contents}\n```"))

# %% [markdown]
# ## 14. Start Spark
#
# - **What:** starts the master, JupyterLab and the workers and waits until every health check passes.
# - **Why:** the lab notebooks need a master with registered workers and a JupyterLab that answers.
# - **How:** `docker compose up -d --wait`; each health check runs `curl -f` against the service's web port.
# - 📄 [docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/)

# %%
run_command(["docker", "compose", "-f", "spark-cluster.docker-compose.yml", "up", "-d", "--wait"])

# %% [markdown]
# ## 15. GraphFrames check
#
# - **What:** checks `graphframes-py` 0.12.3 in `spark-jupyter` and both GraphFrames JARs in `/opt/spark/jars` of the Driver and every worker.
# - **Why:** graph code fails only at run time if a piece is missing; this catches it now.
# - **How:** `docker exec ... python3 -c "import graphframes"` and `test -f` for each JAR.
# - 📄 [GraphFrames](https://graphframes.io/)

# %%
graphframes_version = run_command(
    ["docker", "exec", JUPYTER_LAB_NAME, "python3", "-c", "import graphframes; print(graphframes.__version__)"]
).output.strip()
if graphframes_version != "0.12.3":
    raise RuntimeError(f"spark-jupyter has graphframes-py {graphframes_version!r}, expected '0.12.3'")
for container_name in [JUPYTER_LAB_NAME, *SPARK_WORKER_NAMES]:
    for jar_name in SPARK_GRAPHFRAMES_JARS:
        run_command(["docker", "exec", container_name, "test", "-f", f"/opt/spark/jars/{jar_name}"])
print(f"GraphFrames {graphframes_version} ready in {JUPYTER_LAB_NAME} and {', '.join(SPARK_WORKER_NAMES)}")
