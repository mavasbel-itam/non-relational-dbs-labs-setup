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
# # Hive — infrastructure (metastore + HiveServer2 on the Hadoop cluster)
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
# - **What:** locates the labs-setup root, changes into `hive/` and imports `run_command`.
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
MODULE_DIR = LABS_ROOT / "hive"
import sys

if str(LABS_ROOT) not in sys.path:
    sys.path.insert(0, str(LABS_ROOT))
from labs_runtime import run_command

os.chdir(MODULE_DIR)
print(f"Working directory: {MODULE_DIR}")

# %% [markdown]
# ## 4. Services and resources
#
# - **What:** names and ports of PostgreSQL (`hive-metastore-db`, `15432`), the metastore (`9083`) and HiveServer2 (`10000`, UI `10002`); images `postgres:18` and `apache/hive:4.0.1`; the Hadoop host names Hive uses.
# - **Why:** Hive keeps table definitions in PostgreSQL through the metastore and runs queries on the Hadoop cluster; `hive-server2` is also the student's terminal (`docker exec -it -u hive -w /tmp/hive-lab hive-server2 bash`).
# - **How:** both Hive JVMs get `-Xmx256m` (measured: largest live heap 162 MiB for HiveServer2 and 34 MiB for the metastore) and `MALLOC_ARENA_MAX=2`, so they fit their memory limits (1792 MB for HiveServer2, 512 MB for the metastore).
# - 📄 [Java 8 — `-Xmx`](https://docs.oracle.com/javase/8/docs/technotes/tools/unix/java.html) · [mallopt(3) — `MALLOC_ARENA_MAX`](https://man7.org/linux/man-pages/man3/mallopt.3.html)

# %%
HIVE_START_FROM_SCRATCH = START_FROM_SCRATCH
DOCKER_INTERNAL_HOST = "host.docker.internal"
DOCKER_DNS = [VPN_DNS_IP] if NETWORK_MODE == "vpn" else []
HOST_BIND_IP = VPN_HOST_IP if NETWORK_MODE == "vpn" else "127.0.0.1"

POSTGRES_USER = "hive"
POSTGRES_PASSWORD = "hive"
POSTGRES_DB = "metastore"

HIVE_DB_CONTAINER_NAME = "hive-metastore-db"
HIVE_METASTORE_CONTAINER_NAME = "hive-metastore"
HIVE_SERVER2_CONTAINER_NAME = "hive-server2"
# hive-server2 is also the student's terminal: `docker exec -it -u hive -w /tmp/hive-lab hive-server2 bash`
# gives the Hive and Hadoop clients with HiveServer2's own configuration. Student files live in
# HIVE_STUDENT_DIR, apart from HiveServer2's local scratch (/tmp/hive/local) and its log (/tmp/hive).
# Its memory limit (HIVE_SERVER2_MEMORY) leaves room for HiveServer2 plus the client JVMs a student
# runs next to it (Beeline, hdfs dfs).
HIVE_STUDENT_DIR = "/tmp/hive-lab"
HIVE_SERVER2_MEMORY = "1792M"
HIVE_SERVER2_CPUS = "2.0"

# Java heap of the two Hive services. The image's entrypoint passes -Xmx1G, larger than the
# containers' memory limits (HIVE_SERVER2_MEMORY, 512M metastore), so the JVM may grow its heap
# past what the container can hold. A second -Xmx in SERVICE_OPTS comes after the image's on
# the command line and the last one wins. Measured over the Hive lab and the Hive deck
# walkthroughs with GC logs (2026-10-18): the largest live heap after a collection was 162 MiB
# (HiveServer2) and 34 MiB (metastore). Most of HiveServer2's memory is outside the heap
# (Native Memory Tracking with a 320 MiB heap: classes 202 MiB, code 80 MiB, thread stacks
# 75 MiB, symbols 40 MiB); with -Xmx256m its resident size peaked at 735 MiB.
HIVE_SERVER2_HEAP = "-Xmx256m"
HIVE_METASTORE_HEAP = "-Xmx256m"
# glibc gives each thread that allocates its own malloc arena (up to 8 per CPU); limiting them
# to 2 keeps HiveServer2's ~110 threads from holding hundreds of MiB of half-used arenas.
HIVE_MALLOC_ARENA_MAX = "2"

HIVE_DB_HOSTNAME = HIVE_DB_CONTAINER_NAME
HIVE_METASTORE_HOSTNAME = HIVE_METASTORE_CONTAINER_NAME
HIVE_SERVER2_HOSTNAME = HIVE_SERVER2_CONTAINER_NAME
HIVE_DB_COMPOSE_HOST = (
    HIVE_DB_HOSTNAME
    if NETWORK_MODE == "local"
    else f"{HIVE_DB_CONTAINER_NAME}.{VPN_CLIENT_DOMAIN}"
)
HIVE_METASTORE_COMPOSE_HOST = (
    HIVE_METASTORE_HOSTNAME
    if NETWORK_MODE == "local"
    else f"{HIVE_METASTORE_CONTAINER_NAME}.{VPN_CLIENT_DOMAIN}"
)
HIVE_SERVER2_COMPOSE_HOST = (
    HIVE_SERVER2_HOSTNAME
    if NETWORK_MODE == "local"
    else f"{HIVE_SERVER2_CONTAINER_NAME}.{VPN_CLIENT_DOMAIN}"
)
HIVE_DB_CLIENT_HOST = (
    "127.0.0.1"
    if NETWORK_MODE == "local"
    else f"{HIVE_DB_CONTAINER_NAME}.{VPN_CLIENT_DOMAIN}"
)
HIVE_METASTORE_CLIENT_HOST = (
    "127.0.0.1"
    if NETWORK_MODE == "local"
    else f"{HIVE_METASTORE_CONTAINER_NAME}.{VPN_CLIENT_DOMAIN}"
)
HIVE_SERVER2_CLIENT_HOST = (
    "127.0.0.1"
    if NETWORK_MODE == "local"
    else f"{HIVE_SERVER2_CONTAINER_NAME}.{VPN_CLIENT_DOMAIN}"
)

HIVE_DB_INTERNAL_PORT = 15432
HIVE_METASTORE_INTERNAL_PORT = 9083
HIVE_SERVER2_INTERNAL_PORT = 10000
HIVE_SERVER2_UI_INTERNAL_PORT = 10002

HIVE_DB_EXTERNAL_PORT = 15432
HIVE_METASTORE_EXTERNAL_PORT = 9083
HIVE_SERVER2_EXTERNAL_PORT = 10000
HIVE_SERVER2_UI_EXTERNAL_PORT = 10002

HIVE_USERDIR = "/user/hive"
HIVE_DATADIR = f"{HIVE_USERDIR}/warehouse"

HADOOP_RESOURCEMANAGER_WEBUI_PORT = 8088
HADOOP_RESOURCEMANAGER_RPC_APP_MANAGER_PORT = 8032
HADOOP_RESOURCEMANAGER_TRACKER_PORT = 8031
HADOOP_RESOURCEMANAGER_SCHEDULER_PORT = 8030
HADOOP_RESOURCEMANAGER_ADMIN_PORT = 8033

HADOOP_NAMENODE_HOSTNAME = "namenode"
HADOOP_NAMENODE_PORT = 8020

HADOOP_RESOURCEMANAGER_HOSTNAME = "resourcemanager"
HADOOP_RESOURCEMANAGER_PORT = 8032

APACHE_HIVE_IMAGE = "apache/hive:4.0.1"
POSTGRES_IMAGE = "postgres:18"

# %% [markdown]
# ## 5. Host folder
#
# - **What:** creates `mount/`, with one folder per Hive service.
# - **Why:** the metastore database and the generated configuration live on the host.
# - **How:** relative path `mount/` from the module folder.
# - 📄 [Docker — Bind mounts](https://docs.docker.com/engine/storage/bind-mounts/)

# %%
import os
from pathlib import Path

LOCAL_WORKDIR = f"{os.path.join(os.path.relpath(Path.cwd()))}"
DOCKER_MOUNTDIR = os.path.join(LOCAL_WORKDIR, "mount")

mount_path = Path(DOCKER_MOUNTDIR)
mount_path.mkdir(parents=True, exist_ok=True)

# %% [markdown]
# ## 6. Stop the previous stack
#
# - **What:** with `START_FROM_SCRATCH=True`, removes the Hive containers and volumes; Hadoop is not touched.
# - **Why:** a fresh build must not reuse an old metastore; with `False` the running stack is kept.
# - **How:** `docker compose -f hive-cluster.docker-compose.yml down -v` (`check=False`).
# - 📄 [docker compose down](https://docs.docker.com/reference/cli/docker/compose/down/)

# %%
import subprocess

if HIVE_START_FROM_SCRATCH:
    subprocess.run(
        ["docker", "compose", "-f", "hive-cluster.docker-compose.yml", "down", "-v"],
        check=False,
    )
else:
    print("Preserving existing containers and volumes")


# %% [markdown]
# ## 7. Delete the old state
#
# - **What:** with `START_FROM_SCRATCH=True`, empties each service's folder under `mount/`, then recreates the folders.
# - **Why:** the PostgreSQL files belong to the container's user and the host user cannot always delete them.
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


os.makedirs(os.path.join(DOCKER_MOUNTDIR), exist_ok=True)
for container in [
    HIVE_DB_CONTAINER_NAME,
    HIVE_METASTORE_CONTAINER_NAME,
    HIVE_SERVER2_CONTAINER_NAME,
]:
    if HIVE_START_FROM_SCRATCH:
        clear_bind_directory(os.path.join(DOCKER_MOUNTDIR, container))
    os.makedirs(os.path.join(DOCKER_MOUNTDIR, container), exist_ok=True)

# %% [markdown]
# ## 8. Hadoop client files
#
# - **What:** writes `core-site.xml` (`fs.defaultFS=hdfs://namenode:8020`) and `hdfs-site.xml` for both Hive services.
# - **Why:** without `hdfs-site.xml` Hive's HDFS client writes 3 replicas, but the cluster has 2 DataNodes, so every block it writes would stay under-replicated.
# - **How:** the replication factor is read from the running NameNode with `hdfs getconf -confKey dfs.replication`.
# - 📄 [HDFS commands (getconf)](https://hadoop.apache.org/docs/r3.4.3/hadoop-project-dist/hadoop-hdfs/HDFSCommands.html)

# %%
core_site_xml_content = f"""<?xml version="1.0"?>
<configuration>
    <property>
        <name>fs.defaultFS</name>
        <value>hdfs://{HADOOP_NAMENODE_HOSTNAME}:{HADOOP_NAMENODE_PORT}</value>
    </property>
</configuration>
"""

# Hive's HDFS client reads HADOOP_CONF_DIR=/hive_custom_conf. Without an
# hdfs-site.xml there it writes with Hadoop's default replication of 3, which
# leaves every block Hive writes permanently under-replicated on this
# cluster, so the factor is read from the running NameNode.
HADOOP_REPLICATION = subprocess.run(
    ["docker", "exec", HADOOP_NAMENODE_HOSTNAME, "hdfs", "getconf", "-confKey", "dfs.replication"],
    capture_output=True, text=True, check=True,
    encoding="utf-8",
).stdout.strip().splitlines()[-1]
assert HADOOP_REPLICATION.isdigit(), HADOOP_REPLICATION

hdfs_site_xml_content = f"""<?xml version="1.0"?>
<configuration>
    <property>
        <name>dfs.replication</name>
        <value>{HADOOP_REPLICATION}</value>
    </property>
</configuration>
"""

for container in [HIVE_METASTORE_CONTAINER_NAME, HIVE_SERVER2_CONTAINER_NAME]:
    dest_dir = os.path.join(DOCKER_MOUNTDIR, container, "hive_custom_conf")
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "core-site.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(core_site_xml_content)
    with open(os.path.join(dest_dir, "hdfs-site.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(hdfs_site_xml_content)

# %% [markdown]
# ## 9. hive-site.xml
#
# - **What:** writes Hive's main configuration for both services.
# - **Why:** it tells Hive where its metastore database is, where HDFS and YARN are, and how to run queries.
# - **How:** PostgreSQL JDBC connection (`javax.jdo.option.*`), `hive.metastore.uris=thrift://hive-metastore:9083`, `hive.execution.engine=tez` with the Tez libraries at `/apps/dist-lib/dist-lib.tar.gz` in HDFS, scratch folders, `hive.server2.enable.doAs=false` (queries run as `hive`), and `hive.fetch.task.conversion=more` plus `hive.exec.mode.local.auto=true` so small queries skip YARN.
# - 📄 [Hive metastore administration](https://hive.apache.org/docs/latest/admin/adminmanual-metastore-administration/) · [Hive configuration properties](https://hive.apache.org/docs/latest/user/configuration-properties/) · [Hive configuration (scratch dirs)](https://hive.apache.org/docs/latest/admin/adminmanual-configuration/) · [Tez install (`tez.lib.uris`)](https://tez.apache.org/install.html)

# %%
hive_site_xml_content = f"""<?xml version="1.0"?>
<configuration>
    <property>
        <name>hive.users.in.admin.role</name>
        <value>hive,root,hadoop</value>
    </property>
    <property>
        <name>hive.server2.thrift.bind.host</name>
        <value>0.0.0.0</value>
    </property>
    <property>
        <name>hive.server2.webui.host</name>
        <value>0.0.0.0</value>
    </property>

    <property>
        <name>javax.jdo.option.ConnectionURL</name>
        <value>jdbc:postgresql://{HIVE_DB_HOSTNAME}:{HIVE_DB_EXTERNAL_PORT}/{POSTGRES_DB}</value>
    </property>
    <property>
        <name>javax.jdo.option.ConnectionDriverName</name>
        <value>org.postgresql.Driver</value>
    </property>
    <property>
        <name>javax.jdo.option.ConnectionUserName</name>
        <value>{POSTGRES_USER}</value>
    </property>
    <property>
        <name>javax.jdo.option.ConnectionPassword</name>
        <value>{POSTGRES_PASSWORD}</value>
    </property>

    <property>
        <name>fs.defaultFS</name>
        <value>hdfs://{HADOOP_NAMENODE_HOSTNAME}:{HADOOP_NAMENODE_PORT}</value>
    </property>
    <property>
        <name>dfs.datanode.use.datanode.hostname</name>
        <value>true</value>
    </property>
    <property>
        <name>hive.metastore.uris</name>
        <value>thrift://{HIVE_METASTORE_HOSTNAME}:{HIVE_METASTORE_EXTERNAL_PORT}</value>
    </property>
    <property>
        <name>yarn.resourcemanager.address</name>
        <value>{HADOOP_RESOURCEMANAGER_HOSTNAME}:{HADOOP_RESOURCEMANAGER_RPC_APP_MANAGER_PORT}</value>
    </property>
    <property>
        <name>yarn.resourcemanager.scheduler.address</name>
        <value>{HADOOP_RESOURCEMANAGER_HOSTNAME}:{HADOOP_RESOURCEMANAGER_SCHEDULER_PORT}</value>
    </property>
    <property>
        <name>mapreduce.framework.name</name>
        <value>yarn</value>
    </property>

    <property>
        <name>hive.server2.enable.doAs</name>
        <value>false</value>
    </property>
    <property>
        <name>hive.server2.thrift.port</name>
        <value>10000</value>
    </property>
    <property>
        <name>hive.server2.transport.mode</name>
        <value>binary</value>
    </property>
    <property>
        <name>hive.plan.serialization.format</name>
        <value>javaXML</value>
    </property>
    <property>
        <name>hive.exec.submit.local.task.via.child</name>
        <value>false</value>
    </property>

    <property>
        <name>hive.metastore.event.db.listener.timetolive</name>
        <value>0s</value>
    </property>
    <property>
        <name>hive.notification.event.poll.interval</name>
        <value>0s</value>
    </property>

    <property>
        <name>tez.lib.uris</name>
        <value>hdfs://{HADOOP_NAMENODE_HOSTNAME}:{HADOOP_NAMENODE_PORT}/apps/dist-lib/dist-lib.tar.gz</value>
    </property>
    <property>
        <name>tez.use.cluster.hadoop-libs</name>
        <value>true</value> 
    </property>
    <property>
        <name>tez.ignore.lib.uris</name>
        <value>false</value>
    </property>
    <property>
        <name>hive.execution.engine</name>
        <value>tez</value> 
    </property>
    <property>
        <name>tez.local.mode</name>
        <value>false</value>
    </property>
    <property>
        <name>tez.runtime.optimize.local.fetch</name>
        <value>true</value>
    </property>

    <property>
        <name>hive.exec.scratchdir</name>
        <value>hdfs://{HADOOP_NAMENODE_HOSTNAME}:{HADOOP_NAMENODE_PORT}/tmp/hive/scratch</value>
    </property>
    <property>
        <name>hive.exec.local.scratchdir</name>
        <value>/tmp/hive/local</value>
    </property>
    <property>
        <name>hive.start.cleanup.scratchdir</name>
        <value>true</value>
    </property>
    <property>
        <name>hive.fetch.task.conversion</name>
        <value>more</value>
    </property>
    <property>
        <name>hive.exec.mode.local.auto</name>
        <value>true</value>
    </property>
</configuration>
"""

for container in [HIVE_METASTORE_CONTAINER_NAME, HIVE_SERVER2_CONTAINER_NAME]:
    dest_dir = os.path.join(DOCKER_MOUNTDIR, container, "hive_custom_conf")
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "hive-site.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(hive_site_xml_content)

# %% [markdown]
# ## 10. tez-site.xml
#
# - **What:** writes the Tez configuration for both services.
# - **Why:** Tez runs Hive's query plans as DAGs on YARN and must find its libraries and Hadoop's.
# - **How:** `tez.lib.uris` points at the tarball in HDFS; `tez.use.cluster.hadoop-libs=true` and an extra classpath reuse the Hadoop jars installed on the NodeManagers.
# - 📄 [Tez install (`tez.lib.uris`)](https://tez.apache.org/install.html)

# %%
tez_site_content = f"""<?xml version="1.0"?>
<configuration>
    <property>
        <name>tez.lib.uris</name>
        <value>hdfs://{HADOOP_NAMENODE_HOSTNAME}:{HADOOP_NAMENODE_PORT}/apps/dist-lib/dist-lib.tar.gz</value>
    </property>
    <property>
        <name>tez.use.cluster.hadoop-libs</name>
        <value>true</value> 
    </property>
    <property>
        <name>tez.ignore.lib.uris</name>
        <value>false</value>
    </property>
    <property>
        <name>tez.local.mode</name>
        <value>false</value>
    </property>
    <property>
        <name>tez.runtime.optimize.local.fetch</name>
        <value>true</value>
    </property>
    <property>
        <name>tez.cluster.additional.classpath.prefix</name>
        <value>/opt/hadoop/share/hadoop/common/*:/opt/hadoop/share/hadoop/common/lib/*:/opt/hadoop/share/hadoop/hdfs/*:/opt/hadoop/share/hadoop/hdfs/lib/*:/opt/hadoop/share/hadoop/yarn/*:/opt/hadoop/share/hadoop/yarn/lib/*:/opt/hive/lib/*:/opt/hive/conf</value>
    </property>
    <property>
        <name>tez.am.hostname</name>
        <value>0.0.0.0</value> 
    </property>
    <property>
        <name>tez.am.launch.cmd-opts</name>
        <value>-Djava.net.preferIPv4Stack=true -Dhadoop.rpc.protection=authentication</value>
    </property>

    <property>
        <name>hive.exec.scratchdir</name>
        <value>hdfs://{HADOOP_NAMENODE_HOSTNAME}:{HADOOP_NAMENODE_PORT}/tmp/hive/scratch</value>
    </property>
    <property>
        <name>hive.exec.local.scratchdir</name>
        <value>/tmp/hive/local</value>
    </property>
    <property>
        <name>hive.start.cleanup.scratchdir</name>
        <value>true</value>
    </property>
    
    <property>
        <name>tez.history.logging.service.class</name>
        <value>org.apache.tez.dag.history.logging.ats.ATSHistoryLoggingService</value>
    </property>

    <property>
        <name>mapreduce.framework.name</name>
        <value>yarn</value>
    </property>
    <property>
        <name>hive.exec.submit.local.task.via.child</name>
        <value>false</value>
    </property>
</configuration>
"""

for container in [HIVE_METASTORE_CONTAINER_NAME, HIVE_SERVER2_CONTAINER_NAME]:
    dest_dir = os.path.join(DOCKER_MOUNTDIR, container, "hive_custom_conf")
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "tez-site.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(tez_site_content)

# %% [markdown]
# ## 11. Logging
#
# - **What:** writes `log4j.properties` for both services: everything at `INFO`, to the console.
# - **Why:** `docker logs` then shows Hive, Hadoop, Tez, Parquet and Iceberg messages.
# - **How:** a console appender on `System.err`.

# %%
import os

# 1. Definimos el contenido del archivo de logs
log4j_properties_content = """#
log4j.rootLogger=INFO, console

# Configuración del appender (salida estándar)
log4j.appender.console=org.apache.log4j.ConsoleAppender
log4j.appender.console.target=System.err
log4j.appender.console.layout=org.apache.log4j.PatternLayout
log4j.appender.console.layout.ConversionPattern=%d{yy/MM/dd HH:mm:ss} %p %c{2}: %m%n

# Silenciar componentes específicos que son muy ruidosos
log4j.logger.org.apache.hadoop=INFO
log4j.logger.org.apache.hive=INFO
log4j.logger.org.apache.tez=INFO
log4j.logger.org.apache.parquet=INFO
log4j.logger.org.apache.iceberg=INFO
"""

# 2. Iteramos sobre los contenedores para escribir el archivo
for container in [HIVE_METASTORE_CONTAINER_NAME, HIVE_SERVER2_CONTAINER_NAME]:
    dest_dir = os.path.join(DOCKER_MOUNTDIR, container, "hive_custom_conf")
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "log4j.properties"), "w", encoding="utf-8", newline="\n") as f:
        f.write(log4j_properties_content)

# %% [markdown]
# ## 12. Write the Compose file
#
# - **What:** generates `hive-cluster.docker-compose.yml` with PostgreSQL, the metastore and HiveServer2 on the existing `hadoop-network`.
# - **Why:** Hive must reach the NameNode, the ResourceManager and the NodeManagers by name, so it joins Hadoop's network.
# - **How:** the image reads `SERVICE_NAME`, `SERVICE_OPTS` and `HIVE_CUSTOM_CONF_DIR`; the metastore's entrypoint creates or checks its schema in PostgreSQL, while HiveServer2 runs with `IS_RESUME=true` and never touches it; HiveServer2 removes a stale PID file at start and creates `/tmp/hive-lab`; PostgreSQL listens on `PGPORT=15432` and is healthy when `pg_isready` answers.
# - 📄 [Hive — Docker quickstart](https://hive.apache.org/development/quickstart/) · [postgres image](https://hub.docker.com/_/postgres) · [libpq — PGPORT](https://www.postgresql.org/docs/18/libpq-envars.html) · [pg_isready](https://www.postgresql.org/docs/18/app-pg-isready.html) · [Compose file — services](https://docs.docker.com/reference/compose-file/services/)

# %%
import yaml
from IPython.display import Markdown, display

compose_filename = os.path.join(LOCAL_WORKDIR, "hive-cluster.docker-compose.yml")

# Usamos EXTERNAL_PORT para respetar tu VPN/DNS
metastore_jdbc_opts = f" ".join(
    [
        f"-Dhive.metastore.db.type=postgres",
        f"-Dmetastore.db.type=postgres",
        f"-Djavax.jdo.option.ConnectionDriverName=org.postgresql.Driver",
        f"-Djavax.jdo.option.ConnectionURL=jdbc:postgresql://{HIVE_DB_HOSTNAME}:{HIVE_DB_EXTERNAL_PORT}/{POSTGRES_DB}",
        f"-Djavax.jdo.option.ConnectionUserName={POSTGRES_USER}",
        f"-Djavax.jdo.option.ConnectionPassword={POSTGRES_PASSWORD}",
    ]
)

hdfs_opts = f" ".join(
    [
        f"-Dfs.defaultFS=hdfs://{HADOOP_NAMENODE_HOSTNAME}:{HADOOP_NAMENODE_PORT}",
        f"-Dhive.metastore.warehouse.dir=hdfs://{HADOOP_NAMENODE_HOSTNAME}:{HADOOP_NAMENODE_PORT}{HIVE_DATADIR}/managed",
        "-Dmapreduce.framework.name=yarn",
        f"-Dyarn.resourcemanager.address={HADOOP_RESOURCEMANAGER_HOSTNAME}:{HADOOP_RESOURCEMANAGER_RPC_APP_MANAGER_PORT}",
        f"-Dmapreduce.application.classpath=/opt/hadoop/share/hadoop/mapreduce/*:/opt/hadoop/share/hadoop/mapreduce/lib/*:/opt/hadoop/share/hadoop/common/*:/opt/hadoop/share/hadoop/common/lib/*:/opt/hadoop/share/hadoop/hdfs/*:/opt/hadoop/share/hadoop/hdfs/lib/*:/opt/hadoop/share/hadoop/yarn/*:/opt/hadoop/share/hadoop/yarn/lib/*",
    ]
)

hive_compose_dict = {
    "name": "hive-cluster",
    # "networks": {"hive-cluster": {"driver": "bridge"}},
    # "networks": {
    #     "hadoop-cluster": {"external": True, "name": "hadoop-cluster_hadoop-cluster"}
    # },
    "networks": {
        "hadoop-cluster": {
            "external": True,
            "name": "hadoop-network",
        }
    },
    "services": {
        HIVE_DB_CONTAINER_NAME: {
            "image": POSTGRES_IMAGE,
            "container_name": HIVE_DB_CONTAINER_NAME,
            "hostname": HIVE_DB_COMPOSE_HOST,
            "environment": {
                "POSTGRES_USER": POSTGRES_USER,
                "POSTGRES_PASSWORD": POSTGRES_PASSWORD,
                "POSTGRES_DB": POSTGRES_DB,
                "PGPORT": str(HIVE_DB_INTERNAL_PORT),
            },
            "volumes": [
                f"{os.path.join(DOCKER_MOUNTDIR, HIVE_DB_CONTAINER_NAME)}:/var/lib/postgresql"
            ],
            "networks": ["hadoop-cluster"],
            "ports": [
                f"{HOST_BIND_IP}:{HIVE_DB_EXTERNAL_PORT}:{HIVE_DB_INTERNAL_PORT}"
            ],
            "extra_hosts": [f"{DOCKER_INTERNAL_HOST}:host-gateway"],
            "dns": DOCKER_DNS,
            "deploy": {"resources": {"limits": {"cpus": "1.0", "memory": "512M"}}},
            "healthcheck": {
                "test": [
                    "CMD-SHELL",
                    f"pg_isready -h 127.0.0.1 -p {HIVE_DB_INTERNAL_PORT} -U {POSTGRES_USER} -d {POSTGRES_DB}",
                ],
                "interval": "5s",
                "timeout": "5s",
                "retries": 20,
                "start_period": "15s",
            },
        },
        HIVE_METASTORE_CONTAINER_NAME: {
            "image": APACHE_HIVE_IMAGE,
            "container_name": HIVE_METASTORE_CONTAINER_NAME,
            "hostname": HIVE_METASTORE_COMPOSE_HOST,
            # No IS_RESUME: the image's entrypoint runs `schematool -initOrUpgradeSchema` before
            # starting the metastore, which creates the schema on an empty database and leaves a
            # current one unchanged, so no separate one-shot container is needed (Apache Hive
            # docker README: "To skip schematool initialisation or upgrade for metastore use
            # IS_RESUME=true"). HiveServer2 keeps IS_RESUME=true and never touches the schema.
            "depends_on": {HIVE_DB_CONTAINER_NAME: {"condition": "service_healthy"}},
            "environment": {
                "DB_DRIVER": "postgres",
                "SERVICE_NAME": "metastore",
                "MALLOC_ARENA_MAX": HIVE_MALLOC_ARENA_MAX,
                "HIVE_CUSTOM_CONF_DIR": "/hive_custom_conf",
                "TEZ_CONF_DIR": "/hive_custom_conf",
                "HADOOP_CONF_DIR": "/hive_custom_conf",
                "SERVICE_OPTS": f"{metastore_jdbc_opts} {hdfs_opts} {HIVE_METASTORE_HEAP}",
                # "HADOOP_CLASSPATH": "/hive_custom_conf:/opt/hive/lib/postgresql-42.7.10.jar:/opt/hive/lib/*:/opt/tez/*:/opt/tez/lib/*",
                "HADOOP_CLASSPATH": "/hive_custom_conf:/opt/hive/lib/postgresql-42.7.10.jar:/opt/tez/*:/opt/tez/lib/*",
            },
            "volumes": [
                "./postgresql-42.7.10.jar:/opt/hive/lib/postgresql-42.7.10.jar",
                f"./mount/{HIVE_METASTORE_CONTAINER_NAME}/hive_custom_conf:/hive_custom_conf",
                f"./mount/{HIVE_METASTORE_CONTAINER_NAME}/hive_custom_conf/core-site.xml:/opt/hadoop/etc/hadoop/core-site.xml",
            ],
            "networks": ["hadoop-cluster"],
            "ports": [
                f"{HOST_BIND_IP}:{HIVE_METASTORE_EXTERNAL_PORT}:{HIVE_METASTORE_INTERNAL_PORT}"
            ],
            "extra_hosts": [f"{DOCKER_INTERNAL_HOST}:host-gateway"],
            "dns": DOCKER_DNS,
            "deploy": {"resources": {"limits": {"cpus": "1.0", "memory": "512M"}}},
            "healthcheck": {
                "test": [
                    "CMD-SHELL",
                    f"bash -c '</dev/tcp/127.0.0.1/{HIVE_METASTORE_INTERNAL_PORT}'",
                ],
                "interval": "5s",
                "timeout": "5s",
                "retries": 20,
                "start_period": "15s",
            },
        },
        HIVE_SERVER2_CONTAINER_NAME: {
            "image": APACHE_HIVE_IMAGE,
            "container_name": HIVE_SERVER2_CONTAINER_NAME,
            "hostname": HIVE_SERVER2_COMPOSE_HOST,
            # HiveServer2 leaves /opt/hive/conf/hiveserver2.pid in the container layer. After a hard
            # stop (OOM kill, docker kill, host crash) the same container restarts with PID 7 taken by
            # its own shell and refuses to start ("HiveServer2 running as process 7. Stop it first.").
            # No other HiveServer2 runs in the container, so a PID file at start is always stale.
            # The same start command creates the students' working folder (owned by hive, the
            # image's user), so it exists after every start without a one-shot container.
            "entrypoint": ["sh", "-c", f"rm -f /opt/hive/conf/hiveserver2.pid && mkdir -p {HIVE_STUDENT_DIR} && exec /entrypoint.sh"],
            "depends_on": {
                HIVE_METASTORE_CONTAINER_NAME: {"condition": "service_healthy"}
            },
            "environment": {
                "DB_DRIVER": "postgres",
                "IS_RESUME": "true",
                "SERVICE_NAME": "hiveserver2",
                "MALLOC_ARENA_MAX": HIVE_MALLOC_ARENA_MAX,
                "HIVE_CUSTOM_CONF_DIR": "/hive_custom_conf",
                "TEZ_CONF_DIR": "/hive_custom_conf",
                "HADOOP_CONF_DIR": "/hive_custom_conf",
                "SERVICE_OPTS": f"-Dhive.metastore.uris=thrift://{HIVE_METASTORE_HOSTNAME}:{HIVE_METASTORE_EXTERNAL_PORT} {hdfs_opts} {HIVE_SERVER2_HEAP}",
                # "HADOOP_CLASSPATH": "/hive_custom_conf:/opt/hive/lib/postgresql-42.7.10.jar:/opt/hive/lib/*:/opt/tez/*:/opt/tez/lib/*",
                "HADOOP_CLASSPATH": "/hive_custom_conf:/opt/hive/lib/postgresql-42.7.10.jar:/opt/tez/*:/opt/tez/lib/*",
            },
            "volumes": [
                "./postgresql-42.7.10.jar:/opt/hive/lib/postgresql-42.7.10.jar",
                f"./mount/{HIVE_SERVER2_CONTAINER_NAME}/hive_custom_conf:/hive_custom_conf",
                f"./mount/{HIVE_SERVER2_CONTAINER_NAME}/hive_custom_conf/core-site.xml:/opt/hadoop/etc/hadoop/core-site.xml",
            ],
            "networks": ["hadoop-cluster"],
            "ports": [
                f"{HOST_BIND_IP}:{HIVE_SERVER2_EXTERNAL_PORT}:{HIVE_SERVER2_INTERNAL_PORT}",
                f"{HOST_BIND_IP}:{HIVE_SERVER2_UI_EXTERNAL_PORT}:{HIVE_SERVER2_UI_INTERNAL_PORT}",
            ],
            "extra_hosts": [f"{DOCKER_INTERNAL_HOST}:host-gateway"],
            "dns": DOCKER_DNS,
            "deploy": {"resources": {"limits": {"cpus": HIVE_SERVER2_CPUS, "memory": HIVE_SERVER2_MEMORY}}},
            "healthcheck": {
                "test": [
                    "CMD-SHELL",
                    f"bash -c '</dev/tcp/127.0.0.1/{HIVE_SERVER2_INTERNAL_PORT}'",
                ],
                "interval": "5s",
                "timeout": "5s",
                "retries": 30,
                "start_period": "15s",
            },
        },
    },
}

yaml_contents = yaml.dump(
    hive_compose_dict, default_flow_style=False, sort_keys=False, indent=4
)
with open(compose_filename, "w", encoding="utf-8", newline="\n") as f:
    f.write(yaml_contents)

# %% [markdown]
# ## 13. Safe-mode escape hatch
#
# - **What:** a commented-out `hdfs dfsadmin -safemode leave`.
# - **Why:** only needed by hand if the NameNode stays in safe mode and blocks writes.
# - **How:** nothing runs unless the line is uncommented.
# - 📄 [HDFS commands (getconf)](https://hadoop.apache.org/docs/r3.4.3/hadoop-project-dist/hadoop-hdfs/HDFSCommands.html)

# %%
# # !docker exec namenode hdfs dfsadmin -safemode leave

# %% [markdown]
# ## 14. HDFS folders and the `hive` user
#
# - **What:** with `START_FROM_SCRATCH=True`, clears `/tmp/hive` and the warehouse; then creates the `hive` user in `namenode` and the HDFS folders `/tmp/hive` and `/user/hive/warehouse/{managed,external}`.
# - **Why:** HDFS checks permissions against the users and groups known to the NameNode, and Hive writes its tables and scratch files there.
# - **How:** `groupadd`/`useradd` inside `namenode`, then `hdfs dfs -mkdir -p`, `-chown -R hive:hive` and `-chmod -R 777`; finally a default ACL (`-setfacl -m default:user:hive:rwx,...`) on `/tmp/hive`, `managed` and `external`, so every folder created below them inherits write access for `hive`, whoever creates it. Without it, a folder made from `namenode` (user `hadoop`, umask `022`) ends up `drwxr-xr-x` and `LOAD DATA INPATH`, which moves the file, fails with `Permission denied: user=hive, access=WRITE`.
# - 📄 [FileSystem shell](https://hadoop.apache.org/docs/r3.4.3/hadoop-project-dist/hadoop-common/FileSystemShell.html) · [HDFS Permissions Guide: ACLs](https://hadoop.apache.org/docs/r3.4.3/hadoop-project-dist/hadoop-hdfs/HdfsPermissionsGuide.html#ACLs_Access_Control_Lists)

# %%
if HIVE_START_FROM_SCRATCH:
    for hdfs_path in [
        "/tmp/hive/*",
        f"{HIVE_DATADIR}/managed/*",
        f"{HIVE_DATADIR}/external/*",
    ]:
        subprocess.run(
            [
                "docker", "exec", "-u", "hadoop", "namenode", "bash", "-c",
                f"hdfs dfs -rm -r -f -skipTrash {hdfs_path}",
            ],
            check=False,
        )

run_command(["docker", "exec", "-u", "root", "namenode", "groupadd", "hive"], check=False)
run_command(["docker", "exec", "-u", "root", "namenode", "useradd", "-m", "-g", "hive", "hive"], check=False)
run_command(["docker", "exec", "-u", "root", "namenode", "usermod", "-aG", "sudo", "hive"], check=False)
run_command(["docker", "exec", "-u", "root", "namenode", "usermod", "-aG", "hadoop", "hive"], check=False)
run_command(["docker", "exec", "-u", "root", "namenode", "bash", "-c", "grep -qFx 'hive ALL=(ALL) NOPASSWD:ALL' /etc/sudoers || echo 'hive ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers"], check=False)
# # !docker exec -u root namenode bash -c "echo 'hive ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers"
run_command(["docker", "exec", "-u", "hadoop", "namenode", "hdfs", "dfs", "-mkdir", "-p", "/tmp/hive"], check=False)
run_command(["docker", "exec", "-u", "hadoop", "namenode", "hdfs", "dfs", "-chown", "-R", "hive:hive", "/tmp/hive"], check=False)
run_command(["docker", "exec", "-u", "hadoop", "namenode", "hdfs", "dfs", "-chmod", "-R", "777", "/tmp"], check=False)
run_command(["docker", "exec", "-u", "hadoop", "namenode", "hdfs", "dfs", "-mkdir", "-p", f"{HIVE_DATADIR}/managed"], check=False)
run_command(["docker", "exec", "-u", "hadoop", "namenode", "hdfs", "dfs", "-mkdir", "-p", f"{HIVE_DATADIR}/external"], check=False)
run_command(["docker", "exec", "-u", "hadoop", "namenode", "hdfs", "dfs", "-chown", "-R", "hive:hive", f"{HIVE_USERDIR}"], check=False)
run_command(["docker", "exec", "-u", "hadoop", "namenode", "hdfs", "dfs", "-chmod", "-R", "777", f"{HIVE_USERDIR}"], check=False)
for hdfs_path in ["/tmp/hive", f"{HIVE_DATADIR}/managed", f"{HIVE_DATADIR}/external"]:
    run_command(["docker", "exec", "-u", "hadoop", "namenode", "hdfs", "dfs", "-setfacl", "-m", "default:user:hive:rwx,default:group:hive:rwx,default:mask::rwx", hdfs_path], check=True)

# %% [markdown]
# ## 15. Start Hive
#
# - **What:** starts the three services and waits until each health check passes.
# - **Why:** HiveServer2 starts only after the metastore, and the metastore only after PostgreSQL.
# - **How:** `docker compose up -d --wait --remove-orphans`.
# - 📄 [docker compose up](https://docs.docker.com/reference/cli/docker/compose/up/)

# %% vscode={"languageId": "markdown"}
run_command(["docker", "compose", "-f", "hive-cluster.docker-compose.yml", "up", "-d", "--wait", "--remove-orphans"])

# %% [markdown]
# ## 16. Beeline folder
#
# - **What:** creates `/home/hive/.beeline` owned by `hive` inside `hive-server2`.
# - **Why:** Beeline stores its history there and warns when it cannot.
# - **How:** `docker exec -u root hive-server2 bash -c "mkdir -p ... && chown -R hive:hive ..."`.
# - 📄 [Setting up HiveServer2](https://hive.apache.org/docs/latest/admin/setting-up-hiveserver2/)

# %%
run_command(["docker", "exec", "-u", "root", "hive-server2", "bash", "-c", "mkdir -p /home/hive/.beeline && chown -R hive:hive /home/hive"], check=False)

# %% [markdown]
# ## 17. Tez libraries in HDFS
#
# - **What:** builds `dist-lib.tar.gz` (Tez plus Hive's `commons-collections` and `commons-lang`) inside `hive-server2` and uploads it to `/apps/dist-lib/` in HDFS.
# - **Why:** every Tez task on YARN downloads its libraries from `tez.lib.uris`; nothing is fetched from the internet.
# - **How:** a script run in `hive-server2` builds the tarball (removing duplicate SLF4J jars); `docker cp` moves it to `namenode`, which runs `hdfs dfs -put`; the local temporary files are deleted.
# - 📄 [Tez install (`tez.lib.uris`)](https://tez.apache.org/install.html) · [docker container cp](https://docs.docker.com/reference/cli/docker/container/cp/) · [FileSystem shell](https://hadoop.apache.org/docs/r3.4.3/hadoop-project-dist/hadoop-common/FileSystemShell.html)

# %%
import os

print("--- CONSOLIDANDO Y EMPAQUETANDO DISTRIBUTED CACHE LIB ---")

# Script que se ejecutará DENTRO de hive-server2 para armar el paquete unificado
build_tar_script = """#!/bin/bash
set -e

echo "1. Creando directorio unificado /tmp/dist-lib..."
rm -rf /tmp/dist-lib/* /tmp/dist-lib.tar.gz
mkdir -p /tmp/dist-lib/conf
mkdir -p /tmp/dist-lib/lib

echo "2. Copiando Tez nativo..."
cp -r /opt/tez/* /tmp/dist-lib/

echo "3. Inyectando commons-collections y commons-lang de Hive..."
cp /opt/hive/lib/commons-collections-*.jar /opt/hive/lib/commons-lang-*.jar /tmp/dist-lib/lib/ 2>/dev/null || true

echo "4. Generando log4j seguro..."
cat << 'EOF' > /tmp/dist-lib/conf/tez-container-log4j.properties
tez.root.logger=INFO,CLA
log4j.rootLogger=${tez.root.logger}
log4j.appender.CLA=org.apache.log4j.ConsoleAppender
log4j.appender.CLA.Target=System.out
log4j.appender.CLA.layout=org.apache.log4j.PatternLayout
log4j.appender.CLA.layout.ConversionPattern=%d{ISO8601} [%p] [%t] |%c{2}|: %m%n
EOF

echo "5. Eliminando SLF4J duplicados para evitar conflictos..."
rm -f /tmp/dist-lib/lib/slf4j-*.jar

echo "6. Comprimiendo el paquete final..."
cd /tmp/dist-lib
# El asterisco asegura que no haya carpetas intermedias, tal como YARN lo espera
tar -czf /tmp/dist-lib.tar.gz *

echo "Paquete construido con éxito."
"""

with open("build_dist_lib_tar.sh", "w", newline='\n', encoding="utf-8") as f:
    f.write(build_tar_script)

# Ejecutamos la construcción dentro de hive-server2
print("Construyendo el tarball dentro de hive-server2...")
run_command(["docker", "cp", "build_dist_lib_tar.sh", "hive-server2:/tmp/build_dist_lib_tar.sh"], check=False)
run_command(["docker", "exec", "-u", "root", "hive-server2", "bash", "/tmp/build_dist_lib_tar.sh"], check=False)

# Extraemos SOLO el tarball ya terminado y lo pasamos al namenode
print("Transfiriendo el tarball terminado al Namenode...")
run_command(["docker", "cp", "hive-server2:/tmp/dist-lib.tar.gz", "./dist-lib.tar.gz"], check=False)
run_command(["docker", "cp", "./dist-lib.tar.gz", "namenode:/tmp/dist-lib.tar.gz"], check=False)

# Subimos a HDFS desde el namenode a la nueva ruta
print("Subiendo a HDFS en /apps/dist-lib ...")

run_command(["docker", "exec", "namenode", "hdfs", "dfs", "-mkdir", "-p", "/apps/dist-lib"], check=False)
run_command(["docker", "exec", "namenode", "hdfs", "dfs", "-rm", "-r", "-f", "/apps/dist-lib/*"], check=False)
run_command(["docker", "exec", "namenode", "hdfs", "dfs", "-put", "/tmp/dist-lib.tar.gz", "/apps/dist-lib/dist-lib.tar.gz"], check=False)
run_command(["docker", "exec", "namenode", "hdfs", "dfs", "-chmod", "-R", "777", "/apps/dist-lib"], check=False)

print("✅ ¡ÉXITO! Distributed Cache unificado y subido a HDFS en /apps/dist-lib.")

# 4. Limpieza ultra rápida
os.remove("./dist-lib.tar.gz")
os.remove("./build_dist_lib_tar.sh")
print("Archivos temporales locales limpios.")
