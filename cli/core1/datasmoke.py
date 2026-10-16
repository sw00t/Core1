"""Data services smoke: one Kafka message, one Valkey key, one Postgres row per environment.

Uses the clients already inside each service's pod (kubectl exec with the admin kubeconfig), so the test needs no
extra images. Everything it writes is removed again.
"""
import time

from .clusters import kubectl

NS = "data"
KAFKA_POD = "events-dual-0"
KAFKA_BIN = "/opt/kafka/bin"


def _exec(settings, cluster, pod, script, container=None, stdin=None, timeout=90):
    args = ["-n", NS, "exec", "-i" if stdin is not None else "", pod]
    args = [a for a in args if a]
    if container:
        args += ["-c", container]
    return kubectl(settings, cluster, *args, "--", "sh", "-c", script, input=stdin, check=False, timeout=timeout)


def check_postgres(settings, cluster):
    marker = f"core1-smoke-{int(time.time())}"
    sql = (f"create table if not exists core1_smoke(v text); insert into core1_smoke values ('{marker}'); "
           f"select v from core1_smoke where v = '{marker}'; drop table core1_smoke;")
    r = _exec(settings, cluster, "core1-db-1", f'psql -U postgres -d core1 -tA -c "{sql}"', container="postgres")
    ok = r.returncode == 0 and marker in r.stdout
    return (f"{cluster.name}: postgres write and read", ok, "core1-db" if ok else (r.stderr or r.stdout).strip()[:200])


def check_valkey(settings, cluster):
    marker = f"core1-smoke-{int(time.time())}"
    cli = 'valkey-cli -a "$VALKEY_PASSWORD" --no-auth-warning'
    script = f"{cli} set core1:smoke {marker} EX 60 >/dev/null && {cli} get core1:smoke && {cli} del core1:smoke >/dev/null"
    r = _exec(settings, cluster, "valkey-0", script)
    ok = r.returncode == 0 and marker in r.stdout
    return (f"{cluster.name}: valkey set and get", ok, "valkey" if ok else (r.stderr or r.stdout).strip()[:200])


def check_kafka(settings, cluster):
    stamp = int(time.time())
    topic, marker = f"core1-smoke-{stamp}", f"core1-smoke-message-{stamp}"
    bs = "--bootstrap-server localhost:9092"
    produce = f"{KAFKA_BIN}/kafka-console-producer.sh {bs} --topic {topic}"
    r = _exec(settings, cluster, KAFKA_POD, produce, container="kafka", stdin=marker + "\n", timeout=120)
    if r.returncode != 0:
        return (f"{cluster.name}: kafka produce and consume", False, (r.stderr or r.stdout).strip()[-200:])
    consume = (f"{KAFKA_BIN}/kafka-console-consumer.sh {bs} --topic {topic} --from-beginning "
               f"--max-messages 1 --timeout-ms 30000")
    r = _exec(settings, cluster, KAFKA_POD, consume, container="kafka", timeout=120)
    ok = marker in r.stdout
    _exec(settings, cluster, KAFKA_POD, f"{KAFKA_BIN}/kafka-topics.sh {bs} --delete --topic {topic}", container="kafka")
    return (f"{cluster.name}: kafka produce and consume", ok, f"topic {topic}" if ok else (r.stderr or r.stdout).strip()[-200:])


def present(checkout):
    return (checkout / "platform" / "data").is_dir()


def run(settings):
    results = []
    for c in settings.clusters:
        if c.name == "mgmt":
            continue
        results += [check_postgres(settings, c), check_valkey(settings, c), check_kafka(settings, c)]
    return results
