"""Conservative Linux local-destination checks; no SAP or global iowait inference."""
from pathlib import Path
import os
import time


# Policy budget only: never cancels a syscall or substitutes for durable readback.
LOCAL_PERSISTENCE_SECONDS = 10.0


class PersistenceBlocked(RuntimeError):
    pass


def device_for(root):
    """Bind metrics to the backing device, including the parent of a partition.

    Unknown/network/stacked devices fail closed: their durability is not inferred
    from a successful cached write. No device configuration is changed.
    """
    dev = root.stat().st_dev
    node = Path(f'/sys/dev/block/{os.major(dev)}:{os.minor(dev)}').resolve(strict=True)
    if (node / 'partition').exists():
        node = node.parent
    if not (node / 'device').exists() or (node / 'slaves').is_dir() and any((node / 'slaves').iterdir()):
        raise PersistenceBlocked('unsupported_backing_device')
    if (node / 'ro').read_text().strip() != '0':
        raise PersistenceBlocked('backing_device_read_only')
    return node


def capacity(root):
    stat = os.statvfs(root)
    # Headroom for this bounded JSON capture, not a capacity benchmark.
    if stat.f_flag & os.ST_RDONLY:
        raise PersistenceBlocked('destination_read_only')
    if stat.f_bavail * stat.f_frsize < 64 * 1024 * 1024 or stat.f_favail < 128:
        raise PersistenceBlocked('destination_capacity_insufficient')
    return dict(available_bytes=stat.f_bavail * stat.f_frsize, available_inodes=stat.f_favail)


def counters(device):
    values = [int(v) for v in (device / 'stat').read_text().split()]
    if len(values) < 11:
        raise PersistenceBlocked('device_metrics_unavailable')
    return values


def interval(before, after, seconds):
    if seconds <= 0 or any(a < b for i, (b, a) in enumerate(zip(before, after)) if i != 8):
        raise PersistenceBlocked('invalid_device_metrics')
    completed = after[0] - before[0] + after[4] - before[4]
    service_ms = after[3] - before[3] + after[7] - before[7]
    if len(before) >= 17 and len(after) >= 17:
        completed += after[15] - before[15]
        service_ms += after[16] - before[16]
    return dict(busy_fraction=(after[9] - before[9]) / (seconds * 1000),
                average_queue=(after[10] - before[10]) / (seconds * 1000),
                await_ms=service_ms / completed if completed else 0,
                inflight=after[8])


def pressured(sample):
    # A conservative bounded-capture policy, not a diagnosis of disk failure.
    return (sample['await_ms'] > 250 or
            sample['busy_fraction'] >= .8 and sample['average_queue'] >= 4 or
            sample['inflight'] >= 8 and sample['busy_fraction'] >= .8)


def preflight(root, *, sleep=time.sleep, clock=time.monotonic):
    """Two short read-only device intervals; generic CPU iowait is not an input."""
    try:
        result = capacity(root)
        device = device_for(root)
        samples = []
        previous, start = counters(device), clock()
        for _ in range(2):
            sleep(1)
            current, end = counters(device), clock()
            samples.append(interval(previous, current, end - start))
            previous, start = current, end
        result.update(device=device.name, samples=samples, sap_status='NOT_MEASURED')
        if all(pressured(s) for s in samples):
            raise PersistenceBlocked('destination_device_sustained_pressure:' + str(result))
        return result
    except OSError as exc:
        raise PersistenceBlocked('destination_metrics_unavailable') from exc


def verify_probe(root, save, digest, sync_directory, *, clock=time.monotonic):
    """One tiny durable transaction, only an additional check, never sole proof.

    The caller must first pass device/capacity checks and validate its complete
    copied prefix. A slow syscall is allowed to finish; no abandoned fsync worker.
    """
    path = root / '.persistence-probe.json'
    if path.exists() or path.with_suffix('.json.tmp').exists():
        raise PersistenceBlocked('preexisting_probe')
    started = clock()
    try:
        save(path, {'probe': 'bounded-durable-roundtrip-v1'})
        import hashlib
        expected = hashlib.sha256(b'{"probe": "bounded-durable-roundtrip-v1"}\n').hexdigest()
        if digest(path) != expected:
            raise PersistenceBlocked('probe_readback_mismatch')
        path.unlink()
        sync_directory(root)
        elapsed = clock() - started
        if elapsed > LOCAL_PERSISTENCE_SECONDS:
            raise PersistenceBlocked('destination_sync_latency_exceeded')
        return dict(roundtrip_ms=elapsed * 1000)
    except OSError as exc:
        raise PersistenceBlocked('destination_probe_write_failed') from exc
